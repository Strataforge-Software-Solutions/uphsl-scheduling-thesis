"""Lecture before Lab: ONE rule for every path that changes a class's day or time.

The CSP solver (scheduler.is_consistent) already requires that, for one section, a subject's Lab (code "X" + "L") starts only after its
Lecture (code "X") has ended in the week (Mon..Sun; the same day after the lecture is fine). The other paths (Resolve suggestions,
Change day / time, the Edit window, the old automatic resolver) use this module so they follow exactly the same rule.

bounds()   -> the limit the partner class sets for this class, or None when the subject has no saved partner in that section
violates() -> True when the new periods break that limit
message()  -> a plain-language reason naming the partner and its time"""
from .models import Schedule

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _di(day):
    d = (day or "")[:3]
    return DAYS.index(d) if d in DAYS else 9


def _m(t):
    return t.hour * 60 + t.minute


def _fmt(m):
    h, mm = divmod(int(m), 60)
    return f"{((h + 11) % 12) + 1}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def bounds(subject, section_id, term, exclude_ids=(), moving=()):
    """moving: [(subject_code, section_id, day, start_min, end_min)] -- new positions of other classes changed in the same request.
    Returns {"kind": "lab"|"lec", "pos": (day index, minute), "code", "label"} or None."""
    code = subject.code or ""
    if code.endswith("L") and len(code) > 1:
        kind, partner = "lab", code[:-1]          # this is the Lab: its Lecture must END before it starts
    else:
        kind, partner = "lec", code + "L"         # this is the Lecture: its Lab must START after it ends
    ivs = [(d, s, e) for c, sec, d, s, e in moving if c == partner and sec == section_id]
    rows = Schedule.objects.filter(section_id=section_id, term=term, subject__code=partner).exclude(pk__in=list(exclude_ids)) \
        .select_related("timeslot")
    ivs += [(r.timeslot.day, _m(r.timeslot.start_time), _m(r.timeslot.end_time)) for r in rows]
    if not ivs:
        return None
    if kind == "lab":
        d, _s, e = max(ivs, key=lambda x: (_di(x[0]), x[2]))
        return {"kind": "lab", "pos": (_di(d), e), "code": partner, "label": f"{d[:3]} {_fmt(e)}"}
    d, s, _e = min(ivs, key=lambda x: (_di(x[0]), x[1]))
    return {"kind": "lec", "pos": (_di(d), s), "code": partner, "label": f"{d[:3]} {_fmt(s)}"}


def violates(bound, ivs):
    """ivs: [(day, start_min, end_min)] of the class after the change."""
    if not bound or not ivs:
        return False
    if bound["kind"] == "lab":
        return min((_di(d), s) for d, s, _e in ivs) < bound["pos"]
    return max((_di(d), e) for d, _s, e in ivs) > bound["pos"]


def message(bound, subject):
    if bound["kind"] == "lab":
        return (f"{subject.code} is the Lab: it must come after its Lecture {bound['code']}, which ends {bound['label']}. "
                "Choose a time after that.")
    return (f"{subject.code} is the Lecture: it must come before its Lab {bound['code']}, which starts {bound['label']}. "
            "Choose a time before that.")


def check(subject, section_id, term, ivs, exclude_ids=(), moving=()):
    """'' when the order is kept, otherwise the reason."""
    b = bounds(subject, section_id, term, exclude_ids, moving)
    return message(b, subject) if violates(b, ivs) else ""
