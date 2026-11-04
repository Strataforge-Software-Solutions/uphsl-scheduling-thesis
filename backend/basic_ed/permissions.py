from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError

LEVELS = ("SHS", "JHS")


def allowed_levels(user):
    """School levels this account may manage. IT admin: both. Principal: their own. Others: none."""
    if not user or not user.is_authenticated:
        return set()
    if user.is_it_admin:
        return set(LEVELS)
    if user.role == "principal" and user.school_level in LEVELS:
        return {user.school_level}
    return set()


def level_of(request):
    """The level a request is about: a principal is always locked to their own; an admin must say which."""
    user = request.user
    allowed = allowed_levels(user)
    asked = (request.query_params.get("level") or (request.data.get("level") if hasattr(request, "data") and hasattr(request.data, "get") else None) or "").upper()
    if user.role == "principal" and not user.is_it_admin:
        if asked and asked not in allowed:
            raise PermissionDenied("You can only access your own school level.")
        return next(iter(allowed))
    if asked in LEVELS:
        if asked not in allowed:
            raise PermissionDenied("You can't access that school level.")
        return asked
    raise ValidationError({"level": "Say which school level (SHS or JHS)."})


class IsLevelManager(permissions.BasePermission):
    """IT admin (both levels) or a principal (own level). Teachers and everyone else: no."""
    def has_permission(self, request, view):
        return bool(allowed_levels(request.user))


def check_level(user, level):
    if level not in allowed_levels(user):
        raise PermissionDenied("You can't access that school level.")
