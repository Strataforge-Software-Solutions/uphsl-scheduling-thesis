from engine.models import Schedule
from django.contrib.auth import get_user_model
from django.db.models import Count


def _time_bucket(t):
    if t.hour < 12:
        return "Morning"
    if t.hour < 17:
        return "Afternoon"
    return "Evening"


def _dept_list(department):
    """None -> None (everything); 'X' -> ['X']; a list stays a list."""
    if not department:
        return None
    return [department] if isinstance(department, str) else list(department)


def _hours(slot):
    """Length of a TimeSlot in hours (a 30-minute slot counts 0.5)."""
    return ((slot.end_time.hour * 60 + slot.end_time.minute)
            - (slot.start_time.hour * 60 + slot.start_time.minute)) / 60.0


def compute_faculty_patterns(faculty_id):
    """Mines recurring day/time-of-day patterns for one faculty from their
    imported historical class records (2021-2026) -- e.g. "this faculty has
    historically taught Mon/Wed mornings" -- so the Dean/Registrar can see it
    when reviewing that faculty's current Availability submission. See the
    Availability model's docstring: this is the "ML groundwork" it refers to.

    Returns patterns ranked by frequency; an empty list just means no
    historical records matched to this faculty (e.g. a newly hired teacher)."""
    from analytics.models import HistoricalClassRecord

    qs = HistoricalClassRecord.objects.filter(teacher_id=faculty_id)
    counts = {}
    semesters_seen = set()
    for rec in qs:
        key = (rec.day, _time_bucket(rec.start_time))
        counts[key] = counts.get(key, 0) + 1
        semesters_seen.add((rec.school_year, rec.semester))

    total = sum(counts.values())
    patterns = [
        {"day": day, "time_of_day": bucket, "count": count,
         "share_pct": round(count / total * 100, 1) if total else 0}
        for (day, bucket), count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    return {
        "faculty_id": faculty_id,
        "semesters_covered": len(semesters_seen),
        "total_historical_meetings": total,
        "patterns": patterns,
    }


def compute_analytics(department=None, semester=None):
    """Weekly figures for ONE semester (1st and 2nd Sem reuse the same rooms and teachers, so adding
    them together would double every hour). semester=None picks the semester that has the most classes."""
    department = _dept_list(department)
    qs = Schedule.objects.all()
    if department:
        qs = qs.filter(section__program__department__in=department)
    counts = {
        row["section__semester"]: row["count"]
        for row in qs.values("section__semester").annotate(count=Count("id"))
    }
    semesters = sorted(counts)
    if semester not in counts:
        semester = max(counts, key=lambda k: (counts[k], k == "1st Sem")) if counts else None
    if semester:
        qs = qs.filter(section__semester=semester)

    # ONE query for everything (it used to run ~1 query per schedule row plus two full
    # passes -- over a remote database that took long enough to time out).
    rows = qs.values_list(
        "room_id", "room__name", "teacher_id", "teacher__user__username", "timeslot_id",
        "timeslot__day", "timeslot__start_time", "timeslot__end_time", "status",
    )
    day_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hours_by_day, status_counts = {d: 0 for d in day_order}, {"draft": 0, "approved": 0, "published": 0}
    room_utilization, teacher_workload = {}, {}
    seen_room, seen_teacher = set(), set()      # a shared (merged) class counts once, not once per section
    total = filled = 0
    for room_id, room_name, teacher_id, username, slot_id, day, start, end, status in rows:
        hrs = ((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)) / 60.0
        total += 1
        if teacher_id is not None and room_id is not None:
            filled += 1
        if room_id is not None and (room_id, slot_id) not in seen_room:
            seen_room.add((room_id, slot_id))
            room_utilization[room_name] = room_utilization.get(room_name, 0) + hrs
        if teacher_id is not None and (teacher_id, slot_id) not in seen_teacher:
            seen_teacher.add((teacher_id, slot_id))
            teacher_workload[username] = teacher_workload.get(username, 0) + hrs
        code = (day or "")[:3].title()
        if code in hours_by_day:
            hours_by_day[code] += hrs
        status_counts[status] = status_counts.get(status, 0) + 1

    efficiency = round((filled / total) * 100, 2) if total else 0
    if department:
        # A Dean's Teacher Workload lists the Dean's OWN faculty only (teachers whose department is one of the Dean's), and counts
        # each one's TOTAL weekly hours in the semester -- including classes they teach in other colleges (Gen Ed, minors) -- so an
        # overload is not hidden. Teachers of other departments who teach this college's classes are left out of the response
        # entirely. A shared (merged) class still counts once (same seen-teacher rule as above). Rooms, efficiency, hours by day and
        # recent activity above stay based on this college's classes.
        teacher_workload = _own_faculty_workload(department, semester)
    usernames = list(teacher_workload)
    user_model = get_user_model()
    teacher_names = {
        user.username: (user.get_full_name().strip() or user.username)
        for user in user_model.objects.filter(username__in=usernames).only("username", "first_name", "last_name")
    }
    loads = list(teacher_workload.values())
    workload_std_dev = _std_dev(loads) if loads else 0

    return {
        "room_utilization": room_utilization,
        "teacher_workload": teacher_workload,
        "teacher_names": teacher_names,
        "schedule_efficiency": efficiency,
        "workload_std_dev": workload_std_dev,
        "class_hours_by_day": {d: n for d, n in hours_by_day.items() if n or d != "Sun"},
        "schedule_status": status_counts,
        "recent_activity": compute_recent_activity(department=department),
        "semester": semester,
        "semesters": semesters,
    }


def _own_faculty_workload(departments, semester):
    """{username: weekly hours} for the teachers whose User.department is one of `departments`, over EVERY class they teach in
    `semester` (any college). When the college has no classes at all (no semester was picked), the semester in which these teachers
    have the most classes is used, so 1st and 2nd Sem are never added together."""
    qs = Schedule.objects.filter(teacher__user__department__in=departments)
    if not semester:
        counts = {}
        for sem in qs.values_list("section__semester", flat=True):
            counts[sem] = counts.get(sem, 0) + 1
        semester = max(counts, key=lambda k: (counts[k], k == "1st Sem")) if counts else None
    if semester:
        qs = qs.filter(section__semester=semester)
    workload, seen = {}, set()
    for teacher_id, username, slot_id, start, end in qs.values_list(
            "teacher_id", "teacher__user__username", "timeslot_id", "timeslot__start_time", "timeslot__end_time"):
        if (teacher_id, slot_id) in seen:          # a shared (merged) class counts once
            continue
        seen.add((teacher_id, slot_id))
        hrs = ((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)) / 60.0
        workload[username] = workload.get(username, 0) + hrs
    return workload


def compute_recent_activity(department=None, limit=15):
    department = _dept_list(department)
    """Newest events first: schedules generated, approvals, exam schedules
    generated, and new conflicts. Rows created in one action (the same minute,
    by the same person, for the same class group) are collapsed into one line."""
    from collections import OrderedDict
    from engine.models import ConflictLog
    from exams.models import ExamSchedule

    events = []

    sched = Schedule.objects.select_related("section__program", "approved_by").only(
        "generated_at", "section__year_level", "section__semester", "section__program__name",
        "approved_at", "approved_by_id", "approved_by__first_name", "approved_by__last_name",
        "approved_by__username", "status",
    ).order_by("-generated_at")
    if department:
        sched = sched.filter(section__program__department__in=department)
    groups = OrderedDict()
    for r in sched[:600]:
        sec = r.section
        key = (r.generated_at.replace(second=0, microsecond=0), sec.program.name, sec.year_level, sec.semester)
        groups.setdefault(key, 0)
        groups[key] += 1
    for (when, program, year, sem), n in groups.items():
        events.append({"type": "generated", "when": when,
                       "text": f"Class schedule generated for {program} {year} {sem} ({n} class hours)"})

    appr = sched.filter(approved_at__isnull=False).order_by("-approved_at")
    groups = OrderedDict()
    for r in appr[:600]:
        who = r.approved_by.get_full_name() or r.approved_by.username if r.approved_by else "Someone"
        key = (r.approved_at.replace(second=0, microsecond=0), who, r.status)
        groups.setdefault(key, 0)
        groups[key] += 1
    for (when, who, status), n in groups.items():
        verb = "published" if status == "published" else "approved"
        events.append({"type": "approved", "when": when, "text": f"{who} {verb} {n} class hours"})

    ex = ExamSchedule.objects.select_related("created_by", "section__program").order_by("-created_at")
    if department:
        ex = ex.filter(section__program__department__in=department)
    groups = OrderedDict()
    for e in ex[:600]:
        who = (e.created_by.get_full_name() or e.created_by.username) if e.created_by else "Someone"
        key = (e.created_at.replace(second=0, microsecond=0), who, e.exam_period)
        groups.setdefault(key, 0)
        groups[key] += 1
    for (when, who, period), n in groups.items():
        events.append({"type": "exam", "when": when, "text": f"{who} generated {n} {period} exam entries"})

    cl = ConflictLog.objects.exclude(description__startswith="[Historical import]").order_by("-occurred_at")
    for c in cl[:20]:
        events.append({"type": "conflict", "when": c.occurred_at, "text": c.description[:140]})

    events.sort(key=lambda e: e["when"], reverse=True)
    return [{**e, "when": e["when"].isoformat()} for e in events[:limit]]


def _std_dev(values):
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return round(variance ** 0.5, 2)


def historical_subjects_at(day, start_time, end_time=None, room_name=None, limit=10):
    """
    "What subject was historically taught/examined at this day+time?" --
    looked up from the imported 2021-2026 HistoricalClassRecord data, so the
    Registrar/Dean has a real reference instead of guessing when manually
    placing a class or an exam into a day/time slot.

    day: "Mon".."Sat". start_time/end_time: "HH:MM" strings or time objects --
    rows are matched on ANY overlap with [start_time, end_time), not an exact
    match, since historical period boundaries don't line up 1-to-1 with the
    current system's TimeSlot grid. room_name is matched case-insensitively
    and is optional (room_name is free text in the historical data, not a FK).
    """
    from analytics.models import HistoricalClassRecord

    qs = HistoricalClassRecord.objects.filter(day=day).select_related("teacher__user")
    if room_name:
        qs = qs.filter(room_name__iexact=room_name)

    if end_time:
        # Overlap, not exact match: start_time < end_time AND end_time > start_time.
        qs = qs.filter(start_time__lt=end_time, end_time__gt=start_time)
    else:
        qs = qs.filter(start_time__lte=start_time, end_time__gt=start_time)

    results = []
    for rec in qs.order_by("-school_year", "-semester")[:limit]:
        results.append({
            "subject_code": rec.subject_code,
            "description": rec.description,
            "section_label": rec.section_label,
            "room_name": rec.room_name,
            "teacher_name": rec.teacher.user.get_full_name() or rec.teacher.user.username if rec.teacher_id else (rec.teacher_name_raw or None),
            "day": rec.day,
            "start_time": str(rec.start_time),
            "end_time": str(rec.end_time),
            "school_year": rec.school_year,
            "semester": rec.semester,
        })
    return results
