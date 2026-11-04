"""
Set how many students are in each year level of a program (used for the
room-size preference and the class lists).

    python manage.py set_section_sizes --program "BS Computer Science" --sizes 30,28,20,21
    python manage.py set_section_sizes --program "BA Communication" --year "1st Year" --count 20

--sizes gives the counts for 1st, 2nd, 3rd, 4th (5th) year in order and applies to
both semesters. You can also edit "student count" directly in Django admin > Sections.
"""
from django.core.management.base import BaseCommand, CommandError

from curriculum.section_codes import year_number
from engine.models import Section


class Command(BaseCommand):
    help = "Set student counts for a program's sections."

    def add_arguments(self, parser):
        parser.add_argument("--program", required=True)
        parser.add_argument("--sizes", help="Comma list for year 1,2,3,4(,5), e.g. 30,28,20,21")
        parser.add_argument("--year")
        parser.add_argument("--count", type=int)

    def handle(self, *args, **o):
        secs = Section.objects.filter(program__name=o["program"])
        if not secs.exists():
            raise CommandError(f"No sections found for program '{o['program']}'.")
        by_year = {}
        if o["sizes"]:
            by_year = {str(i + 1): int(x) for i, x in enumerate(o["sizes"].split(","))}
        elif o["year"] and o["count"] is not None:
            by_year = {year_number(o["year"]): o["count"]}
        else:
            raise CommandError("Give either --sizes 30,28,20,21 or --year ... --count ...")
        n = 0
        for sec in secs:
            yn = year_number(sec.year_level)
            if yn in by_year:
                sec.student_count = by_year[yn]
                sec.save(update_fields=["student_count"])
                n += 1
                self.stdout.write(f"  {sec.name} {sec.year_level} {sec.semester}: {sec.student_count} students")
        self.stdout.write(self.style.SUCCESS(f"{n} section(s) updated."))
