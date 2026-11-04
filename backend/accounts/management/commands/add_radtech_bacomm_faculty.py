"""
Adds 16 DEMO faculty accounts (names are made up) for the two newly added programs:
Radiologic Technology (department "Radiologic Technology": 4 full-time + 4 part-time) and
BA Communication (department "College of Arts and Science": 4 full-time + 4 part-time).

    python manage.py add_radtech_bacomm_faculty

The department text must match the program's department exactly, so if you
loaded BA Comm with --department "Something Else", edit DEPT_BACOMM below (or
change it in Django admin). Safe to re-run: existing school IDs are skipped.
Default password = school ID; they must change it on first login.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField
from faculty.models import FacultyProfile

User = get_user_model()

DEPT_RAD = "Radiologic Technology"
DEPT_BACOMM = "College of Arts and Science"

FACULTY = [
    # school_id, full name, faculty_type, department, [specializations]
    ("F1010", "Marco Villareal",       "full_time", DEPT_RAD, ["BS Radiologic Technology", "Radiographic Positioning"]),
    ("F1011", "Elena Dumlao",          "full_time", DEPT_RAD, ["BS Radiologic Technology", "Radiation Physics"]),
    ("F1012", "Rafael Montano",        "full_time", DEPT_RAD, ["BS Radiologic Technology", "Imaging Equipment"]),
    ("F1013", "Dr. Ana Lourdes Reyes", "full_time", DEPT_RAD, ["Human Anatomy and Physiology", "Medical Terminology"]),
    ("P1007", "Dr. Paolo Cañete, MD",  "part_time", DEPT_RAD, ["Doctor in Medicine", "Radiologic Pathology"]),
    ("P1008", "Grace Ilagan",          "part_time", DEPT_RAD, ["BS Radiologic Technology", "Ultrasonography"]),
    ("P1009", "Dennis Bautista",       "part_time", DEPT_RAD, ["BS Radiologic Technology", "Computed Tomography"]),
    ("P1010", "Dr. Liza Fernandez",    "part_time", DEPT_RAD, ["Pharmacology", "Patient Care"]),

    ("F1014", "Camille Ortega",        "full_time", DEPT_BACOMM, ["BA Communication", "Journalism"]),
    ("F1015", "Joaquin Mercado",       "full_time", DEPT_BACOMM, ["BA Communication", "Film and Media Production"]),
    ("P1011", "Bea Salvador",          "part_time", DEPT_BACOMM, ["BA Communication", "Advertising and Marketing Communication"]),
    ("P1012", "Noel Abrenica",         "part_time", DEPT_BACOMM, ["BA Communication", "Broadcasting"]),
    ("F1016", "Patricia Lazaro",       "full_time", DEPT_BACOMM, ["BA Communication", "Public Relations"]),
    ("F1017", "Gerald Pascual",        "full_time", DEPT_BACOMM, ["BA Communication", "Communication Research"]),
    ("P1013", "Mia Constantino",       "part_time", DEPT_BACOMM, ["BA Communication", "Social Media and Digital Content"]),
    ("P1014", "Rommel Aquino",         "part_time", DEPT_BACOMM, ["BA Communication", "Organizational Communication"]),
]


class Command(BaseCommand):
    help = "Create demo faculty for Radiologic Technology and BA Communication."

    def handle(self, *args, **options):
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
