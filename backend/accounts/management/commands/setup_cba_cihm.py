"""
One-time setup for the two new colleges (before or after seed_cba_cihm_curricula):

    ONE dean, DeanCBA (password CBA), heads BOTH colleges in a single dashboard:
        College of Business Administration  +  College of International Hospitality Management

    python manage.py setup_cba_cihm

It also
  * creates DEMO faculty for both colleges (names are made up; password = school ID):
        CBA : F1020-F1022 full-time, P1019-P1021 part-time
        CIHM: F1023-F1026 full-time, P1022-P1024 part-time
  * renames the older "DeanBA" login to DeanCBA; an old separate "DeanCIHM"/"DeanCithm" login is switched off;
  * sets department -> building preferences (CBA classes in the A building, hospitality/tourism in
    the Main building) and marks the two kitchens as CIHM labs so hospitality lab classes prefer them.
Safe to re-run: existing accounts/IDs are skipped.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField, Program
from faculty.models import FacultyProfile
from rooms.models import DepartmentBuilding, Room

User = get_user_model()
CBA = "College of Business Administration"
CIHM = "College of International Hospitality Management"

# ONE dean heads both colleges (one dashboard, two departments):
# new username, old username, school_id/password, first, last, department, extra department
DEANS = [
    ("DeanCBA", "DeanBA", "CBA", "Julius", "Mesina", CBA, CIHM),
]
# separate CIHM dean logins from earlier versions -- switched off so there is only one dean for both
OLD_SECOND_DEANS = ["DeanCIHM", "DeanCithm"]

FACULTY = [
    ("F1020", "Isabel Navarro",     "full_time", CBA,  ["Marketing", "Business Management"]),
    ("F1021", "Gerald Ocampo",      "full_time", CBA,  ["Human Resource Management", "Labor Law"]),
    ("F1022", "Lorna Magsaysay",    "full_time", CBA,  ["Accounting", "Taxation"]),
    ("P1019", "Atty. Daniel Pascual", "part_time", CBA, ["Business Law", "Labor Law"]),
    ("P1020", "Cecilia Domingo",    "part_time", CBA,  ["Economics", "Statistics"]),
    ("P1021", "Rafael Estrada",     "part_time", CBA,  ["Operations Management", "Entrepreneurship"]),
    ("F1023", "Chef Mario Valdez",  "full_time", CIHM, ["Culinary Arts", "Food and Beverage"]),
    ("F1024", "Patricia Soriano",   "full_time", CIHM, ["Hospitality Management", "Front Office"]),
    ("F1025", "Benedict Aquino",    "full_time", CIHM, ["Tourism Management", "Tour Guiding"]),
    ("F1026", "Chef Anna Gonzales", "full_time", CIHM, ["Baking and Pastry", "Culinary Arts"]),
    ("P1022", "Joel Manalang",      "part_time", CIHM, ["Events Management", "Tourism Management"]),
    ("P1023", "Maricar Salonga",    "part_time", CIHM, ["Foreign Language", "Tourism Management"]),
    ("P1024", "Chef Vincent Lacson", "part_time", CIHM, ["Bar and Beverage", "Food and Beverage"]),
]


class Command(BaseCommand):
    help = "Create the single DeanCBA (heads CBA + CIHM), demo faculty, building preferences and kitchen labs."

    @transaction.atomic
    def handle(self, *args, **options):
        for new, old, code, first, last, dept, extra in DEANS:
            existing = User.objects.filter(username=new).first()
            if existing:
                if existing.extra_departments != extra:
                    existing.extra_departments = extra
                    existing.save(update_fields=["extra_departments"])
                    self.stdout.write(self.style.SUCCESS(f"{new} now also heads {extra}."))
                else:
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
            user.extra_departments = extra
            user.must_change_password = True
            user.set_password(code)
            user.save()
            FacultyProfile.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(f"{verb} ({dept} + {extra}). Login: {new} / {code}"))
        for old_name in OLD_SECOND_DEANS:
            n = User.objects.filter(username=old_name, is_active=True).update(is_active=False)
            if n:
                self.stdout.write(self.style.WARNING(f"  {old_name} switched off: DeanCBA now heads both colleges."))

        # keep programs (and any older starter programs) under the full college names
        Program.objects.filter(department__in=["Business Administration"]).update(department=CBA)
        Program.objects.filter(department__in=["Tourism and Hospitality Management"]).update(department=CIHM)
        User.objects.filter(role="faculty", department="Business Administration").update(department=CBA)
        User.objects.filter(role="faculty", department="Tourism and Hospitality Management").update(department=CIHM)

        made, skipped = 0, []
        for school_id, full_name, ftype, dept, specs in FACULTY:
            existing = User.objects.filter(school_id=school_id).first()
            if existing:
                skipped.append((school_id, full_name, existing.get_full_name(), existing.department))
                continue
            first_name, last_name = full_name.rsplit(" ", 1)
            user = User(school_id=school_id, first_name=first_name, last_name=last_name, role="faculty",
                        faculty_type=ftype, department=dept, must_change_password=True)
            user.set_password(school_id)
            user.save()
            profile, _ = FacultyProfile.objects.get_or_create(user=user)
            profile.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in specs])
            made += 1
            self.stdout.write(f"  created {user.username}  {full_name}  ({ftype}, {dept})")
        for sid, wanted, have, dept in skipped:
            if wanted == have:
                self.stdout.write(f"  {sid} {wanted} already exists -- skipped.")
            else:
                self.stdout.write(self.style.WARNING(f"  skipped {sid}: wanted '{wanted}' but it already belongs to '{have}' ({dept})."))

        # preferred buildings (a preference only -- edit in Django admin > Department buildings)
        for dept, b in [(CBA, "A"), (CIHM, "M")]:
            DepartmentBuilding.objects.update_or_create(department=dept, defaults={"building": b})
        DepartmentBuilding.objects.filter(department="Tourism and Hospitality Management").delete()
        kitchens = Room.objects.filter(name__in=["M-KITCHEN-1", "M-KITCHEN-2"]).update(department=CIHM)
        # Tag the other department-specific labs too, so hospitality labs are not given a
        # radiology / nursing / mass-comm lab when a kitchen is busy (they stay free for their owners).
        Room.objects.filter(name__in=["M-XRAY-LAB", "M-RT-LAB"], department__isnull=True).update(department="Radiologic Technology")
        Room.objects.filter(name__startswith="M-NARTS-", department__isnull=True).update(department="Nursing")
        Room.objects.filter(name="M-MC-LAB", department__isnull=True).update(department="College of Arts and Science")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {made} demo faculty created, {len(skipped)} skipped. "
            f"Buildings: CBA -> A, CIHM -> M. Kitchens marked as CIHM labs: {kitchens}."))
        if not kitchens:
            self.stdout.write(self.style.WARNING(
                "  (No kitchen rooms found yet -- run import_gti_rooms first, then this command again.)"))
