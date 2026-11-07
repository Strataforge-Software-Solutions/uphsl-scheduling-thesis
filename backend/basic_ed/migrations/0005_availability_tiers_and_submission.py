from django.db import migrations, models


def forward(apps, schema_editor):
    Availability = apps.get_model("basic_ed", "Availability")
    Faculty = apps.get_model("basic_ed", "Faculty")
    # old yes/no windows keep their meaning
    Availability.objects.filter(available=True).update(preference="available")
    Availability.objects.filter(available=False).update(preference="unavailable")
    # teachers who already have availability: already "Submitted", so the generator behaves exactly as before
    from django.utils import timezone
    ids = Availability.objects.values_list("faculty_id", flat=True).distinct()
    Faculty.objects.filter(id__in=list(ids)).update(availability_status="submitted", availability_submitted_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("basic_ed", "0004_qualification_override")]

    operations = [
        migrations.AddField("availability", "preference", models.CharField(
            max_length=11, default="available",
            choices=[("preferred", "Preferred"), ("available", "Available"), ("unavailable", "Unavailable")])),
        migrations.AddField("faculty", "availability_status", models.CharField(
            max_length=13, default="not_submitted",
            choices=[("not_submitted", "Not submitted"), ("submitted", "Submitted"), ("returned", "Returned for correction")])),
        migrations.AddField("faculty", "availability_submitted_at", models.DateTimeField(null=True, blank=True)),
        migrations.AddField("faculty", "availability_note", models.CharField(max_length=300, blank=True, default="")),
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
