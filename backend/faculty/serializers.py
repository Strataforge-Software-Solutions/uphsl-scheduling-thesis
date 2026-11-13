from rest_framework import serializers
from .models import FacultyProfile, Availability, Absence, WorkloadRecord, CoverageSuggestion


def display_name(user):
    """'Joaquin Mercado (UPHM-F1001)' -- the person's name plus their login, so
    the Registrar/Dean can tell who is who (just the ID told them nothing)."""
    if user is None:
        return None
    name = user.get_full_name().strip()
    return f"{name} ({user.username})" if name else user.username


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Availability
        fields = ["id", "faculty", "day", "start_time", "end_time", "preference", "school_year", "semester", "submitted_at", "is_active"]
        read_only_fields = ["faculty", "submitted_at"]

    def validate(self, attrs):
        """No duplicate or overlapping availability windows: the same faculty may not submit the same day
        twice with overlapping times for the same school year / semester."""
        inst = self.instance
        start = attrs.get("start_time", getattr(inst, "start_time", None))
        end = attrs.get("end_time", getattr(inst, "end_time", None))
        day = (attrs.get("day", getattr(inst, "day", "")) or "").strip()
        if start is not None and end is not None and not start < end:
            raise serializers.ValidationError({"end_time": "The end time must be later than the start time."})
        request = self.context.get("request")
        faculty = getattr(inst, "faculty", None)
        if faculty is None and request is not None and hasattr(request.user, "faculty_profile"):
            faculty = request.user.faculty_profile
        if faculty is None or start is None or end is None or not day:
            return attrs
        year = attrs.get("school_year", getattr(inst, "school_year", "")) or ""
        sem = attrs.get("semester", getattr(inst, "semester", "")) or ""
        clash = Availability.objects.filter(
            faculty=faculty, is_active=True, day__iexact=day, school_year=year, semester=sem,
            start_time__lt=end, end_time__gt=start,
        )
        if inst is not None:
            clash = clash.exclude(pk=inst.pk)
        other = clash.first()
        if other is not None:
            same = other.start_time == start and other.end_time == end
            raise serializers.ValidationError({"detail": (
                f"You already submitted {other.day} {other.start_time.strftime('%I:%M %p').lstrip('0')}-"
                f"{other.end_time.strftime('%I:%M %p').lstrip('0')}. "
                + ("This exact time is already on your list." if same else
                   "The new time overlaps it -- edit or remove that entry instead of adding another."))})
        return attrs


class AbsenceSerializer(serializers.ModelSerializer):
    faculty_name = serializers.SerializerMethodField()

    def get_faculty_name(self, obj):
        return display_name(obj.faculty.user)

    class Meta:
        model = Absence
        fields = [
            "id", "faculty", "faculty_name", "date", "reason", "status",
            "school_year", "semester", "submitted_at", "coverage_status",
        ]
        read_only_fields = ["submitted_at", "coverage_status"]

    def validate(self, attrs):
        """One absence record per faculty per date (a denied one may be filed again)."""
        inst = self.instance
        faculty = attrs.get("faculty", getattr(inst, "faculty", None))
        date = attrs.get("date", getattr(inst, "date", None))
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (faculty is not None and user is not None and user.is_authenticated
                and user.role == "faculty" and user.faculty_type == "dean"
                and faculty.user.department not in user.departments):
            raise serializers.ValidationError("You can only manage absences in your own college.")
        if faculty is not None and date is not None:
            dup = Absence.objects.filter(faculty=faculty, date=date).exclude(status="denied")
            if inst is not None:
                dup = dup.exclude(pk=inst.pk)
            if dup.exists():
                raise serializers.ValidationError({"detail": (
                    f"{display_name(faculty.user)} already has an absence recorded for {date}. "
                    "Open that entry instead of adding a second one.")})
        return attrs


class CoverageSuggestionSerializer(serializers.ModelSerializer):
    suggested_faculty_name = serializers.SerializerMethodField()

    def get_suggested_faculty_name(self, obj):
        return display_name(obj.suggested_faculty.user) if obj.suggested_faculty else None
    schedule_label = serializers.CharField(source="schedule.__str__", read_only=True)

    class Meta:
        model = CoverageSuggestion
        fields = [
            "id", "absence", "schedule", "schedule_label",
            "suggested_faculty", "suggested_faculty_name", "reason", "applied", "created_at",
        ]
        read_only_fields = fields


class WorkloadRecordSerializer(serializers.ModelSerializer):
    faculty_name = serializers.SerializerMethodField()

    def get_faculty_name(self, obj):
        return display_name(obj.faculty.user)

    class Meta:
        model = WorkloadRecord
        fields = ["id", "faculty", "faculty_name", "school_year", "semester", "total_hours", "is_overload", "notes"]
        read_only_fields = ["is_overload"]


class FacultyProfileSerializer(serializers.ModelSerializer):
    availability_slots = AvailabilitySerializer(many=True, read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    department = serializers.CharField(source="user.department", read_only=True)
    faculty_type = serializers.CharField(source="user.faculty_type", read_only=True)
    full_name = serializers.SerializerMethodField()
    specialization_names = serializers.SerializerMethodField()

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (user and user.is_authenticated and user.role == "faculty"
                and user.faculty_type in {"full_time", "part_time"}):
            # Faculty can update their own expertise, but profile/account fields
            # remain managed by the Dean or Registrar.
            for name, field in fields.items():
                if name != "specializations":
                    field.read_only = True
        return fields

    def get_full_name(self, obj):
        return obj.user.get_full_name().strip() or obj.user.username

    def get_specialization_names(self, obj):
        # .all() on the prefetched relation -- no extra query per faculty.
        return sorted(f.name for f in obj.specializations.all())

    class Meta:
        model = FacultyProfile
        fields = [
            "id", "user", "username", "full_name", "faculty_type", "department",
            "specializations", "specialization_names", "target_load_hours", "availability_slots",
        ]
