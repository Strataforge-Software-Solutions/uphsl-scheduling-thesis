"""
Faculty workload monitoring.

Workload = distinct teaching hours per WEEK, per semester (term).  Every Schedule row is one
TimeSlot, so a teacher's hours are the summed durations of the DISTINCT timeslots they teach in a
term.  De-duplicating on (teacher, term, timeslot) means a shared minor class (several sections
attending one class: same teacher, same slot) is counted once, never once per section.

Limits come from the SchedulingConfig singleton (editable), per faculty classification -- nothing
is hard-coded here beyond the field names.
"""
from collections import defaultdict
from datetime import datetime, date

from .models import Schedule, SchedulingConfig, TimeSlot


def _hours(slot):
    a = datetime.combine(date.today(), slot.start_time)
    b = datetime.combine(date.today(), slot.end_time)
    return max((b - a).total_seconds() / 3600.0, 0.0)


def _fmt(h):
    h = round(h + 1e-9, 2)
    return str(int(h)) if h == int(h) else f"{h:g}"


def limits():
    cfg = SchedulingConfig.get_solo()
    return {
        "full_time": cfg.max_weekly_hours_full_time,
        "part_time": cfg.max_weekly_hours_part_time,
        "policy": cfg.workload_policy,
        "reserve_lunch_gap": bool(getattr(cfg, "reserve_lunch_gap", False)),
    }


def limit_for(profile, lim=None):
    lim = lim or limits()
    # Deans are faculty members and follow the full-time limit.
    return lim["part_time"] if profile.user.faculty_type == "part_time" else lim["full_time"]


def overload_message(name, hours, maximum):
    over = hours - maximum
    return (f"Faculty Workload Overload: {name} is assigned {_fmt(hours)} hours per week, "
            f"exceeding the permitted maximum of {_fmt(maximum)} hours per week by {_fmt(over)} hours.")


def _name(profile):
    return profile.user.get_full_name().strip() or profile.user.username


def hours_by_teacher_term(teacher_ids=None, exclude_schedule_ids=()):
    """{teacher_id: {term: hours}} with duplicate (teacher, term, timeslot) rows counted once."""
    qs = Schedule.objects.select_related("timeslot")
    if teacher_ids is not None:
        qs = qs.filter(teacher_id__in=list(teacher_ids))
    if exclude_schedule_ids:
        qs = qs.exclude(pk__in=list(exclude_schedule_ids))
    seen, out = set(), defaultdict(lambda: defaultdict(float))
    for sc in qs.only("teacher_id", "term", "timeslot__start_time", "timeslot__end_time", "timeslot__id"):
        key = (sc.teacher_id, sc.term, sc.timeslot_id)
        if key in seen:
            continue
        seen.add(key)
        out[sc.teacher_id][sc.term] += _hours(sc.timeslot)
    return out


def workload_rows(profiles=None, term=None):
    """One row per faculty: current hours (worst semester, or the requested one), the limit that
    applies to their classification, the overload, and a per-semester breakdown."""
    from faculty.models import FacultyProfile
    if profiles is None:
        profiles = FacultyProfile.objects.select_related("user").filter(user__is_active=True)
    profiles = list(profiles)
    lim = limits()
    hrs = hours_by_teacher_term([p.id for p in profiles])
    # distinct classes (subject + section, shared minor counted once per subject/slot group) for context
    cls = defaultdict(set)
    for sc in Schedule.objects.filter(teacher_id__in=[p.id for p in profiles]).values_list(
            "teacher_id", "term", "subject_id", "section_id", "merge_key"):
        cls[(sc[0], sc[1])].add((sc[2], sc[4] or sc[3]))
    rows = []
    for p in profiles:
        by_term = {t: round(h, 2) for t, h in hrs.get(p.id, {}).items()}
        if term:
            cur_term, cur = term, by_term.get(term, 0.0)
        elif by_term:
            cur_term, cur = max(by_term.items(), key=lambda kv: kv[1])
        else:
            cur_term, cur = "", 0.0
        mx = limit_for(p, lim)
        over = round(max(cur - mx, 0.0), 2)
        rows.append({
            "faculty_id": p.id,
            "school_id": p.user.school_id,
            "full_name": _name(p),
            "faculty_type": p.user.faculty_type,
            "department": p.user.department or "",
            "term": cur_term,
            "current_hours": round(cur, 2),
            "max_hours": mx,
            "remaining_hours": round(max(mx - cur, 0.0), 2),
            "overload_hours": over,
            "status": "overload" if over > 0 else ("at_limit" if cur >= mx and mx > 0 else "ok"),
            "classes": len(cls.get((p.id, cur_term), ())),
            "by_term": [{"term": t, "hours": h, "overload_hours": round(max(h - mx, 0), 2)}
                        for t, h in sorted(by_term.items())],
            "warning": overload_message(_name(p), cur, mx) if over > 0 else "",
        })
    rows.sort(key=lambda r: (-r["overload_hours"], -r["current_hours"], r["full_name"]))
    return rows


def projected(profile, term, new_slots, exclude_schedule_ids=()):
    """Hours this teacher would have in `term` after also teaching `new_slots` (TimeSlot objects).
    Slots they already teach in that term are not counted twice."""
    base = hours_by_teacher_term([profile.id], exclude_schedule_ids).get(profile.id, {})
    have_ids = set(Schedule.objects.filter(teacher=profile, term=term)
                   .exclude(pk__in=list(exclude_schedule_ids)).values_list("timeslot_id", flat=True))
    add = sum(_hours(s) for s in {s.id: s for s in new_slots}.values() if s.id not in have_ids)
    return base.get(term, 0.0) + add


def check_assignment(profile, term, new_slots, exclude_schedule_ids=()):
    """Returns None when within the limit, else a dict describing the overload."""
    hrs = projected(profile, term, new_slots, exclude_schedule_ids)
    mx = limit_for(profile)
    if hrs <= mx + 1e-9:
        return None
    return {
        "faculty_id": profile.id, "full_name": _name(profile), "faculty_type": profile.user.faculty_type,
        "term": term, "hours": round(hrs, 2), "max_hours": mx, "overload_hours": round(hrs - mx, 2),
        "message": overload_message(_name(profile), hrs, mx),
    }


def _overlaps(a, b):
    return a.day == b.day and a.start_time < b.end_time and b.start_time < a.end_time


_STOP = {"and", "of", "the", "in", "for", "to", "a", "an", "i", "ii", "iii", "iv", "lec", "lab", "lecture", "laboratory",
         "introduction", "fundamentals", "principles", "basic", "advanced", "with", "on", "science", "studies"}


def _tokens(text):
    import re
    return {t for t in re.findall(r"[a-z]{3,}", (text or "").lower()) if t not in _STOP}


def _qualification_match(subject, profile):
    """(points, reasons) from how well a teacher's degree / specialization / qualifications fit a subject."""
    reasons, pts = [], 0
    specs = [f.name for f in profile.specializations.all()]
    if subject is not None and subject.field_id is not None:
        if any(f.id == subject.field_id for f in profile.specializations.all()):
            pts += 5
            reasons.append(f"Specialization matches ({subject.field.name})")
    want = _tokens(getattr(subject, "title", "")) | _tokens(getattr(getattr(subject, "field", None), "name", ""))
    if want:
        deg = _tokens(profile.degree)
        spec = _tokens(" ".join(specs))
        qual = _tokens(profile.qualifications)
        if want & deg:
            pts += 3; reasons.append("Degree is related to the subject")
        if want & spec and "Specialization matches" not in " ".join(reasons):
            pts += 2; reasons.append("Specialization is related to the subject")
        if want & qual:
            pts += 1; reasons.append("Relevant license / training")
    # a program (major) subject is also fitted by a degree in the same discipline as its program, e.g. BS Nursing -> Nursing subjects
    if subject is not None and getattr(subject, "classification", "") == "major" and getattr(subject, "program", None) is not None:
        prog = _tokens(subject.program.name)
        if prog & (_tokens(profile.degree) | _tokens(" ".join(specs))) and not any("related" in r or "matches" in r for r in reasons):
            pts += 2; reasons.append("Degree matches the program")
    return pts, reasons


def _availability_text(profile_ids, school_year=None, semester=None):
    """{profile id: 'Mon 8:00AM-5:00PM; Tue ...'} from the availability they submitted (blank = they never restricted themselves)."""
    from faculty.models import Availability
    qs = Availability.objects.filter(faculty_id__in=list(profile_ids), is_active=True).exclude(preference="unavailable")
    if school_year:
        qs = qs.filter(school_year=school_year)
    if semester:
        qs = qs.filter(semester=semester)
    by = defaultdict(list)
    for a in qs.order_by("day", "start_time"):
        lab = lambda t: t.strftime("%I:%M%p").lstrip("0")
        by[a.faculty_id].append(f"{a.day[:3]} {lab(a.start_time)}-{lab(a.end_time)}")
    return {k: "; ".join(v[:6]) + ("…" if len(v) > 6 else "") for k, v in by.items()}


def no_available_text(diag, limit=8):
    """'No available faculty in your department (College of Computer Studies): Santos, J. - not qualified for CS101; ...' from the
    diag of suggest_replacements for a MAJOR subject; "" for a Gen Ed subject (its own message is used)."""
    if not diag or not diag.get("department"):
        return ""
    rej = diag.get("rejected") or []
    head = f"No available faculty in your department ({diag['department']})"
    if not rej:
        return head + ": no other faculty member of the department was found."
    bits = [f"{r['full_name']} - {r['reason']}" for r in rej[:limit]]
    return head + ": " + "; ".join(bits) + (f"; and {len(rej) - limit} more." if len(rej) > limit else ".")


def suggest_replacements(subject, term, slots, exclude_teacher_ids=(), limit=5, school_year=None, exclude_schedule_ids=(), diag=None,
                         user=None, section=None):
    """Qualified stand-ins for teaching `subject` at `slots` in `term`. They must be available (submitted availability covers the
    slots), free of clashes, and have capacity under their own limit.
    * MAJOR subject (a Dean's): only qualified faculty of the department (engine.teacher_scope -- the same rule as Edit -> Save);
      nobody from another department is ever considered, and there is no fallback. Ranked by lower current load first. When
      `diag` is given, diag["rejected"] lists every department teacher left out, with the reason (not qualified / outside their
      availability / already teaching <class> / would exceed their limit).
    * Gen Ed (minor) subject (the Registrar's): qualified under the College of Arts and Science rule (engine.qualification: CAS faculty
      of the subject's area, or another department's teacher with an explicit specialization for it); ranked by qualification fit,
      same college, then remaining capacity."""
    from faculty.models import FacultyProfile
    from .views import _build_availability_rules
    slots = list({s.id: s for s in slots}.values())
    need = sum(_hours(s) for s in slots)
    profiles = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations")
                    .filter(user__is_active=True).exclude(pk__in=list(exclude_teacher_ids)))
    scored = {}
    major = getattr(subject, "classification", "major") != "minor"
    rejected = []
    if major:
        from .teacher_scope import in_department, teacher_allowed, allowed_departments
        profiles = [p for p in profiles if in_department(p, subject, section, user)]    # other departments: never considered
        for p in profiles:
            # the department rule is ADDED to the matching used here before (never widened): both must agree
            pts, reasons = _qualification_match(subject, p)
            if teacher_allowed(user, p, subject, section) or pts == 0:
                rejected.append({"faculty_id": p.id, "full_name": _name(p), "reason": f"not qualified for {subject.code}"})
                continue
            scored[p.id] = (pts, reasons)
    else:
        # Gen Ed: the College of Arts and Science rule (engine.qualification, the same as generation and Edit -> Save); the word
        # match below only ranks the qualified ones
        from .teacher_scope import teacher_allowed
        for p in profiles:
            if teacher_allowed(user, p, subject, section):
                continue                                          # not CAS-qualified / no explicit specialization: never suggested
            pts, reasons = _qualification_match(subject, p)
            scored[p.id] = (max(pts, 1), reasons or ["Qualified for this Gen Ed area (College of Arts and Science rule)"])
    if diag is not None:
        diag.update(considered=len(profiles), qualified=len(scored), unavailable=0, busy=0, no_capacity=0, rejected=rejected,
                    department=", ".join(allowed_departments(user, subject, section) or []) if major else "")
    profiles = [p for p in profiles if p.id in scored]
    if not profiles:
        return []
    rules = _build_availability_rules(profiles, list(TimeSlot.objects.all()), school_year, term or None)
    busy = defaultdict(list)
    for sc in Schedule.objects.filter(teacher__in=profiles, term=term).exclude(
            pk__in=list(exclude_schedule_ids)).select_related("timeslot", "subject", "section"):
        busy[sc.teacher_id].append(sc)
    hrs = hours_by_teacher_term([p.id for p in profiles], exclude_schedule_ids)
    lim = limits()
    dept = getattr(getattr(subject, "program", None), "department", None)
    avail_text = _availability_text([p.id for p in profiles], school_year, term or None)
    out = []
    for p in profiles:
        if any(s.id in rules.get(p.id, set()) for s in slots):
            if diag is not None: diag["unavailable"] += 1
            if major:
                rejected.append({"faculty_id": p.id, "full_name": _name(p), "reason": "not free at that time (outside their availability)"})
            continue                                              # outside their availability
        clash = sorted({f"{b.subject.code} ({b.section.name})" for b in busy[p.id] if any(_overlaps(s, b.timeslot) for s in slots)})
        if clash:
            if diag is not None: diag["busy"] += 1
            if major:
                rejected.append({"faculty_id": p.id, "full_name": _name(p), "reason": f"not free at that time (already teaching {', '.join(clash)})"})
            continue                                              # already teaching then
        cur = hrs.get(p.id, {}).get(term, 0.0)
        mx = limit_for(p, lim)
        if cur + need > mx + 1e-9:
            if diag is not None: diag["no_capacity"] += 1
            if major:
                rejected.append({"faculty_id": p.id, "full_name": _name(p),
                                 "reason": f"would exceed their limit ({round(cur + need, 2):g} of {mx:g} hrs)"})
            continue                                              # no capacity left
        pts, reasons = scored[p.id]
        same = bool(dept and p.user.department == dept)
        if same:
            pts += 1; reasons = reasons + ["Same college"]
        reasons = reasons + ["Free at the class time", f"{round(mx - cur - need, 2):g} h/week capacity left after this class"]
        out.append({"faculty_id": p.id, "school_id": p.user.school_id, "full_name": _name(p),
                    "faculty_type": p.user.faculty_type, "department": p.user.department or "",
                    "degree": p.degree, "qualifications": p.qualifications,
                    "specializations": [f.name for f in p.specializations.all()],
                    "email": p.user.email,
                    "current_hours": round(cur, 2), "max_hours": mx,
                    "remaining_after": round(mx - cur - need, 2),
                    "score": pts, "reasons": reasons, "same_department": same,
                    "fit": "Specialization match" if any(r.startswith("Specialization matches") for r in reasons) else "Related degree / training",
                    "utilization_after": round((cur + need) / mx, 3) if mx else 1.0,
                    "hours_needed": round(need, 2), "availability": avail_text.get(p.id, "No availability limits submitted (open)")})
    if major:      # inside the department: the lower current load first, so work is spread rather than piled up
        out.sort(key=lambda r: (r["current_hours"], -r["score"], r["full_name"]))
    else:          # Gen Ed (unchanged): best qualification fit first; among equal fit the one who ends up LEAST loaded
        out.sort(key=lambda r: (-r["score"], r["utilization_after"], r["full_name"]))
    return out[:limit]


def generation_warnings(teacher_ids, term, exclude_schedule_ids=()):
    """Overload warnings (with replacement ideas) for teachers after a generation run."""
    from faculty.models import FacultyProfile
    out = []
    profiles = FacultyProfile.objects.select_related("user").filter(pk__in=list(teacher_ids))
    hrs = hours_by_teacher_term([p.id for p in profiles])
    lim = limits()
    for p in profiles:
        cur = hrs.get(p.id, {}).get(term, 0.0)
        mx = limit_for(p, lim)
        if cur > mx + 1e-9:
            out.append({"faculty_id": p.id, "full_name": _name(p), "faculty_type": p.user.faculty_type, "term": term,
                        "hours": round(cur, 2), "max_hours": mx, "overload_hours": round(cur - mx, 2),
                        "message": overload_message(_name(p), cur, mx)})
    return out
