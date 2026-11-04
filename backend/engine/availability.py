"""Faculty availability (faculty.Availability) for one generation run.

The HARD rule is engine.views._build_availability_rules (blocked slots; no submission = unrestricted). This module adds, for the same
rows:
  * preferred slots -- a SOFT ordering only: among a teacher's allowed slots, those inside a "preferred" window are tried first. It
    never removes a slot and never changes which subject the Greedy search places next;
  * readable windows -- "Sat 7:00 AM-4:30 PM" -- so a class skipped for availability says exactly why (explain_unresolved).
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
    """({teacher_id: set(slot ids inside a preferred window)}, {teacher_id: "available only ..." text}) for teachers WITH a submission."""
    by = {}
    for w in rows([t.id for t in teachers], school_year, semester):
        by.setdefault(w.faculty_id, []).append(w)
    pref, text = {}, {}
    for tid, ws in by.items():
        good = sorted((w for w in ws if w.preference != "unavailable"), key=lambda w: (_ORDER.get(w.day[:3].lower(), 9), w.start_time))
        bad = sorted((w for w in ws if w.preference == "unavailable"), key=lambda w: (_ORDER.get(w.day[:3].lower(), 9), w.start_time))
        fmt = lambda w: f"{w.day[:3].title()} {_clock(w.start_time)}-{_clock(w.end_time)}" + (" (preferred)" if w.preference == "preferred" else "")
        parts = []
        if good:
            parts.append("available only " + ", ".join(fmt(w) for w in good))
        if bad:
            parts.append("not available " + ", ".join(f"{w.day[:3].title()} {_clock(w.start_time)}-{_clock(w.end_time)}" for w in bad))
        text[tid] = "; ".join(parts)
        prefs = [w for w in good if w.preference == "preferred"]
        if prefs:
            pref[tid] = {s.id for s in timeslots if any(
                w.day[:3].lower() == s.day[:3].lower() and w.start_time <= s.start_time and w.end_time >= s.end_time for w in prefs)}
    return pref, text


def use(pref, text):
    return _PREF.set(pref or {}), _TEXT.set(text or {})


def release(tokens):
    _PREF.reset(tokens[0])
    _TEXT.reset(tokens[1])


def outside_preferred(teacher_id, slot):
    """0 when the slot lies in one of the teacher's preferred windows (or the teacher has none), else 1. Ordering only."""
    pref = _PREF.get().get(teacher_id)
    if not pref:
        return 0
    ids = [s.id for s in getattr(slot, "slots", None) or [slot]]
    return 0 if all(i in pref for i in ids) else 1


def text_for(teacher_id):
    return _TEXT.get().get(teacher_id, "")
