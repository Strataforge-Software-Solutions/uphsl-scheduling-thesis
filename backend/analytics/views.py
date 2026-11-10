from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .services import compute_analytics, compute_faculty_patterns, historical_subjects_at


def _can_view_analytics(user):
    return bool(user.is_it_admin or user.role == "registrar"
                or (user.role == "faculty" and user.faculty_type == "dean"))


def _denied():
    return Response({"detail": "Only the Registrar, a Dean, or an IT admin can view this analytics data."}, status=403)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_view(request):
    user = request.user
    if not _can_view_analytics(user):
        return _denied()
    # Registrar sees institution-wide; Dean sees own department only.
    department = None
    if user.role == "faculty" and user.faculty_type == "dean":
        department = user.departments
    return Response(compute_analytics(department=department, semester=request.query_params.get("semester") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def faculty_patterns_view(request, faculty_id):
    """Historical day/time-of-day teaching patterns for one faculty, mined
    from the 2021-2026 imported class records. See
    analytics.services.compute_faculty_patterns."""
    if not _can_view_analytics(request.user):
        return _denied()
    from faculty.models import FacultyProfile
    profile = FacultyProfile.objects.filter(pk=faculty_id).select_related("user").first()
    if profile is None:
        return Response({"detail": "Faculty member not found."}, status=404)
    if (request.user.role == "faculty" and request.user.faculty_type == "dean"
            and profile.user.department not in request.user.departments):
        return _denied()
    return Response(compute_faculty_patterns(profile.pk))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def historical_lookup_view(request):
    """
    GET /api/analytics/historical-lookup/?day=Mon&start_time=08:00&end_time=09:00&room=Room 201

    "What subject was historically scheduled at this day+time (+room)?" --
    used as a reference when manually placing a class or an exam, so the
    Registrar/Dean isn't guessing. Backed by the imported 2021-2026
    HistoricalClassRecord data. day/start_time are required; end_time and
    room are optional refinements.
    """
    # Historical rows are denormalized imports without a reliable department
    # field, so they cannot be safely scoped to a Dean's college.
    if not (request.user.is_it_admin or request.user.role == "registrar"):
        return _denied()
    day = request.query_params.get("day")
    start_time = request.query_params.get("start_time")
    end_time = request.query_params.get("end_time")
    room = request.query_params.get("room")

    if not day or not start_time:
        return Response({"detail": "day and start_time are required."}, status=400)

    results = historical_subjects_at(day=day, start_time=start_time, end_time=end_time, room_name=room)
    return Response({"count": len(results), "results": results})
