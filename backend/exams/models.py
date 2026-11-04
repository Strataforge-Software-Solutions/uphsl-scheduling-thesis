from django.conf import settings
from django.db import models


class ExamSchedule(models.Model):
    """
    Separate from the regular class Schedule model on purpose — exam-specific
    fields (proctor, exam period, duration) don't belong on regular class rows.
    Conflict-freedom across THIS model and the regular Schedule model is
    enforced by engine.conflicts, not by a UniqueConstraint here alone.
    """
    EXAM_PERIODS = [("prelim", "Prelim"), ("midterm", "Midterm"), ("final", "Final")]

    subject = models.ForeignKey("curriculum.Subject", on_delete=models.CASCADE)
    section = models.ForeignKey("engine.Section", on_delete=models.CASCADE)
    proctor = models.ForeignKey("faculty.FacultyProfile", on_delete=models.CASCADE)
    room = models.ForeignKey("rooms.Room", on_delete=models.CASCADE)
    timeslot = models.ForeignKey("engine.TimeSlot", on_delete=models.CASCADE)
    exam_date = models.DateField(
        null=True, blank=True,
        help_text="Actual calendar date of the exam (e.g. 2026-03-15). TimeSlot only stores "
                   "a recurring weekday, not a real date -- this field is what historical "
                   "exam records from IT need to import into.",
    )
    exam_period = models.CharField(max_length=10, choices=EXAM_PERIODS)
    duration_minutes = models.PositiveSmallIntegerField(default=120)

    # --- ML groundwork: track whether the auto-generated slot was kept or overridden ---
    is_manual_override = models.BooleanField(default=False)
    school_year = models.CharField(max_length=20, blank=True)  # e.g. "2026-2027"

    # Low-enrollment sections of the SAME program and year level that sit one subject's exam together in one room, one hour, one
    # proctor share a merge_key (same idea as Schedule.merge_key for shared classes); "" = an ordinary single-section exam.
    merge_key = models.CharField(max_length=80, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Table-local guard (fast, DB-level) — the cross-table guarantee still
        # comes from engine.conflicts, called in the serializer before save.
        # IMPORTANT: includes exam_date, not just timeslot -- timeslot only
        # stores a recurring weekday+time (e.g. "Mon 2:00-3:00"), so without
        # exam_date, two real exams on the same weekday+time but different
        # actual calendar dates (e.g. Sept 8 2025 vs Feb 16 2026, both Mondays)
        # would incorrectly be treated as the same slot and collide.
        constraints = [
            models.UniqueConstraint(fields=["proctor", "timeslot", "exam_date"], condition=models.Q(merge_key=""),
                                    name="no_proctor_double_booking_exam"),
            models.UniqueConstraint(fields=["room", "timeslot", "exam_date"], condition=models.Q(merge_key=""),
                                    name="no_room_double_booking_exam"),
            models.UniqueConstraint(fields=["section", "timeslot", "exam_date"], name="no_section_double_booking_exam"),
        ]

    @property
    def owner_role_required(self):
        """'registrar' for minor subjects, 'dean' (faculty_type) for majors."""
        return "registrar" if self.subject.classification == "minor" else "dean"

    def __str__(self):
        return f"{self.subject.code} {self.exam_period} exam | {self.section} | {self.timeslot}"
