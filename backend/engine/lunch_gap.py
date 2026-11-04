"""Lunch is not a fixed period in the college: students and professors eat in whatever free time they have between classes, and
12:00-1:00 PM is an ordinary class time.

"Reserve lunch gap (optional)" (SchedulingConfig.reserve_lunch_gap, OFF by default) is a SOFT preference only: when it is on, among the
placements that already pass every hard rule, the scheduler tries first those that still leave the section and the professor at least
one free hour between 10:30 AM and 2:30 PM that day. It never removes a placement, so no class is ever skipped because of it; where a
class could only be placed without such a gap, Generate shows a warning (warnings()).
"""
from contextvars import ContextVar

WINDOW = (10 * 60 + 30, 14 * 60 + 30)       # 10:30 AM - 2:30 PM
NEED = 60                                   # one free hour in it

_ON = ContextVar("reserve_lunch_gap", default=False)
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def enabled_in_settings():
    from .models import SchedulingConfig
    cfg = SchedulingConfig.objects.filter(pk=1).first()
    return bool(cfg and getattr(cfg, "reserve_lunch_gap", False))


def use(on):
    return _ON.set(bool(on))


def release(token):
    _ON.reset(token)


def enabled():
    return _ON.get()


def has_gap(spans):
    """True when the busy (start, end) minute spans of ONE day leave at least NEED free minutes in a row inside WINDOW."""
    busy = sorted((max(a, WINDOW[0]), min(b, WINDOW[1])) for a, b in spans if b > WINDOW[0] and a < WINDOW[1])
    cur = WINDOW[0]
    for a, b in busy:
        if a - cur >= NEED:
            return True
        cur = max(cur, b)
    return WINDOW[1] - cur >= NEED


def _clock(m):
    h = m // 60
    return f"{(h + 11) % 12 + 1}:{m % 60:02d} {'AM' if h < 12 else 'PM'}"


def warnings(rows, sections=None, teachers=None):
    """Plain warnings for each (section, day) and (professor, day) whose classes leave no free hour between 10:30 AM and 2:30 PM.
    rows: objects with .section, .teacher and .timeslot (Assignments or Schedule rows) -- every class of the semester for them.
    sections / teachers: limit the check to these ids (the ones this Generate placed). Read-only."""
    from .scheduler import _slot_keys
    by_s, by_t, names = {}, {}, {}
    for r in rows:
        for k in _slot_keys(r.timeslot):
            if sections is None or r.section.id in sections:
                by_s.setdefault((r.section.id, k[0]), set()).add((k[1], k[2]))
                names[("s", r.section.id)] = f"{getattr(r.section.program, 'name', '')} {r.section.name}".strip()
            if teachers is None or r.teacher.id in teachers:
                by_t.setdefault((r.teacher.id, k[0]), set()).add((k[1], k[2]))
                names[("t", r.teacher.id)] = r.teacher.user.get_full_name().strip() or r.teacher.user.username
    out = []
    span = f"{_clock(WINDOW[0])} and {_clock(WINDOW[1])}"
    for kind, data in (("s", by_s), ("t", by_t)):
        for (oid, day), spans in sorted(data.items(), key=lambda x: (names.get((kind, x[0][0]), ""), x[0][1])):
            if not has_gap(spans):
                who = names[(kind, oid)] + ("" if kind == "s" else " (professor)")
                out.append(f"{who}, {_DAYS[day] if day < 7 else day}: no free hour between {span} (lunch gap could not be kept).")
    return out
