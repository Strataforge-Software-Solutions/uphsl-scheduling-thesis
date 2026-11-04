from django.core.management.base import BaseCommand  # noqa
from django.db import transaction
from curriculum.models import Program, Subject
from engine.models import Section
from curriculum.section_codes import section_name

YEAR_NUMBER = {"1st Year": "1", "2nd Year": "2", "3rd Year": "3", "4th Year": "4", "5th Year": "5"}


@transaction.atomic      # one commit instead of ~80 (far fewer round trips to a remote database)
def load(command, program_name, department, rows, skipped_note="", sizes=None, fix_department=False):
    """rows: (code, title, units, year_level, semester, classification).
    A code ending in 'L' whose lecture code exists in the same list is a lab
    subject (units go in lab_units, which makes the scheduler use a lab room)."""
    program, created = Program.objects.get_or_create(name=program_name, defaults={"department": department})
    command.stdout.write(("Created" if created else "Using existing") + f" program: {program} (department: {program.department})")
    if fix_department and program.department != department:
        command.stdout.write(command.style.WARNING(
            f"  moved program '{program.name}' from department '{program.department}' to '{department}'"))
        program.department = department
        program.save(update_fields=["department"])
    codes = {r[0] for r in rows}
    made = skipped = 0
    for code, title, units, year_level, semester, classification in rows:
        title = title if len(title) <= 150 else title[:147].rstrip() + "..."   # Subject.title is varchar(150)
        if isinstance(units, (tuple, list)):          # (lecture units, lab units) in ONE subject
            lec, lab = int(units[0]), int(units[1])
        else:
            is_lab = code.endswith("L") and code[:-1] in codes
            lec, lab = (0, int(units)) if is_lab else (int(units), 0)
        _, was_created = Subject.objects.get_or_create(
            code=code, program=program,
            defaults=dict(
                title=title, lec_units=lec, lab_units=lab,
                year_level=year_level, semester=semester, classification=classification,
            ),
        )
        made += was_created
        skipped += not was_created
    sections = 0
    for year_level, semester in {(r[3], r[4]) for r in rows}:
        if Section.objects.filter(program=program, year_level=year_level, semester=semester).exists():
            continue
        yn = int(YEAR_NUMBER.get(year_level, "0") or 0)
        count = (sizes or {}).get(yn, 40)
        Section.objects.create(name=section_name(program, year_level), program=program, year_level=year_level,
                               semester=semester, student_count=count)
        sections += 1
    command.stdout.write(command.style.SUCCESS(
        f"Done. {made} subjects created, {skipped} already existed. {sections} sections created."))
    if skipped_note:
        command.stdout.write(command.style.WARNING(skipped_note))
