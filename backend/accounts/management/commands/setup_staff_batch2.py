"""
Creates the missing Dean logins and the faculty accounts for four colleges.

    python manage.py setup_staff_batch2

Deans (login / first password; forced to change it on first login)
    DeanCBA   / CBA      ONE dean for BOTH College of Business Administration and
                         College of International Hospitality Management (one dashboard, two departments)
    DeanAllied / ALLIED  Allied Health  (BS Physical Therapy)
  Computer Studies keeps its existing dean (UPHM-D1001 / D1001) -- no second dean is created.

Faculty (login UPHM-<ID>, first password = the ID; names are made-up demo names)
    Allied Health (PT)     6 full-time (F1032-F1037)  + 6 part-time (P1031-P1036)
    Allied Health (OT)     3 full-time (F1041-F1043)  + 1 part-time (P1038)
    Computer Studies (IT)  3 full-time (F1038-F1040)  + 1 part-time (P1037)
    Business Administration tops up to 6 full-time + 6 part-time (3 + 3 already existed)
    International Hospitality Mgmt tops up to 6 full-time + 6 part-time (4 + 3 already existed)

It first runs setup_cba_cihm (the CBA/CIHM deans, their original demo faculty, building preferences and
kitchen labs), so this ONE command is enough. Safe to re-run: an ID that already exists is skipped
(and reported if it belongs to someone else).
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField
from faculty.models import FacultyProfile

User = get_user_model()
CBA = "College of Business Administration"
CIHM = "College of International Hospitality Management"
AH = "Allied Health"
CCS = "Computer Studies"

# (school_id, name, faculty_type, department, [specializations])
FACULTY = [
    # ---- Allied Health: 6 + 6 ----
    ("F1032", "Dr. Marissa Villareal", "full_time", AH, ["Physical Therapy", "Therapeutic Exercises"]),
    ("F1033", "Jerome Dela Pena", "full_time", AH, ["Musculoskeletal Physical Therapy", "Kinesiology"]),
    ("F1034", "Katrina Bautista", "full_time", AH, ["Neurologic Physical Therapy", "Neurosciences"]),
    ("F1035", "Rodel Mercado", "full_time", AH, ["Anatomy", "Physiology"]),
    ("F1036", "Sheila Ramos", "full_time", AH, ["Pediatric Physical Therapy", "Geriatric Physical Therapy"]),
    ("F1037", "Anton Villamor", "full_time", AH, ["Electrotherapy", "Rehabilitation"]),
    ("P1031", "Dr. Leonora Castillo, MD", "part_time", AH, ["Pathophysiology", "Pharmacology"]),
    ("P1032", "Dr. Emmanuel Santiago, MD", "part_time", AH, ["Psychiatry", "Neurosciences"]),
    ("P1033", "Camille Ferrer", "part_time", AH, ["Cardiopulmonary Physical Therapy", "Wellness and Health Promotion"]),
    ("P1034", "Noel Abad", "part_time", AH, ["Orthotics and Prosthetics", "Assistive Technologies"]),
    ("P1035", "Bianca Salazar", "part_time", AH, ["Research Methods", "Evidence Based Practice"]),
    ("P1036", "Arvin Lacsamana", "part_time", AH, ["Integumentary Physical Therapy", "Industrial Rehabilitation"]),
    # ---- Allied Health / BS Occupational Therapy: 3 FT + 1 PT ----
    ("F1041", "Dr. Patricia Mangubat", "full_time", AH, ["Occupational Therapy", "Mental Health OT"]),
    ("F1042", "Joaquin Delos Reyes", "full_time", AH, ["Occupational Therapy", "Neurological Rehabilitation"]),
    ("F1043", "Elaine Cordero", "full_time", AH, ["Occupational Therapy", "Pediatric Rehabilitation"]),
    ("P1038", "Rhea Montenegro", "part_time", AH, ["Occupational Therapy", "Fieldwork Supervision"]),
    # ---- Computer Studies / BS Information Technology: 3 FT + 1 PT ----
    ("F1038", "Nathaniel Rosales", "full_time", CCS, ["BS Information Technology", "Networking"]),
    ("F1039", "Cherry Anne Dimaculangan", "full_time", CCS, ["BS Information Technology", "Web Development"]),
    ("F1040", "Francis Lopez", "full_time", CCS, ["BS Information Technology", "Information Assurance and Security"]),
    ("P1037", "Engr. Dennis Macaraeg", "part_time", CCS, ["BS Information Technology", "Systems Administration"]),
    # ---- Business Administration: +3 FT, +3 PT (to 6 + 6) ----
    ("F1027", "Teresita Quiambao", "full_time", CBA, ["Marketing", "Entrepreneurship"]),
    ("F1028", "Harold Bernardo", "full_time", CBA, ["Human Resource Management", "Organizational Behavior"]),
    ("F1029", "Pamela Hizon", "full_time", CBA, ["Business Management", "Strategic Management"]),
    ("P1025", "Joseph Almazan", "part_time", CBA, ["Business Law", "Taxation"]),
    ("P1026", "Marites Corpuz", "part_time", CBA, ["Accounting", "Economics"]),
    ("P1027", "Gilbert Tanael", "part_time", CBA, ["Statistics", "Operations Management"]),
    # ---- Intl. Hospitality Mgmt: +2 FT, +3 PT (to 6 + 6) ----
    ("F1030", "Chef Rowena Dalisay", "full_time", CIHM, ["Culinary Arts", "Baking and Pastry"]),
    ("F1031", "Lucas Vergara", "full_time", CIHM, ["Hospitality Management", "Lodging Operations"]),
    ("P1028", "Chef Alfredo Mendoza", "part_time", CIHM, ["Culinary Arts", "Food and Beverage"]),
    ("P1029", "Daisy Fajardo", "part_time", CIHM, ["Tourism Management", "Foreign Language"]),
    ("P1030", "Carlo Evangelista", "part_time", CIHM, ["Events Management", "Front Office"]),
]

# Allied Health dean (only used if no Allied Health dean exists yet)
ALLIED_DEAN = ("DeanAllied", "ALLIED", "Bernadette", "Fernan", AH)


class Command(BaseCommand):
    help = "Create the CBA+CIHM (one shared dean) and Allied Health deans and the faculty accounts for CBA, CIHM, Allied Health and IT."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("setup_cba_cihm", stdout=self.stdout)

        username, code, first, last, dept = ALLIED_DEAN
        if User.objects.filter(username=username).exists() or \
           User.objects.filter(role="faculty", faculty_type="dean", department=dept).exists():
            self.stdout.write("Allied Health dean already exists -- skipped.")
        else:
            u = User(username=username, school_id=code, first_name=first, last_name=last, role="faculty",
                     faculty_type="dean", department=dept, must_change_password=True)
            u.set_password(code)
            u.save()
            FacultyProfile.objects.get_or_create(user=u)
            self.stdout.write(self.style.SUCCESS(f"Created {username} ({dept}). Login: {username} / {code}"))

        made, skipped = 0, []
        for school_id, full_name, ftype, dept, specs in FACULTY:
            have = User.objects.filter(school_id=school_id).first()
            if have:
                skipped.append((school_id, full_name, have.get_full_name(), have.department))
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
                continue                      # already created on an earlier run
            self.stdout.write(self.style.WARNING(f"  skipped {sid}: wanted '{wanted}' but it already belongs to '{have}' ({dept})."))

        self.stdout.write(self.style.SUCCESS(f"\nDone. {made} faculty created, {len(skipped)} skipped."))
        for d in (AH, CCS, CBA, CIHM):
            ft = User.objects.filter(role="faculty", faculty_type="full_time", department=d).count()
            pt = User.objects.filter(role="faculty", faculty_type="part_time", department=d).count()
            self.stdout.write(f"  {d}: {ft} full-time, {pt} part-time")
