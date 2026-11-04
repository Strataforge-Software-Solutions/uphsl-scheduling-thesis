from django.conf import settings
from django.db import models


class FacultyProfile(models.Model):
    """Extends accounts.User for role == 'faculty' with teaching-specific data."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="faculty_profile")
    # Points at AcademicField (a discipline like "Computer Science" or
    # "Mathematics"), NOT at individual Subject rows -- a faculty's
    # specialization is their field of expertise, not a hand-picked list of
    # course codes. The scheduling engine matches a Subject to a qualified
    # teacher via Subject.field, not via a direct subject-to-teacher link.
    specializations = models.ManyToManyField("curriculum.AcademicField", blank=True, related_name="qualified_faculty")
    target_load_hours = models.PositiveSmallIntegerField(default=18)
    # Qualifications used to recommend replacements: highest degree(s) and licences / certifications / trainings.
    degree = models.CharField(max_length=255, blank=True, default="")
    qualifications = models.TextField(blank=True, default="")

    def __str__(self):
        return f"FacultyProfile({self.user.username})"


class Availability(models.Model):
    """Submitted mainly by part-time faculty via FacultyPortal; reviewed by Dean/Registrar.
    Rows accumulate across semesters (not overwritten) so historical patterns
    -- e.g. "this faculty always requests Mon/Wed mornings" -- become visible
    once enough semesters' worth of data exists (ML groundwork)."""
    PREFERENCE_CHOICES = [
        ("preferred", "Preferred"),
        ("available", "Available"),
        ("unavailable", "Unavailable"),
    ]

    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="availability_slots")
    day = models.CharField(max_length=10)          # e.g. "Monday"
    start_time = models.TimeField()
    end_time = models.TimeField()
    # How strongly the faculty wants this block -- "preferred" is a block
    # they'd like to be scheduled in, "available" is a block that merely
    # works for them, "unavailable" lets them explicitly rule out a window
    # instead of just omitting it (clearer than silence for the Registrar
    # reviewing submissions).
    preference = models.CharField(max_length=12, choices=PREFERENCE_CHOICES, default="preferred")
    school_year = models.CharField(max_length=20, blank=True)  # e.g. "2026-2027"
    semester = models.CharField(max_length=20, blank=True)     # e.g. "1st Sem"
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)  # False once a newer semester's submission supersedes it

    def __str__(self):
        return f"{self.faculty.user.username}: {self.day} {self.start_time}-{self.end_time} ({self.preference})"


class Absence(models.Model):
    """Tracks a faculty member being unavailable on a specific date -- distinct from
    Availability (recurring weekly preference). Needed to import historical absence
    records from IT (2021-2026), and going forward for substitute-finding."""
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("denied", "Denied")]

    # Coverage recommendation -- Dean Villanueva's interview explicitly asks that
    # "kung nawalan ang faculty... dapat able ang system to recommend" a stand-in.
    # These fields let Dean/Registrar run find_substitute() for this absence's
    # affected classes and record what was suggested / what actually happened,
    # without implying dedicated "substitute professor" posts exist -- it's a
    # same-department coverage suggestion drawn from current faculty, nothing more.
    COVERAGE_CHOICES = [
        ("none", "No suggestion yet"),
        ("suggested", "Suggested"),
        ("applied", "Applied to schedule"),
        ("declined", "Declined"),
    ]

    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="absences")
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    school_year = models.CharField(max_length=20, blank=True)
    semester = models.CharField(max_length=20, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    coverage_status = models.CharField(max_length=10, choices=COVERAGE_CHOICES, default="none")

    def __str__(self):
        return f"{self.faculty.user.username} absent {self.date} ({self.status})"


class CoverageSuggestion(models.Model):
    """One row per affected class period for a given Absence -- e.g. if a faculty
    is absent on a Monday and teaches 3 classes that day, this holds 3 rows, one
    suggested covering faculty each (or none, if no one qualifies/is free)."""
    absence = models.ForeignKey(Absence, on_delete=models.CASCADE, related_name="coverage_suggestions")
    schedule = models.ForeignKey("engine.Schedule", on_delete=models.CASCADE, related_name="coverage_suggestions")
    suggested_faculty = models.ForeignKey(
        FacultyProfile, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="coverage_suggested_for",
    )
    reason = models.CharField(max_length=255, blank=True)  # e.g. "same specialization, lowest current load"
    applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        who = self.suggested_faculty.user.username if self.suggested_faculty else "No one available"
        return f"Coverage for {self.schedule} -> {who}"


class WorkloadRecord(models.Model):
    """One row per faculty per semester -- total assigned hours and whether that
    exceeded their target load. Computed going forward from Schedule; also the
    landing table for historical overload data requested from IT (2021-2026),
    since raw Schedule history for those years won't exist in this system."""
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="workload_records")
    school_year = models.CharField(max_length=20)   # e.g. "2023-2024"
    semester = models.CharField(max_length=20)       # e.g. "1st Sem"
    total_hours = models.DecimalField(max_digits=5, decimal_places=2)
    is_overload = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("faculty", "school_year", "semester")

    def save(self, *args, **kwargs):
        if self.total_hours and self.faculty_id:
            self.is_overload = float(self.total_hours) > self.faculty.target_load_hours
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.faculty.user.username} {self.school_year} {self.semester}: {self.total_hours}h"
