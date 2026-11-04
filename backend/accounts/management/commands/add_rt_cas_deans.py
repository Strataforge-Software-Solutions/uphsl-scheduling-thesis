"""
Creates the two Dean logins:  DeanRT (Radiologic Technology)  and
DeanCAS (College of Arts and Science, which owns BA Communication).

    python manage.py add_rt_cas_deans

Login: username DeanRT / password RT   and   DeanCAS / CAS  (forced change on first login).
Names are demo names -- change them in Django admin.

If you already ran seed_college_deans before, the old accounts "DeanRadtech" and
"DeanCas" are RENAMED to DeanRT / DeanCAS (and their password reset to RT / CAS)
instead of creating a second Dean for the same department. It also moves BA
Communication (program, faculty) from the department text "Communication" or
"Arts and Sciences" to "College of Arts and Science", so everything matches.
Safe to re-run.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import Program
from faculty.models import FacultyProfile

User = get_user_model()

CAS = "College of Arts and Science"
# new username, old username, school_id/password, first, last, department
DEANS = [
    ("DeanRT",  "DeanRadtech", "RT",  "Dr. Noel Juan", "Acosta", "Radiologic Technology"),
    ("DeanCAS", "DeanCas",     "CAS", "Dr. Marivic D.", "Tañedo",     CAS),
]


class Command(BaseCommand):
    help = "Create DeanRT and DeanCAS logins (renames old DeanRadtech / DeanCas if present)."

    @transaction.atomic
    def handle(self, *args, **options):
        for new, old, code, first, last, dept in DEANS:
            if User.objects.filter(username=new).exists():
                self.stdout.write(f"{new} already exists -- skipped.")
                continue
            user = User.objects.filter(username=old).first()
            if user:
                user.username, user.school_id, user.department = new, code, dept
                user.faculty_type, user.role = "dean", "faculty"
                verb = f"Renamed {old} -> {new}"
            else:
                user = User(username=new, school_id=code, first_name=first, last_name=last,
                            role="faculty", faculty_type="dean", department=dept)
                verb = f"Created {new}"
            user.must_change_password = True
            user.set_password(code)
            user.save()
            FacultyProfile.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(f"{verb} ({dept}). Login: {new} / {code}"))

        # Keep BA Communication under the College of Arts and Science everywhere.
        moved = Program.objects.filter(name="BA Communication").exclude(department=CAS).update(department=CAS)
        fac = User.objects.filter(role="faculty", department__in=["Communication", "Arts and Sciences"]).update(department=CAS)
        if moved or fac:
            self.stdout.write(f"Moved BA Communication program ({moved}) and {fac} faculty/dean account(s) to '{CAS}'.")
        others = User.objects.filter(role="faculty", faculty_type="dean").values_list("username", "department")
        self.stdout.write("Deans now: " + ", ".join(f"{u} ({d})" for u, d in others))
