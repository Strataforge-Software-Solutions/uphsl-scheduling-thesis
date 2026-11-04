import re

from django.db import migrations


# (aliases, building, number, label, capacity) -- same figures as rooms/gti_data.py
LABS = [
    (("COMPLABC", "LABC", "COMPUTERLABC", "D307", "307D"), "D", "307", "Comp Lab C", 40),
    (("COMPLABD", "LABD", "COMPUTERLABD", "D309", "309D"), "D", "309", "Comp Lab D", 40),
]


def key(text):
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


def ensure(apps, schema_editor):
    """Computer Laboratory C and D must be selectable. An existing record (found by name, label or building + number, whatever the spelling)
    is left exactly as it is; one is created only when none exists. Never duplicates."""
    Room = apps.get_model("rooms", "Room")
    Program = apps.get_model("curriculum", "Program")
    existing = list(Room.objects.all())
    dept = next((d for d in Program.objects.values_list("department", flat=True).distinct() if d and "comput" in d.lower()), None)
    for aliases, b, num, label, cap in LABS:
        want = set(aliases)
        if any({key(r.name), key(r.label), key(f"{r.building}{r.room_number}"), key(f"{r.room_number}{r.building}")} & want for r in existing):
            continue
        Room.objects.create(name=label, building=b, room_number=num, label=label, capacity=cap, capacity_is_estimate=True,
                            room_type="lab", department=dept)


class Migration(migrations.Migration):
    dependencies = [("rooms", "0004_department_rooms_enrollment"), ("curriculum", "0001_initial")]
    operations = [migrations.RunPython(ensure, migrations.RunPython.noop)]
