"""Optional Professor per subject in the Dean's Generate preview.

options()  -- READ-ONLY list of the qualified teachers of the Dean's own college for each major subject of one program / year /
              semester, with each teacher's current weekly load (engine.workload hour counting) and limit.
validate() -- re-checks the professors sent with Generate (role, college, qualification, availability, Lec/Lab pair) before
              anything is deleted or saved. A valid choice is then FIXED for that subject's sections in this run, like a fixed room:
              the engine may use that teacher and nobody else for it (rooms.rules.teacher_choice_for), and when the teacher cannot
              take a class the problems list says why (engine.scheduler.explain_unresolved). Nobody is swapped in silently."""
from .qualification import is_qualified, why_nobody
from .scheduler import LAB_HOURS_PER_UNIT, blocks_for_subject

_TITLES = {"dr", "prof", "engr", "mr", "mrs", "ms", "atty", "arch", "rev", "fr", "sr"}


def short_name(profile):
    """'Santos, J.' (titles such as Dr. / Prof. are left out); the username when no name is recorded."""
    u = profile.user
    first = [w for w in (u.first_name or "").split() if w.lower().rstrip(".") not in _TITLES]
    last = (u.last_name or "").strip()
    if not last:
        return u.get_full_name().strip() or u.username
    return f"{last}, {first[0][0]}." if first else last


def weekly_hours(subject):
    """Hours a subject takes per section per week: lecture units are hours, each lab unit is 3 hours (scheduler.blocks_for_subject)."""
    return float(subject.lec_units or 0) + float(subject.lab_units or 0) * LAB_HOURS_PER_UNIT


def _partner_code(subject):
    return subject.code[:-1] if subject.code.endswith("L") else subject.code + "L"


def limits_readonly():
    """The weekly limits from Settings WITHOUT creating the settings row (workload.limits() uses get_or_create)."""
    from .models import SchedulingConfig
    cfg = SchedulingConfig.objects.filter(pk=1).first() or SchedulingConfig()
    return {"full_time": cfg.max_weekly_hours_full_time, "part_time": cfg.max_weekly_hours_part_time, "policy": cfg.workload_policy}


def _college_teachers(dept):
    from faculty.models import FacultyProfile
    out = []
    for p in FacultyProfile.objects.filter(user__is_active=True).select_related("user").prefetch_related("specializations"):
        deps = p.user.departments or ([p.user.department] if p.user.department else [])
        if dept in deps:
            out.append(p)
    return out


def _window(raw):
    """{"start": "07:00", "end": "10:00", "day": "Mon"} from the dialog -> ((start, end) minutes | None, "Mon" | None)."""
    raw = raw if isinstance(raw, dict) else {}
    win = None
    try:
        a, b = str(raw.get("start") or ""), str(raw.get("end") or "")
        if a or b:
            win = (int(a[:2]) * 60 + int(a[3:5]) if a else 0, int(b[:2]) * 60 + int(b[3:5]) if b else 24 * 60)
    except (TypeError, ValueError, IndexError):
        win = None
    day = str(raw.get("day") or "")[:3].title() or None
    return win, day


def subject_groups(user, subject, sections, semester, replaced, window=None, day=None, school_year=None):
    """The three Professor groups (engine.faculty_groups) of one subject row of the Generate dialog."""
    from . import faculty_groups as fg
    n = max(1, len(sections))
    return fg.build(user, subject, sections[0], term=semester, school_year=school_year,
                    blocks=[int(round(float(h) * 60)) for h in blocks_for_subject(subject)], sections=n, window=window, day=day,
                    exclude_ids=replaced, need_hours=weekly_hours(subject) * n, after_label=True)


def _all_teachers():
    from faculty.models import FacultyProfile
    return list(FacultyProfile.objects.filter(user__is_active=True).select_related("user").prefetch_related("specializations"))


def options(program, year_level, semester, user=None, kind="major"):
    """Read-only. Qualified teachers of the program's college per major subject, with current load (the Workload page number, plus
    the hours left after Generate replaces this scope's drafts) and the three Professor groups per subject (engine.faculty_groups)."""
    from curriculum.models import Subject
    from .models import Schedule, Section
    from .workload import hours_by_teacher_term, limit_for

    dept = program.department
    sections = list(Section.objects.filter(program=program, year_level=year_level, semester=semester).select_related("program"))
    subjects = list(Subject.objects.filter(program=program, year_level=year_level, semester=semester, classification=kind)
                    .select_related("field", "program").order_by("code"))
    scope = Schedule.objects.filter(section__in=sections, subject__classification=kind)
    replaced = list(scope.filter(status="draft", is_manual_override=False).values_list("pk", flat=True))
    locked = set(scope.filter(is_manual_override=True).values_list("section_id", "subject_id"))
    # program subjects: the college's own faculty; Gen Ed: every active teacher (the Gen Ed rule decides who qualifies: CAS faculty of the
    # subject's area, or a teacher of another department with an explicit specialization for it)
    teachers = _college_teachers(dept) if kind == "major" else _all_teachers()
    spec = {t.id: {f.id for f in t.specializations.all()} for t in teachers}
    lim = limits_readonly()
    hrs = hours_by_teacher_term([t.id for t in teachers], exclude_schedule_ids=replaced)
    hrs_all = hours_by_teacher_term([t.id for t in teachers])          # what the Workload page shows
    by_code = {s.code: s for s in subjects}
    rows, used = [], set()
    for s in subjects:
        q = [t for t in teachers if sections and is_qualified(t, s, sections[0], spec[t.id])]
        used.update(t.id for t in q)
        n = sum(1 for sec in sections if (sec.id, s.id) not in locked)
        partner = by_code.get(_partner_code(s))
        rows.append({
            "subject_id": s.id, "code": s.code, "title": s.title, "lec_units": s.lec_units, "lab_units": s.lab_units,
            "hours_per_section": weekly_hours(s), "sections": n, "total_hours": weekly_hours(s) * n,
            "qualified": [t.id for t in sorted(q, key=lambda t: short_name(t).lower())],
            "partner_id": partner.id if partner else None,
            "blocks": [int(round(float(h) * 60)) for h in blocks_for_subject(s)],
            "no_qualified_reason": "" if q or not sections else why_nobody(s, sections[0], teachers, spec),
            "groups": subject_groups(user, s, sections, semester, replaced) if (user is not None and sections) else None,
        })
        if rows[-1]["groups"]:
            used.update(o["id"] for o in rows[-1]["groups"]["other"])        # not-connected faculty offered for this row
    info = {}
    week = free_week([t for t in teachers if t.id in used], semester, replaced)
    for t in teachers:
        if t.id not in used:
            continue
        cur = round(hrs.get(t.id, {}).get(semester, 0.0), 2)
        shown = round(hrs_all.get(t.id, {}).get(semester, 0.0), 2)
        info[t.id] = {"id": t.id, "label": short_name(t), "full_name": t.user.get_full_name().strip() or t.user.username,
                      "school_id": t.user.school_id, "username": t.user.username,
                      "faculty_type": t.user.faculty_type, "current_hours": shown, "projected_hours": cur,
                      "after_generate_hours": cur if abs(cur - shown) > 1e-9 else None, "max_hours": limit_for(t, lim),
                      **week.get(t.id, {"free": {}, "preferred": {}, "submitted": False})}
    return {"program_id": program.id, "department": dept, "year_level": year_level, "semester": semester,
            "policy": lim["policy"], "sections": len(sections), "subjects": rows, "teachers": info}


def validate(user, subjects_by_section, raw, school_year, semester, windows=None, replaced=()):
    """(error text | "", {subject_id: faculty_id}, {subject_id: override note}). Called by Generate BEFORE any draft is replaced.
    A value is a faculty id, or {"teacher": id, "override_qualification": true, "reason": "..."} for a manual Assign anyway (a person
    NOT connected to the subject), re-checked here against the groups computed now (faculty_groups.check_override)."""
    raw = raw or {}
    if not isinstance(raw, dict):
        return "Professor choices are not valid.", {}, {}
    picked, wants_override = {}, {}
    for key, tid in raw.items():
        if isinstance(tid, dict):
            if str(tid.get("override_qualification", "")).lower() in ("1", "true", "yes"):
                wants_override[str(key)] = str(tid.get("reason") or "")
            tid = tid.get("teacher")
        if tid in (None, "", 0, "0"):
            continue
        try:
            picked[int(key)] = int(tid)
        except (TypeError, ValueError):
            return "Professor choices are not valid.", {}, {}
    if not picked:
        return "", {}, {}
    is_dean = getattr(user, "role", "") == "faculty" and getattr(user, "faculty_type", "") == "dean"
    is_registrar = getattr(user, "role", "") == "registrar"
    if not (is_dean or is_registrar):
        return ("Only a Dean (program subjects of their own college) or the Registrar (Gen Ed subjects) chooses professors here. "
                "Leave the Professor on Automatic."), {}, {}
    from faculty.models import FacultyProfile
    from .models import TimeSlot
    from .views import _build_availability_rules
    subs = {s.id: s for lst in subjects_by_section.values() for s in lst}
    secs = {s.id: next(sec for sec, lst in subjects_by_section.items() if s in lst) for s in subs.values()}
    profiles = {p.id: p for p in FacultyProfile.objects.select_related("user").prefetch_related("specializations")
                .filter(pk__in=set(picked.values()))}
    rules = None
    out, overrides = {}, {}
    for sid, tid in picked.items():
        sub = subs.get(sid)
        if sub is None:
            continue                                   # not part of this run (e.g. locked by hand): nothing to apply
        if sub.classification == "minor" and not is_registrar:
            return (f"{sub.code} is a Gen Ed (minor) subject: its professor is chosen by the Registrar's generation, not here. "
                    "Leave it on Automatic."), {}, {}
        if sub.classification != "minor" and not is_dean:
            return (f"{sub.code} is a program subject: its professor is chosen by the Dean of the college. "
                    "Leave it on Automatic."), {}, {}
        sec = secs[sid]
        dept = sec.program.department
        p = profiles.get(tid)
        if p is None or not p.user.is_active:
            return f"The professor chosen for {sub.code} does not exist or is not active.", {}, {}
        name = p.user.get_full_name().strip() or p.user.username
        if is_dean and dept not in (user.departments or []):
            return (f"{sub.code} belongs to {dept}, which is not your department. Leave it on Automatic."), {}, {}
        from .teacher_scope import teacher_allowed           # the one department + qualification rule (also used by Edit -> Save)
        _why = teacher_allowed(user, p, sub, sec)
        if _why and str(sid) in wants_override and is_dean:          # Assign anyway: program subjects only, never Gen Ed
            # a manual Assign anyway: only the qualification check is skipped, and only after every other rule is re-checked now
            from . import faculty_groups as fg
            secs_of = [s_ for s_, lst in subjects_by_section.items() if sub in lst]
            win, day = _window((windows or {}).get(str(sid)) or (windows or {}).get(sid))
            groups = subject_groups(user, sub, secs_of or [sec], semester, list(replaced), window=win, day=day, school_year=school_year)
            try:
                reason = fg.check_override(user, sub, sec, p, wants_override[str(sid)], groups)
            except fg.OverrideError as e:
                return e.message, {}, {}
            overrides[sid] = fg.override_meta(user, reason)
            out[sid] = tid
            continue
        if _why:
            return _why + " Or leave it on Automatic.", {}, {}
        if rules is None:
            rules = _build_availability_rules(list(profiles.values()), list(TimeSlot.objects.all()), school_year, semester)
            slot_ids = set(TimeSlot.objects.values_list("id", flat=True))
        if slot_ids and slot_ids <= rules.get(p.id, set()):
            return (f"{name} has no available teaching time in {semester} (their submitted availability blocks every time). "
                    f"Choose another professor for {sub.code}, or update the availability first."), {}, {}
        out[sid] = tid
    # a Lecture and its Lab have ONE teacher: two different choices are refused; one choice covers the pair
    for sid, tid in list(out.items()):
        sub = subs[sid]
        partner = next((s for s in subs.values() if s.code == _partner_code(sub)), None)
        if partner is None:
            continue
        if partner.id in out and out[partner.id] != tid:
            lec, lab = (sub, partner) if not sub.code.endswith("L") else (partner, sub)
            return (f"{lec.code} and {lab.code} are the Lecture and Lab of one subject and must have the same professor. "
                    "Choose the same professor for both, or leave both on Automatic."), {}, {}
        if partner.id in out and sid in overrides and partner.id not in overrides:
            overrides[partner.id] = overrides[sid]           # one class: the same Assign anyway covers its Lec and Lab
        if partner.id not in out:
            p = profiles[tid]
            if sid in overrides:
                overrides[partner.id] = overrides[sid]
                out[partner.id] = tid
                continue
            if not is_qualified(p, partner, secs[partner.id], {f.id for f in p.specializations.all()}):
                name = p.user.get_full_name().strip() or p.user.username
                return (f"{name} is chosen for {sub.code}, but its Lecture and Lab must have the same professor and {name} is not "
                        f"qualified for {partner.code}. Choose another professor, or leave it on Automatic."), {}, {}
            out[partner.id] = tid
    return "", out, overrides


def _hm(t):
    return f"{t.hour:02d}:{t.minute:02d}"


def faculty_time(profile, semester, program=None, year_level=None):
    """READ-ONLY: one teacher's submitted availability, weekly load vs limit, and the classes they already teach in `semester`
    (back-to-back hours of one class merged into one block). With program + year_level, the drafts that Generate for that scope
    would replace are left out, exactly as in the Professor list (options)."""
    from . import availability as av
    from .models import Schedule, Section
    from .workload import hours_by_teacher_term, limit_for

    replaced = []
    if program is not None and year_level:
        secs = Section.objects.filter(program=program, year_level=year_level, semester=semester)
        replaced = list(Schedule.objects.filter(section__in=secs, subject__classification="major", status="draft",
                                                is_manual_override=False).values_list("pk", flat=True))
    windows = [{"day": w.day[:3].title(), "start": _hm(w.start_time), "end": _hm(w.end_time), "preference": w.preference}
               for w in av.rows([profile.id], None, semester).order_by("day", "start_time")]
    rows = (Schedule.objects.filter(teacher=profile, section__semester=semester).exclude(pk__in=replaced)
            .select_related("subject", "section", "room", "timeslot").order_by("timeslot__day", "timeslot__start_time"))
    blocks = []
    for r in rows:
        key = (r.timeslot.day[:3].title(), r.subject.code, r.room.name if r.room_id else "", r.merge_key or r.section.name)
        last = blocks[-1] if blocks else None
        if last and last["_key"] == key and last["end"] == _hm(r.timeslot.start_time):
            last["end"] = _hm(r.timeslot.end_time)
            continue
        if last and last["_key"][:3] == key[:3] and last["start"] == _hm(r.timeslot.start_time) and r.merge_key:
            continue                                       # a shared class: one block, not one per section
        blocks.append({"_key": key, "day": key[0], "start": _hm(r.timeslot.start_time), "end": _hm(r.timeslot.end_time),
                       "code": r.subject.code, "section": r.section.name, "room": key[2], "status": r.status})
    lim = limits_readonly()
    cur = round(hours_by_teacher_term([profile.id], exclude_schedule_ids=replaced).get(profile.id, {}).get(semester, 0.0), 2)
    return {"faculty_id": profile.id, "name": profile.user.get_full_name().strip() or profile.user.username,
            "label": short_name(profile), "faculty_type": profile.user.faculty_type, "department": profile.user.department or "",
            "semester": semester, "submitted": bool(windows), "availability": windows,
            "current_hours": cur, "max_hours": limit_for(profile, lim),
            "teaching": [{k: v for k, v in b.items() if k != "_key"}
                         for b in sorted(blocks, key=lambda b: (_DAY_ORDER.get(b["day"], 9), b["start"]))]}


_DAY_ORDER = {d: i for i, d in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))}


def _merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _minus(iv, cut):
    out = []
    for a, b in iv:
        pieces = [[a, b]]
        for c, d in cut:
            nxt = []
            for x, y in pieces:
                if d <= x or c >= y:
                    nxt.append([x, y])
                    continue
                if c > x:
                    nxt.append([x, c])
                if d < y:
                    nxt.append([d, y])
            pieces = nxt
        out += pieces
    return [p for p in out if p[1] > p[0]]


def free_week(teachers, semester, exclude_ids=()):
    """READ-ONLY, for the "Suggested" professors: {teacher_id: {"free": {day: [[start, end] minutes]}, "preferred": {...},
    "submitted": bool}}. Free = the college time-slot grid, inside the teacher's availability (all of it when nothing was submitted),
    minus the classes they already teach this semester. Rooms and the section's other classes are NOT considered: advice only."""
    from . import availability as av
    from .models import Schedule, TimeSlot
    mins = lambda t: t.hour * 60 + t.minute
    grid = {}
    from .college_break import overlaps as overlaps_college_break
    for day, a, b in TimeSlot.objects.values_list("day", "start_time", "end_time"):
        if overlaps_college_break(a, b):
            continue
        grid.setdefault(day[:3].title(), []).append([mins(a), mins(b)])
    grid = {d: _merge(v) for d, v in grid.items()}
    ids = [t.id for t in teachers]
    wins = {}
    for w in av.rows(ids, None, semester):
        wins.setdefault(w.faculty_id, []).append(w)
    busy = {}
    for tid, day, a, b in (Schedule.objects.filter(teacher_id__in=ids, section__semester=semester).exclude(pk__in=list(exclude_ids))
                           .values_list("teacher_id", "timeslot__day", "timeslot__start_time", "timeslot__end_time")):
        busy.setdefault((tid, day[:3].title()), []).append([mins(a), mins(b)])
    out = {}
    for t in teachers:
        ws = wins.get(t.id, [])
        good = [w for w in ws if w.preference != "unavailable"]
        bad = [w for w in ws if w.preference == "unavailable"]
        free, pref = {}, {}
        for day, iv in grid.items():
            day_good = [[mins(w.start_time), mins(w.end_time)] for w in good if w.day[:3].title() == day]
            allowed = iv if not good else [[max(a, c), min(b, d)] for a, b in iv for c, d in day_good if min(b, d) > max(a, c)]
            allowed = _minus(_merge(allowed), [[mins(w.start_time), mins(w.end_time)] for w in bad if w.day[:3].title() == day])
            allowed = _minus(allowed, _merge(busy.get((t.id, day), [])))
            if allowed:
                free[day] = _merge(allowed)
            p = [[mins(w.start_time), mins(w.end_time)] for w in good if w.preference == "preferred" and w.day[:3].title() == day]
            if p:
                pref[day] = _merge(p)
        out[t.id] = {"free": free, "preferred": pref, "submitted": bool(ws)}
    return out
