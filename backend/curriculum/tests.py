"""BS Respiratory Therapy curriculum import (seed_resptherapy_curriculum): right department, the file's subjects per term, idempotent,
no duplicate Gen Ed rows, Radiologic Technology untouched, Dean visibility / ownership."""
from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from accounts.models import User
from curriculum.models import AcademicField, Program, Subject

AH = "College of Allied Health"
# subjects imported per (year, semester), counted from the screenshots (internships RT4128 / RT4231 not imported)
EXPECTED = {("1st Year", "1st Sem"): 9, ("1st Year", "2nd Sem"): 10, ("2nd Year", "1st Sem"): 9, ("2nd Year", "2nd Sem"): 11,
            ("3rd Year", "1st Sem"): 11, ("3rd Year", "2nd Sem"): 12, ("4th Year", "1st Sem"): 3, ("4th Year", "2nd Sem"): 3}


def run(*args):
    out = StringIO()
    call_command("seed_resptherapy_curriculum", *args, stdout=out)
    return out.getvalue()


def dean(username, dept):
    u = User(username=username, school_id=username, first_name="D", last_name=username, role="faculty", faculty_type="dean",
             department=dept)
    u.set_password("pw"); u.save()
    return u


class RespiratoryTherapyCurriculumTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pt = Program.objects.create(name="BS Physical Therapy", department=AH)
        Subject.objects.create(code="GE401", title="Filipino Christian Living 1", program=cls.pt, lec_units=2, year_level="1st Year",
                               semester="1st Sem", classification="minor")
        cls.rad = Program.objects.create(name="BS Radiologic Technology", department="College of Radiologic Technology")
        for code, title in (("RAD1101", "Introduction to Radiologic Technology and Health Care"), ("RAD1202", "Medical Terminology")):
            Subject.objects.create(code=code, title=title, program=cls.rad, lec_units=3, year_level="1st Year", semester="1st Sem",
                                   classification="major")
        cls.ah_dean = dean("DAH", AH)
        cls.cs_dean = dean("DCS", "College of Computer Studies")

    def rt(self):
        return Program.objects.get(name="BS Respiratory Therapy")

    def rad_snapshot(self):
        return (list(Program.objects.filter(pk=self.rad.pk).values()),
                list(Subject.objects.filter(program=self.rad).order_by("code").values()))

    def test_dry_run_writes_nothing(self):
        before = (Program.objects.count(), Subject.objects.count(), AcademicField.objects.count())
        out = run()
        self.assertIn("DRY RUN", out); self.assertIn("68 to add", out); self.assertIn(f"Department: {AH}", out)
        self.assertEqual((Program.objects.count(), Subject.objects.count(), AcademicField.objects.count()), before)

    def test_program_is_under_allied_health_with_the_files_subjects_per_term(self):
        run("--apply")
        rt = self.rt()
        self.assertEqual(rt.department, AH)                                   # the spelling the Allied Health programs already use
        got = {}
        for y, s in Subject.objects.filter(program=rt).values_list("year_level", "semester"):
            got[(y, s)] = got.get((y, s), 0) + 1
        self.assertEqual(got, EXPECTED)
        subs = {x.code: x for x in Subject.objects.filter(program=rt)}
        self.assertNotIn("RT3118L", subs); self.assertNotIn("RT4128", subs); self.assertNotIn("RT4231", subs)
        self.assertEqual((subs["RT3117L"].lec_units, subs["RT3117L"].lab_units), (0, 1))      # the approved RT3118L correction: a lab
        self.assertEqual((subs["RT2110L"].lec_units, subs["RT2110L"].lab_units), (0, 2))
        self.assertEqual((subs["RT2110"].lec_units, subs["RT2110"].lab_units), (3, 0))
        self.assertEqual(subs["ELEC1AL"].lab_units, 1)
        self.assertEqual({c for c, x in subs.items() if x.classification == "minor"},
                         {"EPP1", "EPP2", "GE401", "GE402", "GE403", "GE404", "GE405", "GE406", "GE407", "GE408", "GE501", "GE502",
                          "GE602", "GE701", "GEC101", "GEC102", "GEC103", "GEC104", "GEC105", "GEC106", "GEC107", "GEC108", "GEC109",
                          "PATHFIT1", "PATHFIT2", "PATHFIT3", "PATHFIT4", "ELEC1A", "ELEC1AL"})
        tagged = {c for c, x in subs.items() if x.field_id}
        self.assertEqual(tagged, {c for c, x in subs.items() if c.startswith("RT")})          # RT majors only; OTPTRT1102 and Gen Ed not
        self.assertEqual({x.field.name for x in subs.values() if x.field_id}, {"Respiratory Therapy"})
        from engine.models import Section
        self.assertFalse(Section.objects.filter(program=rt).exists())                          # no sections created

    def test_running_twice_creates_no_duplicates_and_keeps_a_deans_field(self):
        run("--apply")
        other = AcademicField.objects.create(name="Cardiopulmonary Care")
        Subject.objects.filter(program=self.rt(), code="RT2108").update(field=other)            # a Dean re-tagged one subject
        n = Subject.objects.count()
        out = run("--apply")
        self.assertIn("0 subjects added, 0 updated, 68 unchanged", out)
        self.assertEqual(Subject.objects.count(), n)
        self.assertEqual(Program.objects.filter(name="BS Respiratory Therapy").count(), 1)
        self.assertEqual(Subject.objects.get(program=self.rt(), code="RT2108").field, other)

    def test_no_duplicate_gen_ed_rows(self):
        run("--apply"); run("--apply")
        rt = self.rt()
        for code in ("GE401", "GEC105", "PATHFIT1", "ELEC1A"):
            self.assertEqual(Subject.objects.filter(program=rt, code=code).count(), 1)
        self.assertEqual(Subject.objects.filter(code="GE401").count(), 2)                          # Physical Therapy's own + RT's own
        self.assertEqual(Subject.objects.get(program=self.pt, code="GE401").title, "Filipino Christian Living 1")

    def test_radiologic_technology_is_unchanged(self):
        before = self.rad_snapshot()
        run("--apply")
        self.assertEqual(self.rad_snapshot(), before)
        self.assertEqual(Subject.objects.filter(program=self.rt(), code__startswith="RAD").count(), 0)

    def test_allied_health_dean_sees_it_and_another_colleges_dean_cannot_edit_it(self):
        run("--apply")
        rt = self.rt()
        self.client.force_authenticate(self.ah_dean)
        progs = self.client.get("/api/curriculum/programs/").data
        self.assertIn(rt.id, [p["id"] for p in progs if p["department"] == AH])
        subs = self.client.get("/api/curriculum/subjects/").data
        self.assertEqual(sum(1 for x in subs if x["program"] == rt.id), 68)
        sid = Subject.objects.get(program=rt, code="RT1101").id
        r = self.client.patch(f"/api/curriculum/subjects/{sid}/", {"title": "Introduction to Respiratory Therapy"}, format="json")
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        self.client.force_authenticate(self.cs_dean)
        self.assertFalse(any(x["program"] == rt.id for x in self.client.get("/api/curriculum/subjects/").data))
        r = self.client.patch(f"/api/curriculum/subjects/{sid}/", {"title": "Changed"}, format="json")
        self.assertIn(r.status_code, (403, 404))
        self.assertEqual(Subject.objects.get(pk=sid).title, "Introduction to Respiratory Therapy")

    def test_fresh_database_uses_the_seed_spelling(self):
        Program.objects.filter(name="BS Physical Therapy").update(name="Old PT")                 # no Allied Health program to copy
        self.assertIn("Department: Allied Health", run())


class RespiratoryTherapySectionTests(APITestCase):
    """--sections: one section per year level and semester (B.c1 ... B.c4), only the missing ones, never duplicated."""

    def setUp(self):
        Program.objects.create(name="BS Physical Therapy", department=AH)
        run("--apply")
        self.rt = Program.objects.get(name="BS Respiratory Therapy")

    def sections(self):
        from engine.models import Section
        return {(s.year_level, s.semester): (s.name, s.student_count) for s in Section.objects.filter(program=self.rt)}

    def test_dry_run_then_apply_adds_eight_sections_once(self):
        out = run("--sections")
        self.assertIn("8 to add", out); self.assertIn("DRY RUN", out)
        self.assertEqual(self.sections(), {})
        run("--sections", "--apply")
        got = self.sections()
        self.assertEqual(set(got), set(EXPECTED))                                          # every year level and semester of the file
        self.assertEqual({k: v[0] for k, v in got.items()},
                         {k: f"B.c{k[0][0]}" for k in EXPECTED})                           # 1st Year -> B.c1 ... 4th Year -> B.c4
        self.assertEqual(got[("1st Year", "1st Sem")][1], 30); self.assertEqual(got[("4th Year", "2nd Sem")][1], 20)
        self.assertIn("0 sections added", run("--sections", "--apply"))
        self.assertEqual(len(self.sections()), 8)

    def test_existing_sections_and_their_sizes_are_kept(self):
        from engine.models import Section
        Section.objects.create(program=self.rt, name="B.c1", year_level="1st Year", semester="1st Sem", student_count=33)
        out = run("--sections", "--apply", "--students", "40,35,30,25")
        self.assertIn("7 sections added", out)
        got = self.sections()
        self.assertEqual(got[("1st Year", "1st Sem")], ("B.c1", 33))                     # the Dean's number is not overwritten
        self.assertEqual(got[("2nd Year", "1st Sem")], ("B.c2", 35))

    def test_bad_student_numbers_are_refused(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            run("--sections", "--apply", "--students", "30,28")
        self.assertEqual(self.sections(), {})


class RespiratoryTherapyFacultyTests(APITestCase):
    """add_resptherapy_faculty: 4 full-time + 2 part-time in the RT program's college, qualified for RT majors, never duplicated."""

    def setUp(self):
        Program.objects.create(name="BS Physical Therapy", department=AH)
        run("--apply")

    def fac(self, *args):
        out = StringIO()
        call_command("add_resptherapy_faculty", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_then_apply_creates_six_once(self):
        users = User.objects.count()
        self.assertIn("6 to add", self.fac()); self.assertEqual(User.objects.count(), users)
        self.assertIn("6 faculty created", self.fac("--apply"))
        made = User.objects.filter(school_id__in=["F1081", "F1082", "F1083", "F1084", "P1060", "P1061"])
        self.assertEqual(made.count(), 6)
        self.assertEqual(sorted(made.values_list("faculty_type", flat=True)), ["full_time"] * 4 + ["part_time"] * 2)
        self.assertEqual(set(made.values_list("department", flat=True)), {AH})
        self.assertFalse(made.filter(faculty_type="dean").exists())
        u = made.get(school_id="F1081")
        self.assertEqual(u.username, "UPHM-F1081"); self.assertTrue(u.must_change_password); self.assertTrue(u.check_password("F1081"))
        self.assertIn("0 faculty created", self.fac("--apply"))
        self.assertEqual(User.objects.count(), users + 6)

    def test_they_qualify_for_respiratory_therapy_majors(self):
        from engine.models import Section
        from engine.qualification import is_qualified
        from faculty.models import FacultyProfile
        self.fac("--apply")
        rt = Program.objects.get(name="BS Respiratory Therapy")
        sec = Section(name="B.c1", program=rt, year_level="1st Year", semester="1st Sem", student_count=30)
        p = FacultyProfile.objects.prefetch_related("specializations").select_related("user").get(user__school_id="P1061")
        for code in ("RT1101", "RT3222", "RT3222L"):
            s = Subject.objects.get(program=rt, code=code)
            self.assertTrue(is_qualified(p, s, sec, {f.id for f in p.specializations.all()}), code)

    def test_an_id_used_by_someone_else_is_left_alone(self):
        other = User.objects.create(username="UPHM-F1082", school_id="F1082", first_name="Someone", last_name="Else", role="faculty",
                                    faculty_type="full_time", department="College of Nursing")
        out = self.fac("--apply")
        self.assertIn("skip  F1082", out); self.assertIn("5 faculty created", out)
        other.refresh_from_db()
        self.assertEqual((other.first_name, other.department), ("Someone", "College of Nursing"))
