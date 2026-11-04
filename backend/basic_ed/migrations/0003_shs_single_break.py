from datetime import time

from django.db import migrations, models


def to_single_break(apps, schema_editor):
    """SHS: one 30-minute break instead of recess + lunch, and the school hours back to Grade 11 7:00-12:30 / Grade 12 12:30-6:30 PM
    (they were only stretched by 15 minutes to make room for two breaks). Nothing else is touched; JHS keeps recess and lunch."""
    W = apps.get_model("basic_ed", "GradeWindow")
    for w in W.objects.filter(level="SHS"):
        if w.grade_level == 11:
            if w.end_time == time(12, 45):
                w.end_time = time(12, 30)
            w.break_start, w.break_end = time(9, 30), time(10, 0)
        elif w.grade_level == 12:
            if w.start_time == time(12, 45):
                w.start_time = time(12, 30)
            w.break_start, w.break_end = time(15, 0), time(15, 30)
        else:
            continue
        w.recess_start = w.recess_end = w.lunch_start = w.lunch_end = None
        w.save()


class Migration(migrations.Migration):
    dependencies = [("basic_ed", "0002_grade_window_breaks")]
    operations = [
        migrations.AddField(model_name="gradewindow", name="break_start", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="gradewindow", name="break_end", field=models.TimeField(blank=True, null=True)),
        migrations.RunPython(to_single_break, migrations.RunPython.noop),
    ]
