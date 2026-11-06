from django.db import models


class Section(models.Model):
    """A specific class group, e.g. 'BSCS 2A' — needed so the engine can
    detect section conflicts, not just teacher/room conflicts."""
    name = models.CharField(max_length=30)             # e.g. "2A"
    program = models.ForeignKey("curriculum.Program", on_delete=models.CASCADE, related_name="sections")
    year_level = models.CharField(max_length=20)
    semester = models.CharField(max_length=20)
    student_count = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.program.name} {self.year_level} - {self.name}"


class Student(models.Model):
    """A class-list entry, NOT a login account -- students already use the
    GTI website for their own portal/schedule, so this system deliberately
    has no student-facing dashboard. This exists only so Registrar/Dean can
    record who's in a block section, and so a Full-time/Part-time faculty
    member can see their own class list for a subject (e.g. "who's in my
    IT214 2A class") without building out student auth or enrollment UI.

    Every student in a (PH-style) block section takes that section's whole
    subject load together, so one Student row maps to one Section, not to
    an individual subject -- the roster for any of a teacher's classes is
    just "every active Student in that class's Section"."""
    school_id = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=150)
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="students")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def save(self, *args, **kwargs):
        # Class lists no longer ask for a School ID; the column stays (it must be unique) and is filled with
        # an internal reference nobody has to type.
        if not (self.school_id or "").strip():
            import uuid
            self.school_id = f"CL-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} — {self.section}"


class TimeSlot(models.Model):
    # Sunday included for the non-standard-schedule cases that come up in
    # practice (ROTC, make-up classes, faculty seminars) -- without it, a
    # Sunday class could never be entered even though the Registrar/Dean may
    # legitimately need to put one on the schedule.
    DAYS = [("Mon", "Monday"), ("Tue", "Tuesday"), ("Wed", "Wednesday"),
            ("Thu", "Thursday"), ("Fri", "Friday"), ("Sat", "Saturday"),
            ("Sun", "Sunday")]

    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("day", "start_time", "end_time")

    def __str__(self):
        return f"{self.day} {self.start_time}-{self.end_time}"


def _schedule_text(r):
    """'CS101 CS1 Mon 07:00-08:00 N-101 Juan Cruz' for the audit log (never raises)."""
    try:
        t = r.timeslot
        who = r.teacher.user.get_full_name().strip() or r.teacher.user.username
        return f"{r.subject.code} {r.section.name} {t.day} {t.start_time:%H:%M}-{t.end_time:%H:%M} {r.room.name} {who}"
    except Exception:
        return f"class period #{r.pk}"


_REL = ("subject", "section", "timeslot", "room", "teacher__user")


class ScheduleQuerySet(models.QuerySet):
    """Bulk changes of class periods (Approve / Publish, Remove, Generate, Move ...) are recorded in the audit log as ONE entry each
    (or added to the open Generate entry). The per-record signals are switched off meanwhile, so nothing is logged twice."""

    def update(self, **kwargs):
        from audit import recorder
        rows = list(self.select_related(*_REL)) if not recorder.is_suppressed() else []
        n = super().update(**kwargs)
        if rows:
            fields = sorted(kwargs)
            new = {k: recorder.jsonable(getattr(v, "pk", v)) for k, v in kwargs.items()}
            old_rows = [{"record": _schedule_text(r), **{k: recorder.jsonable(getattr(r, k + "_id", getattr(r, k, None))) for k in fields}}
                        for r in rows]
            recorder.record_rows("update", "schedule", [r.pk for r in rows], [x["record"] for x in old_rows],
                                 old={"rows": old_rows[:recorder.MAX_ITEMS]}, new=new)
        return n

    def delete(self):
        from audit import recorder
        if recorder.is_suppressed():
            return super().delete()
        rows = list(self.select_related(*_REL))
        with recorder.suppressed():
            res = super().delete()
        if rows:
            recorder.record_rows("delete", "schedule", [r.pk for r in rows], [_schedule_text(r) for r in rows])
        return res

    def bulk_create(self, objs, *args, **kwargs):
        from audit import recorder
        made = super().bulk_create(objs, *args, **kwargs)
        if made and not recorder.is_suppressed():
            recorder.record_rows("create", "schedule", [m.pk for m in made], [_schedule_text(m) for m in made])
        return made


class Schedule(models.Model):
    """One CSP 'variable' assignment: subject taught by teacher, in room, at timeslot, for section."""
    objects = ScheduleQuerySet.as_manager()

    # --- Approval workflow (from Dean Villanueva's interview: she drafts the class
    # program, the School Director approves it, only then is it encoded/live). We
    # don't have a separate Director role, so Registrar or Dean marks the approval
    # step themselves (CanEditCurriculum already scopes who may touch which dept).
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("published", "Published"),
    ]

    subject = models.ForeignKey("curriculum.Subject", on_delete=models.CASCADE)
    teacher = models.ForeignKey("faculty.FacultyProfile", on_delete=models.CASCADE)
    room = models.ForeignKey("rooms.Room", on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    is_substitution = models.BooleanField(default=False)
    original_teacher = models.ForeignKey(
        "faculty.FacultyProfile", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="substituted_schedules",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="approved_schedules",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # --- ML groundwork: these accumulate the training signal for the future
    # schedule-ranking model (see AnalyticsTab / ML feature discussion).
    # is_manual_override: True if a Dean/Registrar edited this after the CSP
    # engine generated it -- a negative signal for whatever the engine picked.
    is_manual_override = models.BooleanField(default=False)
    # "Assign anyway": a Dean placed a teacher who is NOT connected to the subject (no matching specialization / degree), by hand,
    # with a reason. Null for every normal class. {"reason", "by_id", "by_name", "role", "at"}. The engine never sets this itself.
    qualification_override = models.JSONField(null=True, blank=True)
    school_year = models.CharField(max_length=20, blank=True)  # e.g. "2026-2027"
    # Copy of section.semester. 1st Sem and 2nd Sem never meet at the same time, so a room or teacher
    # may be used at the same hour in both -- the double-booking rules below are per semester.
    term = models.CharField(max_length=20, blank=True, default="", db_index=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    # Merged (shared) class: several sections from DIFFERENT departments attend
    # ONE class of the same minor subject (same teacher, room and time) when
    # their combined headcount fits the room. All rows of one shared class carry
    # the same merge_key; empty = an ordinary single-section class.
    merge_key = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        constraints = [
            # Hard constraint: Faculty Conflict — same teacher, same timeslot.
            # (Rows of a merged class are exempt from each other: one teacher/room
            # legitimately serves several sections at once. engine.conflicts still
            # blocks any OTHER class from using that teacher/room then.)
            models.UniqueConstraint(fields=["teacher", "timeslot", "term"], condition=models.Q(merge_key=""),
                                    name="no_teacher_double_booking"),
            # Hard constraint: Room Conflict — same room, same timeslot.
            models.UniqueConstraint(fields=["room", "timeslot", "term"], condition=models.Q(merge_key=""),
                                    name="no_room_double_booking"),
            # Hard constraint: Section Conflict — same section, same timeslot.
            models.UniqueConstraint(fields=["section", "timeslot"], name="no_section_double_booking"),
        ]

    def save(self, *args, **kwargs):
        if not self.term and self.section_id:
            self.term = self.section.semester
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject.code} | {self.section} | {self.timeslot}"


class Constraint(models.Model):
    """Faculty availability / room-type rules fed into the CSP domain filter."""
    RULE_TYPES = [("availability", "Availability"), ("room_type", "Room Type")]

    teacher = models.ForeignKey("faculty.FacultyProfile", null=True, blank=True, on_delete=models.CASCADE)
    room = models.ForeignKey("rooms.Room", null=True, blank=True, on_delete=models.CASCADE)
    department = models.CharField(max_length=100, null=True, blank=True)
    day = models.CharField(max_length=10)
    timeslot = models.CharField(max_length=30)
    rule_type = models.CharField(max_length=50, choices=RULE_TYPES)

    def __str__(self):
        return f"{self.rule_type} constraint for {self.teacher or self.room or self.department}"


class ConflictLog(models.Model):
    """Persists what the CSP engine's conflict report only used to return once in
    an API response -- needed both to import IT's historical conflict data and to
    keep a real audit trail of conflicts going forward (used by Generate Schedule
    and manual Schedule edits alike)."""
    CONFLICT_TYPES = [
        ("teacher_double_booking", "Teacher Double-Booking"),
        ("room_double_booking", "Room Double-Booking"),
        ("section_double_booking", "Section Double-Booking"),
        ("room_unavailable", "Room Unavailable"),
        ("faculty_overload", "Faculty Overload"),
        ("unresolved_csp", "Unresolved CSP Assignment"),
    ]

    conflict_type = models.CharField(max_length=30, choices=CONFLICT_TYPES)
    description = models.CharField(max_length=500)
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.SET_NULL)
    teacher = models.ForeignKey("faculty.FacultyProfile", null=True, blank=True, on_delete=models.SET_NULL)
    room = models.ForeignKey("rooms.Room", null=True, blank=True, on_delete=models.SET_NULL)
    school_year = models.CharField(max_length=20, blank=True)
    semester = models.CharField(max_length=20, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.conflict_type}: {self.description[:60]}"


class SchedulingConfig(models.Model):
    """Singleton of system-wide scheduling policy knobs, editable by the Registrar.

    student_overlap_tolerance_minutes: Dean Villanueva's interview — because the
    college has limited course offerings, she deliberately allows a student's two
    classes to overlap by up to 30 minutes rather than flagging it as a hard
    conflict. This stores that grace window so conflicts.py can apply it to
    SECTION/student-facing overlaps only -- teacher and room conflicts stay a
    hard 0-minute tolerance, since one person/room genuinely cannot be in two
    places regardless of policy."""
    student_overlap_tolerance_minutes = models.PositiveSmallIntegerField(default=30)

    # --- Faculty workload policy (configurable; never hard-coded in the engine) ---
    # Maximum teaching hours PER WEEK, per semester, for each classification.
    # A Dean is a faculty member too and uses the Full-time limit unless changed here.
    max_weekly_hours_full_time = models.PositiveSmallIntegerField(default=24)
    max_weekly_hours_part_time = models.PositiveSmallIntegerField(default=12)
    WORKLOAD_POLICY_CHOICES = [
        ("override", "Warn, allow authorized override (audit-logged)"),
        ("strict", "Strict: never allow an overloaded assignment"),
    ]
    workload_policy = models.CharField(max_length=10, choices=WORKLOAD_POLICY_CHOICES, default="override")
    # "Reserve lunch gap (optional)": a SOFT preference for a free hour between 10:30 AM and 2:30 PM for each section and professor
    # per day (engine/lunch_gap.py). OFF by default; never skips a class, only orders placements and warns.
    reserve_lunch_gap = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        from django.db.utils import OperationalError, ProgrammingError
        try:
            obj, _ = cls.objects.get_or_create(pk=1)
            return obj
        except (OperationalError, ProgrammingError):
            # The workload columns are missing: `python manage.py migrate` has not been run yet.
            # Keep the whole system working on the defaults instead of answering every request with a 500.
            from django.db import connection
            tol = 30
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT student_overlap_tolerance_minutes FROM engine_schedulingconfig WHERE id = 1")
                    row = cur.fetchone()
                    tol = row[0] if row else 30
            except Exception:
                pass
            return cls(pk=1, student_overlap_tolerance_minutes=tol)

    def __str__(self):
        return f"SchedulingConfig(tolerance={self.student_overlap_tolerance_minutes}min)"


class Log(models.Model):
    ACTIONS = [("CREATE", "Create"), ("UPDATE", "Update"), ("DELETE", "Delete")]

    action = models.CharField(max_length=10, choices=ACTIONS)
    schedule_id = models.IntegerField()
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField()

    def __str__(self):
        return f"{self.action} on schedule {self.schedule_id} by {self.user}"


class SharedClassGroup(models.Model):
    """Programs that attend ONE shared class of a minor (Gen Ed) subject, chosen before generating (2 or 3 programs).
    Only a CONFIRMED group is used by the generator. The curriculum, sections and students of each program are untouched:
    sharing only gives the participating sections the same teacher, room and time (Schedule.merge_key)."""
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    lec_units = models.PositiveSmallIntegerField(default=0)
    lab_units = models.PositiveSmallIntegerField(default=0)
    year_level = models.CharField(max_length=20)
    semester = models.CharField(max_length=20)
    programs = models.ManyToManyField("curriculum.Program", related_name="shared_class_groups")
    confirmed = models.BooleanField(default=False)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirmed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} {self.year_level} {self.semester} shared"


class SharedClassExclusive(models.Model):
    """The Dean / Registrar decided that this program keeps this minor subject to itself (never merged, not even automatically)."""
    program = models.ForeignKey("curriculum.Program", on_delete=models.CASCADE, related_name="exclusive_minor_classes")
    code = models.CharField(max_length=30)
    year_level = models.CharField(max_length=20)
    semester = models.CharField(max_length=20)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("program", "code", "year_level", "semester")


class GenEdMoveRequest(models.Model):
    """A Dean asks the Registrar to move a Gen Ed (minor) class of their own program to another day / time, e.g. to free a time for a
    major subject. The Dean picks the new time from the Registrar's own clash-free list (engine.reschedule.suggest). Nothing moves until
    the Registrar approves; approval re-checks every schedule at that moment and moves ONLY that Gen Ed class (its whole shared group),
    never another Dean's or Gen Ed class (engine.gened_requests)."""
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled"),
                      ("failed", "Could not be applied")]
    schedule_ids = models.JSONField(default=list)            # the rows of the class when the request was made (one section)
    subject = models.ForeignKey("curriculum.Subject", null=True, on_delete=models.SET_NULL, related_name="+")
    section = models.ForeignKey(Section, null=True, on_delete=models.SET_NULL, related_name="+")
    current_label = models.CharField(max_length=200, blank=True, default="")
    option_key = models.CharField(max_length=200)            # the chosen time (teacher:room:slot ids) from the clash-free list
    target_label = models.CharField(max_length=200, blank=True, default="")
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    requested_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="gened_move_requests")
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
