from rest_framework import permissions


class ReadOnlyOrRegistrarDean(permissions.BasePermission):
    """
    Any authenticated user can read. Only Registrar or a Dean can
    create/update/delete. Used for audit-style data (Absence, WorkloadRecord,
    ConflictLog) that shouldn't be editable by e.g. a Student or part-time
    faculty just because they're logged in.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == "registrar":
            return True
        return user.role == "faculty" and user.faculty_type == "dean"


def can_edit_schedule_kind(user, classification, department=None):
    """Registrar -> minor classes. Dean -> major classes of their own college(s)."""
    if not user or not user.is_authenticated:
        return False
    if user.role == "registrar":
        return classification == "minor"
    if user.role == "faculty" and user.faculty_type == "dean":
        return classification == "major" and (department is None or department in user.departments)
    return False


class CanEditOwnScheduleKind(permissions.BasePermission):
    """Read: anyone logged in (the queryset already scopes what they see).
    Write: Registrar on minor classes, Dean on major classes of their own college(s)."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.role == "registrar" or (user.role == "faculty" and user.faculty_type == "dean")

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return can_edit_schedule_kind(request.user, obj.subject.classification,
                                      obj.section.program.department)


class CanEditSections(permissions.BasePermission):
    """Sections. Read: anyone logged in. Write: the Registrar (any college) or a Dean (sections of their own college(s) only)."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return user.role == "registrar" or (user.role == "faculty" and user.faculty_type == "dean")

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if user.role == "registrar":
            return True
        return (user.role == "faculty" and user.faculty_type == "dean"
                and getattr(getattr(obj, "program", None), "department", None) in user.departments)
