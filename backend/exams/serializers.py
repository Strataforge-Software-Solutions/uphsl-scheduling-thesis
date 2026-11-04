from rest_framework import serializers
from engine.conflicts import find_conflicts
from .models import ExamSchedule


class ExamScheduleSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_title = serializers.CharField(source="subject.title", read_only=True)
    subject_classification = serializers.CharField(source="subject.classification", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    year_level = serializers.CharField(source="section.year_level", read_only=True)
    semester = serializers.CharField(source="section.semester", read_only=True)
    program_name = serializers.CharField(source="section.program.name", read_only=True)
    department = serializers.CharField(source="section.program.department", read_only=True)
    proctor_name = serializers.CharField(source="proctor.user.username", read_only=True)
    proctor_full_name = serializers.SerializerMethodField()
    room_name = serializers.CharField(source="room.name", read_only=True)
    timeslot_day = serializers.CharField(source="timeslot.day", read_only=True)
    timeslot_start = serializers.TimeField(source="timeslot.start_time", read_only=True)
    timeslot_end = serializers.TimeField(source="timeslot.end_time", read_only=True)

    combined_with = serializers.SerializerMethodField()

    def get_combined_with(self, obj):
        """Names of the other sections sitting the same exam in the same room (empty for an ordinary exam)."""
        if not obj.merge_key:
            return []
        rows = (ExamSchedule.objects.filter(merge_key=obj.merge_key, exam_date=obj.exam_date, timeslot_id=obj.timeslot_id)
                .exclude(pk=obj.pk).select_related("section__program"))
        return [f"{r.section.program.name} {r.section.name}" for r in rows]

    def get_proctor_full_name(self, obj):
        u = obj.proctor.user
        return u.get_full_name().strip() or u.username

    class Meta:
        model = ExamSchedule
        fields = [
            "id", "subject", "subject_code", "subject_title", "subject_classification",
            "section", "section_name", "year_level", "semester", "program_name", "department",
            "proctor", "proctor_name", "proctor_full_name",
            "room", "room_name", "timeslot", "timeslot_day", "timeslot_start", "timeslot_end",
            "exam_date", "exam_period", "duration_minutes",
            "is_manual_override", "school_year", "merge_key", "combined_with",
        ]

    def validate(self, attrs):
        subject = attrs.get("subject") or getattr(self.instance, "subject", None)
        request = self.context.get("request")

        # Ownership check mirrors the permission class but at the field level,
        # since `subject` might change on update.
        if request and subject:
            user = request.user
            if subject.classification == "minor" and user.role != "registrar":
                raise serializers.ValidationError(
                    "Only the Registrar may schedule exams for Gen Ed subjects."
                )
            if subject.classification == "major":
                if not (user.role == "faculty" and user.faculty_type == "dean"
                        and subject.department in user.departments):
                    raise serializers.ValidationError(
                        "Only the Dean of the owning department may schedule exams for program subjects."
                    )

        # Cross-table conflict check — this is what actually stops a Dean's
        # major exam from silently colliding with a Registrar's minor exam.
        conflicts = find_conflicts(
            teacher=attrs.get("proctor") or getattr(self.instance, "proctor", None),
            room=attrs.get("room") or getattr(self.instance, "room", None),
            section=attrs.get("section") or getattr(self.instance, "section", None),
            timeslot=attrs.get("timeslot") or getattr(self.instance, "timeslot", None),
            exam_date=attrs.get("exam_date") or getattr(self.instance, "exam_date", None),
            merge_key=getattr(self.instance, "merge_key", "") if self.instance else "",
            exclude_model="ExamSchedule",
            exclude_pk=self.instance.pk if self.instance else None,
            semester=getattr(attrs.get("section") or getattr(self.instance, "section", None), "semester", None),
        )
        if conflicts:
            raise serializers.ValidationError({"timeslot": conflicts})

        return attrs
