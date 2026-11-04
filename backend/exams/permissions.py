from rest_framework import permissions


class CanEditExamSchedule(permissions.BasePermission):
    """
    Registrar: minor-subject exams, any department.
    Dean: major-subject exams, own department only.
    Everyone authenticated: read.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if obj.subject.classification == "minor":
            return user.role == "registrar"
        # major subject
        return (
            user.role == "faculty"
            and user.faculty_type == "dean"
            and obj.subject.department in user.departments
        )
