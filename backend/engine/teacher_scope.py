"""Which teachers may be put on a class: ONE rule for every place that saves or suggests a teacher.

* A Dean's MAJOR subject: only faculty of the Dean's own department(s) (User.departments, which includes extra_departments). Normal
  assignments must be qualified under engine.qualification.is_qualified; the Dean may explicitly approve a not-connected teacher from
  that same department, subject to the separate availability and workload rules.
  Teachers of other departments are never listed, suggested or accepted.
* A Gen Ed (minor) subject (the Registrar's): any qualified teacher, as engine.qualification says (unchanged).

Used by: Edit -> Save (ScheduleViewSet.perform_update), Generate's professor check (professor_choice.validate), the overload
"assign" (overload.assign), the teacher-leaving "assign" (tools.assign_replacement), Smart Resolve's teacher edit (tools), the Edit
dialog's teacher list (teacher_options) and the replacement suggestions for major subjects (workload.suggest_replacements).
"""


def _deps(user):
    if user is None:
        return []
    return list(getattr(user, "departments", None) or ([user.department] if getattr(user, "department", None) else []))


def _name(t):
    return t.user.get_full_name().strip() or t.user.username


def subject_department(subject, section=None):
    prog = getattr(section, "program", None) or getattr(subject, "program", None)
    return getattr(prog, "department", None) or ""


def is_major(subject):
    return getattr(subject, "classification", "major") != "minor"


def allowed_departments(user, subject, section=None):
    """The departments a teacher must belong to for this class, or None when any department is allowed (Gen Ed)."""
    if not is_major(subject):
        return None
    dept = subject_department(subject, section)
    if user is not None and getattr(user, "role", "") == "faculty" and getattr(user, "faculty_type", "") == "dean":
        return [d for d in _deps(user)] or [dept]
    return [dept] if dept else None


def in_department(teacher, subject, section=None, user=None):
    allowed = allowed_departments(user, subject, section)
    if allowed is None:
        return True
    return bool(set(_deps(teacher.user)) & set(allowed))


def teacher_allowed(user, teacher, subject, section=None, spec_ids=None):
    """"" when `teacher` may take this class, else the reason (shown to the user as it is)."""
    from .qualification import is_qualified
    if spec_ids is None:
        spec_ids = {f.id for f in teacher.specializations.all()}
    if is_major(subject) and not in_department(teacher, subject, section, user):
        tdep = ", ".join(_deps(teacher.user)) or "no department"
        allowed = ", ".join(allowed_departments(user, subject, section) or [])
        return (f"{_name(teacher)} is not qualified for {subject.code}: they are not a faculty member of {allowed} (they are in {tdep}). "
                f"{subject.code} is a major subject: only the "
                f"department's own qualified faculty can teach it. Choose a teacher from {allowed}.")
    if not is_qualified(teacher, subject, section, spec_ids):
        where = f" in {subject_department(subject, section)}" if is_major(subject) else ""
        return (f"{_name(teacher)} is not qualified for {subject.code} (no matching specialization or degree{where}). "
                "Choose a qualified teacher, or record the specialization in the Faculty tab first.")
    return ""


def candidates(user, subject, section=None, teachers=None):
    """The active teachers who may take this class (department + qualification), for lists and suggestions."""
    from faculty.models import FacultyProfile
    if teachers is None:
        teachers = FacultyProfile.objects.filter(user__is_active=True).select_related("user").prefetch_related("specializations")
    return [t for t in teachers if not teacher_allowed(user, t, subject, section)]


def options(user, schedule_ids):
    """READ-ONLY teacher list for the Edit dialog: one class (all its periods), only the teachers who may take it (the rule above),
    each with weekly load vs limit and whether they are free then and within their limit ("suggested").
    Returns (payload, error text, http status). Writes nothing (the limits are read without creating the settings row)."""
    from .models import Schedule, TimeSlot
    from .permissions import can_edit_schedule_kind
    from .professor_choice import limits_readonly, short_name
    from .views import _build_availability_rules
    from .workload import hours_by_teacher_term, limit_for, _overlaps
    rows = list(Schedule.objects.filter(pk__in=schedule_ids).select_related("subject", "subject__program", "section__program",
                                                                            "timeslot", "teacher__user"))
    if not rows:
        return None, "Class not found.", 404
    r0 = rows[0]
    if any((r.subject_id, r.section_id) != (r0.subject_id, r0.section_id) for r in rows):
        return None, "These periods are not one class.", 400
    if not can_edit_schedule_kind(user, r0.subject.classification, r0.section.program.department):
        return None, "You cannot change this class.", 403
    ids = [r.id for r in rows]
    shared = None
    members = [(r0.section, r0.subject)]
    if r0.merge_key:
        # a SHARED class is edited as one class (engine.shared_edit): the teacher must suit every attending section, and the rows
        # of the other sections are the same class, not a clash
        from .shared_edit import group_rows
        grp = group_rows(r0.merge_key)
        ids = [r.id for r in grp]
        members = list({r.section_id: (r.section, r.subject) for r in grp}.values())
        shared = {"sections": [f"{sec.program.name} {sec.name}" for sec, _sub in members],
                  "students": sum(int(sec.student_count or 0) for sec, _sub in members)}
    slots = list({r.timeslot_id: r.timeslot for r in rows}.values())
    need = sum((s.end_time.hour * 60 + s.end_time.minute - s.start_time.hour * 60 - s.start_time.minute) / 60 for s in slots)
    term = r0.term or r0.section.semester
    allowed = candidates(user, r0.subject, r0.section)
    for sec, sub in members[1:]:
        ok = {t.id for t in candidates(user, sub, sec, allowed)}
        allowed = [t for t in allowed if t.id in ok]
    # the class's current teacher is listed only when the rule allows them; otherwise (older data) they are named separately,
    # never offered as a choice, with the reason
    outside = "" if r0.teacher_id in {t.id for t in allowed} else teacher_allowed(user, r0.teacher, r0.subject, r0.section)
    lim = limits_readonly()
    hrs = hours_by_teacher_term([t.id for t in allowed])
    free_hrs = hours_by_teacher_term([t.id for t in allowed], exclude_schedule_ids=ids)
    rules = _build_availability_rules(allowed, list(TimeSlot.objects.all()), r0.school_year, term or None)
    busy = {}
    for sc in Schedule.objects.filter(teacher__in=allowed, term=r0.term).exclude(pk__in=ids).select_related("timeslot", "subject", "section"):
        if any(_overlaps(s, sc.timeslot) for s in slots):
            busy.setdefault(sc.teacher_id, set()).add(f"{sc.subject.code} ({sc.section.name})")
    out = []
    for t in allowed:
        cur = round(hrs.get(t.id, {}).get(term, 0.0), 2)
        mx = limit_for(t, lim)
        after = free_hrs.get(t.id, {}).get(term, 0.0) + need
        why = ""
        if any(s.id in rules.get(t.id, set()) for s in slots):
            why = "outside their availability then"
        elif t.id in busy:
            why = "already teaching " + ", ".join(sorted(busy[t.id]))
        elif after > mx + 1e-9:
            why = f"would have {round(after, 2):g} of {mx:g} hrs"
        out.append({"id": t.id, "label": short_name(t), "full_name": _name(t), "school_id": t.user.school_id,
                    "username": t.user.username, "department": t.user.department or "", "faculty_type": t.user.faculty_type,
                    "current_hours": cur, "max_hours": mx, "suggested": not why, "why": why,
                    "current": t.id == r0.teacher_id})
    out.sort(key=lambda x: (not x["suggested"], x["current_hours"], x["label"].lower()))
    from . import faculty_groups as fg
    from .scheduler import _is_lab_of
    _prow = next((p for p in Schedule.objects.filter(section=r0.section, term=term).select_related("subject")
                  if _is_lab_of(r0.subject, p.subject) or _is_lab_of(p.subject, r0.subject)), None)
    partner = _prow.teacher_id if _prow else None
    groups = fg.build(user, r0.subject, r0.section, term=term, school_year=r0.school_year or None, exact_slots=slots, exclude_ids=ids,
                      need_hours=need, partner_teacher_id=partner)
    return {"subject": r0.subject.code, "title": r0.subject.title, "kind": "major" if is_major(r0.subject) else "minor",
            "departments": allowed_departments(user, r0.subject, r0.section) or [], "teacher": r0.teacher_id,
            "current_outside": {"id": r0.teacher_id, "full_name": _name(r0.teacher), "reason": outside} if outside else None,
            "shared": shared,
            "override": r0.qualification_override, "override_badge": fg.badge_text(r0.qualification_override),
            "groups": groups, "partner_code": _prow.subject.code if _prow else "",
            "teachers": out}, "", 200
