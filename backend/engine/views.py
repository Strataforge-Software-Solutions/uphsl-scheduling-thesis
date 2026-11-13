from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse

from curriculum.models import Subject
from faculty.models import FacultyProfile, Absence, CoverageSuggestion
from rooms.models import Room, DepartmentBuilding
from .models import Section, Student, TimeSlot, Schedule, Constraint, Log, ConflictLog, SchedulingConfig
from .serializers import (
    SectionSerializer, StudentSerializer, TimeSlotSerializer, ScheduleSerializer,
    ConstraintSerializer, LogSerializer, ConflictLogSerializer,
    SchedulingConfigSerializer,
)
from .scheduler import generate_schedule_two_phase, find_substitute
from .conflicts import find_conflicts
from .permissions import ReadOnlyOrRegistrarDean, CanEditOwnScheduleKind, CanEditSections, can_edit_schedule_kind
from curriculum.permissions import CanEditCurriculum


from rest_framework.exceptions import APIException


class WorkloadConflict(APIException):
    """409 carrying the overload details + replacement ideas, so the UI can show the exact warning and offer an override."""
    status_code = 409
    default_detail = "Faculty workload limit exceeded."

    def __init__(self, payload):
        self.detail = payload


def _is_it_admin(user):
    return bool(getattr(user, "is_it_admin", False))


def _enforce_workload(request, teacher, subject, section, new_slots, exclude_schedule_ids=(), target_pk=None):
    """Called before a manual create / teacher-or-time change is saved.
    Within limit -> returns None. Over limit: strict policy blocks; otherwise the caller must send
    override_workload=true (Registrar / Dean only -- already guaranteed by the view permission),
    which is then written to the audit log. Never silently overloads anyone."""
    from . import workload as wl
    term = getattr(section, "semester", "") or ""
    over = wl.check_assignment(teacher, term, new_slots, exclude_schedule_ids)
    if over is None:
        return None
    policy = wl.limits()["policy"]
    flag = str(request.data.get("override_workload", "")).lower() in ("1", "true", "yes")
    if policy != "strict" and flag:
        return over
    diag = {}
    sugg = wl.suggest_replacements(subject, term, new_slots, exclude_teacher_ids=[teacher.id],
                                   school_year=getattr(request.data, "get", lambda *_: None)("school_year"),
                                   exclude_schedule_ids=exclude_schedule_ids, diag=diag, user=request.user, section=section)
    raise WorkloadConflict({
        "detail": over["message"],
        "workload_overload": over,
        "conflicting_assignment": f"{subject} - {section}" if subject is not None else "",
        "can_override": policy != "strict",
        "policy": policy,
        "replacement_suggestions": sugg,
        "no_replacement_reason": "" if sugg else wl.no_available_text(diag),
    })


class SectionViewSet(viewsets.ModelViewSet):
    """Read: anyone logged in. Create / edit / delete: the Registrar, or a Dean for the sections of their own college(s) only.
    (Was "anyone logged in" for every method: e.g. a part-time teacher could delete a section, and with it its classes and class list.)"""
    queryset = Section.objects.select_related("program").all()
    serializer_class = SectionSerializer
    permission_classes = [CanEditSections]

    def _check_program(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        prog = serializer.validated_data.get("program")
        user = self.request.user
        if prog is not None and user.role != "registrar" and prog.department not in user.departments:
            raise PermissionDenied("You can only add or move sections of your own college's programs.")

    def perform_create(self, serializer):
        self._check_program(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._check_program(serializer)
        serializer.save()


class StudentViewSet(viewsets.ModelViewSet):
    """
    Class-list entries (NOT login accounts -- students use the GTI website
    for their own portal, this system has no student dashboard). Lets
    Registrar/Dean record who's in a block Section, and lets a Full-time or
    Part-time faculty member see their own class list per subject.

    Read: everyone authenticated, but get_queryset scopes WHAT they can read
    (a faculty member only sees rosters for sections they actually teach).
    Write (add/edit/remove a student): Registrar (any dept) or Dean (own
    dept only) -- matches CanEditCurriculum's policy, which this reuses
    since a class list is curriculum-adjacent data, not scheduling data a
    faculty member should be able to edit.
    """
    serializer_class = StudentSerializer
    permission_classes = [CanEditCurriculum]

    def check_permissions(self, request):
        super().check_permissions(request)
        # Class lists belong to the Deans (teachers only read their own); the Registrar has no access.
        if request.user.is_authenticated and request.user.role == "registrar":
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Class lists are managed by the Deans.")

    def get_queryset(self):
        qs = Student.objects.select_related("section__program").all()
        user = self.request.user
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(section__program__department__in=user.departments)
        if user.role == "faculty" and user.faculty_type in ("full_time", "part_time"):
            # Only the sections this teacher actually has a class in --
            # "who's in MY class", not every student in the institution.
            # Schedule.section has no related_name, so the reverse filter
            # lookup is the default "schedule" (model name, lowercase).
            return qs.filter(section__schedule__teacher__user=user).distinct()
        return qs.none()

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser])
    def import_list(self, request):
        """multipart: file (.csv/.xlsx with Full Name, Section, Year Level), program_id, semester?, commit ("true" to save).
        Without commit it only reports what would be added and what is wrong."""
        from curriculum.models import Program
        from .class_list_import import run_import
        user = request.user
        if not (user.role == "faculty" and user.faculty_type == "dean"):
            return Response({"detail": "Only a Dean can upload a class list."}, status=403)
        program = Program.objects.filter(pk=request.data.get("program_id")).first()
        if program is None:
            return Response({"detail": "Choose a program."}, status=400)
        if program.department not in user.departments:
            return Response({"detail": "That program is not in your college."}, status=403)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Choose a file to upload."}, status=400)
        commit = str(request.data.get("commit", "")).lower() in ("1", "true", "yes")
        try:
            with transaction.atomic():
                result = run_import(upload, program, (request.data.get("semester") or "").strip(), commit)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        except Exception:
            return Response({"detail": "Could not read the file. Use the template: Full Name, Section, Year Level."}, status=400)
        return Response(result)


class TimeSlotViewSet(viewsets.ModelViewSet):
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    # Was IsAuthenticated-only -- any logged-in Student could DELETE a TimeSlot,
    # which cascades (Schedule.timeslot is on_delete=CASCADE) and wipes every
    # class using that slot institution-wide. Read stays open; writes are
    # Registrar/Dean only, same as every other scheduling-infrastructure viewset.
    permission_classes = [ReadOnlyOrRegistrarDean]

    @action(detail=False, methods=["post"])
    def get_or_create(self, request):
        """
        Lets Registrar/Dean pick any day/start/end when creating an exam slot
        instead of choosing from a fixed pre-seeded list -- reuses a matching
        TimeSlot if one already exists, creates it otherwise.
        """
        day = request.data.get("day")
        start_time = request.data.get("start_time")
        end_time = request.data.get("end_time")
        if not (day and start_time and end_time):
            return Response({"detail": "day, start_time, end_time are required."}, status=status.HTTP_400_BAD_REQUEST)

        slot, _ = TimeSlot.objects.get_or_create(day=day, start_time=start_time, end_time=end_time)
        return Response(TimeSlotSerializer(slot).data, status=status.HTTP_200_OK)


class ScheduleViewSet(viewsets.ModelViewSet):
    """Registrar edits/removes MINOR classes only; a Dean edits/removes/approves MAJOR classes of their own
    college(s) only. Everyone else (and each role for the other kind) can read but not change."""
    serializer_class = ScheduleSerializer
    permission_classes = [CanEditOwnScheduleKind]

    def get_queryset(self):
        # section__program, approved_by and subject__field are all read by
        # ScheduleSerializer for every row -- without joining them, each row
        # cost extra database queries (very slow over a remote Supabase DB,
        # and a likely cause of "Could not load schedules." timeouts).
        qs = Schedule.objects.select_related(
            "subject", "subject__field", "teacher__user", "room", "section", "section__program",
            "timeslot", "approved_by",
        )
        if getattr(self, "action", None) == "list":
            # The schedule list is the largest recurring response. Keep the
            # joins needed by ScheduleSerializer, but avoid transferring unused
            # columns (for example room equipment and faculty qualifications)
            # from the hosted database on every list request.
            qs = qs.only(
                "id", "subject_id", "teacher_id", "room_id", "section_id", "timeslot_id",
                "is_substitution", "original_teacher_id", "is_manual_override", "school_year",
                "generated_at", "status", "approved_by_id", "approved_at", "merge_key",
                "qualification_override",
                "subject__code", "subject__title", "subject__classification", "subject__field_id",
                "subject__field__name",
                "teacher__user__first_name", "teacher__user__last_name",
                "room__name",
                "section__name", "section__program_id", "section__year_level", "section__semester",
                "section__student_count", "section__program__name", "section__program__department",
                "timeslot__day", "timeslot__start_time", "timeslot__end_time",
                "approved_by__username",
            )
        user = self.request.user
        if user.role == "faculty" and user.faculty_type in ("full_time", "part_time"):
            return qs.filter(teacher__user=user)          # faculty sees only their own classes
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(section__program__department__in=user.departments)
        if user.role == "student":
            # SAFE DEFAULT: there is no Enrollment model yet linking a student
            # to their actual section, so there's no correct way to filter
            # this to "their" classes. Returning nothing is safer than the
            # previous behavior, which fell through to "Registrar sees all"
            # and showed every student every class in the institution.
            # TODO: build an Enrollment model (student <-> section) and filter
            # by qs.filter(section__in=user.enrollments.values('section')).
            return qs.none()
        return qs                                          # Registrar sees all

    def _check_conflicts(self, validated_data, exclude_pk=None):
        """Manual creates/edits (e.g. the Edit-schedule modal's free-typed
        day/time) had NO overlap check at all -- only the CSP generator's
        OWN exact-TimeSlot-id matching stood in the way, and that doesn't
        catch two different TimeSlot rows that merely overlap in wall-clock
        time. A Dean/Registrar could save a class into a room/section that's
        already occupied 1-2pm by something else, with nothing flagging it,
        which is exactly how a schedule like that gets into the database.
        Reuses the same find_conflicts() already relied on for exams, so
        the policy (hard block for teacher/room, grace-window tolerance for
        section) is identical across the whole system instead of exams-only."""
        from .college_break import is_blocked_slot, message as college_break_message
        slot = validated_data.get("timeslot")
        if slot is not None and is_blocked_slot(slot):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": college_break_message()})
        conflicts = find_conflicts(
            teacher=validated_data.get("teacher"),
            room=validated_data.get("room"),
            section=validated_data.get("section"),
            timeslot=validated_data.get("timeslot"),
            exclude_model="Schedule", exclude_pk=exclude_pk,
            merge_key=validated_data.get("merge_key", ""),
            semester=getattr(validated_data.get("section"), "semester", None),
        )
        room, section = validated_data.get("room"), validated_data.get("section")
        if room is not None and section is not None:
            from rooms.rules import may_use, reserved_message
            dept = getattr(section.program, "department", None)
            if not may_use(room, dept):
                conflicts = list(conflicts or []) + [reserved_message(room, dept)]
        if conflicts:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": " ".join(conflicts)})

    @staticmethod
    def _save_or_conflict(serializer, **extra):
        """Save inside a savepoint; if the database's own double-booking rule fires (someone booked the same teacher /
        room / students a moment earlier) answer with a clear 400 instead of a crash."""
        from rest_framework.exceptions import ValidationError
        try:
            with transaction.atomic():
                return serializer.save(**extra)
        except IntegrityError:
            raise ValidationError({"detail": "That time was just taken by another class (the same teacher, room or "
                                             "students). Reload the schedule and pick a free time."})

    def perform_create(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        subj, sec = serializer.validated_data.get("subject"), serializer.validated_data.get("section")
        if subj is not None and not can_edit_schedule_kind(
                self.request.user, subj.classification, getattr(getattr(sec, "program", None), "department", None)):
            raise PermissionDenied("You can only add " + ("Gen Ed" if self.request.user.role == "registrar" else "program")
                                   + " subjects to the schedule.")
        self._check_conflicts(serializer.validated_data)
        from rooms.rules import fixed_room_message, room_kind_message
        from rest_framework.exceptions import ValidationError as _VE
        _rm = serializer.validated_data.get("room")
        _fx = (fixed_room_message(subj, _rm) or room_kind_message(subj, _rm)) if subj is not None else None
        if _fx:
            raise _VE({"detail": _fx})
        vd = serializer.validated_data
        if subj is not None and sec is not None and vd.get("timeslot") is not None:
            from . import lecorder                       # Lecture before Lab (the solver's rule)
            _ts = vd["timeslot"]
            _why = lecorder.check(subj, sec.id, vd.get("term") or sec.semester,
                                  [(_ts.day, _ts.start_time.hour * 60 + _ts.start_time.minute, _ts.end_time.hour * 60 + _ts.end_time.minute)])
            if _why:
                raise _VE({"detail": _why})
        over = _enforce_workload(self.request, vd["teacher"], subj, sec, [vd["timeslot"]]) if vd.get("teacher") and vd.get("timeslot") else None
        instance = self._save_or_conflict(serializer)
        Log.objects.create(
            action="CREATE", schedule_id=instance.id, user=self.request.user,
            details=f"Created schedule entry {instance}",
        )
        if over:
            Log.objects.create(
                action="UPDATE", schedule_id=instance.id, user=self.request.user,
                details=f"WORKLOAD OVERRIDE: {over['message']}",
            )

    def perform_update(self, serializer):
        # A partial update (e.g. the modal only sends the fields it changed)
        # may be missing teacher/room/section/timeslot from validated_data --
        # fall back to the existing row's current value for whichever one
        # wasn't part of this request, so the check still runs against the
        # FULL resulting assignment, not just the fields that happened to
        # be touched this time.
        instance = serializer.instance
        if instance.status != "draft":
            # approved / published classes are never changed by accident: back to Draft first (Schedules tab > Back to draft)
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": f"This class is {instance.status}. Move it back to Draft before editing it."})
        if instance.merge_key:
            from rest_framework.exceptions import ValidationError
            others = Schedule.objects.filter(merge_key=instance.merge_key).exclude(section=instance.section) \
                .values_list("section__name", flat=True).distinct()
            raise ValidationError({"detail": (
                f"This is a shared class (also attended by section(s) {', '.join(sorted(set(others)))}). "
                "Change it from the Edit dialog: a new teacher, room or day/time is applied to every section of the shared class "
                "together, so the sharing is kept.")})
        merged = {
            "teacher": serializer.validated_data.get("teacher", instance.teacher),
            "room": serializer.validated_data.get("room", instance.room),
            "section": serializer.validated_data.get("section", instance.section),
            "timeslot": serializer.validated_data.get("timeslot", instance.timeslot),
        }
        self._check_conflicts(merged, exclude_pk=instance.pk)
        if merged["timeslot"].id != instance.timeslot_id or merged["section"].id != instance.section_id:
            # Lecture before Lab (the solver's rule): an edit may not put the Lab before its Lecture
            from . import lecorder
            _ts = merged["timeslot"]
            _why = lecorder.check(instance.subject, merged["section"].id, instance.term or merged["section"].semester,
                                  [(_ts.day, _ts.start_time.hour * 60 + _ts.start_time.minute, _ts.end_time.hour * 60 + _ts.end_time.minute)],
                                  exclude_ids=[instance.pk])
            if _why:
                from rest_framework.exceptions import ValidationError as _VE
                raise _VE({"detail": _why})
        _ov_meta = instance.qualification_override             # kept unless the teacher changes
        _new_override = False
        if merged["teacher"].id != instance.teacher_id:
            # one shared rule (engine.teacher_scope): a Dean's major goes only to qualified faculty of the Dean's own department(s);
            # a Gen Ed subject to any qualified teacher. Re-checked here on every Save, whatever the dialog showed.
            from .teacher_scope import teacher_allowed
            _why = teacher_allowed(self.request.user, merged["teacher"], instance.subject, merged["section"])
            _ov_meta = None
            if _why and str(self.request.data.get("override_qualification", "")).lower() in ("1", "true", "yes"):
                # a manual Assign anyway (not connected): only the qualification check is skipped. Department, a reason, free at this
                # exact time inside the person's availability, within the weekly limit and "no qualified faculty free" are re-checked now.
                from rest_framework.exceptions import ValidationError as _VE
                from . import faculty_groups as _fg
                if merged["timeslot"].id != instance.timeslot_id:
                    raise _VE({"detail": "Change the day and time first, then assign a faculty member who is not connected to the subject."})
                if str(self.request.data.get("override_workload", "")).lower() in ("1", "true", "yes"):
                    raise _VE({"detail": "The weekly limit cannot be overridden when assigning a faculty member who is not connected."})
                cls = list(Schedule.objects.filter(section=instance.section, subject=instance.subject, term=instance.term)
                           .select_related("timeslot"))
                slots = list({r.timeslot_id: r.timeslot for r in cls}.values())
                need = sum((_s.end_time.hour * 60 + _s.end_time.minute - _s.start_time.hour * 60 - _s.start_time.minute) / 60 for _s in slots)
                groups = _fg.build(self.request.user, instance.subject, instance.section, term=instance.term,
                                   school_year=instance.school_year or None, exact_slots=slots, exclude_ids=[r.id for r in cls],
                                   need_hours=need)
                try:
                    reason = _fg.check_override(self.request.user, instance.subject, instance.section, merged["teacher"],
                                                self.request.data.get("override_reason"), groups)
                except _fg.OverrideError as e:
                    raise _VE({"detail": e.message})
                _ov_meta = _fg.override_meta(self.request.user, reason)
                _new_override = True
                _why = ""
            if _why:
                from rest_framework.exceptions import ValidationError as _VE
                raise _VE({"detail": _why})
        if merged["teacher"].id != instance.teacher_id:
            # one teacher for a subject's Lec and Lab in a section: a manual edit may not split them
            from .scheduler import _is_lab_of
            partner = next((p for p in Schedule.objects.filter(section=merged["section"], term=instance.term)
                            .select_related("subject", "teacher__user")
                            if (_is_lab_of(instance.subject, p.subject) or _is_lab_of(p.subject, instance.subject))
                            and p.teacher_id != merged["teacher"].id), None)
            if partner is not None:
                from rest_framework.exceptions import ValidationError as _VE
                pname = partner.teacher.user.get_full_name().strip() or partner.teacher.user.username
                raise _VE({"detail": (f"{instance.subject.code} and {partner.subject.code} (its Lec / Lab) must have the same teacher. "
                                      f"{partner.subject.code} is taught by {pname}, so keep {pname} here. To give both parts another teacher, "
                                      "remove both classes and Generate them again.")})
        if merged["room"].id != instance.room_id:
            from rooms.rules import fixed_room_message, room_kind_message
            from rest_framework.exceptions import ValidationError as _VE
            _fx = fixed_room_message(instance.subject, merged["room"]) or room_kind_message(instance.subject, merged["room"])
            if _fx:
                raise _VE({"detail": _fx})
        over = None
        if merged["teacher"].id != instance.teacher_id or merged["timeslot"].id != instance.timeslot_id:
            over = _enforce_workload(self.request, merged["teacher"], instance.subject, merged["section"],
                                     [merged["timeslot"]], exclude_schedule_ids=[instance.pk])
        instance = self._save_or_conflict(serializer, is_manual_override=True, qualification_override=_ov_meta)
        Log.objects.create(
            action="UPDATE", schedule_id=instance.id, user=self.request.user,
            details=f"Updated schedule entry {instance}",
        )
        if _new_override:
            from . import faculty_groups as _fg
            _fg.log_overrides(self.request.user, [instance], "the Edit dialog", action="UPDATE")
        if over:
            Log.objects.create(
                action="UPDATE", schedule_id=instance.id, user=self.request.user,
                details=f"WORKLOAD OVERRIDE: {over['message']}",
            )

    def perform_destroy(self, instance):
        # Approved / published classes are never removed by accident: they must go back to Draft first (also enforced for remove_bulk)
        if instance.status != "draft":
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": f"This class is {instance.status}. Move it back to Draft before removing it."})
        Log.objects.create(
            action="DELETE", schedule_id=instance.id, user=self.request.user,
            details=f"Removed schedule entry {instance}",
        )
        instance.delete()
        from .housekeeping import cleanup_after_delete
        cleanup_after_delete()

    @action(detail=False, methods=["post"])
    def approve_bulk(self, request):
        """
        Dean Villanueva's interview: she drafts the class program, the School
        Director approves it, and only then is it encoded/live. We have no
        separate Director role, so Registrar or Dean (already scoped to their
        own department by CanEditCurriculum via get_queryset) performs this
        approval step explicitly, moving schedules forward one stage:
        draft -> approved, or approved -> published.

        Body: { "to_status": "approved"|"published", AND EITHER
                 "ids": [schedule_id, ...]  -- approve/publish just these specific
                 rows (e.g. one subject's periods, from an Approve button on a
                 single table row), one or two subjects at a time while the rest
                 stay in review, OR
                 "program_id", "year_level", "semester" -- the original
                 whole-scope bulk move (every draft/approved row matching the
                 filter), still supported for "approve everything at once". }
        """
        to_status = request.data.get("to_status")
        if to_status not in ("approved", "published", "draft"):
            return Response({"detail": "to_status must be 'approved', 'published' or 'draft'."}, status=status.HTTP_400_BAD_REQUEST)
        from . import schedule_actions as sa
        from_status = {"approved": "draft", "published": "approved", "draft": "approved"}[to_status]
        qs = self.get_queryset()
        # Each role approves / publishes only its own kind: Registrar -> minor, Dean -> major.
        if request.user.role == "registrar":
            qs = qs.filter(subject__classification="minor")
        elif request.user.role == "faculty" and request.user.faculty_type == "dean":
            qs = qs.filter(subject__classification="major")
        else:
            return Response({"detail": "Only the Registrar or a Dean can approve schedules."}, status=status.HTTP_403_FORBIDDEN)
        ids = request.data.get("ids")
        if ids:
            # exactly the selected rows: other rows of the filter are never touched
            qs = qs.filter(id__in=ids)
            if to_status == "draft":
                qs = qs.filter(status__in=("approved", "published"))
            else:
                qs = qs.filter(status=from_status)
            scope_desc = f"ids={list(ids)}"
        else:
            qs = qs.filter(status=from_status)
            program_id = request.data.get("program_id")
            department = request.data.get("department")
            year_level = request.data.get("year_level")
            semester = request.data.get("semester")
            if program_id:
                qs = qs.filter(section__program_id=program_id)
            if department:
                qs = qs.filter(section__program__department=department)
            if year_level:
                qs = qs.filter(section__year_level=year_level)
            if semester:
                qs = qs.filter(section__semester=semester)
            scope_desc = f"program={program_id}, dept={department}, year={year_level}, sem={semester}"
        try:
            # conflict check first (server side): conflicting classes stay where they are, with the reason
            out = sa.change_status(request.user, list(qs), to_status)
        except sa.ActionError as e:
            return Response({"detail": e.message, **e.extra}, status=e.status)
        Log.objects.create(action="UPDATE", schedule_id=0, user=request.user,
                           details=f"Moved {out['updated']} schedule(s) from {from_status} to {to_status} ({scope_desc}); "
                                   f"{len(out['blocked'])} class(es) blocked")
        return Response(out)

    def _action_call(self, fn):
        from . import schedule_actions as sa
        u = self.request.user
        if not (u.role == "registrar" or (u.role == "faculty" and u.faculty_type == "dean")):
            return Response({"detail": "Only the Registrar or a Dean can change schedules."}, status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(fn(sa, u, self.request.data))
        except sa.ActionError as e:
            return Response({"detail": e.message, **e.extra}, status=e.status)
        except (TypeError, ValueError, KeyError):
            return Response({"detail": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def remove_preview(self, request):
        """{ids} -> exactly which classes / periods would be removed, which are locked (approved / published) and the warnings."""
        return self._action_call(lambda sa, u, d: sa.remove_preview(u, [int(i) for i in d.get("ids") or []]))

    @action(detail=False, methods=["post"])
    def remove_override(self, request):
        """POST {ids}: undo an Assign anyway (not connected) from the Edit dialog. The class's DRAFT rows are removed, so the class is
        not placed again (unassigned); nothing else changes. Only the Dean of that department."""
        from rest_framework.exceptions import ValidationError as _VE
        from . import faculty_groups as _fg
        try:
            ids = [int(x) for x in (request.data.get("ids") or [])]
        except (TypeError, ValueError):
            raise _VE({"detail": "ids must be numbers."})
        rows = list(Schedule.objects.filter(pk__in=ids).select_related("subject", "section__program", "teacher__user"))
        if not rows or len(rows) != len(set(ids)):
            raise _VE({"detail": "That class was changed or removed. Reload the schedule."})
        r0 = rows[0]
        if any((r.section_id, r.subject_id) != (r0.section_id, r0.subject_id) for r in rows):
            raise _VE({"detail": "These periods belong to different classes."})
        if not _fg.override_possible(request.user, r0.subject, r0.section):
            raise PermissionDenied("Only the Dean of this department can remove an Assign anyway.")
        cls = list(Schedule.objects.filter(section=r0.section, subject=r0.subject, term=r0.term))
        if not any(r.qualification_override for r in cls):
            raise _VE({"detail": "This class was not assigned anyway; nothing to remove."})
        if any(r.status != "draft" for r in cls):
            raise _VE({"detail": "This class is approved or published. Move it back to Draft first."})
        teacher = r0.teacher.user.get_full_name().strip() or r0.teacher.user.username
        with transaction.atomic():
            for r in cls:
                Log.objects.create(action="DELETE", schedule_id=r.id, user=request.user,
                                   details=f"ASSIGN ANYWAY REMOVED: {teacher} no longer teaches {r.subject.code} "
                                           f"({r.section.program.name} {r.section.name}); the class is not placed.")
            Schedule.objects.filter(pk__in=[r.id for r in cls]).delete()
        return Response({"removed": len(cls), "detail": f"{r0.subject.code} ({r0.section.name}) is not placed now. Generate or place it again."})

    @action(detail=False, methods=["post"])
    def remove_bulk(self, request):
        """{ids, confirm_shared?} -> removes the selected DRAFT periods (all or nothing) and returns an undo token."""
        return self._action_call(lambda sa, u, d: sa.remove(u, [int(i) for i in d.get("ids") or []],
                                                            confirm_shared=str(d.get("confirm_shared", "")).lower() in ("1", "true", "yes")))

    @action(detail=False, methods=["post"])
    def undo_remove(self, request):
        """{token} -> restores the exact rows of a removal made by this user in the last few minutes."""
        return self._action_call(lambda sa, u, d: sa.undo_remove(u, int(d["token"])))

    @action(detail=False, methods=["get"])
    def history(self, request):
        """?ids=1,2,3 -> created / changed / approved / removed events of that class, with who and when."""
        ids = [int(x) for x in (request.query_params.get("ids") or "").split(",") if x.strip().isdigit()]
        visible = set(self.get_queryset().filter(pk__in=ids).values_list("id", flat=True))
        from . import schedule_actions as sa
        try:
            return Response(sa.history(request.user, [i for i in ids if i in visible]))
        except sa.ActionError as e:
            return Response({"detail": e.message}, status=e.status)


class ConstraintViewSet(viewsets.ModelViewSet):
    queryset = Constraint.objects.all()
    serializer_class = ConstraintSerializer
    # Same gap as TimeSlotViewSet above -- any authenticated user could rewrite
    # the CSP engine's availability/room-type rules. Writes restricted to Registrar/Dean.
    permission_classes = [ReadOnlyOrRegistrarDean]


class LogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Log.objects.select_related("user").order_by("-timestamp")
    serializer_class = LogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Log.objects.select_related("user").order_by("-timestamp")
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            schedule_ids = Schedule.objects.filter(
                section__program__department__in=user.departments
            ).values_list("pk", flat=True)
            return qs.filter(schedule_id__in=schedule_ids)
        return qs.none()


class ConflictLogViewSet(viewsets.ModelViewSet):
    """Also the landing point for historical conflict data requested from IT (2021-2026)."""
    queryset = ConflictLog.objects.select_related("section", "teacher__user", "room").order_by("-occurred_at")
    serializer_class = ConflictLogSerializer
    permission_classes = [ReadOnlyOrRegistrarDean]

    def get_queryset(self):
        user = self.request.user
        qs = ConflictLog.objects.select_related("section", "teacher__user", "room").order_by("-occurred_at")
        if user.is_it_admin or user.role == "registrar":
            return qs
        if user.role == "faculty" and user.faculty_type == "dean":
            return qs.filter(
                Q(section__program__department__in=user.departments)
                | Q(teacher__user__department__in=user.departments)
            )
        return qs.none()

    def _check_dean_scope(self, section, teacher):
        user = self.request.user
        if user.role != "faculty" or user.faculty_type != "dean":
            return
        if section is None and teacher is None:
            raise PermissionDenied("A conflict must be linked to a record in your college.")
        if section is not None and section.program.department not in user.departments:
            raise PermissionDenied("You can only manage conflicts in your own college.")
        if teacher is not None and teacher.user.department not in user.departments:
            raise PermissionDenied("You can only manage conflicts in your own college.")

    def perform_create(self, serializer):
        self._check_dean_scope(serializer.validated_data.get("section"), serializer.validated_data.get("teacher"))
        serializer.save()

    def perform_update(self, serializer):
        current = self.get_object()
        self._check_dean_scope(
            serializer.validated_data.get("section", current.section),
            serializer.validated_data.get("teacher", current.teacher),
        )
        serializer.save()


def _build_availability_rules(teachers, timeslots, school_year=None, semester=None):
    """
    Builds {teacher_id: set(blocked_timeslot_id, ...)} for the CSP engine.

    BUG FIX: this previously created an empty set per teacher and never
    populated it, so faculty availability was silently NEVER enforced during
    generation -- a real gap directly relevant to Dean Villanueva's interview
    point that scheduling is supposed to be built around faculty availability.

    The actual source of truth is faculty.Availability (what a faculty member
    submitted as free), not Constraint (which this system never ends up
    populating from the UI). A teacher's blocked slots = the TimeSlots that overlap
    a window they marked "unavailable" for the given school_year/semester; their
    "preferred" / "available" windows only set the ORDER (engine.availability), they
    do not close the rest of the day. A teacher who has submitted NO
    availability rows is treated as unrestricted (no blocks) -- otherwise every
    full-time faculty member, who never submits Availability today, would be
    wrongly blocked from every slot.
    """
    from . import availability as _av

    rules = {}
    # ONE query for everybody (was one query per teacher -- slow over a remote DB). Rows saved without a school year / semester
    # apply to every term (engine.availability.rows).
    all_qs = _av.rows(None, school_year, semester)
    windows_by_teacher = {}
    for w in all_qs:
        windows_by_teacher.setdefault(w.faculty_id, []).append(w)
    for teacher in teachers:
        windows = windows_by_teacher.get(teacher.id, [])

        if not windows:
            rules[teacher.id] = set()  # no submission on file -> unrestricted
            continue

        # A teacher's "preferred" / "available" windows are PRIORITIES, not limits (engine.availability ranks them first): the
        # other times of the day stay open. Only times they marked "unavailable" are blocked for automatic scheduling.
        # (Before, every time outside the submitted windows was blocked.) A Dean may still place a class anywhere by hand as
        # long as nothing clashes (engine.reschedule: "Choose a new day and time" lists those times, marked).
        block_windows = [w for w in windows if w.preference == "unavailable"]
        blocked = set()
        for slot in timeslots:
            overlaps_blocked_window = any(
                w.day[:3].lower() == slot.day[:3].lower()
                and w.start_time < slot.end_time
                and w.end_time > slot.start_time
                for w in block_windows
            )
            if overlaps_blocked_window:
                blocked.add(slot.id)
        rules[teacher.id] = blocked
    return rules


def plain_reason(text):
    """The reason a class was skipped, without the sentences that point to suggested times / rooms (the Generate pop-up shows the
    reason only; suggestions stay in the Smart Resolve screens)."""
    import re as _re
    parts = _re.split(r"(?<=[.!?])\s+", (text or "").strip())
    keep = [p for p in parts if p and not _re.search(r"suggest|pick one of", p, _re.I)]
    return " ".join(keep) or (text or "").strip()


def room_choice_error(role, sub, room, dept, rooms, gym):
    """Empty text when `room` may be chosen for subject `sub` (section department `dept`) by this role, else the reason. The ONE check used by
    Generate (_preview_choices) and by the Room dropdown's list of allowed rooms (rooms.dean_views.preview_choices)."""
    from rooms import rules as rr
    from .scheduler import _room_matches_subject
    if role == "registrar" and sub.classification != "minor":
        return (f"{sub.code} is a program (major) subject: its rooms are assigned by the Dean of {dept}, not by the Registrar. "
                "Leave its Room on Automatic.")
    if role != "registrar" and sub.classification == "minor":
        return (f"{sub.code} is a Gen Ed (minor) subject: its rooms are assigned by the Registrar. "
                "Ask the Registrar to choose the room, or leave it on Automatic.")
    if sub.classification != "minor":
        des = rr.designated_rooms(rooms, dept)
        if des is not None and room.id not in {d.id for d in des}:
            return rr.designated_message(sub, dept, rooms)
    if not rr.may_use(room, dept):
        return f"Room {room.name} is reserved for {room.department} and cannot be used for {sub.code}."
    if (not _room_matches_subject(room, sub, gym)
            or (sub.lab_units == 0 and getattr(room, "room_type", "") == "lab" and not rr.is_owned_lab(room))):
        kind = "a laboratory" if sub.lab_units > 0 else "a lecture room"
        return f"{sub.code} needs {kind}; {room.name} is not suitable."
    return ""


def _preview_choices(request, subjects_by_section, rooms):
    """Validate the optional per-subject Room / Start / End picked in the curriculum preview.
    Returns (error text | "", {subject_id: room_id}, {subject_id: (start_min, end_min)})."""
    from rooms import rules as rr
    from .scheduler import _room_matches_subject, _slot_minutes
    subs = {sub.id: sub for lst in subjects_by_section.values() for sub in lst}
    by_room = {r.id: r for r in rooms}
    gym = any(getattr(r, "room_type", "") == "gym" for r in rooms)
    choices, windows = {}, {}
    for key, rid in (request.data.get("room_choices") or {}).items():
        if rid in (None, "", 0):
            continue
        try:
            sid, rid = int(key), int(rid)
        except (TypeError, ValueError):
            return "Room choices are not valid.", {}, {}
        sub, room = subs.get(sid), by_room.get(rid)
        if sub is None:
            continue
        if room is None:
            return f"The room chosen for {sub.code} does not exist or is not available.", {}, {}
        dept = next((sec.program.department for sec, lst in subjects_by_section.items() if sub in lst), None)
        err = room_choice_error(getattr(request.user, "role", ""), sub, room, dept, rooms, gym)
        if err:
            return err, {}, {}
        choices[sid] = rid
    for key, w in (request.data.get("time_windows") or {}).items():
        if isinstance(w, dict) and w.get("day"):
            if str(w["day"])[:3].title() not in {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}:
                return "The chosen day is not valid.", {}, {}
        if not isinstance(w, dict) or not (w.get("start") or w.get("end")):
            continue
        try:
            sid = int(key)
            a = _slot_minutes(w.get("start") or "00:00")
            b = _slot_minutes(w.get("end") or "23:59")
        except (TypeError, ValueError):
            return "Start / End times are not valid.", {}, {}
        if sid in subs:
            if b <= a:
                return f"{subs[sid].code}: the End Time must be later than the Start Time.", {}, {}
            from .scheduler import window_need_minutes
            need = window_need_minutes(subs[sid])
            if b - a < need:
                return (f"{subs[sid].code} needs an unbroken {need / 60:g}-hour class period, but the chosen Start and End Time is only "
                        f"{(b - a) / 60:g} hour(s). Choose a longer window (or 'Any time')."), {}, {}
            windows[sid] = (a, b)
    return "", choices, windows


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def generate_schedule_view(request):
    """
    Body: { "program_id": ..., "year_level": ..., "semester": ..., "school_year": ... }
    Runs the CSP engine for the given scope and bulk-creates Schedule rows as
    DRAFT (Dean Villanueva's interview: she prepares a draft class program
    first; it only goes live after approval -- see ScheduleViewSet.approve_bulk).

    Gen Ed/minor subjects are solved FIRST and major subjects are then solved
    around that fixed Gen Ed schedule (generate_schedule_two_phase), matching
    her description of the real planning order and why Gen Ed faculty changes
    cascade into major-schedule rework.
    """
    import time
    import traceback
    t0 = time.time()

    program_id = request.data.get("program_id")
    year_level = request.data.get("year_level")
    semester = request.data.get("semester")
    school_year = request.data.get("school_year", "")

    if not all([program_id, year_level, semester]):
        return Response(
            {"detail": "program_id, year_level, and semester are all required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        program_id = int(program_id)
    except (TypeError, ValueError):
        return Response({"detail": "program_id must be a number."}, status=status.HTTP_400_BAD_REQUEST)

    # Only the Registrar and Deans build class schedules, and each builds ONE kind:
    #   Registrar -> minor (Gen Ed) subjects      Dean -> major subjects of their own college(s)
    # Both end up in the same weekly schedule; the second one is placed around the first.
    _u = request.user
    _is_dean = getattr(_u, "role", "") == "faculty" and getattr(_u, "faculty_type", "") == "dean"
    if getattr(_u, "role", "") == "registrar":
        kind = "minor"
    elif _is_dean:
        kind = "major"
    else:
        return Response({"detail": "Only the Registrar (Gen Ed subjects) or a Dean (program subjects) can generate class schedules."},
                        status=status.HTTP_403_FORBIDDEN)
    if _is_dean:
        from curriculum.models import Program as _Program
        _prog = _Program.objects.filter(pk=program_id).first()
        if _prog is not None and _prog.department not in _u.departments:
            return Response({"detail": "You can only generate subjects for programs in your own college."},
                            status=status.HTTP_403_FORBIDDEN)

    # Everything below used to run with no safety net -- any unexpected error
    # (a data issue, a bad row, anything) propagated as a bare, undecorated
    # 500 with no JSON body, which the frontend could only show as a generic
    # "Schedule generation failed." with zero information to act on. Wrapping
    # it mirrors the same try/except already used in exams/views.py's
    # generate_exam_schedule_view, and logs the full traceback server-side
    # (visible in the `runserver` console) so the real cause is never lost.
    from audit import recorder as _audit
    try:
      # audit log: the drafts this run replaces and the class periods it creates go into ONE "generate" entry
      with transaction.atomic(), _audit.batch("generate", "schedule", f"program {program_id}",
                                              summary=f"Generate {year_level} {semester} (program {program_id})"):
        from . import locks as _locks
        if not _locks.try_lock("classes"):
            return Response({"detail": _locks.BUSY}, status=status.HTTP_409_CONFLICT)
        sections = Section.objects.filter(program_id=program_id, year_level=year_level, semester=semester)
        subjects = Subject.objects.filter(program_id=program_id, year_level=year_level, semester=semester,
                                          classification=kind)
        subjects_by_section = {s: list(subjects) for s in sections}
        if not subjects_by_section:
            return Response({"detail": f"No section exists for this program, {year_level}, {semester}. "
                                       "Add the sections (curriculum seed or Django admin > Sections) first."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not subjects.exists():
            return Response({"detail": f"No {kind} subjects are set up for this program, {year_level}, {semester}. "
                                       "Add the curriculum first."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Re-generating the same program/year/semester used to stack a SECOND
        # full copy of every class on top of the first. Now: if this scope
        # already has approved/published classes, refuse (never silently
        # change a schedule that has been signed off); otherwise the earlier
        # DRAFT is replaced. Done inside one transaction, so if generation
        # fails the old draft is kept, not lost.
        scope_rows = Schedule.objects.filter(section__in=sections, subject__classification=kind)
        other_kind_exists = Schedule.objects.filter(
            section__in=sections).exclude(subject__classification=kind).exists()
        # "Generate only the missing ones": only classes (section + subject) without their full hours are placed. Every complete class
        # stays exactly where it is (draft, hand-edited, approved, published or shared alike) and counts as booked. A partly placed
        # DRAFT class (not edited by hand, not shared) is redone as a whole; a partly placed locked / approved / published / shared
        # class is never touched and is reported instead.
        only_missing = str(request.data.get("only_missing", "")).lower() in ("1", "true", "yes")
        missing_untouched = []
        if only_missing:
            from collections import defaultdict as _dd
            from .placement import expected_minutes as _expected
            _have, _rows, _frozen = _dd(int), _dd(list), set()
            for pk, sec_id, sub_id, st, mo, mk, a, b in scope_rows.values_list(
                    "pk", "section_id", "subject_id", "status", "is_manual_override", "merge_key", "timeslot__start_time", "timeslot__end_time"):
                _have[(sec_id, sub_id)] += (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)
                _rows[(sec_id, sub_id)].append(pk)
                if st != "draft" or mo or mk:
                    _frozen.add((sec_id, sub_id))
            redo = []
            for _sec in list(subjects_by_section):
                keep = []
                for _sub in subjects_by_section[_sec]:
                    key = (_sec.id, _sub.id)
                    if _have[key] >= _expected(_sub):
                        continue                                        # complete: left as it is
                    if key in _frozen:
                        missing_untouched.append(f"{_sub.code} ({_sec.program.name} {_sec.name}): partly placed and locked, approved, "
                                                 "published or shared, so it was not changed. Edit it by hand or move it back to draft.")
                        continue
                    keep.append(_sub)
                    redo += _rows[key]
                subjects_by_section[_sec] = keep
            scope_rows = Schedule.objects.filter(pk__in=redo)           # only the incomplete drafts of the classes being placed
        locked_count = 0 if only_missing else scope_rows.exclude(status="draft").count()
        if locked_count:
            return Response(
                {"detail": f"This year level and semester already has {locked_count} approved/published "
                           f"{kind}-subject class period(s). Move them back to draft or remove them before generating again."},
                status=status.HTTP_409_CONFLICT,
            )
        # Classes changed by hand (Edit, Smart Resolve, Change day / time: is_manual_override) are LOCKED: a later Generate keeps
        # them exactly where they are (they count as booked for everything else) instead of replacing them. Send keep_edited=false
        # to re-place them too.
        kept_classes = []
        _keep_edited = str(request.data.get("keep_edited", True)).lower() not in ("false", "0", "no")
        if not only_missing:
            # an Assign-anyway class (qualification_override) is ALWAYS kept, like a fixed assignment; other hand edits unless keep_edited=false
            kept_keys = set((scope_rows.filter(is_manual_override=True) if _keep_edited else scope_rows.filter(qualification_override__isnull=False))
                            .values_list("section_id", "subject_id"))
            if kept_keys:
                from django.db.models import Q as _Q
                keep_q = _Q(pk__in=[])
                for _sid, _subid in kept_keys:
                    keep_q |= _Q(section_id=_sid, subject_id=_subid)
                for _sec, _subs in subjects_by_section.items():
                    subjects_by_section[_sec] = [x for x in _subs if (_sec.id, x.id) not in kept_keys]
                kept_classes = sorted(f"{r[0]} ({r[1]} {r[2]})" for r in scope_rows.filter(keep_q).values_list(
                    "subject__code", "section__program__name", "section__name").distinct())
                scope_rows = scope_rows.exclude(keep_q)
        # Professor chosen per subject in the preview: re-checked here (role, college, qualification, availability, Lec/Lab pair)
        # BEFORE any draft is replaced, so a refused choice changes nothing.
        from . import professor_choice as _pc
        _t_err, _teacher_choices, _qual_overrides = _pc.validate(
            request.user, subjects_by_section, request.data.get("teacher_choices"), school_year, semester,
            windows=request.data.get("time_windows") or {}, replaced=list(scope_rows.values_list("pk", flat=True)))
        if _t_err:
            transaction.set_rollback(True)
            return Response({"detail": _t_err}, status=status.HTTP_400_BAD_REQUEST)
        replaced_drafts = scope_rows.count()
        scope_rows.delete()

        # Minor subjects another department already holds, with seats left in
        # that room, are JOINED (shared class) instead of scheduled again.
        merge_report = []
        from . import shared_classes as _sc
        _share_rules = _sc.share_rules(year_level, semester, kind)
        _merge_enabled = kind == "major" or str(request.data.get("merge_minors", True)).lower() not in ("false", "0", "no")
        if _merge_enabled:
            from .merging import join_minor_classes
            merge_report = join_minor_classes(subjects_by_section, school_year, rules=_share_rules, subject_kind=kind)

        teachers = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(user__is_active=True))   # a deactivated teacher is never given a class
        rooms = list(Room.objects.all())
        from .college_break import allowed_slots as _college_slots
        timeslots = _college_slots(list(TimeSlot.objects.all()))

        # Every Schedule row already in the database -- from an earlier
        # Generate click for a different program/year/semester, or a manual
        # edit -- must be treated as already-occupying its teacher/room/
        # section/timeslot OF THE SAME SEMESTER (1st and 2nd Sem never meet, so they may
        # reuse the same rooms and teachers). The DB enforces teacher/room vs. timeslot
        # uniqueness per semester (see Schedule.Meta.constraints), so without this the engine could pick a
        # combo this exact run has never seen before but that some earlier
        # run already took, and bulk_create below would then fail with an
        # IntegrityError instead of the engine simply avoiding it up front.
        existing_assignments = list(
            Schedule.objects.filter(section__semester=semester)
            .select_related("teacher", "teacher__user", "room", "section", "section__program", "timeslot", "subject")
        )

        availability_rules = _build_availability_rules(teachers, timeslots, school_year, semester)
        from . import availability as _avail
        _av_pref, _av_text = _avail.build(teachers, timeslots, school_year, semester)

        from . import workload as _wl
        _lim = _wl.limits()
        # Strict policy: the weekly-hour limit is a HARD rule for the engine (it simply won't give a
        # teacher more than their limit). Otherwise the result is checked afterwards and warned about.
        teacher_caps = {t.id: _wl.limit_for(t, _lim) for t in teachers} if _lim["policy"] == "strict" else None
        _ov_map = {}
        if _qual_overrides:
            from . import faculty_groups as _fg
            _by_id = {t.id: t for t in teachers}
            for _sid in _qual_overrides:
                _tid = _teacher_choices[_sid]
                _ov_map[_sid] = {"teacher": _tid, "blocked": _fg.strict_blocked_slots(_tid, timeslots, school_year, semester)}
                if _tid in _by_id:
                    teacher_caps = dict(teacher_caps or {})
                    teacher_caps.setdefault(_tid, _wl.limit_for(_by_id[_tid], _lim))

        t1 = time.time()
        # The Dean's preferred / alternative / fixed rooms for the subjects being generated.
        from rooms import rules as _room_rules
        room_assign = _room_rules.load_assignments({sub.id for subs in subjects_by_section.values() for sub in subs})
        # Room / Start / End chosen in the curriculum preview (this run only): the chosen room is tried first for that subject
        # (kept ahead of the saved preferred room), and the start-end time is a hard window for its classes.
        _pre_err, _choices, _windows = _preview_choices(request, subjects_by_section, rooms)
        if _pre_err:
            # undo everything this request did so far (the replaced drafts, any shared-class joins): a refused choice changes nothing
            transaction.set_rollback(True)
            return Response({"detail": _pre_err}, status=status.HTTP_400_BAD_REQUEST)
        for _sid, _rid in _choices.items():
            _old = room_assign.get(_sid) or {"alts": [], "fixed": False}
            # the Dean's pick for THIS run is kept: the engine searches other days and times inside this room, never another room
            room_assign[_sid] = {"preferred": _rid, "alts": [x for x in _old["alts"] if x != _rid], "fixed": True}
        # Confirmed shared classes: the host section's room is sized for every member, and its time must be free for them too.
        share_plans, _sizes, _busy = [], {}, {}
        if _merge_enabled:
            _claimed_shared_sections = set()
            for sec_, subs_ in subjects_by_section.items():
                for sub_ in subs_:
                    if sub_.lab_units == 0:
                        members, total = _sc.plan_members(sec_, sub_, _share_rules, _claimed_shared_sections)
                        if members:
                            share_plans.append((sec_, sub_, members))
                            _sizes[(sec_.id, sub_.id)] = total
                            _busy[(sec_.id, sub_.id)] = _sc.busy_intervals([m.id for m in members], ignore_subject_id=sub_.id)
        _gtok = _room_rules.use_group_sizes({**_room_rules.current_group_sizes(), **_sizes})
        _btok = _room_rules.use_share_busy(_busy)
        _tok = _room_rules.use_assignments(room_assign)
        _ttok = _room_rules.use_time_windows(_windows)
        # the day the Dean assigned from the Faculty time window (optional): that subject is placed on that day only
        _dtok = _room_rules.use_day_choices({int(k): str(w["day"])[:3].title() for k, w in (request.data.get("time_windows") or {}).items()
                                             if isinstance(w, dict) and w.get("day") and str(k).isdigit()})
        _ptok = _room_rules.use_teacher_choices(_teacher_choices)
        _otok = _room_rules.use_qualification_overrides(_ov_map)      # the Dean's manual Assign anyway pins (empty almost always)
        _atok = _avail.use(_av_pref, _av_text)
        from . import lunch_gap as _lunch
        _lgon = _lunch.enabled_in_settings()                 # "Reserve lunch gap (optional)": soft, OFF by default
        _ltok = _lunch.use(_lgon)
        try:
            assignments, unresolved, phase_breakdown = generate_schedule_two_phase(
                subjects_by_section, teachers, rooms, timeslots, availability_rules,
                existing_assignments=existing_assignments,
                dept_building={d.department: d.building for d in DepartmentBuilding.objects.all()},
                teacher_caps=teacher_caps,
            )
            # unresolved reasons are built inside the engine while the assignments are still active
        finally:
            _room_rules.release_assignments(_tok)
            _room_rules.release_time_windows(_ttok)
            _room_rules.release_day_choices(_dtok)
            _room_rules.release_teacher_choices(_ptok)
            _room_rules.release_qualification_overrides(_otok)
            _avail.release(_atok)
            _lunch.release(_ltok)
            _room_rules.release_share_busy(_btok)
            _room_rules.release_group_sizes(_gtok)
        t2 = time.time()
        room_notes = []
        _rooms_by_id = {r.id: r for r in rooms}
        _seen_notes = set()
        for a_ in assignments:
            asg = room_assign.get(a_.subject.id)
            if not asg or not asg["preferred"] or a_.room.id == asg["preferred"]:
                continue
            key = (a_.subject.id, a_.section.id, a_.room.id)
            if key in _seen_notes:
                continue
            _seen_notes.add(key)
            pref = _rooms_by_id.get(asg["preferred"])
            room_notes.append(f"{a_.subject.title} ({a_.section.name}): preferred room {pref.name if pref else ''} was busy, "
                              f"placed in {a_.room.name}" + (" (one of your alternatives)." if a_.room.id in asg["alts"] else "."))

        # bulk_create instead of one .create() per assignment -- looping .create() here was
        # another N+1 pattern (up to ~25 separate network round-trips to a remote DB).
        schedule_objs = [
            Schedule(
                subject=a.subject, teacher=a.teacher, room=a.room, section=a.section, timeslot=a.timeslot,
                school_year=school_year, status="draft", term=a.section.semester,
                # an Assign-anyway class is kept by later Generate runs like a class edited by hand
                **({"is_manual_override": True, "qualification_override": _qual_overrides[a.subject.id]}
                   if a.subject.id in _qual_overrides and a.teacher.id == _teacher_choices.get(a.subject.id) else {}),
            )
            for a in assignments
        ]
        created_objs = Schedule.objects.bulk_create(schedule_objs)
        if _qual_overrides:
            from . import faculty_groups as _fg
            _fg.log_overrides(request.user, [o for o in created_objs if o.qualification_override], "Generate")
        created = [obj.id for obj in created_objs if obj.id is not None]
        created += [i for m in merge_report for i in m["schedule_ids"]]
        shared_report = _sc.extend_to_members(share_plans, created_objs, school_year) if share_plans else []
        created += [i for m in shared_report for i in m["schedule_ids"]]
        t3 = time.time()

        print(
            f"[generate_schedule_view] data-fetch={t1-t0:.2f}s  "
            f"csp-engine={t2-t1:.2f}s  bulk-insert={t3-t2:.2f}s  total={t3-t0:.2f}s  "
            f"placed={len(assignments)}  unresolved={len(unresolved)}  phases={phase_breakdown}"
        )

        # A class the greedy search could not place in the Dean's / Registrar's chosen room and time is NOT fixed behind their back
        # (no other class is moved automatically). It is reported with its reason; the pop-up then lists the free days / times in
        # the SAME room (inside the chosen window first) and nothing changes until the owner picks one and confirms
        # (engine.reschedule.suggest / apply).
        auto_resolved = []
        conflict_report = [
            {"section": str(v[0]), "subject": str(v[1]), "period_index": v[2], "section_id": v[0].id, "subject_id": v[1].id,
             "program_id": v[0].program_id, "year_level": v[0].year_level, "reason": plain_reason(getattr(v, "reason", "")),
             "code": v[1].code, "title": v[1].title,
             "classification": v[1].classification, "department": v[0].program.department,
             # what the owner chose in the preview, so the pop-up shows it instead of "not assigned"
             "chosen_room_id": _choices.get(v[1].id), "chosen_room": (_rooms_by_id[_choices[v[1].id]].name if _choices.get(v[1].id) in _rooms_by_id else ""),
             "chosen_start": (f"{_windows[v[1].id][0] // 60:02d}:{_windows[v[1].id][0] % 60:02d}" if v[1].id in _windows else ""),
             "chosen_end": (f"{_windows[v[1].id][1] // 60:02d}:{_windows[v[1].id][1] % 60:02d}" if v[1].id in _windows else ""),
             "chosen_teacher_id": _teacher_choices.get(v[1].id)}
            for v in {(u[0].id, u[1].id): u for u in unresolved}.values()
        ]

        # Workload check of the generated result (every schedule of the semester counted, shared
        # minor classes once), with the lowest-priority generated class named and replacement ideas.
        workload_warnings = _wl.generation_warnings({a.teacher.id for a in assignments}, semester)
        for w in workload_warnings:
            mine = [a for a in assignments if a.teacher.id == w["faculty_id"]]
            if mine:
                last = mine[-1]
                grp = [a.timeslot for a in mine if a.subject.id == last.subject.id and a.section.id == last.section.id]
                w["conflicting_assignment"] = f"{last.subject} - {last.section}"
                w["replacement_suggestions"] = _wl.suggest_replacements(
                    last.subject, semester, grp, exclude_teacher_ids=[w["faculty_id"]], school_year=school_year,
                    user=request.user, section=last.section)
            Log.objects.create(action="CREATE", schedule_id=0, user=request.user,
                               details=f"WORKLOAD WARNING (generation): {w['message']}")

        # Persist to ConflictLog -- previously this report only ever existed in the
        # single API response and was lost afterward.
        ConflictLog.objects.bulk_create([
            ConflictLog(
                conflict_type="unresolved_csp",
                description=(f"Could not place {v[1]} for {v[0]} (class block {v[2] + 1}). "
                             f"{getattr(v, 'reason', '')}")[:500],
                section=v[0],
                school_year=school_year,  # was missing -- broke filtering/reporting by year
                semester=semester,
            )
            for v in unresolved
        ])
    except Exception as exc:
        traceback.print_exc()
        from . import locks as _locks
        return Response(
            {"detail": _locks.explain(exc) or f"Schedule generation hit an unexpected error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Automatic conflict check of what was just created against EVERYTHING already scheduled.
    try:
        from .conflict_report import scan as _scan
        clash = _scan(semester=semester, involving_ids=set(created)) if created else {"total": 0, "counts": {}, "conflicts": [], "checked": 0}
    except Exception:                              # the report is informational; never fail a finished generation
        clash = {"total": 0, "counts": {}, "conflicts": [], "checked": 0}

    return Response({
        "created_schedule_ids": created,
        "clashes": clash,
        "merged_classes": [{k: v for k, v in m.items() if k != "schedule_ids"} for m in merge_report],
        "shared_classes": [{k: v for k, v in m.items() if k != "schedule_ids"} for m in shared_report],
        "conflicts": conflict_report,
        "auto_resolved": [{"section": r["section"], "subject": r["subject"], "method": r["method"], "moved": r["moved"]}
                          for r in auto_resolved],
        "phase_breakdown": {
            "minor": {"placed": phase_breakdown["minor"][0], "unresolved": phase_breakdown["minor"][1]},
            "major": {"placed": phase_breakdown["major"][0], "unresolved": phase_breakdown["major"][1]},
        },
        "workload_warnings": workload_warnings,
        # optional lunch gap: a warning (never an error) for each section / professor day this run could not keep a free hour in
        "lunch_gap_warnings": (_lunch.warnings(list(existing_assignments) + list(assignments),
                                               sections={a.section.id for a in assignments},
                                               teachers={a.teacher.id for a in assignments})[:40] if _lgon and assignments else []),
        "room_notes": room_notes[:25],
        "kept_edited": kept_classes,
        "only_missing": only_missing,
        "missing_untouched": missing_untouched,
        "workload_policy": _lim["policy"],
        "status": "complete" if not conflict_report else "partial",
        "kind": kind,
        "warning": ("" if (kind == "minor" or other_kind_exists) else
                    "The Registrar has not generated the Gen Ed subjects for this year level and semester yet. "
                    "Your program subjects were placed first; the Gen Ed subjects will be fitted around them later."),
        "note": "Created as Draft. Use /api/engine/schedules/approve_bulk/ to move to Approved/Published.",
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def professor_options_view(request):
    """GET ?program_id=&year_level=&semester= -- READ-ONLY: the qualified teachers of the Dean's own college for each major subject,
    with their current weekly load and limit, for the optional Professor column of the Generate preview."""
    from curriculum.models import Program
    from . import professor_choice as _pc
    u = request.user
    is_dean = getattr(u, "role", "") == "faculty" and getattr(u, "faculty_type", "") == "dean"
    if not (is_dean or getattr(u, "role", "") == "registrar"):
        return Response({"detail": "Only a Dean (program subjects) or the Registrar (Gen Ed subjects) chooses professors."}, status=403)
    q = request.query_params
    try:
        program = Program.objects.get(pk=int(q.get("program_id")))
    except (TypeError, ValueError, Program.DoesNotExist):
        return Response({"detail": "Choose a program."}, status=400)
    if is_dean and program.department not in (u.departments or []):
        return Response({"detail": "You can only choose professors for programs in your own college."}, status=403)
    if not q.get("year_level") or not q.get("semester"):
        return Response({"detail": "year_level and semester are required."}, status=400)
    return Response(_pc.options(program, q.get("year_level"), q.get("semester"), user=u, kind="major" if is_dean else "minor"))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def professor_groups_view(request):
    """GET ?program_id=&year_level=&semester=&subject_id=[&day=&start=&end=] -- READ-ONLY: the three Professor groups of one subject row
    of the Generate dialog after the Dean set its Day / Start / End (engine.faculty_groups)."""
    from curriculum.models import Program, Subject
    from . import professor_choice as _pc
    u, q = request.user, request.query_params
    is_dean = getattr(u, "role", "") == "faculty" and getattr(u, "faculty_type", "") == "dean"
    if not (is_dean or getattr(u, "role", "") == "registrar"):
        return Response({"detail": "Only a Dean (program subjects) or the Registrar (Gen Ed subjects) chooses professors."}, status=403)
    kind = "major" if is_dean else "minor"
    try:
        program = Program.objects.get(pk=int(q.get("program_id")))
        subject = Subject.objects.get(pk=int(q.get("subject_id")), program=program, classification=kind)
    except (TypeError, ValueError, Program.DoesNotExist, Subject.DoesNotExist):
        return Response({"detail": "Choose a program and subject."}, status=400)
    if is_dean and program.department not in (u.departments or []):
        return Response({"detail": "You can only choose professors for programs in your own college."}, status=403)
    semester, year_level = q.get("semester"), q.get("year_level")
    sections = list(Section.objects.filter(program=program, year_level=year_level, semester=semester).select_related("program"))
    if not sections:
        return Response({"detail": "This year level has no section."}, status=400)
    replaced = list(Schedule.objects.filter(section__in=sections, subject__classification=kind, status="draft",
                                            is_manual_override=False).values_list("pk", flat=True))
    win, day = _pc._window({"start": q.get("start") or "", "end": q.get("end") or "", "day": q.get("day") or ""})
    return Response(_pc.subject_groups(u, subject, sections, semester, replaced, window=win, day=day))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def faculty_time_view(request):
    """GET ?faculty_id=&semester=[&program_id=&year_level=] -- READ-ONLY: a teacher's availability, weekly load and current classes,
    for the info button next to the Professor dropdown. A Dean sees only faculty of their own college(s); the Registrar any
    active faculty (Gen Ed is taught by every college); nobody else."""
    from curriculum.models import Program
    from . import professor_choice as _pc
    u, q = request.user, request.query_params
    is_dean = getattr(u, "role", "") == "faculty" and getattr(u, "faculty_type", "") == "dean"
    if not (is_dean or getattr(u, "role", "") == "registrar"):
        return Response({"detail": "Only a Dean or the Registrar can see faculty time here."}, status=403)
    if not q.get("semester"):
        return Response({"detail": "Choose a semester."}, status=400)
    try:
        p = FacultyProfile.objects.select_related("user").get(pk=int(q.get("faculty_id")), user__is_active=True)
    except (TypeError, ValueError, FacultyProfile.DoesNotExist):
        return Response({"detail": "No such faculty member."}, status=404)
    if is_dean and not set(p.user.departments or []) & set(u.departments or []):
        return Response({"detail": "You can only see the faculty of your own college."}, status=403)
    program = None
    if q.get("program_id"):
        program = Program.objects.filter(pk=q.get("program_id")).first()
        if program is not None and is_dean and program.department not in (u.departments or []):
            program = None
    return Response(_pc.faculty_time(p, q.get("semester"), program, q.get("year_level")))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def conflict_scan_view(request):
    """GET /api/engine/conflicts/?semester=  -- every teacher / room / student double-booking in the class schedule."""
    from .conflict_report import scan
    u = request.user
    is_dean = u.role == "faculty" and u.faculty_type == "dean"
    if not (u.role == "registrar" or is_dean or _is_it_admin(u)):
        return Response({"detail": "Only a Dean, the Registrar or IT Admin can run the conflict check."}, status=403)
    return Response(scan(semester=request.query_params.get("semester") or None,
                         departments=u.departments if is_dean else None))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def conflict_demo_view(request):
    """POST {action: "add" | "remove"} -- sample conflicts for demonstrating the detection (tagged, removable)."""
    from .conflict_report import add_demo_conflicts, remove_demo_conflicts
    u = request.user
    is_dean = u.role == "faculty" and u.faculty_type == "dean"
    if not (u.role == "registrar" or is_dean or _is_it_admin(u)):
        return Response({"detail": "Only a Dean, the Registrar or IT Admin can do this."}, status=403)
    if request.data.get("action") == "remove":
        return Response({"removed": remove_demo_conflicts()})
    try:
        with transaction.atomic():
            made = add_demo_conflicts(u.departments if is_dean else None)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    return Response({"created": made})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def conflict_resolve_view(request):
    """POST {kind, a_ids, b_ids}  -> fix that one conflict;  POST {all: true, semester?} -> fix every conflict it can."""
    from .conflict_resolve import resolve_all, resolve_pair
    u = request.user
    is_dean = u.role == "faculty" and u.faculty_type == "dean"
    if not (u.role == "registrar" or is_dean):
        return Response({"detail": "Only a Dean or the Registrar can resolve conflicts."}, status=403)
    d = request.data
    if str(d.get("all", "")).lower() in ("1", "true", "yes"):
        return Response(resolve_all(u, semester=d.get("semester") or None, departments=u.departments if is_dean else None))
    return Response(resolve_pair(d.get("kind"), d.get("a_ids") or [], d.get("b_ids") or [], u))


def _unplaced_scope(request, d):
    """Classes of the request's scope that are not fully placed, limited to what this account is allowed to place."""
    from .placement import incomplete_groups
    u = request.user
    is_dean = u.role == "faculty" and u.faculty_type == "dean"
    if not (u.role == "registrar" or is_dean):
        return None
    return incomplete_groups(
        d.get("semester"), program_id=d.get("program_id") or None, year_level=d.get("year_level") or None,
        section_id=d.get("section_id") or None, subject_id=d.get("subject_id") or None,
        kind="minor" if u.role == "registrar" else "major", departments=u.departments if is_dean else None)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def unplaced_list_view(request):
    """GET ?semester=&program_id=&year_level= -> the classes still without a full schedule (Registrar: Gen Ed; Dean: own majors)."""
    if not request.query_params.get("semester"):
        return Response({"detail": "Choose a semester."}, status=400)
    found = _unplaced_scope(request, request.query_params)
    if found is None:
        return Response({"detail": "Only a Dean or the Registrar can do this."}, status=403)
    reasons = _last_skip_reasons(found, request.query_params.get("semester"))
    return Response({"total": len(found), "items": [
        {"section": str(s), "subject": str(b), "section_id": s.id, "subject_id": b.id, "program_id": s.program_id,
         "program": s.program.name, "department": s.program.department, "year_level": s.year_level,
         "code": b.code, "title": b.title, "section_name": s.name,
         "placed_minutes": have, "needed_minutes": need,
         "reason": reasons.get((s.id, b.id)) or ("Not generated yet." if have == 0 else "Only partly placed.")}
        for s, b, have, need in found]})


def _last_skip_reasons(found, semester):
    """{(section_id, subject_id): reason} from the newest "could not place" log of each class (read-only)."""
    if not found:
        return {}
    want = {(s.id, f"Could not place {b} for {s} "): (s.id, b.id) for s, b, _h, _n in found}
    out = {}
    logs = (ConflictLog.objects.filter(conflict_type="unresolved_csp", section_id__in={s.id for s, _b, _h, _n in found})
            .order_by("-occurred_at").values_list("section_id", "description"))
    if semester:
        logs = logs.filter(semester=semester)
    for sec_id, desc in logs[:2000]:
        for (sid, prefix), key in want.items():
            if sid == sec_id and key not in out and desc.startswith(prefix):
                rest = desc.split("). ", 1)[1] if "). " in desc else ""
                out[key] = plain_reason(rest)
    return out


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def unplaced_resolve_view(request):
    """POST {semester, school_year?, section_id?, subject_id?, program_id?, year_level?} -> place the unplaced classes of that scope
    (one class, or all of them) by re-arranging what is in their way. All changes are validated; failures are undone."""
    d = request.data
    if not d.get("semester"):
        return Response({"detail": "Choose a semester."}, status=400)
    found = _unplaced_scope(request, d)
    if found is None:
        return Response({"detail": "Only a Dean or the Registrar can place classes."}, status=403)
    from .placement import incomplete_groups, resolve_groups
    sy = d.get("school_year") or ""
    try:
        with transaction.atomic():
            out = resolve_groups(request.user, [(s, b) for s, b, _h, _n in found], d["semester"], sy)
    except Exception as exc:                                    # never a bare 500
        import traceback; traceback.print_exc()
        return Response({"detail": f"Could not place the classes: {exc}"}, status=500)
    left = _unplaced_scope(request, d) or []
    placed = [r for r in out["results"] if r["status"] == "placed"]
    return Response({"requested": len(found), "placed": len(placed), "remaining": len(left),
                     "results": out["results"], "validated": True})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def minor_generate_all_view(request):
    """POST {school_year, semester, year_level ("1st Year".."4th Year" or "All")} -> minor schedules of CCS, RadTech, Nursing,
    BAComm, Allied Health, IHM and BA in one validated, all-or-nothing action (Registrar only)."""
    from .minor_batch import generate_all
    if request.user.role != "registrar":
        return Response({"detail": "Only the Registrar generates the Gen Ed (minor) schedules."}, status=403)
    d = request.data
    from audit import recorder as _audit
    with _audit.batch("generate", "schedule", "Gen Ed (all colleges)",
                      summary=f"Generate Gen Ed {d.get('year_level') or ''} {d.get('semester') or ''}".strip()) as _ab:
        payload, code = generate_all(request.user, d.get("school_year"), d.get("semester"), d.get("year_level"))
        if code >= 300:
            _ab["items"].clear()               # refused / rolled back: nothing changed, nothing to log
    return Response(payload, status=code)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def minor_comparison_view(request):
    """GET ?semester=&year_level= -> the four departments' minor schedules side by side (shared / separate / conflicts)."""
    from .minor_batch import comparison
    u = request.user
    if not (u.role == "registrar" or (u.role == "faculty" and u.faculty_type == "dean") or _is_it_admin(u)):
        return Response({"detail": "Not allowed."}, status=403)
    sem = request.query_params.get("semester")
    if not sem:
        return Response({"detail": "Choose a semester."}, status=400)
    return Response(comparison(sem, request.query_params.get("year_level")))


class SchedulingConfigView(viewsets.ViewSet):
    """Singleton settings endpoint -- currently just the student-overlap grace
    window (default 30 min) Dean Villanueva described. Anyone logged in can
    read it (so the Faculty/Dean UI can show it); only Registrar may change it."""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        return Response(SchedulingConfigSerializer(SchedulingConfig.get_solo()).data)

    def partial_update(self, request, pk=None):
        if request.user.role != "registrar" and not _is_it_admin(request.user):
            return Response({"detail": "Only the Registrar or IT Admin may change scheduling policy."}, status=status.HTTP_403_FORBIDDEN)
        config = SchedulingConfig.get_solo()
        serializer = SchedulingConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def suggest_substitute_view(request):
    """
    Body: { "absence_id": ... }

    Dean Villanueva's interview, verbatim intent: when a faculty becomes
    unavailable, the system should recommend who could cover their classes.
    This is framed as a coverage suggestion among EXISTING faculty, not a
    dedicated substitute-teacher pool (there isn't one).

    For every Schedule row the absent faculty teaches on that date's weekday,
    runs find_substitute() and records a CoverageSuggestion. Returns the
    suggestions so the Dean/Registrar can review before anything is applied.
    """
    absence_id = request.data.get("absence_id")
    absence = Absence.objects.select_related("faculty__user").filter(pk=absence_id).first()
    if not absence:
        return Response({"detail": "Absence not found."}, status=status.HTTP_404_NOT_FOUND)

    weekday_abbrev = absence.date.strftime("%a")  # "Mon", "Tue", ...
    affected = Schedule.objects.select_related("subject", "timeslot", "teacher", "section").filter(
        teacher=absence.faculty, timeslot__day=weekday_abbrev,
    )
    if absence.semester:
        affected = affected.filter(section__semester=absence.semester)

    teachers = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(user__is_active=True))   # never suggest a deactivated teacher
    from .college_break import allowed_slots as _college_slots
    timeslots = _college_slots(list(TimeSlot.objects.all()))
    availability_rules = _build_availability_rules(teachers, timeslots, absence.school_year, absence.semester)

    # Current workload = how many periods each teacher is already assigned,
    # used as the substitute tiebreaker (lowest load first).
    from django.db.models import Count
    workload_counts = {
        row["teacher_id"]: row["c"]
        for row in Schedule.objects.values("teacher_id").annotate(c=Count("id"))
    }

    # A class is stored one row per time slot; group each class's rows for that
    # day into ONE block so the Dean sees one suggestion per class (not one per
    # hour) and the substitute is free for the WHOLE block.
    from collections import OrderedDict
    from .scheduler import BlockSlot
    from faculty.serializers import display_name
    groups = OrderedDict()
    for row in sorted(affected, key=lambda r: (r.subject_id, r.section_id, r.timeslot.start_time)):
        groups.setdefault((row.subject_id, row.section_id), []).append(row)

    results = []
    for rows in groups.values():
        rows.sort(key=lambda r: r.timeslot.start_time)
        row = rows[0]
        start, end = rows[0].timeslot.start_time, rows[-1].timeslot.end_time
        block = BlockSlot([r.timeslot for r in rows])
        already = CoverageSuggestion.objects.filter(absence=absence, schedule=row, applied=True).select_related(
            "suggested_faculty__user").first()
        if already is not None:                 # never overwrite coverage that was already applied
            results.append({
                "coverage_suggestion_id": already.id, "schedule_id": row.id, "subject": str(row.subject),
                "subject_field": row.subject.field.name if row.subject.field_id else None,
                "section": str(row.section),
                "timeslot": f"{row.timeslot.day} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
                "suggested_faculty_id": already.suggested_faculty_id,
                "suggested_faculty_name": display_name(already.suggested_faculty.user) if already.suggested_faculty else None,
                "suggested_faculty_specializations": [], "reason": "Already applied.",
            })
            continue
        busy_teacher_ids = set(
            Schedule.objects.filter(timeslot__day=row.timeslot.day, section__semester=row.section.semester,
                                    timeslot__start_time__lt=end,
                                    timeslot__end_time__gt=start)
            .exclude(pk__in=[r.pk for r in rows]).values_list("teacher_id", flat=True)
        )
        suggestion = find_substitute(
            absence.faculty, block, row.subject, teachers, workload_counts, availability_rules,
            busy_teacher_ids=busy_teacher_ids,
        )
        reason = ""
        if suggestion:
            same_field = row.subject.field_id is not None and any(
                f.id == row.subject.field_id for f in suggestion.specializations.all())
            reason = "Same specialization, lowest current load" if same_field else "No specialization match -- lowest-load faculty who is free"

        cs, _ = CoverageSuggestion.objects.update_or_create(
            absence=absence, schedule=row,
            defaults={"suggested_faculty": suggestion, "reason": reason},
        )
        # the class's other hourly rows are covered by this one suggestion
        CoverageSuggestion.objects.filter(absence=absence, schedule__in=rows[1:]).delete()
        results.append({
            "coverage_suggestion_id": cs.id,
            "schedule_id": row.id,
            "subject": str(row.subject),
            "subject_field": row.subject.field.name if row.subject.field_id else None,
            "section": str(row.section),
            "timeslot": f"{row.timeslot.day} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
            "suggested_faculty_id": suggestion.id if suggestion else None,
            "suggested_faculty_name": display_name(suggestion.user) if suggestion else None,
            "suggested_faculty_specializations": [f.name for f in suggestion.specializations.all()] if suggestion else [],
            "reason": reason or "No qualified, free faculty found for this slot.",
        })

    absence.coverage_status = "suggested" if results else absence.coverage_status
    absence.save(update_fields=["coverage_status"])

    return Response({"absence_id": absence.id, "suggestions": results})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def apply_coverage_suggestion_view(request):
    """
    Body: { "coverage_suggestion_id": ... }
    Marks a suggested coverage as applied (a Dean/Registrar decision, not an
    automatic one) and logs it. Deliberately does NOT rewrite the recurring
    Schedule row's teacher -- that row is the standing weekly assignment, and
    this is a one-date absence, so permanently reassigning it would be wrong.
    This records who is actually covering that date for visibility/reporting.
    """
    cs_id = request.data.get("coverage_suggestion_id")
    cs = CoverageSuggestion.objects.select_related("schedule", "suggested_faculty__user", "absence").filter(pk=cs_id).first()
    if not cs:
        return Response({"detail": "Coverage suggestion not found."}, status=status.HTTP_404_NOT_FOUND)
    if not cs.suggested_faculty:
        return Response({"detail": "This suggestion has no eligible covering faculty to apply."}, status=status.HTTP_400_BAD_REQUEST)
    if cs.applied:
        return Response({"detail": "This coverage was already applied."}, status=status.HTTP_409_CONFLICT)

    cs.applied = True
    cs.save(update_fields=["applied"])
    cs.absence.coverage_status = "applied"
    cs.absence.save(update_fields=["coverage_status"])

    from notifications.models import Notification
    Notification.objects.create(
        recipient=cs.suggested_faculty.user, notif_type="substitute_assignment",
        message=f"You've been assigned to cover {cs.schedule.subject.title} "
                f"({cs.schedule.section.name}) on {cs.absence.date} for "
                f"{cs.absence.faculty.user.get_full_name() or cs.absence.faculty.user.username}'s absence.",
    )

    Log.objects.create(
        action="UPDATE", schedule_id=cs.schedule_id, user=request.user,
        details=f"Applied coverage: {cs.suggested_faculty.user.username} covers "
                f"{cs.schedule} on {cs.absence.date} for {cs.absence.faculty.user.username}'s absence.",
    )
    return Response({"applied": True, "covering_faculty": cs.suggested_faculty.user.username})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def export_schedule_pdf(request):
    """
    GET /api/engine/export-pdf/?program_id=&year_level=&semester=&department=&status=
    Returns a downloadable PDF matching UPHSL's own printed schedule format.
    """
    from .pdf_export import build_schedule_pdf
    from curriculum.models import Program

    _u = request.user
    # Deans print their own college(s); the Registrar prints any college / program, following the Schedules tab's filters
    if not ((_u.role == "faculty" and _u.faculty_type == "dean") or _u.role == "registrar"):
        return Response({"detail": "Only a Dean or the Registrar can preview or print the class schedule."},
                        status=status.HTTP_403_FORBIDDEN)

    program_id = request.query_params.get("program_id")
    year_level = request.query_params.get("year_level")
    semester = request.query_params.get("semester")
    department = request.query_params.get("department")
    status_filter = request.query_params.get("status")
    classification = request.query_params.get("classification")     # "major" | "minor" | "" (both)
    export_format = (request.query_params.get("format") or "pdf").lower()
    if export_format not in {"pdf", "xlsx", "csv"}:
        return Response({"detail": "Choose pdf, xlsx, or csv for the report format."}, status=status.HTTP_400_BAD_REQUEST)

    qs = Schedule.objects.select_related("subject", "teacher__user", "room", "section", "timeslot", "section__program")
    if classification in ("major", "minor"):
        qs = qs.filter(subject__classification=classification)
    if program_id:
        qs = qs.filter(section__program_id=program_id)
    if year_level:
        qs = qs.filter(section__year_level=year_level)
    if semester:
        qs = qs.filter(section__semester=semester)
    if department:
        qs = qs.filter(section__program__department=department)
    if status_filter:
        qs = qs.filter(status=status_filter)

    user = request.user
    if user.role == "faculty" and user.faculty_type == "dean":
        qs = qs.filter(section__program__department__in=user.departments)
    elif user.role == "faculty":
        qs = qs.filter(teacher__user=user)
    elif user.role == "student":
        # Same safe-default reasoning as ScheduleViewSet.get_queryset -- no
        # Enrollment model exists yet, so return nothing rather than leaking
        # the whole institution's schedule to a student via direct API call.
        qs = qs.none()

    program_name = ""
    if program_id:
        program = Program.objects.filter(pk=program_id).first()
        program_name = program.name if program else ""

    title = "Schedules" if not program_name else f"{program_name} Schedules"
    if classification == "minor":
        title = "Gen Ed Schedules"
    subtitle = ""
    workspace_label = "REGISTRAR WORKSPACE"
    if user.role == "faculty" and user.faculty_type == "dean":
        workspace_label = f"{' & '.join(user.departments).upper()} · DEAN VIEW"
    elif user.role == "faculty":
        workspace_label = "MY SCHEDULE"

    if not qs.exists():
        return Response({"detail": "No schedule entries found for the given filters."}, status=status.HTTP_404_NOT_FOUND)

    # Never print a clashing table without saying so: check the classes in THIS table against the whole schedule first.
    from .conflict_report import scan as _scan
    _ids = set(qs.values_list("id", flat=True))
    _clash = _scan(semester=semester or None, involving_ids=_ids, limit=20)
    if _clash["total"] and str(request.query_params.get("allow_conflicts", "")).lower() not in ("1", "true", "yes"):
        return Response({"detail": f"This table has {_clash['total']} conflict(s): a teacher, room or section is booked for two classes "
                                   "at the same time. Fix them in the Conflicts tab before printing.",
                         "conflicts": _clash["conflicts"], "total": _clash["total"]}, status=status.HTTP_409_CONFLICT)
    if _clash["total"]:
        subtitle = (f'<font color="#b91c1c"><b>NOT FINAL: {_clash["total"]} unresolved conflict(s) in this table. '
                    "Resolve them in the Conflicts tab and print again.</b></font>")

    if export_format in {"xlsx", "csv"}:
        headers = ["Semester / Term", "Year Level", "College", "Program", "Section", "Subject Code", "Subject",
                   "Subject Type", "Day", "Start Time", "End Time", "Room", "Faculty", "Status", "Report Note"]
        report_note = f"NOT FINAL: {_clash['total']} unresolved conflict(s)" if _clash["total"] else ""
        rows = [[s.section.semester, s.section.year_level, s.section.program.department or "", s.section.program.name,
                 s.section.name, s.subject.code, s.subject.title, s.subject.classification,
                 s.timeslot.day, s.timeslot.start_time.strftime("%I:%M %p"), s.timeslot.end_time.strftime("%I:%M %p"),
                 s.room.name, s.teacher.user.get_full_name().strip() or s.teacher.user.username, s.status, report_note]
                for s in qs.order_by("section__semester", "section__program__name", "section__year_level", "section__name",
                                     "timeslot__day", "timeslot__start_time", "subject__code")]
        if export_format == "csv":
            import csv
            import io
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(headers)
            def csv_safe(value):
                value = str(value or "")
                return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
            writer.writerows([[csv_safe(value) for value in row] for row in rows])
            response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="class_schedule.csv"'
            return response

        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Class Schedule"
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="003366")
        for row in rows:
            sheet.append(row)
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 36)
        output = BytesIO()
        workbook.save(output)
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="class_schedule.xlsx"'
        return response

    departments = sorted({d for d in qs.values_list("section__program__department", flat=True).distinct() if d})
    pdf_buffer = build_schedule_pdf(
        list(qs), title, subtitle,
        workspace_label=workspace_label,
        source_url=request.build_absolute_uri("/dashboard"),
        departments=departments,
        year_level=year_level, semester=semester,
    )
    response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
    # "inline" (not "attachment") -- opens as a preview/print tab instead of
    # silently saving to the Downloads folder. The frontend currently builds
    # its own Blob from this response and ignores this header either way
    # (see downloadPdf() in FacultyDashboard.js / RegistrarDashboard.js), but
    # this keeps the raw endpoint correct for any other caller.
    response["Content-Disposition"] = 'inline; filename="class_schedule.pdf"'
    return response


# ---------------------------------------------------------------------------
# Faculty workload monitoring
# ---------------------------------------------------------------------------
def _workload_scope(user):
    """Which faculty profiles this user may see workload for."""
    qs = FacultyProfile.objects.select_related("user").filter(user__is_active=True)
    if user.role == "registrar" or _is_it_admin(user):
        return qs
    if user.role == "faculty" and user.faculty_type == "dean":
        return qs.filter(user__department__in=user.departments)
    if user.role == "faculty":
        return qs.filter(user=user)
    return qs.none()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def workload_list(request):
    """Every in-scope faculty member's current vs. permitted weekly hours (+ overload warning text)."""
    from . import workload as wl
    rows = wl.workload_rows(_workload_scope(request.user), term=request.query_params.get("term") or None)
    return Response({"limits": wl.limits(), "faculty": rows,
                     "overloaded": sum(1 for r in rows if r["overload_hours"] > 0)})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def workload_detail(request, faculty_id):
    """One teacher's workload, with the classes (subject + section, shared minors once) that make it up."""
    from . import workload as wl
    from collections import OrderedDict
    prof = _workload_scope(request.user).filter(pk=faculty_id).first()
    if prof is None:
        return Response({"detail": "Faculty member not found."}, status=status.HTTP_404_NOT_FOUND)
    row = wl.workload_rows([prof], term=request.query_params.get("term") or None)[0]
    groups = OrderedDict()
    rows = Schedule.objects.filter(teacher=prof, term=row["term"]).select_related(
        "subject", "section", "timeslot").order_by("subject_id", "merge_key", "section_id", "timeslot__day", "timeslot__start_time")
    seen = set()
    for sc in rows:
        k = (sc.subject_id, sc.merge_key or sc.section_id)
        g = groups.setdefault(k, {"subject": str(sc.subject), "subject_id": sc.subject_id, "sections": set(),
                                  "section_id": sc.section_id, "hours": 0.0, "schedule_ids": []})
        g["sections"].add(sc.section.name)
        g["schedule_ids"].append(sc.id)
        if (k, sc.timeslot_id) not in seen:
            seen.add((k, sc.timeslot_id))
            g["hours"] += wl._hours(sc.timeslot)
    classes = [{**g, "sections": sorted(g["sections"]), "hours": round(g["hours"], 2)} for g in groups.values()]
    return Response({**row, "limits": wl.limits(), "class_list": classes})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def workload_replacements(request):
    """Replacement faculty for one class: ?faculty_id=<current teacher>&subject_id=&section_id=
    (specialization, availability, no clash, enough remaining capacity)."""
    from . import workload as wl
    if request.user.role not in ("registrar", "faculty") and not _is_it_admin(request.user):
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
    if request.user.role == "faculty" and request.user.faculty_type != "dean":
        return Response({"detail": "Only a Dean or the Registrar can look up replacements."}, status=status.HTTP_403_FORBIDDEN)
    rows = Schedule.objects.filter(teacher_id=request.query_params.get("faculty_id"),
                                   subject_id=request.query_params.get("subject_id"),
                                   section_id=request.query_params.get("section_id")).select_related(
        "subject", "section", "timeslot")
    first = rows.first()
    if first is None:
        return Response({"detail": "Class not found."}, status=status.HTTP_404_NOT_FOUND)
    if request.user.role == "faculty" and first.section.program.department not in request.user.departments:
        return Response({"detail": "That class belongs to another college."}, status=status.HTTP_403_FORBIDDEN)
    diag = {}
    sugg = wl.suggest_replacements(first.subject, first.term, [r.timeslot for r in rows],
                                   exclude_teacher_ids=[first.teacher_id], school_year=first.school_year,
                                   exclude_schedule_ids=[], limit=8, diag=diag, user=request.user, section=first.section)
    return Response({"subject": str(first.subject), "section": str(first.section), "term": first.term,
                     "suggestions": sugg, "reason_none": "" if sugg else wl.no_available_text(diag),
                     "rejected": diag.get("rejected") or []})


def _overload_user(request):
    u = request.user
    if not (u.role == "registrar" or (u.role == "faculty" and u.faculty_type == "dean")):
        raise PermissionDenied("Only a Dean or the Registrar can resolve overloads.")
    return u


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def overload_summary(request):
    """The overloaded teachers (with their subjects) behind the warning banner -- includes outside teachers on this user's classes."""
    from . import overload
    return Response(overload.summary(_overload_user(request)))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def overload_plan(request):
    """Overloaded teachers in the user's scope, the classes they can move, and qualified / available / free people for each."""
    from . import overload
    return Response(overload.plan(_overload_user(request), request.query_params.get("term") or None))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def overload_assign(request):
    """body {schedule_ids: [...], teacher: <FacultyProfile id>} -> applies it to the real schedule after strict validation."""
    from . import overload
    user = _overload_user(request)
    try:
        return Response(overload.assign(user, request.data.get("schedule_ids") or [], request.data.get("teacher")))
    except overload.AssignError as e:
        return Response({"detail": e.detail, **e.extra}, status=e.code)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def workload_check(request):
    """Dry run before saving a teacher change on a class (all of its periods together):
    body {teacher: <FacultyProfile id>, schedule_ids: [...]} -> would this overload them?"""
    from . import workload as wl
    ids = request.data.get("schedule_ids") or []
    rows = list(Schedule.objects.filter(pk__in=ids).select_related("subject", "section", "section__program", "timeslot"))
    teacher = FacultyProfile.objects.select_related("user").filter(pk=request.data.get("teacher")).first()
    if not rows or teacher is None:
        return Response({"detail": "Class or teacher not found."}, status=status.HTTP_404_NOT_FOUND)
    for r in rows:
        if not can_edit_schedule_kind(request.user, r.subject.classification, getattr(r.section.program, "department", None)):
            return Response({"detail": "You cannot change this class."}, status=status.HTTP_403_FORBIDDEN)
    term = rows[0].term or rows[0].section.semester
    slots = [r.timeslot for r in rows]
    over = wl.check_assignment(teacher, term, slots, exclude_schedule_ids=ids)
    if over is None:
        return Response({"overloaded": False})
    policy = wl.limits()["policy"]
    diag = {}
    sugg = wl.suggest_replacements(rows[0].subject, term, slots, exclude_teacher_ids=[teacher.id, rows[0].teacher_id],
                                   school_year=rows[0].school_year, exclude_schedule_ids=ids, diag=diag,
                                   user=request.user, section=rows[0].section)
    return Response({
        "overloaded": True, "workload_overload": over, "detail": over["message"],
        "conflicting_assignment": f"{rows[0].subject} - {rows[0].section}",
        "can_override": policy != "strict", "policy": policy,
        "replacement_suggestions": sugg, "no_replacement_reason": "" if sugg else wl.no_available_text(diag),
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Home-page numbers for the Dean and the Registrar, counted from the database on every call (never cached): class periods by status,
    conflicts and overloaded teachers recomputed from the schedules that exist right now, and this user's latest notifications."""
    from django.db.models import Count
    from . import overload
    from .conflict_report import scan
    from notifications.models import Notification
    u = request.user
    is_dean = u.role == "faculty" and u.faculty_type == "dean"
    if not (u.role == "registrar" or is_dean):
        raise PermissionDenied("Only a Dean or the Registrar has this dashboard.")
    qs = Schedule.objects.all()
    if is_dean:
        qs = qs.filter(section__program__department__in=u.departments)
    by = {"draft": 0, "approved": 0, "published": 0}
    for row in qs.values("status").annotate(n=Count("id")):
        by[row["status"]] = by.get(row["status"], 0) + row["n"]
    total = sum(by.values())
    conflicts = scan(departments=u.departments if is_dean else None, limit=0)["total"] if total else 0
    overloaded = overload.summary(u)["overloaded"] if total else 0
    notes = Notification.objects.filter(recipient=u)
    resp = Response({
        "class_periods": total, "draft": by["draft"], "approved": by["approved"], "published": by["published"],
        "conflicts": conflicts, "overloaded": overloaded,
        "unread": notes.filter(is_read=False).count(),
        "notifications": [{"id": n.id, "message": n.message, "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in notes[:5]],
    })
    resp["Cache-Control"] = "no-store"
    return resp


def _reschedule_call(request, fn):
    from . import reschedule as rs
    d = request.data
    try:
        ids = [int(x) for x in (d.get("ids") or [])] or None
        kw = dict(ids=ids, section_id=d.get("section_id"), subject_id=d.get("subject_id"), room_id=int(d["room_id"]) if d.get("room_id") else None,
                  school_year=d.get("school_year") or "",
                  split_session=str(d.get("split_session", "false")).lower() in ("1", "true", "yes"))
        if d.get("start") or d.get("end"):
            from .scheduler import _slot_minutes
            a, b = _slot_minutes(d.get("start") or "00:00"), _slot_minutes(d.get("end") or "23:59")
            if b > a:
                kw["window"] = (a, b)
        if d.get("limit"):
            kw["limit"] = max(1, min(int(d["limit"]), 300))
        if d.get("teacher_id"):
            kw["teacher_id"] = int(d["teacher_id"])
            kw["override_qualification"] = str(d.get("override_qualification", "")).lower() in ("1", "true", "yes")
            kw["override_reason"] = str(d.get("override_reason") or "")[:300]
    except (TypeError, ValueError):
        return Response({"detail": "Invalid request."}, status=400)
    u = request.user
    if not (u.role == "registrar" or (u.role == "faculty" and u.faculty_type == "dean")):
        return Response({"detail": "Only a Dean or the Registrar can resolve scheduling problems."}, status=403)
    try:
        return Response(fn(rs, u, kw, d))
    except rs.RescheduleError as e:
        return Response({"detail": e.message, **e.extra}, status=e.status)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def slot_options(request):
    """Days / times a class can move to (or be placed at) with its CURRENT ROOM kept, every rule checked.
    Set split_session=true for one candidate 1.5-hour session of an eligible Gen Ed subject.
    """
    return _reschedule_call(request, lambda rs, u, kw, d: rs.suggest(u, **kw))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def slot_options_apply(request):
    """Body: same as slot-options + key, or split_session=true and session_keys=[key1,key2]."""
    return _reschedule_call(request, lambda rs, u, kw, d: rs.apply(
        u, key=d.get("key"), session_keys=d.get("session_keys"),
        **{k: v for k, v in kw.items() if k != "limit"}))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def unplaced_faculty_groups(request):
    """READ-ONLY. body {section_id, subject_id}: the three Professor groups for a class that was not placed ("See other available faculty")."""
    return _reschedule_call(request, lambda rs, u, kw, d: rs.unplaced_groups(u, d.get("section_id"), d.get("subject_id")))


def _shared_call(request, fn):
    from . import shared_classes as sc
    try:
        return Response(fn(sc, request.user, request.data))
    except sc.SharedError as e:
        return Response({"detail": e.message}, status=e.status)
    except (TypeError, ValueError, KeyError):
        return Response({"detail": "Invalid request."}, status=400)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def shared_options(request):
    """Subjects of one program / year / semester with their shared-class choice and compatible programs."""
    q = request.query_params
    return _shared_call(request, lambda sc, u, d: sc.options(u, int(q["program_id"]), q["year_level"], q["semester"], q.get("classification")))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_validate(request):
    from curriculum.models import Program
    def run(sc, u, d):
        sub = Subject.objects.select_related("program").filter(pk=int(d["subject_id"]), classification__in=("minor", "major")).first()
        if sub is None:
            raise sc.SharedError("Subject not found.", 404)
        if not sc._can_configure(u, sub.classification, sub.program):
            raise sc.SharedError("You do not have permission to configure sharing for this subject.", 403)
        ids = [sub.program_id] + [int(i) for i in d.get("program_ids", []) if int(i) != sub.program_id]
        if sub.classification == "major" and any(p.department != sub.program.department for p in Program.objects.filter(pk__in=ids)):
            raise sc.SharedError("Major classes can only be shared between programs in your own department.", 403)
        return sc.validate(ids, sub.code, sub.lec_units, sub.lab_units, sub.title, sub.year_level, sub.semester, sub.classification)
    return _shared_call(request, run)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_save(request):
    return _shared_call(request, lambda sc, u, d: sc.save_group(u, None, int(d["subject_id"]), d.get("program_ids", [])))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_exclusive(request):
    return _shared_call(request, lambda sc, u, d: sc.set_exclusive(u, None, int(d["subject_id"])))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_clear(request):
    return _shared_call(request, lambda sc, u, d: sc.clear_choice(u, None, int(d["subject_id"])))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_confirm(request):
    return _shared_call(request, lambda sc, u, d: sc.confirm_group(u, int(d["group_id"])))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def shared_batch_options(request):
    from . import shared_classes as sc
    try:
        return Response(sc.batch_options(request.user, request.query_params.get("semester", ""),
                                         request.query_params.get("year_level", "")))
    except sc.SharedError as e:
        return Response({"detail": e.message}, status=e.status)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_batch_choice(request):
    return _shared_call(request, lambda sc, u, d: sc.batch_choice(u, int(d["subject_id"]), d.get("mode", "auto"),
                                                                  d.get("departments", [])))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def teacher_options_view(request):
    """READ-ONLY. ?schedule_ids=1,2,3 -> the teachers the Edit dialog may offer for that class (engine.teacher_scope.options)."""
    from . import teacher_scope
    try:
        ids = [int(x) for x in str(request.query_params.get("schedule_ids") or "").split(",") if x.strip()]
    except ValueError:
        return Response({"detail": "schedule_ids must be numbers."}, status=status.HTTP_400_BAD_REQUEST)
    data, err, code = teacher_scope.options(request.user, ids)
    if err:
        return Response({"detail": err}, status=code)
    return Response(data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def shared_class_edit_view(request):
    """body {ids: [rows of the shared class], teacher?, room?, override_workload?} -> changes the teacher / room of EVERY section of the
    shared class together (engine.shared_edit). Nothing changes when any rule fails."""
    from . import shared_edit
    try:
        return Response(shared_edit.edit(request.user, request.data.get("ids") or [], request.data.get("teacher"), request.data.get("room"),
                                         str(request.data.get("override_workload", "")).lower() in ("1", "true", "yes")))
    except shared_edit.SharedEditError as e:
        return Response({"detail": e.message, **e.extra}, status=e.status)


def _gened_req_call(fn):
    from . import gened_requests as gr
    try:
        return Response(fn(gr))
    except gr.RequestError as e:
        return Response({"detail": e.message, **e.extra}, status=e.status)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def gened_requests_view(request):
    """GET: the Gen Ed move requests (Registrar: all; Dean: their college's). POST {ids, key, reason}: a Dean asks to move a Gen Ed class."""
    if request.method == "GET":
        return _gened_req_call(lambda gr: gr.listing(request.user, request.query_params.get("status") or ""))
    d = request.data
    return _gened_req_call(lambda gr: gr.create(request.user, d.get("ids") or [], d.get("key") or "", d.get("reason") or ""))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def gened_request_options_view(request):
    """READ-ONLY. body {ids} -> the times the Dean may ask this Gen Ed class to move to (the Registrar's clash-free list)."""
    return _gened_req_call(lambda gr: gr.options(request.user, request.data.get("ids") or []))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def gened_request_decide_view(request, req_id, action):
    """POST approve / reject (Registrar, body {note}) or cancel (the Dean who asked)."""
    note = request.data.get("note") or ""
    if action == "approve":
        return _gened_req_call(lambda gr: gr.approve(request.user, req_id, note))
    if action == "reject":
        return _gened_req_call(lambda gr: gr.reject(request.user, req_id, note))
    if action == "cancel":
        return _gened_req_call(lambda gr: gr.cancel(request.user, req_id))
    return Response({"detail": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)
