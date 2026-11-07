"""
SHS / JHS scheduling engine -- independent of the college engine.

A weekly timetable is built for every section of a level (or one grade level) for one grading
period. Hard rules (never broken; anything that can't satisfy them is reported as unresolved with
the reason):
  * every class sits inside the grade level's daily window (SHS Grade 11 07:00-12:30, Grade 12
    12:30-18:30, JHS 08:00-14:00 -- read from GradeWindow, so administrators can change them)
  * a teacher teaches one class at a time, inside their availability, within their daily and weekly caps
  * a room hosts one class at a time and is the right type / size, in the level's own building (and
    floor, for JHS), active
  * a section attends one class at a time
  * a teacher must hold the subject's specialization
  * every subject gets its sessions_per_week periods
"""
import random
from collections import defaultdict
from datetime import time

from .models import (Availability, CurriculumSubject, Faculty, GradeWindow, Room, ScheduleEntry,
                     ScheduleRun, Section, SchoolLevelConfig, DAYS)

DAY_KEYS = [d for d, _ in DAYS]


def to_min(t):
    return t.hour * 60 + t.minute


def to_time(m):
    return time(m // 60, m % 60)


def window_breaks(window):
    """[(label, start_min, end_min), ...] breaks of a grade level's window (SHS: one "Break"; JHS: "Recess" and "Lunch"), in time order (only valid ones)."""
    out = []
    if window.level == "SHS":            # SHS: a single 30-minute break (no separate recess / lunch)
        pairs = (("Break", window.break_start, window.break_end),)
    else:                                # JHS: recess and lunch
        pairs = (("Recess", window.recess_start, window.recess_end), ("Lunch", window.lunch_start, window.lunch_end))
    for label, a, b in pairs:
        if a and b and to_min(b) > to_min(a):
            out.append((label, to_min(a), to_min(b)))
    return sorted(out, key=lambda x: x[1])


def build_grid(config, window):
    """[(start_min, end_min), ...] class periods for one grade level's daily window. Recess and lunch (when set on the window) are
    skipped: a period never overlaps them. Without explicit breaks the older rule applies (a short break after every `break_every`)."""
    start, end = to_min(window.start_time), to_min(window.end_time)
    p, brk, every = config.period_minutes, config.break_minutes, max(config.break_every, 1)
    breaks = window_breaks(window)
    slots, cur, n = [], start, 0
    while cur + p <= end:
        hit = next((b for b in breaks if cur < b[2] and cur + p > b[1]), None)
        if hit:                                  # the period would touch a break: resume when the break is over
            cur = max(cur, hit[2]) if cur >= hit[1] else hit[2]
            continue
        slots.append((cur, cur + p))
        cur += p
        n += 1
        if not breaks and brk and n % every == 0:
            cur += brk
    return slots


def build_rows(config, window):
    """The whole school day for display: [("period", s, e) | ("Recess", s, e) | ("Lunch", s, e)] in time order. A break is shown
    even when it falls where a gap would be left."""
    rows = [("period", s, e) for s, e in build_grid(config, window)]
    rows += [(label, s, e) for label, s, e in window_breaks(window)]
    return sorted(rows, key=lambda r: (r[1], r[0] != "period"))


def eligible(faculty, subject):
    """A teacher is eligible when one of their specializations (or their department) equals one of the
    alternatives the subject accepts. `subject.specialization` holds alternatives separated by '|'
    (e.g. "English|Filipino"); when it is blank the learning area is used. Homeroom/guidance periods
    can be taken by any teacher."""
    if subject.category == "guidance":
        return True
    need = {x.strip().lower() for x in (subject.specialization or subject.learning_area or "").split("|") if x.strip()}
    have = set(faculty.spec_list)
    if faculty.department:
        have.add(faculty.department.strip().lower())
    return bool(need & have)


SHARED_ROOMS = ("Comp Lab B",)      # reserved for SHS and JHS together


class Problem:
    def __init__(self, level, academic_year, grading_period, grade_level, ignore_run_ids=()):
        self.level = level
        self.config = SchoolLevelConfig.objects.get(level=level)
        self.grade_level = grade_level
        self.windows = {w.grade_level: w for w in GradeWindow.objects.filter(level=level)}
        self.grids = {g: build_grid(self.config, w) for g, w in self.windows.items()}
        self.sections = list(Section.objects.filter(level=level, academic_year=academic_year, is_active=True,
                                                    grade_level=grade_level).select_related("strand", "adviser", "home_room"))
        self.rooms = list(Room.objects.filter(level=level, building=self.config.building, is_active=True))
        if self.config.floor is not None:
            self.rooms = [r for r in self.rooms if r.floor == self.config.floor]
        # Rooms shared by SHS and JHS (Comp Lab B): usable by both levels whatever their own building/floor,
        # and a booking by one level blocks the other (same physical room -> one canonical id).
        self.canon_map = {}
        shared = list(Room.objects.filter(room_number__in=SHARED_ROOMS, is_active=True))
        groups = defaultdict(list)
        for r in shared:
            groups[(r.building, r.room_number)].append(r)
        for g in groups.values():
            for r in g:
                self.canon_map[r.id] = min(x.id for x in g)
        have = {r.id for r in self.rooms}
        self.rooms += [r for r in shared if r.level == level and r.id not in have]
        self.faculty = list(Faculty.objects.filter(level=level, is_active=True, user__is_active=True).select_related("user"))
        subs = CurriculumSubject.objects.filter(level=level, academic_year=academic_year, is_active=True,
                                                grade_level=grade_level, grading_period__in=[0, grading_period])
        self.subjects = list(subs.select_related("strand"))
        # availability windows per faculty/day
        self.avail = defaultdict(lambda: defaultdict(list))       # submitted Preferred + Available windows
        self.unavail = defaultdict(lambda: defaultdict(list))     # submitted Unavailable windows
        self.pref = defaultdict(lambda: defaultdict(list))        # submitted Preferred windows (tried first)
        for a in Availability.objects.filter(faculty__in=self.faculty):
            w = (to_min(a.start_time), to_min(a.end_time))
            (self.avail if a.available else self.unavail)[a.faculty_id][a.day].append(w)
            if a.available and getattr(a, "preference", "") == "preferred":
                self.pref[a.faculty_id][a.day].append(w)
        # what the OTHER grade levels' active timetables already use (a teacher is shared across grades)
        self.busy_teacher = defaultdict(set)     # (faculty_id) -> {(day, start_min)}
        self.busy_room = defaultdict(set)
        self.teacher_minutes = defaultdict(int)
        others = ScheduleRun.objects.filter(level=level, academic_year=academic_year, grading_period=grading_period) \
            .exclude(status="superseded").exclude(grade_level=grade_level).exclude(id__in=ignore_run_ids)
        others_all = ScheduleRun.objects.filter(academic_year=academic_year, grading_period=grading_period) \
            .exclude(status="superseded").exclude(id__in=ignore_run_ids)
        for e in ScheduleEntry.objects.filter(run__in=others_all.exclude(level=level, grade_level=grade_level),
                                              room_id__in=list(self.canon_map)).exclude(run__in=others):
            self.busy_room[self.canon(e.room_id)].add((e.day, to_min(e.start_time)))
        for e in ScheduleEntry.objects.filter(run__in=others):
            if e.teacher_id:
                self.busy_teacher[e.teacher_id].add((e.day, to_min(e.start_time)))
                self.teacher_minutes[e.teacher_id] += to_min(e.end_time) - to_min(e.start_time)
            if e.room_id:
                self.busy_room[self.canon(e.room_id)].add((e.day, to_min(e.start_time)))
        self.anchor = []        # Grade 11: another term's whole-year placements to repeat (set by services.generate)
        # pinned teaching assignments
        from .models import TeachingAssignment
        self.pinned = {(t.section_id, t.subject_id): t.faculty for t in TeachingAssignment.objects.filter(
            section__in=self.sections).select_related("faculty__user")}

    def canon(self, room_id):
        return self.canon_map.get(room_id, room_id)

    def subjects_for(self, section):
        out = []
        for s in self.subjects:
            if s.strand_id in (None, section.strand_id):
                out.append(s)
        # a strand-specific line overrides a generic one with the same code
        by_code = {}
        for s in out:
            if s.code not in by_code or (s.strand_id and not by_code[s.code].strand_id):
                by_code[s.code] = s
        return list(by_code.values())


# SHS / JHS: whether the time outside a teacher's submitted Available / Preferred windows may be used. True = today's rule (a hard
# limit). The comparison of the soft variant (like the college) is measured in the tests only; the setting is not changed here.
SUBMITTED_WINDOWS_ARE_HARD = True

TIER_PREFERRED, TIER_AVAILABLE, TIER_OUTSIDE = 0, 1, 2


def teacher_time_rule(P, fac, day, slot):
    """THE availability rule of the SHS / JHS generator, in one place (change it here only).
    Returns None when the teacher may NOT teach at this time, otherwise a tier used to order the choices (lower = tried first):
      * a time inside a window the teacher marked Unavailable                 -> None (always a hard block)
      * a teacher who submitted Available / Preferred windows, outside them   -> None (today's hard rule; TIER_OUTSIDE when
                                                                                 SUBMITTED_WINDOWS_ARE_HARD is False)
      * outside the teacher's preferred start / end on their profile          -> None (unchanged hard limit, set by the school)
      * inside a Preferred window -> TIER_PREFERRED; any other allowed time   -> TIER_AVAILABLE
    A teacher who has submitted nothing is free at any time not blocked otherwise. "Returned for correction" changes nothing here: the
    last submitted windows stay in use until the teacher submits again."""
    s, e = slot
    for us, ue in P.unavail[fac.id].get(day, []):
        if s < ue and e > us:
            return None
    if fac.preferred_start and fac.preferred_end:
        if s < to_min(fac.preferred_start) or e > to_min(fac.preferred_end):
            return None
    tier = TIER_AVAILABLE
    if P.avail.get(fac.id):
        if not any(s >= ws and e <= we for ws, we in P.avail[fac.id].get(day, [])):
            if SUBMITTED_WINDOWS_ARE_HARD:
                return None
            tier = TIER_OUTSIDE
    if any(s >= ws and e <= we for ws, we in P.pref[fac.id].get(day, [])):
        tier = TIER_PREFERRED
    return tier


def _free_for_teacher(P, fac, day, slot, taken_teacher):
    s, e = slot
    if (day, s) in taken_teacher[fac.id] or (day, s) in P.busy_teacher[fac.id]:
        return False
    return teacher_time_rule(P, fac, day, slot) is not None


def solve(P, seed=0, stats=None):
    """The generator: backtracking search with MRV and forward checking (basic_ed/search.py). Returns (assignments, unresolved)."""
    from .search import solve as _search
    return _search(P, seed=seed, stats=stats)


def solve_greedy(P, seed=0, attempt_limit=3):
    """The OLD generator (greedy, up to 3 shuffled restarts), kept only to measure the new search against it
    (tests and `manage.py compare_basic_ed_solvers`). Generate does not use it.
    Returns (assignments, unresolved). assignment = dict(section, subject, teacher, room, day, start, end)."""
    best = None
    for attempt in range(attempt_limit):
        rng = random.Random(seed + attempt)
        res = _solve_once(P, rng, shuffle=attempt > 0)
        if best is None or len(res[1]) < len(best[1]):
            best = res
        if not best[1]:
            break
    return best


def _solve_once(P, rng, shuffle):
    grid = P.grids.get(P.grade_level, [])
    cap_day = P.config.max_periods_per_teacher_day
    taken_sec = defaultdict(set)         # section_id -> {(day, start)}
    taken_teacher = defaultdict(set)
    taken_room = defaultdict(set)
    for rid, v in P.busy_room.items():
        taken_room[rid] |= v
    teacher_day = defaultdict(int)       # (fac_id, day) -> periods
    minutes = defaultdict(int, P.teacher_minutes)
    assignments, unresolved = [], []

    # Whole-year subjects (Grade 11 core) repeat exactly as in the other term's timetable, when still free
    anchored = set()
    for a in getattr(P, "anchor", []):
        if a.teacher is None or a.room is None or a.section_id not in {s.id for s in P.sections}:
            continue
        slot = (to_min(a.start_time), to_min(a.end_time))
        key = (a.day, slot[0])
        if slot not in grid:            # the other term's period is not on today's grid (recess/lunch or period length changed since)
            continue
        if (key in taken_sec[a.section_id] or key in taken_room[P.canon(a.room_id)] or not a.teacher.is_active
                or not _free_for_teacher(P, a.teacher, a.day, slot, taken_teacher)):
            continue
        taken_sec[a.section_id].add(key)
        taken_teacher[a.teacher_id].add(key)
        taken_room[P.canon(a.room_id)].add(key)
        teacher_day[(a.teacher_id, a.day)] += 1
        minutes[a.teacher_id] += slot[1] - slot[0]
        assignments.append(dict(section=a.section, subject=a.subject, teacher=a.teacher, room=a.room, day=a.day, start=slot[0], end=slot[1],
                                anchored=True))
        anchored.add((a.section_id, a.subject_id))
    # a subject only counts as anchored when ALL its periods were repeated; otherwise place it afresh
    need_n = {}
    for sec in P.sections:
        for sub in P.subjects_for(sec):
            need_n[(sec.id, sub.id)] = sub.sessions_per_week
    got = defaultdict(int)
    for a in assignments:
        got[(a["section"].id, a["subject"].id)] += 1
    for k in list(anchored):
        if got[k] != need_n.get(k, -1):
            anchored.discard(k)
            for a in [x for x in assignments if (x["section"].id, x["subject"].id) == k]:
                key = (a["day"], a["start"])
                taken_sec[k[0]].discard(key); taken_teacher[a["teacher"].id].discard(key); taken_room[P.canon(a["room"].id)].discard(key)
                teacher_day[(a["teacher"].id, a["day"])] -= 1; minutes[a["teacher"].id] -= a["end"] - a["start"]
                assignments.remove(a)

    tasks = []
    for sec in P.sections:
        for sub in P.subjects_for(sec):
            if (sec.id, sub.id) in anchored:
                continue
            cands = [f for f in P.faculty if eligible(f, sub)]
            pin = P.pinned.get((sec.id, sub.id))
            if sub.category == "guidance" and sec.adviser_id and not pin:
                pin = sec.adviser
            tasks.append((sec, sub, cands, pin))
    tasks.sort(key=lambda t: (len(t[2]) if not t[3] else 0, -t[1].sessions_per_week, t[1].required_room_type == "classroom"))
    if shuffle:
        rng.shuffle(tasks)
        tasks.sort(key=lambda t: len(t[2]) if not t[3] else 0)

    def rooms_for(sec, sub, day, slot):
        want = sub.required_room_type
        pool = [r for r in P.rooms if r.room_type == want and r.capacity >= sec.student_count]
        pool = [r for r in pool if (day, slot[0]) not in taken_room[P.canon(r.id)]]
        if sec.home_room_id and want == "classroom":
            pool.sort(key=lambda r: r.id != sec.home_room_id)
        return pool

    for sec, sub, cands, pin in tasks:
        need = sub.sessions_per_week
        if pin:
            cands = [pin]
        if not cands:
            unresolved.append(dict(section=sec, subject=sub, kind="no_eligible_teacher", needed=need, placed=0,
                                   message=f"No active {P.level} teacher is qualified for {sub.code} {sub.name} "
                                           f"(needs specialization '{sub.specialization or sub.learning_area}')."))
            continue
        cands = sorted(cands, key=lambda f: minutes[f.id])
        done, last_reason = False, ""
        for fac in cands:
            plan, reason = _plan_task(P, grid, sec, sub, fac, need, taken_sec, taken_teacher, taken_room, teacher_day, minutes, rooms_for, cap_day)
            if plan is not None:
                for day, slot, room in plan:
                    taken_sec[sec.id].add((day, slot[0]))
                    taken_teacher[fac.id].add((day, slot[0]))
                    taken_room[P.canon(room.id)].add((day, slot[0]))
                    teacher_day[(fac.id, day)] += 1
                    minutes[fac.id] += slot[1] - slot[0]
                    assignments.append(dict(section=sec, subject=sub, teacher=fac, room=room, day=day, start=slot[0], end=slot[1]))
                done = True
                break
            last_reason = reason
        if not done:
            unresolved.append(dict(section=sec, subject=sub, kind="no_slot", needed=need, placed=0, message=last_reason))
    return assignments, unresolved


def _plan_task(P, grid, sec, sub, fac, need, taken_sec, taken_teacher, taken_room, teacher_day, minutes, rooms_for, cap_day):
    """Pick `need` (day, slot, room) triples for one teacher, or (None, reason)."""
    max_min = (fac.max_weekly_hours or P.config.max_teacher_hours) * 60
    plan, used_days = [], defaultdict(int)
    local_sec, local_t, local_r, local_day = set(), set(), set(), defaultdict(int)
    fail = {"section": 0, "teacher": 0, "room": 0, "cap": 0}
    for _ in range(need):
        choice = None
        # prefer days this subject isn't on yet, and the section's lightest days
        day_load = {d: sum(1 for (dd, _s) in taken_sec[sec.id] if dd == d) + sum(1 for (dd, _s) in local_sec if dd == d) for d in DAY_KEYS}
        days = sorted(DAY_KEYS, key=lambda d: (used_days[d] >= 1, used_days[d], day_load[d]))
        for day in days:
            if used_days[day] >= 2:
                continue
            for slot in grid:
                key = (day, slot[0])
                if key in taken_sec[sec.id] or key in local_sec:
                    fail["section"] += 1
                    continue
                planned = sum(sl[1] - sl[0] for _d, sl, _r in plan)
                if minutes[fac.id] + planned + (slot[1] - slot[0]) > max_min:
                    fail["cap"] += 1
                    continue
                if teacher_day[(fac.id, day)] + local_day[day] >= cap_day:
                    fail["cap"] += 1
                    continue
                if key in local_t or not _free_for_teacher(P, fac, day, slot, taken_teacher):
                    fail["teacher"] += 1
                    continue
                pool = [r for r in rooms_for(sec, sub, day, slot) if (P.canon(r.id), day, slot[0]) not in local_r]
                if not pool:
                    fail["room"] += 1
                    continue
                choice = (day, slot, pool[0])
                break
            if choice:
                break
        if not choice:
            why = max(fail, key=fail.get)
            msg = {
                "section": "the section has no free period left",
                "teacher": f"{fac.full_name} has no free period inside their availability",
                "room": f"no free {sub.required_room_type.replace('_', ' ')} in {P.config.building}"
                        + (f" floor {P.config.floor}" if P.config.floor is not None else ""),
                "cap": f"{fac.full_name} would exceed the daily / weekly teaching-load limit",
            }[why]
            return None, (f"Could only place {len(plan)} of {need} periods of {sub.code} {sub.name} for {sec.name}: {msg}.")
        day, slot, room = choice
        plan.append(choice)
        used_days[day] += 1
        local_sec.add((day, slot[0]))
        local_t.add((day, slot[0]))
        local_r.add((P.canon(room.id), day, slot[0]))
        local_day[day] += 1
    return plan, ""
