from rest_framework import serializers
from .models import Section, Student, TimeSlot, Schedule, Constraint, Log, ConflictLog, SchedulingConfig


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "name", "program", "year_level", "semester", "student_count"]


class StudentSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source="section.name", read_only=True)
    program_name = serializers.CharField(source="section.program.name", read_only=True)
    year_level = serializers.CharField(source="section.year_level", read_only=True)
    semester = serializers.CharField(source="section.semester", read_only=True)

    class Meta:
        model = Student
        fields = ["id", "school_id", "full_name", "section", "section_name", "year_level", "semester", "program_name",
                  "is_active", "created_at"]
        extra_kwargs = {"school_id": {"required": False, "allow_blank": True}}


class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = ["id", "day", "start_time", "end_time"]


class ScheduleSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_title = serializers.CharField(source="subject.title", read_only=True)
    # the teacher's NAME (never the login / school ID, which is private)
    teacher_name = serializers.SerializerMethodField()
    room_name = serializers.CharField(source="room.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    program = serializers.IntegerField(source="section.program.id", read_only=True)
    program_name = serializers.CharField(source="section.program.name", read_only=True)
    department = serializers.CharField(source="section.program.department", read_only=True)
    year_level = serializers.CharField(source="section.year_level", read_only=True)
    semester = serializers.CharField(source="section.semester", read_only=True)
    timeslot_day = serializers.CharField(source="timeslot.day", read_only=True)
    timeslot_start = serializers.TimeField(source="timeslot.start_time", read_only=True)
    timeslot_end = serializers.TimeField(source="timeslot.end_time", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.username", read_only=True, default=None)
    subject_classification = serializers.CharField(source="subject.classification", read_only=True)
    subject_field = serializers.IntegerField(source="subject.field_id", read_only=True, default=None)
    subject_field_name = serializers.CharField(source="subject.field.name", read_only=True, default=None)
    merged_with = serializers.SerializerMethodField()
    merged_students = serializers.SerializerMethodField()

    def _merge_info(self, obj):
        """{merge_key: {section_id: (label, student_count)}} built once per request."""
        if not obj.merge_key:
            return {}
        cache = self.context.setdefault("_merge_cache", {})
        if "all" not in cache:
            data = {}
            for k, sid, name, prog, n in Schedule.objects.exclude(merge_key="").values_list(
                    "merge_key", "section_id", "section__name", "section__program__name", "section__student_count").distinct():
                data.setdefault(k, {})[sid] = (f"{name} ({prog})", n)
            cache["all"] = data
        return cache["all"].get(obj.merge_key, {})

    def get_merged_with(self, obj):
        info = self._merge_info(obj)
        return [label for sid, (label, n) in info.items() if sid != obj.section_id]

    def get_merged_students(self, obj):
        info = self._merge_info(obj)
        return sum(n for _, n in info.values()) if info else None

    class Meta:
        model = Schedule
        # The DB constraints stay as the last safety net, but DRF's auto "must make a unique set" messages are replaced by
        # the view's own plain-language conflict check (teacher / room / students named), so a clash reads clearly.
        validators = []
        fields = [
            "id", "subject", "subject_code", "subject_title", "subject_classification",
            "subject_field", "subject_field_name",
            "teacher", "teacher_name",
            "room", "room_name", "section", "section_name", "timeslot",
            "timeslot_day", "timeslot_start", "timeslot_end",
            "program", "program_name", "department", "year_level", "semester",
            "is_substitution", "original_teacher",
            "is_manual_override", "school_year", "generated_at",
            "status", "approved_by", "approved_by_name", "approved_at",
            "merge_key", "merged_with", "merged_students", "qualification_override",
        ]
        read_only_fields = ["status", "approved_by", "approved_at", "merge_key", "qualification_override"]

    def get_teacher_name(self, obj):
        u = obj.teacher.user if obj.teacher_id else None
        return (u.get_full_name().strip() or "Unnamed teacher") if u else ""


class ConstraintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Constraint
        fields = ["id", "teacher", "room", "department", "day", "timeslot", "rule_type"]


class LogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Log
        fields = ["id", "action", "schedule_id", "user", "timestamp", "details"]
        read_only_fields = fields


class ConflictLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConflictLog
        fields = [
            "id", "conflict_type", "description", "section", "teacher", "room",
            "school_year", "semester", "occurred_at", "resolved",
        ]


class SchedulingConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchedulingConfig
        fields = ["id", "student_overlap_tolerance_minutes", "max_weekly_hours_full_time",
                  "max_weekly_hours_part_time", "workload_policy", "reserve_lunch_gap", "updated_at"]
        read_only_fields = ["id", "updated_at"]
        extra_kwargs = {
            "max_weekly_hours_full_time": {"min_value": 1, "max_value": 80},
            "max_weekly_hours_part_time": {"min_value": 1, "max_value": 80},
        }
