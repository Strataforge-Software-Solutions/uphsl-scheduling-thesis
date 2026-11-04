from django.contrib import admin
from .models import HistoricalClassRecord


@admin.register(HistoricalClassRecord)
class HistoricalClassRecordAdmin(admin.ModelAdmin):
    list_display = ["subject_code", "school_year", "semester", "day", "start_time", "end_time",
                     "room_name", "teacher_name_raw", "teacher"]
    list_filter = ["school_year", "semester", "day"]
    search_fields = ["subject_code", "description", "teacher_name_raw", "section_label"]
