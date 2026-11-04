from django.contrib import admin
from . import models as m

for model in (m.SchoolLevelConfig, m.GradeWindow, m.AcademicYear, m.CalendarPeriod, m.PeriodMapping, m.CalendarEvent, m.Strand,
              m.Section, m.Room, m.CurriculumSource, m.CurriculumSubject, m.Faculty, m.Availability, m.TeachingAssignment,
              m.ScheduleRun, m.ScheduleEntry, m.ConflictRecord, m.ScheduleEvent):
    admin.site.register(model)
