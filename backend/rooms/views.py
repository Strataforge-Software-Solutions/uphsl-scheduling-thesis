from rest_framework import viewsets
from .models import Room
from .serializers import RoomSerializer
from rest_framework import permissions


class ReadOnlyOrItAdmin(permissions.BasePermission):
    """Everyone signed in may read rooms (dropdowns); only the IT Admin may create, edit or delete room records."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return request.method in permissions.SAFE_METHODS or bool(getattr(u, "is_it_admin", False))


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    # Was IsAuthenticated-only -- any logged-in Student could DELETE a Room,
    # which cascades (Schedule.room is on_delete=CASCADE) and wipes every
    # class in that room institution-wide. Writes are IT Admin only.
    permission_classes = [ReadOnlyOrItAdmin]
