from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ExamScheduleViewSet, generate_exam_schedule_view, export_exam_pdf, resolve_exam_conflicts_view

router = DefaultRouter()
router.register(r"", ExamScheduleViewSet, basename="examschedule")

# IMPORTANT: "generate/" must come BEFORE router.urls. The router is registered
# at an empty prefix, so its auto-generated detail route (`<pk>/`) matches the
# literal string "generate" as if it were a record id. If router.urls were
# listed first, POST /api/exams/generate/ would get shadowed by that detail
# route (which only allows GET/PUT/PATCH/DELETE) and return 405 instead of
# ever reaching generate_exam_schedule_view.
urlpatterns = [
    path("generate/", generate_exam_schedule_view, name="generate_exam_schedule"),
    path("export-pdf/", export_exam_pdf, name="export_exam_pdf"),
    path("resolve/", resolve_exam_conflicts_view, name="resolve_exam_conflicts"),
] + router.urls
