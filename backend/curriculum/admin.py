from django.contrib import admin
from .models import Program, Subject, AcademicField


@admin.register(AcademicField)
class AcademicFieldAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "program", "classification", "field"]
    list_filter = ["program", "classification", "field"]
    search_fields = ["code", "title"]


admin.site.register(Program)
