"""
Basic-education (Senior High / Junior High) data.

Everything here is kept in its own tables, tagged with a `level` ("SHS" or "JHS"), and none of it
points at the college tables (curriculum.*, rooms.*, engine.*). Authentication is shared: the same
accounts.User model, with role "principal" / "teacher" and a `school_level`.
"""
from django.conf import settings
from django.db import models

LEVELS = [("SHS", "Senior High School"), ("JHS", "Junior High School")]
DAYS = [("Mon", "Monday"), ("Tue", "Tuesday"), ("Wed", "Wednesday"), ("Thu", "Thursday"), ("Fri", "Friday")]
DAY_ORDER = {d: i for i, (d, _) in enumerate(DAYS)}


class SchoolLevelConfig(models.Model):
    """One row per school level: building, floor and scheduling parameters."""
    level = models.CharField(max_length=3, choices=LEVELS, unique=True)
    name = models.CharField(max_length=60)
    building = models.CharField(max_length=60)
    floor = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Floor reserved for this level (blank = whole building).")
    period_minutes = models.PositiveSmallIntegerField(default=50, help_text="Length of one class period.")
    break_minutes = models.PositiveSmallIntegerField(default=15, help_text="Break after every `break_every` periods (0 = none).")
    break_every = models.PositiveSmallIntegerField(default=2)
    max_teacher_hours = models.PositiveSmallIntegerField(default=30, help_text="Default weekly teaching-hour cap.")
    max_periods_per_teacher_day = models.PositiveSmallIntegerField(default=6)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.level} - {self.name}"


class GradeWindow(models.Model):
    """The daily time window a grade level may be scheduled in (e.g. Grade 11: 07:00-12:30)."""
    level = models.CharField(max_length=3, choices=LEVELS)
    grade_level = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    # Non-instructional breaks inside the daily window: no class may be placed in them (blank = no such break).
    recess_start = models.TimeField(null=True, blank=True)
    recess_end = models.TimeField(null=True, blank=True)
    lunch_start = models.TimeField(null=True, blank=True)
    lunch_end = models.TimeField(null=True, blank=True)
    # SHS only: ONE 30-minute break replaces recess + lunch (JHS keeps recess and lunch). No class is placed in it.
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)
    curriculum_framework = models.CharField(max_length=80, blank=True, help_text="Curriculum that applies to this grade, e.g. 'MATATAG'.")
    framework_verified = models.BooleanField(default=False)
    framework_note = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = ("level", "grade_level")
        ordering = ["level", "grade_level"]

    def __str__(self):
        return f"{self.level} Grade {self.grade_level} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class AcademicYear(models.Model):
    label = models.CharField(max_length=9, unique=True)       # "2026-2027"
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.label


class CalendarPeriod(models.Model):
    """A term (both levels), a semester (SHS) or a quarter (JHS). Terms, semesters and quarters are
    separate things -- the link between them is `PeriodMapping`, which administrators configure."""
    KINDS = [("term", "Term"), ("semester", "Semester"), ("quarter", "Quarter")]
    level = models.CharField(max_length=3, choices=LEVELS)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="periods")
    kind = models.CharField(max_length=10, choices=KINDS)
    number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=40)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=300, blank=True)
    is_placeholder = models.BooleanField(default=False, help_text="True until an administrator confirms the dates against the official calendar.")

    class Meta:
        unique_together = ("level", "academic_year", "kind", "number")
        ordering = ["level", "kind", "number"]

    def __str__(self):
        return f"{self.level} {self.academic_year} {self.name}"


class PeriodMapping(models.Model):
    """Which terms fall inside a semester / quarter."""
    grading_period = models.ForeignKey(CalendarPeriod, on_delete=models.CASCADE, related_name="term_links",
                                       limit_choices_to={"kind__in": ["semester", "quarter"]})
    term = models.ForeignKey(CalendarPeriod, on_delete=models.CASCADE, related_name="grading_links",
                             limit_choices_to={"kind": "term"})

    class Meta:
        unique_together = ("grading_period", "term")


class CalendarEvent(models.Model):
    """Holidays, examination blocks, suspensions: no regular classes on these dates."""
    KINDS = [("holiday", "Holiday"), ("exam", "Examination period"), ("suspension", "Class suspension"),
             ("break", "Break"), ("other", "Other (no classes)")]
    level = models.CharField(max_length=3, choices=LEVELS)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=12, choices=KINDS)
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    blocks_classes = models.BooleanField(default=True)
    source = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["start_date"]


class Strand(models.Model):
    """SHS strand / program (STEM, ABM, AHSS, TVL, ICT)."""
    TRACKS = [("ACADEMIC", "Academic Track"), ("TECHPRO", "Technical-Professional Track")]
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    track = models.CharField(max_length=10, choices=TRACKS)
    deped_cluster = models.CharField(max_length=120, blank=True, help_text="Matching cluster in the Strengthened SHS curriculum.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["track", "code"]

    def __str__(self):
        return self.code


class Section(models.Model):
    level = models.CharField(max_length=3, choices=LEVELS)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="sections")
    grade_level = models.PositiveSmallIntegerField()
    strand = models.ForeignKey(Strand, null=True, blank=True, on_delete=models.PROTECT, related_name="sections")
    name = models.CharField(max_length=40)
    student_count = models.PositiveSmallIntegerField(default=40)
    adviser = models.ForeignKey("Faculty", null=True, blank=True, on_delete=models.SET_NULL, related_name="advised_sections")
    home_room = models.ForeignKey("Room", null=True, blank=True, on_delete=models.SET_NULL, related_name="home_sections")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("level", "academic_year", "name")
        ordering = ["level", "grade_level", "name"]

    def __str__(self):
        return f"{self.level} G{self.grade_level} {self.name}"


class Room(models.Model):
    TYPES = [("classroom", "Classroom"), ("computer_lab", "Computer lab"), ("science_lab", "Science lab"),
             ("workshop", "TVL workshop"), ("gym", "Gym / court")]
    level = models.CharField(max_length=3, choices=LEVELS)
    building = models.CharField(max_length=60)
    floor = models.PositiveSmallIntegerField()
    room_number = models.CharField(max_length=20)
    capacity = models.PositiveSmallIntegerField(default=40)
    room_type = models.CharField(max_length=20, choices=TYPES, default="classroom")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("level", "building", "room_number")
        ordering = ["level", "floor", "room_number"]

    @property
    def name(self):
        return f"{self.building} {self.room_number}"

    def __str__(self):
        return self.name


class CurriculumSource(models.Model):
    """Where a batch of curriculum records came from (and how far it can be trusted)."""
    level = models.CharField(max_length=3, choices=LEVELS)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="curriculum_sources")
    title = models.CharField(max_length=200)
    reference = models.CharField(max_length=300, blank=True, help_text="DepEd Order / Memorandum number or document name.")
    url = models.URLField(blank=True, max_length=500)
    version = models.CharField(max_length=40, blank=True)
    is_verified = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class CurriculumSubject(models.Model):
    """One curriculum line. Schedules keep a snapshot of the fields they use, so editing or
    retiring a line (is_active=False) never changes a past schedule."""
    CATEGORIES = [("core", "Core"), ("applied", "Applied"), ("specialized", "Specialized"),
                  ("elective", "Elective"), ("learning_area", "Learning area"), ("guidance", "Homeroom / guidance")]
    level = models.CharField(max_length=3, choices=LEVELS)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="curriculum_subjects")
    source = models.ForeignKey(CurriculumSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="subjects")
    strand = models.ForeignKey(Strand, null=True, blank=True, on_delete=models.CASCADE, related_name="subjects",
                               help_text="Blank = applies to every strand of that grade (SHS) / all sections (JHS).")
    grade_level = models.PositiveSmallIntegerField()
    grading_period = models.PositiveSmallIntegerField(
        default=0, help_text="Semester number (SHS) or quarter number (JHS). 0 = the whole school year.")
    term = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Term the subject belongs to, where the curriculum names one.")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    learning_area = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=14, choices=CATEGORIES, default="core")
    classification = models.CharField(max_length=60, blank=True, help_text="Track-specific label, e.g. 'Academic elective - STEM cluster'.")
    sessions_per_week = models.PositiveSmallIntegerField(default=4, help_text="How many class periods per week.")
    total_hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    units = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    required_room_type = models.CharField(max_length=20, choices=Room.TYPES, default="classroom")
    prerequisite = models.CharField(max_length=200, blank=True)
    specialization = models.CharField(max_length=120, blank=True, help_text="Teacher specialization required (matches Faculty.specializations).")
    is_verified = models.BooleanField(default=False, help_text="True only when the line was read from an official DepEd document.")
    verification_note = models.CharField(max_length=400, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["level", "grade_level", "strand__code", "grading_period", "code"]
        unique_together = ("level", "academic_year", "strand", "grade_level", "grading_period", "code")

    def __str__(self):
        return f"{self.code} {self.name}"


class Faculty(models.Model):
    """Teacher profile for SHS / JHS (a shared User login, a separate profile)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="basic_ed_profile")
    level = models.CharField(max_length=3, choices=LEVELS)
    employee_id = models.CharField(max_length=30, unique=True)
    department = models.CharField(max_length=80, blank=True, help_text="Learning area / department.")
    strand = models.ForeignKey(Strand, null=True, blank=True, on_delete=models.SET_NULL, related_name="faculty")
    specializations = models.CharField(max_length=300, blank=True, help_text="Semicolon-separated, e.g. 'Mathematics; General Mathematics'.")
    qualifications = models.CharField(max_length=300, blank=True)
    max_weekly_hours = models.PositiveSmallIntegerField(default=30)
    preferred_start = models.TimeField(null=True, blank=True)
    preferred_end = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["level", "user__last_name"]

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def spec_list(self):
        return [x.strip().lower() for x in (self.specializations or "").split(";") if x.strip()]

    def __str__(self):
        return self.full_name


class Availability(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="availability")
    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    available = models.BooleanField(default=True, help_text="False = NOT available in this window.")

    class Meta:
        ordering = ["day", "start_time"]


class TeachingAssignment(models.Model):
    """Pins a teacher to a subject for a section. Anything not pinned is assigned by the engine."""
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="assignments")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="assignments")
    subject = models.ForeignKey(CurriculumSubject, on_delete=models.CASCADE, related_name="assignments")

    class Meta:
        unique_together = ("section", "subject")


class ScheduleRun(models.Model):
    """One generated (or revised) timetable for a level / grading period. Runs are never overwritten:
    a regeneration or a revision creates a new version, so the history is kept."""
    STATUSES = [("draft", "Draft"), ("submitted", "Submitted for review"), ("revision_requested", "Revision requested"),
                ("approved", "Approved"), ("published", "Published"), ("superseded", "Superseded")]
    level = models.CharField(max_length=3, choices=LEVELS)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="runs")
    grading_period = models.PositiveSmallIntegerField(help_text="Semester (SHS) or quarter (JHS) number.")
    grade_level = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Blank = every grade level.")
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUSES, default="draft")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=300, blank=True)
    validation = models.JSONField(default=dict, blank=True)
    stats = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ScheduleEntry(models.Model):
    run = models.ForeignKey(ScheduleRun, on_delete=models.CASCADE, related_name="entries")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="entries")
    subject = models.ForeignKey(CurriculumSubject, null=True, on_delete=models.SET_NULL, related_name="entries")
    # Snapshot: the timetable stays correct even if the curriculum line is edited later.
    subject_code = models.CharField(max_length=30)
    subject_name = models.CharField(max_length=200)
    learning_area = models.CharField(max_length=80, blank=True)
    teacher = models.ForeignKey(Faculty, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_manual = models.BooleanField(default=False)

    class Meta:
        ordering = ["day", "start_time"]


class ConflictRecord(models.Model):
    """Something the engine (or the validator) could not satisfy, with the reason."""
    run = models.ForeignKey(ScheduleRun, on_delete=models.CASCADE, related_name="conflicts")
    kind = models.CharField(max_length=40)
    severity = models.CharField(max_length=8, default="error")     # error | warning
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    subject_code = models.CharField(max_length=30, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class ScheduleEvent(models.Model):
    """Approval / revision history of a run."""
    run = models.ForeignKey(ScheduleRun, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=30)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
