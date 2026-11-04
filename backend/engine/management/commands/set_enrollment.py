"""
Sets the number of students per program and year level, so room capacity and the Gen Ed exam "combine low-enrollment sections" rule
(exams.services / engine.merging) work from the real enrollment.

    python manage.py set_enrollment --dry-run     # show what would change
    python manage.py set_enrollment               # apply the built-in counts below
    python manage.py set_enrollment --semester "1st Sem"

The count of a year level is its TOTAL; when a year level has several sections the total is shared between them. Programs that are
not listed, and sections you edited by hand for other programs, are never touched. Nothing is created or deleted.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from engine.models import Section

YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
COUNTS = {
    "BS Computer Science": [15, 15, 10, 20],
    "BS Information Technology": [15, 16, 10, 9],
    "BS Radiologic Technology": [25, 30, 25, 30],
    "BA Communication": [5, 5, 6, 9],
}


class Command(BaseCommand):
    help = "Set students per program / year level (CS, IT, RadTech, BA) from the Registrar's enrollment counts."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--semester", default="", help="only this semester label, e.g. '1st Sem' (default: every semester)")

    @transaction.atomic
    def handle(self, *a, **o):
        changed = 0
        for program, per_year in COUNTS.items():
            for year, total in zip(YEARS, per_year):
                qs = Section.objects.filter(program__name=program, year_level=year)
                if o["semester"]:
                    qs = qs.filter(semester=o["semester"])
                by_sem = {}
                for s in qs.order_by("name", "id"):
                    by_sem.setdefault(s.semester, []).append(s)
                if not by_sem:
                    self.stdout.write(self.style.WARNING(f"{program} {year}: no section found"))
                for sem, secs in by_sem.items():
                    for i, s in enumerate(secs):
                        n = total // len(secs) + (1 if i < total % len(secs) else 0)
                        if s.student_count != n:
                            self.stdout.write(f"{program} {year} {sem} {s.name}: {s.student_count} -> {n}")
                            changed += 1
                            if not o["dry_run"]:
                                s.student_count = n
                                s.save(update_fields=["student_count"])
        if o["dry_run"]:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f"{'Would change' if o['dry_run'] else 'Changed'} {changed} section(s)."))
