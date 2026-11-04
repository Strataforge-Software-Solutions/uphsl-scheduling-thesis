"""IT-admin endpoints (the in-app "IT Admin" dashboard). Only IT admins -- role 'admin'
or a Django superuser -- may call these."""
import time

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

User = get_user_model()


def _deny(request):
    if request.user.is_authenticated and request.user.is_it_admin:
        return None
    return Response({"detail": "Only an IT admin can do this."}, status=status.HTTP_403_FORBIDDEN)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def overview(request):
    denied = _deny(request)
    if denied:
        return denied
    from datetime import time as dtime
    from curriculum.models import Program, Subject
    from engine.models import ConflictLog, Log, Schedule, Section, TimeSlot
    from exams.models import ExamSchedule
    from faculty.models import FacultyProfile
    from rooms.models import DepartmentBuilding, Room

    t0 = time.time()
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
    db_ms = round((time.time() - t0) * 1000)

    users = {"registrar": 0, "dean": 0, "full_time": 0, "part_time": 0, "student": 0, "admin": 0}
    for u in User.objects.all():
        if u.is_it_admin:
            users["admin"] += 1
        elif u.role == "faculty":
            users[u.faculty_type or "full_time"] = users.get(u.faculty_type or "full_time", 0) + 1
        else:
            users[u.role] = users.get(u.role, 0) + 1

    status_counts = {"draft": 0, "approved": 0, "published": 0}
    for st in Schedule.objects.values_list("status", flat=True):
        status_counts[st] = status_counts.get(st, 0) + 1

    counts = {
        "programs": Program.objects.count(), "subjects": Subject.objects.count(), "sections": Section.objects.count(),
        "rooms": Room.objects.count(), "time_slots": TimeSlot.objects.count(), "faculty": FacultyProfile.objects.count(),
        "class_rows": sum(status_counts.values()), "exam_rows": ExamSchedule.objects.count(),
    }

    # ---- setup health: things that make generating fail or look wrong ----
    checks = []

    def add(level, text):
        checks.append({"level": level, "text": text})

    if not counts["time_slots"]:
        add("error", "No time slots exist. Run: python manage.py seed_timeslots")
    if not counts["rooms"]:
        add("error", "No rooms exist. Import them with import_gti_rooms / add_demo_rooms.")
    if not counts["faculty"]:
        add("error", "No faculty exist, so no class can be assigned a teacher.")
    short_slots = TimeSlot.objects.filter(end_time__in=[dtime(h, 30) for h in range(7, 21)]).exists()
    if not short_slots and Program.objects.filter(name__icontains="nursing", subjects__isnull=False).exists():
        add("warn", "Nursing has a curriculum but there are no 30-minute time slots. Run: python manage.py seed_timeslots")
    deans = [u for u in User.objects.filter(role="faculty", faculty_type="dean")]
    covered = {d for u in deans for d in u.departments}
    for prog in Program.objects.all():
        n_sub = Subject.objects.filter(program=prog).count()
        n_sec = Section.objects.filter(program=prog).count()
        if n_sub and not n_sec:
            add("error", f"{prog.name} has {n_sub} subjects but no sections.")
        elif n_sec and not n_sub:
            add("warn", f"{prog.name} has sections but no subjects (no curriculum yet).")
        elif not n_sub and not n_sec:
            add("info", f"{prog.name} has no curriculum yet.")
        if prog.department not in covered:
            add("warn", f"No dean is assigned to '{prog.department}' ({prog.name}).")
        if n_sec and Section.objects.filter(program=prog, student_count=40).count() == n_sec:
            add("info", f"{prog.name}: every section still has the default 40 students. Set the real counts.")
    for d in sorted({p.department for p in Program.objects.all()}):
        if not DepartmentBuilding.objects.filter(department=d).exists():
            add("info", f"No preferred building set for '{d}' (Django admin > Department buildings).")
    stray = Section.objects.exclude(semester__in=["1st Sem", "2nd Sem"]).values_list("semester", flat=True).distinct()
    if stray:
        add("warn", f"Odd semester labels found: {', '.join(sorted(set(stray)))}. Run: python manage.py fix_semester_labels --apply")
    if not checks:
        add("ok", "Everything looks set up.")

    logs = [{"when": lg.timestamp.isoformat(), "who": (lg.user.username if lg.user else "—"), "action": lg.action, "text": lg.details[:300]}
            for lg in Log.objects.select_related("user").order_by("-timestamp")[:200]]
    conflicts = ConflictLog.objects.count()

    return Response({
        "db": {"engine": connection.vendor, "latency_ms": db_ms},
        "users": users, "counts": counts, "schedule_status": status_counts, "conflict_log_entries": conflicts,
        "checks": checks, "recent_logs": logs,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def clear_generated(request):
    """Body: {scope: 'classes'|'exams', program_id?, year_level?, semester?, include_approved?, apply?}
    Without apply=true it only reports how many rows would be removed."""
    denied = _deny(request)
    if denied:
        return denied
    from engine.models import Schedule
    from exams.models import ExamSchedule

    d = request.data
    scope = d.get("scope")
    if scope not in ("classes", "exams"):
        return Response({"detail": "scope must be 'classes' or 'exams'."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        program_id = int(d["program_id"]) if d.get("program_id") else None
    except (TypeError, ValueError):
        return Response({"detail": "program_id must be a number."}, status=status.HTTP_400_BAD_REQUEST)
    apply = bool(d.get("apply"))
    kept = 0
    if scope == "classes":
        qs = Schedule.objects.all()
        if d.get("year_level"):
            qs = qs.filter(section__year_level=d["year_level"])
        if d.get("semester"):
            qs = qs.filter(section__semester=d["semester"])
        if program_id:
            qs = qs.filter(section__program_id=program_id)
        if not d.get("include_approved"):
            kept = qs.exclude(status="draft").count()
            qs = qs.filter(status="draft")
    else:
        qs = ExamSchedule.objects.all()
        if d.get("semester"):
            qs = qs.filter(section__semester=d["semester"])
        if d.get("year_level"):
            qs = qs.filter(section__year_level=d["year_level"])
        if program_id:
            qs = qs.filter(section__program_id=program_id)
    ids = list(qs.values_list("pk", flat=True))
    if apply and ids:
        with transaction.atomic():
            qs.model.objects.filter(pk__in=ids).delete()
            from engine.housekeeping import cleanup_after_delete
            cleanup_after_delete()
    return Response({"count": len(ids), "kept_approved": kept, "applied": apply})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def set_active(request):
    denied = _deny(request)
    if denied:
        return denied
    user = User.objects.filter(username=request.data.get("username", "")).first()
    if not user:
        return Response({"detail": "No such account."}, status=status.HTTP_404_NOT_FOUND)
    if user.pk == request.user.pk:
        return Response({"detail": "You cannot disable your own account."}, status=status.HTTP_400_BAD_REQUEST)
    user.is_active = bool(request.data.get("active"))
    user.save(update_fields=["is_active"])
    return Response({"detail": f"{user.username} is now {'active' if user.is_active else 'disabled (cannot log in)'}."})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def set_dean_departments(request):
    """Body: {username, extra_departments: ["Dept A", ...]} -- one dean heading several departments."""
    denied = _deny(request)
    if denied:
        return denied
    dean = User.objects.filter(username=request.data.get("username", ""), role="faculty", faculty_type="dean").first()
    if not dean:
        return Response({"detail": "That account is not a dean."}, status=status.HTTP_404_NOT_FOUND)
    extras = [str(x).strip() for x in (request.data.get("extra_departments") or []) if str(x).strip() and str(x).strip() != dean.department]
    dean.extra_departments = ";".join(dict.fromkeys(extras))
    dean.save(update_fields=["extra_departments"])
    return Response({"detail": f"{dean.username} now covers: {' + '.join(dean.departments)}", "departments": dean.departments})
