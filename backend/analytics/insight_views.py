"""New read-only insight endpoints (GET only). Roles are enforced here, on the server. The existing analytics views are unchanged."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import insights


def _admin_only(request):
    if request.user.is_authenticated and request.user.is_it_admin:
        return None
    return Response({"detail": "Only an IT admin can see this."}, status=status.HTTP_403_FORBIDDEN)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_health(request):
    """GET /api/analytics/admin/health/?semester= -- unplaced classes, open conflicts, rooms with no department,
    faculty with no specialization, sections with no curriculum."""
    return _admin_only(request) or Response(insights.admin_health(semester=request.query_params.get("semester") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_accounts(request):
    """GET /api/analytics/admin/accounts/ -- accounts never signed in, inactive accounts, duplicate e-mails."""
    return _admin_only(request) or Response(insights.admin_accounts())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_audit(request):
    """GET /api/analytics/admin/audit/?category=&limit= -- who approved / published / removed / generated what and when."""
    try:
        limit = max(1, min(int(request.query_params.get("limit") or 300), 1000))
    except ValueError:
        limit = 300
    return _admin_only(request) or Response(insights.admin_audit(limit=limit, category=request.query_params.get("category") or None))


# ----------------------------------------------------------------------------------------------- Stage 2: Deans
class _Denied(Exception):
    pass


def college_scope(request):
    """Which colleges a request may see. A Dean: only their own (asking for another college -> 403). The IT admin and the Registrar
    (read-only, all colleges): every college, or the one asked for with ?department=. Everyone else: no access.
    Returns a list of departments, or None for 'all colleges'."""
    u, asked = request.user, (request.query_params.get("department") or "").strip()
    if u.role == "faculty" and u.faculty_type == "dean":
        own = list(u.departments or [])
        if asked:
            if asked not in own:
                raise _Denied("You can only see your own college.")
            return [asked]
        return own
    if u.is_it_admin or u.role == "registrar":
        return [asked] if asked else None
    raise _Denied("Only a Dean, the Registrar or the IT admin can see this.")


def _pid(q):
    v = q.get("program_id")
    return int(v) if v and str(v).isdigit() else None


def _college_call(request, fn):
    try:
        deps = college_scope(request)
    except _Denied as e:
        return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
    q = request.query_params
    return Response(fn(deps, q.get("semester") or None, q))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dean_readiness(request):
    """GET /api/analytics/dean/readiness/?semester=&program_id=&kind=major|minor|all&department="""
    def run(deps, sem, q):
        pid = q.get("program_id")
        return insights.dean_readiness(departments=deps, semester=sem, kind=q.get("kind") or "major",
                                       program_id=int(pid) if pid and pid.isdigit() else None, school_year=q.get("school_year") or None)
    return _college_call(request, run)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dean_faculty_fit(request):
    """GET /api/analytics/dean/faculty-fit/?semester=&department="""
    return _college_call(request, lambda deps, sem, q: insights.dean_faculty_fit(departments=deps, semester=sem, program_id=_pid(q),
                                                                                  school_year=q.get("school_year") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dean_lab_capacity(request):
    """GET /api/analytics/dean/lab-capacity/?semester=&department="""
    return _college_call(request, lambda deps, sem, q: insights.dean_lab_capacity(departments=deps, semester=sem, program_id=_pid(q),
                                                                                   school_year=q.get("school_year") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dean_load_bands(request):
    """GET /api/analytics/dean/load-bands/?semester=&under_pct=50&department="""
    def run(deps, sem, q):
        try:
            pct = max(1, min(int(q.get("under_pct") or 50), 100))
        except ValueError:
            pct = 50
        return insights.dean_load_bands(departments=deps, semester=sem, under_pct=pct, program_id=_pid(q))
    return _college_call(request, run)


# ----------------------------------------------------------------------------------------------- Stage 3: Registrar
def _registrar_only(request):
    u = request.user
    if u.is_authenticated and (u.role == "registrar" or u.is_it_admin):
        return None
    return Response({"detail": "Only the Registrar or the IT admin can see this."}, status=status.HTTP_403_FORBIDDEN)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def registrar_gened_coverage(request):
    """GET /api/analytics/registrar/gened-coverage/?semester=&department= -- Gen Ed coverage and what sharing saves."""
    q = request.query_params
    return _registrar_only(request) or Response(insights.registrar_gened_coverage(
        semester=q.get("semester") or None, departments=[q["department"]] if q.get("department") else None, program_id=_pid(q),
        school_year=q.get("school_year") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def registrar_dependencies(request):
    """GET /api/analytics/registrar/dependencies/?semester= -- majors blocked by Gen Ed; shared groups waiting for confirmation."""
    q = request.query_params
    return _registrar_only(request) or Response(insights.registrar_dependencies(
        semester=q.get("semester") or None, departments=[q["department"]] if q.get("department") else None, program_id=_pid(q)))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def room_heatmap(request):
    """GET /api/analytics/room-heatmap/?semester=&room_type=&department= -- rooms booked per day and hour.
    Registrar / IT admin: every college; a Dean: the classes of their own college only."""
    return _college_call(request, lambda deps, sem, q: insights.room_heatmap(semester=sem, departments=deps, room_type=q.get("room_type") or None,
                                                                              program_id=_pid(q), school_year=q.get("school_year") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def capacity_vs_enrollment(request):
    """GET /api/analytics/capacity/?semester=&department= -- classes over room capacity or under 50% full (same scope rules)."""
    return _college_call(request, lambda deps, sem, q: insights.capacity_vs_enrollment(semester=sem, departments=deps, program_id=_pid(q),
                                                                                        school_year=q.get("school_year") or None))


# ----------------------------------------------------------------------------------------------- Stage 4: SHS / JHS principals
def _basic_ed_call(request, fn):
    """A principal sees only their own level (asking for the other -> 403); the IT admin says which with ?level=SHS|JHS.
    Uses basic_ed.permissions (the same rule as every Basic Ed screen)."""
    from basic_ed.permissions import allowed_levels, level_of
    from basic_ed.views import active_year
    if not allowed_levels(request.user):
        return Response({"detail": "Only a principal (own level) or the IT admin can see this."}, status=status.HTTP_403_FORBIDDEN)
    level = level_of(request)                     # raises 403 for the other level, 400 when the admin did not say which
    return Response(fn(level, active_year(request), request.query_params.get("period") or None))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def basic_ed_feasibility(request):
    """GET /api/analytics/basic-ed/feasibility/?level=&year=&period= -- periods that fit in each grade's day after the breaks."""
    def run(level, ay, period):
        if ay is None:
            return {"level": level, "configured": False, "grades": [], "period": None, "note": "No academic year is set up yet."}
        return insights.basic_ed_feasibility(level, ay, period)
    return _basic_ed_call(request, run)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def basic_ed_completeness(request):
    """GET /api/analytics/basic-ed/completeness/?level=&year=&period= -- missing subjects or teachers per grade and strand."""
    def run(level, ay, period):
        if ay is None:
            return {"level": level, "period": None, "periods_with_timetables": [], "groups": [], "note": "No academic year is set up yet."}
        return insights.basic_ed_completeness(level, ay, period)
    return _basic_ed_call(request, run)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def basic_ed_absences(request):
    """GET /api/analytics/basic-ed/absences/?level= -- absence impact (not recorded for SHS / JHS: says so)."""
    return _basic_ed_call(request, lambda level, ay, period: insights.basic_ed_absences(level))


# ----------------------------------------------------------------------------------------------- Stage 5: filters and trend
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def filter_options(request):
    """GET /api/analytics/filters/ -- school years, semesters, colleges and programs this user may filter by (same scope as the cards)."""
    return _college_call(request, lambda deps, sem, q: insights.filter_options(departments=deps))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def basic_ed_run_trend(request):
    """GET /api/analytics/basic-ed/run-trend/?level=&year= -- efficiency and conflicts of every stored SHS / JHS generation run."""
    return _basic_ed_call(request, lambda level, ay, period: insights.basic_ed_run_trend(level, ay) if ay is not None
                          else {"level": level, "academic_year": "", "runs": [], "years": []})
