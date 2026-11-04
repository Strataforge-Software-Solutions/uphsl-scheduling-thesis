from rest_framework.routers import DefaultRouter
from .views import (
    FacultyProfileViewSet, AvailabilityViewSet, AbsenceViewSet, WorkloadRecordViewSet,
    CoverageSuggestionViewSet,
)

router = DefaultRouter()
router.register(r"profiles", FacultyProfileViewSet)
router.register(r"availability", AvailabilityViewSet, basename="availability")
router.register(r"absences", AbsenceViewSet)
router.register(r"workload-records", WorkloadRecordViewSet)
router.register(r"coverage-suggestions", CoverageSuggestionViewSet, basename="coverage-suggestion")

urlpatterns = router.urls
