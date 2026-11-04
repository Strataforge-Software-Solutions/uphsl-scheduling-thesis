from rest_framework import permissions


class CanEditCurriculum(permissions.BasePermission):
    """
    Read: any authenticated user.
    Write: Registrar (any department) or Faculty/Dean (own department only).
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

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if user.role == "registrar":
            return True
        target_department = getattr(obj, "department", None)
        return (
            user.role == "faculty"
            and user.faculty_type == "dean"
            and target_department in user.departments
        )
