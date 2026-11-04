"""
Seeds one Dean login per college, each scoped to their own department -- since
FacultyDashboard's DeanView already filters everything (curriculum, schedules,
exam schedules, analytics) by `user.department`, each Dean automatically gets
their own isolated view with zero overlap, no code changes needed for this.

Also creates one minimal Program per college so each Dean's Program dropdown
isn't empty on first login -- they can add real curriculum themselves via the
existing Curriculum Mgmt tab, same as CS's Dean already does.

Login IDs are literal (no "UPHM-" prefix) per explicit request, e.g. "DeanCS".
Default password = the college code shown in parentheses below; forced change
on first login, same as every other account in this system.

Run with: python manage.py seed_college_deans
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from curriculum.models import Program
from faculty.models import FacultyProfile

User = get_user_model()

# (login_username, school_id_code, first, last, department, starter_program_name)
# NOTE: Computer Studies is intentionally NOT listed here -- UPHM-D1001 (from
# seed_demo_data) already is that college's Dean. Adding a second "DeanCS"
# account would create two different Dean logins for the same department.
COLLEGES = [
    ("DeanNursing", "NURS", "Darwin D.", "Aznar", "Nursing", "BS Nursing"),
    # Business Administration and Tourism/Hospitality now come from `python manage.py setup_cba_cihm`
    # (DeanCBA / DeanCIHM, with their real curricula).
    ("DeanCAS", "CAS", "Corazon", "Reyes", "College of Arts and Science", "BA Communication"),
    ("DeanRT", "RT", "Aira", "Gargantos", "Radiologic Technology", "BS Radiologic Technology"),
    ("DeanAllied", "ALLIED", "Bernadette", "Fernan", "Allied Health", "BS Medical Technology"),
]


class Command(BaseCommand):
    help = "Seed one Dean login per college, each with their own department and starter Program."

    def handle(self, *args, **options):
        for username, code, first, last, department, program_name in COLLEGES:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "school_id": code, "first_name": first, "last_name": last,
                    "role": "faculty", "faculty_type": "dean", "department": department,
                    "must_change_password": True,
                },
            )
            if created:
                user.set_password(code)  # default password = college code
                user.save()
                FacultyProfile.objects.get_or_create(user=user)
                self.stdout.write(self.style.SUCCESS(f"Created {username} / {code} -> {department}"))
            else:
                self.stdout.write(f"{username} already exists -- skipped.")

            Program.objects.get_or_create(name=program_name, defaults={"department": department})

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Each Dean is scoped to their own department -- no overlap between colleges.\n"
            "Login as e.g. 'DeanNursing' / 'NURS' -- forced password change on first login."
        ))
