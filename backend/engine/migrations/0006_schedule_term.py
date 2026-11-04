from django.db import migrations, models


def backfill_term(apps, schema_editor):
    Schedule = apps.get_model("engine", "Schedule")
    Section = apps.get_model("engine", "Section")
    for sem in Section.objects.values_list("semester", flat=True).distinct():
        Schedule.objects.filter(section__semester=sem).update(term=sem)


class Migration(migrations.Migration):

    dependencies = [("engine", "0005_shared_minor_classes")]

    operations = [
        migrations.AddField(
            model_name="schedule", name="term",
            field=models.CharField(blank=True, db_index=True, default="", max_length=20),
        ),
        migrations.RunPython(backfill_term, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="schedule", name="no_teacher_double_booking"),
        migrations.RemoveConstraint(model_name="schedule", name="no_room_double_booking"),
        migrations.AddConstraint(
            model_name="schedule",
            constraint=models.UniqueConstraint(condition=models.Q(("merge_key", "")), fields=("teacher", "timeslot", "term"), name="no_teacher_double_booking"),
        ),
        migrations.AddConstraint(
            model_name="schedule",
            constraint=models.UniqueConstraint(condition=models.Q(("merge_key", "")), fields=("room", "timeslot", "term"), name="no_room_double_booking"),
        ),
    ]
