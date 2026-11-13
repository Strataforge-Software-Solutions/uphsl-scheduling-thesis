from rest_framework import permissions


class CanManageFacultyProfiles(permissions.BasePermission):
    """Deans manage faculty in their departments; faculty may edit only their own specializations."""

    def has_permission(self, request, view):
        user = request.user
        if request.method in permissions.SAFE_METHODS:
            return bool(user and user.is_authenticated)
        if not user or not user.is_authenticated:
            return False
        if user.is_it_admin or user.role == "registrar":
            return True
        if user.role == "faculty" and user.faculty_type == "dean":
            return True
        return user.role == "faculty" and user.faculty_type in {"full_time", "part_time"} and request.method == "PATCH"

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if user.is_it_admin or user.role == "registrar":
            return True
        if user.role == "faculty" and user.faculty_type == "dean":
            return obj.user.department in user.departments
        return (
            user.role == "faculty"
            and user.faculty_type in {"full_time", "part_time"}
            and obj.user_id == user.id
            and request.method == "PATCH"
            and set(request.data.keys()) <= {"specializations"}
        )
