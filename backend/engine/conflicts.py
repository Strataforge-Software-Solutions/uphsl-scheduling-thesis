"""
Shared conflict-checking layer.

Any model that assigns (teacher/proctor, room, section, timeslot) — regular
class Schedule, ExamSchedule, and anything added later (makeup classes,
seminars, etc.) — should call these functions instead of relying on its own
UniqueConstraint alone. UniqueConstraint only protects a single table; these
functions check ACROSS all schedule-like tables, which is what actually
prevents a Dean's major-exam slot from silently colliding with a Registrar's
minor-exam slot (or a regular class) in a different table.

To register a new schedule-like model here, add it to SCHEDULE_LIKE_MODELS
with the field names it uses for teacher/room/section/timeslot.

--- Real time-range overlap, not just identical-TimeSlot-id matching ---
Originally this only flagged a conflict when two rows pointed at the exact
same TimeSlot row. That missed the case Dean Villanueva described: two
different TimeSlot rows (e.g. 9:00-10:30 and 10:00-11:30) that partially
overlap on the same day. We now compare actual start/end times on the same
day. For TEACHER and ROOM, any overlap at all is a hard conflict (one person
or one room cannot be in two places). For SECTION (i.e. the student-facing
conflict), Dean Villanueva's interview says she deliberately allows up to a
configurable grace window (default 30 minutes, see SchedulingConfig) because
the college has limited course offerings -- so a section overlap only counts
as a conflict once it exceeds that tolerance.
"""
from django.apps import apps


def _get_schedule_like_querysets(exclude_model=None, exclude_pk=None):
    """
    Returns [(queryset, field_map, date_field), ...] for every registered
    schedule-like model, so callers can check a candidate assignment against
    all of them. field_map maps the logical role ("teacher", "room",
    "section", "timeslot") to that model's actual field name. "date_field"
    (optional) names the field holding a real calendar date, e.g.
    ExamSchedule.exam_date -- used to avoid treating two exams on the same
    weekday+time but different actual dates as a conflict (regular Schedule
    has no date_field since it recurs every week, so it always conflicts
    with any exam at that weekday+time, regardless of date).
    """
    registry = [
        ("engine", "Schedule", {"teacher": "teacher", "room": "room", "section": "section", "timeslot": "timeslot"}, None),
        ("exams", "ExamSchedule", {"teacher": "proctor", "room": "room", "section": "section", "timeslot": "timeslot"}, "exam_date"),
    ]
    results = []
    for app_label, model_name, field_map, date_field in registry:
        model = apps.get_model(app_label, model_name)
        qs = model.objects.select_related("timeslot").all()
        if exclude_model == model_name and exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        results.append((qs, field_map, date_field))
    return results


def model_has_merge_key(qs):
    return any(f.name == "merge_key" for f in qs.model._meta.get_fields())


def _overlap_minutes(a_start, a_end, b_start, b_end):
    """Minutes of overlap between two time ranges on the same day. 0 (or
    negative, clamped to 0) if they don't overlap at all.

    Accepts either datetime.time objects or "HH:MM"/"HH:MM:SS" strings --
    a TimeSlot built in-memory via .objects.create(start_time="08:50", ...)
    (e.g. TimeSlotViewSet.get_or_create) keeps the raw string until it's
    reloaded from the DB, since Django doesn't coerce field values on plain
    attribute assignment. Normalizing here avoids a TypeError the moment a
    freshly-created TimeSlot is checked for conflicts before any refetch."""
    from datetime import date, datetime, time as time_cls

    def to_time(t):
        if isinstance(t, time_cls):
            return t
        parts = [int(p) for p in str(t).split(":")]
        while len(parts) < 3:
            parts.append(0)
        return time_cls(*parts[:3])

    def to_dt(t):
        return datetime.combine(date.min, to_time(t))

    latest_start = max(to_dt(a_start), to_dt(b_start))
    earliest_end = min(to_dt(a_end), to_dt(b_end))
    delta = (earliest_end - latest_start).total_seconds() / 60
    return max(0, delta)


def _get_tolerance_minutes():
    from .models import SchedulingConfig
    try:
        return SchedulingConfig.get_solo().student_overlap_tolerance_minutes
    except Exception:
        # Migrations not yet run / table missing -- fail safe to the Dean's
        # stated default rather than erroring the whole conflict check.
        return 30


# CLASS schedules: a section's students can never be in two classes at once (0 minutes), exactly like the CSP solver's
# is_consistent(). The configurable grace window (SchedulingConfig.student_overlap_tolerance_minutes) applies to EXAMS only; using it for
# classes let Resolve / edits / the conflict scan accept and hide overlaps the solver itself never allows.
CLASS_STUDENT_OVERLAP_MINUTES = 0


def class_tolerance_minutes():
    return CLASS_STUDENT_OVERLAP_MINUTES


def find_conflicts(*, teacher=None, room=None, section=None, timeslot, exam_date=None, exclude_model=None, exclude_pk=None,
                   merge_key="", semester=None):
    """
    Returns a list of human-readable conflict descriptions for the given
    candidate assignment, checked against EVERY schedule-like table.
    Empty list == no conflicts, safe to assign.

    exam_date: pass this when checking a candidate ExamSchedule row -- if the
    table being checked also has a date field (i.e. it's ExamSchedule too),
    a match only counts as a conflict when the dates are equal. Regular
    Schedule rows have no date field and always conflict at that weekday+time
    regardless of exam_date, since a weekly class recurs every week.
    """
    conflicts = []
    # exams (a real exam_date) keep the configured grace window; weekly classes use the solver's rule (no overlap)
    tolerance = _get_tolerance_minutes() if exam_date is not None else class_tolerance_minutes()

    for qs, field_map, date_field in _get_schedule_like_querysets(exclude_model, exclude_pk):
        if date_field and exam_date is None:
            # This table (ExamSchedule) only books a real one-off calendar
            # date, never a recurring weekday -- but the candidate being
            # checked here is a REGULAR class (no exam_date given), which
            # recurs every week for the whole semester. Exams run during a
            # separate exam period where regular classes don't meet, so a
            # weekday+time match against some unrelated exam's calendar date
            # isn't a real conflict -- it was blocking every ordinary class
            # edit for any teacher who has ever proctored an exam at that
            # weekday+time. Skip this table entirely for a regular-class
            # candidate instead of comparing across incompatible notions of
            # "when" (recurring weekday vs. one specific date).
            continue

        if merge_key and model_has_merge_key(qs):
            # rows of the same merged (shared) class never conflict with each other
            qs = qs.exclude(merge_key=merge_key)
        if semester:        # 1st and 2nd Sem never meet, so only the same semester can clash
            qs = qs.filter(**{f"{field_map['section']}__semester": semester})
        same_day = qs.filter(**{f"{field_map['timeslot']}__day": timeslot.day})

        if date_field and exam_date is not None:
            same_day = same_day.filter(**{date_field: exam_date})

        if teacher is not None:
            for row in same_day.filter(**{field_map["teacher"]: teacher}):
                row_slot = getattr(row, field_map["timeslot"])
                if _overlap_minutes(timeslot.start_time, timeslot.end_time, row_slot.start_time, row_slot.end_time) > 0:
                    conflicts.append(f"Teacher/proctor already booked at an overlapping time ({row._meta.model_name} #{row.pk}).")

        if room is not None:
            for row in same_day.filter(**{field_map["room"]: room}):
                row_slot = getattr(row, field_map["timeslot"])
                if _overlap_minutes(timeslot.start_time, timeslot.end_time, row_slot.start_time, row_slot.end_time) > 0:
                    conflicts.append(f"Room already booked at an overlapping time ({row._meta.model_name} #{row.pk}).")

        if section is not None:
            # Add up the overlap across ALL of the section's rows (a 1.5-hour
            # class is stored as 30-minute rows, so judging row by row would let
            # a 60-minute clash slip under a 30-minute allowance).
            total, first = 0, None
            for row in same_day.filter(**{field_map["section"]: section}):
                row_slot = getattr(row, field_map["timeslot"])
                overlap = _overlap_minutes(timeslot.start_time, timeslot.end_time, row_slot.start_time, row_slot.end_time)
                if overlap > 0:
                    total += overlap
                    first = first or row
            # Grace window: a section/student overlap under the configured
            # tolerance (default 30 min) is allowed, per Dean Villanueva's
            # stated policy for colleges with limited course offerings.
            if first is not None and total > tolerance:
                conflicts.append(
                    f"Section already has an entry overlapping by {int(total)} min"
                    + (f", over the {tolerance}-min allowance" if tolerance else "")
                    + f" ({first._meta.model_name} #{first.pk})."
                )

    return conflicts


def is_slot_free(**kwargs):
    return len(find_conflicts(**kwargs)) == 0
