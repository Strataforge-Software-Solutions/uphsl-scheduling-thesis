"""IT Admin -> Rooms: the ONLY place room records are created, edited or deleted. Deans and the Registrar choose from these rooms."""
import re

from django.db.models import Count
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from curriculum.models import Program
from .models import Room
from .rules import room_code, room_text

TYPES = ("lecture", "lab", "gym", "offsite")


class IsItAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "is_it_admin", False))


def _json(r, used=0):
    return {"id": r.id, "name": r.name, "text": room_text(r), "code": room_code(r), "building": r.building, "room_number": r.room_number,
            "label": r.label, "capacity": r.capacity, "room_type": r.room_type, "equipment": r.equipment, "department": r.department or "",
            "classes": used}


def _clean(d, instance=None):
    errors = {}
    building = str(d.get("building", "") or "").strip().upper()
    number = re.sub(r"[#*]", "", str(d.get("room_number", "") or "")).strip()
    rtype = str(d.get("room_type", "") or "").strip()
    dept = str(d.get("department", "") or "").strip()
    label = str(d.get("label", "") or "").strip()[:80]
    try:
        cap = int(d.get("capacity"))
    except (TypeError, ValueError):
        cap = 0
    if building not in {b for b, _l in Room.BUILDINGS}:
        errors["building"] = "Choose the building (M, D, N or A)."
    if not number:
        errors["room_number"] = "Enter the room number."
    if rtype not in TYPES:
        errors["room_type"] = "Choose the room type."
    if not 1 <= cap <= 500:
        errors["capacity"] = "Enter a capacity between 1 and 500."
    if dept and dept not in set(Program.objects.values_list("department", flat=True)) | ({instance.department} if instance else set()):
        errors["department"] = "Choose an existing college, or leave blank for a shared room."
    name = f"{building}-{number}" if building and number else ""
    if name and not errors:
        dup = Room.objects.filter(name__iexact=name)
        if instance is not None:
            dup = dup.exclude(pk=instance.pk)
        if dup.exists():
            errors["room_number"] = f"Room {name} already exists."
    return errors, dict(name=name, building=building, room_number=number, capacity=cap, room_type=rtype, department=dept or None,
                        equipment=str(d.get("equipment", "") or "").strip()[:255], label=label)


@api_view(["GET", "POST"])
@permission_classes([IsItAdmin])
def rooms(request):
    if request.method == "POST":
        errors, f = _clean(request.data)
        if errors:
            return Response({"detail": "; ".join(errors.values()), "errors": errors}, status=400)
        return Response(_json(Room.objects.create(**f)), status=201)
    used = dict(Room.objects.annotate(n=Count("schedule")).values_list("id", "n"))
    return Response({
        "rooms": [_json(r, used.get(r.id, 0)) for r in Room.objects.order_by("building", "room_number", "name")],
        "departments": sorted({d for d in Program.objects.values_list("department", flat=True) if d}),
        "buildings": [{"code": c, "label": l} for c, l in Room.BUILDINGS],
        "types": list(TYPES),
    })


@api_view(["PATCH", "DELETE"])
@permission_classes([IsItAdmin])
def room_detail(request, pk):
    r = Room.objects.filter(pk=pk).first()
    if r is None:
        return Response({"detail": "Room not found."}, status=404)
    if request.method == "DELETE":
        n = r.schedule_set.count()
        if n:
            return Response({"detail": f"{r.name} is used by {n} scheduled class period(s). Clear or move those classes first (deleting the room would delete them)."}, status=409)
        r.delete()
        return Response(status=204)
    data = {"building": r.building, "room_number": r.room_number, "capacity": r.capacity, "room_type": r.room_type, "equipment": r.equipment,
            "label": r.label, "department": r.department or ""}
    data.update(dict(request.data.items()))
    errors, f = _clean(data, instance=r)
    if errors:
        return Response({"detail": "; ".join(errors.values()), "errors": errors}, status=400)
    for k, v in f.items():
        setattr(r, k, v)
    r.save()
    return Response(_json(r, r.schedule_set.count()))
