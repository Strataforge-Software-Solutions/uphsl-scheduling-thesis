from django.contrib.auth import get_user_model
from rest_framework import serializers

from . import models as m

User = get_user_model()


class SchoolLevelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.SchoolLevelConfig
        fields = "__all__"


class GradeWindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.GradeWindow
        fields = "__all__"

    def validate(self, attrs):
        """SHS has ONE 30-minute break (no recess / lunch); JHS keeps recess and lunch. Breaks stay inside the school hours."""
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))
        level = get("level")
        start, end = get("start_time"), get("end_time")
        if start and end and end <= start:
            raise serializers.ValidationError("The school day must end after it starts.")
        if level == "SHS":
            attrs["recess_start"] = attrs["recess_end"] = attrs["lunch_start"] = attrs["lunch_end"] = None
            a, b = get("break_start"), get("break_end")
            if bool(a) != bool(b):
                raise serializers.ValidationError("Set both the start and the end of the break.")
            if a and b:
                if (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute) != 30:
                    raise serializers.ValidationError("The SHS break must be exactly 30 minutes.")
                if start and end and (a < start or b > end):
                    raise serializers.ValidationError("The break must be inside the school hours.")
        else:
            attrs["break_start"] = attrs["break_end"] = None
            for lo, hi, name in (("recess_start", "recess_end", "Recess"), ("lunch_start", "lunch_end", "Lunch")):
                a, b = get(lo), get(hi)
                if a and b and ((b <= a) or (start and a < start) or (end and b > end)):
                    raise serializers.ValidationError(f"{name} must end after it starts and stay inside the school hours.")
        return attrs


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.AcademicYear
        fields = "__all__"


class CalendarPeriodSerializer(serializers.ModelSerializer):
    linked_terms = serializers.SerializerMethodField()

    def get_linked_terms(self, obj):
        return [l.term_id for l in obj.term_links.all()] if obj.kind != "term" else []

    class Meta:
        model = m.CalendarPeriod
        fields = "__all__"
        read_only_fields = ("level", "academic_year")


class CalendarEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.CalendarEvent
        fields = "__all__"
        read_only_fields = ("level", "academic_year")


class StrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Strand
        fields = "__all__"


class SectionSerializer(serializers.ModelSerializer):
    strand_code = serializers.CharField(source="strand.code", read_only=True, default="")
    adviser_name = serializers.SerializerMethodField()
    home_room_name = serializers.CharField(source="home_room.name", read_only=True, default="")

    def get_adviser_name(self, obj):
        return obj.adviser.full_name if obj.adviser_id else ""

    class Meta:
        model = m.Section
        fields = "__all__"
        read_only_fields = ("level", "academic_year")


class RoomSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)

    class Meta:
        model = m.Room
        fields = "__all__"
        read_only_fields = ("level",)


class CurriculumSourceSerializer(serializers.ModelSerializer):
    subject_count = serializers.SerializerMethodField()

    def get_subject_count(self, obj):
        return obj.subjects.count()

    class Meta:
        model = m.CurriculumSource
        fields = "__all__"
        read_only_fields = ("level", "academic_year")


class CurriculumSubjectSerializer(serializers.ModelSerializer):
    strand_code = serializers.CharField(source="strand.code", read_only=True, default="")
    source_title = serializers.CharField(source="source.title", read_only=True, default="")

    def validate(self, attrs):
        from .structure import structure
        req = self.context.get("request")
        level = self.instance.level if self.instance else (req.query_params.get("level") if req else None) or (req.data.get("level") if req else None)
        grade = attrs.get("grade_level", getattr(self.instance, "grade_level", None))
        gp = attrs.get("grading_period", getattr(self.instance, "grading_period", 0))
        if level and grade is not None:
            kind, n = structure(level, grade)
            if gp < 0 or gp > n:
                raise serializers.ValidationError({"grading_period": f"Grade {grade} has {n} {kind}s per school year (use 1-{n}, or 0 for the whole year)."})
        return attrs

    class Meta:
        model = m.CurriculumSubject
        fields = "__all__"
        read_only_fields = ("level", "academic_year")


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Availability
        fields = ("id", "day", "start_time", "end_time", "available")

    def validate(self, data):
        if data["end_time"] <= data["start_time"]:
            raise serializers.ValidationError({"detail": "End time must be after start time."})
        return data


class FacultySerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.CharField(read_only=True)
    strand_code = serializers.CharField(source="strand.code", read_only=True, default="")
    availability = AvailabilitySerializer(many=True, read_only=True)
    account_active = serializers.BooleanField(source="user.is_active", required=False)
    weekly_hours = serializers.SerializerMethodField()

    def get_weekly_hours(self, obj):
        return self.context.get("hours", {}).get(obj.id, 0)

    class Meta:
        model = m.Faculty
        fields = ("id", "level", "employee_id", "first_name", "last_name", "username", "full_name", "department", "strand", "strand_code",
                  "specializations", "qualifications", "max_weekly_hours", "preferred_start", "preferred_end", "is_active",
                  "account_active", "availability", "weekly_hours")
        read_only_fields = ("level",)

    def create(self, validated):
        u = validated.pop("user")
        level = validated.pop("level", None) or self.context["level"]
        user = User(school_id=validated["employee_id"], first_name=u.get("first_name", ""), last_name=u.get("last_name", ""),
                    role="teacher", school_level=level, must_change_password=True, is_active=u.get("is_active", True))
        user.set_password(validated["employee_id"])
        user.save()
        return m.Faculty.objects.create(user=user, level=level, **validated)

    def update(self, inst, validated):
        u = validated.pop("user", {})
        for k, v in u.items():
            setattr(inst.user, k, v)
        if u:
            inst.user.save()
        for k, v in validated.items():
            setattr(inst, k, v)
        inst.save()
        return inst


class AssignmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source="faculty.full_name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = m.TeachingAssignment
        fields = "__all__"
        read_only_fields = ("qualification_override",)          # set only by the server's Assign anyway check


class EntrySerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source="section.name", read_only=True)
    grade_level = serializers.IntegerField(source="section.grade_level", read_only=True)
    strand_code = serializers.CharField(source="section.strand.code", read_only=True, default="")
    teacher_name = serializers.SerializerMethodField()
    room_name = serializers.SerializerMethodField()

    def get_teacher_name(self, obj):
        return obj.teacher.full_name if obj.teacher_id else ""

    def get_room_name(self, obj):
        return obj.room.name if obj.room_id else ""

    class Meta:
        model = m.ScheduleEntry
        fields = ("id", "run", "section", "section_name", "grade_level", "strand_code", "subject", "subject_code", "subject_name",
                  "learning_area", "teacher", "teacher_name", "room", "room_name", "day", "start_time", "end_time", "is_manual",
                  "qualification_override")
        read_only_fields = ("run", "subject", "subject_code", "subject_name", "learning_area", "is_manual", "qualification_override")


class ConflictSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source="section.name", read_only=True, default="")

    class Meta:
        model = m.ConflictRecord
        fields = ("id", "kind", "severity", "section", "section_name", "subject_code", "message", "created_at")


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    def get_actor_name(self, obj):
        return (obj.actor.get_full_name() or obj.actor.username) if obj.actor_id else ""

    class Meta:
        model = m.ScheduleEvent
        fields = ("id", "action", "actor_name", "comment", "created_at")


class RunSerializer(serializers.ModelSerializer):
    academic_year_label = serializers.CharField(source="academic_year.label", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    entry_count = serializers.SerializerMethodField()
    period_label = serializers.SerializerMethodField()

    def get_period_label(self, obj):
        from .structure import period_name
        return period_name(obj.level, obj.grade_level, obj.grading_period)

    def get_created_by_name(self, obj):
        return (obj.created_by.get_full_name() or obj.created_by.username) if obj.created_by_id else ""

    def get_entry_count(self, obj):
        return obj.entries.count()

    class Meta:
        model = m.ScheduleRun
        fields = ("id", "level", "academic_year", "academic_year_label", "grading_period", "grade_level", "version", "status", "created_by_name",
                  "created_at", "note", "validation", "stats", "entry_count", "period_label")
