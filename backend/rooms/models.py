from django.db import models


class Room(models.Model):
    ROOM_TYPES = [
        ("lecture", "Lecture"),
        ("lab", "Laboratory"),
        # PE / NSTP-ROTC classes are held here. Never used for ordinary subjects.
        ("gym", "Gym"),
        # Clinical areas, field sites, hospitals, "Online" -- real places classes
        # happen, but not rooms the scheduler may hand out on its own. Assigned
        # manually only.
        ("offsite", "Off-site / Online"),
    ]
    BUILDINGS = [
        ("M", "Main Building"),
        ("D", "Alta Building"),
        ("N", "New Building"),
        ("A", "Alfredo Building"),
    ]

    # `name` is the code shown everywhere in the system, e.g. "D-307".
    name = models.CharField(max_length=50)
    building = models.CharField(max_length=1, choices=BUILDINGS, blank=True)
    room_number = models.CharField(max_length=20, blank=True)
    label = models.CharField(
        max_length=80, blank=True,
        help_text="Friendly name, e.g. 'Computer Lab C' or 'BA Comm room'.",
    )
    capacity = models.PositiveSmallIntegerField()
    capacity_is_estimate = models.BooleanField(
        default=False,
        help_text="True when the capacity is a registrar's rough figure rather than a measured one.",
    )
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    department = models.CharField(max_length=100, null=True, blank=True)
    equipment = models.CharField(
        max_length=255, blank=True,
        help_text="Comma-separated, e.g. 'Projector, Whiteboard, 30 PCs, Aircon'",
    )
    is_accessible = models.BooleanField(
        default=True, help_text="Wheelchair/PWD accessible (ground floor, ramp, elevator, etc.)"
    )

    def __str__(self):
        return self.name


class DepartmentBuilding(models.Model):
    """Which building a department's major subjects should prefer. Editable by
    the Registrar in the admin -- the scheduler only reads it as a preference,
    never as a hard rule, so a full building falls back to another room."""
    department = models.CharField(max_length=100, unique=True)
    building = models.CharField(max_length=1, choices=Room.BUILDINGS)

    def __str__(self):
        return f"{self.department} -> {self.get_building_display()}"


class SubjectRoomAssignment(models.Model):
    """A Dean's room choice for ONE major subject: a preferred room, optional alternative rooms, and whether the
    preferred room is FIXED (the only room the subject may use). The generator tries the preferred room first, then
    the alternatives, then any other compatible room -- unless the assignment is fixed."""
    subject = models.OneToOneField("curriculum.Subject", on_delete=models.CASCADE, related_name="room_assignment")
    preferred_room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    alternative_rooms = models.ManyToManyField(Room, blank=True, related_name="+")
    is_fixed = models.BooleanField(default=False)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subject} -> {self.preferred_room}{' (fixed)' if self.is_fixed else ''}"


class DepartmentRoom(models.Model):
    """A room that is a department's 'home' room for its major subjects, taken from the GTI class program.
    It is only a PREFERENCE (the generator tries these rooms first); exclusive rooms are the ones whose
    Room.department is set."""
    department = models.CharField(max_length=100)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="home_for")
    source = models.CharField(max_length=60, blank=True, default="GTI class program")

    class Meta:
        unique_together = ("department", "room")

    def __str__(self):
        return f"{self.department} -> {self.room}"


class DepartmentEnrollment(models.Model):
    """Number of students a department has in a year level. The Dean can spread it over the department's
    sections (Section.student_count), which is what every room-capacity check uses."""
    department = models.CharField(max_length=100)
    year_level = models.CharField(max_length=20)
    students = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("department", "year_level")

    def __str__(self):
        return f"{self.department} {self.year_level}: {self.students}"
