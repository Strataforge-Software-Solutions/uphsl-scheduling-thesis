from rest_framework import viewsets
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
