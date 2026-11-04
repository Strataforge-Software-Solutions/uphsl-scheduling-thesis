"""
Adds 6 DEMO Gen Ed faculty accounts (names are made up), all in the College of Arts and Science:
    2 full-time FCL (Filipino Christian Living)   F1018, F1019
    2 part-time English                            P1015, P1016
    2 part-time Mathematics                        P1017, P1018

    python manage.py add_gened_faculty

Safe to re-run: existing school IDs are skipped. Default password = school ID;
they must change it on first login.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField
from faculty.models import FacultyProfile

User = get_user_model()
CAS = "College of Arts and Science"

FACULTY = [
    ("F1018", "Ramon Dela Cruz",   "full_time", CAS, ["FCL", "Religious Education"]),
    ("F1019", "Sister Teresa Lim", "full_time", CAS, ["FCL", "Values Education"]),
    ("P1015", "Katrina Alvarez",   "part_time", CAS, ["BEd in English", "English Proficiency"]),
    ("P1016", "Marcus Villaruz",   "part_time", CAS, ["BA in English", "Purposive Communication"]),
    ("P1017", "Dr. Elaine Soriano","part_time", CAS, ["Major in Mathematics", "Statistics"]),
    ("P1018", "Jerome Bautista",   "part_time", CAS, ["BS in Mathematics", "Mathematics in the Modern World"]),
]


class Command(BaseCommand):
    help = "Create demo Gen Ed faculty (FCL, English, Math)."

    def handle(self, *args, **options):
        created, skipped = 0, []
        for school_id, full_name, ftype, department, specs in FACULTY:
            existing = User.objects.filter(school_id=school_id).first()
            if existing:
                skipped.append((school_id, full_name, existing.get_full_name(), existing.department))
                continue
            first_name, last_name = full_name.rsplit(" ", 1)
            with transaction.atomic():
                user = User(
                    school_id=school_id, first_name=first_name, last_name=last_name,
                    role="faculty", faculty_type=ftype, department=department, must_change_password=True,
                )
                user.set_password(school_id)
                user.save()
                profile, _ = FacultyProfile.objects.get_or_create(user=user)
                profile.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in specs])
            created += 1
            self.stdout.write(f"  created {user.username}  {full_name}  ({ftype}, {department})  {specs}")
        self.stdout.write(self.style.SUCCESS(f"\nDone. {created} created, {len(skipped)} skipped."))
        for school_id, wanted, have, dept in skipped:
            self.stdout.write(self.style.WARNING(
                f"  skipped {school_id}: wanted '{wanted}', but that ID already belongs to '{have}' ({dept}). Nothing changed."))
