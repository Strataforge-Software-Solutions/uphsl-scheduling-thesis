"""
Tops up FULL-TIME and PART-TIME teachers in every department (NO dean accounts are created) with Filipino names.

    python manage.py add_department_staff            # add what is missing
    python manage.py add_department_staff --dry-run  # only show what would be added

Target headcount per department (full-time / part-time):  Nursing 14 / 12 (extra staff for the clinical/RLE load),
every other department 6 / 5.  Existing staff count toward the target, so re-running adds nothing new.
Login: UPHM-<ID> (F#### full-time, P#### part-time), first password = the ID; they must change it at first login.
IDs continue after the highest ID already in use.  A person with the same name in the same department is never duplicated.
"""
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField, Program
from faculty.models import FacultyProfile

User = get_user_model()

# CAS teaches every Gen Ed subject and proctors the Gen Ed exams (one proctor per section, all sections of a subject in the same hour),
# so it gets a larger pool whose teachers each cover three specializations.
TARGETS = {"Nursing": (14, 12), "College of Arts and Science": (24, 16)}
DEFAULT = (6, 5)
# Departments whose real faculty list is known and complete: this command never tops them up (Computer Studies = the Dean + the six
# faculty in setup_ccs_faculty.py; use trim_computer_studies_staff to remove accounts that were added before).
VERIFIED_DEPARTMENTS = {"Computer Studies"}
EXTRA_DEPARTMENTS = ["College of Arts and Science", "Radiologic Technology"]

SPECIALIZATIONS = {
    "Nursing": ["Nursing", "Fundamentals of Nursing", "Medical-Surgical Nursing", "Maternal and Child Nursing",
                "Community Health Nursing", "Psychiatric Nursing", "Nursing Research", "Pharmacology", "Anatomy", "Physiology"],
    "Computer Studies": ["Computer Science", "Information Technology", "Programming", "Database Systems", "Networking"],
    "Radiologic Technology": ["Radiologic Technology", "Radiographic Positioning", "Radiation Physics", "Anatomy"],
    "College of Arts and Science": ["English", "Filipino", "Mathematics", "Social Science", "FCL", "Communication", "Science",
                                    "Physical Education", "NSTP"],
    "Allied Health": ["Physical Therapy", "Occupational Therapy", "Medical Technology", "Anatomy"],
    "College of Business Administration": ["Business Administration", "Marketing", "Accounting", "Human Resource Management"],
    "College of International Hospitality Management": ["Hospitality Management", "Tourism", "Culinary Arts", "Food and Beverage"],
}
GENERIC = ["General Education"]

FIRST = ["Maria Cristina", "Jose Miguel", "Angelica", "Mark Anthony", "Katrina", "Ramon", "Leah", "Joselito", "Maricar",
         "Eduardo", "Rowena", "Gilbert", "Carmela", "Nestor", "Imelda", "Arnel", "Jocelyn", "Reynaldo", "Vilma", "Dennis",
         "Lorna", "Rodel", "Teresita", "Alvin", "Corazon", "Jerome", "Marites", "Rolando", "Evangeline", "Ferdinand",
         "Gloria", "Benedict", "Liza", "Arturo", "Noemi", "Christian", "Perla", "Efren", "Ligaya", "Bayani",
         "Rhea", "Danilo", "Cecilia", "Romeo", "Analyn", "Wilfredo", "Amparo", "Jun-Jun", "Mylene", "Ernesto",
         "Shiela", "Leonardo", "Divina", "Marlon", "Josephine", "Rodrigo", "Luzviminda", "Bernardo", "Aileen", "Manuel"]
LAST = ["Dela Cruz", "Santos", "Reyes", "Garcia", "Bautista", "Ocampo", "Aquino", "Mendoza", "Villanueva", "Pascual",
        "Castillo", "Torres", "Ramos", "Navarro", "Flores", "Gonzales", "Salazar", "Aguilar", "Domingo", "Manalo",
        "Cruz", "Tolentino", "Magsaysay", "De Guzman", "Lacson", "Soriano", "Panganiban", "Macaraeg", "Evangelista",
        "Del Rosario", "Hernandez", "Valdez", "Corpuz", "Padilla", "Sarmiento", "Dizon", "Estrada", "Alcantara",
        "Ilagan", "Buenaventura", "Cabrera", "Lumbao", "Mercado", "Pangilinan", "Quizon", "Roxas", "Sison", "Tiongson",
        "Umali", "Viray", "Yap", "Zamora", "Abad", "Bacani", "Catapang", "Dumlao", "Escobar", "Fajardo", "Gatdula", "Hizon"]


def _next_ids():
    nums = {"F": 1000, "P": 1000}
    for sid in User.objects.values_list("school_id", flat=True):
        m = re.fullmatch(r"([FP])(\d+)", sid or "")
        if m:
            nums[m.group(1)] = max(nums[m.group(1)], int(m.group(2)))
    return nums


class Command(BaseCommand):
    help = "Add full-time and part-time teachers (no deans) with Filipino names to every department."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        depts = sorted({p.department for p in Program.objects.all() if p.department} | set(EXTRA_DEPARTMENTS))
        nums = _next_ids()
        used = {(u.first_name.lower(), u.last_name.lower()) for u in User.objects.filter(role="faculty")}
        pool = [(f, l) for l in LAST for f in FIRST]
        # a stable, spread-out walk through all first/last combinations so no two people look alike
        pool = [pool[(i * 37) % len(pool)] for i in range(len(pool))]
        cursor = 0
        total = 0
        for dept in depts:
            if dept in VERIFIED_DEPARTMENTS:
                self.stdout.write(f"  {dept}: verified faculty list, not topped up")
                continue
            want_ft, want_pt = TARGETS.get(dept, DEFAULT)
            for ftype, want, prefix in (("full_time", want_ft, "F"), ("part_time", want_pt, "P")):
                have = User.objects.filter(role="faculty", faculty_type=ftype, department=dept).count()
                specs = SPECIALIZATIONS.get(dept, GENERIC)
                for k in range(max(0, want - have)):
                    while (pool[cursor % len(pool)][0].lower(), pool[cursor % len(pool)][1].lower()) in used:
                        cursor += 1
                    first, last = pool[cursor % len(pool)]
                    cursor += 1
                    used.add((first.lower(), last.lower()))
                    nums[prefix] += 1
                    sid = f"{prefix}{nums[prefix]}"
                    total += 1
                    if opts["dry_run"]:
                        self.stdout.write(f"  would add {sid}  {first} {last}  ({ftype}, {dept})")
                        continue
                    u = User(school_id=sid, first_name=first, last_name=last, role="faculty", faculty_type=ftype,
                             department=dept, must_change_password=True)
                    u.set_password(sid)
                    u.save()
                    prof, _ = FacultyProfile.objects.get_or_create(user=u)
                    chosen = [specs[(k + j) % len(specs)] for j in range(3 if dept == "College of Arts and Science" else 2)]
                    prof.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in chosen])
        verb = "Would add" if opts["dry_run"] else "Added"
        self.stdout.write(self.style.SUCCESS(f"{verb} {total} teacher account(s). No dean accounts were created."))
        for dept in depts:
            ft = User.objects.filter(role="faculty", faculty_type="full_time", department=dept).count()
            pt = User.objects.filter(role="faculty", faculty_type="part_time", department=dept).count()
            self.stdout.write(f"  {dept}: {ft} full-time, {pt} part-time")
