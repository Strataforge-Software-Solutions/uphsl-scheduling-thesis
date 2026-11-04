import csv
import io
from collections import defaultdict
from datetime import time as dtime

from django.db import transaction
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import models as m
from . import serializers as s
from .engine import eligible, to_min, to_time
from .permissions import IsLevelManager, allowed_levels, level_of, check_level
from .services import (generate, instructional_days, log, refresh_validation, run_report, terms_for, validate_curriculum,
                       grading_period_obj)

LEVEL_PARAM = "level"


def active_year(request=None):
    ay = None
    if request is not None and request.query_params.get("year"):
        ay = m.AcademicYear.objects.filter(label=request.query_params["year"]).first()
    return ay or m.AcademicYear.objects.filter(is_active=True).first() or m.AcademicYear.objects.order_by("-label").first()


class LevelViewSet(viewsets.ModelViewSet):
    """Base: every row belongs to one school level, and a request only ever sees/edits that level."""
    permission_classes = [IsLevelManager]
    has_level = True
    has_year = False

    def level(self):
        return level_of(self.request)

    def get_queryset(self):
        qs = super().get_queryset()
        lv = self.level()
        if self.has_level:
            qs = qs.filter(level=lv)
        if self.has_year:
            ay = active_year(self.request)
            if ay and not self.request.query_params.get("all_years"):
                qs = qs.filter(academic_year=ay)
        return qs

    def perform_create(self, serializer):
        extra = {}
        if self.has_level:
            extra["level"] = self.level()
        if self.has_year and "academic_year" not in serializer.validated_data:
            extra["academic_year"] = active_year(self.request)
        serializer.save(**extra)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        try:
            ctx["level"] = self.level()
        except Exception:
            pass
        return ctx


class GradeWindowViewSet(LevelViewSet):
    queryset = m.GradeWindow.objects.all()
    serializer_class = s.GradeWindowSerializer


class StrandViewSet(viewsets.ModelViewSet):
    """SHS only; Academic / TECHPRO strands."""
    permission_classes = [IsLevelManager]
    queryset = m.Strand.objects.all()
    serializer_class = s.StrandSerializer


class SectionViewSet(LevelViewSet):
    queryset = m.Section.objects.select_related("strand", "adviser__user", "home_room")
    serializer_class = s.SectionSerializer
    has_year = True

    def _check_refs(self, data, lv):
        for key, model in (("adviser", m.Faculty), ("home_room", m.Room)):
            obj = data.get(key)
            if obj is not None and obj.level != lv:
                raise ValidationError({key: "That record belongs to the other school level."})

    def perform_create(self, ser):
        self._check_refs(ser.validated_data, self.level())
        if ser.validated_data.get("strand") and self.level() != "SHS":
            raise ValidationError({"strand": "Only SHS sections have a strand."})
        super().perform_create(ser)

    def perform_update(self, ser):
        self._check_refs(ser.validated_data, self.level())
        ser.save()


class RoomViewSet(LevelViewSet):
    queryset = m.Room.objects.all()
    serializer_class = s.RoomSerializer

    def _check(self, data):
        cfg = m.SchoolLevelConfig.objects.get(level=self.level())
        b = data.get("building", getattr(self.get_object(), "building", None) if self.kwargs.get("pk") else None)
        floor = data.get("floor")
        if b and b != cfg.building:
            raise ValidationError({"building": f"{self.level()} rooms must be in {cfg.building}."})
        if cfg.floor is not None and floor is not None and floor != cfg.floor:
            raise ValidationError({"floor": f"{self.level()} classrooms are on floor {cfg.floor} of {cfg.building} only."})

    def perform_create(self, ser):
        self._check(ser.validated_data)
        super().perform_create(ser)

    def perform_update(self, ser):
        self._check(ser.validated_data)
        ser.save()


class CurriculumSourceViewSet(LevelViewSet):
    queryset = m.CurriculumSource.objects.all()
    serializer_class = s.CurriculumSourceSerializer
    has_year = True


class CurriculumSubjectViewSet(LevelViewSet):
    queryset = m.CurriculumSubject.objects.select_related("strand", "source")
    serializer_class = s.CurriculumSubjectSerializer
    has_year = True

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("grade"):
            qs = qs.filter(grade_level=p["grade"])
        if p.get("period"):
            qs = qs.filter(grading_period__in=[0, p["period"]])
        if p.get("strand"):
            qs = qs.filter(strand__code=p["strand"])
        if p.get("active", "1") == "1":
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, inst):
        # Curriculum lines are retired, not deleted, so past timetables keep their subject.
        inst.is_active = False
        inst.save(update_fields=["is_active"])


class FacultyViewSet(LevelViewSet):
    queryset = m.Faculty.objects.select_related("user", "strand").prefetch_related("availability")
    serializer_class = s.FacultySerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        hours = defaultdict(float)
        runs = m.ScheduleRun.objects.filter(level=self.level()).exclude(status="superseded")
        for e in m.ScheduleEntry.objects.filter(run__in=runs, teacher__isnull=False):
            hours[e.teacher_id] += (to_min(e.end_time) - to_min(e.start_time)) / 60
        ctx["hours"] = {k: round(v, 1) for k, v in hours.items()}
        return ctx

    @action(detail=True, methods=["post"], url_path="availability")
    def set_availability(self, request, pk=None):
        fac = self.get_object()
        rows = request.data.get("rows", [])
        ser = s.AvailabilitySerializer(data=rows, many=True)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            fac.availability.all().delete()
            m.Availability.objects.bulk_create([m.Availability(faculty=fac, **r) for r in ser.validated_data])
        return Response(s.FacultySerializer(fac, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        fac = self.get_object()
        fac.user.set_password(fac.employee_id)
        fac.user.must_change_password = True
        fac.user.save()
        return Response({"detail": f"Password reset to the employee ID for {fac.full_name}."})


class AssignmentViewSet(LevelViewSet):
    queryset = m.TeachingAssignment.objects.select_related("faculty__user", "section", "subject")
    serializer_class = s.AssignmentSerializer
    has_level = False

    def get_queryset(self):
        return super().get_queryset().filter(section__level=self.level())

    def perform_create(self, ser):
        d = ser.validated_data
        lv = self.level()
        if d["faculty"].level != lv or d["section"].level != lv or d["subject"].level != lv:
            raise ValidationError({"detail": "Teacher, section and subject must all belong to the same school level."})
        if not eligible(d["faculty"], d["subject"]):
            raise ValidationError({"detail": f"{d['faculty'].full_name} is not qualified for {d['subject'].code}."})
        ser.save()


class CalendarEventViewSet(LevelViewSet):
    queryset = m.CalendarEvent.objects.all()
    serializer_class = s.CalendarEventSerializer
    has_year = True


class CalendarPeriodViewSet(LevelViewSet):
    queryset = m.CalendarPeriod.objects.prefetch_related("term_links")
    serializer_class = s.CalendarPeriodSerializer
    has_year = True

    def get_queryset(self):
        return super().get_queryset().exclude(kind="quarter").exclude(kind="semester", level="JHS")

    @action(detail=True, methods=["post"], url_path="terms")
    def set_terms(self, request, pk=None):
        """Configure which terms fall inside this semester (SHS Grade 12)."""
        gp = self.get_object()
        if gp.kind != "semester":
            raise ValidationError({"detail": "Only a semester can be linked to terms (JHS and Grade 11 work in terms directly)."})
        ids = request.data.get("terms", [])
        terms = m.CalendarPeriod.objects.filter(id__in=ids, kind="term", level=gp.level, academic_year=gp.academic_year)
        with transaction.atomic():
            m.PeriodMapping.objects.filter(grading_period=gp).delete()
            m.PeriodMapping.objects.bulk_create([m.PeriodMapping(grading_period=gp, term=t) for t in terms])
            gp.is_placeholder = False
            gp.save(update_fields=["is_placeholder"])
        return Response(s.CalendarPeriodSerializer(gp).data)


# ----------------------------------------------------------------- overview / config
@api_view(["GET"])
@permission_classes([IsLevelManager])
def overview(request):
    level = level_of(request)
    ay = active_year(request)
    cfg = m.SchoolLevelConfig.objects.get(level=level)
    windows = m.GradeWindow.objects.filter(level=level)
    # terms for everyone; semesters only for SHS (Grade 12). The retired JHS quarters are not shown.
    periods = list(m.CalendarPeriod.objects.filter(level=level, academic_year=ay).exclude(kind="quarter")
                   .exclude(kind="semester", level="JHS").prefetch_related("term_links"))
    runs = m.ScheduleRun.objects.filter(level=level, academic_year=ay).exclude(status="superseded")
    pending = runs.filter(status="submitted").count()
    out = {
        "level": level, "academic_year": ay.label if ay else "", "years": list(m.AcademicYear.objects.values_list("label", flat=True)),
        "config": s.SchoolLevelConfigSerializer(cfg).data,
        "windows": s.GradeWindowSerializer(windows, many=True).data,
        "structure": structure_dict(level, windows.values_list("grade_level", flat=True)),
        "periods": s.CalendarPeriodSerializer(periods, many=True).data,
        "counts": {
            "sections": m.Section.objects.filter(level=level, academic_year=ay, is_active=True).count(),
            "faculty": m.Faculty.objects.filter(level=level, is_active=True).count(),
            "rooms": m.Room.objects.filter(level=level, is_active=True).count(),
            "subjects": m.CurriculumSubject.objects.filter(level=level, academic_year=ay, is_active=True).count(),
            "unverified_subjects": m.CurriculumSubject.objects.filter(level=level, academic_year=ay, is_active=True, is_verified=False).count(),
            "runs": runs.count(), "pending_review": pending,
            "open_conflicts": m.ConflictRecord.objects.filter(run__in=runs, severity="error").count(),
        },
        "runs": s.RunSerializer(runs.order_by("grade_level", "grading_period"), many=True).data,
        "recent": s.EventSerializer(m.ScheduleEvent.objects.filter(run__level=level).order_by("-created_at")[:15], many=True).data,
    }
    return Response(out)


@api_view(["PATCH"])
@permission_classes([IsLevelManager])
def update_config(request):
    level = level_of(request)
    cfg = m.SchoolLevelConfig.objects.get(level=level)
    ser = s.SchoolLevelConfigSerializer(cfg, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save(level=level)
    return Response(ser.data)


@api_view(["GET", "POST"])
@permission_classes([IsLevelManager])
def academic_years(request):
    level_of(request)
    if request.method == "POST":
        ser = s.AcademicYearSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ay = ser.save()
        if ay.is_active:
            m.AcademicYear.objects.exclude(id=ay.id).update(is_active=False)
        return Response(ser.data, status=201)
    return Response(s.AcademicYearSerializer(m.AcademicYear.objects.all(), many=True).data)


# ----------------------------------------------------------------- curriculum tools
from .structure import structure, as_dict as structure_dict   # noqa: E402

TEMPLATE_COLUMNS = ["grade_level", "strand_code", "grading_period", "code", "name", "learning_area", "category", "sessions_per_week",
                    "total_hours", "required_room_type", "specialization", "prerequisite", "verified"]


@api_view(["GET"])
@permission_classes([IsLevelManager])
def curriculum_template(request):
    level = level_of(request)
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{level}_curriculum_template.csv"'
    w = csv.writer(resp)
    w.writerow(TEMPLATE_COLUMNS)
    if level == "SHS":
        w.writerow([11, "STEM", 1, "EXAMPLE-01", "Replace with the official subject name", "Mathematics", "core", 4, 160, "classroom", "Mathematics", "", "no"])
    else:
        w.writerow([7, "", 1, "EXAMPLE-01", "Replace with the official learning area", "Mathematics", "learning_area", 5, "", "classroom", "Mathematics", "", "no"])
    w.writerow([])
    w.writerow(["# category: core | applied | specialized | elective | learning_area | guidance.  grading_period: term 1-3 (JHS and SHS Grade 11) or semester 1-2 (SHS Grade 12); 0 = whole school year (Grade 11 core subjects)."])
    w.writerow(["# required_room_type: classroom | computer_lab | science_lab | workshop | gym.   verified: yes only if the line was copied from an official DepEd document."])
    return resp


@api_view(["POST"])
@permission_classes([IsLevelManager])
def curriculum_import(request):
    """Import a CSV / XLSX in the template format. Nothing is saved if any row is invalid."""
    level = level_of(request)
    ay = active_year(request)
    f = request.FILES.get("file")
    if not f:
        raise ValidationError({"file": "Attach the filled-in template (.csv or .xlsx)."})
    rows = []
    if f.name.lower().endswith(".xlsx"):
        import openpyxl
        ws = openpyxl.load_workbook(f, read_only=True).active
        it = ws.iter_rows(values_only=True)
        head = [str(c or "").strip() for c in next(it)]
        rows = [dict(zip(head, r)) for r in it if any(c not in (None, "") for c in r)]
    else:
        text = f.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    rows = [r for r in rows if str(next(iter(r.values()), "") or "").strip() and not str(next(iter(r.values()), "")).startswith("#")]
    strands = {x.code.upper(): x for x in m.Strand.objects.all()}
    errors, objs = [], []
    seen = set()
    for i, r in enumerate(rows, start=2):
        try:
            grade = int(r.get("grade_level"))
            if (level == "SHS" and grade not in (11, 12)) or (level == "JHS" and grade not in (7, 8, 9, 10)):
                raise ValueError(f"grade {grade} is not a {level} grade")
            code = str(r.get("code") or "").strip()
            name = str(r.get("name") or "").strip()
            if not code or not name:
                raise ValueError("code and name are required")
            sc = str(r.get("strand_code") or "").strip().upper()
            strand = strands.get(sc) if sc else None
            if sc and not strand:
                raise ValueError(f"unknown strand '{sc}'")
            if level == "JHS" and strand:
                raise ValueError("JHS subjects have no strand")
            gp = int(r.get("grading_period") or 0)
            if gp < 0 or gp > structure(level, grade)[1]:
                kind_, n_ = structure(level, grade)
                raise ValueError(f"Grade {grade} has {n_} {kind_}s per school year (use 1-{n_}, or 0 for the whole year); got {gp}")
            spw = int(r.get("sessions_per_week") or 0)
            if spw < 1:
                raise ValueError("sessions_per_week must be at least 1")
            cat = str(r.get("category") or "core").strip()
            if cat not in dict(m.CurriculumSubject.CATEGORIES):
                raise ValueError(f"unknown category '{cat}'")
            rt = str(r.get("required_room_type") or "classroom").strip()
            if rt not in dict(m.Room.TYPES):
                raise ValueError(f"unknown room type '{rt}'")
            key = (strand.id if strand else None, grade, gp, code)
            if key in seen:
                raise ValueError(f"duplicate of an earlier row ({code})")
            seen.add(key)
            th = r.get("total_hours")
            objs.append(m.CurriculumSubject(
                level=level, academic_year=ay, strand=strand, grade_level=grade, grading_period=gp, code=code, name=name,
                learning_area=str(r.get("learning_area") or "").strip(), category=cat, sessions_per_week=spw,
                total_hours=float(th) if th not in (None, "") else None, required_room_type=rt,
                specialization=str(r.get("specialization") or "").strip(), prerequisite=str(r.get("prerequisite") or "").strip(),
                is_verified=str(r.get("verified") or "").strip().lower() in ("yes", "y", "true", "1"),
                verification_note="Imported from file " + f.name))
        except Exception as ex:
            errors.append({"row": i, "message": str(ex)})
    if errors:
        return Response({"imported": 0, "errors": errors}, status=400)
    with transaction.atomic():
        src = m.CurriculumSource.objects.create(level=level, academic_year=ay, title=f"Imported file: {f.name}",
                                                reference=request.data.get("reference", ""), version=request.data.get("version", ""),
                                                notes=f"Imported by {request.user.username}", is_verified=False)
        created = updated = 0
        for o in objs:
            o.source = src
            existing = m.CurriculumSubject.objects.filter(level=level, academic_year=ay, strand=o.strand, grade_level=o.grade_level,
                                                          grading_period=o.grading_period, code=o.code).first()
            if existing:
                for fld in ("name", "learning_area", "category", "sessions_per_week", "total_hours", "required_room_type", "specialization",
                            "prerequisite", "is_verified", "verification_note", "source"):
                    setattr(existing, fld, getattr(o, fld))
                existing.is_active = True
                existing.save()
                updated += 1
            else:
                o.save()
                created += 1
    return Response({"imported": created, "updated": updated, "errors": []})


@api_view(["GET"])
@permission_classes([IsLevelManager])
def curriculum_validate(request):
    level = level_of(request)
    ay = active_year(request)
    gp = int(request.query_params.get("period") or 1)
    grade = request.query_params.get("grade")
    issues = validate_curriculum(level, ay, gp, int(grade) if grade else None)
    return Response({"issues": issues, "errors": sum(1 for i in issues if i["severity"] == "error"),
                     "warnings": sum(1 for i in issues if i["severity"] == "warning")})


# ----------------------------------------------------------------- schedule runs
def _run_for(request, pk):
    run = m.ScheduleRun.objects.select_related("academic_year").filter(pk=pk).first()
    if not run:
        raise ValidationError({"detail": "Schedule not found."})
    check_level(request.user, run.level)
    return run


@api_view(["POST"])
@permission_classes([IsLevelManager])
def generate_view(request):
    level = level_of(request)
    ay = active_year(request)
    gp = int(request.data.get("grading_period") or 1)
    grade = request.data.get("grade_level")
    windows = list(m.GradeWindow.objects.filter(level=level).values_list("grade_level", flat=True))
    grades = [int(grade)] if grade not in (None, "", "all") else sorted(windows)
    if any(g not in windows for g in grades):
        raise ValidationError({"detail": "That grade level is not part of this school level."})
    for g in grades:
        kind_, n_ = structure(level, g)
        if gp < 1 or gp > n_:
            raise ValidationError({"detail": f"Grade {g} has {n_} {kind_}s per school year, so {kind_} {gp} does not exist. "
                                             f"Choose the grade level and its {kind_} again."})
    blockers = []
    for g in grades:
        blockers += [i for i in validate_curriculum(level, ay, gp, g) if i["severity"] == "error"]
    if blockers and not request.data.get("force"):
        return Response({"detail": "Fix the curriculum problems first.", "issues": blockers[:50]}, status=400)
    results = []
    for g in grades:
        run, unresolved = generate(level, ay, gp, g, request.user, request.data.get("note", ""))
        results.append({"run": s.RunSerializer(run).data,
                        "unresolved": [{"section": u["section"].name, "subject": u["subject"].code, "message": u["message"]} for u in unresolved]})
    return Response({"results": results}, status=201)


@api_view(["GET"])
@permission_classes([IsLevelManager])
def runs_list(request):
    level = level_of(request)
    qs = m.ScheduleRun.objects.filter(level=level).select_related("academic_year", "created_by").order_by("-created_at")
    if not request.query_params.get("history"):
        qs = qs.filter(academic_year=active_year(request)).exclude(status="superseded")
    return Response(s.RunSerializer(qs[:200], many=True).data)


@api_view(["GET"])
@permission_classes([IsLevelManager])
def run_detail(request, pk):
    run = _run_for(request, pk)
    entries = run.entries.select_related("section__strand", "teacher__user", "room")
    sec = request.query_params.get("section")
    if sec:
        entries = entries.filter(section_id=sec)
    return Response({
        "run": s.RunSerializer(run).data,
        "entries": s.EntrySerializer(entries, many=True).data,
        "conflicts": s.ConflictSerializer(run.conflicts.select_related("section"), many=True).data,
        "events": s.EventSerializer(run.events.select_related("actor"), many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsLevelManager])
def run_report_view(request, pk):
    run = _run_for(request, pk)
    return Response({"run": s.RunSerializer(run).data, **run_report(run)})


def _editable(run):
    if run.status not in ("draft", "revision_requested"):
        raise ValidationError({"detail": f"A {run.get_status_display().lower()} schedule can't be edited. Request a revision first."})


@api_view(["PATCH", "DELETE"])
@permission_classes([IsLevelManager])
def entry_edit(request, pk):
    entry = m.ScheduleEntry.objects.select_related("run", "section").filter(pk=pk).first()
    if not entry:
        raise ValidationError({"detail": "Period not found."})
    check_level(request.user, entry.run.level)
    run = entry.run
    _editable(run)
    if request.method == "DELETE":
        entry.delete()
        log(run, "entry_removed", request.user, f"{entry.subject_code} {entry.section.name} {entry.day}")
        issues = refresh_validation(run)
        return Response({"issues": issues, "run": s.RunSerializer(run).data})
    d = request.data
    lv = run.level
    if "teacher" in d and d["teacher"]:
        t = m.Faculty.objects.filter(pk=d["teacher"], level=lv).first()
        if not t:
            raise ValidationError({"teacher": "Pick a teacher from this school level."})
        entry.teacher = t
    if "room" in d and d["room"]:
        r = m.Room.objects.filter(pk=d["room"], level=lv).first()
        if not r:
            raise ValidationError({"room": "Pick a room from this school level."})
        entry.room = r
    if "day" in d and d["day"] in dict(m.DAYS):
        entry.day = d["day"]
    for key in ("start_time", "end_time"):
        if d.get(key):
            hh, mm = str(d[key])[:5].split(":")
            setattr(entry, key, dtime(int(hh), int(mm)))
    if entry.end_time <= entry.start_time:
        raise ValidationError({"detail": "End time must be after start time."})
    entry.is_manual = True
    entry.save()
    log(run, "entry_edited", request.user, f"{entry.subject_code} {entry.section.name} -> {entry.day} {entry.start_time:%H:%M}")
    issues = refresh_validation(run)
    mine = [i for i in issues if i.get("section") == entry.section_id and i["subject_code"] == entry.subject_code]
    return Response({"entry": s.EntrySerializer(entry).data, "issues": issues, "entry_issues": mine, "run": s.RunSerializer(run).data})


@api_view(["POST"])
@permission_classes([IsLevelManager])
def run_resolve(request, pk):
    """POST {kind?, section?, subject_code?} -> fix every error of the timetable (or just that one) by changing a teacher, room or period.
    Each change is re-validated with all the hard rules and kept only when it leaves fewer problems and none new."""
    from .resolve import resolve_run
    run = _run_for(request, pk)
    _editable(run)
    only = {k: request.data.get(k) for k in ("kind", "section", "subject_code") if request.data.get(k)} or None
    if only and only.get("kind") == "no_slot":              # "could not be placed" at generation = a missing period in the validation
        only["kind"] = "missing_sessions"
    out = resolve_run(run, request.user, only=only)
    out["run"] = s.RunSerializer(run).data
    return Response(out)


@api_view(["GET"])
@permission_classes([IsLevelManager])
def workload_analytics(request):
    """Teacher workload analytics of ONE school level's latest timetables (see basic_ed/analytics.py). Read-only."""
    from . import analytics
    level = level_of(request)
    ay = active_year(request)
    if ay is None:
        raise ValidationError({"detail": "No academic year is set up yet."})
    if not m.SchoolLevelConfig.objects.filter(level=level).exists():
        raise ValidationError({"detail": f"The {level} school level is not set up yet. Run the seed command first."})
    return Response(analytics.build(level, ay, request.query_params.get("period")))


@api_view(["POST"])
@permission_classes([IsLevelManager])
def run_revalidate(request, pk):
    run = _run_for(request, pk)
    issues = refresh_validation(run)
    return Response({"issues": issues, "run": s.RunSerializer(run).data})


@api_view(["POST"])
@permission_classes([IsLevelManager])
def run_action(request, pk, action):
    run = _run_for(request, pk)
    user = request.user
    comment = request.data.get("comment", "")
    st = run.status
    if action == "submit":
        if st not in ("draft", "revision_requested"):
            raise ValidationError({"detail": "Only a draft can be submitted."})
        issues = refresh_validation(run)
        if any(i["severity"] == "error" for i in issues):
            raise ValidationError({"detail": "Fix the conflicts before submitting for approval.", "issues": issues[:30]})
        run.status = "submitted"
    elif action == "approve":
        if st != "submitted":
            raise ValidationError({"detail": "Only a submitted schedule can be approved."})
        if user.role != "principal" and not user.is_it_admin:
            raise PermissionDenied("Only the principal approves schedules.")
        run.status = "approved"
    elif action == "request-revision":
        if st not in ("submitted", "approved"):
            raise ValidationError({"detail": "Only a submitted or approved schedule can be sent back."})
        if not comment.strip():
            raise ValidationError({"detail": "Tell the team what to revise."})
        run.status = "revision_requested"
    elif action == "publish":
        if st != "approved":
            raise ValidationError({"detail": "Approve the schedule before publishing."})
        run.status = "published"
    else:
        raise ValidationError({"detail": "Unknown action."})
    run.save(update_fields=["status"])
    log(run, action.replace("-", "_"), user, comment)
    return Response(s.RunSerializer(run).data)


@api_view(["GET"])
@permission_classes([IsLevelManager])
def run_pdf(request, pk):
    from .pdf import build_run_pdf
    run = _run_for(request, pk)
    if not run.entries.exists():
        return Response({"detail": "This schedule has no periods yet."}, status=404)
    data = build_run_pdf(run, request.user)
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{run.level}_grade{run.grade_level}_v{run.version}.pdf"'
    return resp


# ----------------------------------------------------------------- teacher
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_schedule(request):
    user = request.user
    fac = m.Faculty.objects.filter(user=user).select_related("user").first()
    if user.role != "teacher" or not fac:
        raise PermissionDenied("This page is for SHS / JHS teachers.")
    runs = m.ScheduleRun.objects.filter(level=fac.level, status__in=["approved", "published"])
    entries = m.ScheduleEntry.objects.filter(run__in=runs, teacher=fac).select_related("section__strand", "room", "run")
    total = sum((to_min(e.end_time) - to_min(e.start_time)) for e in entries) / 60
    return Response({
        "profile": s.FacultySerializer(fac, context={"level": fac.level, "hours": {fac.id: round(total, 1)}}).data,
        "entries": s.EntrySerializer(entries, many=True).data,
        "advised": list(fac.advised_sections.values_list("name", flat=True)),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_availability(request):
    fac = m.Faculty.objects.filter(user=request.user).first()
    if request.user.role != "teacher" or not fac:
        raise PermissionDenied("This page is for SHS / JHS teachers.")
    ser = s.AvailabilitySerializer(data=request.data.get("rows", []), many=True)
    ser.is_valid(raise_exception=True)
    with transaction.atomic():
        fac.availability.all().delete()
        m.Availability.objects.bulk_create([m.Availability(faculty=fac, **r) for r in ser.validated_data])
    return Response({"detail": "Availability saved. The principal will see it when the schedule is generated."})


@api_view(["POST"])
@permission_classes([IsLevelManager])
def clear_generated(request):
    """IT admin only. POST {level, grade_level?, grading_period?, include_approved?, apply?} -> removes the generated timetables of that level.
    Without apply=true it only reports what would be removed. Approved / published ones are kept unless include_approved is true.
    Curriculum, sections, rooms and teachers are never touched."""
    if not request.user.is_it_admin:
        raise PermissionDenied("Only the IT Admin can clear generated schedules.")
    level = level_of(request)
    d = request.data
    qs = m.ScheduleRun.objects.filter(level=level)
    if d.get("grade_level"):
        qs = qs.filter(grade_level=int(d["grade_level"]))
    if d.get("grading_period"):
        qs = qs.filter(grading_period=int(d["grading_period"]))
    kept = 0
    if str(d.get("include_approved", "")).lower() not in ("1", "true", "yes"):
        kept = qs.filter(status__in=["approved", "published"]).count()
        qs = qs.exclude(status__in=["approved", "published"])
    runs, entries = qs.count(), m.ScheduleEntry.objects.filter(run__in=qs).count()
    if str(d.get("apply", "")).lower() in ("1", "true", "yes"):
        qs.delete()
    return Response({"runs": runs, "entries": entries, "kept_approved": kept, "applied": str(d.get("apply", "")).lower() in ("1", "true", "yes")})
