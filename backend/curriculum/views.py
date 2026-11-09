from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Program, Subject, AcademicField
from .serializers import ProgramSerializer, SubjectSerializer, AcademicFieldSerializer
from .permissions import CanEditCurriculum


class AcademicFieldViewSet(viewsets.ModelViewSet):
    """Lets Registrar/Dean list existing fields (e.g. "Computer Science") and
    add new ones on the fly when tagging a Subject, rather than hand-editing
    them only through the Django admin."""
    queryset = AcademicField.objects.all()
    serializer_class = AcademicFieldSerializer
    permission_classes = [CanEditCurriculum]


class ProgramViewSet(viewsets.ModelViewSet):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer
    permission_classes = [CanEditCurriculum]


class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    permission_classes = [CanEditCurriculum]

    def get_queryset(self):
        qs = Subject.objects.select_related("program").all()
        user = self.request.user
        # Dean's tab only ever shows their own department; Registrar sees all.
        if user.role == "faculty" and user.faculty_type == "dean":
            qs = qs.filter(program__department__in=user.departments)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "Provide a non-empty list of subject IDs."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > 500 or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in ids):
            return Response({"detail": "Subject IDs must be positive integers (up to 500 per request)."},
                            status=status.HTTP_400_BAD_REQUEST)
        ids = set(ids)

        with transaction.atomic():
            subjects = self.get_queryset().filter(pk__in=ids)
            if subjects.count() != len(ids):
                return Response({"detail": "One or more subjects were not found or cannot be removed."},
                                status=status.HTTP_404_NOT_FOUND)
            deleted_count = len(ids)
            subjects.delete()

        return Response({"deleted": deleted_count}, status=status.HTTP_200_OK)
