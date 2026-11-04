"""
Exam Schedule generator -- greedy assignment (not full CSP backtracking, since
exam scheduling has far fewer variables than class scheduling and doesn't need
it), but uses the SAME shared conflict checker (engine.conflicts) as manual
exam creation, so anything it generates is guaranteed consistent with:
  - the other role's exam schedule (Dean vs Registrar)
  - regular class Schedule entries
  - exams it has already placed earlier in the same run
"""
from collections import defaultdict

from engine.conflicts import _get_tolerance_minutes
from engine.scheduler import _room_preference
from engine.models import TimeSlot
from rooms.models import Room
from faculty.models import FacultyProfile
from .models import ExamSchedule


def _minutes(t):
    if isinstance(t, str):
        parts = [int(x) for x in t.split(":")]
        return parts[0] * 60 + parts[1]
    return t.hour * 60 + t.minute


def generate_exam_schedule(**kw):
    """(created, unresolved strings) -- see generate_exam_schedule_detailed."""
    out = generate_exam_schedule_detailed(**kw)
    return out["created"], out["unresolved"]


class _Pair:
    """One exam sitting: a subject and ONE section, or (low enrollment) several sections of the same Gen Ed course that share a room.
    members = [(subject, section), ...]; every member keeps its own program's Subject row."""
    __slots__ = ("subject", "section", "members", "rooms", "n_pref", "why", "turn")

    def __init__(self, subject, section, members=None):
        self.subject, self.section = subject, section
        self.members = list(members or [(subject, section)])
        self.rooms, self.n_pref, self.turn = [], 0, 0
        self.why = {"section": 0, "room": 0, "proctor": 0}

    @property
    def size(self):
        return sum(getattr(sec, "student_count", 0) or 0 for _sub, sec in self.members)

    @property
    def merge_key(self):
        if len(self.members) < 2:
            return ""
        return f"exam|{self.subject.code}|{self.section.year_level}|{self.section.semester}|{min(sec.id for _s, sec in self.members)}"[:80]


def generate_exam_schedule_detailed(*, subjects, sections, exam_period, exam_dates, school_year, requesting_user,
                                    dept_building=None):
    """
    subjects / sections may span SEVERAL programs: a subject is paired with the sections of its OWN program and year level.

    Gen Ed (minor) subjects follow the college's exam-week practice: ONE subject = ONE common date and time, every section in its
    own room with its own proctor (e.g. Reading in Philippine History, 10-11AM, sections N24-0101A..F in 301M, 304M, 305M ...).
    If no hour suits every section, the sections are split over as few hours as possible. Program (major) subjects are placed
    one section at a time.

    Low enrollment: the same Gen Ed course (same code, title, units, year level and semester -- the rule engine.merging uses for shared
    classes) of several programs sits ONE exam together (one room, one hour, one proctor, rows tied by ExamSchedule.merge_key) when
    all their students fit one Gen Ed exam room, e.g. 5 BA + 15 CS + 15 IT = 35 students in a 40-seat room. Larger groups keep one
    room per section, as in the exam history. Lab subjects are never combined.

    Rules kept from before: proctor and room never overlap; a section may overlap a class or another exam only within the
    configured tolerance; checked against the weekly class schedule of that weekday and every exam on that real date; rooms follow
    exams.room_rules (CS labs -> Comp Lab C/D, Gen Ed rooms, Nursing labs ...). Room capacity is a preference for exams: a room
    that seats the section is used when one is free, otherwise the best room is used and reported as a capacity warning.

    Returns {"created", "unresolved" (strings), "pending" (dicts for the conflict pop-up), "capacity_warnings"}.
    """
    from engine.models import Schedule
    from exams.room_rules import exam_rooms
    from rooms.rules import fits_size

    rooms = list(Room.objects.filter(room_type__in=["lecture", "lab"]))
    faculty = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations"))
    from exams.proctors import ProctorPool
    pool = ProctorPool(faculty)
    exam_dates = list(exam_dates)
    subjects = list(subjects)
    sections = list(sections)
    tolerance = _get_tolerance_minutes()
    out = {"created": [], "unresolved": [], "pending": [], "capacity_warnings": []}
    if not exam_dates:
        out["unresolved"].append("No exam dates were provided.")
        return out

    ExamSchedule.objects.filter(
        subject__in=subjects, section__in=sections, exam_period=exam_period,
        school_year=school_year, is_manual_override=False,
    ).delete()

    classes_by_day = defaultdict(list)
    for r in Schedule.objects.filter(section__semester__in={s.semester for s in sections}).select_related("timeslot"):
        t = r.timeslot
        classes_by_day[t.day].append((_minutes(t.start_time), _minutes(t.end_time), r.teacher_id, r.room_id, r.section_id))
    exams_by_date = defaultdict(list)
    proctor_load = defaultdict(int)
    for e in ExamSchedule.objects.select_related("timeslot"):
        t = e.timeslot
        exams_by_date[e.exam_date].append((_minutes(t.start_time), _minutes(t.end_time), e.proctor_id, e.room_id, e.section_id))
        proctor_load[e.proctor_id] += 1

    slots_by_code = {}

    def timeslots_for(exam_date):
        code = exam_date.strftime("%a")[:3]
        if code not in slots_by_code:
            def _long(qs):
                return [t for t in qs if _minutes(t.end_time) - _minutes(t.start_time) >= 60]
            slots = _long(TimeSlot.objects.filter(day=code))
            slots_by_code[code] = sorted(slots or _long(TimeSlot.objects.all()), key=lambda x: (_minutes(x.start_time), x.id))
        return slots_by_code[code]

    def rows_at(exam_date, slot):
        s0, s1 = _minutes(slot.start_time), _minutes(slot.end_time)
        code = slot.day if slot.day else exam_date.strftime("%a")[:3]
        return s0, s1, [r for r in classes_by_day.get(code, []) + exams_by_date.get(exam_date, []) if min(s1, r[1]) > max(s0, r[0])]

    def section_free(section, rows, s0, s1):
        return sum(min(s1, r[1]) - max(s0, r[0]) for r in rows if r[4] == section.id) <= tolerance

    # ---- pairs and their rooms ----------------------------------------------------------------------------------------------
    pairs, index = [], 0
    for subject in subjects:
        mine = [s for s in sections if s.program_id == subject.program_id and s.year_level == subject.year_level]
        if not mine:
            out["unresolved"].append(f"No {subject.year_level} section found for {subject.code}.")
            continue
        for section in mine:
            pairs.append(_Pair(subject, section))

    def combine(minor_pairs):
        """First-fit-decreasing packing of the same Gen Ed course (by year level) into sittings that fit one exam room."""
        buckets = defaultdict(list)
        for p in minor_pairs:
            sub = p.subject
            buckets[((sub.title or "").strip().lower(), sub.lec_units, sub.lab_units, p.section.year_level)].append(p)
        packed = []
        for plist in buckets.values():
            lone = [p for p in plist if (p.subject.lab_units or 0) > 0 or not p.size]
            plist = [p for p in plist if p not in lone]
            # Computer Studies (CS + IT) sit together first; the other departments fill the seats that remain
            plist.sort(key=lambda p: (0 if "comput" in (p.section.program.department or "").lower() else 1, -p.size, p.section.id))
            cap = 0
            if plist:
                probe, _h, npf = exam_rooms(rooms, plist[0].section, plist[0].subject, lambda r: 0)
                cap = max([getattr(r, "capacity", 0) or 0 for r in probe[:npf]] or [0])
            bins = []
            for p in plist:
                for b in bins:
                    if cap and sum(x.size for x in b) + p.size <= cap:
                        b.append(p); break
                else:
                    bins.append([p])
            for b in bins:
                packed.append(b[0] if len(b) == 1 else _Pair(b[0].subject, b[0].section, [m for x in b for m in x.members]))
            packed += lone
        return packed

    from rooms.rules import may_use
    bycode = defaultdict(list)
    rest = []
    for p in pairs:
        (bycode[(p.subject.code, p.subject.semester)] if p.subject.classification == "minor" else rest).append(p)
    pairs = rest
    for plist in bycode.values():
        pairs += combine(plist)
    for p in pairs:
        p.turn = index
        index += 1
        section, subject = p.section, p.subject
        ordered, _hard, n_pref = exam_rooms(rooms, section, subject,
                                            lambda r, section=section, subject=subject: _room_preference(r, section, subject, dept_building),
                                            turn=p.turn)
        if len(p.members) > 1:                                   # every department of the sitting must be allowed to use the room
            depts = {getattr(sec.program, "department", None) for _s, sec in p.members}
            keep = [r for r in ordered if all(may_use(r, d) for d in depts)]
            n_pref = sum(1 for r in ordered[:n_pref] if r in keep)
            ordered = keep
        p.rooms, p.n_pref = ordered, n_pref

    def room_levels(p):
        """Room lists from the best to the most relaxed: preferred+seats, preferred, any that seats, any."""
        fit = lambda lst: [r for r in lst if not p.size or not (getattr(r, "capacity", 0) or 0) or r.capacity >= p.size]
        pref = p.rooms[:p.n_pref]
        every = p.rooms
        if not fit(every):            # nothing seats this many students: the biggest rooms first, so the shortfall is as small as possible
            big = lambda lst: sorted(lst, key=lambda r: -(getattr(r, "capacity", 0) or 0))
            pref, every = big(pref), big(every)
        levels = [fit(pref), pref, fit(every), every]
        out_, seen = [], set()
        for lv in levels:
            key = tuple(r.id for r in lv)
            if lv and key not in seen:
                seen.add(key); out_.append(lv)
        return out_

    def commit(p, exam_date, slot, room, s0, s1, proctor):
        for sub, m in p.members:
            out["created"].append(ExamSchedule(
                subject=sub, section=m, proctor=proctor, room=room, timeslot=slot, exam_date=exam_date,
                exam_period=exam_period, school_year=school_year, created_by=requesting_user, merge_key=p.merge_key))
            exams_by_date[exam_date].append((s0, s1, proctor.id, room.id, m.id))
        proctor_load[proctor.id] += 1
        cap = getattr(room, "capacity", 0) or 0
        if p.size and cap and cap < p.size:
            names = "+".join(f"{sec.program.name} {sec.name}" if len(p.members) > 1 else sec.name for _s, sec in p.members)
            out["capacity_warnings"].append(f"{p.subject.code} ({names}): {p.size} students in {room.name} ({cap} seats)")

    def place_together(group, dates):
        """Place every pair of `group` in ONE common hour, each in its own room with its own proctor; split only when it must."""
        remaining = sorted(group, key=lambda p: -p.size)
        while remaining:
            best = None                                   # (count, -level, date, slot, chosen)
            levels = max([len(room_levels(p)) for p in remaining] + [1])
            full = False
            for lv in range(levels):
                for exam_date in dates:
                    for slot in timeslots_for(exam_date):
                        s0, s1, rows = rows_at(exam_date, slot)
                        busy_r = {r[3] for r in rows}
                        busy_p = {r[2] for r in rows}
                        used_r, used_p, chosen = set(), set(), []
                        for p in remaining:
                            if not all(section_free(sec, rows, s0, s1) for _s, sec in p.members):
                                p.why["section"] += 1
                                continue
                            ls = room_levels(p)
                            room = next((r for r in ls[min(lv, len(ls) - 1)] if r.id not in busy_r and r.id not in used_r), None) if ls else None
                            proc = pool.pick(p.subject, busy_p | used_p, proctor_load)
                            if room is None or proc is None:
                                p.why["room" if room is None else "proctor"] += 1
                                continue
                            chosen.append((p, room, proc)); used_r.add(room.id); used_p.add(proc.id)
                        cand = (len(chosen), -lv)
                        if chosen and (best is None or cand > best[0]):
                            best = (cand, exam_date, slot, s0, s1, chosen)
                        if len(chosen) == len(remaining):
                            full = True
                            break
                    if full:
                        break
                if full:
                    break                                  # every section fits in one hour at this room level
            if best is None:
                return remaining
            _c, exam_date, slot, s0, s1, chosen = best
            for p, room, proc in chosen:
                commit(p, exam_date, slot, room, s0, s1, proc)
            done = {id(p) for p, _r, _q in chosen}
            remaining = [p for p in remaining if id(p) not in done]
        return []

    def explain(p):
        main = max(p.why, key=p.why.get)
        cause = {"section": f"{'/'.join(sec.name for _s, sec in p.members)} already has a class or another exam in every free hour of the exam week",
                 "room": "no allowed room is free in the remaining hours",
                 "proctor": "every proctor is busy in the remaining hours"}[main]
        return cause

    # ---- minors: one subject = one common hour; majors: one section at a time ------------------------------------------------
    groups = defaultdict(list)
    singles = []
    for p in pairs:
        if p.subject.classification == "minor":
            groups[(p.subject.code, p.subject.semester)].append(p)
        else:
            singles.append(p)
    ordered_groups = [g for _k, g in sorted(groups.items(), key=lambda kv: kv[0])] + [[p] for p in singles]
    leftovers = []
    for i, group in enumerate(ordered_groups):
        offset = i % len(exam_dates)
        dates = exam_dates[offset:] + exam_dates[:offset]
        leftovers += place_together(group, dates)

    for p in leftovers:
        why = explain(p)
        for sub, m in p.members:
            out["unresolved"].append(f"[{getattr(m.program, 'name', '')}] Could not place {sub.code} for {m}: {why}. Widen the exam week (more days) and generate again.")
            out["pending"].append({"subject_id": sub.id, "section_id": m.id, "subject": f"{sub.code} - {sub.title}",
                                   "section": str(m), "program": getattr(m.program, "name", ""), "reason": why})

    if out["created"]:
        out["created"] = ExamSchedule.objects.bulk_create(out["created"])
    return out
