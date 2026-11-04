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
