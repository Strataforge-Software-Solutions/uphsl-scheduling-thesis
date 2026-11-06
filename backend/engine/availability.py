"""Faculty availability (faculty.Availability) for one generation run.

The HARD rule is engine.views._build_availability_rules: only times a teacher marked "unavailable" are blocked (no submission =
unrestricted). Their "preferred" and "available" windows do NOT limit the day; this module turns them into a SOFT order:
  * tier 0 = inside a "preferred" window (or the teacher submitted no preferred / available window), tier 1 = inside an "available"
    window, tier 2 = any other open time. The Greedy search tries lower tiers first for a class; it never removes a slot and never
    changes which subject is placed next;
  * readable text of the unavailable windows -- "not available Mon 8:00 AM-12:00 PM" -- so a class skipped for that reason says why.
Both are made visible to the scheduler through context variables, like the Dean's room / time choices (rooms.rules).
"""
from contextvars import ContextVar

from django.db.models import Q

_PREF = ContextVar("teacher_preferred_slots", default={})
_TEXT = ContextVar("teacher_availability_text", default={})


def rows(teacher_ids=None, school_year=None, semester=None):
    """Active availability rows of the term. A row saved WITHOUT a school year / semester applies to every term (it used to be ignored
    as soon as the term was known, so such a teacher was treated as free at any time)."""
    from faculty.models import Availability
    qs = Availability.objects.filter(is_active=True)
    if teacher_ids is not None:
        qs = qs.filter(faculty_id__in=list(teacher_ids))
    if school_year:
        qs = qs.filter(Q(school_year=school_year) | Q(school_year=""))
    if semester:
        qs = qs.filter(Q(semester=semester) | Q(semester=""))
    return qs


def _clock(t):
    return f"{((t.hour + 11) % 12) + 1}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


_ORDER = {d: i for i, d in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))}


def build(teachers, timeslots, school_year=None, semester=None):
    """({teacher_id: {slot_id: tier}} for teachers with preferred / available windows, {teacher_id: "not available ..." text})."""
    by = {}
    for w in rows([t.id for t in teachers], school_year, semester):
        by.setdefault(w.faculty_id, []).append(w)
    pref, text = {}, {}
    for tid, ws in by.items():
        good = sorted((w for w in ws if w.preference != "unavailable"), key=lambda w: (_ORDER.get(w.day[:3].lower(), 9), w.start_time))
        bad = sorted((w for w in ws if w.preference == "unavailable"), key=lambda w: (_ORDER.get(w.day[:3].lower(), 9), w.start_time))
        fmt = lambda w: f"{w.day[:3].title()} {_clock(w.start_time)}-{_clock(w.end_time)}" + (" (preferred)" if w.preference == "preferred" else "")
        parts = []
        if bad:
            parts.append("not available " + ", ".join(f"{w.day[:3].title()} {_clock(w.start_time)}-{_clock(w.end_time)}" for w in bad))
        text[tid] = "; ".join(parts)
        if good:
            _inside = lambda s, ws: any(w.day[:3].lower() == s.day[:3].lower() and w.start_time <= s.start_time and w.end_time >= s.end_time
                                        for w in ws)
            prefs = [w for w in good if w.preference == "preferred"]
            others = [w for w in good if w.preference != "preferred"]
            tiers = {}
            for s in timeslots:
                if _inside(s, prefs):
                    tiers[s.id] = 0
                elif _inside(s, others):
                    tiers[s.id] = 1
            pref[tid] = tiers
    return pref, text


def use(pref, text):
    return _PREF.set(pref or {}), _TEXT.set(text or {})


def release(tokens):
    _PREF.reset(tokens[0])
    _TEXT.reset(tokens[1])


def outside_preferred(teacher_id, slot):
    """Priority tier of a placement for this teacher: 0 = inside their preferred time (or nothing preferred / available submitted),
    1 = inside their available time, 2 = outside both (still allowed). Ordering only: it never excludes a time."""
    tiers = _PREF.get().get(teacher_id)
    if not tiers:
        return 0
    ids = [s.id for s in getattr(slot, "slots", None) or [slot]]
    return max(tiers.get(i, 2) for i in ids) if ids else 0


def text_for(teacher_id):
    return _TEXT.get().get(teacher_id, "")
