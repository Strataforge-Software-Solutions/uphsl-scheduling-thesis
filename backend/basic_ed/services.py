"""Generation, validation, calendar maths and reports for the SHS / JHS modules."""
import datetime as dt
from collections import defaultdict

from django.db import transaction

from .engine import Problem, build_grid, eligible, solve, to_min, to_time, window_breaks, DAY_KEYS
from .models import (AcademicYear, CalendarEvent, CalendarPeriod, ConflictRecord, CurriculumSubject, Faculty,
                     GradeWindow, PeriodMapping, Room, ScheduleEntry, ScheduleEvent, ScheduleRun, Section,
                     SchoolLevelConfig, TeachingAssignment)

WEEKDAYS = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


# ------------------------------------------------------------------ calendar
def instructional_days(level, academic_year, term):
    """Weekday class-day counts of a term, after removing holidays, examination blocks and suspensions."""
    if not term or not term.start_date or not term.end_date:
        return {"days": {}, "total": 0, "excluded": []}
    events = list(CalendarEvent.objects.filter(level=level, academic_year=academic_year, blocks_classes=True,
                                               end_date__gte=term.start_date, start_date__lte=term.end_date))
    counts, excluded, d = defaultdict(int), [], term.start_date
    while d <= term.end_date:
        if d.weekday() in WEEKDAYS:
            hit = next((e for e in events if e.start_date <= d <= e.end_date), None)
            if hit:
                excluded.append({"date": d.isoformat(), "reason": f"{hit.get_kind_display()}: {hit.name}"})
            else:
                counts[WEEKDAYS[d.weekday()]] += 1
        d += dt.timedelta(days=1)
    return {"days": dict(counts), "total": sum(counts.values()), "excluded": excluded}


def terms_for(grading_period):
    if grading_period.kind == "term":                # terms stand on their own
        return [grading_period]
    return [m.term for m in PeriodMapping.objects.filter(grading_period=grading_period).select_related("term")]


def grading_period_obj(level, academic_year, number, grade_level=None):
    """The calendar period a schedule run covers: a TERM (JHS, SHS Grade 11) or a SEMESTER (SHS Grade 12)."""
    from .structure import structure
    kind = structure(level, grade_level)[0]
    return CalendarPeriod.objects.filter(level=level, academic_year=academic_year, kind=kind, number=number).first()


# ------------------------------------------------------------------ curriculum validation
def validate_curriculum(level, academic_year, grading_period, grade_level=None):
    """Flags missing, duplicated, inconsistent or unverified curriculum records before generation."""
    issues = []

    def add(sev, kind, msg, **kw):
        issues.append(dict(severity=sev, kind=kind, message=msg, **kw))

    windows = {w.grade_level: w for w in GradeWindow.objects.filter(level=level)}
    grades = [grade_level] if grade_level else sorted(windows)
    cfg = SchoolLevelConfig.objects.get(level=level)
    faculty = list(Faculty.objects.filter(level=level, is_active=True))
    from .structure import structure, period_name, weeks_per_period
    for g in grades:
        w = windows.get(g)
        if not w:
            add("error", "no_window", f"Grade {g} has no daily time window configured.")
            continue
        kind_g, count_g = structure(level, g)
        if grading_period > count_g:
            add("error", "bad_period", f"Grade {g} has {count_g} {kind_g}s per school year; there is no {kind_g} {grading_period}.")
            continue
        for stray in CurriculumSubject.objects.filter(level=level, academic_year=academic_year, grade_level=g, is_active=True,
                                                      grading_period__gt=count_g)[:5]:
            add("warning", "outside_structure", f"Grade {g}: {stray.code} is set for period {stray.grading_period}, but Grade {g} only has "
                f"{count_g} {kind_g}s. It is ignored until you correct it.", subject_code=stray.code)
        if not w.framework_verified:
            add("warning", "framework_unverified", f"Grade {g}: curriculum framework '{w.curriculum_framework or 'not set'}' is not verified. {w.framework_note}")
        grid = build_grid(cfg, w)
        have_breaks = {label for label, _a, _b in window_breaks(w)}
        needed = ("Break",) if level == "SHS" else ("Recess", "Lunch")
        for need in needed:
            if need not in have_breaks:
                what = "the 15-minute break" if level == "SHS" else ("the 20-minute recess" if need == "Recess" else need.lower())
                add("error", "no_break", f"Grade {g}: {what} is not set. Every school day needs {'its break' if level == 'SHS' else 'recess and lunch'} -- set "
                    f"it in Settings > Daily time windows (or run: python manage.py set_basic_ed_breaks).")
        for label, bs, be_ in window_breaks(w):
            if bs < to_min(w.start_time) or be_ > to_min(w.end_time):
                add("error", "break_outside", f"Grade {g}: the {label.lower()} ({to_time(bs):%H:%M}-{to_time(be_):%H:%M}) is outside the school hours "
                    f"({w.start_time:%H:%M}-{w.end_time:%H:%M}).")
            expected_break = 15 if level == "SHS" else (20 if label == "Recess" else None)
            if expected_break is not None and be_ - bs != expected_break:
                add("error", "break_length", f"Grade {g}: {label.lower()} must be exactly {expected_break} minutes (it is {be_ - bs}).")
        sections = list(Section.objects.filter(level=level, academic_year=academic_year, grade_level=g, is_active=True).select_related("strand"))
        if not sections:
            add("error", "no_sections", f"Grade {g} has no sections.")
            continue
        subs = list(CurriculumSubject.objects.filter(level=level, academic_year=academic_year, grade_level=g, is_active=True,
                                                     grading_period__in=[0, grading_period]).select_related("strand"))
        if not subs:
            add("error", "no_curriculum", f"Grade {g}: no curriculum records for {period_name(level, g, grading_period)}. Import or encode them first.")
            continue
        # duplicates
        seen = defaultdict(list)
        for s in subs:
            seen[(s.strand_id, s.code)].append(s)
        for (_st, code), rows in seen.items():
            if len(rows) > 1:
                add("error", "duplicate", f"Grade {g}: subject code {code} appears {len(rows)} times for the same strand/period.", subject_code=code)
        for s in subs:
            if s.sessions_per_week < 1:
                add("error", "inconsistent", f"{s.code} has 0 sessions per week.", subject_code=s.code)
            weeks = 40 if s.grading_period == 0 else weeks_per_period(level, g, s.grading_period)
            if s.total_hours and s.sessions_per_week * cfg.period_minutes * weeks < float(s.total_hours) * 60 * 0.9:
                add("warning", "hours_short", f"{s.code} {s.name}: {s.sessions_per_week} x {cfg.period_minutes}-minute periods give about "
                    f"{s.sessions_per_week * cfg.period_minutes * weeks / 60:.0f} h, below the {float(s.total_hours):.0f} h in the curriculum.", subject_code=s.code)
            if not s.is_verified:
                add("warning", "unverified", f"{s.code} {s.name}: not read from an official DepEd document yet ({s.verification_note or 'review it'}).", subject_code=s.code)
        # every strand/section needs subjects and a qualified teacher
        for sec in sections:
            mine = {}
            for s in subs:
                if s.strand_id in (None, sec.strand_id):
                    if s.code not in mine or (s.strand_id and not mine[s.code].strand_id):
                        mine[s.code] = s
            if not mine:
                add("error", "section_no_subjects", f"Section {sec.name} (Grade {g}) has no subjects.", section=sec.id)
                continue
            demand = sum(s.sessions_per_week for s in mine.values())
            if demand > len(grid) * len(DAY_KEYS):
                add("error", "section_overload", f"Section {sec.name}: {demand} periods per week are required but the Grade {g} day only has "
                    f"{len(grid) * len(DAY_KEYS)} class periods ({len(grid)} per day) after the break(s). Lengthen the window or shorten the breaks.", section=sec.id)
            for s in mine.values():
                if not any(eligible(f, s) for f in faculty) and not TeachingAssignment.objects.filter(
                        section=sec, subject=s, qualification_override__isnull=False).exists():
                    add("error", "no_teacher", f"No active {level} teacher is qualified for {s.code} {s.name} (needs '{s.specialization or s.learning_area}').",
                        subject_code=s.code, section=sec.id)
    # teacher capacity: periods needed per required specialization vs the weekly hours of the teachers who hold it
    need_min = defaultdict(int)
    for g in grades:
        w = windows.get(g)
        if not w:
            continue
        secs = Section.objects.filter(level=level, academic_year=academic_year, grade_level=g, is_active=True)
        subs_g = CurriculumSubject.objects.filter(level=level, academic_year=academic_year, grade_level=g, is_active=True,
                                                  grading_period__in=[0, grading_period]).select_related("strand")
        for sec in secs:
            mine = {}
            for s2 in subs_g:
                if s2.strand_id in (None, sec.strand_id) and (s2.code not in mine or s2.strand_id):
                    mine[s2.code] = s2
            for s2 in mine.values():
                if s2.category != "guidance":
                    need_min[s2.specialization or s2.learning_area] += s2.sessions_per_week * cfg.period_minutes
    for spec, minutes in need_min.items():
        alts = {x.strip().lower() for x in spec.split("|") if x.strip()}
        cap = sum((f.max_weekly_hours or cfg.max_teacher_hours) * 60 for f in faculty if alts & (set(f.spec_list) | {(f.department or "").lower()}))
        if minutes > cap:
            add("warning", "capacity", f"Teaching hours may be short for '{spec}': {minutes / 60:.0f} h per week are required but the qualified teachers "
                f"can give {cap / 60:.0f} h (teachers shared between specializations can make this tighter).")
    # de-duplicate identical messages
    out, seen_msgs = [], set()
    for i in issues:
        k = (i["kind"], i["message"])
        if k not in seen_msgs:
            seen_msgs.add(k)
            out.append(i)
    return out


# ------------------------------------------------------------------ run validation
def validate_run(run):
    """Re-check a saved timetable against every hard rule. Returns a list of issue dicts."""
    level = run.level
    cfg = SchoolLevelConfig.objects.get(level=level)
    windows = {w.grade_level: w for w in GradeWindow.objects.filter(level=level)}
    entries = list(run.entries.select_related("section", "teacher__user", "room", "subject"))
    other_runs = ScheduleRun.objects.filter(level=level, academic_year=run.academic_year, grading_period=run.grading_period) \
        .exclude(status="superseded").exclude(id=run.id)
    others = list(ScheduleEntry.objects.filter(run__in=other_runs).select_related("section", "teacher__user", "room"))
    issues = []

    def add(sev, kind, msg, entry=None, section=None, code=""):
        issues.append(dict(severity=sev, kind=kind, message=msg, entry=(entry.id if entry else None),
                           section=(entry.section_id if entry else section), subject_code=(entry.subject_code if entry else code)))

    # unavailable-window lookups
    from .models import Availability
    avail = defaultdict(lambda: defaultdict(list))
    unav = defaultdict(lambda: defaultdict(list))
    for a in Availability.objects.filter(faculty__level=level):
        (avail if a.available else unav)[a.faculty_id][a.day].append((to_min(a.start_time), to_min(a.end_time)))

    sec_slots, tea_slots, room_slots = defaultdict(list), defaultdict(list), defaultdict(list)
    tea_minutes = defaultdict(int)
    for e in entries + others:
        s, f = to_min(e.start_time), to_min(e.end_time)
        sec_slots[e.section_id].append((e.day, s, f, e))
        if e.teacher_id:
            tea_slots[e.teacher_id].append((e.day, s, f, e))
            tea_minutes[e.teacher_id] += f - s
        if e.room_id:
            room_slots[e.room_id].append((e.day, s, f, e))

    def overlaps(bucket, label, getname):
        for key, rows in bucket.items():
            rows = sorted(rows, key=lambda r: (r[0], r[1]))
            for a, b in zip(rows, rows[1:]):
                if a[0] == b[0] and b[1] < a[2] and (a[3].run_id == run.id or b[3].run_id == run.id):
                    ent = a[3] if a[3].run_id == run.id else b[3]
                    add("error", f"{label}_conflict",
                        f"{getname(a[3])} is double-booked on {a[0]} {to_time(max(a[1], b[1])):%H:%M}: {a[3].subject_code} and {b[3].subject_code}.", entry=ent)

    overlaps(sec_slots, "section", lambda e: f"Section {e.section.name}")
    overlaps(tea_slots, "teacher", lambda e: f"Teacher {e.teacher.full_name}")
    overlaps(room_slots, "room", lambda e: f"Room {e.room.name}")

    for e in entries:
        w = windows.get(e.section.grade_level)
        s, f = to_min(e.start_time), to_min(e.end_time)
        if not w or s < to_min(w.start_time) or f > to_min(w.end_time):
            add("error", "outside_window", f"{e.subject_code} for {e.section.name} on {e.day} {e.start_time:%H:%M}-{e.end_time:%H:%M} is outside the Grade "
                f"{e.section.grade_level} window ({w.start_time:%H:%M}-{w.end_time:%H:%M}).", entry=e)
        if w:
            for label, bs, be_ in window_breaks(w):
                if s < be_ and f > bs:
                    add("error", "during_break", f"{e.subject_code} for {e.section.name} on {e.day} {e.start_time:%H:%M}-{e.end_time:%H:%M} overlaps "
                        f"{label.lower()} ({to_time(bs):%H:%M}-{to_time(be_):%H:%M}).", entry=e)
        if e.room_id:
            r = e.room
            if r.level != level or r.building != cfg.building or (cfg.floor is not None and r.floor != cfg.floor) or not r.is_active:
                add("error", "bad_room", f"Room {r.name} is not an eligible {level} classroom ({cfg.building}"
                    f"{', floor ' + str(cfg.floor) if cfg.floor is not None else ''}).", entry=e)
            elif e.subject and r.room_type != e.subject.required_room_type:
                add("error", "room_type", f"{e.subject_code} needs a {e.subject.required_room_type.replace('_', ' ')} but is in {r.name} ({r.room_type.replace('_', ' ')}).", entry=e)
            elif r.capacity < e.section.student_count:
                add("error", "room_capacity", f"Room {r.name} seats {r.capacity} but section {e.section.name} has {e.section.student_count} students.", entry=e)
        else:
            add("error", "no_room", f"{e.subject_code} for {e.section.name} on {e.day} has no room.", entry=e)
        if e.teacher_id:
            t = e.teacher
            if not t.is_active:
                add("error", "inactive_teacher", f"{t.full_name} is not an active teacher.", entry=e)
            if e.subject and not eligible(t, e.subject):
                if e.qualification_override:
                    add("warning", "assigned_anyway", f"{t.full_name} teaches {e.subject_code} by the Principal's choice (not connected). "
                        f"Reason: {e.qualification_override.get('reason', '')}", entry=e)
                else:
                    add("error", "not_qualified", f"{t.full_name} is not qualified for {e.subject_code}.", entry=e)
            if any(s < ue and f > us for us, ue in unav[t.id].get(e.day, [])):
                add("error", "teacher_unavailable", f"{t.full_name} is unavailable on {e.day} {e.start_time:%H:%M}-{e.end_time:%H:%M}.", entry=e)
            elif avail[t.id] and not any(s >= ws and f <= we for ws, we in avail[t.id].get(e.day, [])):
                add("error", "teacher_unavailable", f"{t.full_name} has no availability on {e.day} {e.start_time:%H:%M}-{e.end_time:%H:%M}.", entry=e)
        else:
            add("error", "no_teacher", f"{e.subject_code} for {e.section.name} on {e.day} has no teacher.", entry=e)

    for fid, minutes in tea_minutes.items():
        fac = next((r[3].teacher for r in tea_slots[fid] if r[3].teacher), None)
        if fac and minutes > (fac.max_weekly_hours or cfg.max_teacher_hours) * 60:
            add("error", "overload", f"{fac.full_name} teaches {minutes / 60:.1f} h per week (limit {fac.max_weekly_hours}).", section=None)

    # every required subject gets its sessions
    have = defaultdict(int)
    for e in entries:
        have[(e.section_id, e.subject_id)] += 1
    for sec in Section.objects.filter(level=level, academic_year=run.academic_year, grade_level=run.grade_level, is_active=True):
        subs = CurriculumSubject.objects.filter(level=level, academic_year=run.academic_year, grade_level=run.grade_level, is_active=True,
                                                grading_period__in=[0, run.grading_period])
        mine = {}
        for s in subs:
            if s.strand_id in (None, sec.strand_id):
                if s.code not in mine or (s.strand_id and not mine[s.code].strand_id):
                    mine[s.code] = s
        for s in mine.values():
            n = have.get((sec.id, s.id), 0)
            if n < s.sessions_per_week:
                add("error", "missing_sessions", f"{sec.name}: {s.code} {s.name} has {n} of {s.sessions_per_week} required periods.", section=sec.id, code=s.code)
                issues[-1]["missing"] = s.sessions_per_week - n
            elif n > s.sessions_per_week:
                add("warning", "extra_sessions", f"{sec.name}: {s.code} has {n} periods but only {s.sessions_per_week} are required.", section=sec.id, code=s.code)
    return issues


def refresh_validation(run):
    issues = validate_run(run)
    run.conflicts.all().delete()
    ConflictRecord.objects.bulk_create([
        ConflictRecord(run=run, kind=i["kind"], severity=i["severity"], section_id=i.get("section"),
                       subject_code=i.get("subject_code", ""), message=i["message"]) for i in issues])
    errors = sum(1 for i in issues if i["severity"] == "error")
    run.validation = {"errors": errors, "warnings": len(issues) - errors, "valid": errors == 0}
    run.save(update_fields=["validation"])
    return issues


# ------------------------------------------------------------------ generation
def log(run, action, actor=None, comment=""):
    ScheduleEvent.objects.create(run=run, action=action, actor=actor, comment=comment[:500])


def core_anchor(level, academic_year, grading_period, grade_level):
    """Grade 11 (3 terms): the whole-year subjects (the 5 core subjects, homeroom, a full-year TechPro elective) keep the
    SAME teacher, room, day and time in every term. Returns the entries of another term's timetable to copy, or []."""
    from .structure import structure
    if level != "SHS" or structure(level, grade_level) != ("term", 3):
        return []
    src = ScheduleRun.objects.filter(level=level, academic_year=academic_year, grade_level=grade_level) \
        .exclude(grading_period=grading_period).exclude(status="superseded").order_by("grading_period", "-version").first()
    if not src:
        return []
    return list(ScheduleEntry.objects.filter(run=src, subject__grading_period=0).select_related("subject", "section"))


@transaction.atomic
def generate(level, academic_year, grading_period, grade_level, actor, note=""):
    from engine import locks
    locks.require("basic_ed")   # one JHS/SHS generation at a time (see engine/locks.py)
    problem = Problem(level, academic_year, grading_period, grade_level)
    problem.anchor = core_anchor(level, academic_year, grading_period, grade_level)
    search_stats = {}
    assignments, unresolved = solve(problem, seed=grade_level * 7 + grading_period, stats=search_stats)
    previous = list(ScheduleRun.objects.filter(level=level, academic_year=academic_year, grading_period=grading_period,
                                               grade_level=grade_level).exclude(status="superseded"))
    version = (ScheduleRun.objects.filter(level=level, academic_year=academic_year, grading_period=grading_period,
                                          grade_level=grade_level).count()) + 1
    for p in previous:
        p.status = "superseded"
        p.save(update_fields=["status"])
        log(p, "superseded", actor, f"Replaced by version {version}")
    run = ScheduleRun.objects.create(level=level, academic_year=academic_year, grading_period=grading_period, grade_level=grade_level,
                                     version=version, created_by=actor, note=note or "Generated by the scheduling engine")
    # Assign-anyway pins: the note is copied onto their periods (same section, subject AND teacher), so the timetable shows the badge
    _ov = {(t.section_id, t.subject_id, t.faculty_id): t for t in TeachingAssignment.objects.filter(
        section__in=problem.sections, qualification_override__isnull=False).select_related("faculty__user", "subject", "section")}
    ScheduleEntry.objects.bulk_create([
        ScheduleEntry(run=run, section=a["section"], subject=a["subject"], subject_code=a["subject"].code, subject_name=a["subject"].name,
                      learning_area=a["subject"].learning_area, teacher=a["teacher"], room=a["room"], day=a["day"],
                      start_time=to_time(a["start"]), end_time=to_time(a["end"]),
                      qualification_override=(_ov[(a["section"].id, a["subject"].id, a["teacher"].id)].qualification_override
                                              if a["teacher"] is not None and (a["section"].id, a["subject"].id, a["teacher"].id) in _ov else None))
        for a in assignments])
    log(run, "generated", actor, f"{len(assignments)} periods placed, {len(unresolved)} could not be placed")
    from audit import recorder as _audit
    _audit.record("generate", "SHS/JHS timetable", run.id, user=actor,
                  summary=f"{level} Grade {grade_level} period {grading_period}: version {version}, {len(assignments)} periods placed",
                  old={"replaced_runs": [p.id for p in previous]},
                  new={"run": run.id, "level": level, "version": version, "placed": len(assignments), "not_placed": len(unresolved)})
    for t in _ov.values():
        log(run, "assigned_anyway", actor, f"{t.faculty.full_name} teaches {t.subject.code} ({t.section.name}) by the Principal's choice "
            f"(not connected). Reason: {t.qualification_override.get('reason', '')}")
    issues = refresh_validation(run)
    ConflictRecord.objects.bulk_create([
        ConflictRecord(run=run, kind=u["kind"], severity="error", section=u["section"], subject_code=u["subject"].code, message=u["message"])
        for u in unresolved])
    errors = run.conflicts.filter(severity="error").count()
    run.validation = {"errors": errors, "warnings": run.conflicts.filter(severity="warning").count(), "valid": errors == 0,
                      "unresolved": len(unresolved)}
    run.stats = {"placed": len(assignments), "unresolved": len(unresolved), "sections": len(problem.sections), "search": search_stats}
    run.save(update_fields=["validation", "stats"])
    return run, unresolved


# ------------------------------------------------------------------ reports
def run_report(run):
    entries = list(run.entries.select_related("section", "teacher__user", "room"))
    cfg = SchoolLevelConfig.objects.get(level=run.level)
    teacher_minutes, room_minutes = defaultdict(int), defaultdict(int)
    for e in entries:
        m = to_min(e.end_time) - to_min(e.start_time)
        if e.teacher_id:
            teacher_minutes[e.teacher_id] += m
        if e.room_id:
            room_minutes[e.room_id] += m
    teachers = []
    for f in Faculty.objects.filter(id__in=teacher_minutes).select_related("user"):
        cap = (f.max_weekly_hours or cfg.max_teacher_hours) * 60
        teachers.append({"id": f.id, "name": f.full_name, "hours": round(teacher_minutes[f.id] / 60, 1),
                         "max_hours": f.max_weekly_hours, "load_pct": round(100 * teacher_minutes[f.id] / cap)})
    teachers.sort(key=lambda t: -t["hours"])
    w = GradeWindow.objects.filter(level=run.level, grade_level=run.grade_level).first()
    window_min = (to_min(w.end_time) - to_min(w.start_time)) * 5 if w else 0
    rooms = []
    for r in Room.objects.filter(id__in=room_minutes):
        rooms.append({"id": r.id, "name": r.name, "type": r.room_type, "hours": round(room_minutes[r.id] / 60, 1),
                      "utilization_pct": round(100 * room_minutes[r.id] / window_min) if window_min else 0})
    rooms.sort(key=lambda r: -r["hours"])
    gp = grading_period_obj(run.level, run.academic_year, run.grading_period, run.grade_level)
    cal = []
    for t in (terms_for(gp) if gp else []):
        info = instructional_days(run.level, run.academic_year, t)
        cal.append({"term": t.name, "start": t.start_date, "end": t.end_date, "class_days": info["total"], "by_weekday": info["days"],
                    "excluded_dates": info["excluded"]})
    return {"teachers": teachers, "rooms": rooms, "calendar": cal, "entries": len(entries),
            "sections": len({e.section_id for e in entries})}
