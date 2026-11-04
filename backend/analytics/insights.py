"""Read-only insight cards (new, additive). Nothing in this module writes to the database, changes a schedule or runs the scheduler:
every function only reads, and reuses the existing rules (engine.placement.incomplete_groups, engine.conflict_report.scan,
engine.qualification, rooms.rules) instead of inventing new ones. The existing compute_analytics() output is not touched.

Stage 1 (IT admin): admin_health, admin_accounts, admin_audit."""
from collections import Counter, defaultdict

UNDO_TAG = "UNDO-SNAPSHOT "      # removal snapshots kept for Undo (engine.schedule_actions); not an audit event of their own


def _name(u):
    if u is None:
        return ""
    return (u.get_full_name() or "").strip() or u.username


# --------------------------------------------------------------------------------------------- 1a. system health
def admin_health(semester=None):
    from curriculum.models import Subject
    from engine.conflict_report import scan
    from engine.models import ConflictLog, Schedule, Section
    from engine.placement import incomplete_groups
    from faculty.models import FacultyProfile
    from rooms.models import Room

    sems = [semester] if semester else sorted(set(Section.objects.values_list("semester", flat=True)))
    # a class "was generated" when its section already has classes of the same kind (Gen Ed / major) in the schedule
    generated_kind = set(Schedule.objects.values_list("section_id", "subject__classification").distinct())
    unplaced, not_generated = [], 0
    for sem in sems:
        for sec, sub, have, need in incomplete_groups(sem):
            if (sec.id, sub.classification) in generated_kind:
                unplaced.append({"subject": f"{sub.code} {sub.title}", "section": f"{sec.program.name} {sec.name}",
                                 "department": sec.program.department, "kind": "Gen Ed" if sub.classification == "minor" else "Major",
                                 "semester": sem, "placed_hours": round(have / 60, 1), "needed_hours": round(need / 60, 1)})
            else:
                not_generated += 1
    conflicts = {"total": 0, "counts": {}}
    for sem in sems:
        rep = scan(semester=sem, limit=1)
        conflicts["total"] += rep["total"]
        for k, n in rep["counts"].items():
            conflicts["counts"][k] = conflicts["counts"].get(k, 0) + n
    logged_unplaced = ConflictLog.objects.filter(conflict_type="unresolved_csp", resolved=False).count()

    rooms_no_dept = [{"name": r.name, "type": r.room_type, "capacity": r.capacity}
                     for r in Room.objects.filter(department__isnull=True).order_by("name")] + \
                    [{"name": r.name, "type": r.room_type, "capacity": r.capacity}
                     for r in Room.objects.filter(department="").order_by("name")]

    no_spec = []
    for f in FacultyProfile.objects.select_related("user").prefetch_related("specializations").order_by("user__last_name"):
        if not f.specializations.all():
            no_spec.append({"name": _name(f.user), "department": f.user.department or "", "active": f.user.is_active,
                            "has_degree": bool((f.degree or "").strip() or (f.qualifications or "").strip())})

    have_curr = set(Subject.objects.values_list("program_id", "year_level", "semester").distinct())
    no_curr = [{"section": f"{s.program.name} {s.name}", "department": s.program.department, "year_level": s.year_level, "semester": s.semester}
               for s in Section.objects.select_related("program").order_by("program__name", "name")
               if (s.program_id, s.year_level, s.semester) not in have_curr]

    return {
        "semesters": sems,
        "unplaced_classes": len(unplaced), "unplaced": unplaced[:300],
        "not_generated_classes": not_generated,
        "open_conflicts": conflicts["total"], "conflict_counts": conflicts["counts"],
        "unresolved_unplaced_log_entries": logged_unplaced,
        "rooms_no_department": len(rooms_no_dept), "rooms_no_department_list": rooms_no_dept,
        "faculty_no_specialization": len(no_spec), "faculty_no_specialization_list": no_spec,
        "sections_no_curriculum": len(no_curr), "sections_no_curriculum_list": no_curr,
        "notes": [
            "Rooms with no department are shared rooms any college may use (that is normal for ordinary lecture rooms); "
            "a laboratory with no department is worth checking.",
            "Unplaced = classes with fewer hours than their units need, in year levels that were already generated. "
            "'Not generated yet' counts classes of year levels nobody has generated.",
        ],
    }


# --------------------------------------------------------------------------------------------- 1b. account hygiene
def admin_accounts():
    from django.contrib.auth import get_user_model
    User = get_user_model()

    def row(u):
        role = "IT admin" if u.is_it_admin else (u.faculty_type or u.role) if u.role == "faculty" else u.role
        return {"username": u.username, "name": _name(u), "role": role, "department": u.department or "",
                "school_level": u.school_level or "", "active": u.is_active,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "date_joined": u.date_joined.isoformat() if u.date_joined else None, "email": u.email or ""}

    users = list(User.objects.order_by("role", "username"))
    never = [row(u) for u in users if u.last_login is None and u.is_active]
    inactive = [row(u) for u in users if not u.is_active]
    by_email = defaultdict(list)
    for u in users:
        e = (u.email or "").strip().lower()
        if e:
            by_email[e].append(u)
    dupes = [{"email": e, "accounts": [row(u) for u in us]} for e, us in sorted(by_email.items()) if len(us) > 1]
    must_change = sum(1 for u in users if u.is_active and getattr(u, "must_change_password", False))
    return {"total_accounts": len(users), "never_signed_in": len(never), "never_signed_in_list": never,
            "inactive": len(inactive), "inactive_list": inactive,
            "duplicate_emails": len(dupes), "duplicate_email_list": dupes,
            "still_on_first_password": must_change,
            "accounts_without_email": sum(1 for u in users if not (u.email or "").strip())}


# --------------------------------------------------------------------------------------------- 1c. audit trail
def _category(lg):
    d = lg.details or ""
    if lg.action == "DELETE":
        return "removed"
    if d.startswith("Published:"):
        return "published"
    if d.startswith("Approved:"):
        return "approved"
    if d.startswith("Moved back to draft"):
        return "back to draft"
    if d.startswith("Not ") and "(conflict)" in d:
        return "blocked approval"
    if d.startswith("Moved ") and "schedule(s) from" in d:
        return "status change (summary)"
    if d.startswith("Restored by Undo"):
        return "restored (undo)"
    if d.startswith("Smart Resolve") or d.startswith("Conflict resolved") or d.startswith("Moved "):
        return "moved / resolved"
    if "WORKLOAD" in d:
        return "workload"
    if lg.action == "CREATE":
        return "created"
    return "edited"


def admin_audit(limit=300, category=None):
    from engine.models import Log, Schedule

    events = []
    for lg in Log.objects.exclude(details__startswith=UNDO_TAG).select_related("user").order_by("-timestamp")[:2000]:
        cat = _category(lg)
        if category and cat != category:
            continue
        events.append({"when": lg.timestamp, "who": _name(lg.user) or "—", "category": cat, "details": lg.details[:300], "source": "log"})
    # Generate runs are NOT written to the log: they are reconstructed from the classes that still exist (creation time only, no user).
    if not category or category == "generated":
        groups = Counter()
        for when, prog, year, sem in Schedule.objects.values_list("generated_at", "section__program__name", "section__year_level",
                                                                 "section__semester").order_by("-generated_at")[:5000]:
            groups[(when.replace(second=0, microsecond=0), prog, year, sem)] += 1
        for (when, prog, year, sem), n in groups.items():
            events.append({"when": when, "who": "not recorded", "category": "generated",
                           "details": f"{n} class period(s) created for {prog} {year} {sem} (still in the schedule)", "source": "classes"})
    events.sort(key=lambda e: e["when"], reverse=True)
    events = events[:limit]
    for e in events:
        e["when"] = e["when"].isoformat()
    return {"events": events, "categories": sorted({e["category"] for e in events}),
            "not_recorded": [
                "Who ran Generate is not stored: a generate run writes no log entry and a class keeps only its creation time. "
                "Generated events are rebuilt from the classes still in the schedule, so removed or regenerated classes leave no trace.",
                "Admin > Data Tools 'clear generated' writes no log entry.",
                "Approve / publish / back to draft / remove / undo are logged per class with the user since the Schedules-tab update; "
                "earlier approvals are only stored on the class itself (its latest approver and time).",
            ]}


# ============================================================================================= Stage 2: Deans
DAY_ORDER = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _m(t):
    return t.hour * 60 + t.minute


def _sy(qs, school_year, prefix=""):
    """Filter a Schedule queryset by school year (Schedule.school_year, e.g. "2026-2027")."""
    return qs.filter(**{f"{prefix}school_year": school_year}) if school_year else qs


def _pick_semester(qs, semester):
    """The requested semester, or the one with the most classes in scope (1st and 2nd Sem never add up)."""
    if semester:
        return semester
    counts = Counter(qs.values_list("section__semester", flat=True))
    return max(counts, key=lambda k: (counts[k], k == "1st Sem")) if counts else None


def dean_readiness(departments=None, semester=None, kind="major", program_id=None, school_year=None):
    """Per program + year level + semester: classes Published / Approved / Draft (fully placed) and Unplaced (fewer hours than their
    units need, including year levels not generated yet). One class = one section x one subject."""
    from curriculum.models import Program, Subject
    from engine.models import Schedule, Section
    from engine.placement import expected_minutes

    progs = Program.objects.all()
    if departments is not None:
        progs = progs.filter(department__in=departments)
    if program_id:
        progs = progs.filter(pk=program_id)
    secs = Section.objects.filter(program__in=progs).select_related("program")
    if semester:
        secs = secs.filter(semester=semester)
    secs = list(secs)
    subs = Subject.objects.filter(program__in=progs)
    if kind in ("major", "minor"):
        subs = subs.filter(classification=kind)
    by_py = defaultdict(list)
    for s in subs:
        by_py[(s.program_id, s.year_level, s.semester)].append(s)
    placed, stage = defaultdict(int), defaultdict(set)
    for sec_id, sub_id, st, en, status in _sy(Schedule.objects.filter(section__in=secs), school_year).values_list(
            "section_id", "subject_id", "timeslot__start_time", "timeslot__end_time", "status"):
        placed[(sec_id, sub_id)] += _m(en) - _m(st)
        stage[(sec_id, sub_id)].add(status)
    rows = {}
    for sec in secs:
        key = (sec.program.name, sec.program.department, sec.year_level, sec.semester)
        r = rows.setdefault(key, {"program": key[0], "department": key[1], "year_level": key[2], "semester": key[3], "sections": 0,
                                  "classes": 0, "published": 0, "approved": 0, "draft": 0, "unplaced": 0})
        r["sections"] += 1
        for sub in by_py.get((sec.program_id, sec.year_level, sec.semester), []):
            r["classes"] += 1
            k = (sec.id, sub.id)
            if placed.get(k, 0) < expected_minutes(sub):
                r["unplaced"] += 1
            elif "draft" in stage[k]:
                r["draft"] += 1                                    # a class is only as far as its least advanced period
            elif "approved" in stage[k]:
                r["approved"] += 1
            else:
                r["published"] += 1
    out = sorted(rows.values(), key=lambda r: (r["program"], r["semester"], r["year_level"]))
    for r in out:
        n = r["classes"]
        r["placed"] = n - r["unplaced"]
        r["placed_pct"] = round(r["placed"] / n * 100) if n else 0
        r["published_pct"] = round(r["published"] / n * 100) if n else 0
    tot = {k: sum(r[k] for r in out) for k in ("classes", "placed", "published", "approved", "draft", "unplaced")}
    return {"kind": kind, "semester": semester, "school_year": school_year, "rows": out, "totals": tot}


def dean_faculty_fit(departments=None, semester=None, program_id=None, school_year=None):
    """Subjects with no qualified teacher, and classes taught by a teacher who does not meet the qualification rule
    (engine.qualification -- the same rule the generator uses), or who meets it only through a degree with no recorded specialization."""
    from types import SimpleNamespace
    from curriculum.models import Subject
    from engine.models import Schedule
    from engine.qualification import is_qualified
    from faculty.models import FacultyProfile

    teachers = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(user__is_active=True))
    spec = {t.id: {f.id for f in t.specializations.all()} for t in teachers}
    subs = Subject.objects.select_related("program", "field").filter(classification="major")
    if departments is not None:
        subs = subs.filter(program__department__in=departments)
    if semester:
        subs = subs.filter(semester=semester)
    if program_id:
        subs = subs.filter(program_id=program_id)
    nobody = []
    for s in subs.order_by("program__name", "year_level", "code"):
        fake_section = SimpleNamespace(program=s.program)
        if not any(is_qualified(t, s, fake_section, spec[t.id]) for t in teachers):
            nobody.append({"code": s.code, "title": s.title, "program": s.program.name, "year_level": s.year_level, "semester": s.semester,
                           "field": s.field.name if s.field_id else "", "why": "No field recorded: tag it in Curriculum." if not s.field_id
                           else f"No active teacher has '{s.field.name}' as a specialization or a same-discipline degree in this college."})
    qs = Schedule.objects.select_related("subject__field", "subject__program", "section__program", "teacher__user") \
        .prefetch_related("teacher__specializations")
    if departments is not None:
        qs = qs.filter(section__program__department__in=departments)
    if semester:
        qs = qs.filter(section__semester=semester)
    if program_id:
        qs = qs.filter(section__program_id=program_id)
    qs = _sy(qs, school_year)
    outside, by_degree, seen = [], [], set()
    for r in qs:
        k = (r.teacher_id, r.section_id, r.subject_id)
        if k in seen:
            continue
        seen.add(k)
        ids = spec.get(r.teacher_id)
        if ids is None:                                            # an inactive teacher still on a class
            ids = {f.id for f in r.teacher.specializations.all()}
        item = {"teacher": _name(r.teacher.user), "teacher_department": r.teacher.user.department or "", "code": r.subject.code,
                "title": r.subject.title, "section": f"{r.section.program.name} {r.section.name}", "status": r.status,
                "kind": "Gen Ed" if r.subject.classification == "minor" else "Major",
                "field": r.subject.field.name if r.subject.field_id else ""}
        if not is_qualified(r.teacher, r.subject, r.section, ids):
            outside.append(item)
        elif r.subject.field_id and r.subject.field_id not in ids:
            by_degree.append(item)
    return {"subjects_without_qualified_faculty": nobody, "teaching_outside_specialization": outside,
            "qualified_by_degree_only": by_degree,
            "notes": ["Qualification uses the system's rule (engine/qualification.py): a recorded specialization, or a same-discipline degree "
                      "inside the subject's college for majors.",
                      "'Qualified by degree only': allowed by the rule, but the subject's field is not one of the teacher's recorded "
                      "specializations. Recording it in the Faculty tab makes the match explicit."]}


def dean_lab_capacity(departments=None, semester=None, program_id=None, school_year=None):
    """Designated laboratories (rooms.rules.designated_rooms, e.g. Comp Lab C / D for Computer Studies): hours booked vs free per day.
    Free hours = the time-slot table's day span minus booked hours (a shared class is counted once)."""
    from engine.models import Schedule, TimeSlot
    from rooms import rules as rr
    from rooms.models import Room

    rooms = list(Room.objects.all())
    deps = departments if departments is not None else sorted({r.department for r in rooms if r.department})
    labs = []
    for d in deps:
        for r in rr.designated_rooms(rooms, d) or []:
            if r not in labs:
                labs.append(r)
    span = {}
    for day, st, en in TimeSlot.objects.values_list("day", "start_time", "end_time"):
        d = day[:3]
        lo, hi = span.get(d, (24 * 60, 0))
        span[d] = (min(lo, _m(st)), max(hi, _m(en)))
    days = [d for d in DAY_ORDER if d in span]
    qs = _sy(Schedule.objects.filter(room__in=labs), school_year)
    if program_id:                                  # only that program's classes (the lab's other bookings then count as free)
        qs = qs.filter(section__program_id=program_id)
    sem = _pick_semester(qs, semester)
    if sem:
        qs = qs.filter(section__semester=sem)
    booked = defaultdict(set)
    for room_id, slot_id, day, st, en in qs.values_list("room_id", "timeslot_id", "timeslot__day", "timeslot__start_time", "timeslot__end_time"):
        booked[(room_id, day[:3])].add((slot_id, _m(st), _m(en)))
    out = []
    for r in labs:
        per = []
        for d in days:
            ivs = sorted((s, e) for _i, s, e in booked.get((r.id, d), ()))
            used, cur = 0, None                                       # union of the booked intervals (overlaps never counted twice)
            for s, e in ivs:
                if cur and s <= cur[1]:
                    cur[1] = max(cur[1], e)
                else:
                    if cur:
                        used += cur[1] - cur[0]
                    cur = [s, e]
            if cur:
                used += cur[1] - cur[0]
            avail = span[d][1] - span[d][0]
            per.append({"day": d, "used_hours": round(used / 60, 1), "free_hours": round(max(avail - used, 0) / 60, 1),
                        "available_hours": round(avail / 60, 1), "used_pct": round(used / avail * 100) if avail else 0})
        tu, ta = sum(p["used_hours"] for p in per), sum(p["available_hours"] for p in per)
        out.append({"room": r.name, "label": r.label or "", "department": r.department or "", "capacity": r.capacity, "days": per,
                    "used_hours": round(tu, 1), "free_hours": round(ta - tu, 1), "used_pct": round(tu / ta * 100) if ta else 0})
    return {"semester": sem, "labs": out,
            "note": "" if out else "This college has no designated laboratories (only Computer Studies has the Comp Lab C / D rule)."}


def _limits_readonly():
    """The weekly limits from Settings, read WITHOUT creating the settings row (engine.workload.limits() uses get_or_create)."""
    from engine.models import SchedulingConfig
    cfg = SchedulingConfig.objects.filter(pk=1).first() or SchedulingConfig()        # unsaved defaults when the row is missing
    return {"full_time": cfg.max_weekly_hours_full_time, "part_time": cfg.max_weekly_hours_part_time}


def dean_load_bands(departments=None, semester=None, under_pct=50, program_id=None):
    """Teachers of the college (plus outside teachers on its classes) in bands by weekly hours against their own limit (the same
    limits and hour counting as engine.workload): overloaded = above the limit, normal, underloaded = below `under_pct` % of the limit
    (a display band only, not a scheduling rule: the system has no minimum load)."""
    from django.db.models import Q
    from engine.models import Schedule
    from engine.workload import hours_by_teacher_term
    from faculty.models import FacultyProfile

    profiles = FacultyProfile.objects.select_related("user").filter(user__is_active=True)
    if departments is not None:
        on_classes = set(Schedule.objects.filter(section__program__department__in=departments).values_list("teacher_id", flat=True))
        q = Q(pk__in=on_classes)
        for d in departments:
            q |= Q(user__department=d)
        profiles = profiles.filter(q)
    if program_id:                                  # teachers of that program's classes (their hours still count every class)
        profiles = profiles.filter(pk__in=set(Schedule.objects.filter(section__program_id=program_id).values_list("teacher_id", flat=True)))
    profiles = list(profiles)
    lim = _limits_readonly()
    hrs = hours_by_teacher_term([p.id for p in profiles])
    classes = defaultdict(set)
    for tid, term, sub, sec, mk in Schedule.objects.filter(teacher_id__in=[p.id for p in profiles]).values_list(
            "teacher_id", "term", "subject_id", "section_id", "merge_key"):
        classes[(tid, term)].add((sub, mk or sec))
    bands = {"overloaded": [], "normal": [], "underloaded": []}
    for p in profiles:
        by_term = hrs.get(p.id, {})
        if semester:
            term, cur = semester, by_term.get(semester, 0.0)
        elif by_term:
            term, cur = max(by_term.items(), key=lambda kv: kv[1])     # worst semester, like the Workload tab
        else:
            term, cur = "", 0.0
        mx = lim["part_time"] if p.user.faculty_type == "part_time" else lim["full_time"]
        over = round(max(cur - mx, 0.0), 2)
        b = "overloaded" if over > 0 else ("underloaded" if mx and cur < mx * under_pct / 100.0 else "normal")
        bands[b].append({"faculty_id": p.id, "full_name": _name(p.user), "faculty_type": p.user.faculty_type or "",
                         "department": p.user.department or "", "term": term, "current_hours": round(cur, 2), "max_hours": mx,
                         "overload_hours": over, "remaining_hours": round(max(mx - cur, 0.0), 2),
                         "classes": len(classes.get((p.id, term), ()))})
    for v in bands.values():
        v.sort(key=lambda r: (-r["overload_hours"], -r["current_hours"], r["full_name"]))
    return {"semester": semester, "under_pct": under_pct, "counts": {k: len(v) for k, v in bands.items()}, "bands": bands,
            "note": f"Underloaded = below {under_pct}% of the teacher's own weekly limit. This band is for review only; the system "
                    "has no minimum-load rule. Overloaded uses the existing limit (Settings)."}


# ============================================================================================= Stage 3: Registrar
def _class_key(sec_id, sub_id, merge_key):
    """One class: a shared class (merge_key) is ONE class however many sections attend it."""
    return ("m", merge_key) if merge_key else ("s", sec_id, sub_id)


def registrar_gened_coverage(semester=None, departments=None, program_id=None, school_year=None):
    """Per Gen Ed (minor) subject -- grouped like the shared-class feature (same code, units and title): sections that take it,
    sections placed, sections attending a shared class, the number of classes actually held, and what sharing saves
    (classes and weekly teaching hours that would otherwise be needed)."""
    from curriculum.models import Subject
    from engine.models import Schedule, Section
    from engine.placement import expected_minutes
    from engine.shared_classes import key_of

    secs = Section.objects.select_related("program")
    if semester:
        secs = secs.filter(semester=semester)
    if departments is not None:
        secs = secs.filter(program__department__in=departments)
    if program_id:
        secs = secs.filter(program_id=program_id)
    secs = list(secs)
    subs = list(Subject.objects.filter(classification="minor", program__in={s.program_id for s in secs}).select_related("program"))
    by_py = defaultdict(list)
    for s in subs:
        by_py[(s.program_id, s.year_level, s.semester)].append(s)
    rows_by = defaultdict(list)
    for sec_id, sub_id, mk, st, en in _sy(Schedule.objects.filter(section__in=secs, subject__classification="minor"), school_year).values_list(
            "section_id", "subject_id", "merge_key", "timeslot__start_time", "timeslot__end_time"):
        rows_by[(sec_id, sub_id)].append((mk, _m(en) - _m(st)))
    groups = {}
    for sec in secs:
        for sub in by_py.get((sec.program_id, sec.year_level, sec.semester), []):
            k = (sec.semester,) + key_of(sub)
            g = groups.setdefault(k, {"code": sub.code, "title": sub.title, "units": sub.lec_units + sub.lab_units, "semester": sec.semester,
                                      "programs": set(), "sections": 0, "placed": 0, "shared_sections": 0, "classes": set(),
                                      "hours": expected_minutes(sub) / 60.0})
            g["programs"].add(sec.program.name)
            g["sections"] += 1
            rows = rows_by.get((sec.id, sub.id), [])
            if sum(m for _mk, m in rows) >= expected_minutes(sub):
                g["placed"] += 1
            mks = {mk for mk, _m2 in rows if mk}
            if mks:
                g["shared_sections"] += 1
            for mk in mks or ({None} if rows else set()):
                g["classes"].add(_class_key(sec.id, sub.id, mk))
    out = []
    for g in groups.values():
        held = len(g["classes"])
        placed_sections = g["placed"]
        saved = max(placed_sections - held, 0)                # sections placed minus classes actually held
        out.append({"code": g["code"], "title": g["title"], "units": g["units"], "semester": g["semester"], "programs": sorted(g["programs"]),
                    "sections": g["sections"], "placed_sections": placed_sections, "unplaced_sections": g["sections"] - placed_sections,
                    "shared_sections": g["shared_sections"], "classes_held": held, "classes_saved": saved,
                    "teaching_hours_saved": round(saved * g["hours"], 1)})
    out.sort(key=lambda r: (r["semester"], r["code"]))
    tot = {k: sum(r[k] for r in out) for k in ("sections", "placed_sections", "unplaced_sections", "shared_sections", "classes_held",
                                               "classes_saved", "teaching_hours_saved")}
    return {"semester": semester, "subjects": out, "totals": tot,
            "note": "Saved = sections placed minus the classes actually held: each shared class serves several sections with one "
                    "teacher, one room and one time. Weekly teaching hours saved = classes saved x the subject's weekly hours."}


def room_heatmap(semester=None, departments=None, room_type=None, program_id=None, school_year=None):
    """Day x hour grid: how many rooms are booked in each hour, out of the rooms that exist (optionally one room type).
    For a Dean (departments given) only the classes of their college are counted."""
    from engine.models import Schedule, TimeSlot
    from rooms.models import Room

    rooms = Room.objects.exclude(room_type="offsite")
    if room_type:
        rooms = rooms.filter(room_type=room_type)
    room_ids = set(rooms.values_list("id", flat=True))
    qs = _sy(Schedule.objects.filter(room_id__in=room_ids), school_year)
    if departments is not None:
        qs = qs.filter(section__program__department__in=departments)
    if program_id:
        qs = qs.filter(section__program_id=program_id)
    sem = _pick_semester(qs, semester)
    if sem:
        qs = qs.filter(section__semester=sem)
    span = {}
    for day, st, en in TimeSlot.objects.values_list("day", "start_time", "end_time"):
        d = day[:3]
        lo, hi = span.get(d, (24 * 60, 0))
        span[d] = (min(lo, _m(st)), max(hi, _m(en)))
    days = [d for d in DAY_ORDER if d in span]
    first = min((s for s, _e in span.values()), default=7 * 60) // 60
    last = (max((e for _s, e in span.values()), default=20 * 60) + 59) // 60
    hours = list(range(first, last))
    busy = defaultdict(set)                                     # (day, hour) -> rooms booked at any minute of that hour
    for room_id, day, st, en in qs.values_list("room_id", "timeslot__day", "timeslot__start_time", "timeslot__end_time"):
        for h in hours:
            if _m(st) < (h + 1) * 60 and _m(en) > h * 60:
                busy[(day[:3], h)].add(room_id)
    total = len(room_ids)
    cells = [{"day": d, "hour": h, "rooms_busy": len(busy.get((d, h), ())), "pct": round(len(busy.get((d, h), ())) / total * 100) if total else 0}
             for d in days for h in hours]
    peak = max(cells, key=lambda c: c["rooms_busy"], default=None)
    return {"semester": sem, "rooms": total, "days": days, "hours": hours, "cells": cells,
            "peak": peak if peak and peak["rooms_busy"] else None, "room_type": room_type or ""}


def registrar_dependencies(semester=None, departments=None, program_id=None):
    """(1) Major classes that cannot be placed because the section's Gen Ed classes take every time long enough for them:
    with the Gen Ed classes the section has no free window of the needed length, without them it would.
    (2) Shared Gen Ed groups still waiting for the Registrar's confirmation."""
    from engine.models import Schedule, Section, SharedClassGroup, TimeSlot
    from engine.placement import incomplete_groups
    from engine.scheduler import blocks_for_subject

    span = {}
    for day, st, en in TimeSlot.objects.values_list("day", "start_time", "end_time"):
        d = day[:3]
        lo, hi = span.get(d, (24 * 60, 0))
        span[d] = (min(lo, _m(st)), max(hi, _m(en)))

    def longest_free(busy_ivs):
        best = 0
        for d, (lo, hi) in span.items():
            ivs = sorted((s, e) for dd, s, e in busy_ivs if dd == d)
            cur = lo
            for s, e in ivs:
                best = max(best, s - cur)
                cur = max(cur, e)
            best = max(best, hi - cur)
        return best

    sems = [semester] if semester else sorted(set(Section.objects.values_list("semester", flat=True)))
    generated = set(Schedule.objects.filter(subject__classification="major").values_list("section_id", flat=True).distinct())
    blocked = []
    for sem in sems:
        groups = [g for g in incomplete_groups(sem, kind="major", program_id=program_id, departments=departments) if g[0].id in generated]
        rows = defaultdict(list)
        for sec_id, cls_, code, title, day, st, en in Schedule.objects.filter(section_id__in={g[0].id for g in groups}).values_list(
                "section_id", "subject__classification", "subject__code", "subject__title", "timeslot__day", "timeslot__start_time",
                "timeslot__end_time"):
            rows[sec_id].append((cls_, code, title, day[:3], _m(st), _m(en)))
        for sec, sub, have, need in groups:
            blk = max(int(round(float(h) * 60)) for h in blocks_for_subject(sub))     # the longest unbroken period (a pair: one session)
            all_ivs = [(d, s, e) for _c, _code, _t, d, s, e in rows[sec.id]]
            major_ivs = [(d, s, e) for c, _code, _t, d, s, e in rows[sec.id] if c != "minor"]
            if longest_free(all_ivs) < blk <= longest_free(major_ivs):
                gen = sorted({f"{code} {t}" for c, code, t, _d, _s, _e in rows[sec.id] if c == "minor"})
                gen_h = round(sum(e - s for c, _code, _t, _d, s, e in rows[sec.id] if c == "minor") / 60, 1)
                blocked.append({"section": f"{sec.program.name} {sec.name}", "department": sec.program.department, "semester": sem,
                                "subject": f"{sub.code} {sub.title}", "needs_block_hours": round(blk / 60, 1),
                                "gen_ed_hours_in_section": gen_h, "gen_ed_classes": gen})
    waiting = []
    for g in SharedClassGroup.objects.filter(confirmed=False).prefetch_related("programs").select_related("created_by").order_by("semester", "code"):
        waiting.append({"id": g.id, "code": g.code, "title": g.title, "year_level": g.year_level, "semester": g.semester,
                        "programs": sorted(p.name for p in g.programs.all()), "departments": sorted({p.department for p in g.programs.all()}),
                        "requested_by": _name(g.created_by) if g.created_by else "", "requested_at": g.created_at.isoformat()})
    return {"blocked_by_gen_ed": blocked, "shared_groups_waiting": waiting,
            "note": "Blocked = with the section's Gen Ed classes there is no free window as long as the major's longest block; without "
                    "them there would be. Teachers, rooms and availability can still matter: this only isolates the Gen Ed effect. "
                    "Confirm waiting shared classes in Generate > Shared Class / Programs."}


def capacity_vs_enrollment(semester=None, departments=None, program_id=None, school_year=None):
    """Every class (a shared class once, with all its sections' students) against its room's seats:
    over capacity (more students than seats) and under 50% full."""
    from engine.models import Schedule

    qs = _sy(Schedule.objects.select_related("room", "section__program", "subject"), school_year)
    if departments is not None:
        qs = qs.filter(section__program__department__in=departments)
    if program_id:
        qs = qs.filter(section__program_id=program_id)
    sem = _pick_semester(qs, semester)
    if sem:
        qs = qs.filter(section__semester=sem)
    classes = {}
    for r in qs:
        k = _class_key(r.section_id, r.subject_id, r.merge_key) + (r.room_id,)
        c = classes.setdefault(k, {"subject": f"{r.subject.code} {r.subject.title}", "kind": "Gen Ed" if r.subject.classification == "minor" else "Major",
                                   "room": r.room.name, "seats": r.room.capacity or 0, "sections": {}, "shared": bool(r.merge_key)})
        c["sections"][r.section_id] = (f"{r.section.program.name} {r.section.name}", r.section.student_count or 0)
    over, under, unknown = [], [], 0
    for c in classes.values():
        students = sum(n for _l, n in c["sections"].values())
        item = {"subject": c["subject"], "kind": c["kind"], "room": c["room"], "seats": c["seats"], "students": students,
                "sections": sorted(l for l, _n in c["sections"].values()), "shared": c["shared"],
                "fill_pct": round(students / c["seats"] * 100) if c["seats"] else None}
        if not c["seats"]:
            unknown += 1
        elif students > c["seats"]:
            over.append(item)
        elif students < c["seats"] * 0.5:
            under.append(item)
    over.sort(key=lambda x: -(x["students"] - x["seats"]))
    under.sort(key=lambda x: x["fill_pct"])
    return {"semester": sem, "classes": len(classes), "over_capacity": over, "under_half": under, "rooms_without_capacity": unknown,
            "note": "Students = the section's recorded student count (a shared class adds up every section). Classes in a room with no "
                    "recorded capacity are counted separately."}


# ============================================================================================= Stage 4: SHS / JHS principals
def _section_subjects(section, subjects):
    """The subjects that apply to one Basic Ed section: the same selection the curriculum validator uses (a strand's own line wins
    over the common one with the same code)."""
    mine = {}
    for s in subjects:
        if s.strand_id in (None, section.strand_id):
            if s.code not in mine or (s.strand_id and not mine[s.code].strand_id):
                mine[s.code] = s
    return mine


def basic_ed_feasibility(level, academic_year, period=None):
    """Per grade level: how many class periods fit in the school day after the break(s) (the engine's own build_grid / window_breaks),
    the weekly capacity (Mon-Fri), and the most periods any section of that grade needs for the chosen grading period."""
    from basic_ed import models as bm
    from basic_ed.analytics import choose_period
    from basic_ed.engine import build_grid, window_breaks, to_min
    from basic_ed.structure import structure

    cfg = bm.SchoolLevelConfig.objects.filter(level=level).first()
    if cfg is None:
        return {"level": level, "configured": False, "grades": [], "period": None,
                "note": f"The {level} school level is not set up yet."}
    period, _have = choose_period(level, academic_year, period)
    days = len(bm.DAYS)
    out = []
    for w in bm.GradeWindow.objects.filter(level=level).order_by("grade_level"):
        grid = build_grid(cfg, w)
        breaks = window_breaks(w)
        day_min = to_min(w.end_time) - to_min(w.start_time)
        break_min = sum(b - a for _l, a, b in breaks)
        taught = len(grid) * cfg.period_minutes
        needed_breaks = ("Break",) if level == "SHS" else ("Recess", "Lunch")
        missing = [n for n in needed_breaks if n not in {l for l, _a, _b in breaks}]
        _kind, count = structure(level, w.grade_level)
        subs = list(bm.CurriculumSubject.objects.filter(level=level, academic_year=academic_year, grade_level=w.grade_level, is_active=True,
                                                        grading_period__in=[0, period]))
        demand = []
        for sec in bm.Section.objects.filter(level=level, academic_year=academic_year, grade_level=w.grade_level, is_active=True).select_related("strand"):
            demand.append((sum(s.sessions_per_week for s in _section_subjects(sec, subs).values()), sec.name))
        worst = max(demand, default=(0, ""))
        cap = len(grid) * days
        out.append({
            "grade": w.grade_level, "start": w.start_time.strftime("%H:%M"), "end": w.end_time.strftime("%H:%M"),
            "day_minutes": day_min, "breaks": [{"name": l, "start": f"{a // 60:02d}:{a % 60:02d}", "end": f"{b // 60:02d}:{b % 60:02d}"} for l, a, b in breaks],
            "break_minutes": break_min, "missing_breaks": missing, "period_minutes": cfg.period_minutes,
            "periods_per_day": len(grid), "unused_minutes": max(day_min - break_min - taught, 0),
            "periods_per_week": cap, "sections": len(demand), "max_needed_per_week": worst[0], "max_needed_section": worst[1],
            "fits": worst[0] <= cap, "period_in_structure": period <= count,
        })
    return {"level": level, "configured": True, "period": period, "grades": out,
            "note": f"Periods are {cfg.period_minutes} minutes, Monday to Friday. A period never overlaps a break. "
                    "Unused = minutes of the day left over because a whole period does not fit there."}


def basic_ed_completeness(level, academic_year, period=None):
    """Per grade level and strand: sections, subjects required, subjects with no qualified teacher (the engine's eligible() rule),
    and -- from the latest timetables -- subjects not fully scheduled and periods with no teacher."""
    from basic_ed import models as bm
    from basic_ed.analytics import choose_period, latest_runs
    from basic_ed.engine import eligible

    period, have = choose_period(level, academic_year, period)
    faculty = list(bm.Faculty.objects.filter(level=level, is_active=True))
    runs = latest_runs(level, academic_year, period)
    sched = defaultdict(int)                  # (section_id, code) -> periods in the timetable
    no_teacher = defaultdict(int)
    for sec_id, code, teacher_id in bm.ScheduleEntry.objects.filter(run__in=runs).values_list("section_id", "subject_code", "teacher_id"):
        sched[(sec_id, code)] += 1
        if teacher_id is None:
            no_teacher[(sec_id, code)] += 1
    timetabled_grades = set(bm.ScheduleEntry.objects.filter(run__in=runs).values_list("section__grade_level", flat=True).distinct())
    groups = {}
    for sec in bm.Section.objects.filter(level=level, academic_year=academic_year, is_active=True).select_related("strand").order_by("grade_level", "name"):
        subs = list(bm.CurriculumSubject.objects.filter(level=level, academic_year=academic_year, grade_level=sec.grade_level, is_active=True,
                                                        grading_period__in=[0, period]))
        mine = _section_subjects(sec, subs)
        key = (sec.grade_level, sec.strand.code if sec.strand_id else "")
        g = groups.setdefault(key, {"grade": key[0], "strand": key[1], "sections": [], "subjects": set(), "no_teacher_subjects": set(),
                                    "not_scheduled": [], "periods_without_teacher": 0, "timetabled": key[0] in timetabled_grades})
        g["sections"].append(sec.name)
        for code, s in mine.items():
            g["subjects"].add(code)
            if not any(eligible(f, s) for f in faculty):
                g["no_teacher_subjects"].add(f"{code} {s.name} (needs '{s.specialization or s.learning_area}')")
            if g["timetabled"]:
                got = sched.get((sec.id, code), 0)
                if got < s.sessions_per_week:
                    g["not_scheduled"].append({"section": sec.name, "subject": f"{code} {s.name}", "scheduled": got, "needed": s.sessions_per_week})
                g["periods_without_teacher"] += no_teacher.get((sec.id, code), 0)
        if not mine:
            g["not_scheduled"].append({"section": sec.name, "subject": "(no subjects in the curriculum for this period)", "scheduled": 0, "needed": 0})
    out = []
    for g in groups.values():
        out.append({"grade": g["grade"], "strand": g["strand"], "sections": g["sections"], "subjects": len(g["subjects"]),
                    "no_teacher_subjects": sorted(g["no_teacher_subjects"]), "timetabled": g["timetabled"],
                    "not_scheduled": g["not_scheduled"], "periods_without_teacher": g["periods_without_teacher"],
                    "complete": not g["no_teacher_subjects"] and not g["not_scheduled"] and not g["periods_without_teacher"] and g["timetabled"]})
    return {"level": level, "period": period, "periods_with_timetables": have, "groups": out,
            "note": "Not scheduled = fewer periods in the latest timetable than the subject's sessions per week. Grades without a "
                    "timetable for this period show only the curriculum and teacher checks."}


def basic_ed_absences(level):
    """Absence impact. SHS / JHS teachers have no absence records in the system (the faculty Absence model covers college faculty
    only), so nothing can be computed. Reported honestly instead of showing zero."""
    return {"level": level, "recorded": False, "uncovered_classes": None,
            "note": "SHS / JHS teacher absences are not recorded anywhere in U-FAST (the Absence records belong to college faculty), "
                    "so classes left uncovered cannot be counted. Recording them would need a new Basic Ed absence table (a migration)."}


# ============================================================================================= Stage 5: filters and trend
def filter_options(departments=None):
    """Choices for the filter bar, limited to what this user may see: school years and semesters that have classes, colleges, programs."""
    from curriculum.models import Program
    from engine.models import Schedule, Section

    progs = Program.objects.all().order_by("name")
    secs = Section.objects.all()
    sched = Schedule.objects.all()
    if departments is not None:
        progs = progs.filter(department__in=departments)
        secs = secs.filter(program__department__in=departments)
        sched = sched.filter(section__program__department__in=departments)
    return {"school_years": sorted({y for y in sched.values_list("school_year", flat=True).distinct() if y}, reverse=True),
            "semesters": sorted({s for s in secs.values_list("semester", flat=True).distinct() if s}),
            "departments": sorted({p.department for p in progs if p.department}),
            "programs": [{"id": p.id, "name": p.name, "department": p.department} for p in progs]}


def basic_ed_run_trend(level, academic_year):
    """Every stored Basic Ed generation run (ScheduleRun keeps every version, replaced ones included) in time order, per grade and
    grading period: periods placed, periods that could not be placed, efficiency = placed / (placed + unresolved), and conflicts
    (validation errors). Runs created before these counts were stored are listed with blank numbers instead of zeros."""
    from basic_ed import models as bm

    out = []
    for r in bm.ScheduleRun.objects.filter(level=level, academic_year=academic_year).select_related("created_by").order_by("created_at"):
        st, va = r.stats or {}, r.validation or {}
        placed, unres = st.get("placed"), st.get("unresolved")
        eff = round(placed / (placed + unres) * 100, 1) if isinstance(placed, int) and isinstance(unres, int) and (placed + unres) else None
        out.append({"id": r.id, "when": r.created_at.isoformat(), "grade": r.grade_level, "period": r.grading_period, "version": r.version,
                    "status": r.status, "by": _name(r.created_by) if r.created_by else "", "placed": placed, "unresolved": unres,
                    "efficiency_pct": eff, "conflicts": va.get("errors"), "warnings": va.get("warnings"), "sections": st.get("sections")})
    return {"level": level, "academic_year": academic_year.label if academic_year else "", "runs": out,
            "years": list(bm.AcademicYear.objects.order_by("-label").values_list("label", flat=True))}
