from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views as v

router = DefaultRouter()
router.register("strands", v.StrandViewSet, basename="be-strand")
router.register("sections", v.SectionViewSet, basename="be-section")
router.register("rooms", v.RoomViewSet, basename="be-room")
router.register("windows", v.GradeWindowViewSet, basename="be-window")
router.register("curriculum-sources", v.CurriculumSourceViewSet, basename="be-source")
router.register("curriculum", v.CurriculumSubjectViewSet, basename="be-curriculum")
router.register("faculty", v.FacultyViewSet, basename="be-faculty")
router.register("assignments", v.AssignmentViewSet, basename="be-assignment")
router.register("calendar/events", v.CalendarEventViewSet, basename="be-event")
router.register("calendar/periods", v.CalendarPeriodViewSet, basename="be-period")

urlpatterns = [
    path("overview/", v.overview),
    path("config/", v.update_config),
    path("years/", v.academic_years),
    path("curriculum-tools/template/", v.curriculum_template),
    path("curriculum-tools/import/", v.curriculum_import),
    path("curriculum-tools/validate/", v.curriculum_validate),
    path("schedules/generate/", v.generate_view),
    path("schedules/", v.runs_list),
    path("schedules/<int:pk>/", v.run_detail),
    path("schedules/<int:pk>/report/", v.run_report_view),
    path("schedules/<int:pk>/pdf/", v.run_pdf),
    path("schedules/<int:pk>/validate/", v.run_revalidate),
    path("schedules/<int:pk>/resolve/", v.run_resolve),
    path("clear-generated/", v.clear_generated),
    path("analytics/workload/", v.workload_analytics),
    path("schedules/<int:pk>/<str:action>/", v.run_action),
    path("entries/<int:pk>/", v.entry_edit),
    path("my/schedule/", v.my_schedule),
    path("my/availability/", v.my_availability),
    path("availability/", v.availability_overview),
    path("availability/remind/", v.availability_remind),
    path("availability/<int:fid>/", v.availability_detail),
    path("availability/<int:fid>/return/", v.availability_return),
    path("", include(router.urls)),
]
