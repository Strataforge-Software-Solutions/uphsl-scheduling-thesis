from datetime import time as dtime

from rest_framework.test import APITestCase

from accounts.models import User
from curriculum.models import Program, Subject
from engine.models import Section, TimeSlot
from exams.models import ExamSchedule
from exams.room_rules import check_exams
from faculty.models import FacultyProfile
from rooms.models import Room

CS = "Computer Studies"
START, END = "2026-10-12", "2026-10-17"


def _user(name, role="faculty", ftype="full_time", dept=CS):
    u = User(username=name, school_id=name, first_name=name, last_name="X", role=role, faculty_type=ftype, department=dept)
    u.set_password("pw"); u.save()
    if role == "faculty":
        FacultyProfile.objects.create(user=u)
    return u


class ExamRoomRuleTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dean = _user("DeanCS", ftype="dean")
        cls.registrar = _user("RegX", role="registrar", ftype="")
        for i in range(4):
            _user(f"P{i}")
        mk = lambda name, b, n, t, dept=None, cap=40: Room.objects.create(name=name, building=b, room_number=n, room_type=t, capacity=cap, department=dept)
        cls.lab_c = mk("Comp Lab C", "D", "307", "lab", CS)
        cls.lab_d = mk("Comp Lab D", "D", "309", "lab", CS)
        cls.lec = {k: mk(k, k[0], k[2:], "lecture") for k in ("M-101", "M-205", "M-301", "M-402", "D-301", "N-201", "N-301", "N-101")}
        cls.cs = Program.objects.create(name="BS CSx", department=CS)
        cls.sec = Section.objects.create(name="A1", program=cls.cs, year_level="1st Year", semester="1st Sem", student_count=30)
        Subject.objects.create(code="CS101", title="Intro", program=cls.cs, lec_units=3, lab_units=0, year_level="1st Year",
                               semester="1st Sem", classification="major")
        Subject.objects.create(code="CS101L", title="Intro Lab", program=cls.cs, lec_units=0, lab_units=1, year_level="1st Year",
                               semester="1st Sem", classification="major")
        Subject.objects.create(code="GE101", title="Gen Ed", program=cls.cs, lec_units=3, lab_units=0, year_level="1st Year",
                               semester="1st Sem", classification="minor")
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"):
            for h in range(7, 20):
                TimeSlot.objects.get_or_create(day=d, start_time=dtime(h), end_time=dtime(h + 1))

    def gen(self, user):
        self.client.force_authenticate(user)
        return self.client.post("/api/exams/generate/", {"semester": "1st Sem", "exam_period": "Midterm",
                                                         "exam_start_date": START, "exam_end_date": END}, format="json")

    def _url_ok(self):
        r = self.gen(self.dean)
        return r

    def test_lab_and_lecture_subjects_both_get_exams_and_cs_labs_use_lab_c_or_d(self):
        r = self.gen(self.dean)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["unresolved"], [])
        exams = {e.subject.code: e for e in ExamSchedule.objects.select_related("room", "subject")}
        self.assertEqual(set(exams), {"CS101", "CS101L"})
        self.assertIn(exams["CS101L"].room_id, (self.lab_c.id, self.lab_d.id))
        self.assertNotIn(exams["CS101"].room_id, (self.lab_c.id, self.lab_d.id))      # the lecture leaves the labs free
        self.assertEqual(r.data["validation"]["counts"]["missing"], 0)
        self.assertEqual(r.data["validation"]["counts"]["rule_violations"], 0)

    def test_minor_exams_use_main_1_to_3_alta_3_and_new_building_2_to_3(self):
        r = self.gen(self.registrar)
        self.assertEqual(r.status_code, 201, r.data)
        e = ExamSchedule.objects.select_related("room").get(subject__code="GE101")
        self.assertIn(e.room.name, {"M-101", "M-205", "M-301", "D-301", "N-201", "N-301"})
        self.assertNotIn(e.room.name, {"M-402", "N-101"})
        self.assertNotIn(e.room_id, (self.lab_c.id, self.lab_d.id))

    def test_rooms_are_spread_over_the_three_buildings(self):
        for i in range(2, 13):
            Section.objects.create(name=f"A{i}", program=self.cs, year_level="1st Year", semester="1st Sem", student_count=30)
        self.gen(self.registrar)
        buildings = {e.room.building for e in ExamSchedule.objects.select_related("room")}
        self.assertEqual(buildings, {"M", "D", "N"})
        self.assertEqual(self.gen(self.registrar).data["validation"]["counts"]["room_conflicts"], 0)

    def test_check_reports_a_cs_lab_exam_in_the_wrong_room(self):
        self.gen(self.dean)
        e = ExamSchedule.objects.select_related("subject", "section__program", "room", "timeslot").get(subject__code="CS101L")
        e.room = self.lec["M-101"]
        out = check_exams([e], {(e.subject_id, e.section_id)})
        self.assertEqual(out["counts"]["rule_violations"], 1)
        self.assertEqual(check_exams([], {(e.subject_id, e.section_id)})["counts"]["missing"], 1)


class ExamCommonSlotAndResolveTests(ExamRoomRuleTests):
    """Gen Ed: one subject = one hour, each section in its own room. Blocked exams are placed by moving program exams."""

    def _two_sections(self):
        return [self.sec, Section.objects.create(name="A2", program=self.cs, year_level="1st Year", semester="1st Sem", student_count=30)]

    def test_same_subject_same_hour_different_rooms(self):
        self._two_sections()
        r = self.gen(self.registrar)
        self.assertEqual(r.status_code, 201, r.data)
        exams = list(ExamSchedule.objects.filter(subject__code="GE101"))
        self.assertEqual(len(exams), 2)
        self.assertEqual(len({(e.exam_date, e.timeslot_id) for e in exams}), 1)        # same date and hour
        self.assertEqual(len({e.room_id for e in exams}), 2)                           # different rooms
        self.assertEqual(len({e.proctor_id for e in exams}), 2)                        # different proctors

    def test_oversized_section_is_placed_with_a_capacity_warning(self):
        Section.objects.filter(pk=self.sec.pk).update(student_count=55)
        r = self.gen(self.registrar)
        self.assertEqual(r.data["unresolved"], [])
        self.assertTrue(r.data["capacity_warnings"])

    def _blocked_setup(self):
        a1, a2 = self._two_sections()
        ge, major = Subject.objects.get(code="GE101"), Subject.objects.get(code="CS101")
        mon = TimeSlot.objects.get(day="Mon", start_time=dtime(7))
        profs = list(FacultyProfile.objects.all())
        day = __import__("datetime").date(2026, 10, 12)
        mk = lambda sub, sec, room, proc, **k: ExamSchedule.objects.create(
            subject=sub, section=sec, proctor=profs[proc], room=room, timeslot=mon, exam_date=day,
            exam_period="midterm", school_year="2026-2027", **k)
        mk(ge, a1, self.lec["M-101"], 0)                                              # sibling section already at Mon 7:00
        blocker = mk(major, a2, self.lec["M-205"], 1, is_manual_override=True)       # A2's own program exam sits in that hour
        body = {"semester": "1st Sem", "exam_period": "midterm", "exam_start_date": START, "exam_end_date": END,
                "items": [{"subject_id": ge.id, "section_id": a2.id}]}
        return ge, a2, mon, day, blocker, body

    def test_registrar_cannot_move_major_exams_it_asks_the_dean(self):
        from notifications.models import Notification
        ge, a2, mon, day, blocker, body = self._blocked_setup()
        self.client.force_authenticate(self.registrar)
        prev = self.client.post("/api/exams/resolve/", body, format="json")
        item = prev.data["items"][0]
        self.assertEqual(item["status"], "needs_dean", item)
        self.assertEqual(item["place"]["start"], "07:00")                             # same hour as the other section
        done = self.client.post("/api/exams/resolve/", {**body, "apply": True}, format="json")
        self.assertEqual(done.data["items"][0]["status"], "requested")
        blocker.refresh_from_db()
        self.assertEqual((blocker.exam_date, blocker.timeslot_id), (day, mon.id))     # the major exam was NOT touched
        self.assertFalse(ExamSchedule.objects.filter(subject=ge, section=a2).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.dean, notif_type="conflict_alert").exists())

    def test_dean_moves_own_major_exam_then_registrar_places_the_gen_ed_exam(self):
        ge, a2, mon, day, blocker, body = self._blocked_setup()
        self.client.force_authenticate(self.dean)
        dean_body = {k: v for k, v in body.items() if k != "items"}
        done = self.client.post("/api/exams/resolve/", {**dean_body, "apply": True}, format="json")
        self.assertTrue(done.data["applied"], done.data)
        blocker.refresh_from_db()
        self.assertNotEqual((blocker.exam_date, blocker.timeslot_id), (day, mon.id))
        self.client.force_authenticate(self.registrar)
        placed = self.client.post("/api/exams/resolve/", {**body, "apply": True}, format="json")
        self.assertEqual(placed.data["items"][0]["status"], "placed", placed.data)
        self.assertTrue(ExamSchedule.objects.filter(subject=ge, section=a2, timeslot=mon, exam_date=day).exists())
        rows = list(ExamSchedule.objects.select_related("subject", "section__program", "room", "timeslot"))
        self.assertEqual(check_exams(rows)["counts"]["room_conflicts"], 0)

    def test_resolve_is_refused_for_other_roles(self):
        self.client.force_authenticate(User.objects.get(username="P0"))
        r = self.client.post("/api/exams/resolve/", {}, format="json")
        self.assertEqual(r.status_code, 403)


class ProctorRuleTests(ExamRoomRuleTests):
    """Major exams: own-college faculty and Dean. Gen Ed exams: CAS faculty whose specialization matches the subject."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from curriculum.models import AcademicField
        CAS = "College of Arts and Science"
        cls.english = FacultyProfile.objects.get(user=_user("CasEng", dept=CAS))
        cls.english.specializations.add(AcademicField.objects.get_or_create(name="English")[0])
        cls.math = FacultyProfile.objects.get(user=_user("CasMath", dept=CAS))
        cls.math.specializations.add(AcademicField.objects.get_or_create(name="Mathematics")[0])
        cls.nurse = FacultyProfile.objects.get(user=_user("NurseX", dept="Nursing"))
        cls.nurse.specializations.add(AcademicField.objects.get_or_create(name="English")[0])   # right specialization, wrong college
        Subject.objects.create(code="GEC106", title="Purposive Communication", program=cls.cs, lec_units=3, lab_units=0,
                               year_level="1st Year", semester="1st Sem", classification="minor")
        Subject.objects.create(code="GEC105", title="Mathematics in the Modern World", program=cls.cs, lec_units=3, lab_units=0,
                               year_level="1st Year", semester="1st Sem", classification="minor")

    def test_gen_ed_exam_proctors_are_cas_faculty_of_the_right_specialization(self):
        self.assertEqual(self.gen(self.registrar).status_code, 201)
        by = {e.subject.code: e.proctor_id for e in ExamSchedule.objects.filter(subject__classification="minor")}
        self.assertEqual(by["GEC106"], self.english.id)
        self.assertEqual(by["GEC105"], self.math.id)

    def test_major_exam_proctors_come_from_the_own_college_including_the_dean(self):
        self.assertEqual(self.gen(self.dean).status_code, 201)
        cs_ids = set(FacultyProfile.objects.filter(user__department=CS).values_list("id", flat=True))
        got = set(ExamSchedule.objects.filter(subject__classification="major").values_list("proctor_id", flat=True))
        self.assertTrue(got and got <= cs_ids)

    def test_check_reports_a_wrong_proctor(self):
        self.gen(self.registrar)
        e = ExamSchedule.objects.select_related("subject", "section__program", "room", "timeslot", "proctor__user").get(subject__code="GEC106")
        e.proctor = FacultyProfile.objects.get(user__username="P0")          # a Computer Studies teacher: not CAS, no matching specialization
        out = check_exams([e])
        self.assertTrue(any("proctor" in v for v in out["rule_violations"]))


class ExamCombineTests(APITestCase):
    """Low-enrollment Gen Ed sections of different programs sit ONE exam together (same rule as shared classes in engine.merging)."""

    @classmethod
    def setUpTestData(cls):
        cls.registrar = _user("RegY", role="registrar", ftype="")
        cas = "College of Arts and Science"
        for i in range(3):
            u = _user(f"C{i}", dept=cas)
            u.faculty_profile.specializations.set([]) if hasattr(u, "faculty_profile") else None
        for i, n in enumerate(("M-301", "M-304", "M-305", "M-306")):
            Room.objects.create(name=n, building="M", room_number=n[2:], room_type="lecture", capacity=40)
        Room.objects.create(name="Comp Lab C", building="D", room_number="307", room_type="lab", capacity=40, department=CS)
        Room.objects.create(name="Chem Lab", building="D", room_number="101", room_type="lab", capacity=40)
        cls.progs = {}
        for name, dept, counts in (("BS CSy", CS, 15), ("BS ITy", CS, 15), ("BA Cy", cas, 5), ("BS RTy", "Radiologic Technology", 30)):
            p = Program.objects.create(name=name, department=dept)
            cls.progs[name] = p
            Section.objects.create(name="A1", program=p, year_level="1st Year", semester="1st Sem", student_count=counts)
            for code, lab in (("GE900", 0), ("GE901", 1)):
                Subject.objects.create(code=code, title=f"Gen {code}", program=p, lec_units=3, lab_units=lab, year_level="1st Year",
                                       semester="1st Sem", classification="minor")
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"):
            for h in range(7, 20):
                TimeSlot.objects.get_or_create(day=d, start_time=dtime(h), end_time=dtime(h + 1))

    def gen(self):
        self.client.force_authenticate(self.registrar)
        return self.client.post("/api/exams/generate/", {"semester": "1st Sem", "exam_period": "Midterm",
                                                         "exam_start_date": START, "exam_end_date": END}, format="json")

    def test_small_sections_share_one_room_hour_and_proctor(self):
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["unresolved"], [])
        rows = list(ExamSchedule.objects.filter(subject__code="GE900").select_related("section__program"))
        self.assertEqual(len(rows), 4)                                  # every section still has its own exam row
        groups = {}
        for e in rows:
            groups.setdefault(e.merge_key, []).append(e)
        # Computer Studies (CS 15 + IT 15) are packed first, then the next department takes the seats that are left (BA 5 -> 35 of 40);
        # RadTech (30) no longer fits, so it keeps its own exam room
        merged = [g for k, g in groups.items() if k]
        self.assertEqual([sorted(e.section.program.name for e in g) for g in merged], [["BA Cy", "BS CSy", "BS ITy"]])
        self.assertEqual([e.section.program.name for e in groups[""]], ["BS RTy"])
        for g in merged:
            self.assertEqual(len({(e.room_id, e.timeslot_id, e.exam_date, e.proctor_id) for e in g}), 1)   # one room, hour, proctor
            self.assertLessEqual(sum(e.section.student_count for e in g), 40)
        self.assertEqual(len({e.room_id for e in rows}), 2)
        self.assertEqual(r.data["validation"]["counts"]["room_conflicts"], 0)
        self.assertEqual(r.data["validation"]["counts"]["missing"], 0)

    def test_lab_subjects_are_never_combined(self):
        self.gen()
        self.assertEqual(ExamSchedule.objects.filter(subject__code="GE901").exclude(merge_key="").count(), 0)

    def test_a_busy_member_moves_the_sitting_to_another_hour(self):
        from engine.models import Schedule
        sec = Section.objects.get(program=self.progs["BA Cy"])
        self.gen()
        first = ExamSchedule.objects.filter(subject__code="GE900", section=sec).first()
        ExamSchedule.objects.all().delete()
        teacher = FacultyProfile.objects.first()
        sub = Subject.objects.get(code="GE900", program=sec.program)
        Schedule.objects.create(subject=sub, teacher=teacher, room=Room.objects.first(), section=sec, timeslot=first.timeslot,
                                school_year="2026-2027", status="draft", term="1st Sem")
        self.gen()
        mine = ExamSchedule.objects.get(subject__code="GE900", section=sec)
        self.assertNotEqual((mine.exam_date, mine.timeslot_id), (first.exam_date, first.timeslot_id))
        mates = ExamSchedule.objects.filter(merge_key=mine.merge_key)
        self.assertEqual(len(mates), 3)
        self.assertEqual(len({(e.exam_date, e.timeslot_id, e.room_id) for e in mates}), 1)       # the sitting moved as a whole

    def test_api_lists_who_is_combined(self):
        self.gen()
        self.client.force_authenticate(self.registrar)
        rows = self.client.get("/api/exams/").data
        rows = rows["results"] if isinstance(rows, dict) else rows
        ge = [x for x in rows if x["subject_code"] == "GE900" and x["merge_key"]]
        self.assertEqual(len(ge), 3)
        self.assertTrue(all(len(x["combined_with"]) == 2 for x in ge))

    def test_set_enrollment_command_applies_the_counts(self):
        from django.core.management import call_command
        p = Program.objects.create(name="BS Computer Science", department=CS)
        for y in ("1st Year", "2nd Year"):
            Section.objects.create(name="A", program=p, year_level=y, semester="1st Sem", student_count=33)
            Section.objects.create(name="B", program=p, year_level=y, semester="1st Sem", student_count=33)
        call_command("set_enrollment", "--dry-run", verbosity=0)
        self.assertEqual(Section.objects.filter(program=p, student_count=33).count(), 4)
        call_command("set_enrollment", verbosity=0)
        self.assertEqual(sorted(Section.objects.filter(program=p, year_level="1st Year").values_list("student_count", flat=True)), [7, 8])
        self.assertEqual(sorted(Section.objects.filter(program=p, year_level="2nd Year").values_list("student_count", flat=True)), [7, 8])
