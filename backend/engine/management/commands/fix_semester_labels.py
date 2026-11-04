"""
Tidies stray semester labels such as "1st" or "2nd" (the Semester drop-downs list
whatever is stored) into the standard "1st Sem" / "2nd Sem".

    python manage.py fix_semester_labels          # show what would change
    python manage.py fix_semester_labels --apply  # do it

If a section with the proper label already exists and the stray one has no
class schedule rows, the stray duplicate is deleted; otherwise it is renamed.
"""
from django.core.management.base import BaseCommand

from curriculum.models import Subject
from engine.models import Schedule, Section

MAP = {"1st": "1st Sem", "1": "1st Sem", "first": "1st Sem", "1st semester": "1st Sem",
       "2nd": "2nd Sem", "2": "2nd Sem", "second": "2nd Sem", "2nd semester": "2nd Sem"}


class Command(BaseCommand):
    help = "Rename stray semester labels (e.g. '1st') to '1st Sem' / '2nd Sem'."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        apply = o["apply"]
        changed = 0
        for sec in Section.objects.all():
            new = MAP.get((sec.semester or "").strip().lower())
            if not new:
                continue
            twin = Section.objects.filter(program=sec.program, year_level=sec.year_level,
                                          semester=new, name=sec.name).exclude(pk=sec.pk).first()
            has_rows = Schedule.objects.filter(section=sec).exists()
            if twin and not has_rows:
                self.stdout.write(f"  delete duplicate section {sec.name} {sec.year_level} '{sec.semester}' (same exists as '{new}')")
                if apply:
                    sec.delete()
            elif twin:
                self.stdout.write(f"  SKIP {sec.name} {sec.year_level} '{sec.semester}': has class rows and a '{new}' twin -- fix by hand in admin")
                continue
            else:
                self.stdout.write(f"  rename section {sec.name} {sec.year_level} '{sec.semester}' -> '{new}'")
                if apply:
                    sec.semester = new
                    sec.save(update_fields=["semester"])
                    Schedule.objects.filter(section=sec).update(term=new)
            changed += 1
        for sub in Subject.objects.all():
            new = MAP.get((sub.semester or "").strip().lower())
            if new:
                clash = Subject.objects.filter(code=sub.code, program=sub.program, semester=new).exclude(pk=sub.pk).exists()
                self.stdout.write(f"  subject {sub.code} '{sub.semester}' -> '{new}'" + ("  (SKIPPED: duplicate exists)" if clash else ""))
                if apply and not clash:
                    sub.semester = new
                    sub.save(update_fields=["semester"])
                changed += 1
        self.stdout.write(self.style.SUCCESS(f"{changed} item(s) {'fixed' if apply else 'would change (run again with --apply)'}."))
