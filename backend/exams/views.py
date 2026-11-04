from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from datetime import datetime, timedelta

from curriculum.models import Subject, Program
from engine.models import Section
from .models import ExamSchedule
from .serializers import ExamScheduleSerializer
from .permissions import CanEditExamSchedule
from .services import generate_exam_schedule, generate_exam_schedule_detailed


class ExamScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ExamScheduleSerializer
    permission_classes = [CanEditExamSchedule]

    def get_queryset(self):
        qs = ExamSchedule.objects.select_related(
            "subject", "section", "section__program", "proctor__user", "room", "timeslot")
        user = self.request.user
        if user.role == "registrar":
            return qs.filter(subject__classification="minor")   # the Registrar works with minor subjects only
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(subject__program__department__in=user.departments)
        if user.role == "faculty":  # full-time/part-time proctoring
            return qs.filter(proctor__user=user)
        if user.role == "student":
            return qs.filter(section__in=user.enrolled_sections.all()) if hasattr(user, "enrolled_sections") else qs.none()
        return qs.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_exam_pdf(request):
    """GET /api/exams/export-pdf/?exam_period=&semester=
    Registrar prints the MINOR-subject exam schedule; a Dean prints the MAJOR-subject exam schedule
    of their own college(s) (even though minors are visible on the Dean's screen)."""
    from django.http import HttpResponse
    from .pdf_export import build_exam_pdf
    user = request.user
    qs = ExamSchedule.objects.select_related(
        "subject", "section", "section__program", "proctor__user", "room", "timeslot")
    if user.role == "registrar":
        qs = qs.filter(subject__classification="minor")
        prepared_title, departments = "Registrar", []
    elif user.role == "faculty" and user.faculty_type == "dean":
        qs = qs.filter(subject__classification="major", subject__program__department__in=user.departments)
        prepared_title, departments = "Dean", list(user.departments)
    else:
        return Response({"detail": "Only the Registrar or a Dean can print the exam schedule."},
                        status=status.HTTP_403_FORBIDDEN)
    period = request.query_params.get("exam_period")
    semester = request.query_params.get("semester")
    if period:
        qs = qs.filter(exam_period=period)
    if semester:
        qs = qs.filter(section__semester=semester)
    rows = list(qs)
    if not rows:
        return Response({"detail": "No exam entries found to print for these filters."}, status=status.HTTP_404_NOT_FOUND)
    pdf = build_exam_pdf(rows, exam_period=period, semester=semester, prepared_by_user=user,
                         prepared_title=prepared_title, departments=departments)
    resp = HttpResponse(pdf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="exam_schedule.pdf"'
    return resp


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_exam_schedule_view(request):
    """
    Body: {
      "semester", "exam_period", "exam_start_date": "YYYY-MM-DD",
      "exam_end_date": "YYYY-MM-DD", "program_id" (optional)
    }

    Two changes from the old single-date/single-year-level version, both per
    request:
      1. No `year_level` anymore -- a real exam week covers every year level
         (1st-4th) at once, so this now schedules ALL year levels for the
         matching subjects/sections in one run instead of requiring one
         Generate click per year level.
      2. `exam_date` (one day) is now `exam_start_date`/`exam_end_date` (a
         real exam-week range) -- exams are spread across the days in that
         range, round-robin per subject, instead of being crammed onto a
         single date.

    Registrar generates minor-subject exams across EVERY program/department
    in one run; Dean generates major-subject exams across every program in
    their OWN department in one run. `program_id` stays optional -- passing
    it narrows the run to just that one program.
    """
    user = request.user
    program_id = request.data.get("program_id") or None
    semester = request.data.get("semester")
    exam_period = request.data.get("exam_period")
    start_str = request.data.get("exam_start_date")
    end_str = request.data.get("exam_end_date")

    if not all([semester, exam_period, start_str, end_str]):
        return Response({"detail": "semester, exam_period, exam_start_date, exam_end_date are all required."},
                         status=status.HTTP_400_BAD_REQUEST)

    try:
        exam_start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        exam_end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    except ValueError:
        return Response({"detail": "exam_start_date/exam_end_date must be YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

    if exam_end_date < exam_start_date:
        return Response({"detail": "exam_end_date cannot be before exam_start_date."}, status=status.HTTP_400_BAD_REQUEST)

    if (exam_end_date - exam_start_date).days > 30:
        return Response({"detail": "Exam date range is too wide (max 30 days) -- pick a tighter exam-week window."},
                         status=status.HTTP_400_BAD_REQUEST)

    exam_dates = [exam_start_date + timedelta(days=i) for i in range((exam_end_date - exam_start_date).days + 1)]

    if user.role == "registrar":
        classification = "minor"
        programs = Program.objects.all()
    elif user.role == "faculty" and user.faculty_type == "dean":
        classification = "major"
        programs = Program.objects.filter(department__in=user.departments)
    else:
        return Response({"detail": "Only Registrar or Dean can generate exam schedules."}, status=status.HTTP_403_FORBIDDEN)

    if program_id:
        try:
            programs = programs.filter(id=int(program_id))
        except (TypeError, ValueError):
            return Response({"detail": "program_id must be a number."}, status=status.HTTP_400_BAD_REQUEST)

    programs = list(programs)
    if not programs:
        detail = ("No programs found." if not program_id else "No matching program found.")
        if user.role == "faculty" and user.faculty_type == "dean":
            detail = "No programs found in your department."
        return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

    school_year = f"{exam_start_date.year}-{exam_start_date.year + 1}"
    from rooms.models import DepartmentBuilding
    dept_building = {d.department: d.building for d in DepartmentBuilding.objects.all()}
    created_total, unresolved_total, skipped_programs = [], [], []

    try:
        # ONE run over every program: a Gen Ed subject taken by several programs gets one common date and time (each section in
        # its own room), exactly like the college's exam-week schedule.
        all_subjects, all_sections = [], []
        for program in programs:
            subs = list(Subject.objects.filter(program=program, semester=semester, classification=classification))
            secs = list(Section.objects.filter(program=program, semester=semester))
            if not subs or not secs:
                skipped_programs.append(program.name)      # nothing to schedule that term: skipped quietly, not a failure
                continue
            all_subjects += subs
            all_sections += secs
        result = {"created": [], "unresolved": [], "pending": [], "capacity_warnings": []}
        if all_subjects:
            from django.db import transaction as _tx
            from engine import locks as _locks
            with _tx.atomic():
                if not _locks.try_lock("exams"):
                    return Response({"detail": _locks.BUSY}, status=status.HTTP_409_CONFLICT)
                result = generate_exam_schedule_detailed(
                    subjects=all_subjects, sections=all_sections, exam_period=exam_period, exam_dates=exam_dates,
                    school_year=school_year, requesting_user=user, dept_building=dept_building)
        created_total, unresolved_total = result["created"], result["unresolved"]
        pending_total, capacity_warnings = result["pending"], result["capacity_warnings"]
    except Exception as exc:
        from engine import locks as _locks
        return Response(
            {"detail": _locks.explain(exc) or f"Exam generation hit an unexpected error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Let each assigned proctor know they have exam duty, instead of them
    # only finding out by happening to check the Exam Schedule tab.
    if created_total:
        from notifications.models import Notification
        proctor_counts = {}
        for exam in created_total:
            key = exam.proctor.user_id
            proctor_counts[key] = proctor_counts.get(key, 0) + 1
        Notification.objects.bulk_create([
            Notification(
                recipient_id=user_id, notif_type="exam_assignment",
                message=f"You've been assigned to proctor {n} {exam_period} exam period{'s' if n != 1 else ''} "
                        f"between {exam_start_date} and {exam_end_date}.",
            )
            for user_id, n in proctor_counts.items()
        ])

    # Re-check what is now saved: every subject of every section has an exam, no room is double-booked, the room rules hold.
    validation = {}
    try:
        from .room_rules import check_exams
        expected = set()
        for program in programs:
            subs = list(Subject.objects.filter(program=program, semester=semester, classification=classification))
            for sec in Section.objects.filter(program=program, semester=semester):
                expected |= {(s.id, sec.id) for s in subs if s.year_level == sec.year_level}
        saved = list(ExamSchedule.objects.filter(exam_period=exam_period, school_year=school_year,
                                                 section__semester=semester, subject__classification=classification)
                     .select_related("subject", "section__program", "room", "timeslot", "proctor__user"))
        validation = check_exams(saved, expected)
        names = {(s.id, c.id): f"{s.code} - {s.title} ({c.name})"
                 for s in Subject.objects.filter(id__in={a for a, _ in expected})
                 for c in Section.objects.filter(id__in={b for _, b in expected})}
        validation["missing"] = [names.get((m["subject_id"], m["section_id"]), str(m)) for m in validation["missing"]]
    except Exception as exc:                       # informational; never fail a finished generation
        validation = {"error": str(exc)}

    note = ""
    if not created_total and not unresolved_total:
        note = (f"Nothing to schedule: no {classification} subjects with sections were found for {semester}.")
    return Response({
        "detail": note,
        "created_count": len(created_total),
        "unresolved": unresolved_total,
        "status": "complete" if not unresolved_total else "partial",
        "programs_covered": len(programs) - len(skipped_programs),
        "programs_skipped": skipped_programs,
        "validation": validation,
        "pending": pending_total,
        "capacity_warnings": capacity_warnings,
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resolve_exam_conflicts_view(request):
    """POST {semester, exam_period, exam_start_date, exam_end_date, items: [{subject_id, section_id}], apply: bool}
    Registrar: places blocked Gen Ed exams and asks the Dean(s) to move the program exams in the way.
    Dean: changes the date/hour of their OWN program exams that block Gen Ed exams (items may be empty = all blocked ones)."""
    from .resolve import resolve
    u = request.user
    if not (u.role == "registrar" or (u.role == "faculty" and u.faculty_type == "dean")):
        return Response({"detail": "Only the Registrar or a Dean can resolve exam conflicts."}, status=status.HTTP_403_FORBIDDEN)
    d = request.data
    try:
        start = datetime.strptime(d.get("exam_start_date", ""), "%Y-%m-%d").date()
        end = datetime.strptime(d.get("exam_end_date", ""), "%Y-%m-%d").date()
    except ValueError:
        return Response({"detail": "exam_start_date/exam_end_date must be YYYY-MM-DD."}, status=400)
    items = [i for i in (d.get("items") or []) if i.get("subject_id") and i.get("section_id")]
    is_dean = u.role == "faculty" and u.faculty_type == "dean"
    if not (d.get("semester") and d.get("exam_period") and (items or is_dean)) or end < start or (end - start).days > 30:
        return Response({"detail": "semester, exam_period, a valid exam week and at least one exam are required."}, status=400)
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    try:
        return Response(resolve(u, semester=d["semester"], exam_period=d["exam_period"], dates=dates,
                                school_year=f"{start.year}-{start.year + 1}", items=items, apply=bool(d.get("apply"))))
    except Exception as exc:
        return Response({"detail": f"Could not resolve the exam conflicts: {exc}"}, status=500)
