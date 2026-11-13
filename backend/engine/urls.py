from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views, tools

router = DefaultRouter()
router.register(r"sections", views.SectionViewSet)
router.register(r"students", views.StudentViewSet, basename="student")
router.register(r"timeslots", views.TimeSlotViewSet)
router.register(r"schedules", views.ScheduleViewSet, basename="schedule")
router.register(r"constraints", views.ConstraintViewSet)
router.register(r"logs", views.LogViewSet, basename="log")
router.register(r"conflict-logs", views.ConflictLogViewSet)

urlpatterns = router.urls + [
    path("generate-schedule/", views.generate_schedule_view, name="generate_schedule"),
    path("generate/professor-options/", views.professor_options_view, name="professor_options"),
    path("generate/professor-groups/", views.professor_groups_view, name="professor_groups"),
    path("generate/faculty-time/", views.faculty_time_view, name="faculty_time"),
    path("teacher-options/", views.teacher_options_view, name="teacher_options"),
    path("shared-classes/edit/", views.shared_class_edit_view, name="shared_class_edit"),
    path("gened-requests/", views.gened_requests_view, name="gened_requests"),
    path("gened-requests/options/", views.gened_request_options_view, name="gened_request_options"),
    path("gened-requests/<int:req_id>/<str:action>/", views.gened_request_decide_view, name="gened_request_decide"),
    path("export-pdf/", views.export_schedule_pdf, name="export_schedule_pdf"),
    path("export-report/", views.export_schedule_pdf, name="export_schedule_report"),
    path("scheduling-config/", views.SchedulingConfigView.as_view({"get": "list", "patch": "partial_update"}), name="scheduling_config"),
    path("workload/", views.workload_list, name="workload_list"),
    path("workload/check/", views.workload_check, name="workload_check"),
    path("slot-options/", views.slot_options, name="slot_options"),
    path("slot-options/apply/", views.slot_options_apply, name="slot_options_apply"),
    path("unplaced/faculty-groups/", views.unplaced_faculty_groups, name="unplaced_faculty_groups"),
    path("shared-classes/options/", views.shared_options, name="shared_options"),
    path("shared-classes/validate/", views.shared_validate, name="shared_validate"),
    path("shared-classes/save/", views.shared_save, name="shared_save"),
    path("shared-classes/exclusive/", views.shared_exclusive, name="shared_exclusive"),
    path("shared-classes/clear/", views.shared_clear, name="shared_clear"),
    path("shared-classes/confirm/", views.shared_confirm, name="shared_confirm"),
    path("shared-classes/batch-options/", views.shared_batch_options, name="shared_batch_options"),
    path("shared-classes/batch-choice/", views.shared_batch_choice, name="shared_batch_choice"),
    path("dashboard-stats/", views.dashboard_stats, name="dashboard_stats"),
    path("workload/overload-summary/", views.overload_summary, name="overload_summary"),
    path("workload/overload-plan/", views.overload_plan, name="overload_plan"),
    path("workload/overload-assign/", views.overload_assign, name="overload_assign"),
    path("workload/replacements/", views.workload_replacements, name="workload_replacements"),
    path("workload/<int:faculty_id>/", views.workload_detail, name="workload_detail"),
    path("conflicts/", views.conflict_scan_view, name="conflict_scan"),
    path("schedule-plot/", views.schedule_plot_view, name="schedule_plot"),
    path("conflicts/demo/", views.conflict_demo_view, name="conflict_demo"),
    path("conflicts/resolve/", views.conflict_resolve_view, name="conflict_resolve"),
    path("minor/generate-all/", views.minor_generate_all_view, name="minor_generate_all"),
    path("minor/comparison/", views.minor_comparison_view, name="minor_comparison"),
    path("unplaced/", views.unplaced_list_view, name="unplaced_list"),
    path("unplaced/resolve/", views.unplaced_resolve_view, name="unplaced_resolve"),
    path("reschedule/", tools.reschedule_view, name="reschedule"),
    path("replacements/teacher/", tools.teacher_replacements, name="teacher_replacements"),
    path("replacements/assign/", tools.assign_replacement, name="assign_replacement"),
    path("suggest-substitute/", views.suggest_substitute_view, name="suggest_substitute"),
    path("apply-coverage/", views.apply_coverage_suggestion_view, name="apply_coverage"),
]
