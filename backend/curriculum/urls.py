from rest_framework.routers import DefaultRouter
from .views import ProgramViewSet, SubjectViewSet, AcademicFieldViewSet

router = DefaultRouter()
router.register(r"programs", ProgramViewSet)
router.register(r"subjects", SubjectViewSet, basename="subject")
router.register(r"academic-fields", AcademicFieldViewSet, basename="academic-field")

urlpatterns = router.urls
