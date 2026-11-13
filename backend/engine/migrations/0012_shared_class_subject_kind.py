from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("engine", "0011_schedule_qualification_override")]

    operations = [
        migrations.AddField(
            model_name="sharedclassgroup",
            name="subject_kind",
            field=models.CharField(
                choices=[("major", "Major"), ("minor", "Minor")],
                default="minor",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="sharedclassexclusive",
            name="subject_kind",
            field=models.CharField(
                choices=[("major", "Major"), ("minor", "Minor")],
                default="minor",
                max_length=10,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="sharedclassexclusive",
            unique_together={("program", "code", "year_level", "semester", "subject_kind")},
        ),
    ]
