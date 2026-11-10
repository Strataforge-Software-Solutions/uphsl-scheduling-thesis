"""
Conflict report: finds every double-booking in the class schedule, in memory, from ONE query.

A "class block" is a class as the schedule shows it (a 3-hour class stored as three 1-hour rows is one block).
Two blocks on the same day of the same semester CONFLICT when they overlap in time and share
  * the same TEACHER   (any overlap),
  * the same ROOM      (any overlap), or
  * the same STUDENTS (section) (any overlap: a section is never in two classes at once, the same rule the CSP solver uses;
    the configurable grace window applies to exams only).
Rows of one shared (merged) class never conflict with each other. These are the same rules as engine.conflicts.
"""
from collections import defaultdict

from .conflicts import class_tolerance_minutes
from .models import Schedule

DEMO_TAG = "DEMO-CONFLICT"          # Schedule.school_year of the sample rows, so they can be found and removed
DAY_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
KIND_LABEL = {"teacher": "Teacher", "room": "Room", "section": "Students"}


def _category(ra, rb):
    kinds = {ra.subject.classification, rb.subject.classification}
    return "minor-minor" if kinds == {"minor"} else "major-major" if kinds == {"major"} else "minor-major"


def _min(t):
    return t.hour * 60 + t.minute


def _label(m):
    h, mm = divmod(m, 60)
    return f"{(h % 12) or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def _blocks(rows):
    """Merge contiguous periods of the same class into one block."""
    rows = sorted(rows, key=lambda r: (r.subject_id, r.section_id, r.teacher_id, r.room_id, r.merge_key,
                                       r.timeslot.day, _min(r.timeslot.start_time)))
    out, cur = [], None
    for r in rows:
        s, e = _min(r.timeslot.start_time), _min(r.timeslot.end_time)
        key = (r.subject_id, r.section_id, r.teacher_id, r.room_id, r.merge_key, r.timeslot.day)
        if cur and cur["key"] == key and s <= cur["end"]:
            cur["end"] = max(cur["end"], e)
            cur["ids"].append(r.id)
        else:
            cur = {"key": key, "ids": [r.id], "start": s, "end": e, "row": r, "day": r.timeslot.day,
                   "sem": r.section.semester, "merge": r.merge_key}
            out.append(cur)
    return out


def _describe(b):
    r = b["row"]
    u = r.teacher.user
    return {
        "ids": b["ids"], "subject": f"{r.subject.code} {r.subject.title}", "section": f"{r.section.program.name} {r.section.name}",
        "teacher": (u.get_full_name().strip() or u.username), "room": r.room.name,
        "time": f"{b['day']} {_label(b['start'])} - {_label(b['end'])}", "demo": r.school_year == DEMO_TAG,
        "code": r.subject.code, "title": r.subject.title, "department": r.section.program.department,
        "year_level": r.section.year_level, "semester": r.section.semester, "section_name": r.section.name,
        "day": b["day"], "classification": r.subject.classification, "school_year": r.school_year,
        # so the pop-up can say up front that a class cannot be moved (approved / published, or a shared class)
        "status": r.status, "shared": bool(getattr(r, "merge_key", "")),
    }


def scan(*, semester=None, departments=None, involving_ids=None, limit=300, year_level=None):
    """Returns {"checked": n classes, "total": n conflicts, "counts": {kind: n}, "conflicts": [...]}.
    departments: only conflicts where at least one class belongs to these departments.
    involving_ids: only conflicts that involve one of these schedule rows (used right after generating)."""
    tol = class_tolerance_minutes()        # same rule as the solver: students are never in two classes at once
    # The dashboard runs this scan to get a conflict count. Restrict selected columns so the
    # full schedule scan transfers only fields the detector and its response formatter use.
    qs = Schedule.objects.select_related("subject", "section__program", "teacher__user", "room", "timeslot").only(
        "id", "subject_id", "section_id", "teacher_id", "room_id", "timeslot_id", "merge_key", "school_year", "status",
        "subject__code", "subject__title", "subject__classification",
        "section__name", "section__semester", "section__year_level", "section__student_count", "section__program_id",
        "section__program__name", "section__program__department",
        "teacher__user_id",
        "teacher__user__first_name", "teacher__user__last_name", "teacher__user__username",
        "room__name", "timeslot__day", "timeslot__start_time", "timeslot__end_time",
    )
    if semester:
        qs = qs.filter(section__semester=semester)
    blocks = _blocks(list(qs))
    groups = defaultdict(list)
    for b in blocks:
        groups[(b["sem"], b["day"])].append(b)
    involving = set(involving_ids or [])
    dept = set(departments or [])
    found, counts = [], defaultdict(int)
    for (sem, day), grp in groups.items():
        grp.sort(key=lambda b: b["start"])
        for i, a in enumerate(grp):
            for b in grp[i + 1:]:
                if b["start"] >= a["end"]:
                    break                                        # sorted by start: nothing later can overlap `a`
                if a["merge"] and a["merge"] == b["merge"]:
                    continue
                ov = min(a["end"], b["end"]) - max(a["start"], b["start"])
                if ov <= 0:
                    continue
                ra, rb = a["row"], b["row"]
                kinds = []
                if ra.teacher_id == rb.teacher_id:
                    kinds.append("teacher")
                if ra.room_id == rb.room_id:
                    kinds.append("room")
                if ra.section_id == rb.section_id and ov > tol:
                    kinds.append("section")
                if not kinds:
                    continue
                if involving and not (involving & set(a["ids"]) or involving & set(b["ids"])):
                    continue
                if dept and not (ra.section.program.department in dept or rb.section.program.department in dept):
                    continue
                if year_level and not ({ra.section.year_level, rb.section.year_level} & set(
                        [year_level] if isinstance(year_level, str) else year_level)):
                    continue
                for k in kinds:
                    counts[k] += 1
                    if len(found) < limit:
                        who = {"teacher": _describe(a)["teacher"], "room": ra.room.name, "section": f"{ra.section.program.name} {ra.section.name}"}[k]
                        found.append({
                            "kind": k, "kind_label": KIND_LABEL[k], "day": day, "semester": sem, "overlap_minutes": ov,
                            "message": (f"{KIND_LABEL[k]} {who} is booked for two classes that overlap by {ov} min on {day} "
                                        f"({_label(max(a['start'], b['start']))} - {_label(min(a['end'], b['end']))})."
                                        + (" The students cannot attend both." if k == "section" and not tol else (f" Only {tol} min is allowed for students." if k == "section" else ""))),
                            "a": _describe(a), "b": _describe(b),
                            "category": _category(ra, rb),
                        })
    found.sort(key=lambda c: (DAY_ORDER.get(c["day"], 9), c["a"]["time"], c["kind"]))
    return {"checked": len(blocks), "total": sum(counts.values()), "counts": dict(counts), "conflicts": found,
            "allowance_minutes": tol, "demo_rows": Schedule.objects.filter(school_year=DEMO_TAG).count()}


# ------------------------------------------------------------------------------------------------ demo
def add_demo_conflicts(user_departments=None):
    """Creates three sample double-bookings (teacher, room, students) next to a real class, tagged DEMO-CONFLICT, so the
    detection can be shown. Returns a list of what was created, or raises ValueError when there is not enough data."""
    from .models import Section, TimeSlot
    from faculty.models import FacultyProfile
    from rooms.models import Room
    from datetime import time as dtime

    remove_demo_conflicts()
    qs = Schedule.objects.select_related("subject", "section__program", "teacher", "room", "timeslot").order_by("id")
    if user_departments:
        qs = qs.filter(section__program__department__in=user_departments)
    base = next((r for r in qs if _min(r.timeslot.end_time) - _min(r.timeslot.start_time) >= 60 and r.timeslot.day in DAY_ORDER), None)
    if base is None:
        raise ValueError("Generate a class schedule first: there is no class to put a sample conflict next to.")
    sec = base.section
    other_sections = list(Section.objects.filter(semester=sec.semester).exclude(pk=sec.pk)[:3])
    other_teachers = list(FacultyProfile.objects.exclude(pk=base.teacher_id)[:3])
    other_rooms = list(Room.objects.filter(room_type__in=["lecture", "lab"]).exclude(pk=base.room_id)[:3])
    if not (other_sections and other_teachers and other_rooms):
        raise ValueError("Not enough sections, teachers or rooms to build a sample conflict.")

    # overlapping but NOT identical time (shifted by 30 min), so the database's exact-slot rule does not block it
    s0, e0 = _min(base.timeslot.start_time), _min(base.timeslot.end_time)
    day = base.timeslot.day

    def slot(shift):
        s, e = s0 + shift, e0 + shift
        return TimeSlot.objects.get_or_create(day=day, start_time=dtime(s // 60, s % 60), end_time=dtime(e // 60, e % 60))[0]

    made = []

    def add(kind, section, teacher, room, shift, note):
        row = Schedule.objects.create(subject=base.subject, section=section, teacher=teacher, room=room, timeslot=slot(shift),
                                      status="draft", school_year=DEMO_TAG, term=section.semester)
        made.append({"kind": kind, "note": note, "schedule_id": row.id})

    add("teacher", other_sections[0], base.teacher, other_rooms[0], 30, "same teacher, different room and students")
    add("room", other_sections[-1], other_teachers[0], base.room, 60 if e0 - s0 > 60 else 30, "same room, different teacher and students")
    add("section", sec, other_teachers[-1], other_rooms[-1], 90 if e0 - s0 > 90 else 30, "same students, different teacher and room")
    return made


def remove_demo_conflicts():
    n, _ = Schedule.objects.filter(school_year=DEMO_TAG).delete()
    return n
