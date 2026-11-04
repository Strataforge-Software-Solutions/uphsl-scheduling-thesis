from django.db import models


class HistoricalClassRecord(models.Model):
    """One row per (class, specific weekly meeting day) imported from IT's
    2021-2026 class-program spreadsheets (GTI_class_prog.xlsx). A class that
    meets twice a week (e.g. Mon + Wed) produces two rows here, one per day,
    matching how the scheduling engine's TimeSlot model represents a single
    day+time -- the source spreadsheet records both meetings as one data row
    plus a "continuation" row underneath holding only the 2nd day/time.

    This is intentionally a flat, denormalized import table -- not wired into
    live Schedule/Section/Subject FKs -- because 5 years of manually-typed
    spreadsheet data has free-text subject descriptions, inconsistent section
    labels, and teacher names that don't reliably match current FacultyProfile
    records (staff who've left, name-spelling drift, etc.). `teacher` is a
    best-effort FK match done at import time; `teacher_name_raw` always holds
    the literal spreadsheet text so nothing is silently lost or guessed.

    Feeds three things (see analytics/services.py):
      - WorkloadRecord backfill (faculty/models.py) -- historical overload data
      - Faculty availability pattern mining -- "this faculty has historically
        taught Mon/Wed mornings"
      - ConflictLog backfill (engine/models.py) -- historical teacher
        double-bookings, as its own docstring already anticipated.
    """

    DAY_CHOICES = [("Mon", "Monday"), ("Tue", "Tuesday"), ("Wed", "Wednesday"),
                    ("Thu", "Thursday"), ("Fri", "Friday"), ("Sat", "Saturday")]

    school_year = models.CharField(max_length=20)    # e.g. "2026-2027"
    semester = models.CharField(max_length=20)        # e.g. "1st Sem"
    subject_code = models.CharField(max_length=30)
    description = models.CharField(max_length=200, blank=True)
    section_label = models.CharField(max_length=60, blank=True)
    day = models.CharField(max_length=3, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_name = models.CharField(max_length=60, blank=True)
    # TextField, not CharField(max_length=...) -- some rows list several
    # co-teachers/proctors in one cell as a long comma-separated string (seen
    # up to ~470 characters in the real 2021-2026 data), which blew past an
    # earlier 150-char cap and crashed the import with a Postgres
    # "value too long for type character varying(150)" error.
    teacher_name_raw = models.TextField(blank=True)
    teacher = models.ForeignKey(
        "faculty.FacultyProfile", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="historical_records",
        help_text="Best-effort match to a current FacultyProfile by name. Null "
                   "when no confident single match was found (e.g. staff who's "
                   "left, or an ambiguous/duplicate name) -- teacher_name_raw "
                   "always has the original text regardless.",
    )
    units = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    student_count = models.PositiveSmallIntegerField(null=True, blank=True)
    source_row = models.PositiveIntegerField(help_text="Row number in the source sheet, for traceability.")

    class Meta:
        indexes = [
            models.Index(fields=["school_year", "semester"]),
            models.Index(fields=["teacher", "day"]),
        ]

    def __str__(self):
        return f"{self.subject_code} {self.day} {self.start_time}-{self.end_time} ({self.school_year} {self.semester})"
