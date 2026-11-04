"""
Sets up the Senior High (SHS) and Junior High (JHS) modules for A.Y. 2026-2027.

    python manage.py seed_basic_ed

Safe to re-run (existing rows are kept). What it loads, and how far each part can be trusted:

  VERIFIED from DepEd documents (sources are stored on the curriculum records):
    * three-term calendar: Term 1 Jun 8-Sep 15 2026, Term 2 Sep 16-Dec 18 2026, Term 3 Jan 4-Apr 8 2027,
      with the holidays / examination dates published for the school year (DepEd Order 009 s.2026)
    * Strengthened SHS Grade 11: the 5 core subjects (160 h each, 4 h/week), Homeroom Guidance 1 h/week,
      Academic electives (80 h per semester) and TechPro electives (320 h)
    * MATATAG started in Grade 7 in SY 2024-2025 (DepEd FAQ)

  NOT verifiable from what DepEd publishes, so stored as UNVERIFIED and flagged in the validator:
    * the exact elective subject names (DepEd lists clusters only)  -> "<strand> Elective n" placeholders
    * the Grade 12 curriculum for SY 2026-2027 (DepEd has not issued it)
    * the Grade 8-10 MATATAG phase-in and the Grade 7-10 learning-area list
    * how the 3 terms map onto SHS semesters / JHS quarters (placeholder mapping; edit it in the dashboard)
    * rooms, sections and student counts are SAMPLE data -- replace them with the school's real ones
"""
import datetime as dt
from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed import models as m

D = dt.date
SRC_CAL = "DepEd Order No. 009, s. 2026 (three-term calendar); dates as reported at depedclub.com - confirm against the order"
URL_KF = "https://www.deped.gov.ph/wp-content/uploads/5_4_2026_SSHS-Key-Features.pdf"
URL_DM48 = "https://www.deped.gov.ph/wp-content/uploads/DM-48-s.-2025_-Pilot-Implementation-of-the-Strengthened-Senior-High-School-Curriculum-for-Grade-11-in-School-Year-2025-2026.pdf"
URL_FAQ = "https://deped.gov.ph/wp-content/uploads/FAQs-ON-THE-MATATAG-CURRICULUM.pdf"

STRANDS = [  # code, name, track, DepEd cluster of the Strengthened SHS
    ("STEM", "Science, Technology, Engineering, and Mathematics", "ACADEMIC", "Science, Technology, Engineering, and Mathematics (STEM)"),
    ("ABM", "Accountancy, Business, and Management", "ACADEMIC", "Business and Entrepreneurship"),
    ("AHSS", "Arts, Humanities, and Social Sciences", "ACADEMIC", "Arts, Social Sciences, and Humanities"),
    ("TVL", "Technical-Vocational-Livelihood", "TECHPRO", "Industrial Technologies"),
    ("ICT", "Information and Communications Technology", "TECHPRO", "ICT Support and Computer Programming Technologies"),
]
ELECTIVE_SPEC = {"STEM": "STEM|Science|Mathematics", "ABM": "Business|Accountancy|Entrepreneurship", "AHSS": "Humanities|Social Science|Arts",
                 "TVL": "TVL|Industrial Technologies", "ICT": "ICT|Computer Programming"}

CIVIC = ["Rizal", "Bonifacio", "Mabini", "Luna", "Aguinaldo", "Silang", "Del Pilar", "Jacinto"]


class Command(BaseCommand):
    help = "Seed SHS / JHS configuration, calendar, strands, sample rooms and sections, and the curriculum (A.Y. 2026-2027)."

    @transaction.atomic
    def handle(self, *args, **opts):
        ay, _ = m.AcademicYear.objects.get_or_create(label="2026-2027", defaults={"is_active": True})
        self.config()
        self.calendar(ay)
        strands = self.strands()
        self.rooms()
        self.sections(ay, strands)
        self.curriculum(ay, strands)
        self.stdout.write(self.style.SUCCESS("Done. Open the SHS / JHS dashboards and run 'Curriculum > Validate' before generating."))

    # ------------------------------------------------------------ configuration
    def config(self):
        m.SchoolLevelConfig.objects.get_or_create(level="SHS", defaults=dict(
            name="Senior High School", building="Alfredo Building", floor=None, period_minutes=50, break_minutes=0, break_every=2,
            max_teacher_hours=30, max_periods_per_teacher_day=6,
            notes="50-minute periods: DepEd's sample program uses 60 minutes, but 28+ weekly periods do not fit in the 5.5-hour Grade 11 window with 60-minute periods."))
        m.SchoolLevelConfig.objects.get_or_create(level="JHS", defaults=dict(
            name="Junior High School", building="Alta Building", floor=4, period_minutes=45, break_minutes=0, break_every=2,
            max_teacher_hours=30, max_periods_per_teacher_day=7,
            notes="45-minute periods, 8 per day in the 8:00-2:00 window. Recess and lunch are set per grade level in Settings (default recess 10:15, lunch 12:00-12:45, day ends 3:00 PM)."))
        win = [("SHS", 11, time(7, 0), time(12, 30), "Strengthened SHS Curriculum", False,
                "Confirm whether the school implements the Strengthened SHS curriculum for Grade 11 in SY 2026-2027 (DM 48 s.2025 covered pilot schools only)."),
               ("SHS", 12, time(12, 30), time(18, 30), "Transition: Grade 12 curriculum for SY 2026-2027 not yet published", False,
                "DepEd had not issued the Grade 12 structure for SY 2026-2027 in the documents found. The subject list is a placeholder to review."),
               ("JHS", 7, time(8, 0), time(14, 0), "MATATAG Curriculum", True, "MATATAG started in Grade 7 in SY 2024-2025 (DepEd FAQ)."),
               ("JHS", 8, time(8, 0), time(14, 0), "MATATAG Curriculum (phase-in year not confirmed)", False, "The DepEd FAQ phase-in table could not be read; confirm the year Grade 8 moved to MATATAG."),
               ("JHS", 9, time(8, 0), time(14, 0), "MATATAG Curriculum (phase-in year not confirmed)", False, "Confirm the year Grade 9 moves to MATATAG."),
               ("JHS", 10, time(8, 0), time(14, 0), "MATATAG Curriculum (phase-in year not confirmed)", False, "Confirm the year Grade 10 moves to MATATAG.")]
        for lv, g, a, b, fw, ver, note in win:
            win, made = m.GradeWindow.objects.get_or_create(level=lv, grade_level=g, defaults=dict(
                start_time=a, end_time=b, curriculum_framework=fw, framework_verified=ver, framework_note=note))
            if made:                                           # recess + lunch (see set_basic_ed_breaks)
                from basic_ed.management.commands.set_basic_ed_breaks import apply_defaults
                apply_defaults(win)
                win.save()

    # ------------------------------------------------------------ calendar
    def calendar(self, ay):
        terms = {1: (D(2026, 6, 8), D(2026, 9, 15)), 2: (D(2026, 9, 16), D(2026, 12, 18)), 3: (D(2027, 1, 4), D(2027, 4, 8))}
        for lv in ("SHS", "JHS"):
            tm = {}
            for n, (a, b) in terms.items():
                tm[n], _ = m.CalendarPeriod.objects.get_or_create(level=lv, academic_year=ay, kind="term", number=n, defaults=dict(
                    name=f"Term {n}", start_date=a, end_date=b, source=SRC_CAL))
            # Grade 11 and JHS work in the 3 terms directly; only SHS Grade 12 keeps 2 semesters (term 1+2, term 3).
            spec = {1: [1, 2], 2: [3]} if lv == "SHS" else {}
            kind, label = "semester", "Semester"
            for n, ts in spec.items():
                gp, made = m.CalendarPeriod.objects.get_or_create(level=lv, academic_year=ay, kind=kind, number=n, defaults=dict(
                    name=f"{label} {n}", is_placeholder=True,
                    source="PLACEHOLDER: DepEd's calendar order does not say how the 3 terms map onto semesters/quarters. Set the official mapping."))
                if made:
                    m.PeriodMapping.objects.bulk_create([m.PeriodMapping(grading_period=gp, term=tm[t]) for t in ts])
            ev = [("holiday", "Independence Day", D(2026, 6, 12), D(2026, 6, 12)), ("holiday", "Ninoy Aquino Day", D(2026, 8, 21), D(2026, 8, 21)),
                  ("holiday", "National Heroes Day", D(2026, 8, 31), D(2026, 8, 31)), ("other", "Term 1 opening block (no regular classes)", D(2026, 6, 8), D(2026, 6, 11)),
                  ("exam", "Term 1 Examination", D(2026, 8, 28), D(2026, 8, 28)), ("exam", "Term 1 Examination", D(2026, 9, 1), D(2026, 9, 1)),
                  ("break", "Learner wellness break", D(2026, 9, 10), D(2026, 9, 15)),
                  ("holiday", "All Saints' Day / All Souls' Day", D(2026, 11, 1), D(2026, 11, 2)), ("holiday", "Bonifacio Day", D(2026, 11, 30), D(2026, 11, 30)),
                  ("holiday", "Immaculate Conception", D(2026, 12, 8), D(2026, 12, 8)), ("exam", "Term 2 Examination", D(2026, 12, 3), D(2026, 12, 4)),
                  ("break", "Learner wellness break", D(2026, 12, 17), D(2026, 12, 18)), ("break", "Year-end break", D(2026, 12, 19), D(2026, 12, 31)),
                  ("holiday", "New Year's Day", D(2027, 1, 1), D(2027, 1, 1)), ("holiday", "Chinese New Year", D(2027, 2, 6), D(2027, 2, 6)),
                  ("exam", "Term 3 Examination (moving up / graduating)", D(2027, 3, 15), D(2027, 3, 16)),
                  ("exam", "Term 3 Examination (other grade levels)", D(2027, 3, 22), D(2027, 3, 23)),
                  ("holiday", "Maundy Thursday - Black Saturday", D(2027, 3, 25), D(2027, 3, 27)), ("holiday", "Day of Valor", D(2027, 4, 9), D(2027, 4, 9))]
            if lv == "JHS":
                ev.append(("exam", "NAT for Grade 10 (Grade 10 only)", D(2026, 10, 5), D(2026, 10, 9)))
            for kind_, name, a, b in ev:
                m.CalendarEvent.objects.get_or_create(level=lv, academic_year=ay, kind=kind_, name=name, start_date=a, defaults=dict(
                    end_date=b, blocks_classes=True, source=SRC_CAL))

    # ------------------------------------------------------------ strands, rooms, sections
    def strands(self):
        out = {}
        for code, name, track, cluster in STRANDS:
            out[code], _ = m.Strand.objects.get_or_create(code=code, defaults=dict(name=name, track=track, deped_cluster=cluster))
        return out

    def rooms(self):
        sample = "Sample room - replace with the school's actual rooms"
        for fl, nums in ((1, range(101, 105)), (2, range(201, 205)), (3, range(301, 305))):
            for n in nums:
                m.Room.objects.get_or_create(level="SHS", building="Alfredo Building", room_number=str(n), defaults=dict(floor=fl, capacity=45, notes=sample))
        for rn, fl, typ in (("SCI-LAB 1", 3, "science_lab"), ("COMP-LAB 1", 2, "computer_lab"), ("COMP-LAB 2", 2, "computer_lab"), ("TVL-WORKSHOP", 1, "workshop")):
            m.Room.objects.get_or_create(level="SHS", building="Alfredo Building", room_number=rn, defaults=dict(floor=fl, capacity=40, room_type=typ, notes=sample))
        for n in range(401, 411):
            m.Room.objects.get_or_create(level="JHS", building="Alta Building", room_number=str(n), defaults=dict(floor=4, capacity=45, notes=sample))

    def sections(self, ay, strands):
        for g in (11, 12):
            for code, st in strands.items():
                m.Section.objects.get_or_create(level="SHS", academic_year=ay, name=f"{g}-{code}-A", defaults=dict(grade_level=g, strand=st, student_count=35))
        names = iter(CIVIC)
        for g in (7, 8, 9, 10):
            for _ in range(2):
                m.Section.objects.get_or_create(level="JHS", academic_year=ay, name=f"{g}-{next(names)}", defaults=dict(grade_level=g, student_count=40))
        # home rooms (a classroom per section, so a class keeps its room)
        shs_rooms = list(m.Room.objects.filter(level="SHS", room_type="classroom").order_by("room_number"))
        for i, sec in enumerate(m.Section.objects.filter(level="SHS", home_room__isnull=True).order_by("grade_level", "name")):
            sec.home_room = shs_rooms[i % 5 if sec.grade_level == 11 else (5 + i % 5) % len(shs_rooms)]
            sec.save(update_fields=["home_room"])
        jhs_rooms = list(m.Room.objects.filter(level="JHS").order_by("room_number"))
        for i, sec in enumerate(m.Section.objects.filter(level="JHS", home_room__isnull=True).order_by("grade_level", "name")):
            sec.home_room = jhs_rooms[i % len(jhs_rooms)]
            sec.save(update_fields=["home_room"])

    # ------------------------------------------------------------ curriculum
    def curriculum(self, ay, strands):
        src_core = m.CurriculumSource.objects.get_or_create(level="SHS", academic_year=ay, title="Strengthened SHS Curriculum - Key Features (DepEd)", defaults=dict(
            reference="DepEd 'Strengthened SHS Curriculum: Key Features' (2026)", url=URL_KF, version="2026", is_verified=True,
            notes="Core subjects, hours, track clusters."))[0]
        src_dm = m.CurriculumSource.objects.get_or_create(level="SHS", academic_year=ay, title="DM 48 s.2025 - Pilot of the Strengthened SHS Curriculum (Grade 11)", defaults=dict(
            reference="DepEd Memorandum No. 48, s. 2025", url=URL_DM48, version="s.2025", is_verified=True,
            notes="Weekly hours, elective counts per semester, Homeroom Guidance 1 h/week. Effective Communication: the memo lists 80/80 h in Table 1 but 160 h in the Annex - 4 periods/week used."))[0]
        src_g12 = m.CurriculumSource.objects.get_or_create(level="SHS", academic_year=ay, title="Grade 12 placeholder (legacy SHS subject names)", defaults=dict(
            reference="DepEd SHS core list (80 h per semester); Grade 12 SY 2026-2027 issuance pending", url="https://www.teacherph.com/list-deped-senior-high-school-shs-core-curriculum-subjects/",
            version="", is_verified=False, notes="PLACEHOLDER. Replace with the Grade 12 curriculum once DepEd issues it."))[0]
        src_jhs = m.CurriculumSource.objects.get_or_create(level="JHS", academic_year=ay, title="MATATAG time allotment - Option B pattern", defaults=dict(
            reference="DepEd Order No. 010, s. 2024 (MATATAG) and its time-allotment guidelines", url=URL_FAQ, version="", is_verified=False,
            notes="Weekly pattern (English, Mathematics, Science, Values 5x; Filipino, AP, TLE, MAPEH 4x; Homeroom 1x) taken from the reported guidelines. "
                  "The learning-area list and Grade 7-10 details must be checked against DO 010 s.2024 Annex 3."))[0]

        def add(lv, src, strand, grade, gp, code, name, area, cat, spw, hours, spec, room="classroom", verified=False, note=""):
            m.CurriculumSubject.objects.get_or_create(
                level=lv, academic_year=ay, strand=strand, grade_level=grade, grading_period=gp, code=code, defaults=dict(
                    source=src, name=name, learning_area=area, category=cat, sessions_per_week=spw, total_hours=hours,
                    required_room_type=room, specialization=spec, is_verified=verified, verification_note=note))

        core = [("SHS11-EFFCOM", "Effective Communication / Mabisang Komunikasyon", "Languages", "English|Filipino", 160,
                 "Hours differ inside DM 48 (80/80 vs 160); 4 periods/week used."),
                ("SHS11-GENMATH", "General Mathematics", "Mathematics", "Mathematics", 160, ""),
                ("SHS11-GENSCI", "General Science", "Science", "Science", 160, ""),
                ("SHS11-LCS", "Life and Career Skills", "Values / HOPE / Personal Development", "Values Education|HOPE|Personal Development", 160, ""),
                ("SHS11-PKLP", "Pag-aaral ng Kasaysayan at Lipunang Pilipino", "Araling Panlipunan / Social Science", "Araling Panlipunan|Social Science", 160, "")]
        for code, name, area, spec, hrs, note in core:
            add("SHS", src_dm, None, 11, 0, code, name, area, "core", 4, hrs, spec, verified=True, note=note or "DepEd Strengthened SHS - 160 h, 4 periods/week")
        add("SHS", src_dm, None, 11, 0, "SHS11-HGP", "Homeroom Guidance Program", "Guidance", "guidance", 1, 40, "", verified=True, note="DM 48: 1 hour per week")
        for code, st in strands.items():
            if st.track == "ACADEMIC":
                for term in (1, 2, 3):          # Grade 11: 3 terms; the strand electives may change every term
                    for k in (1, 2):
                        add("SHS", src_core, st, 11, term, f"SHS11-{code}-E{term}{k}", f"{code} Elective {k} (Term {term})",
                            st.deped_cluster, "elective", 4, 40, ELECTIVE_SPEC[code],
                            note=f"Academic: 2 electives per term (cluster '{st.deped_cluster}'). Per-term hours are a placeholder; DepEd lists clusters only: replace with the elective the school offers.")
            else:
                add("SHS", src_core, st, 11, 0, f"SHS11-{code}-TP", f"{code} TechPro Elective (full year)", st.deped_cluster, "elective", 8, 320,
                    ELECTIVE_SPEC[code], room="computer_lab" if code == "ICT" else "workshop",
                    note=f"Structure verified (TechPro Grade 11: one elective, 320 h, full year, cluster '{st.deped_cluster}'). Replace with the actual TechPro elective.")
        # Grade 12 placeholders
        g12note = "PLACEHOLDER (Grade 12 SY 2026-2027 not issued): legacy subject name, 80 h per semester. Review before use."
        for sem, subs in ((1, [("UCSP", "Understanding Culture, Politics, and Society", "Social Science|Araling Panlipunan"),
                              ("21CLIT", "21st-Century Literature from the Philippines and the World", "English|Humanities|Filipino")]),
                          (2, [("CPAR", "Contemporary Philippine Arts from the Regions", "Humanities|Arts"),
                               ("PEH", "Physical Education and Health", "Physical Education|HOPE")])):
            for code, name, spec in subs:
                add("SHS", src_g12, None, 12, sem, f"SHS12-{code}", name, "Core (legacy)", "core", 2 if code == "PEH" else 4, 80, spec, note=g12note)
        add("SHS", src_g12, None, 12, 0, "SHS12-HGP", "Homeroom Guidance Program", "Guidance", "guidance", 1, 40, "", note=g12note)
        for code, st in strands.items():
            if st.track == "ACADEMIC":
                for sem in (1, 2):
                    for k in (1, 2):
                        add("SHS", src_g12, st, 12, sem, f"SHS12-{code}-E{sem}{k}", f"{code} Elective {k} (Semester {sem})", st.deped_cluster, "elective", 4, 80,
                            ELECTIVE_SPEC[code], note="PLACEHOLDER elective (80 h per semester, Academic Grade 12).")
            else:
                add("SHS", src_g12, st, 12, 1, f"SHS12-{code}-TP", f"{code} TechPro Elective (Semester 1)", st.deped_cluster, "elective", 8, 320,
                    ELECTIVE_SPEC[code], room="computer_lab" if code == "ICT" else "workshop",
                    note="PLACEHOLDER: TechPro Grade 12 elective is 320 h in one semester (DM 48). Work Immersion (off-campus) is not scheduled.")
        # JHS (whole year: the same learning areas in each of the 3 terms)
        jhs = [("English", 5, "English"), ("Filipino", 4, "Filipino"), ("Mathematics", 5, "Mathematics"), ("Science", 5, "Science"),
               ("Araling Panlipunan", 4, "Araling Panlipunan"), ("Values Education", 5, "Values Education"),
               ("Technology and Livelihood Education (TLE)", 4, "TLE"), ("MAPEH", 4, "MAPEH")]
        note = "Learning area and weekly pattern from reported DepEd MATATAG guidelines; confirm against DO 010 s.2024 Annex 3."
        for g in (7, 8, 9, 10):
            for name, spw, spec in jhs:
                add("JHS", src_jhs, None, g, 0, f"JHS{g}-{spec.upper().replace(' ', '')[:6]}", name, name, "learning_area", spw, None, spec, note=note)
            add("JHS", src_jhs, None, g, 0, f"JHS{g}-HGP", "Homeroom Guidance Program", "Guidance", "guidance", 1, None, "", note=note)
