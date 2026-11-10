"""SHS / JHS: the teacher list for a pin (TeachingAssignment: one section + one subject) in three groups, for the Principal.

  Suggested  -- eligible for the subject (engine.eligible: specialization or department), with enough free periods for the subject's
                sessions per week, and within their weekly hours. Lightest load first; at most SUGGESTED_MAX.
  Qualified  -- the other eligible teachers. Those who cannot take it are listed but NOT selectable, with the reason.
  Other available (not connected) -- for the Principal of this level: teachers of the SAME level who
                are NOT eligible but have the free periods and the hours. Choosing one is a manual "Assign anyway" with a reason.
                This group remains visible alongside eligible groups. The Principal never assigns themself. Not-eligible teachers over
                the limit are named in one muted "Full:" line.

"Free" uses the SHS engine's own rule (engine._free_for_teacher): inside the windows the teacher marked available (all of the day when
none were submitted), outside the windows they marked unavailable, inside their preferred start / end, and not booked by another
grade level's timetable of the same grading period. The weekly hours shown are the Workload (Analytics) numbers for that grading period.
READ-ONLY: nothing here writes to the database.
"""
from collections import defaultdict
from datetime import datetime

from . import models as m
from .engine import DAY_KEYS, Problem, _free_for_teacher, eligible

SUGGESTED_MAX = 5
APPROVAL = "Not connected to this subject. Principal approval required."
EMPTY_TEXT = "No faculty in your school level is free at this time."


def _fmt(h):
    return f"{round(float(h), 1):g}"


def is_principal_of(user, level):
    return getattr(user, "role", "") == "principal" and getattr(user, "school_level", "") == level


def grading_period_for(level, academic_year, subject):
    from .analytics import choose_period
    return subject.grading_period or choose_period(level, academic_year)[0]


def _timetable_hours(level, academic_year, period):
    """{faculty_id: hours} exactly as the Analytics / Workload tab counts them (latest runs of that grading period)."""
    from .analytics import _hours, latest_runs
    out = defaultdict(float)
    runs = latest_runs(level, academic_year, period)
    for e in m.ScheduleEntry.objects.filter(run__in=runs, teacher__isnull=False).only("teacher_id", "start_time", "end_time"):
        out[e.teacher_id] += _hours(e)
    return out


def build(user, section, subject, problem=None):
    level, ay = section.level, section.academic_year
    period = grading_period_for(level, ay, subject)
    P = problem or Problem(level, ay, period, section.grade_level)
    grid = P.grids.get(section.grade_level, [])
    period_min = P.config.period_minutes or 60
    need = subject.sessions_per_week
    need_hours = need * period_min / 60.0
    shown = _timetable_hours(level, ay, period)
    # periods each teacher is already pinned to elsewhere in THIS grade (they will be placed by the same Generate)
    pinned_elsewhere = defaultdict(int)
    for t in m.TeachingAssignment.objects.filter(section__level=level, section__academic_year=ay, section__grade_level=section.grade_level,
                                                 subject__grading_period__in=[0, period]).exclude(section=section, subject=subject) \
            .select_related("subject"):
        pinned_elsewhere[t.faculty_id] += t.subject.sessions_per_week
    can_override = is_principal_of(user, level)
    rows = []
    for f in P.faculty:
        ok_subject = eligible(f, subject)
        if not ok_subject and (not can_override or f.user_id == getattr(user, "id", None)):
            continue
        free_slots = sum(1 for d in DAY_KEYS for slot in grid if _free_for_teacher(P, f, d, slot, defaultdict(set)))
        free = free_slots - pinned_elsewhere[f.id] >= need
        cap = f.max_weekly_hours or P.config.max_teacher_hours
        projected = P.teacher_minutes.get(f.id, 0) / 60.0 + pinned_elsewhere[f.id] * period_min / 60.0
        full = cap and projected + need_hours > cap + 1e-9
        cur = round(shown.get(f.id, 0.0), 1)
        rows.append({"f": f, "qualified": ok_subject, "free": free, "full": bool(full), "projected": projected, "cap": cap, "cur": cur,
                     "out": {"id": f.id, "label": f.full_name, "full_name": f.full_name, "school_id": f.employee_id, "username": f.user.username,
                             "current_hours": cur, "max_hours": cap, "load_text": f"{_fmt(cur)}/{_fmt(cap)} hrs",
                             "after_generate_hours": round(projected, 1) if abs(projected - cur) > 0.05 else None,
                             "specializations": f.specializations or f.department or "none recorded"}})

    def full_text(r):
        return f"Full: {_fmt(r['cur'])}/{_fmt(r['cap'])} hrs" if r["projected"] >= r["cap"] - 1e-9 else \
            f"Over the limit with this subject: {_fmt(r['projected'] + need_hours)}/{_fmt(r['cap'])} hrs"

    free_q = sorted((r for r in rows if r["qualified"] and r["free"] and not r["full"]),
                    key=lambda r: (section.adviser_id != r["f"].id, r["projected"], r["out"]["label"].lower()))
    sug, rest = free_q[:SUGGESTED_MAX], free_q[SUGGESTED_MAX:]
    low = min((r["projected"] for r in sug), default=None)

    def tag(r, top):
        if section.adviser_id == r["f"].id:
            return "Section adviser"
        if top and low is not None and abs(r["projected"] - low) < 1e-9:
            return "Lowest load"
        return "Has free periods"
    out_s = [{**r["out"], "group": "suggested", "selectable": True, "not_connected": False, "tag": tag(r, True)} for r in sug]
    out_q = [{**r["out"], "group": "qualified", "selectable": True, "not_connected": False, "tag": tag(r, False)} for r in rest]
    for r in sorted((r for r in rows if r["qualified"] and r not in free_q), key=lambda r: r["out"]["label"].lower()):
        why = full_text(r) if r["full"] else f"Not enough free periods ({need} needed) inside their availability"
        out_q.append({**r["out"], "group": "qualified", "selectable": False, "not_connected": False, "tag": why})
    # Principals can see the explicit not-connected fallback even when there
    # are eligible teachers. Eligibility is a soft rule for a manual pin;
    # level, availability and workload rules remain enforced.
    show_other = can_override
    out_o, full_line = [], []
    if show_other:
        for r in sorted((r for r in rows if not r["qualified"]), key=lambda r: (r["projected"], r["out"]["label"].lower())):
            if r["full"]:
                full_line.append({"id": r["f"].id, "label": r["out"]["label"], "current_hours": r["cur"], "max_hours": r["cap"]})
            elif r["free"]:
                out_o.append({**r["out"], "group": "other", "selectable": True, "not_connected": True, "tag": "Not connected"})
    any_pick = any(o["selectable"] for o in out_s + out_q + out_o)
    return {"subject_id": subject.id, "code": subject.code, "title": subject.name, "section_id": section.id,
            "suggested": out_s, "qualified": out_q, "other": out_o, "other_shown": show_other, "full_line": full_line,
            "full_text": ("Full: " + ", ".join(f"{x['label']} {_fmt(x['current_hours'])}/{_fmt(x['max_hours'])} hrs" for x in full_line)) if full_line else "",
            "approval_text": APPROVAL, "override_possible": can_override, "empty_text": "" if any_pick else EMPTY_TEXT,
            "grading_period": period}


class OverrideError(Exception):
    pass


def override_meta(user, reason):
    return {"reason": reason, "by_id": user.id, "by_name": user.get_full_name().strip() or user.username, "role": "Principal",
            "at": datetime.now().astimezone().isoformat(timespec="seconds")}


def check_override(user, section, subject, faculty, reason):
    """The reason when this manual Assign anyway is allowed; raises OverrideError with a clear message otherwise. The groups are
    computed again now (never trusted from the browser)."""
    reason = (reason or "").strip()
    if not is_principal_of(user, section.level):
        raise OverrideError("Only the Principal of this school level can assign a teacher who is not connected to the subject.")
    if faculty.level != section.level or subject.level != section.level:
        raise OverrideError("Teacher, section and subject must all belong to the same school level.")
    if faculty.user_id == user.id:
        raise OverrideError("You cannot assign yourself to a subject you are not connected to.")
    if len(reason) < 3:
        raise OverrideError("Write a short reason for assigning a teacher who is not connected to this subject.")
    groups = build(user, section, subject)
    if not any(o["id"] == faculty.id for o in groups["other"]):
        if any(x["id"] == faculty.id for x in groups["full_line"]):
            raise OverrideError(f"{faculty.full_name} is at the weekly limit.")
        raise OverrideError(f"{faculty.full_name} does not have {subject.sessions_per_week} free periods inside their availability.")
    return reason


def badge_text(meta):
    return "Assigned by Principal (not connected)" if meta else ""
