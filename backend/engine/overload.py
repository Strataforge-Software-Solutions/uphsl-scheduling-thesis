"""
Overload resolution for Deans (and the Registrar for Gen Ed): which overloaded teachers exist, which of their classes can be moved,
who is qualified and free to take each, and a strict one-click assignment that re-validates everything.

A class can be moved only when the person may edit it (a Dean: draft program subjects of their own college; the Registrar: draft
Gen Ed) -- approved / published / shared (merged) classes are never moved. Recommended people must hold a matching specialization or
a related degree / qualification, be inside their submitted availability, be free at every period, and stay within their own
weekly limit (full-time / part-time) after taking the class. Assignment applies the change to the real schedule rows.
"""
from collections import defaultdict

from django.db import transaction

from . import workload as wl
from .models import Schedule
from .placement import _can_edit


def _label_time(t):
    return t.strftime("%I:%M%p").lstrip("0")


def scope_profiles(user):
    """Faculty an overload warning may concern for this user: their own college's faculty PLUS anyone teaching one of the classes the
    user owns (a Dean's own-college program subjects, the Registrar's Gen Ed) -- a generated class can land on a teacher whose home
    department is another college, and the warning must still reach the person who can fix it."""
    from faculty.models import FacultyProfile
    from .views import _workload_scope
    base = _workload_scope(user)
    owned = Schedule.objects.exclude(teacher__isnull=True)
    if user.role == "registrar":
        owned = owned.filter(subject__classification="minor")
    else:
        owned = owned.filter(subject__classification="major", section__program__department__in=user.departments)
    ids = set(base.values_list("pk", flat=True)) | set(owned.values_list("teacher_id", flat=True).distinct())
    return FacultyProfile.objects.select_related("user").filter(pk__in=ids, user__is_active=True)


def locked_reason(row, user):
    if row.merge_key:
        return "Shared class (several sections)"
    if row.status != "draft":
        return f"Already {row.status}"
    if row.subject.classification == "minor" and user.role != "registrar":
        return "Gen Ed class (Registrar's)"
    if row.subject.classification == "major" and user.role == "registrar":
        return "Program subject (Dean's)"
    return "Another college's class"


def _class_groups(profile, user, term):
    """(movable groups, locked groups) of this teacher's classes in a term. Rows of one class (subject + section) move together."""
    rows = Schedule.objects.filter(teacher=profile, term=term).select_related(
        "subject", "subject__field", "subject__program", "section__program", "timeslot", "room")
    movable, locked = defaultdict(list), defaultdict(list)
    for r in rows:
        key = (r.subject_id, r.section_id, r.merge_key or "")
        (movable if _can_edit(user, r) else locked)[key].append(r)
    return list(movable.values()), list(locked.values())


def _hours(rows):
    return round(sum(wl._hours(r.timeslot) for r in rows), 2)


def _describe(rows):
    r0 = rows[0]
    return {
        "subject_id": r0.subject_id, "section_id": r0.section_id, "schedule_ids": [r.id for r in rows], "code": r0.subject.code,
        "subject": r0.subject.title, "section": f"{r0.section.program.name} {r0.section.name}", "term": r0.term,
        "classification": r0.subject.classification, "status": r0.status, "merged": bool(r0.merge_key),
        "required_field": r0.subject.field.name if r0.subject.field_id else "",
        "hours": _hours(rows),
        "when": ", ".join(f"{x.timeslot.day} {_label_time(x.timeslot.start_time)}-{_label_time(x.timeslot.end_time)}"
                          for x in sorted(rows, key=lambda x: (x.timeslot.day, x.timeslot.start_time))),
    }


def why_none(rows, diag, who):
    """Plain-language reason nobody can take a class automatically."""
    r0 = rows[0]
    need = f"{r0.subject.code} {r0.subject.title}"
    field = f" ({r0.subject.field.name})" if r0.subject.field_id else ""
    if not diag or not diag.get("qualified"):
        return (f"No faculty member is qualified for {need}{field}: none of the {diag.get('considered', 0) if diag else 0} other active faculty "
                "has the matching specialization, or a related degree or qualification. Add the specialization to a suitable teacher's "
                "profile, or hire a qualified teacher, then check again.")
    bits = []
    if diag["unavailable"]:
        bits.append(f"{diag['unavailable']} are not available at the class time")
    if diag["busy"]:
        bits.append(f"{diag['busy']} are already teaching then")
    if diag["no_capacity"]:
        bits.append(f"{diag['no_capacity']} would exceed their weekly hour limit")
    return (f"{diag['qualified']} faculty member(s) are qualified for {need}{field}, but " + "; ".join(bits or ["none is free"]) +
            ". Ask a qualified teacher to add availability, move the class to a time they are free, or raise the limit under Workload.")


def plan(user, term=None):
    """Everything the View Suggestions screen needs."""
    scope = scope_profiles(user)
    rows = wl.workload_rows(scope, term=term or None)
    out = []
    for row in rows:
        for bt in row["by_term"]:
            if bt["overload_hours"] <= 0 or (term and bt["term"] != term):
                continue
            prof = scope.filter(pk=row["faculty_id"]).first()
            if prof is None:
                continue
            t = bt["term"]
            movable, locked = _class_groups(prof, user, t)
            excess = bt["overload_hours"]
            locked_hours = round(sum(_hours(g) for g in locked), 2)
            # choose the fewest classes that remove the excess: the smallest one that is big enough, else the biggest, repeat
            pool, chosen, left = sorted(movable, key=_hours), [], excess
            while left > 1e-9 and pool:
                big = [g for g in pool if _hours(g) >= left - 1e-9]
                g = big[0] if big else pool[-1]
                pool.remove(g); chosen.append(g); left = round(left - _hours(g), 2)
            chosen_ids = {id(g) for g in chosen}
            classes = []
            sim_hours = defaultdict(float)             # extra hours already promised to someone by an earlier suggestion
            for g in sorted(movable, key=lambda g: (id(g) not in chosen_ids, -_hours(g))):
                d = _describe(g)
                d["recommended"] = id(g) in chosen_ids
                d["suggestions"], d["reason_none"] = None, ""
                if d["recommended"]:
                    diag = {}
                    sugg = wl.suggest_replacements(g[0].subject, t, [r.timeslot for r in g], exclude_teacher_ids=[prof.id],
                                                   school_year=g[0].school_year, limit=6, diag=diag, user=user, section=g[0].section)
                    for s in sugg:                     # keep two suggestions from piling onto one person beyond their limit
                        s["current_hours"] = round(s["current_hours"] + sim_hours[s["faculty_id"]], 2)
                        s["remaining_after"] = round(s["max_hours"] - s["current_hours"] - d["hours"], 2)
                    sugg = [s for s in sugg if s["remaining_after"] >= -1e-9]
                    d["suggestions"] = sugg
                    if sugg:
                        sim_hours[sugg[0]["faculty_id"]] += d["hours"]
                    else:
                        # nobody qualified at all: the existing explanation, then the department list with each teacher's reason
                        dep = wl.no_available_text(diag)
                        d["reason_none"] = (why_none(g, diag, prof) + (" " + dep if dep else "")) if not diag.get("qualified") else (dep or why_none(g, diag, prof))
                    d["rejected"] = diag.get("rejected") or []
                classes.append(d)
            problems = []
            if left > 1e-9:
                if not movable:
                    problems.append("None of this teacher's classes can be changed from here"
                                    + (": they are Gen Ed / shared classes or already approved or published." if locked else "."))
                else:
                    problems.append(f"Even moving every changeable class would leave {left:g} h over.")
            if locked_hours:
                problems.append(f"{locked_hours:g} h of this teacher's load are classes you cannot change here "
                                "(Gen Ed owned by the Registrar, shared, or already approved/published).")
            subjects = [dict(_describe(g), editable=True, locked_reason="") for g in movable] + \
                       [dict(_describe(g), editable=False, locked_reason=locked_reason(g[0], user)) for g in locked]
            subjects.sort(key=lambda x: -x["hours"])
            out.append({
                "subjects": [{k: x[k] for k in ("code", "subject", "section", "hours", "when", "editable", "locked_reason")} for x in subjects],
                "faculty_id": prof.id, "full_name": row["full_name"], "faculty_type": row["faculty_type"], "school_id": row["school_id"],
                "department": row["department"], "term": t, "hours": bt["hours"], "max_hours": row["max_hours"],
                "overload_hours": bt["overload_hours"], "classes": classes, "notes": problems,
                "solvable": not any(c["recommended"] and not c["suggestions"] for c in classes) and left <= 1e-9 and bool(movable),
            })
    out.sort(key=lambda r: -r["overload_hours"])
    return {"overloaded": len(out), "items": out, "policy": wl.limits()["policy"]}


class AssignError(Exception):
    def __init__(self, detail, code=400, extra=None):
        super().__init__(detail)
        self.detail, self.code, self.extra = detail, code, extra or {}


def assign(user, schedule_ids, teacher_id):
    """Move one class (all its periods) to `teacher_id`, re-validating every rule. Raises AssignError; otherwise returns a report."""
    from faculty.models import FacultyProfile
    from .conflict_report import scan
    from .conflicts import find_conflicts
    from .views import _build_availability_rules
    from .models import TimeSlot
    rows = list(Schedule.objects.filter(pk__in=schedule_ids).select_related("subject", "subject__field", "subject__program",
                                                                            "section__program", "timeslot", "teacher__user"))
    teacher = FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(pk=teacher_id, user__is_active=True).first()
    if not rows or teacher is None:
        raise AssignError("Class or teacher not found.", 404)
    for r in rows:
        if not _can_edit(user, r):
            raise AssignError(f"{r.subject.title} cannot be changed from here: it is not a draft class you own, or it is shared.", 403)
    olds = {r.teacher_id for r in rows}
    if len(olds) != 1 or None in olds:
        raise AssignError("These periods do not belong to one teacher. Reload and try again.", 409)
    old = rows[0].teacher
    if old.id == teacher.id:
        raise AssignError("That teacher already has this class.", 400)
    r0 = rows[0]
    term = r0.term
    # 1 department + qualification (engine.teacher_scope: a major stays inside the department; Gen Ed keeps its own rule)
    from .teacher_scope import teacher_allowed
    _why = teacher_allowed(user, teacher, r0.subject, r0.section)
    if _why:
        raise AssignError(_why, 422)
    _pts, reasons = wl._qualification_match(r0.subject, teacher)          # for the report only: the rule above decides
    reasons = reasons or ["Qualified (specialization / same-discipline degree)"]
    # 2 availability (their submitted availability must cover every period)
    slots = [r.timeslot for r in rows]
    rules = _build_availability_rules([teacher], list(TimeSlot.objects.all()), r0.school_year, term or None)
    if any(s.id in rules.get(teacher.id, set()) for s in slots):
        raise AssignError(f"{wl._name(teacher)} is not available at the class time.", 422)
    with transaction.atomic():
        from . import locks
        if not locks.try_lock("classes"):
            raise AssignError(locks.BUSY, 409)
        # re-read inside the lock so a concurrent change cannot slip through
        fresh = list(Schedule.objects.select_for_update().filter(pk__in=schedule_ids))
        if any(f.teacher_id != old.id or f.status != "draft" for f in fresh):
            raise AssignError("This class was changed by someone else. Reload and try again.", 409)
        # 3 clashes (teacher busy / rooms / sections already enforced by find_conflicts for the teacher)
        for r in rows:
            msgs = find_conflicts(teacher=teacher, timeslot=r.timeslot, exclude_model="Schedule", exclude_pk=r.pk,
                                  merge_key=r.merge_key, semester=r.section.semester)
            if msgs:
                raise AssignError(f"{wl._name(teacher)} is not free: {msgs[0]}", 422)
        # 4 weekly limit (full-time / part-time) -- always strict here: an assignment that is meant to cure an overload must not create one
        over = wl.check_assignment(teacher, term, slots, [r.id for r in rows])
        if over:
            raise AssignError(over["message"], 409, {"workload_overload": over})
        ids = {r.id for r in rows}
        before = scan(semester=r0.section.semester, involving_ids=ids, limit=200)["total"]
        for r in rows:
            r.teacher = teacher
            r.is_manual_override = True
            r.save(update_fields=["teacher", "is_manual_override"])
        # 5 fresh validation of what is now saved: the change must not ADD a clash (older, unrelated ones are not blamed on it)
        clashes = scan(semester=r0.section.semester, involving_ids=ids, limit=200)
        if clashes["total"] > before:
            transaction.set_rollback(True)
            raise AssignError("The change would create a scheduling conflict, so nothing was saved.", 409,
                              {"conflicts": clashes["conflicts"][:10]})
    after = {r["faculty_id"]: r for r in wl.workload_rows([old, teacher], term=term)}
    o, n = after[old.id], after[teacher.id]
    return {
        "updated": len(rows), "subject": r0.subject.title, "section": f"{r0.section.program.name} {r0.section.name}",
        "from": {"id": old.id, "name": wl._name(old), "hours": o["current_hours"], "max_hours": o["max_hours"], "overload_hours": o["overload_hours"]},
        "to": {"id": teacher.id, "name": wl._name(teacher), "hours": n["current_hours"], "max_hours": n["max_hours"], "overload_hours": n["overload_hours"]},
        "checks": [
            {"label": "Qualified for the subject", "ok": True, "detail": "; ".join(reasons[:2])},
            {"label": "Inside their availability", "ok": True},
            {"label": "No teacher, room or student clash", "ok": True},
            {"label": f"{wl._name(teacher)} within weekly limit", "ok": n["overload_hours"] <= 0, "detail": f"{n['current_hours']:g} / {n['max_hours']:g} h"},
            {"label": f"{wl._name(old)} {'is no longer overloaded' if o['overload_hours'] <= 0 else 'is still overloaded'}", "ok": o["overload_hours"] <= 0,
             "detail": f"{o['current_hours']:g} / {o['max_hours']:g} h"},
        ],
    }


def summary(user):
    """Light list for the warning banner: each overloaded teacher with the subjects that make up the load."""
    scope = scope_profiles(user)
    rows = [r for r in wl.workload_rows(scope) if r["overload_hours"] > 0]
    if not rows:
        return {"overloaded": 0, "items": []}
    terms = {r["faculty_id"]: next(b["term"] for b in sorted(r["by_term"], key=lambda b: -b["overload_hours"]) if b["overload_hours"] > 0) for r in rows}
    sched = Schedule.objects.filter(teacher_id__in=list(terms)).select_related("subject", "section__program", "timeslot")
    seen, subj = set(), defaultdict(list)
    for sc in sched:
        if sc.term != terms[sc.teacher_id]:
            continue
        key = (sc.teacher_id, sc.subject_id, sc.section_id, sc.merge_key or "")
        if key in seen:
            continue
        seen.add(key)
        subj[sc.teacher_id].append(sc)
    hours = defaultdict(float)
    for sc in sched:
        if sc.term == terms[sc.teacher_id]:
            hours[(sc.teacher_id, sc.subject_id, sc.section_id, sc.merge_key or "")] += wl._hours(sc.timeslot)
    items = []
    for r in rows:
        t = terms[r["faculty_id"]]
        bt = next(b for b in r["by_term"] if b["term"] == t)
        items.append({
            "faculty_id": r["faculty_id"], "full_name": r["full_name"], "faculty_type": r["faculty_type"], "term": t,
            "hours": bt["hours"], "max_hours": r["max_hours"], "overload_hours": bt["overload_hours"],
            "subjects": sorted(({"code": sc.subject.code, "subject": sc.subject.title, "section": f"{sc.section.program.name} {sc.section.name}",
                                 "hours": round(hours[(sc.teacher_id, sc.subject_id, sc.section_id, sc.merge_key or "")], 2)}
                                for sc in subj[r["faculty_id"]]), key=lambda x: -x["hours"]),
        })
    items.sort(key=lambda i: -i["overload_hours"])
    return {"overloaded": len(items), "items": items}
