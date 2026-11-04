"""
Sets the student counts the user gave for the demo programs (used for room-size
preference and for deciding whether minor classes can be shared):

    python manage.py set_demo_student_counts

    BS Computer Science           : 30 / 28 / 20 / 21  (1st-4th year)
    BA Communication (BA Comm)    :  6 /  8 /  7 /  9
    Radiologic Technology (RadTech): about 36 in total -> 10 / 9 / 9 / 8
    BSBA Marketing 21/10/9/9, BSBA HRDM 9/7/14/9, BS Hospitality 39/35/34/30, BS Tourism 22/15/13/11
    (rough figures from the GTI class program -- change them to the real counts)

Edit any number later in Django admin > Sections, or with
    python manage.py set_section_sizes --program "<name>" --sizes a,b,c,d
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from curriculum.models import Program

PLAN = [
    (("computer science",), "30,28,20,21"),
    (("communication", "bacomm", "ba comm"), "6,8,7,9"),
    (("radiologic", "radtech"), "10,9,9,8"),
    (("marketing",), "21,10,9,9"),
    (("human resource",), "9,7,14,9"),
    (("hospitality",), "39,35,34,30"),
    (("tourism",), "22,15,13,11"),
]


class Command(BaseCommand):
    help = "Set demo student counts for CS, BA Comm and RadTech."

    def handle(self, *args, **o):
        for keys, sizes in PLAN:
            hit = [p for p in Program.objects.all() if any(k in p.name.lower() for k in keys)]
            if not hit:
                self.stdout.write(f"  (no program matching {keys[0]!r} yet -- skipped)")
            for p in hit:
                self.stdout.write(f"{p.name}: {sizes}")
                call_command("set_section_sizes", program=p.name, sizes=sizes, stdout=self.stdout)
