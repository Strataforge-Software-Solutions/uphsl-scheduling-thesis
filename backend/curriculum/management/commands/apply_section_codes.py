"""
Renames every existing section to its program code + year number (CS1, IT2, RAD3, BAC1, TM4, HM1, HRDM2, MM3, N1, PT1, OT2,
RT3; other programs I, J, ...). See curriculum/section_codes.py. When a program has more than one section in the same year level
and semester, a letter is added in the current name order: CS1A, CS1B, ...

    python manage.py apply_section_codes            (preview: lists every change, writes nothing)
    python manage.py apply_section_codes --apply    (rename)

Only the name changes; schedules, exams, class lists and shared classes stay attached (they point to the section, not its name).
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.section_codes import section_name
from engine.models import Section


def planned_names():
    """{section id: new name} for every section."""
    groups = defaultdict(list)
    for sec in Section.objects.select_related("program").order_by("program__id", "year_level", "semester", "name", "id"):
        groups[(sec.program_id, sec.year_level, sec.semester)].append(sec)
    out = {}
    for secs in groups.values():
        base = section_name(secs[0].program, secs[0].year_level)
        for i, sec in enumerate(secs):
            out[sec.id] = base if len(secs) == 1 else f"{base}{chr(ord('A') + i)}"
    return out


class Command(BaseCommand):
    help = "Rename sections to the program codes (CS1, IT1, RAD1, BAC1, TM1, HM1, HRDM1, MM1, N1, PT1, OT1, RT1, ...)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        plan = planned_names()
        changes = 0
        with transaction.atomic():
            for sec in Section.objects.select_related("program").order_by("program__name", "year_level", "semester", "name"):
                new = plan[sec.id]
                if new == sec.name:
                    continue
                self.stdout.write(f"  {sec.program.name:45} {sec.year_level:9} {sec.semester:8} {sec.name} -> {new}")
                changes += 1
                if o["apply"]:
                    sec.name = new
                    sec.save(update_fields=["name"])
        self.stdout.write(self.style.SUCCESS(f"{changes} section(s) {'renamed' if o['apply'] else 'would be renamed'}."))
        if changes and not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Nothing was changed. Add --apply to rename."))
