from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include

def api_root(request):
    return JsonResponse({
        "service": "U-FAST Scheduling API",
        "status": "running",
        "api_prefix": "/api/",
    })

urlpatterns = [
    path("", api_root, name="api-root"),
    path("admin/", admin.site.urls),

    # Auth: login, password change, token refresh
    path("api/accounts/", include("accounts.urls")),

    # Curriculum: subjects, programs, prerequisites
    path("api/curriculum/", include("curriculum.urls")),

    # Faculty: teacher profiles, availability submissions, workload
    path("api/faculty/", include("faculty.urls")),

    # Rooms: room CRUD, availability calendar
    path("api/rooms/", include("rooms.urls")),

    # Engine: sections, schedules, generate-schedule, conflict reports
    path("api/engine/", include("engine.urls")),

    # Exams: exam scheduling -- Registrar owns minors, Dean owns majors, shared conflict layer
    path("api/exams/", include("exams.urls")),

    # Analytics: room utilization, workload distribution, efficiency score
    path("api/analytics/", include("analytics.urls")),

    # Notifications: alerts, audit logs
    path("api/notifications/", include("notifications.urls")),

    # Basic education: Senior High (SHS) and Junior High (JHS) scheduling modules
    path("api/basic-ed/", include("basic_ed.urls")),

    # Audit logs (IT Admin, read only)
    path("api/audit/", include("audit.urls")),
]
