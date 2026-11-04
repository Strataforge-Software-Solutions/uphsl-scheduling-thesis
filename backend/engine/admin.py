from django.contrib import admin
from .models import Section, Student, TimeSlot, Schedule, Constraint, Log, ConflictLog


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    # Section.__str__ ("<program> <year_level> - <name>") leaves out semester,
    # so the 1st-Sem and 2nd-Sem row for the same year level look identical
    # in the default admin list -- it looks like duplicates even though it
    # isn't. Showing semester as its own column makes that visible again.
    list_editable = ("student_count",)
    list_display = ("program", "year_level", "semester", "name", "student_count")
    list_filter = ("program", "year_level", "semester")


for m in (Student, TimeSlot, Schedule, Constraint, Log, ConflictLog):
    admin.site.register(m)
