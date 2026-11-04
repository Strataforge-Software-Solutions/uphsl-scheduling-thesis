"""
One-time rename: your existing sections are all named "A" regardless of
year level (that's why the admin list looked like duplicates -- it's really
1st Sem and 2nd Sem rows for the same year, both just called "A", and the
admin list doesn't show semester as a column). This renames them to
"A1"/"A2"/"A3"/"A4" by year level. Safe to re-run.

Run from backend/:
    python manage.py shell < rename_sections.py
"""
from engine.models import Section

YEAR_NUMBER = {"1st Year": "1", "2nd Year": "2", "3rd Year": "3", "4th Year": "4"}

updated = 0
for s in Section.objects.all():
    num = YEAR_NUMBER.get(s.year_level)
    if not num:
        print(f"Skipping Section #{s.id} ({s}) -- unrecognized year_level '{s.year_level}', leaving as-is.")
        continue
    new_name = f"A{num}"
    if s.name != new_name:
        print(f"Renaming Section #{s.id}: '{s.name}' -> '{new_name}'  ({s.program.name} {s.year_level}, {s.semester})")
        s.name = new_name
        s.save()
        updated += 1

print(f"\nDone. {updated} section(s) renamed.")
