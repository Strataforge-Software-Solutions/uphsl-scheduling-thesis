from rest_framework import serializers
from .models import Program, Subject, AcademicField


class AcademicFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicField
        fields = ["id", "name"]


class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ["id", "name", "department"]


class SubjectSerializer(serializers.ModelSerializer):
    department = serializers.CharField(read_only=True)
    total_units = serializers.IntegerField(read_only=True)
    # Read-only convenience so the frontend table can show "Computer Science"
    # instead of just a field id; writes still go through "field" (the FK id).
    field_name = serializers.CharField(source="field.name", read_only=True, default=None)
    program_name = serializers.CharField(source="program.name", read_only=True)
    # read-only: the shortest Start-End window Generate accepts for this subject (engine.scheduler.window_need_minutes)
    need_minutes = serializers.SerializerMethodField()

    def get_need_minutes(self, obj):
        from engine.scheduler import window_need_minutes
        return window_need_minutes(obj)

    class Meta:
        model = Subject
        fields = [
            "id", "code", "title", "lec_units", "lab_units", "total_units",
            "program", "year_level", "semester", "prerequisite", "department",
            "classification", "field", "field_name", "program_name", "need_minutes",
        ]

    def validate(self, attrs):
        # Enforce department-scoped edit rights at the serializer level too,
        # since DeanView is scoped to their own department in the frontend.
        request = self.context.get("request")
        program = attrs.get("program") or getattr(self.instance, "program", None)
        if request and program:
            user = request.user
            if user.role == "faculty" and user.faculty_type == "dean":
                if program.department not in user.departments:
                    raise serializers.ValidationError(
                        "Deans may only edit curriculum for their own department."
                    )
        return attrs
