from django.contrib import admin
from .models import Room, DepartmentBuilding, DepartmentRoom, DepartmentEnrollment


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "building", "room_type", "capacity", "capacity_is_estimate", "department")
    list_filter = ("building", "room_type", "department", "capacity_is_estimate")
    search_fields = ("name", "label")


admin.site.register(DepartmentBuilding)
admin.site.register(DepartmentRoom)
admin.site.register(DepartmentEnrollment)
