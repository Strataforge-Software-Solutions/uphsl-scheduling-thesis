from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from .models import FacultyProfile, Availability, Absence, WorkloadRecord, CoverageSuggestion
from .serializers import (
    FacultyProfileSerializer, AvailabilitySerializer,
    AbsenceSerializer, WorkloadRecordSerializer, CoverageSuggestionSerializer,
)
from .permissions import CanManageFacultyProfiles
from engine.permissions import ReadOnlyOrRegistrarDean

# Availability.day is a free-text field (the submission form's placeholder
# is "Day (e.g., Monday)"), not a fixed choice list like engine.TimeSlot.DAYS
# -- so values in the wild are full day names, typed freely, and may vary in
# case/spelling. This covers the expected form; anything that doesn't match
# sorts after the known days rather than erroring.
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _check_dean_faculty_scope(user, faculty_user):
    if (user.role == "faculty" and user.faculty_type == "dean"
            and faculty_user.department not in user.departments):
        raise PermissionDenied("You can only manage faculty in your own college.")


class FacultyProfileViewSet(viewsets.ModelViewSet):
    queryset = FacultyProfile.objects.select_related("user").prefetch_related(
        "availability_slots", "specializations"
    ).all()
    serializer_class = FacultyProfileSerializer
    permission_classes = [CanManageFacultyProfiles]

    def get_queryset(self):
        user = self.request.user
        qs = FacultyProfile.objects.select_related("user").prefetch_related(
            "availability_slots", "specializations"
        )
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(user__department__in=user.departments)
        if user.role == "faculty":
            return qs.filter(user=user)
        return qs.none()

    def perform_create(self, serializer):
        faculty_user = serializer.validated_data.get("user")
        if faculty_user is not None:
            _check_dean_faculty_scope(self.request.user, faculty_user)
        serializer.save()

    def perform_update(self, serializer):
        faculty_user = serializer.validated_data.get("user", self.get_object().user)
        _check_dean_faculty_scope(self.request.user, faculty_user)
        serializer.save()

    @action(detail=False, methods=["get"])
    def roster(self, request):
        """One row per faculty member -- full name, type, current teaching
        load (in units, counting each assigned subject once regardless of how
        many weekly periods it occupies), the distinct days they've submitted
        availability for, plus (added so a Dean can click a teacher and see
        enough to decide what major/minor subject to hand them) their full
        availability slots (day/start/end/preference) and specialization
        field names. Feeds the Dean's "Faculty" tab roster card. Dean sees
        only their own department; Registrar sees everyone; anyone else gets
        nothing -- this is staff-facing data."""
        from engine.models import Schedule
        from curriculum.models import Subject

        user = request.user
        qs = FacultyProfile.objects.select_related("user").prefetch_related(
            "availability_slots", "specializations"
        )
        if user.is_it_admin or user.role == "registrar":
            pass
        elif user.role == "faculty" and user.faculty_type == "dean":
            qs = qs.filter(user__department__in=user.departments)
        else:
            raise PermissionDenied("Only the Registrar or a Dean may view the faculty roster.")

        from engine import workload as wl
        qs = list(qs)
        wl_by_id = {r["faculty_id"]: r for r in wl.workload_rows(qs)}
        data = []
        for fp in qs:
            full_name = fp.user.get_full_name().strip() or fp.user.username
            active_slots = [a for a in fp.availability_slots.all() if a.is_active]
            days = sorted(
                {a.day.strip().capitalize() for a in active_slots if a.day},
                key=lambda d: DAY_ORDER.index(d) if d in DAY_ORDER else 99,
            )
            availability_slots = sorted(
                [
                    {
                        "id": a.id,
                        "day": a.day.strip().capitalize() if a.day else a.day,
                        "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,
                        "end_time": a.end_time.strftime("%H:%M") if a.end_time else None,
                        "preference": a.preference,
                    }
                    for a in active_slots
                ],
                key=lambda s: (
                    DAY_ORDER.index(s["day"]) if s["day"] in DAY_ORDER else 99,
                    s["start_time"] or "",
                ),
            )
            subject_ids = set(
                Schedule.objects.filter(teacher=fp).values_list("subject_id", flat=True)
            )
            load_units = sum(
                s.total_units for s in Subject.objects.filter(id__in=subject_ids)
            ) if subject_ids else 0

            data.append({
                "id": fp.id,
                "full_name": full_name,
                "faculty_type": fp.user.faculty_type,
                "department": fp.user.department,
                "load_units": load_units,
                "availability_days": days,
                "availability_slots": availability_slots,
                "specializations": [f.name for f in fp.specializations.all()],
                "school_id": fp.user.school_id,
                "workload": {k: wl_by_id[fp.id][k] for k in (
                    "current_hours", "max_hours", "remaining_hours", "overload_hours", "status", "term", "warning")},
            })
        return Response(data)


class AvailabilityViewSet(viewsets.ModelViewSet):
    """Part-time AND full-time faculty submit their own; Dean/Registrar view all
    for their scope. (Dean Villanueva's interview: scheduling should be built
    around ALL faculty's availability, not just part-time's -- full-time
    previously had no submission path at all.)"""
    serializer_class = AvailabilitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Availability.objects.select_related("faculty__user")
        # Scoped to "only my own rows" for BOTH part-time and full-time --
        # otherwise a full-time faculty would fall through to an unscoped
        # queryset and see every faculty's submitted availability, the same
        # privacy-leak pattern fixed earlier for students/schedules.
        if user.role == "faculty" and user.faculty_type in ("part_time", "full_time"):
            return qs.filter(faculty__user=user)
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(faculty__user__department__in=user.departments)
        # Anything else (e.g. a Student account) gets nothing -- this is
        # faculty-facing data, not something every authenticated user should see.
        return qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        # Only part-time/full-time faculty actually have a faculty_profile to
        # attach to -- a Student or Registrar hitting this endpoint used to hit
        # an unhandled RelatedObjectDoesNotExist (500) instead of a clean 403.
        if not (user.role == "faculty" and user.faculty_type in ("part_time", "full_time")):
            raise PermissionDenied("Only part-time or full-time faculty may submit availability.")
        serializer.save(faculty=user.faculty_profile)


class AbsenceViewSet(viewsets.ModelViewSet):
    """Faculty absence records -- also the landing point for historical absence
    data requested from IT (2021-2026)."""
    queryset = Absence.objects.select_related("faculty__user").all()
    serializer_class = AbsenceSerializer
    permission_classes = [ReadOnlyOrRegistrarDean]

    def get_queryset(self):
        user = self.request.user
        qs = Absence.objects.select_related("faculty__user")
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(faculty__user__department__in=user.departments)
        if user.role == "faculty":
            return qs.filter(faculty__user=user)
        return qs.none()

    def perform_create(self, serializer):
        _check_dean_faculty_scope(self.request.user, serializer.validated_data["faculty"].user)
        serializer.save()

    def perform_update(self, serializer):
        faculty = serializer.validated_data.get("faculty", self.get_object().faculty)
        _check_dean_faculty_scope(self.request.user, faculty.user)
        serializer.save()


class WorkloadRecordViewSet(viewsets.ModelViewSet):
    """Per-faculty, per-semester total hours + overload flag -- also the landing
    point for historical workload data requested from IT (2021-2026)."""
    queryset = WorkloadRecord.objects.select_related("faculty__user").all()
    serializer_class = WorkloadRecordSerializer
    permission_classes = [ReadOnlyOrRegistrarDean]

    def get_queryset(self):
        user = self.request.user
        qs = WorkloadRecord.objects.select_related("faculty__user")
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(faculty__user__department__in=user.departments)
        if user.role == "faculty":
            return qs.filter(faculty__user=user)
        return qs.none()

    def perform_create(self, serializer):
        _check_dean_faculty_scope(self.request.user, serializer.validated_data["faculty"].user)
        serializer.save()

    def perform_update(self, serializer):
        faculty = serializer.validated_data.get("faculty", self.get_object().faculty)
        _check_dean_faculty_scope(self.request.user, faculty.user)
        serializer.save()


class CoverageSuggestionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only view of what engine.suggest_substitute_view generated -- the
    actual suggest/apply actions live under /api/engine/ since they need the
    CSP engine's find_substitute(); this just lets the Dean/Registrar UI list
    and review what's been suggested so far, per absence."""
    queryset = CoverageSuggestion.objects.select_related(
        "absence__faculty__user", "schedule", "suggested_faculty__user"
    ).order_by("-created_at")
    serializer_class = CoverageSuggestionSerializer
    permission_classes = [ReadOnlyOrRegistrarDean]

    def get_queryset(self):
        user = self.request.user
        qs = CoverageSuggestion.objects.select_related(
            "absence__faculty__user", "schedule", "suggested_faculty__user"
        ).order_by("-created_at")
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(schedule__section__program__department__in=user.departments)
        return qs.none()
