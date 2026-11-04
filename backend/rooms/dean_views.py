"""
Dean Dashboard -> Rooms tab. A Dean manages the rooms of their own college(s) and chooses, for each MAJOR subject,
a preferred room, alternative rooms and whether the preferred room is fixed. Gen Ed (minor) subjects keep the
Main Building default and are not touched here.
"""
import re
from collections import defaultdict

from django.db import transaction
from django.db.models import Max, Q
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from curriculum.models import Subject
from .models import DepartmentBuilding, DepartmentEnrollment, DepartmentRoom, Room, SubjectRoomAssignment
from .rules import may_use, norm, owns_labs, room_code, room_kind_message, room_text

BUILDING_CODES = [c for c, _ in Room.BUILDINGS if c in ("M", "D", "N", "A")]
ROOM_TYPES = ("lecture", "lab")


def _dean(request):
    u = request.user
    if u.is_authenticated and u.role == "faculty" and u.faculty_type == "dean":
        return u
    return None


def _deny():
    return Response({"detail": "Only a Dean can manage room assignments."}, status=status.HTTP_403_FORBIDDEN)


def _room_json(r, depts, home=()):
    return {"id": r.id, "text": room_text(r), "code": room_code(r), "home": r.id in home, "name": r.name, "building": r.building, "room_number": r.room_number, "label": r.label,
            "capacity": r.capacity, "room_type": r.room_type, "equipment": r.equipment, "department": r.department or "",
            "owned": bool(r.department and r.department in depts)}


def _clean_code(v):
    return re.sub(r"[#*]", "", str(v or "")).strip()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def overview(request):
    """?program_id= -> rooms the Dean may use, the program's major subjects with their assignment, building preference."""
    u = _dean(request)
    if u is None:
        return _deny()
    depts = list(u.departments)
    rooms = Room.objects.filter(room_type__in=ROOM_TYPES).filter(
        Q(department__in=depts) | Q(department__isnull=True) | Q(department="")).order_by("building", "room_number", "name")
    home = set(DepartmentRoom.objects.filter(department__in=depts).values_list("room_id", flat=True))
    subjects = []
    pid = request.query_params.get("program_id")
    if pid:
        from engine.models import Section
        sizes = {(s["year_level"], s["semester"]): s["m"] for s in Section.objects.filter(program_id=pid)
                 .values("year_level", "semester").annotate(m=Max("student_count"))}
        qs = Subject.objects.filter(program_id=pid, classification="major", program__department__in=depts) \
            .select_related("room_assignment", "program").prefetch_related("room_assignment__alternative_rooms") \
            .order_by("year_level", "semester", "code")
        for s in qs:
            a = getattr(s, "room_assignment", None)
            subjects.append({
                "id": s.id, "code": s.code, "title": s.title, "year_level": s.year_level, "semester": s.semester,
                "needs_lab": s.lab_units > 0, "students": sizes.get((s.year_level, s.semester), 0) or 0,
                "preferred_room": a.preferred_room_id if a else None,
                "alternative_rooms": [r.id for r in a.alternative_rooms.all()] if a else [],
                "is_fixed": bool(a and a.is_fixed),
            })
    designated = []
    if pid:
        from curriculum.models import Program
        from rooms.rules import designated_rooms
        prog = Program.objects.filter(pk=pid).first()
        designated = [r.id for r in (designated_rooms(list(Room.objects.all()), prog.department if prog else None) or [])]
    return Response({
        "rooms": [_room_json(r, depts, home) for r in rooms],
        "designated": designated,        # Computer Studies: the only rooms its major subjects may use (Comp Lab C / D)
        "subjects": subjects,
        "departments": depts,
        "building_preference": {d.department: d.building for d in DepartmentBuilding.objects.filter(department__in=depts)},
        "buildings": [{"code": c, "label": l} for c, l in Room.BUILDINGS if c in BUILDING_CODES],
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def preview_choices(request):
    """Rooms for the Room dropdown of the curriculum preview (Dean and Registrar), plus the room already saved per subject.
    Dean: rooms of the Dean's own departments and shared rooms. Registrar: all rooms (the page lists a reserved room only for programs of its department)."""
    u = request.user
    is_dean = u.role == "faculty" and getattr(u, "faculty_type", "") == "dean"
    if not (is_dean or u.role == "registrar"):
        return Response({"detail": "Only a Dean or the Registrar can choose rooms for a generation."}, status=status.HTTP_403_FORBIDDEN)
    depts = list(u.departments) if is_dean else []
    qs = Room.objects.filter(room_type__in=ROOM_TYPES)
    if is_dean:                       # Registrar: every room (a reserved lab such as Comp Lab C / D is offered for that department's programs)
        qs = qs.filter(Q(department__in=depts) | Q(department__isnull=True) | Q(department=""))
    room_objs = list(qs.order_by("building", "room_number", "name"))
    rooms = [_room_json(r, depts) for r in room_objs]
    saved = {}
    pid = request.query_params.get("program_id")
    if is_dean and pid:
        for a in SubjectRoomAssignment.objects.filter(subject__program_id=pid, subject__program__department__in=depts):
            if a.preferred_room_id:
                saved[a.subject_id] = a.preferred_room_id
    out = {"rooms": rooms, "saved": saved}
    # Optional, read-only extras for the Generate preview: free hours per room in the semester, and per subject the rooms that
    # Generate would accept for this role (the same check as engine.views.room_choice_error).
    semester = request.query_params.get("semester")
    if semester:
        from .usage import free_hours
        hours = free_hours([r.id for r in room_objs], semester)
        for x in rooms:
            x["free_hours"], x["total_hours"] = hours["free"].get(x["id"], hours["total"]), hours["total"]
        out["week_hours"] = hours["total"]
    year = request.query_params.get("year_level")
    if pid and semester and year:
        out["allowed"] = _allowed_rooms(u, pid, year, semester, room_objs)
    return Response(out)


def _allowed_rooms(user, program_id, year_level, semester, room_objs):
    """{subject_id: [room ids]} of the rooms listed that Generate would accept for each subject of this run (this role's kind only)."""
    from curriculum.models import Program, Subject
    from engine.views import room_choice_error
    prog = Program.objects.filter(pk=program_id).first()
    if prog is None:
        return {}
    kind = "minor" if user.role == "registrar" else "major"
    every_room = list(Room.objects.all())                  # the designated-room rule looks at every room, as Generate does
    gym = any(getattr(r, "room_type", "") == "gym" for r in every_room)
    subs = Subject.objects.filter(program=prog, year_level=year_level, semester=semester, classification=kind)
    return {s.id: [r.id for r in room_objs if not room_choice_error(user.role, s, r, prog.department, every_room, gym)] for s in subs}


def _validate_room_fields(d, depts, instance=None):
    errors = {}
    building = str(d.get("building", "") or "").strip().upper()
    number = _clean_code(d.get("room_number"))
    rtype = str(d.get("room_type", "") or "").strip()
    dept = str(d.get("department", "") or "").strip() or (instance.department if instance else (depts[0] if depts else ""))
    try:
        cap = int(d.get("capacity"))
    except (TypeError, ValueError):
        cap = 0
    if building not in BUILDING_CODES:
        errors["building"] = "Choose M (Main), D (Alta) or N (New Building)."
    if not number:
        errors["room_number"] = "Enter the room number."
    if rtype not in ROOM_TYPES:
        errors["room_type"] = "Choose Lecture or Laboratory."
    if not 1 <= cap <= 500:
        errors["capacity"] = "Enter a capacity between 1 and 500."
    if dept not in depts:
        errors["department"] = "You can only manage rooms of your own college."
    name = f"{building}-{number}" if building and number else ""
    if name and not errors:
        dup = Room.objects.filter(name__iexact=name)
        if instance is not None:
            dup = dup.exclude(pk=instance.pk)
        if dup.exists():
            errors["room_number"] = f"Room {name} already exists."
    return errors, dict(name=name, building=building, room_number=number, capacity=cap, room_type=rtype, department=dept,
                        equipment=str(d.get("equipment", "") or "").strip()[:255],
                        label=str(d.get("label", "") or "").strip()[:80])


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_room(request):
    """Room records are managed by the IT Admin only (rooms/admin_views.py); Deans only choose from them."""
    return Response({"detail": "Room records are managed by the IT Admin. You can choose from the existing rooms."}, status=status.HTTP_403_FORBIDDEN)


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_room(request, pk):
    return Response({"detail": "Room records are managed by the IT Admin. You can choose from the existing rooms."}, status=status.HTTP_403_FORBIDDEN)


@api_view(["PUT"])
@permission_classes([permissions.IsAuthenticated])
def subject_room(request):
    """body {subject, preferred_room|null, alternative_rooms:[ids], is_fixed}"""
    from engine.scheduler import _room_matches_subject
    u = request.user
    if not u.is_authenticated:
        return Response({"detail": "Sign in first."}, status=401)
    is_dean = u.role == "faculty" and getattr(u, "faculty_type", "") == "dean"
    is_reg = u.role == "registrar"
    d = request.data
    subj = Subject.objects.select_related("program").filter(pk=d.get("subject")).first()
    if not (is_dean or is_reg):
        return Response({"detail": "Room assignments for subjects are made by the Dean (program subjects) and the Registrar (Gen Ed subjects). "
                                   "Room records themselves are kept by the IT Admin.", "action": "Ask your Dean or the Registrar."}, status=403)
    if subj is None:
        return Response({"detail": "Subject not found."}, status=404)
    if subj.classification == "minor" and not is_reg:
        return Response({"detail": f"{subj.code} is a Gen Ed (minor) subject: its room is assigned by the Registrar.",
                         "action": "Ask the Registrar to assign or change this room."}, status=403)
    if subj.classification != "minor" and (not is_dean or subj.program.department not in u.departments):
        return Response({"detail": f"{subj.code} is a program (major) subject: its room is assigned by the Dean of {subj.program.department}.",
                         "action": f"Ask the Dean of {subj.program.department}."}, status=403)
    dept = subj.program.department
    pref_id = d.get("preferred_room") or None
    alt_ids = [int(x) for x in (d.get("alternative_rooms") or []) if x]
    fixed = bool(d.get("is_fixed"))
    if pref_id is not None:
        pref_id = int(pref_id)
    if fixed and pref_id is None:
        return Response({"detail": "Choose the preferred room before marking it fixed."}, status=400)
    if pref_id in alt_ids:
        alt_ids = [i for i in alt_ids if i != pref_id]
    rooms = {r.id: r for r in Room.objects.filter(pk__in=([pref_id] if pref_id else []) + alt_ids)}
    if len(rooms) != len(set(([pref_id] if pref_id else []) + alt_ids)):
        return Response({"detail": "One of the chosen rooms no longer exists."}, status=400)
    from engine.models import Section
    size = Section.objects.filter(program=subj.program, year_level=subj.year_level, semester=subj.semester) \
        .aggregate(m=Max("student_count"))["m"] or 0
    all_rooms = list(Room.objects.all())
    gym_exists = any(r.room_type == "gym" for r in all_rooms)
    from rooms.rules import designated_rooms, designated_message
    des = designated_rooms(all_rooms, dept) if subj.classification != "minor" else None
    for r in rooms.values():
        if des is not None and r.id not in {x.id for x in des}:
            return Response({"detail": designated_message(subj, dept, all_rooms), "action": "Choose Comp Lab C or Comp Lab D."}, status=400)
        if not may_use(r, dept):
            return Response({"detail": f"Room {r.name} is reserved for {r.department}."}, status=400)
        kind_msg = room_kind_message(subj, r)
        if kind_msg:
            return Response({"detail": kind_msg}, status=400)
        if not _room_matches_subject(r, subj, gym_exists):
            kind = "a laboratory" if subj.lab_units > 0 else "a lecture room"
            return Response({"detail": f"{subj.title} needs {kind}; {r.name} is not suitable."}, status=400)
        if subj.lab_units > 0 and owns_labs(all_rooms, dept) and not (r.room_type == "lab" and r.department and norm(r.department) == norm(dept)):
            return Response({"detail": f"{subj.title} is a lab subject: use one of your college's own laboratories ({r.name} is not)."}, status=400)
        if size and r.capacity < size:
            return Response({"detail": f"Room {r.name} seats {r.capacity} but a section of {subj.title} has {size} students."}, status=400)
    with transaction.atomic():
        a, _ = SubjectRoomAssignment.objects.get_or_create(subject=subj)
        a.preferred_room = rooms.get(pref_id)
        a.is_fixed = fixed and pref_id is not None
        a.updated_by = u
        a.save()
        a.alternative_rooms.set([rooms[i] for i in alt_ids])
        if a.preferred_room is None and not alt_ids:
            a.delete()
    return Response({"subject": subj.id, "preferred_room": pref_id, "alternative_rooms": alt_ids, "is_fixed": fixed and pref_id is not None})


@api_view(["PUT"])
@permission_classes([permissions.IsAuthenticated])
def department_building(request):
    u = _dean(request)
    if u is None:
        return _deny()
    dept, b = request.data.get("department"), str(request.data.get("building", "")).upper()
    if dept not in u.departments or b not in BUILDING_CODES:
        return Response({"detail": "Choose your college and a building (M, D or N)."}, status=400)
    DepartmentBuilding.objects.update_or_create(department=dept, defaults={"building": b})
    return Response({"department": dept, "building": b})


# ----------------------------------------------------------------------------- department headcount / capacity
YEAR_ORDER = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"]


def _year_key(y):
    return (YEAR_ORDER.index(y) if y in YEAR_ORDER else 99, y)


def _enrollment_payload(depts):
    """Per department and year level: headcount, number of sections, the section size it implies, the sections'
    current size, and whether the college's rooms can seat that size. Plus every booked class whose room is too small."""
    from engine.models import Schedule, Section
    from math import ceil
    out = []
    for d in depts:
        secs = list(Section.objects.filter(program__department=d))
        saved = {e.year_level: e.students for e in DepartmentEnrollment.objects.filter(department=d)}
        years = sorted({s.year_level for s in secs} | set(saved), key=_year_key)
        rooms = [r for r in Room.objects.filter(room_type__in=ROOM_TYPES) if may_use(r, d)]
        biggest = max([r.capacity for r in rooms if r.room_type == "lecture"] or [0])
        rows = []
        for y in years:
            ys = [s for s in secs if s.year_level == y]
            per_sem = defaultdict(int)
            for s in ys:
                per_sem[s.semester] += 1
            n = max(per_sem.values() or [0])
            students = saved.get(y)
            implied = ceil(students / n) if students and n else None
            cur = max([s.student_count for s in ys] or [0])
            size = implied if implied is not None else cur
            rows.append({"year_level": y, "students": students, "sections": n, "per_section": implied, "current_section_size": cur,
                         "rooms_that_fit": sum(1 for r in rooms if r.room_type == "lecture" and r.capacity >= size) if size else None,
                         "fits": (biggest >= size) if size else True})
        total = sum(v or 0 for v in saved.values())
        out.append({"department": d, "years": rows, "total_students": total, "largest_lecture_room": biggest})
    over = []
    qs = Schedule.objects.filter(section__program__department__in=depts, section__student_count__gt=0) \
        .select_related("room", "section", "subject").order_by("subject__code")
    seen = set()
    for r in qs:
        if r.room and r.room.capacity and r.room.capacity < r.section.student_count:
            k = (r.subject_id, r.section_id, r.room_id)
            if k not in seen:
                seen.add(k)
                over.append({"subject": f"{r.subject.code} {r.subject.title}", "section": str(r.section), "room": room_text(r.room),
                             "capacity": r.room.capacity, "students": r.section.student_count})
    return {"departments": out, "too_small": over[:40], "too_small_count": len(over)}


@api_view(["GET", "PUT"])
@permission_classes([permissions.IsAuthenticated])
def enrollment(request):
    """GET -> headcount per year level for the Dean's college(s). PUT {department, year_level, students, apply?} saves a
    headcount; with apply=true the section sizes are set to students / sections so room capacity checks use them."""
    u = _dean(request)
    if u is None:
        return _deny()
    depts = list(u.departments)
    if request.method == "PUT":
        from engine.models import Section
        from math import ceil
        d = request.data
        dept, year = d.get("department"), str(d.get("year_level") or "").strip()
        try:
            students = int(d.get("students"))
        except (TypeError, ValueError):
            return Response({"detail": "Enter the number of students."}, status=400)
        if dept not in depts or not year or students < 0 or students > 5000:
            return Response({"detail": "Choose your college, a year level and a number of students between 0 and 5000."}, status=400)
        with transaction.atomic():
            DepartmentEnrollment.objects.update_or_create(department=dept, year_level=year,
                                                          defaults={"students": students, "updated_by": u})
            if d.get("apply"):
                secs = list(Section.objects.filter(program__department=dept, year_level=year))
                per_sem = defaultdict(int)
                for s in secs:
                    per_sem[s.semester] += 1
                n = max(per_sem.values() or [0])
                if n and students:
                    size = ceil(students / n)
                    Section.objects.filter(pk__in=[s.pk for s in secs]).update(student_count=size)
    return Response(_enrollment_payload(depts))
