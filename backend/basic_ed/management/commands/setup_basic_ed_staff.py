"""
Creates the SHS / JHS principal accounts and sample teacher accounts.

    python manage.py seed_basic_ed          # first (strands, sections, curriculum)
    python manage.py setup_basic_ed_staff

Principals   PrincipalSHS / SHSPRIN        PrincipalJHS / JHSPRIN     (forced password change on first login)
Teachers     login UPHM-<employee id>, first password = the employee id (SHS-T001..., JHS-T001...)

All names are FICTIONAL sample data, not real employees. Safe to re-run.
"""
from datetime import time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed import models as m

User = get_user_model()

# (first, last, department, [specializations], strand code or "", qualification)
SHS = [
    ("Maria Cristina", "Reyes", "English", ["English", "Humanities"], "", "LPT, MA English"),
    ("Jose Miguel", "Santos", "Mathematics", ["Mathematics", "STEM"], "STEM", "LPT, MS Mathematics"),
    ("Angelica Mae", "Dela Cruz", "Science", ["Science", "STEM"], "STEM", "LPT, MS Chemistry"),
    ("Mark Anthony", "Bautista", "Filipino", ["Filipino"], "", "LPT, MA Filipino"),
    ("Patricia Anne", "Mendoza", "Social Science", ["Social Science", "Araling Panlipunan", "Humanities"], "AHSS", "LPT, MA History"),
    ("John Carlo", "Villanueva", "ICT", ["ICT", "Computer Programming"], "ICT", "BSIT, NC III Programming"),
    ("Camille Grace", "Navarro", "Business", ["Business", "Accountancy", "Entrepreneurship"], "ABM", "CPA, LPT"),
    ("Daniel Rafael", "Garcia", "Values Education", ["Values Education", "HOPE", "Personal Development"], "", "LPT, MA Guidance"),
    ("Rosario Joy", "Ocampo", "Mathematics", ["Mathematics", "STEM", "Science"], "STEM", "LPT, MAEd Mathematics"),
    ("Paolo Emmanuel", "Cruz", "Science", ["Science", "STEM"], "STEM", "LPT, BS Biology"),
    ("Katrina Louise", "Aquino", "English", ["English", "Humanities", "Arts"], "AHSS", "LPT, MA Literature"),
    ("Ramon Isidro", "Pascual", "TVL", ["TVL", "Industrial Technologies"], "TVL", "NC II, TESDA trainer"),
    ("Jennifer Rose", "Manalo", "Physical Education", ["Physical Education", "HOPE", "Values Education"], "", "LPT, BPEd"),
    ("Gabriel Anton", "Lim", "Business", ["Business", "Entrepreneurship", "Accountancy"], "ABM", "BSBA, LPT"),
    ("Teresita Joy", "Villareal", "Social Science", ["Social Science", "Araling Panlipunan", "Humanities"], "AHSS", "LPT, MA Social Studies"),
]
JHS = [
    ("Liza Marie", "Fernandez", "English", ["English"]), ("Christian Paul", "Ramos", "English", ["English"]),
    ("Maribel Joy", "Aguilar", "Filipino", ["Filipino"]), ("Rommel Jose", "Castillo", "Filipino", ["Filipino"]),
    ("Jasmine Kate", "Flores", "Mathematics", ["Mathematics"]), ("Eduardo Miguel", "Torres", "Mathematics", ["Mathematics"]),
    ("Rowena Faith", "Domingo", "Science", ["Science"]), ("Allan Jay", "Soriano", "Science", ["Science"]),
    ("Cheryl Ann", "Mercado", "Araling Panlipunan", ["Araling Panlipunan"]), ("Vincent Carlo", "Salazar", "Araling Panlipunan", ["Araling Panlipunan"]),
    ("Gloria Mae", "Hernandez", "Values Education", ["Values Education"]), ("Nathaniel Ray", "Lopez", "Values Education", ["Values Education"]),
    ("Bernadette Ann", "Cortez", "TLE", ["TLE"]), ("Francis Xavier", "Rivera", "TLE", ["TLE"]),
    ("Joanna Marie", "Valdez", "MAPEH", ["MAPEH"]), ("Albert Lorenz", "Perez", "MAPEH", ["MAPEH"]),
]
PRINCIPALS = [("PrincipalSHS", "SHSPRIN", "SHS", "Sheryl B.", "Gamboa"), ("PrincipalJHS", "JHSPRIN", "JHS", "Sheryl B.", "Gamboa")]


class Command(BaseCommand):
    help = "Create the SHS/JHS principals and sample teachers (fictional names)."

    @transaction.atomic
    def handle(self, *a, **o):
        for username, code, level, first, last in PRINCIPALS:
            u, made = User.objects.get_or_create(username=username, defaults=dict(
                school_id=code, first_name=first, last_name=last, role="principal", school_level=level, must_change_password=True))
            if made:
                u.set_password(code)
                u.save()
                self.stdout.write(self.style.SUCCESS(f"Created {username} ({level} principal). Login: {username} / {code}"))
            else:
                self.stdout.write(f"{username} already exists -- skipped.")
        strands = {s.code: s for s in m.Strand.objects.all()}
        made = 0
        rows = [("SHS", i + 1, f, l, d, sp, st, q) for i, (f, l, d, sp, st, q) in enumerate(SHS)] + \
               [("JHS", i + 1, f, l, d, sp, "", "LPT") for i, (f, l, d, sp) in enumerate(JHS)]
        for level, n, first, last, dept, specs, st, qual in rows:
            eid = f"{level}-T{n:03d}"
            if User.objects.filter(school_id=eid).exists():
                continue
            u = User(school_id=eid, first_name=first, last_name=last, role="teacher", school_level=level, must_change_password=True)
            u.set_password(eid)
            u.save()
            m.Faculty.objects.create(user=u, level=level, employee_id=eid, department=dept, strand=strands.get(st),
                                     specializations="; ".join(specs), qualifications=qual, max_weekly_hours=30)
            made += 1
        # a sample availability restriction, so the engine visibly respects it (SHS-T004 not free Friday morning)
        f4 = m.Faculty.objects.filter(employee_id="SHS-T004").first()
        if f4 and not f4.availability.exists():
            m.Availability.objects.create(faculty=f4, day="Fri", start_time=time(7, 0), end_time=time(10, 0), available=False)
        # JHS advisers: one teacher per section, spread over the 16 teachers
        jhs_f = list(m.Faculty.objects.filter(level="JHS").order_by("employee_id"))
        for i, sec in enumerate(m.Section.objects.filter(level="JHS", adviser__isnull=True).order_by("grade_level", "name")):
            sec.adviser = jhs_f[(i * 2) % len(jhs_f)]
            sec.save(update_fields=["adviser"])
        self.stdout.write(self.style.SUCCESS(
            f"Done. {made} teachers created (SHS {m.Faculty.objects.filter(level='SHS').count()}, JHS {m.Faculty.objects.filter(level='JHS').count()})."))
