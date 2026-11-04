"""
Renames every existing section to its department's block letter + year number
(CS A1.., IT A.b1.., Allied Health/PT B1.., OT B.b1.., RT B.c1.., BA Comm C1..,
RadTech D1.., other programs E, F, ...). See curriculum/section_codes.py.

    python manage.py apply_section_codes            (preview)
    python manage.py apply_section_codes --apply    (rename)

Only the name changes; schedules, exams and class lists stay attached.
"""
from django.core.management.base import BaseCommand

from curriculum.section_codes import section_name
from engine.models import Section


class Command(BaseCommand):
    help = "Rename sections to the per-department block letters (A, A.b, B, B.b, B.c, C, D, ...)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        changes = 0
        for sec in Section.objects.select_related("program").order_by("program__id", "year_level", "semester"):
            new = section_name(sec.program, sec.year_level)
            if new != sec.name:
                self.stdout.write(f"  {sec.program.name:32} {sec.year_level:9} {sec.semester:8} {sec.name} -> {new}")
                changes += 1
                if o["apply"]:
                    sec.name = new
                    sec.save(update_fields=["name"])
        self.stdout.write(self.style.SUCCESS(f"{changes} section(s) {'renamed' if o['apply'] else 'would be renamed'}."))
        if changes and not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to rename."))
