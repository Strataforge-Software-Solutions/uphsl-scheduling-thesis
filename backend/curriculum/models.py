from django.db import models


class AcademicField(models.Model):
    """A faculty's actual field of expertise -- 'Computer Science',
    'Mathematics', 'Nursing', 'Literature' -- as distinct from the granular
    list of curriculum Subject rows (course codes like 'CS4234 - On-the-Job
    Training'). FacultyProfile.specializations points HERE, not at Subject
    directly, so "Specializations" in the admin/UI reads as an actual
    academic discipline instead of a jumble of individual course codes."""
    name = models.CharField(max_length=100, unique=True)  # e.g. "Computer Science"

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Program(models.Model):
    name = models.CharField(max_length=100)          # e.g. "BS Computer Science"
    department = models.CharField(max_length=100)     # e.g. "Computer Studies"

    def __str__(self):
        return self.name


class Subject(models.Model):
    CLASSIFICATION_CHOICES = [("major", "Major"), ("minor", "Minor")]

    code = models.CharField(max_length=20)
    title = models.CharField(max_length=150)
    lec_units = models.PositiveSmallIntegerField(default=0)
    lab_units = models.PositiveSmallIntegerField(default=0)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="subjects")
    year_level = models.CharField(max_length=20)       # e.g. "1st Year"
    semester = models.CharField(max_length=20)         # e.g. "1st Sem"
    prerequisite = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    classification = models.CharField(
        max_length=10, choices=CLASSIFICATION_CHOICES, default="major",
        help_text="Determines exam-scheduling ownership: Registrar handles minors, Dean handles majors.",
    )
    field = models.ForeignKey(
        AcademicField, null=True, blank=True, on_delete=models.SET_NULL, related_name="subjects",
        help_text="The academic discipline this subject belongs to -- used to match it against "
                   "a faculty's specialization (AcademicField), not the subject itself.",
    )

    class Meta:
        unique_together = ("code", "program")

    @property
    def total_units(self):
        return self.lec_units + self.lab_units

    @property
    def department(self):
        return self.program.department

    def __str__(self):
        return f"{self.code} - {self.title}"
