"""
Derives three things from the imported HistoricalClassRecord rows
(see import_historical_schedule):

  1. WorkloadRecord backfill -- total weekly contact hours per faculty per
     semester, so the Dean's overload dashboard has 2021-2026 history instead
     of only going-forward data.
  2. ConflictLog backfill -- historical teacher double-bookings (same
     teacher, same school_year/semester/day, overlapping times, different
     room), exactly what ConflictLog's own docstring says it's for.
  3. (Availability pattern mining is computed on demand, not persisted --
     see analytics/services.py:compute_faculty_patterns -- since it's just a
     frequency read over HistoricalClassRecord and doesn't need a table.)

Usage:
    python manage.py derive_historical_analytics
Re-running is safe: prior backfilled rows (tagged, see below) are deleted
and recomputed first.
"""
from datetime import datetime, date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction


HISTORICAL_TAG = "[Historical import]"


def _duration_hours(start_t, end_t):
    dt_start = datetime.combine(date.min, start_t)
    dt_end = datetime.combine(date.min, end_t)
    return (dt_end - dt_start).total_seconds() / 3600


class Command(BaseCommand):
    help = "Backfill WorkloadRecord and ConflictLog from imported HistoricalClassRecord data."

    def handle(self, *args, **options):
        from analytics.models import HistoricalClassRecord
        from faculty.models import WorkloadRecord
        from engine.models import ConflictLog

        self._backfill_workload(HistoricalClassRecord, WorkloadRecord)
        self._backfill_conflicts(HistoricalClassRecord, ConflictLog)

    def _backfill_workload(self, HistoricalClassRecord, WorkloadRecord):
        totals = {}  # (teacher_id, school_year, semester) -> hours
        qs = HistoricalClassRecord.objects.filter(teacher__isnull=False).select_related("teacher")
        for rec in qs:
            key = (rec.teacher_id, rec.school_year, rec.semester)
            totals[key] = totals.get(key, 0) + _duration_hours(rec.start_time, rec.end_time)

        created, updated = 0, 0
        with transaction.atomic():
            for (teacher_id, school_year, semester), hours in totals.items():
                obj, was_created = WorkloadRecord.objects.update_or_create(
                    faculty_id=teacher_id, school_year=school_year, semester=semester,
                    defaults={
                        "total_hours": Decimal(str(round(hours, 2))),
                        "notes": f"{HISTORICAL_TAG} backfilled from 2021-2026 class-program records.",
                    },
                )
                created += was_created
                updated += (not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"WorkloadRecord: {created} created, {updated} updated from {len(totals)} faculty/semester combinations."
        ))

    def _backfill_conflicts(self, HistoricalClassRecord, ConflictLog):
        # Clear out any previous backfill so reruns don't duplicate.
        ConflictLog.objects.filter(description__startswith=HISTORICAL_TAG).delete()

        # Group matched-teacher records by (teacher, school_year, semester, day),
        # then pairwise-check for overlapping times in different rooms -- the
        # same "physically can't be in two places" test engine/conflicts.py
        # uses for live schedules, applied here to the historical data.
        qs = (HistoricalClassRecord.objects
              .filter(teacher__isnull=False)
              .select_related("teacher__user")
              .order_by("teacher_id", "school_year", "semester", "day", "start_time"))

        groups = {}
        for rec in qs:
            key = (rec.teacher_id, rec.school_year, rec.semester, rec.day)
            groups.setdefault(key, []).append(rec)

        to_create = []
        seen_pairs = set()
        for key, records in groups.items():
            for i in range(len(records)):
                for j in range(i + 1, len(records)):
                    a, b = records[i], records[j]
                    if a.room_name == b.room_name:
                        continue  # same room -- not a double-booking (combined class)
                    latest_start = max(a.start_time, b.start_time)
                    earliest_end = min(a.end_time, b.end_time)
                    if latest_start >= earliest_end:
                        continue  # no actual overlap
                    pair_key = tuple(sorted([a.id, b.id]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    teacher_name = a.teacher.user.get_full_name() or a.teacher.user.username
                    to_create.append(ConflictLog(
                        conflict_type="teacher_double_booking",
                        description=(
                            f"{HISTORICAL_TAG} {teacher_name} double-booked {a.day} "
                            f"{a.start_time.strftime('%H:%M')}-{a.end_time.strftime('%H:%M')} "
                            f"({a.subject_code} in {a.room_name or 'unknown room'}) vs. "
                            f"{b.start_time.strftime('%H:%M')}-{b.end_time.strftime('%H:%M')} "
                            f"({b.subject_code} in {b.room_name or 'unknown room'})."
                        )[:500],
                        teacher_id=a.teacher_id,
                        school_year=a.school_year,
                        semester=a.semester,
                    ))

        ConflictLog.objects.bulk_create(to_create, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"ConflictLog: {len(to_create)} historical double-bookings recorded."))
