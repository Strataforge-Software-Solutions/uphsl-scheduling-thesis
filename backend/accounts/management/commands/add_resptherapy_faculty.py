"""
Respiratory Therapy faculty for the Allied Health college: 4 full-time + 2 part-time (made-up demo names).

    python manage.py add_resptherapy_faculty            # DRY RUN: shows what would be created
    python manage.py add_resptherapy_faculty --apply    # create them (safe to re-run: an existing ID is skipped)

Login UPHM-<ID>, first password = the ID (they must change it on first login). Department = the one BS Respiratory Therapy uses
(e.g. "College of Allied Health"). Each has a Respiratory Therapy degree and the "Respiratory Therapy" specialization, so the RT major
subjects (field "Respiratory Therapy") can be given to them; the second specialization follows the RT curriculum's subject areas.
No dean account is created, and no existing account is changed.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

User = get_user_model()

# (school_id, first name, last name, faculty_type, degree, [specializations])
FACULTY = [
    ("F1081", "Ramon", "Esguerra", "full_time", "BS Respiratory Therapy, MS Respiratory Care", ["Respiratory Therapy", "Mechanical Ventilation"]),
    ("F1082", "Liza", "Manalastas", "full_time", "BS Respiratory Therapy, RRT", ["Respiratory Therapy", "Critical Care"]),
    ("F1083", "Paolo", "Ignacio", "full_time", "BS Respiratory Therapy, RRT", ["Respiratory Therapy", "Pulmonary Function Testing"]),
    ("F1084", "Marivic", "Tolentino", "full_time", "BS Respiratory Therapy, RRT", ["Respiratory Therapy", "Neonatal and Pediatric Respiratory Care"]),
    ("P1060", "Jose", "Lacson", "part_time", "BS Respiratory Therapy, RRT", ["Respiratory Therapy", "Polysomnography"]),
    ("P1061", "Ana", "Belmonte", "part_time", "BS Respiratory Therapy, RRT", ["Respiratory Therapy", "Pulmonary Rehabilitation"]),
]


def department():
    from curriculum.models import Program
    prog = Program.objects.filter(name="BS Respiratory Therapy").first()
    if prog is None:
        raise CommandError("BS Respiratory Therapy does not exist yet: run seed_resptherapy_curriculum --apply first.")
    return prog.department


class Command(BaseCommand):
    help = "Add 4 full-time + 2 part-time Respiratory Therapy faculty (Allied Health). Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="create the accounts (default: dry run, nothing is written)")

    def handle(self, *args, **o):
        dept = department()
        self.stdout.write(f"Department: {dept}")
        todo = []
        for sid, first, last, ftype, degree, specs in FACULTY:
            have = User.objects.filter(school_id=sid).first() or User.objects.filter(username=f"UPHM-{sid}").first()
            if have is None:
                todo.append((sid, first, last, ftype, degree, specs))
                self.stdout.write(f"  add   UPHM-{sid:6} {first} {last:12} {ftype:9} {degree} | {', '.join(specs)}")
            elif (have.first_name, have.last_name) == (first, last):
                self.stdout.write(f"  keep  UPHM-{sid:6} {first} {last} (already created)")
            else:
                self.stdout.write(self.style.WARNING(f"  skip  {sid}: already belongs to {have.get_full_name()} ({have.department}); not changed"))
        self.stdout.write(f"Summary: {len(todo)} to add. No dean account, rooms, sections or schedules are touched.")
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN: nothing was written. Run again with --apply to create them."))
            return
        self.stdout.write(self.style.SUCCESS(f"Done: {self.create(todo, dept)} faculty created (first password = their ID)."))

    @transaction.atomic
    def create(self, todo, dept):
        from curriculum.models import AcademicField
        from faculty.models import FacultyProfile
        for sid, first, last, ftype, degree, specs in todo:
            u = User(school_id=sid, first_name=first, last_name=last, role="faculty", faculty_type=ftype, department=dept,
                     must_change_password=True)
            u.set_password(sid)
            u.save()
            p, _ = FacultyProfile.objects.get_or_create(user=u)
            p.degree = degree
            p.save(update_fields=["degree"])
            p.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in specs])
        return len(todo)
