from django.contrib import admin
from .models import FacultyProfile, Availability, Absence, WorkloadRecord


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
    # filter_horizontal gives a proper dual-list picker for the M2M instead of
    # the default multi-select box -- this is the exact screen the user
    # screenshotted as confusing, now listing AcademicField rows ("Computer
    # Science", "Mathematics", etc.) instead of raw Subject codes.
    list_display = ["user", "target_load_hours"]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
    filter_horizontal = ["specializations"]


admin.site.register(Availability)
admin.site.register(Absence)
admin.site.register(WorkloadRecord)
