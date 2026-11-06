from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user so `username` can follow the UPHM-<SchoolID> convention
    and so IT can bulk-create accounts with a forced default password.
    """
    ROLE_CHOICES = [
        ("registrar", "Registrar"),
        ("faculty", "Faculty"),   # Dean / Full-time / Part-time all live here
        ("student", "Student"),
        ("admin", "IT Admin"),
        # Basic-education modules (Senior High / Junior High). Kept apart from the college roles so
        # none of the college queries (which filter role="faculty") ever pick these accounts up.
        ("principal", "Principal"),
        ("teacher", "SHS/JHS Teacher"),
    ]
    SCHOOL_LEVEL_CHOICES = [("SHS", "Senior High School"), ("JHS", "Junior High School")]
    FACULTY_TYPE_CHOICES = [
        ("dean", "Dean"),
        ("full_time", "Full-Time"),
        ("part_time", "Part-Time"),
    ]

    school_id = models.CharField(max_length=30, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    faculty_type = models.CharField(
        max_length=20, choices=FACULTY_TYPE_CHOICES, null=True, blank=True,
        help_text="Only set when role == 'faculty'."
    )
    department = models.CharField(max_length=100, null=True, blank=True)
    extra_departments = models.CharField(
        max_length=300, blank=True, default="",
        help_text="A Dean who heads more than one department: the OTHER departments, separated by "
                  "semicolons (e.g. 'College of International Hospitality Management'). Leave blank otherwise.",
    )
    school_level = models.CharField(
        max_length=3, choices=SCHOOL_LEVEL_CHOICES, blank=True, default="",
        help_text="Only for Principal / SHS-JHS Teacher accounts: which school level they belong to.",
    )
    must_change_password = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~models.Q(role="faculty") | models.Q(faculty_type__isnull=False),
                name="faculty_must_have_faculty_type",
            )
        ]

    @property
    def is_it_admin(self):
        """IT admin: role 'admin', or a Django superuser that has no regular U-FAST role
        (e.g. the account made with `createsuperuser`)."""
        return self.role == "admin" or (self.is_superuser and self.role not in ("registrar", "faculty", "student"))

    @property
    def departments(self):
        """Every department this person covers: their own plus any extras (a dean
        of two colleges sees both in one dashboard)."""
        out = []
        for d in [self.department] + (self.extra_departments or "").split(";"):
            d = (d or "").strip()
            if d and d not in out:
                out.append(d)
        return out

    def save(self, *args, **kwargs):
        # Enforce the UPHM-<SchoolID> username convention automatically.
        if not self.school_id and self.username:      # e.g. `createsuperuser` leaves it blank (must be unique)
            self.school_id = self.username
        if not self.username:
            self.username = f"UPHM-{self.school_id}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"


class UserPreference(models.Model):
    """Personal settings of one user (the "My settings" page). Display only: nothing here changes roles,
    permissions, scheduling rules or schedule data. A user without a row simply gets the defaults
    (the row is created the first time it is read)."""
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="preference")
    phone = models.CharField(max_length=30, blank=True, default="")
    picture = models.CharField(max_length=100, blank=True, default="",
                               help_text="File name of the profile picture inside MEDIA_ROOT/profile_pictures (random, never the uploaded name).")
    theme = models.CharField(max_length=10, default="light")
    text_size = models.CharField(max_length=10, default="medium")
    table_density = models.CharField(max_length=12, default="comfortable")
    reduce_motion = models.CharField(max_length=10, default="system")
    time_format = models.CharField(max_length=4, default="12h")
    date_format = models.CharField(max_length=10, default="mdy_short")
    week_start = models.CharField(max_length=3, default="mon")
    landing_page = models.CharField(max_length=30, blank=True, default="")
    notify_schedule = models.BooleanField(default=True)
    notify_conflict = models.BooleanField(default=True)
    notify_exam = models.BooleanField(default=True)
    notify_substitute = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences of {self.user_id}"
