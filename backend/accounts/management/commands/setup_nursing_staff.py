"""
Creates the Nursing Dean (if missing) and tops Nursing faculty up to 6 full-time + 6 part-time.

    python manage.py setup_nursing_staff

Dean:    DeanNursing / NURS   (forced to change the password on first login)
Faculty: login UPHM-<ID>, first password = the ID (F1044-F1049, P1039-P1044; names are made-up demo names).
Safe to re-run: an ID or username that already exists is skipped.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField, Program
from faculty.models import FacultyProfile

User = get_user_model()
NURS = "Nursing"

FACULTY = [
    ("F1044", "Dr. Lourdes Navarro", "full_time", ["Nursing", "Medical-Surgical Nursing"]),
    ("F1045", "Maricel Dumlao", "full_time", ["Nursing", "Fundamentals of Nursing"]),
    ("F1046", "Ronaldo Pascual", "full_time", ["Nursing", "Community Health Nursing"]),
    ("F1047", "Josefina Alcantara", "full_time", ["Nursing", "Maternal and Child Nursing"]),
    ("F1048", "Kevin Salonga", "full_time", ["Nursing", "Nursing Leadership and Management"]),
    ("F1049", "Angelica Bustamante", "full_time", ["Nursing", "Psychiatric Nursing"]),
    ("P1039", "Dr. Ramon Escudero, MD", "part_time", ["Pharmacology", "Pathophysiology"]),
    ("P1040", "Cristina Valdez", "part_time", ["Nursing", "Nursing Research"]),
    ("P1041", "Dennis Manalastas", "part_time", ["Anatomy", "Physiology"]),
    ("P1042", "Dr. Helen Ocampo, RND", "part_time", ["Nutrition and Diet Therapy", "Biochemistry"]),
    ("P1043", "Marvin Tolentino", "part_time", ["Nursing", "Emergency and Disaster Nursing"]),
    ("P1044", "Sheryl Aquino", "part_time", ["Nursing", "Gerontologic Nursing"]),
]


class Command(BaseCommand):
    help = "Create the Nursing Dean and 6 full-time + 6 part-time Nursing faculty."

    @transaction.atomic
    def handle(self, *args, **options):
        Program.objects.get_or_create(name="BS Nursing", defaults={"department": NURS})
        if User.objects.filter(role="faculty", faculty_type="dean", department=NURS).exists():
            d = User.objects.filter(role="faculty", faculty_type="dean", department=NURS).first()
            self.stdout.write(f"Nursing dean already exists ({d.username}) -- skipped.")
        else:
            u = User(username="DeanNursing", school_id="NURS", first_name="Grace", last_name="Villanueva",
                     role="faculty", faculty_type="dean", department=NURS, must_change_password=True)
            u.set_password("NURS")
            u.save()
            FacultyProfile.objects.get_or_create(user=u)
            self.stdout.write(self.style.SUCCESS("Created DeanNursing (Nursing). Login: DeanNursing / NURS"))

        made = 0
        for sid, full_name, ftype, specs in FACULTY:
            # Top up to exactly 6 of each type (an older demo part-timer, e.g. P1005, may already count).
            if not User.objects.filter(school_id=sid).exists() and \
               User.objects.filter(role="faculty", faculty_type=ftype, department=NURS).count() >= 6:
                continue
            have = User.objects.filter(school_id=sid).first()
            if have:
                if have.get_full_name() != full_name:
                    self.stdout.write(self.style.WARNING(f"  skipped {sid}: already belongs to '{have.get_full_name()}'."))
                continue
            first, last = full_name.rsplit(" ", 1)
            user = User(school_id=sid, first_name=first, last_name=last, role="faculty",
                        faculty_type=ftype, department=NURS, must_change_password=True)
            user.set_password(sid)
            user.save()
            prof, _ = FacultyProfile.objects.get_or_create(user=user)
            prof.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in specs])
            made += 1
            self.stdout.write(f"  created {user.username}  {full_name}  ({ftype})")
        ft = User.objects.filter(role="faculty", faculty_type="full_time", department=NURS).count()
        pt = User.objects.filter(role="faculty", faculty_type="part_time", department=NURS).count()
        self.stdout.write(self.style.SUCCESS(f"Done. {made} created. Nursing now has {ft} full-time, {pt} part-time."))
