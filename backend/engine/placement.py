"""
Placing classes that the generator could not place -- inside the scheduling dashboard, with the same rules as generation.

A class (one subject of one section) is UNPLACED when fewer class minutes are saved for it than its units require.
`resolve_groups` places it the way the GTI class program is worked out by hand, from the cheapest change to the biggest:

  1. place it in a free (teacher, room, time) -- nothing else moves;
  2. otherwise find the windows where only a few other classes are in the way (a busy room, a busy teacher, the section's
     own other class) and RE-SOLVE those classes together with this one: a blocking class takes another room, another
     qualified teacher or another time, exactly as a planner would swap them on the paper class program;
  3. the lecture of a lab is always re-solved with its lab, so "lecture before lab" is kept.

Every re-solve uses engine.scheduler.generate_schedule (teacher / room / section overlap, qualified teachers, availability, room
ownership and capacity, lab rooms, workload cap, lecture-before-lab, one day per minor subject) with everything else locked in
place, and the result is checked again with engine.conflict_report.scan. A step that fails or creates a clash is rolled back,
so a class is only reported "placed" when the saved schedule is verified clean.

Only classes the user owns are moved: the Registrar's Gen Ed (minor) classes, or a Dean's major classes of their own college;
approved / published classes and shared (merged) Gen Ed classes are never touched.
"""
from collections import defaultdict

from django.db import transaction

from . import scheduler as S
from .conflict_report import scan
from .models import Log, Schedule, TimeSlot

MAX_MOVED = 8              # most blocking classes re-solved together with the leftover class
TIME_BUDGET = 12           # seconds the search may use for one re-solve


class _Undo(Exception):
    pass


def _mins(t):
    return S._slot_minutes(t)


def expected_minutes(subject):
    total = 0
    for h in S.blocks_for_subject(subject):
        total += int(round(float(h) * 60)) * (2 if isinstance(h, S.PairHours) else 1)
    return total


def _row_minutes(row):
    return _mins(row.timeslot.end_time) - _mins(row.timeslot.start_time)


def _query():
    return Schedule.objects.select_related("teacher__user", "room", "section__program", "timeslot", "subject__program")


def incomplete_groups(semester, *, program_id=None, year_level=None, section_id=None, subject_id=None, kind=None,
                      departments=None):
    """[(section, subject, placed_minutes, expected_minutes)] for every class that has fewer minutes than its units need."""
    from curriculum.models import Subject
    from .models import Section
    secs = Section.objects.filter(semester=semester).select_related("program")
    if program_id:
        secs = secs.filter(program_id=program_id)
    if year_level and year_level != "All":
        secs = secs.filter(year_level=year_level)
    if section_id:
        secs = secs.filter(pk=section_id)
    if departments is not None:
        secs = secs.filter(program__department__in=departments)
    secs = list(secs)
    placed = defaultdict(int)
    for sec_id, sub_id, st, en in Schedule.objects.filter(section__in=secs).values_list(
            "section_id", "subject_id", "timeslot__start_time", "timeslot__end_time"):
        placed[(sec_id, sub_id)] += _mins(en) - _mins(st)
    subs = Subject.objects.filter(program__in={s.program_id for s in secs}, semester=semester).select_related("program")
    if kind:
        subs = subs.filter(classification=kind)
    if subject_id:
        subs = subs.filter(pk=subject_id)
    by_prog_year = defaultdict(list)
    for sub in subs:
        by_prog_year[(sub.program_id, sub.year_level)].append(sub)
    out = []
    for sec in secs:
        for sub in by_prog_year.get((sec.program_id, sec.year_level), []):
            need = expected_minutes(sub)
            have = placed.get((sec.id, sub.id), 0)
            if have < need:
                out.append((sec, sub, have, need))
    return out


def _can_edit(user, row):
    """May this user move this saved class?"""
    if row.status != "draft" or getattr(row, "merge_key", ""):
        return False
    role = getattr(user, "role", "")
    minor = row.subject.classification == "minor"
    if role == "registrar":
        return minor
    if role == "faculty" and getattr(user, "faculty_type", "") == "dean":
        return (not minor) and row.section.program.department in (user.departments or [])
    return False


class _Ctx:
    """Everything the generator needs, loaded once per call."""

    def __init__(self, semester, school_year):
        from faculty.models import FacultyProfile
        from rooms.models import Room
        from . import workload as wl
        from rooms.models import DepartmentBuilding
        from .views import _build_availability_rules
        self.teachers = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(user__is_active=True))          # a deactivated teacher is never given a class
        self.rooms = list(Room.objects.all())
        from .college_break import allowed_slots
        self.timeslots = allowed_slots(list(TimeSlot.objects.all()))
        self.av = _build_availability_rules(self.teachers, self.timeslots, school_year, semester)
        lim = wl.limits()
        self.caps = {t.id: wl.limit_for(t, lim) for t in self.teachers} if lim["policy"] == "strict" else None
        self.dept_building = {d.department: d.building for d in DepartmentBuilding.objects.all()}
        self.spec = {t.id: {f.id for f in t.specializations.all()} for t in self.teachers}
        self.block_slots = {}

    def slots_for(self, hours):
        if hours not in self.block_slots:
            self.block_slots[hours] = S.build_block_slots(self.timeslots, hours)
        return self.block_slots[hours]


def _gkey(row):
    return (row.section_id, row.subject_id)


def _describe(rows):
    """'Tue 13:00-16:00 Comp Lab C (Teacher)' for the rows of one class."""
    parts = []
    for r in sorted(rows, key=lambda x: (x.timeslot.day, _mins(x.timeslot.start_time))):
        parts.append([r.timeslot.day[:3], _mins(r.timeslot.start_time), _mins(r.timeslot.end_time), r.room.name,
                      r.teacher.user.get_full_name().strip() or r.teacher.user.username])
    merged = []
    for p in parts:
        if merged and merged[-1][0] == p[0] and merged[-1][2] == p[1] and merged[-1][3] == p[3]:
            merged[-1][2] = p[2]
        else:
            merged.append(p)
    f = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return "; ".join(f"{d} {f(s)}-{f(e)} {room} ({t})" for d, s, e, room, t in merged)


def _candidates(ctx, sub, sec, biggest_only=False):
    cands = []
    blocks = S.blocks_for_subject(sub)
    for h in sorted({float(x) for x in blocks}, reverse=True)[: (1 if biggest_only else 2)]:
        hours = next(x for x in blocks if float(x) == h)
        cands += S.build_domain(sec, sub, ctx.teachers, ctx.rooms, ctx.slots_for(hours), ctx.av, ctx.spec,
                                dept_building=ctx.dept_building)
    return cands


def _is_owned_lab(room):
    return getattr(room, "room_type", "") == "lab" and bool(getattr(room, "department", None))


def _free_rooms_for(ctx, section, subject, rows_all, day, s0, e0, skip_ids):
    """Non-lab rooms this lecture may use that nobody holds on `day` between s0 and e0."""
    from rooms import rules as rr
    gym = any(getattr(r, "room_type", "") == "gym" for r in ctx.rooms)
    ok = [r for r in ctx.rooms if S._room_matches_subject(r, subject, gym)]
    ok = rr.allowed_rooms(ok, getattr(section.program, "department", None), lab_subject=False, major=subject.classification != "minor")
    asg = rr.assignment_for(subject.id)
    if asg and asg["fixed"]:
        return []
    if subject.classification != "minor" and rr.designated_rooms(ctx.rooms, getattr(section.program, "department", None)) is not None:
        return []                 # Computer Studies majors stay in Comp Lab C / D: no move to an ordinary lecture room
    size = rr.effective_size(section, subject)
    ok = [r for r in ok if not _is_owned_lab(r) and not (size and (r.capacity or 0) and r.capacity < size)]
    busy = {r.room_id for r in rows_all if r.id not in skip_ids and r.timeslot.day[:3] == day
            and _mins(r.timeslot.start_time) < e0 and _mins(r.timeslot.end_time) > s0}
    ok = [r for r in ok if r.id not in busy]
    ok.sort(key=lambda r: (S._room_preference(r, section, subject, ctx.dept_building), r.id))
    return ok


def _evict_lectures(ctx, user, semester, sec, sub, rows_all, movable):
    """GTI rule: a department's laboratory is kept for its lab classes. When a lab class has no room, lectures sitting in
    that lab are moved to a free lecture room (same teacher, same time) -- no search, nothing else changes.
    Returns the list of moved descriptions (empty when nothing could be moved)."""
    lab_ids = {r.id for t, r, sl in _candidates(ctx, sub, sec, biggest_only=True) if _is_owned_lab(r)}
    if not lab_ids:
        return []
    by_block = defaultdict(list)
    for r in rows_all:
        if r.room_id in lab_ids and r.subject.lab_units == 0 and movable.get(_gkey(r), False):
            by_block[(_gkey(r), r.room_id, r.timeslot.day[:3])].append(r)
    moved = []
    try:
        with transaction.atomic():
            changed_ids = set()
            for (gk, room_id, day), rows in by_block.items():
                rows.sort(key=lambda x: _mins(x.timeslot.start_time))
                runs, cur = [], [rows[0]]
                for r in rows[1:]:                                 # back-to-back hours = one block
                    if _mins(r.timeslot.start_time) == _mins(cur[-1].timeslot.end_time) and r.teacher_id == cur[-1].teacher_id:
                        cur.append(r)
                    else:
                        runs.append(cur); cur = [r]
                runs.append(cur)
                for run in runs:
                    s0, e0 = _mins(run[0].timeslot.start_time), _mins(run[-1].timeslot.end_time)
                    cands = _free_rooms_for(ctx, run[0].section, run[0].subject, rows_all, day, s0, e0, {x.id for x in run})
                    cands = [c for c in cands if not any(x.room_id == c.id and x.id not in {y.id for y in run}
                                                         and x.timeslot.day[:3] == day and _mins(x.timeslot.start_time) < e0
                                                         and _mins(x.timeslot.end_time) > s0 for x in rows_all)]
                    if not cands:
                        continue
                    new_room = cands[0]
                    old_name = run[0].room.name
                    for r in run:
                        r.room = new_room
                        r.save(update_fields=["room"])
                        changed_ids.add(r.id)
                    # later blocks of the same pass must see the room as taken
                    for r in rows_all:
                        if r.id in {x.id for x in run}:
                            r.room = new_room
                    moved.append({"section": str(run[0].section), "subject": str(run[0].subject),
                                  "from": f"{day} {s0 // 60:02d}:{s0 % 60:02d}-{e0 // 60:02d}:{e0 % 60:02d} {old_name}",
                                  "to": f"{new_room.name} (same teacher and time)"})
            if changed_ids and scan(semester=semester, involving_ids=changed_ids, limit=5)["total"]:
                raise _Undo()
    except _Undo:
        return []
    return moved


def _blocker_sets(ctx, sec, sub, rows_by_day, group_movable):
    """For the candidate windows of this class: the set of OTHER classes standing in the way (fewest first)."""
    seen, sets = set(), []
    for teacher, room, slot in _candidates(ctx, sub, sec):
        parts = slot.parts if isinstance(slot, S.PairSlot) else (slot,)
        blockers, ok = set(), True
        for part in parts:
            s0, e0 = _mins(part.start_time), _mins(part.end_time)
            for rs, re_, row in rows_by_day.get(part.day[:3], ()):
                if re_ <= s0 or rs >= e0:
                    continue
                if row.teacher_id == teacher.id or row.room_id == room.id or row.section_id == sec.id:
                    k = _gkey(row)
                    if not group_movable.get(k, False):
                        ok = False
                        break
                    blockers.add(k)
            if not ok:
                break
        if ok and blockers and len(blockers) <= MAX_MOVED:
            fs = frozenset(blockers)
            if fs not in seen:
                seen.add(fs)
                sets.append(fs)
    sets.sort(key=len)
    return sets


def _try(ctx, group_objs, remove_keys, rows_all, semester, school_year, budget=TIME_BUDGET):
    """One re-solve of `remove_keys` with everything else locked, inside a savepoint. (ok, new_ids, removed_ids)."""
    try:
        with transaction.atomic():
            by_sec = defaultdict(list)
            for k in remove_keys:
                s2, b2 = group_objs[k]
                by_sec[s2].append(b2)
            locked = [r for r in rows_all if _gkey(r) not in remove_keys]
            placed, unresolved = S.generate_schedule(
                dict(by_sec), ctx.teachers, ctx.rooms, ctx.timeslots, ctx.av, max_steps=200000, locked_assignments=locked,
                time_budget_seconds=budget, dept_building=ctx.dept_building, teacher_caps=ctx.caps)
            if unresolved:
                raise _Undo()
            old = [r for r in rows_all if _gkey(r) in remove_keys]
            year_of = {_gkey(r): r.school_year for r in old}
            Schedule.objects.filter(id__in=[r.id for r in old]).delete()
            made = Schedule.objects.bulk_create([
                Schedule(subject=a.subject, teacher=a.teacher, room=a.room, section=a.section, timeslot=a.timeslot,
                         school_year=year_of.get((a.section.id, a.subject.id)) or school_year, status="draft",
                         term=a.section.semester) for a in placed])
            new_ids = [o.id for o in made if o.id is not None]
            if new_ids and scan(semester=semester, involving_ids=set(new_ids), limit=5)["total"]:
                raise _Undo()
            return True, new_ids, [r.id for r in old]
    except _Undo:
        return False, [], []


def resolve_groups(user, groups, semester, school_year="", log=True, overrides=None):
    """groups: [(section, subject)]. Returns {"results": [...], "new_ids": [...], "removed_ids": [...]}.
    Each result: section / subject (+ ids), status ("placed" | "unplaced" | "not_allowed"), method, moved, reason."""
    from rooms import rules as room_rules
    ctx = _Ctx(semester, school_year)
    asg = room_rules.load_assignments(
        set(Schedule.objects.filter(section__semester=semester).values_list("subject_id", flat=True))
        | {sub.id for _s, sub in groups})
    asg.update(overrides or {})            # rooms the Dean picked in the preview for this run stay fixed while re-arranging
    tok = room_rules.use_assignments(asg)
    try:
        return _resolve(ctx, user, groups, semester, school_year, log)
    finally:
        room_rules.release_assignments(tok)


def _resolve(ctx, user, groups, semester, school_year, log):
    results, all_new, all_removed = [], [], []
    role = getattr(user, "role", "")
    is_dean = role == "faculty" and getattr(user, "faculty_type", "") == "dean"
    for sec, sub in groups:
        res = {"section": str(sec), "subject": str(sub), "section_id": sec.id, "subject_id": sub.id,
               "program_id": sec.program_id, "year_level": sec.year_level, "moved": [], "method": "", "reason": ""}
        results.append(res)
        minor = sub.classification == "minor"
        if not ((role == "registrar" and minor) or (is_dean and not minor and sec.program.department in (user.departments or []))):
            res.update(status="not_allowed", reason=("Gen Ed (minor) classes are placed by the Registrar." if minor
                                                      else "Major classes are placed by the Dean of the program's college."))
            continue
        rows_all = list(_query().filter(section__semester=semester))
        mine = [r for r in rows_all if _gkey(r) == (sec.id, sub.id)]
        if sum(_row_minutes(r) for r in mine) >= expected_minutes(sub):
            res.update(status="placed", method="already placed")
            continue
        by_group = defaultdict(list)
        for r in rows_all:
            by_group[_gkey(r)].append(r)
        movable = {k: all(_can_edit(user, r) for r in rs) for k, rs in by_group.items()}
        me = (sec.id, sub.id)
        movable[me] = all(_can_edit(user, r) for r in mine)
        if not movable[me]:
            res.update(status="unplaced", reason="Some saved periods of this class are approved/published or shared; "
                                                  "move them back to draft first.")
            continue
        group_objs = {k: (rs[0].section, rs[0].subject) for k, rs in by_group.items()}
        group_objs[me] = (sec, sub)
        base = {me}
        if sub.code.endswith("L"):                       # a lab is re-solved with its lecture (lecture-before-lab)
            for k, (s2, b2) in group_objs.items():
                if k[0] == sec.id and b2.code == sub.code[:-1] and movable.get(k):
                    base.add(k)
        rows_by_day = defaultdict(list)
        for r in rows_all:
            if _gkey(r) not in base:
                rows_by_day[r.timeslot.day[:3]].append((_mins(r.timeslot.start_time), _mins(r.timeslot.end_time), r))
        plans = [frozenset(base)]
        sets = _blocker_sets(ctx, sec, sub, rows_by_day, movable)
        for limit in (1, 2, 4, MAX_MOVED):
            union = set()
            for fs in sets[:80]:
                if len(union | fs) <= limit:
                    union |= fs
                if len(union) >= limit:
                    break
            plan = frozenset(base | union)
            if plan not in plans:
                plans.append(plan)
        done = False
        evicted = []
        for n_plan, plan in enumerate(plans):
            if n_plan == 1 and sub.lab_units > 0:
                # the cheap GTI fix first: lectures sitting in the department's lab go to lecture rooms
                evicted = _evict_lectures(ctx, user, semester, sec, sub, rows_all, movable)
                if evicted:
                    rows_all = list(_query().filter(section__semester=semester))
                    mine = [r for r in rows_all if _gkey(r) == me]
                    by_group = defaultdict(list)
                    for r in rows_all:
                        by_group[_gkey(r)].append(r)
                    group_objs.update({k: (rs[0].section, rs[0].subject) for k, rs in by_group.items()})
                    group_objs[me] = (sec, sub)
                    ok, new_ids, old_ids = _try(ctx, group_objs, plans[0], rows_all, semester, school_year, budget=4)
                    if ok:
                        all_new += new_ids; all_removed += old_ids
                        res.update(status="placed", moved=evicted, method=f"moved {len(evicted)} lecture(s) out of the laboratory")
                        done = True
                        break
            before = {k: _describe(by_group[k]) for k in plan if k in by_group}
            ok, new_ids, old_ids = _try(ctx, group_objs, plan, rows_all, semester, school_year,
                                         budget=TIME_BUDGET if n_plan >= len(plans) - 1 else 2 + n_plan)
            if not ok:
                continue
            all_new += new_ids
            all_removed += old_ids
            after = defaultdict(list)
            for r in _query().filter(pk__in=new_ids):
                after[_gkey(r)].append(r)
            for k in plan:
                if k not in base and before.get(k) != _describe(after.get(k, [])):
                    s2, b2 = group_objs[k]
                    res["moved"].append({"section": str(s2), "subject": str(b2), "from": before.get(k, ""),
                                         "to": _describe(after.get(k, []))})
            res["moved"] = evicted + res["moved"]
            extra = len(plan) - len(base)
            res.update(status="placed", method=("placed in a free time" if not extra
                                                else f"re-arranged {len(res['moved'])} other class(es) to make room"))
            if log:
                Log.objects.create(action="UPDATE", schedule_id=0, user=user,
                                   details=f"Unplaced class placed: {sub} for {sec} ({res['method']})")
            done = True
            break
        if not done:
            res.update(status="unplaced", reason=_why_not(ctx, sec, sub, rows_by_day, movable))
    return {"results": results, "new_ids": all_new, "removed_ids": all_removed}


def _why_not(ctx, sec, sub, rows_by_day, movable):
    """What is in the way when even re-arranging does not help, and who can change it (never 'add rooms or faculty')."""
    cands = _candidates(ctx, sub, sec, biggest_only=True)
    if not cands:
        from .qualification import qualified_teachers as _q, why_nobody as _wn
        if not _q(sub, sec, ctx.teachers, ctx.spec):
            return _wn(sub, sec, ctx.teachers, ctx.spec)
        rr = __import__("rooms.rules", fromlist=["x"])
        win = rr.time_window_for(sub.id)
        if win:
            hrs = S.blocks_for_subject(sub)
            fits = any(win[0] <= S._slot_minutes(b.start_time) and S._slot_minutes(b.end_time) <= win[1]
                       for h in hrs for b in S.with_half_blocks(S.build_block_slots(ctx.timeslots, h), win))
            if not fits:
                return ("No class period fits between the chosen Start and End Time: this subject needs a block of "
                        + " / ".join(f"{float(h):g}" for h in hrs) + " hour(s) in one piece. Widen the Start / End Time in the curriculum "
                        "preview, or set it to 'Any time'.")
            lab = lambda m: f"{((m // 60 + 11) % 12) + 1}:{m % 60:02d} {'AM' if m < 720 else 'PM'}"
            return (f"No {sub.code} class period inside the chosen {lab(win[0])} – {lab(win[1])} has a qualified teacher who is available "
                    "(or the chosen room is taken at every such time). Widen the Start / End Time in the curriculum preview, set it to "
                    "'Any time', or ask the qualified teachers to submit availability inside that window.")
        return ("No qualified teacher is available for this class in a room that suits it. "
                "Check the teachers' availability in the Faculty tab and the room chosen for this subject.")
    held = defaultdict(int)
    for teacher, room, slot in cands[:4000]:
        s0, e0 = _mins(slot.start_time), _mins(slot.end_time)
        for rs, re_, row in rows_by_day.get(slot.day[:3], ()):
            if re_ <= s0 or rs >= e0:
                continue
            if (row.teacher_id == teacher.id or row.room_id == room.id or row.section_id == sec.id) \
                    and not movable.get(_gkey(row), False):
                who = "the Registrar" if row.subject.classification == "minor" else f"the Dean of {row.section.program.department}"
                state = "approved/published or shared" if (row.status != "draft" or getattr(row, "merge_key", "")) \
                    else f"owned by {who}"
                held[(str(row.subject), str(row.section), state)] += 1
    # Is the (designated) room taken at EVERY possible time? Then say so plainly: that is the real reason, not a search limit.
    room_names = sorted({r.name for _t, r, _sl in cands})
    if cands and 1 <= len(room_names) <= 3:
        def _room_busy(room, slot):
            s0, e0 = _mins(slot.start_time), _mins(slot.end_time)
            return any(row.room_id == room.id for rs, re_, row in rows_by_day.get(slot.day[:3], ()) if rs < e0 and re_ > s0)
        if all(_room_busy(r, sl) for _t, r, sl in cands):
            return (f"{' and '.join(room_names)} {'is' if len(room_names) == 1 else 'are'} already booked at every possible time for this class "
                    f"(no free {'/'.join(f'{float(h):g}' for h in S.blocks_for_subject(sub))}-hour period is left in "
                    f"{'it' if len(room_names) == 1 else 'them'}). {sub.code} may only use "
                    f"{'this room' if len(room_names) == 1 else 'these rooms'}, so it stays unplaced rather than going to another room. "
                    "Free a period in the room (move or remove another class that uses it) or have the IT Admin make another designated room available, "
                    "then press Resolve.")
    if held:
        top = sorted(held.items(), key=lambda kv: -kv[1])[:3]
        return ("Free windows are held by classes this account cannot move: "
                + "; ".join(f"{s} ({sc}) - {st}" for (s, sc, st), _n in top)
                + ". Ask that owner to move one of them (or move it back to draft), then press Resolve again.")
    return ("No arrangement was found within the time limit even after moving the blocking classes. "
            "Press Resolve again - it tries a different arrangement each time.")
