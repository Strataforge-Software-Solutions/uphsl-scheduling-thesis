"""
Adds the 13 new faculty accounts (8 full-time, 5 part-time) with their
department and specialization(s).

    python manage.py add_faculty_accounts

Safe to re-run: anyone whose school_id already exists is skipped (never
overwritten). Default password = school ID; they must change it on first login.

Special case: the old demo part-time account "Carlo Dizon" used school_id F1002.
That ID now belongs to Jamie Valley, so if Carlo is still sitting on F1002 this
command renames him to P1001 (keeping his schedules/availability) to free the
ID -- matching the F1002 -> P1001 convention change made earlier.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField
from faculty.models import FacultyProfile

User = get_user_model()

CAS = "College of Arts and Science"

FACULTY = [
    # school_id, full name, faculty_type, department, [specializations]
    ("F1002", "Jamie Valley",  "full_time", CAS,                 ["BA in Filipino"]),
    ("F1003", "Kaine Qis",     "full_time", CAS,                 ["FCL"]),
    ("F1004", "Jeremy Poi",    "full_time", "SHS",               ["BA in Physical Education"]),
    ("F1005", "Lance Pingles", "full_time", CAS,                 ["Major in English Literature"]),
    ("F1006", "Fred Gergia",   "full_time", "Computer Studies",  ["BS Computer Science"]),
    ("F1007", "Michael Heins", "full_time", "Computer Studies",  ["BS Information Technology"]),
    ("F1008", "Billy Oggly",   "full_time", "Computer Studies",  ["Major in Mathematics"]),
    ("F1009", "Henry Thaylor", "full_time", CAS,                 ["BA Filipino", "Major in Literature", "FCL"]),

    ("P1002", "Engr. Gregory Stanley", "part_time", "Computer Studies", ["BS in Computer Engineering"]),
    ("P1003", "Engr. Carl Niel",       "part_time", "Computer Studies", ["BS in Mechanical Engineering"]),
    ("P1004", "Tristan Wiq",           "part_time", CAS,                ["BEd in Filipino", "Physical Education", "Literature"]),
    ("P1005", "Dr. Fiona Hailer, MD",  "part_time", "Nursing",          ["Doctor in Medicine"]),
    ("P1006", "Billy Densley",         "part_time", CAS,                ["FCL", "BEd in Literature"]),
]


class Command(BaseCommand):
    help = "Create the 13 new full-time/part-time faculty accounts with specializations."

    def handle(self, *args, **options):
        self._free_up_f1002()

        created, skipped = 0, []
        for school_id, full_name, ftype, department, specs in FACULTY:
            existing = User.objects.filter(school_id=school_id).first()
            if existing:
                skipped.append((school_id, full_name, existing.get_full_name(), existing.department))
                continue

            # Split on the LAST space; Django's get_full_name() re-joins with a
            # single space, so the display name comes out exactly as typed
            # (including "Engr." / ", MD").
            first_name, last_name = full_name.rsplit(" ", 1)
            with transaction.atomic():
                user = User(
                    school_id=school_id, first_name=first_name, last_name=last_name,
                    role="faculty", faculty_type=ftype, department=department,
                    must_change_password=True,
                )
                user.set_password(school_id)
                user.save()
                profile, _ = FacultyProfile.objects.get_or_create(user=user)
                profile.specializations.set(
                    [AcademicField.objects.get_or_create(name=s)[0] for s in specs]
                )
            created += 1
            self.stdout.write(f"  created {user.username}  {full_name}  ({ftype}, {department})  {specs}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. {created} created, {len(skipped)} skipped."))
        for school_id, wanted, have, dept in skipped:
            self.stdout.write(self.style.WARNING(
                f"  skipped {school_id}: wanted '{wanted}', but that ID already belongs to '{have}' ({dept}). Nothing changed."
            ))

    def _free_up_f1002(self):
        old = User.objects.filter(school_id="F1002", first_name="Carlo", last_name="Dizon").first()
        if not old:
            return
        if User.objects.filter(school_id="P1001").exists():
            self.stdout.write(self.style.WARNING(
                "Old demo account Carlo Dizon is still on F1002 but P1001 is already taken -- "
                "rename him manually in Django admin, then re-run."
            ))
            return
        old.school_id = "P1001"
        old.username = "UPHM-P1001"
        old.save()
        self.stdout.write(self.style.SUCCESS("Renamed old demo account Carlo Dizon: F1002 -> P1001 (frees F1002 for Jamie Valley)."))
