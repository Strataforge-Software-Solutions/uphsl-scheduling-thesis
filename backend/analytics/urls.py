from django.urls import path
from .views import analytics_view, faculty_patterns_view, historical_lookup_view
from . import insight_views

urlpatterns = [
    path("", analytics_view, name="analytics"),
    path("faculty-patterns/<int:faculty_id>/", faculty_patterns_view, name="faculty-patterns"),
    path("historical-lookup/", historical_lookup_view, name="historical-lookup"),
    # new read-only insight cards (additive; the paths above are unchanged)
    path("admin/health/", insight_views.admin_health, name="insight-admin-health"),
    path("admin/accounts/", insight_views.admin_accounts, name="insight-admin-accounts"),
    path("admin/audit/", insight_views.admin_audit, name="insight-admin-audit"),
    path("dean/readiness/", insight_views.dean_readiness, name="insight-dean-readiness"),
    path("dean/faculty-fit/", insight_views.dean_faculty_fit, name="insight-dean-faculty-fit"),
    path("dean/lab-capacity/", insight_views.dean_lab_capacity, name="insight-dean-lab-capacity"),
    path("dean/load-bands/", insight_views.dean_load_bands, name="insight-dean-load-bands"),
    path("registrar/gened-coverage/", insight_views.registrar_gened_coverage, name="insight-registrar-gened"),
    path("registrar/dependencies/", insight_views.registrar_dependencies, name="insight-registrar-dependencies"),
    path("room-heatmap/", insight_views.room_heatmap, name="insight-room-heatmap"),
    path("capacity/", insight_views.capacity_vs_enrollment, name="insight-capacity"),
    path("basic-ed/feasibility/", insight_views.basic_ed_feasibility, name="insight-basic-ed-feasibility"),
    path("basic-ed/completeness/", insight_views.basic_ed_completeness, name="insight-basic-ed-completeness"),
    path("basic-ed/absences/", insight_views.basic_ed_absences, name="insight-basic-ed-absences"),
    path("basic-ed/run-trend/", insight_views.basic_ed_run_trend, name="insight-basic-ed-run-trend"),
    path("filters/", insight_views.filter_options, name="insight-filters"),
]
