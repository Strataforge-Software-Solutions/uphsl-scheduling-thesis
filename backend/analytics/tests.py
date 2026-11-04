"""Tests for the new read-only insight cards: exact numbers on a known dataset, role-restricted access, and NO database writes.

    python manage.py test analytics"""
from datetime import time as dtime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase
from basic_ed import models as bm
from collections import Counter

from accounts.models import User
from curriculum.models import AcademicField, Program, Subject
from engine.models import ConflictLog, Log, Schedule, Section, TimeSlot
from faculty.models import FacultyProfile
from rooms.models import Room

CCS = "Computer Studies"


def user(username, role, **kw):
    u = User(username=username, school_id=username, first_name=username.title(), last_name="T", role=role, **kw)
    u.set_password("pw")
    u.save()
    return u


class ReadOnlyMixin:
    def get_readonly(self, url, who, params=None):
        """GET as `who` and fail if ANY insert / update / delete statement ran."""
        self.client.force_authenticate(who)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url, params or {})
        writes = [q["sql"] for q in ctx.captured_queries
                  if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"))]
        self.assertEqual(writes, [], f"{url} wrote to the database")
        return r


class InsightBase(APITestCase, ReadOnlyMixin):
    @classmethod
    def setUpTestData(cls):
        cls.admin = user("itadmin", "admin")
        cls.registrar = user("reg", "registrar")
        cls.dean = user("deancs", "faculty", faculty_type="dean", department=CCS)
        cls.dean_nurse = user("deannu", "faculty", faculty_type="dean", department="Nursing")
        cls.shs = user("prinshs", "principal", school_level="SHS")
        cls.jhs = user("prinjhs", "principal", school_level="JHS")
        cls.field = AcademicField.objects.create(name="Computer Science")
        cls.t1 = FacultyProfile.objects.create(user=user("teach1", "faculty", faculty_type="full_time", department=CCS), degree="BS Computer Science")
        cls.t1.specializations.add(cls.field)
        cls.t2 = FacultyProfile.objects.create(user=user("teach2", "faculty", faculty_type="full_time", department=CCS))   # no specialization
        Room.objects.filter(name__startswith="Comp Lab").delete()        # rooms a migration may have added: this test builds its own
        cls.lab = Room.objects.create(name="Comp Lab C", capacity=40, room_type="lab", department=CCS)
        cls.lec = Room.objects.create(name="M-101", capacity=45, room_type="lecture")                                   # no department
        cls.prog = Program.objects.create(name="BS Computer Science", department=CCS)
        cls.secA = Section.objects.create(name="A1", program=cls.prog, year_level="1st Year", semester="1st Sem", student_count=30)
        cls.secB = Section.objects.create(name="B1", program=cls.prog, year_level="1st Year", semester="1st Sem", student_count=30)
        cls.secX = Section.objects.create(name="X1", program=cls.prog, year_level="2nd Year", semester="1st Sem", student_count=30)  # no curriculum
        cls.s1 = Subject.objects.create(code="CS101", title="Programming", program=cls.prog, lec_units=3, lab_units=0,
                                        year_level="1st Year", semester="1st Sem", classification="major", field=cls.field)
        cls.s2 = Subject.objects.create(code="CS102", title="Discrete", program=cls.prog, lec_units=3, lab_units=0,
                                        year_level="1st Year", semester="1st Sem", classification="major", field=cls.field)
        for d in ("Mon", "Tue"):
            for h in range(7, 12):
                TimeSlot.objects.get_or_create(day=d, start_time=dtime(h), end_time=dtime(h + 1))

    def put(self, sec, sub, day, hours, teacher=None, room=None, status="draft"):
        for h in hours:
            Schedule.objects.create(subject=sub, section=sec, teacher=teacher or self.t1, room=room or self.lec,
                                    timeslot=TimeSlot.objects.get(day=day, start_time=dtime(h)), status=status, term=sec.semester)


class AdminInsightTests(InsightBase):
    def test_health_numbers_on_a_known_dataset(self):
        self.put(self.secA, self.s1, "Mon", [7, 8, 9])            # complete (3 h)
        self.put(self.secA, self.s2, "Tue", [7])                   # 1 of 3 h -> unplaced
        # section B: nothing generated for it -> counted as "not generated yet", not as unplaced
        ConflictLog.objects.create(conflict_type="unresolved_csp", description="Could not place CS102", section=self.secA)
        r = self.get_readonly("/api/analytics/admin/health/", self.admin)
        self.assertEqual(r.status_code, 200, r.data)
        d = r.data
        self.assertEqual(d["unplaced_classes"], 1)
        self.assertEqual((d["unplaced"][0]["subject"][:5], d["unplaced"][0]["placed_hours"], d["unplaced"][0]["needed_hours"]), ("CS102", 1.0, 3.0))
        self.assertEqual(d["not_generated_classes"], 2)            # CS101 + CS102 of section B
        self.assertEqual(d["open_conflicts"], 0)
        self.assertEqual(d["unresolved_unplaced_log_entries"], 1)
        self.assertEqual([x["name"] for x in d["rooms_no_department_list"]], ["M-101"])
        self.assertEqual([x["name"] for x in d["faculty_no_specialization_list"]], ["Teach2 T"])
        self.assertEqual([x["section"] for x in d["sections_no_curriculum_list"]], ["BS Computer Science X1"])

    def test_open_conflicts_are_counted_not_hidden(self):
        self.put(self.secA, self.s1, "Mon", [7])
        half, _ = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))
        Schedule.objects.create(subject=self.s2, section=self.secB, teacher=self.t1, room=self.lab, timeslot=half, term="1st Sem")  # same teacher, overlapping
        d = self.get_readonly("/api/analytics/admin/health/", self.admin).data
        self.assertEqual(d["open_conflicts"], 1)
        self.assertEqual(d["conflict_counts"], {"teacher": 1})

    def test_account_hygiene(self):
        User.objects.filter(username="teach2").update(is_active=False)
        User.objects.filter(username__in=["reg", "deancs"]).update(email="Same@uphsl.edu.ph")
        User.objects.filter(username="deannu").update(email="same@UPHSL.edu.ph")
        from django.utils import timezone
        User.objects.filter(username="itadmin").update(last_login=timezone.now())
        d = self.get_readonly("/api/analytics/admin/accounts/", self.admin).data
        self.assertEqual(d["inactive"], 1); self.assertEqual(d["inactive_list"][0]["username"], "teach2")
        self.assertEqual(d["duplicate_emails"], 1)
        self.assertEqual(sorted(a["username"] for a in d["duplicate_email_list"][0]["accounts"]), ["deancs", "deannu", "reg"])
        # every ACTIVE account except the admin who signed in has never signed in
        self.assertEqual(d["never_signed_in"], User.objects.filter(is_active=True, last_login__isnull=True).count())
        self.assertNotIn("itadmin", [a["username"] for a in d["never_signed_in_list"]])

    def test_audit_trail_categories_and_gaps(self):
        self.put(self.secA, self.s1, "Mon", [7, 8, 9])
        sid = Schedule.objects.first().id
        Log.objects.create(action="UPDATE", schedule_id=sid, user=self.dean, details="Approved: CS101 (BS Computer Science A1) Mon 7:00 AM")
        Log.objects.create(action="UPDATE", schedule_id=sid, user=self.dean, details="Published: CS101 (BS Computer Science A1) Mon 7:00 AM")
        Log.objects.create(action="DELETE", schedule_id=sid, user=self.dean, details="Removed CS101 (BS Computer Science A1) Mon 7:00 AM")
        Log.objects.create(action="DELETE", schedule_id=0, user=self.dean, details='UNDO-SNAPSHOT {"rows": []}')   # not an event
        d = self.get_readonly("/api/analytics/admin/audit/", self.admin).data
        cats = Counter(e["category"] for e in d["events"])
        self.assertEqual((cats["approved"], cats["published"], cats["removed"], cats["generated"]), (1, 1, 1, 1))
        self.assertFalse(any("UNDO-SNAPSHOT" in e["details"] for e in d["events"]))
        gen = next(e for e in d["events"] if e["category"] == "generated")
        self.assertEqual(gen["who"], "not recorded")
        self.assertTrue(any("Generate" in n for n in d["not_recorded"]))
        only = self.get_readonly("/api/analytics/admin/audit/", self.admin, {"category": "approved"}).data
        self.assertEqual([e["category"] for e in only["events"]], ["approved"])

    def test_only_it_admin_may_see_admin_cards(self):
        for url in ("/api/analytics/admin/health/", "/api/analytics/admin/accounts/", "/api/analytics/admin/audit/"):
            for who in (self.registrar, self.dean, self.shs, self.t1.user):
                self.assertEqual(self.get_readonly(url, who).status_code, 403, (url, who.username))
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_empty_database_does_not_crash(self):
        Schedule.objects.all().delete(); Section.objects.all().delete(); Room.objects.all().delete()
        for url in ("/api/analytics/admin/health/", "/api/analytics/admin/accounts/", "/api/analytics/admin/audit/"):
            self.assertEqual(self.get_readonly(url, self.admin).status_code, 200, url)


class DeanInsightTests(InsightBase):
    """Stage 2: readiness, faculty fit, lab capacity, load bands -- own college only, read-only."""
    URLS = ("/api/analytics/dean/readiness/", "/api/analytics/dean/faculty-fit/", "/api/analytics/dean/lab-capacity/",
            "/api/analytics/dean/load-bands/")

    def _dataset(self):
        self.put(self.secA, self.s1, "Mon", [7, 8, 9], status="published")      # CS101 A1: published
        self.put(self.secB, self.s1, "Tue", [7, 8, 9], status="approved")       # CS101 B1: approved
        self.put(self.secA, self.s2, "Mon", [10])                                 # CS102 A1: draft, 3 h over two days
        self.put(self.secA, self.s2, "Tue", [10, 11])
        # CS102 B1: nothing -> unplaced

    def test_readiness_counts(self):
        self._dataset()
        d = self.get_readonly("/api/analytics/dean/readiness/", self.dean).data
        row = next(r for r in d["rows"] if r["year_level"] == "1st Year")
        self.assertEqual({k: row[k] for k in ("sections", "classes", "published", "approved", "draft", "unplaced", "placed", "placed_pct", "published_pct")},
                         {"sections": 2, "classes": 4, "published": 1, "approved": 1, "draft": 1, "unplaced": 1, "placed": 3, "placed_pct": 75, "published_pct": 25})
        x = next(r for r in d["rows"] if r["year_level"] == "2nd Year")
        self.assertEqual((x["classes"], x["placed_pct"]), (0, 0))                 # no curriculum: no division by zero
        # a class is only as far as its least advanced period
        one = Schedule.objects.filter(section=self.secA, subject=self.s1).first()
        Schedule.objects.filter(pk=one.pk).update(status="draft")
        row = next(r for r in self.get_readonly("/api/analytics/dean/readiness/", self.dean).data["rows"] if r["year_level"] == "1st Year")
        self.assertEqual((row["published"], row["draft"]), (0, 2))

    def test_faculty_fit(self):
        from curriculum.models import AcademicField
        net = AcademicField.objects.create(name="Networking")
        s3 = Subject.objects.create(code="CS103", title="Networks", program=self.prog, lec_units=1, lab_units=0, year_level="1st Year",
                                    semester="1st Sem", classification="major", field=net)
        self.put(self.secA, self.s1, "Mon", [7], teacher=self.t2)                # teach2: no specialization, no degree
        self.put(self.secA, s3, "Mon", [8])                                       # teach1: BS Computer Science, Networking not recorded
        nprog = Program.objects.create(name="BS Nursing", department="Nursing")
        Subject.objects.create(code="NCM101", title="Care", program=nprog, lec_units=3, lab_units=0, year_level="1st Year",
                               semester="1st Sem", classification="major", field=AcademicField.objects.create(name="Nursing"))
        d = self.get_readonly("/api/analytics/dean/faculty-fit/", self.dean).data
        self.assertEqual([(x["teacher"], x["code"]) for x in d["teaching_outside_specialization"]], [("Teach2 T", "CS101")])
        self.assertEqual([(x["teacher"], x["code"]) for x in d["qualified_by_degree_only"]], [("Teach1 T", "CS103")])
        self.assertEqual(d["subjects_without_qualified_faculty"], [])            # the Nursing subject is not this Dean's
        n = self.get_readonly("/api/analytics/dean/faculty-fit/", self.dean_nurse).data
        self.assertEqual([x["code"] for x in n["subjects_without_qualified_faculty"]], ["NCM101"])
        self.assertEqual(n["teaching_outside_specialization"], [])

    def test_lab_capacity(self):
        self.put(self.secA, self.s1, "Mon", [7, 8], room=self.lab)
        d = self.get_readonly("/api/analytics/dean/lab-capacity/", self.dean).data
        self.assertEqual([l["room"] for l in d["labs"]], ["Comp Lab C"])
        mon = next(x for x in d["labs"][0]["days"] if x["day"] == "Mon")
        self.assertEqual((mon["used_hours"], mon["free_hours"], mon["available_hours"], mon["used_pct"]), (2.0, 3.0, 5.0, 40))
        self.assertEqual((d["labs"][0]["used_hours"], d["labs"][0]["free_hours"]), (2.0, 8.0))
        n = self.get_readonly("/api/analytics/dean/lab-capacity/", self.dean_nurse).data
        self.assertEqual(n["labs"], []); self.assertIn("no designated", n["note"])

    def test_load_bands_never_create_the_settings_row(self):
        from engine.models import SchedulingConfig
        SchedulingConfig.objects.all().delete()                                     # missing row: must NOT be created by a read
        t3 = FacultyProfile.objects.create(user=user("teach3", "faculty", faculty_type="full_time", department=CCS))
        self.put(self.secA, self.s1, "Mon", [7, 8, 9])                            # teach1: 3 h
        d = self.get_readonly("/api/analytics/dean/load-bands/", self.dean, {"under_pct": 10}).data
        self.assertFalse(SchedulingConfig.objects.exists())
        names = {b: [r["full_name"] for r in rows] for b, rows in d["bands"].items()}
        self.assertEqual(names["normal"], ["Teach1 T"])                            # 3 h of 24 = 12.5% >= 10%
        self.assertIn("Teach3 T", names["underloaded"]); self.assertIn("Teach2 T", names["underloaded"])
        SchedulingConfig.objects.create(pk=1, max_weekly_hours_full_time=2)
        d = self.get_readonly("/api/analytics/dean/load-bands/", self.dean).data
        over = d["bands"]["overloaded"]
        self.assertEqual([(r["full_name"], r["current_hours"], r["max_hours"], r["overload_hours"]) for r in over], [("Teach1 T", 3.0, 2, 1.0)])
        self.assertTrue(t3)

    def test_roles(self):
        self._dataset()
        for url in self.URLS:
            self.assertEqual(self.get_readonly(url, self.dean_nurse, {"department": CCS}).status_code, 403, url)   # another college
            self.assertEqual(self.get_readonly(url, self.shs).status_code, 403, url)
            self.assertEqual(self.get_readonly(url, self.t1.user).status_code, 403, url)
            self.assertEqual(self.get_readonly(url, self.registrar).status_code, 200, url)                       # read-only, all colleges
            self.assertEqual(self.get_readonly(url, self.admin).status_code, 200, url)
        own = self.get_readonly("/api/analytics/dean/readiness/", self.dean_nurse).data
        self.assertEqual(own["rows"], [])                                                                         # sees nothing of CCS
        reg = self.get_readonly("/api/analytics/dean/readiness/", self.registrar, {"department": CCS}).data
        self.assertTrue(reg["rows"])

    def test_empty_database(self):
        Schedule.objects.all().delete(); Section.objects.all().delete(); Room.objects.all().delete()
        for url in self.URLS:
            self.assertEqual(self.get_readonly(url, self.dean).status_code, 200, url)


class RegistrarInsightTests(InsightBase):
    """Stage 3: Gen Ed coverage, room heatmap, cross-college dependencies, capacity vs enrollment."""

    def _gen_ed(self):
        """GE1 (3 units) in BS Computer Science (A1, B1) and BS Information Technology (I1, 20 students).
        A1 + I1 attend ONE shared class (Mon 7-10, M-101, 45 seats); B1 has its own (Tue 7-10)."""
        self.it = Program.objects.create(name="BS Information Technology", department=CCS)
        self.secI = Section.objects.create(name="I1", program=self.it, year_level="1st Year", semester="1st Sem", student_count=20)
        self.ge = Subject.objects.create(code="GE1", title="Understanding the Self", program=self.prog, lec_units=3, lab_units=0,
                                         year_level="1st Year", semester="1st Sem", classification="minor")
        self.ge_it = Subject.objects.create(code="GE1", title="Understanding the Self", program=self.it, lec_units=3, lab_units=0,
                                            year_level="1st Year", semester="1st Sem", classification="minor")
        for sec, sub in ((self.secA, self.ge), (self.secI, self.ge_it)):
            for h in (7, 8, 9):
                Schedule.objects.create(subject=sub, section=sec, teacher=self.t2, room=self.lec, merge_key="g1", term="1st Sem",
                                        timeslot=TimeSlot.objects.get(day="Mon", start_time=dtime(h)))
        Section.objects.filter(pk=self.secB.pk).update(student_count=15)
        self.put(self.secB, self.ge, "Tue", [7, 8, 9], teacher=self.t2)

    def test_gened_coverage_and_sharing_savings(self):
        self._gen_ed()
        d = self.get_readonly("/api/analytics/registrar/gened-coverage/", self.registrar).data
        self.assertEqual(len(d["subjects"]), 1)                                     # GE1 of both programs is ONE requirement
        g = d["subjects"][0]
        self.assertEqual({k: g[k] for k in ("sections", "placed_sections", "unplaced_sections", "shared_sections", "classes_held",
                                            "classes_saved", "teaching_hours_saved")},
                         {"sections": 3, "placed_sections": 3, "unplaced_sections": 0, "shared_sections": 2, "classes_held": 2,
                          "classes_saved": 1, "teaching_hours_saved": 3.0})
        self.assertEqual(g["programs"], ["BS Computer Science", "BS Information Technology"])

    def test_capacity_vs_enrollment(self):
        self._gen_ed()
        d = self.get_readonly("/api/analytics/capacity/", self.registrar).data
        self.assertEqual(d["classes"], 2)                                           # the shared class counts once
        self.assertEqual([(x["subject"][:3], x["students"], x["seats"], x["shared"]) for x in d["over_capacity"]], [("GE1", 50, 45, True)])
        self.assertEqual([(x["students"], x["fill_pct"]) for x in d["under_half"]], [(15, 33)])

    def test_room_heatmap(self):
        self._gen_ed()
        d = self.get_readonly("/api/analytics/room-heatmap/", self.registrar).data
        self.assertEqual(d["rooms"], 2)                                             # Comp Lab C + M-101
        cell = lambda day, h: next(c for c in d["cells"] if c["day"] == day and c["hour"] == h)
        self.assertEqual((cell("Mon", 7)["rooms_busy"], cell("Mon", 7)["pct"]), (1, 50))  # shared class: one room, once
        self.assertEqual(cell("Mon", 10)["rooms_busy"], 0)
        self.assertEqual(d["days"], ["Mon", "Tue"]); self.assertEqual(d["hours"], [7, 8, 9, 10, 11])
        labs = self.get_readonly("/api/analytics/room-heatmap/", self.registrar, {"room_type": "lab"}).data
        self.assertEqual((labs["rooms"], max(c["rooms_busy"] for c in labs["cells"])), (1, 0))

    def test_dependencies_majors_blocked_by_gen_ed_and_waiting_groups(self):
        from engine.models import SharedClassGroup
        ge = Subject.objects.create(code="GE1", title="Self", program=self.prog, lec_units=3, lab_units=0, year_level="1st Year",
                                    semester="1st Sem", classification="minor")
        ge2 = Subject.objects.create(code="GE2", title="Ethics", program=self.prog, lec_units=2, lab_units=0, year_level="1st Year",
                                     semester="1st Sem", classification="minor")
        self.put(self.secA, ge, "Mon", [7, 8, 9], teacher=self.t2)                # Gen Ed: Mon 7-10
        self.put(self.secA, ge2, "Tue", [8, 9], teacher=self.t2)                  # Gen Ed: Tue 8-10
        self.put(self.secA, self.s1, "Mon", [11])                                  # a major, 1 of 3 h
        d = self.get_readonly("/api/analytics/registrar/dependencies/", self.registrar).data
        got = sorted(x["subject"][:5] for x in d["blocked_by_gen_ed"] if x["section"].endswith("A1"))
        self.assertEqual(got, ["CS101", "CS102"])                                  # longest free window 2 h < 3 h; without Gen Ed: 5 h
        self.assertEqual(d["blocked_by_gen_ed"][0]["gen_ed_hours_in_section"], 5.0)
        # free a 3-hour window: no longer blocked by Gen Ed
        Schedule.objects.filter(section=self.secA, subject=ge2).delete()
        d = self.get_readonly("/api/analytics/registrar/dependencies/", self.registrar).data
        self.assertEqual(d["blocked_by_gen_ed"], [])
        g = SharedClassGroup.objects.create(code="GE1", title="Self", lec_units=3, year_level="1st Year", semester="1st Sem",
                                            created_by=self.dean, confirmed=False)
        g.programs.set([self.prog, Program.objects.create(name="BS Nursing", department="Nursing")])
        SharedClassGroup.objects.create(code="GE2", title="Ethics", lec_units=2, year_level="1st Year", semester="1st Sem", confirmed=True)
        d = self.get_readonly("/api/analytics/registrar/dependencies/", self.registrar).data
        self.assertEqual([(w["code"], w["departments"], w["requested_by"]) for w in d["shared_groups_waiting"]],
                         [("GE1", [CCS, "Nursing"], "Deancs T")])

    def test_roles(self):
        self._gen_ed()
        for url in ("/api/analytics/registrar/gened-coverage/", "/api/analytics/registrar/dependencies/"):
            self.assertEqual(self.get_readonly(url, self.registrar).status_code, 200)
            self.assertEqual(self.get_readonly(url, self.admin).status_code, 200)
            for who in (self.dean, self.shs, self.t1.user):
                self.assertEqual(self.get_readonly(url, who).status_code, 403, (url, who.username))
        for url in ("/api/analytics/room-heatmap/", "/api/analytics/capacity/"):
            self.assertEqual(self.get_readonly(url, self.dean).status_code, 200)
            self.assertEqual(self.get_readonly(url, self.dean_nurse, {"department": CCS}).status_code, 403)
            self.assertEqual(self.get_readonly(url, self.jhs).status_code, 403)
        # a Dean of another college sees none of these classes
        n = self.get_readonly("/api/analytics/capacity/", self.dean_nurse).data
        self.assertEqual((n["classes"], n["over_capacity"]), (0, []))

    def test_empty_database(self):
        Schedule.objects.all().delete(); Section.objects.all().delete(); Room.objects.all().delete()
        for url in ("/api/analytics/registrar/gened-coverage/", "/api/analytics/registrar/dependencies/", "/api/analytics/room-heatmap/",
                    "/api/analytics/capacity/"):
            self.assertEqual(self.get_readonly(url, self.registrar).status_code, 200, url)


class BasicEdInsightTests(APITestCase, ReadOnlyMixin):
    """Stage 4: feasibility, completeness and absences for SHS / JHS principals -- own level only, read-only."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = user("itadmin", "admin")
        cls.jhs = user("prinjhs", "principal", school_level="JHS")
        cls.shs = user("prinshs", "principal", school_level="SHS")
        cls.dean = user("deancs", "faculty", faculty_type="dean", department=CCS)
        bm.AcademicYear.objects.update(is_active=False)
        cls.ay = bm.AcademicYear.objects.create(label="2030-2031", is_active=True)
        for lv in ("JHS", "SHS"):
            bm.SchoolLevelConfig.objects.update_or_create(level=lv, defaults={"name": lv, "building": "B", "period_minutes": 60,
                                                                              "break_minutes": 0, "break_every": 2})
        bm.GradeWindow.objects.filter(level__in=["JHS", "SHS"]).delete()
        # JHS Grade 7: 8:00-2:00 PM, recess 10:00-10:15, lunch 12:00-1:00 -> periods 8-9, 9-10, 10:15-11:15, 1-2 (11:15-12:15 hits lunch)
        bm.GradeWindow.objects.create(level="JHS", grade_level=7, start_time=dtime(8), end_time=dtime(14), recess_start=dtime(10),
                                      recess_end=dtime(10, 15), lunch_start=dtime(12), lunch_end=dtime(13))
        bm.GradeWindow.objects.create(level="SHS", grade_level=11, start_time=dtime(7), end_time=dtime(12, 30), break_start=dtime(9, 30),
                                      break_end=dtime(10))
        cls.sec = bm.Section.objects.create(level="JHS", academic_year=cls.ay, grade_level=7, name="7-A", student_count=40)
        cls.math = bm.CurriculumSubject.objects.create(level="JHS", academic_year=cls.ay, grade_level=7, grading_period=0, code="MATH7",
                                                       name="Mathematics", learning_area="Mathematics", specialization="Math", sessions_per_week=12)
        cls.sci = bm.CurriculumSubject.objects.create(level="JHS", academic_year=cls.ay, grade_level=7, grading_period=0, code="SCI7",
                                                      name="Science", learning_area="Science", specialization="Science", sessions_per_week=10)
        t = user("jt1", "teacher", school_level="JHS")
        cls.teacher = bm.Faculty.objects.create(user=t, level="JHS", employee_id="J1", specializations="Math", max_weekly_hours=30)

    def test_feasibility_uses_the_engines_periods(self):
        d = self.get_readonly("/api/analytics/basic-ed/feasibility/", self.jhs).data
        self.assertEqual(d["level"], "JHS")
        g = d["grades"][0]
        self.assertEqual({k: g[k] for k in ("grade", "day_minutes", "break_minutes", "periods_per_day", "unused_minutes", "periods_per_week",
                                            "max_needed_per_week", "fits", "missing_breaks")},
                         {"grade": 7, "day_minutes": 360, "break_minutes": 75, "periods_per_day": 4, "unused_minutes": 45, "periods_per_week": 20,
                          "max_needed_per_week": 22, "fits": False, "missing_breaks": []})
        self.assertEqual([b["name"] for b in g["breaks"]], ["Recess", "Lunch"])
        s = self.get_readonly("/api/analytics/basic-ed/feasibility/", self.shs).data
        self.assertEqual((s["level"], [x["grade"] for x in s["grades"]], s["grades"][0]["periods_per_day"]), ("SHS", [11], 4))   # 7-8, 8-9, 10-11, 11-12

    def test_completeness_before_and_after_a_timetable(self):
        d = self.get_readonly("/api/analytics/basic-ed/completeness/", self.jhs).data
        g = d["groups"][0]
        self.assertEqual((g["grade"], g["sections"], g["subjects"], g["timetabled"], g["complete"]), (7, ["7-A"], 2, False, False))
        self.assertEqual(g["no_teacher_subjects"], ["SCI7 Science (needs 'Science')"])
        self.assertEqual(g["not_scheduled"], [])                                    # no timetable yet: only curriculum / teacher checks
        run = bm.ScheduleRun.objects.create(level="JHS", academic_year=self.ay, grading_period=1, grade_level=7)
        for i, teacher in enumerate([self.teacher, self.teacher, self.teacher, None]):
            bm.ScheduleEntry.objects.create(run=run, section=self.sec, subject=self.math, subject_code="MATH7", subject_name="Mathematics",
                                                 teacher=teacher, day="Mon", start_time=dtime(8 + i), end_time=dtime(9 + i))
        d = self.get_readonly("/api/analytics/basic-ed/completeness/", self.jhs, {"period": 1}).data
        g = d["groups"][0]
        self.assertTrue(g["timetabled"])
        self.assertEqual(sorted((x["subject"][:5], x["scheduled"], x["needed"]) for x in g["not_scheduled"]), [("MATH7", 4, 12), ("SCI7 ", 0, 10)])
        self.assertEqual(g["periods_without_teacher"], 1)

    def test_absences_are_reported_as_not_recorded(self):
        d = self.get_readonly("/api/analytics/basic-ed/absences/", self.jhs).data
        self.assertEqual((d["recorded"], d["uncovered_classes"]), (False, None))
        self.assertIn("not recorded", d["note"])

    def test_a_principal_never_sees_the_other_level(self):
        for url in ("/api/analytics/basic-ed/feasibility/", "/api/analytics/basic-ed/completeness/", "/api/analytics/basic-ed/absences/"):
            self.assertEqual(self.get_readonly(url, self.jhs, {"level": "SHS"}).status_code, 403, url)
            self.assertEqual(self.get_readonly(url, self.shs, {"level": "JHS"}).status_code, 403, url)
            self.assertEqual(self.get_readonly(url, self.dean).status_code, 403, url)
            self.assertEqual(self.get_readonly(url, self.admin).status_code, 400, url)          # the admin must say which level
            self.assertEqual(self.get_readonly(url, self.admin, {"level": "JHS"}).status_code, 200, url)
        shs = self.get_readonly("/api/analytics/basic-ed/completeness/", self.shs).data
        self.assertEqual(shs["groups"], [])                                                     # the JHS section is not shown to SHS

    def test_level_not_set_up_does_not_crash(self):
        bm.SchoolLevelConfig.objects.filter(level="JHS").delete()
        d = self.get_readonly("/api/analytics/basic-ed/feasibility/", self.jhs).data
        self.assertFalse(d["configured"])
        bm.ScheduleEntry.objects.all().delete(); bm.Section.objects.all().delete()
        self.assertEqual(self.get_readonly("/api/analytics/basic-ed/completeness/", self.jhs).status_code, 200)


class FilterAndTrendTests(InsightBase):
    """Stage 5: filter options (scoped), school-year and program filters, and the SHS / JHS run trend."""

    def _two_programs(self):
        self.it = Program.objects.create(name="BS Information Technology", department=CCS)
        self.secI = Section.objects.create(name="I1", program=self.it, year_level="1st Year", semester="1st Sem", student_count=60)
        self.sI = Subject.objects.create(code="IT101", title="IT Basics", program=self.it, lec_units=1, lab_units=0, year_level="1st Year",
                                         semester="1st Sem", classification="major")
        self.put(self.secA, self.s1, "Mon", [7, 8, 9])                                      # CS, 30 students in 45 seats
        Schedule.objects.filter(section=self.secA).update(school_year="2026-2027")
        Schedule.objects.create(subject=self.sI, section=self.secI, teacher=self.t2, room=self.lec, term="1st Sem", school_year="2025-2026",
                                timeslot=TimeSlot.objects.get(day="Tue", start_time=dtime(7)))      # IT, 60 students in 45 seats
        self.nprog = Program.objects.create(name="BS Nursing", department="Nursing")

    def test_filter_options_are_scoped(self):
        self._two_programs()
        d = self.get_readonly("/api/analytics/filters/", self.dean).data
        self.assertEqual([p["name"] for p in d["programs"]], ["BS Computer Science", "BS Information Technology"])
        self.assertEqual(d["departments"], [CCS]); self.assertEqual(d["school_years"], ["2026-2027", "2025-2026"])
        r = self.get_readonly("/api/analytics/filters/", self.registrar).data
        self.assertIn("BS Nursing", [p["name"] for p in r["programs"]])
        self.assertEqual(self.get_readonly("/api/analytics/filters/", self.shs).status_code, 403)

    def test_school_year_and_program_filters(self):
        self._two_programs()
        cap = lambda **p: self.get_readonly("/api/analytics/capacity/", self.registrar, p).data
        self.assertEqual(len(cap()["over_capacity"]), 1)                                     # IT: 60 in 45
        self.assertEqual(cap(school_year="2026-2027")["over_capacity"], [])                 # IT class is 2025-2026
        self.assertEqual(cap(program_id=self.prog.id)["classes"], 1)
        self.assertEqual(cap(program_id=self.it.id)["over_capacity"][0]["subject"][:5], "IT101")
        rd = self.get_readonly("/api/analytics/dean/readiness/", self.dean, {"school_year": "2025-2026", "program_id": self.prog.id}).data
        row = next(r for r in rd["rows"] if r["year_level"] == "1st Year")
        self.assertEqual(row["placed"], 0)                                                   # the CS class is 2026-2027
        hm = self.get_readonly("/api/analytics/room-heatmap/", self.registrar, {"program_id": self.it.id}).data
        self.assertEqual(sum(c["rooms_busy"] for c in hm["cells"]), 1)
        # a Dean asking for another college's program gets nothing of it (scope still applies)
        n = self.get_readonly("/api/analytics/capacity/", self.dean_nurse, {"program_id": self.it.id}).data
        self.assertEqual(n["classes"], 0)

    def test_basic_ed_run_trend(self):
        bm.AcademicYear.objects.update(is_active=False)
        ay = bm.AcademicYear.objects.create(label="2031-2032", is_active=True)
        old = bm.ScheduleRun.objects.create(level="JHS", academic_year=ay, grading_period=1, grade_level=7, status="superseded")   # no counts stored
        new = bm.ScheduleRun.objects.create(level="JHS", academic_year=ay, grading_period=1, grade_level=7, version=2,
                                            stats={"placed": 90, "unresolved": 10, "sections": 3}, validation={"errors": 2, "warnings": 1})
        bm.ScheduleRun.objects.create(level="SHS", academic_year=ay, grading_period=1, grade_level=11, stats={"placed": 5, "unresolved": 0})
        jhs = user("pj2", "principal", school_level="JHS")
        d = self.get_readonly("/api/analytics/basic-ed/run-trend/", jhs).data
        self.assertEqual([r["id"] for r in d["runs"]], [old.id, new.id])                    # time order, replaced runs kept, JHS only
        self.assertEqual((d["runs"][0]["placed"], d["runs"][0]["efficiency_pct"]), (None, None))   # not stored: blank, not zero
        self.assertEqual((d["runs"][1]["efficiency_pct"], d["runs"][1]["conflicts"]), (90.0, 2))
        self.assertEqual(self.get_readonly("/api/analytics/basic-ed/run-trend/", jhs, {"level": "SHS"}).status_code, 403)
        self.assertEqual(self.get_readonly("/api/analytics/basic-ed/run-trend/", self.dean).status_code, 403)


class DeanTeacherWorkloadTests(InsightBase):
    """The existing Analytics (/api/analytics/): a Dean's Teacher Workload lists the Dean's OWN faculty only, with their total hours."""

    def _data(self):
        nprog = Program.objects.create(name="BS Nursing", department="Nursing")
        self.secN = Section.objects.create(name="N1", program=nprog, year_level="1st Year", semester="1st Sem", student_count=30)
        nsub = Subject.objects.create(code="NCM1", title="Care", program=nprog, lec_units=3, lab_units=0, year_level="1st Year",
                                      semester="1st Sem", classification="major")
        ge = Subject.objects.create(code="GE1", title="Self", program=self.prog, lec_units=3, lab_units=0, year_level="1st Year",
                                    semester="1st Sem", classification="minor")
        self.gened = FacultyProfile.objects.create(user=user("gened1", "faculty", faculty_type="full_time", department="Arts and Sciences"))
        self.nurse = FacultyProfile.objects.create(user=user("nurse1", "faculty", faculty_type="full_time", department="Nursing"))
        self.put(self.secA, self.s1, "Mon", [7, 8, 9])                                  # teach1 (CCS): 3 h in CCS
        self.put(self.secN, nsub, "Tue", [7, 8], room=self.lab)                         # teach1 also teaches 2 h in Nursing
        self.put(self.secA, ge, "Mon", [10], teacher=self.gened)                        # a Gen Ed teacher of another department, CCS class
        self.put(self.secN, nsub, "Tue", [9], teacher=self.nurse, room=self.lab)        # a Nursing teacher, Nursing class
        for sec in (self.secA, self.secB):                                              # teach2: one SHARED class, two sections, 1 h
            Schedule.objects.create(subject=ge, section=sec, teacher=self.t2, room=self.lec, merge_key="shared1", term="1st Sem",
                                    timeslot=TimeSlot.objects.get(day="Tue", start_time=dtime(10)))

    def get(self, who):
        r = self.get_readonly("/api/analytics/", who)
        self.assertEqual(r.status_code, 200)
        return r

    def test_dean_sees_only_own_faculty_with_total_hours(self):
        self._data()
        r = self.get(self.dean)
        d = r.data
        self.assertEqual(d["teacher_workload"], {"teach1": 5.0, "teach2": 1.0})        # 3 h CCS + 2 h Nursing; shared class once
        self.assertEqual(d["workload_std_dev"], 2.0)                                    # from [5, 1]
        # another department's teacher is not in the API response at all (not just hidden in the UI)
        body = r.content.decode()
        self.assertNotIn("gened1", body); self.assertNotIn("nurse1", body)
        # unchanged college figures: the Gen Ed class in a CCS section still counts for rooms and hours by day
        self.assertEqual(d["room_utilization"], {"M-101": 5.0})                          # CS 3 h + Gen Ed 1 h + shared 1 h (once)
        self.assertEqual(d["class_hours_by_day"]["Mon"], 4.0)

    def test_dean_with_two_departments_sees_both(self):
        self._data()
        both = user("deanboth", "faculty", faculty_type="dean", department=CCS, extra_departments="Nursing")
        d = self.get(both).data
        self.assertEqual(d["teacher_workload"], {"teach1": 5.0, "teach2": 1.0, "nurse1": 1.0})
        self.assertNotIn("gened1", d["teacher_workload"])
        n = self.get(self.dean_nurse).data                                              # Nursing dean: own faculty only
        self.assertEqual(n["teacher_workload"], {"nurse1": 1.0})

    def test_registrar_output_is_unchanged(self):
        self._data()
        d = self.get(self.registrar).data
        # institution-wide, every teacher on any class, exactly as before (teach1 counted over both colleges)
        self.assertEqual(d["teacher_workload"], {"teach1": 5.0, "teach2": 1.0, "gened1": 1.0, "nurse1": 1.0})
        self.assertEqual(d["room_utilization"], {"M-101": 5.0, "Comp Lab C": 3.0})

    def test_own_faculty_without_classes_is_simply_absent(self):
        self.put(self.secA, self.s1, "Mon", [7], teacher=FacultyProfile.objects.create(
            user=user("outsider", "faculty", faculty_type="full_time", department="Arts and Sciences")))
        d = self.get(self.dean).data
        self.assertEqual(d["teacher_workload"], {})                                     # teach1 / teach2 have no classes
        self.assertEqual(d["workload_std_dev"], 0)
