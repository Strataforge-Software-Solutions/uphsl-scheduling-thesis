"""
Regression tests for the schedule workflow: generation (empty table, repeated, several programs), conflict
prevention on save, the DB safety net, deletion, and the conflict report / resolver.

    python manage.py test engine
"""
from datetime import time as dtime

from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from accounts.models import User
from curriculum.models import AcademicField, Program, Subject
from engine.conflict_report import scan
from engine.conflict_resolve import resolve_all
from engine.models import ConflictLog, Schedule, Section, TimeSlot
from faculty.models import FacultyProfile
from rooms.models import Room

DEPT = "Computer Studies"
SY = "2026-2027"


def make_teacher(i, ftype="full_time"):
    u = User(username=f"T{i}", school_id=f"T{i}", first_name="Teach", last_name=f"Er{i}", role="faculty", faculty_type=ftype,
             department=DEPT)
    u.set_password("pw")
    u.save()
    # Computer Studies faculty with a computing degree: a major subject only goes to a teacher of a related discipline
    p = FacultyProfile.objects.create(user=u, degree="BS Computer Science")
    return p


def make_cas_teacher(i, ftype="full_time"):
    """A College of Arts and Science teacher for the Gen Ed fixtures: since the CAS rule, Gen Ed subjects go to CAS faculty of the
    subject's area (Psychology for Understanding the Self, English for Purposive Communication, FCL, Philosophy for Ethics, ...)."""
    u = User(username=f"C{i}", school_id=f"C{i}", first_name="Cas", last_name=f"Ge{i}", role="faculty", faculty_type=ftype,
             department="College of Arts and Science")
    u.set_password("pw")
    u.save()
    p = FacultyProfile.objects.create(user=u)
    p.specializations.set([AcademicField.objects.get_or_create(name=n)[0] for n in
                           ("Psychology", "English", "FCL", "Philosophy", "Literature", "Science", "Physical Education", "Social Science")])
    return p


class Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dean = User(username="DeanT", school_id="DT", first_name="Dean", last_name="T", role="faculty",
                        faculty_type="dean", department=DEPT)
        cls.dean.set_password("pw"); cls.dean.save()
        FacultyProfile.objects.create(user=cls.dean)
        cls.registrar = User(username="RegT", school_id="RT", first_name="Reg", last_name="T", role="registrar")
        cls.registrar.set_password("pw"); cls.registrar.save()
        cls.teachers = [make_teacher(i) for i in range(1, 7)]
        cls.rooms = [Room.objects.create(name=f"N-10{i}", capacity=60, room_type="lecture") for i in range(1, 5)]
        cls.prog = Program.objects.create(name="BS CS Test", department=DEPT)
        cls.sec = [Section.objects.create(name=f"T1{c}", program=cls.prog, year_level="1st Year", semester="1st Sem",
                                          student_count=30) for c in "AB"]
        for i in range(6):
            Subject.objects.create(code=f"TST10{i}", title=f"Test Subject {i}", program=cls.prog, lec_units=3, lab_units=0,
                                   year_level="1st Year", semester="1st Sem", classification="major")
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in range(7, 20):
                TimeSlot.objects.get_or_create(day=d, start_time=dtime(h), end_time=dtime(h + 1))

    def gen(self, user=None, **over):
        self.client.force_authenticate(user or self.dean)
        body = {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem", "school_year": SY}
        body.update(over)
        return self.client.post("/api/engine/generate-schedule/", body, format="json")

    def row(self, sec=None, teacher=None, room=None, day="Mon", h=7, subj=0, merge=""):
        slot, _ = TimeSlot.objects.get_or_create(day=day, start_time=dtime(h), end_time=dtime(h + 1))
        return Schedule.objects.create(subject=Subject.objects.get(code=f"TST10{subj}"), section=sec or self.sec[0],
                                       teacher=teacher or self.teachers[0], room=room or self.rooms[0], timeslot=slot,
                                       merge_key=merge)


class GenerationTests(Base):
    def test_generates_on_empty_table_without_conflicts(self):
        self.assertEqual(Schedule.objects.count(), 0)
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertGreater(Schedule.objects.count(), 0)
        self.assertEqual(scan()["total"], 0)
        self.assertEqual(r.data["clashes"]["total"], 0)

    def test_repeat_generation_replaces_draft_not_stacks(self):
        self.gen()
        n = Schedule.objects.count()
        for _ in range(3):
            r = self.gen()
            self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Schedule.objects.count(), n)
        self.assertEqual(scan()["total"], 0)

    def test_generate_after_everything_deleted(self):
        self.gen()
        Schedule.objects.all().delete()
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(scan()["total"], 0)

    def test_approved_classes_are_not_overwritten(self):
        self.gen()
        Schedule.objects.update(status="approved")
        n = Schedule.objects.count()
        r = self.gen()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Schedule.objects.count(), n)

    def test_invalid_input_gives_clear_errors(self):
        self.client.force_authenticate(self.dean)
        for body in ({}, {"program_id": "abc", "year_level": "1st Year", "semester": "1st Sem"},
                     {"program_id": self.prog.id, "year_level": "9th Year", "semester": "1st Sem"},
                     {"program_id": 99999, "year_level": "1st Year", "semester": "1st Sem"}):
            r = self.client.post("/api/engine/generate-schedule/", body, format="json")
            self.assertIn(r.status_code, (400, 403), (body, r.status_code))
            self.assertIn("detail", r.data)

    def test_wrong_role_is_refused(self):
        r = self.gen(user=self.teachers[0].user)
        self.assertEqual(r.status_code, 403)

    def test_two_programs_share_teachers_without_clashing(self):
        p2 = Program.objects.create(name="BS CS Test Two", department=DEPT)
        Section.objects.create(name="T2A", program=p2, year_level="1st Year", semester="1st Sem", student_count=30)
        for i in range(6):
            Subject.objects.create(code=f"TWO10{i}", title=f"Two Subject {i}", program=p2, lec_units=3, lab_units=0,
                                   year_level="1st Year", semester="1st Sem", classification="major")
        self.assertEqual(self.gen().status_code, 201)
        self.assertEqual(self.gen(program_id=p2.id).status_code, 201)
        self.assertEqual(self.gen().status_code, 201)             # regenerate the first around the second
        self.assertEqual(scan()["total"], 0)


class SaveValidationTests(Base):
    def post(self, **kw):
        self.client.force_authenticate(self.dean)
        slot, _ = TimeSlot.objects.get_or_create(day=kw.get("day", "Mon"), start_time=dtime(kw.get("h", 7)), end_time=dtime(kw.get("h", 7) + 1))
        body = {"subject": Subject.objects.get(code=f"TST10{kw.get('subj', 1)}").id, "section": kw["sec"].id,
                "teacher": kw["teacher"].id, "room": kw["room"].id, "timeslot": slot.id}
        return self.client.post("/api/engine/schedules/", body, format="json")

    def test_teacher_room_and_section_double_booking_are_refused(self):
        self.row()
        r1 = self.post(sec=self.sec[1], teacher=self.teachers[0], room=self.rooms[1])      # same teacher
        r2 = self.post(sec=self.sec[1], teacher=self.teachers[1], room=self.rooms[0])      # same room
        r3 = self.post(sec=self.sec[0], teacher=self.teachers[1], room=self.rooms[1])      # same students
        for r in (r1, r2, r3):
            self.assertEqual(r.status_code, 400, r.data)
            self.assertIn("detail", r.data)
        self.assertEqual(Schedule.objects.count(), 1)

    def test_free_slot_is_saved_and_overlap_in_another_slot_is_refused(self):
        self.row()
        ok = self.post(sec=self.sec[1], teacher=self.teachers[1], room=self.rooms[1], h=9)
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(Schedule.objects.count(), 2)

    def test_update_into_a_conflict_is_refused_and_row_unchanged(self):
        a = self.row()
        b = self.row(sec=self.sec[1], teacher=self.teachers[1], room=self.rooms[1], h=9, subj=1)
        self.client.force_authenticate(self.dean)
        r = self.client.patch(f"/api/engine/schedules/{b.id}/", {"teacher": a.teacher_id, "timeslot": a.timeslot_id}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        b.refresh_from_db()
        self.assertEqual(b.teacher_id, self.teachers[1].id)

    def test_database_blocks_double_booking_even_without_the_api(self):
        self.row()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(sec=self.sec[1], teacher=self.teachers[0], room=self.rooms[1], subj=1)

    def test_garbage_input_gives_400_not_500(self):
        self.client.force_authenticate(self.dean)
        for body in ({}, {"subject": 999999, "section": 1, "teacher": 1, "room": 1, "timeslot": 1}, {"subject": "x"}):
            r = self.client.post("/api/engine/schedules/", body, format="json")
            self.assertEqual(r.status_code, 400, (body, r.status_code))

    def test_delete_then_regenerate(self):
        self.gen()
        row = Schedule.objects.first()
        self.client.force_authenticate(self.dean)
        self.assertEqual(self.client.delete(f"/api/engine/schedules/{row.id}/").status_code, 204)
        self.assertEqual(self.gen().status_code, 201)
        self.assertEqual(scan()["total"], 0)

    def test_deleting_a_teacher_room_or_section_leaves_no_orphans(self):
        self.gen()
        used = Schedule.objects.values_list("teacher_id", flat=True).first()
        FacultyProfile.objects.filter(pk=used).delete()          # cascade: their classes go with them, nothing dangles
        self.assertFalse(Schedule.objects.filter(teacher_id=used).exists())
        self.assertEqual(self.gen().status_code, 201)


class ConflictToolTests(Base):
    def test_students_never_overlap_and_print_refuses_a_clashing_table(self):
        """Class schedules follow the solver's rule: a section is never in two classes at once (even 30 min)."""
        a = self.row(h=7)                                                    # Mon 7-8, section A
        half, _ = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))
        Schedule.objects.create(subject=Subject.objects.get(code="TST102"), section=a.section, teacher=self.teachers[3], room=self.rooms[2], timeslot=half)
        rep = scan()
        self.assertEqual(rep["counts"].get("section"), 1, rep)               # a 30-minute student overlap is reported, not hidden
        from engine.conflicts import find_conflicts
        self.assertTrue(find_conflicts(section=a.section, timeslot=half, semester="1st Sem", exclude_pk=None))
        # the print preview refuses to print a clashing table silently
        self.client.force_authenticate(self.dean)
        r = self.client.get("/api/engine/export-pdf/", {"program_id": self.prog.id, "semester": "1st Sem"})
        self.assertEqual(r.status_code, 409); self.assertEqual(r.data["total"], 1)
        r = self.client.get("/api/engine/export-pdf/", {"program_id": self.prog.id, "semester": "1st Sem", "allow_conflicts": 1})
        self.assertEqual(r.status_code, 200)                                 # printed only on purpose, marked NOT FINAL
        # Resolve never suggests a time that overlaps the students' other class
        moved = Schedule.objects.get(timeslot=half)
        opts = self.client.post("/api/engine/slot-options/", {"ids": [moved.id], "limit": 300}, format="json").data
        for o in opts["options"]:
            if o["day"] == "Mon":
                self.assertTrue(o["start"] >= "08:00" or o["end"] <= "07:00", o)

    def test_conflict_checker_fix_is_suggest_then_confirm(self):
        """The Conflict Checker pop-up: free times for ONE side, nothing saved until Apply, approved sides are flagged."""
        a = self.row()
        s = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))[0]
        b = Schedule.objects.create(subject=Subject.objects.get(code="TST102"), section=self.sec[1], teacher=self.teachers[2], room=a.room, timeslot=s)
        Schedule.objects.filter(pk=a.pk).update(status="approved")
        c = next(x for x in scan()["conflicts"] if x["kind"] == "room")
        sides = {tuple(x["ids"]): x for x in (c["a"], c["b"])}
        self.assertEqual((sides[(a.id,)]["status"], sides[(b.id,)]["status"]), ("approved", "draft"))
        self.assertFalse(sides[(b.id,)]["shared"])
        self.client.force_authenticate(self.dean)
        r = self.client.post("/api/engine/slot-options/", {"ids": [b.id]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["options"])
        self.assertEqual({o["room_id"] for o in r.data["options"]}, {a.room_id})       # same room first
        self.assertEqual(Schedule.objects.get(pk=b.pk).timeslot_id, s.id)              # looking changes nothing
        self.assertEqual(self.client.post("/api/engine/slot-options/", {"ids": [a.id]}, format="json").status_code, 403)   # approved: never moved
        done = self.client.post("/api/engine/slot-options/apply/", {"ids": [b.id], "key": r.data["options"][0]["key"]}, format="json")
        self.assertEqual(done.status_code, 200, done.data)
        self.assertEqual(scan()["total"], 0)
        self.assertEqual(Schedule.objects.get(pk=a.pk).timeslot_id, a.timeslot_id)    # the approved class stayed

    def test_scan_finds_and_resolver_fixes_each_kind(self):
        a = self.row()
        # overlapping but not identical slots slip past the exact-slot DB rule: that is what the report is for
        s = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))[0]
        Schedule.objects.create(subject=Subject.objects.get(code="TST101"), section=self.sec[1], teacher=a.teacher,
                                room=self.rooms[1], timeslot=s)
        Schedule.objects.create(subject=Subject.objects.get(code="TST102"), section=self.sec[1], teacher=self.teachers[2],
                                room=a.room, timeslot=TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 15), end_time=dtime(8, 15))[0])
        rep = scan()
        self.assertGreaterEqual(rep["total"], 2)
        out = resolve_all(self.dean)
        self.assertEqual(out["remaining"], 0, out)
        self.assertEqual(scan()["total"], 0)

    def _clash(self):
        a = self.row()
        s = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))[0]
        b = Schedule.objects.create(subject=Subject.objects.get(code="TST101"), section=self.sec[1], teacher=a.teacher,
                                    room=self.rooms[1], timeslot=s)
        return a, b

    def _pair(self, a, b):
        c = next(x for x in scan()["conflicts"] if x["kind"] == "teacher")
        return {"kind": c["kind"], "a_ids": c["a"]["ids"], "b_ids": c["b"]["ids"]}

    def test_resolve_one_conflict_through_the_api_and_a_stale_one_is_not_redone(self):
        a, b = self._clash()
        body = self._pair(a, b)
        self.client.force_authenticate(self.dean)
        r = self.client.post("/api/engine/conflicts/resolve/", body, format="json")
        self.assertTrue(r.data["ok"], r.data)
        self.assertEqual(scan()["total"], 0)
        before = list(Schedule.objects.order_by("id").values_list("id", "teacher_id", "room_id", "timeslot_id"))
        again = self.client.post("/api/engine/conflicts/resolve/", body, format="json")
        self.assertTrue(again.data["ok"])
        self.assertIn("already gone", again.data["summary"])
        self.assertEqual(before, list(Schedule.objects.order_by("id").values_list("id", "teacher_id", "room_id", "timeslot_id")))

    def test_a_clash_between_classes_you_may_not_change_names_the_owners_and_notifies_them(self):
        from notifications.models import Notification
        a, b = self._clash()
        Schedule.objects.filter(pk=b.pk).update(status="approved")
        Schedule.objects.filter(pk=a.pk).update(status="approved")
        body = self._pair(a, b)
        self.client.force_authenticate(self.registrar)               # the Registrar owns Gen Ed only; these are program subjects
        r = self.client.post("/api/engine/conflicts/resolve/", body, format="json")
        self.assertFalse(r.data["ok"])
        self.assertIn("belongs to the Dean of", r.data["summary"])
        self.assertIn("approved or published", r.data["summary"])
        self.assertTrue(Notification.objects.filter(recipient=self.dean, notif_type="conflict_alert").exists())

    def test_merged_classes_do_not_count_as_conflicts(self):
        self.row(merge="M1")
        self.row(sec=self.sec[1], merge="M1")
        self.assertEqual(scan()["total"], 0)

    def test_conflict_endpoints_need_the_right_role(self):
        self.client.force_authenticate(self.teachers[0].user)
        self.assertEqual(self.client.get("/api/engine/conflicts/").status_code, 403)
        self.assertEqual(self.client.post("/api/engine/conflicts/resolve/", {"all": True}, format="json").status_code, 403)


class EmptyTableSmokeTests(Base):
    """With no schedules at all (e.g. right after 'delete all') nothing may crash: every read returns 200 (or a clear 4xx)."""

    def test_reads_work_with_empty_schedule_table(self):
        self.assertEqual(Schedule.objects.count(), 0)
        urls = ["/api/engine/schedules/", "/api/engine/conflicts/", "/api/engine/workload/", "/api/engine/logs/",
                "/api/engine/conflict-logs/", "/api/engine/timeslots/", "/api/engine/sections/", "/api/analytics/",
                f"/api/engine/export-pdf/?program_id={self.prog.id}&year_level=1st%20Year&semester=1st%20Sem",
                "/api/engine/export-pdf/"]
        for user in (self.dean, self.registrar):
            self.client.force_authenticate(user)
            for u in urls:
                r = self.client.get(u)
                self.assertLess(r.status_code, 500, (user.username, u, r.status_code))

    def test_malformed_requests_never_500(self):
        self.client.force_authenticate(self.dean)
        for u, body in (("/api/engine/reschedule/", {}), ("/api/engine/reschedule/", {"items": [{"ids": [99999], "day": "Mon", "start_time": "07:00"}]}),
                        ("/api/engine/reschedule/", {"items": [{"ids": [1], "day": "Xyz"}]}),
                        ("/api/engine/conflicts/resolve/", {}), ("/api/engine/conflicts/resolve/", {"kind": "teacher", "a_ids": [1], "b_ids": [2]}),
                        ("/api/engine/replacements/assign/", {}), ("/api/engine/conflicts/demo/", {"action": "add"}),
                        ("/api/engine/conflicts/demo/", {"action": "remove"})):
            r = self.client.post(u, body, format="json")
            self.assertLess(r.status_code, 500, (u, body, r.status_code, getattr(r, "data", "")))


class MinorBatchTests(Base):
    """Generate All Minor Schedules for CCS / RadTech / Nursing / BAComm."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.progs = {}
        for label, name, dept, n in (("CCS", "BS Computer Science", "Computer Studies", 10), ("RadTech", "BS Radiologic Technology", "Radiologic Technology", 11),
                                     ("Nursing", "BS Nursing", "Nursing", 14), ("BAComm", "BA Communication", "College of Arts and Science", 12)):
            p = Program.objects.get_or_create(name=name, defaults={"department": dept})[0]
            Section.objects.create(name=f"{label}1", program=p, year_level="1st Year", semester="1st Sem", student_count=n)
            cls.progs[label] = p
            for code, title, units in (("GE901", "Understanding the Self", 3), ("GE902", "Purposive Communication", 3), ("GE903", "Filipino Christian Living 1", 3 if label == "Nursing" else 2)):
                Subject.objects.create(code=code, title=title, program=p, lec_units=units, lab_units=0, year_level="1st Year",
                                       semester="1st Sem", classification="minor")
            Subject.objects.create(code=f"{label}M101", title=f"{label} Major", program=p, lec_units=3, lab_units=0,
                                   year_level="1st Year", semester="1st Sem", classification="major")
        for i in range(10):
            make_teacher(100 + i)
            make_cas_teacher(300 + i)                                      # Gen Ed teachers (College of Arts and Science rule)
        for i in range(5, 9):
            Room.objects.create(name=f"M-10{i}", capacity=40, room_type="lecture")

    def go(self, user=None, **over):
        self.client.force_authenticate(user or self.registrar)
        body = {"school_year": SY, "semester": "1st Sem", "year_level": "1st Year"}
        body.update(over)
        return self.client.post("/api/engine/minor/generate-all/", body, format="json")

    def test_generates_validates_and_groups(self):
        r = self.go()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["validated"])
        self.assertEqual(r.data["conflicts_after"], 0)
        self.assertTrue({"CCS", "RadTech", "Nursing", "BAComm"} <= set(r.data["departments"]))
        self.assertGreater(r.data["groups"]["actually_shared"], 0)
        self.assertEqual(scan()["total"], 0)

    def test_equivalence_uses_units_so_fcl_with_different_units_is_not_merged(self):
        self.go()
        cmp = self.client.get("/api/engine/minor/comparison/?semester=1st%20Sem&year_level=1st%20Year").data
        fcl = [g for g in cmp["groups"] if g["code"] == "GE903"]
        self.assertEqual(len(fcl), 2)                                   # 2-unit group and the 3-unit Nursing group
        nursing = next(g for g in fcl if g["departments"] == ["Nursing"])
        self.assertEqual(nursing["mode"], "separate")
        self.assertEqual(nursing["cells"][0]["shared_with"], [])
        shared = next(g for g in fcl if "Nursing" not in g["departments"])
        self.assertIn(shared["mode"], ("shared", "mixed"))

    def test_too_many_students_stay_in_separate_sections(self):
        Section.objects.filter(program=self.progs["Nursing"]).update(student_count=59)
        Section.objects.filter(program=self.progs["CCS"]).update(student_count=59)
        r = self.go()
        self.assertEqual(r.status_code, 201, r.data)
        cmp = self.client.get("/api/engine/minor/comparison/?semester=1st%20Sem").data
        for g in cmp["groups"]:
            for c in g["cells"]:
                if c["students"] == 59:
                    self.assertEqual(c["shared_with"], [])
        self.assertTrue(r.data["validated"])
        Section.objects.filter(program=self.progs["Nursing"]).update(student_count=14)
        Section.objects.filter(program=self.progs["CCS"]).update(student_count=10)

    def test_rerun_has_no_duplicates_and_all_year_levels_works(self):
        self.go()
        n = Schedule.objects.count()
        r = self.go()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Schedule.objects.count(), n)
        self.assertEqual(r.data["replaced_rows"], n)
        self.assertEqual(self.go(year_level="All").status_code, 201)
        self.assertEqual(Schedule.objects.count(), n)

    def test_major_subjects_are_untouched(self):
        self.gen()                                                       # the existing Dean generation for BS Test
        major_ids = set(Schedule.objects.values_list("id", flat=True))
        self.go()
        self.assertTrue(major_ids <= set(Schedule.objects.values_list("id", flat=True)))
        self.assertEqual(scan()["total"], 0)

    def test_locked_classes_refuse_and_change_nothing(self):
        self.go()
        Schedule.objects.update(status="approved")
        n = Schedule.objects.count()
        r = self.go()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Schedule.objects.count(), n)

    def test_invalid_schedule_is_rolled_back_not_kept(self):
        from unittest import mock
        fake = {"total": 1, "counts": {"teacher": 1}, "conflicts": [{"kind": "teacher"}], "checked": 1}
        real = scan
        with mock.patch("engine.minor_batch.scan", side_effect=lambda **kw: fake if kw.get("involving_ids") else real(**kw)):
            r = self.go()
        self.assertEqual(r.status_code, 422, getattr(r, "data", ""))
        self.assertTrue(r.data["blocked"])
        self.assertEqual(Schedule.objects.filter(subject__classification="minor").count(), 0)

    def test_only_registrar_and_bad_input(self):
        self.assertEqual(self.go(user=self.dean).status_code, 403)
        for over in ({"school_year": ""}, {"year_level": "9th Year"}, {"semester": ""}):
            r = self.go(**over)
            self.assertEqual(r.status_code, 400, over)
            self.assertIn("detail", r.data)


class StaffCommandTests(Base):
    def test_adds_teachers_without_deans_and_is_idempotent(self):
        from django.core.management import call_command
        from io import StringIO
        deans = User.objects.filter(faculty_type="dean").count()
        Program.objects.create(name="BS Nursing", department="Nursing")
        call_command("add_department_staff", stdout=StringIO())
        self.assertEqual(User.objects.filter(faculty_type="dean").count(), deans)
        nurse_ft = User.objects.filter(department="Nursing", faculty_type="full_time").count()
        nurse_pt = User.objects.filter(department="Nursing", faculty_type="part_time").count()
        self.assertGreaterEqual(nurse_ft, 14); self.assertGreaterEqual(nurse_pt, 12)
        for d in ("Radiologic Technology", "College of Arts and Science", "Computer Studies"):
            self.assertGreaterEqual(User.objects.filter(department=d, faculty_type="full_time").count(), 6)
        total = User.objects.count()
        call_command("add_department_staff", stdout=StringIO())
        self.assertEqual(User.objects.count(), total)
        names = [(u.first_name, u.last_name) for u in User.objects.filter(role="faculty")]
        self.assertEqual(len(names), len(set(names)))


class MinorAllDepartmentsTests(MinorBatchTests):
    """Same checks with Allied Health, IHM and BA (CBA) programs added to the four original departments."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for label, name, dept, n in (("AH", "BS Physical Therapy", "Allied Health", 9), ("IHM", "BS Hospitality Management", "College of International Hospitality Management", 13),
                                     ("CBA", "BSBA Major in Marketing Management", "College of Business Administration", 11)):
            p = Program.objects.create(name=name, department=dept)
            Section.objects.create(name=f"{label}1", program=p, year_level="1st Year", semester="1st Sem", student_count=n)
            for code, title, units in (("GE901", "Understanding the Self", 3), ("GE902", "Purposive Communication", 3), ("GE903", "Filipino Christian Living 1", 2)):
                Subject.objects.create(code=code, title=title, program=p, lec_units=units, lab_units=0, year_level="1st Year",
                                       semester="1st Sem", classification="minor")

    def test_labels(self):
        from engine.minor_batch import dept_label
        got = {p.name: dept_label(p) for p in Program.objects.all()}
        self.assertEqual(got["BS Physical Therapy"], "Allied Health")
        self.assertEqual(got["BS Hospitality Management"], "IHM")
        self.assertEqual(got["BSBA Major in Marketing Management"], "CBA")
        self.assertEqual(got["BA Communication"], "BAComm")

    def test_seven_departments_generate_validated(self):
        r = self.go()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(set(r.data["departments"]), {"CCS", "RadTech", "Nursing", "BAComm", "Allied Health", "IHM", "CBA"})
        self.assertTrue(r.data["validated"])
        self.assertEqual(scan()["total"], 0)
        self.assertIn("capacity_warnings", r.data)

    def test_oversized_section_is_reported_not_hidden(self):
        Section.objects.filter(program=self.progs["Nursing"]).update(student_count=99)
        r = self.go()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(any(w["students"] > w["capacity"] for w in r.data["capacity_warnings"]))
        self.assertEqual(scan()["total"], 0)
        Section.objects.filter(program=self.progs["Nursing"]).update(student_count=14)


class UnplacedResolveTests(Base):
    """Classes the generator could not place are listed and placed from the dashboard -- by re-arranging what blocks them."""

    def _unplaced(self, user=None, **q):
        self.client.force_authenticate(user or self.dean)
        return self.client.get("/api/engine/unplaced/", {"semester": "1st Sem", **q})

    def _resolve(self, user=None, **body):
        self.client.force_authenticate(user or self.dean)
        return self.client.post("/api/engine/unplaced/resolve/", {"semester": "1st Sem", "school_year": SY, **body}, format="json")

    def test_missing_class_is_listed_and_placed(self):
        self.gen()
        Schedule.objects.filter(section=self.sec[0], subject__code="TST100").delete()
        r = self._unplaced()
        self.assertEqual(r.status_code, 200)
        self.assertEqual([(i["section_id"], i["subject"][:6]) for i in r.data["items"]], [(self.sec[0].id, "TST100")])
        out = self._resolve(section_id=self.sec[0].id)
        self.assertEqual(out.status_code, 200, out.data)
        self.assertEqual((out.data["placed"], out.data["remaining"]), (1, 0))
        self.assertEqual(self._unplaced().data["total"], 0)
        self.assertEqual(scan()["total"], 0)

    def test_lab_blocked_by_lectures_is_placed_by_moving_them(self):
        lab = Room.objects.create(name="Lab X", capacity=40, room_type="lab", department=DEPT)
        lab_subject = Subject.objects.create(code="LAB100L", title="Test Lab", program=self.prog, lec_units=0, lab_units=1,
                                             year_level="1st Year", semester="1st Sem", classification="major")
        Schedule.objects.all().delete()
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):               # Lab X is taken all week by a LECTURE of section B
            for h in range(7, 20):
                self.row(sec=self.sec[1], room=lab, day=d, h=h, subj=1)
        self.assertEqual(len([i for i in self._unplaced().data["items"] if i["subject"].startswith("LAB100L")]), 2)
        before = scan()["total"]
        out = self._resolve(section_id=self.sec[0].id, subject_id=lab_subject.id)
        self.assertEqual(out.status_code, 200, out.data)
        res = out.data["results"][0]
        self.assertEqual(res["status"], "placed", res)
        self.assertTrue(res["moved"])                                # the lecture was moved to a lecture room
        placed = Schedule.objects.filter(section=self.sec[0], subject=lab_subject)
        self.assertEqual(placed.count(), 3)
        self.assertEqual({r.room_id for r in placed}, {lab.id})
        self.assertEqual(scan()["total"], before)                    # no clash was created

    def test_approved_classes_are_never_moved(self):
        self.gen()
        Schedule.objects.filter(section=self.sec[0], subject__code="TST100").delete()
        Schedule.objects.update(status="approved")
        snapshot = list(Schedule.objects.order_by("id").values_list("id", "timeslot_id", "room_id", "teacher_id"))
        out = self._resolve(section_id=self.sec[0].id)
        self.assertEqual(out.status_code, 200)
        self.assertEqual(snapshot, [t for t in Schedule.objects.order_by("id").values_list("id", "timeslot_id", "room_id", "teacher_id")
                                    if t[0] in {s[0] for s in snapshot}])

    def test_other_roles_are_refused(self):
        self.assertEqual(self._unplaced(user=self.teachers[0].user).status_code, 403)
        self.assertEqual(self._resolve(user=self.teachers[0].user).status_code, 403)

    def test_registrar_cannot_place_a_major_class(self):
        self.gen()
        Schedule.objects.filter(section=self.sec[0], subject__code="TST100").delete()
        out = self._resolve(user=self.registrar, section_id=self.sec[0].id)
        self.assertEqual(out.status_code, 200)
        self.assertEqual(out.data["requested"], 0)                  # majors are not in the Registrar's scope


class GenerationLockTests(APITestCase):
    """engine.locks: overlapping generations are refused, and database waits/timeouts get readable text."""

    def test_try_lock_is_reentrant_and_noop_off_postgres(self):
        from django.db import transaction
        from . import locks
        with transaction.atomic():
            self.assertTrue(locks.try_lock("classes"))
            self.assertTrue(locks.try_lock("classes"))     # same session: nested generation calls keep working

    def test_explain_maps_timeouts_only(self):
        from django.db import OperationalError
        from . import locks
        self.assertEqual(locks.explain(OperationalError("canceling statement due to statement timeout")), locks.STUCK)
        self.assertEqual(locks.explain(OperationalError("canceling statement due to lock timeout")), locks.STUCK)
        self.assertIsNone(locks.explain(ValueError("statement timeout")))
        self.assertIsNone(locks.explain(OperationalError("no such table")))


class OverloadResolveTests(Base):
    """Dean: overloaded teachers get qualified / available / free suggestions, and Assign changes the real schedule."""

    def setUp(self):
        from engine.models import SchedulingConfig
        cfg = SchedulingConfig.get_solo()
        cfg.max_weekly_hours_full_time = 2
        cfg.max_weekly_hours_part_time = 2
        cfg.save()
        self.field = AcademicField.objects.create(name="Test Field")
        Subject.objects.filter(program=self.prog).update(field=self.field)
        self.t = self.teachers
        for p in (self.t[0], self.t[1], self.t[3]):
            p.specializations.add(self.field)               # qualified
        # t[2] is NOT qualified; t[3] is qualified but teaching on Mon 7-8 already
        self.rows = [self.row(subj=0, h=7), self.row(subj=1, h=8), self.row(subj=2, h=9)]   # t[0]: 3 h > 2 h limit
        self.row(sec=self.sec[1], teacher=self.t[3], room=self.rooms[1], subj=3, h=9)
        self.client.force_authenticate(self.dean)

    def plan(self):
        return self.client.get("/api/engine/workload/overload-plan/").data

    def test_plan_names_the_overload_and_only_qualified_free_people(self):
        d = self.plan()
        item = next(i for i in d["items"] if i["faculty_id"] == self.t[0].id)
        self.assertAlmostEqual(item["overload_hours"], 1.0)
        rec = [c for c in item["classes"] if c["recommended"]]
        self.assertEqual(len(rec), 1)
        ids = {s["faculty_id"] for s in rec[0]["suggestions"]}
        self.assertIn(self.t[1].id, ids)
        self.assertNotIn(self.t[2].id, ids)                           # not qualified
        for s in rec[0]["suggestions"]:
            self.assertTrue(s["reasons"] and "max_hours" in s and s["fit"])

    def test_assign_validates_then_changes_the_real_schedule(self):
        rec = [c for c in next(i for i in self.plan()["items"] if i["faculty_id"] == self.t[0].id)["classes"] if c["recommended"]][0]
        body = lambda t: {"schedule_ids": rec["schedule_ids"], "teacher": t.id}
        url = "/api/engine/workload/overload-assign/"
        r = self.client.post(url, body(self.t[2]), format="json")
        self.assertEqual(r.status_code, 422, r.data)                  # unqualified
        self.assertIn("not qualified", r.data["detail"])
        r = self.client.post(url, body(self.t[1]), format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(all(c["ok"] for c in r.data["checks"]), r.data["checks"])
        self.assertEqual(Schedule.objects.get(pk=rec["schedule_ids"][0]).teacher_id, self.t[1].id)
        self.assertEqual(self.plan()["overloaded"], 0)                # warnings update from the new state
        self.assertEqual(scan()["total"], 0)

    def test_busy_and_over_limit_people_are_refused(self):
        rec = [c for c in next(i for i in self.plan()["items"] if i["faculty_id"] == self.t[0].id)["classes"] if c["recommended"]][0]
        slot_id = Schedule.objects.get(pk=rec["schedule_ids"][0]).timeslot_id
        Schedule.objects.create(subject=Subject.objects.get(code="TST104"), section=self.sec[1], teacher=self.t[3], room=self.rooms[2],
                                timeslot_id=slot_id)                  # t[3] now busy exactly then
        r = self.client.post("/api/engine/workload/overload-assign/", {"schedule_ids": rec["schedule_ids"], "teacher": self.t[3].id}, format="json")
        self.assertEqual(r.status_code, 422, r.data)
        for h, subj in ((14, 4), (15, 5)):                            # t[1] fills their 2 h limit
            self.row(sec=self.sec[1], teacher=self.t[1], room=self.rooms[3], subj=subj, h=h, day="Tue")
        r = self.client.post("/api/engine/workload/overload-assign/", {"schedule_ids": rec["schedule_ids"], "teacher": self.t[1].id}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(Schedule.objects.get(pk=rec["schedule_ids"][0]).teacher_id, self.t[0].id)     # nothing changed

    def test_approved_classes_are_never_moved_and_the_plan_says_why(self):
        Schedule.objects.filter(pk__in=[r.id for r in self.rows]).update(status="approved")
        item = next(i for i in self.plan()["items"] if i["faculty_id"] == self.t[0].id)
        self.assertFalse(item["solvable"])
        self.assertTrue(any("cannot change" in n or "None of this teacher" in n for n in item["notes"]), item["notes"])
        r = self.client.post("/api/engine/workload/overload-assign/", {"schedule_ids": [self.rows[0].id], "teacher": self.t[1].id}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_no_qualified_teacher_gives_a_clear_reason(self):
        for p in (self.t[1], self.t[3]):
            p.specializations.clear()
        item = next(i for i in self.plan()["items"] if i["faculty_id"] == self.t[0].id)
        rec = [c for c in item["classes"] if c["recommended"]][0]
        self.assertEqual(rec["suggestions"], [])
        self.assertIn("No faculty member is qualified", rec["reason_none"])
        self.assertFalse(item["solvable"])

    def test_others_cannot_use_it(self):
        self.client.force_authenticate(self.t[1].user)
        self.assertEqual(self.client.get("/api/engine/workload/overload-plan/").status_code, 403)

    def test_a_teacher_from_another_college_on_the_deans_classes_is_still_warned_about(self):
        outsider = make_teacher(9)
        User.objects.filter(pk=outsider.user_id).update(department="Culinary Arts")
        for h in (10, 11, 12):                                    # 3 h on this Dean's program subjects, limit is 2 h
            self.row(sec=self.sec[1], teacher=outsider, room=self.rooms[2], subj=h - 7 if h - 7 < 6 else 5, h=h, day="Wed")
        names = {i["faculty_id"] for i in self.client.get("/api/engine/workload/overload-summary/").data["items"]}
        self.assertIn(outsider.id, names)
        item = next(i for i in self.plan()["items"] if i["faculty_id"] == outsider.id)
        self.assertTrue(item["subjects"] and all("hours" in s for s in item["subjects"]))
        self.assertTrue(any(c["recommended"] for c in item["classes"]))

    def test_summary_lists_the_assigned_subjects_and_the_excess(self):
        it = next(i for i in self.client.get("/api/engine/workload/overload-summary/").data["items"] if i["faculty_id"] == self.t[0].id)
        self.assertAlmostEqual(it["overload_hours"], 1.0)
        self.assertEqual(len(it["subjects"]), 3)

    def test_candidates_carry_their_availability_text(self):
        item = next(i for i in self.plan()["items"] if i["faculty_id"] == self.t[0].id)
        s = [c for c in item["classes"] if c["recommended"]][0]["suggestions"][0]
        self.assertTrue(s["availability"])


class CcsFirstAndLibraryTests(MinorAllDepartmentsTests):
    """Computer Studies minors merge CS + IT first, other departments only take the seats that remain; the Library is a last resort."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        it = Program.objects.create(name="BS Information Technology", department="Computer Studies")
        Section.objects.create(name="IT1", program=it, year_level="1st Year", semester="1st Sem", student_count=12)
        for code, title, units in (("GE901", "Understanding the Self", 3), ("GE902", "Purposive Communication", 3), ("GE903", "Filipino Christian Living 1", 2)):
            Subject.objects.create(code=code, title=title, program=it, lec_units=units, lab_units=0, year_level="1st Year",
                                   semester="1st Sem", classification="minor")
        Room.objects.create(name="M-LIBRARY", label="Library", capacity=40, room_type="lecture")

    def test_cs_and_it_share_first_and_others_fill_the_remaining_seats(self):
        from engine.minor_batch import plan_groups, target_programs
        _sizes, bins, order = plan_groups(target_programs(), ["1st Year"], "1st Sem")
        names = [p.name for p in order]
        ccs = [n for n in names if n in ("BS Computer Science", "BS Information Technology", "BS CS Test")]
        self.assertEqual(names[:len(ccs)], ccs)                        # every Computer Studies program comes before every other department
        r = self.go()
        self.assertEqual(r.status_code, 201, r.data)
        cmp = self.client.get("/api/engine/minor/comparison/?semester=1st%20Sem&year_level=1st%20Year").data
        g = next(x for x in cmp["groups"] if x["code"] == "GE901")
        cs = next(c for c in g["cells"] if c["program"] == "BS Computer Science")
        self.assertTrue(any("IT1" in w for w in cs["shared_with"]), cs["shared_with"])

    def test_with_limited_seats_cs_and_it_fill_the_room_before_any_other_department(self):
        Room.objects.filter(room_type="lecture").update(capacity=30)   # CS 10 + IT 12 = 22; only 8 seats left, no other department fits
        r = self.go()
        self.assertEqual(r.status_code, 201, r.data)
        cmp = self.client.get("/api/engine/minor/comparison/?semester=1st%20Sem&year_level=1st%20Year").data
        g = next(x for x in cmp["groups"] if x["code"] == "GE901")
        cs = next(c for c in g["cells"] if c["program"] == "BS Computer Science")
        self.assertEqual([w.split()[-1] for w in cs["shared_with"]], ["IT1"], cs["shared_with"])

    def test_the_library_is_not_used_while_a_classroom_is_free(self):
        self.go()
        lib = Room.objects.get(name="M-LIBRARY")
        self.assertEqual(Schedule.objects.filter(room=lib, subject__classification="minor").count(), 0)


class PreviewChoicesTests(Base):
    """Room / Start / End picked per subject in the curriculum preview are honoured, validated and explained."""

    def _sub(self):
        return Subject.objects.get(code="TST100")

    def test_chosen_room_and_time_window_are_used(self):
        sub = self._sub()
        room = self.rooms[2]
        r = self.gen(room_choices={str(sub.id): room.id}, time_windows={str(sub.id): {"start": "13:00", "end": "17:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        rows = Schedule.objects.filter(subject=sub).select_related("timeslot")
        self.assertTrue(rows.exists())
        self.assertEqual({x.room_id for x in rows}, {room.id})
        for x in rows:
            self.assertGreaterEqual(x.timeslot.start_time, dtime(13, 0))
            self.assertLessEqual(x.timeslot.end_time, dtime(17, 0))
        self.assertEqual(scan()["total"], 0)

    def test_room_choices_endpoint_lists_rooms_for_the_preview(self):
        for who in (self.dean, self.registrar):
            self.client.force_authenticate(who)
            r = self.client.get("/api/rooms/preview-choices/")
            self.assertEqual(r.status_code, 200, getattr(r, "data", None))
            self.assertTrue(len(r.data["rooms"]) >= 1)
        self.client.force_authenticate(self.teachers[0].user)
        self.assertEqual(self.client.get("/api/rooms/preview-choices/").status_code, 403)
        self.client.force_authenticate(self.dean)
        r = self.client.get("/api/rooms/preview-choices/")
        self.assertTrue(len(r.data["rooms"]) >= 1)
        self.assertTrue(all("id" in x and "capacity" in x for x in r.data["rooms"]))

    def test_bad_choices_are_rejected_before_anything_is_saved(self):
        sub = self._sub()
        lab = Room.objects.create(name="LAB-X", capacity=40, room_type="lab")
        for body in ({"time_windows": {str(sub.id): {"start": "15:00", "end": "09:00"}}},
                     {"room_choices": {str(sub.id): lab.id}},
                     {"room_choices": {str(sub.id): 999999}}):
            r = self.gen(**body)
            self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(Schedule.objects.count(), 0)

    def test_a_window_nothing_fits_in_is_reported_with_the_reason(self):
        sub = self._sub()
        r = self.gen(time_windows={str(sub.id): {"start": "07:00", "end": "07:30"}})
        self.assertEqual(r.status_code, 400, r.data)               # told before anything runs
        self.assertIn("unbroken", r.data["detail"])
        self.assertFalse(Schedule.objects.filter(subject=sub).exists())


class ComputerLabsAvailableTests(Base):
    """Comp Lab C and D are always selectable in the Room dropdown; existing records are reused, never duplicated."""

    def _run(self):
        import importlib
        from django.apps import apps
        mod = importlib.import_module("rooms.migrations.0005_ensure_computer_labs_c_d")
        mod.ensure(apps, None)

    def test_created_once_when_missing_and_listed_for_the_computer_studies_dean(self):
        from rooms.rules import room_key
        self._run(); self._run()
        names = [room_key(r.label) for r in Room.objects.filter(label__startswith="Comp Lab")]
        self.assertEqual(sorted(names), ["COMPLABC", "COMPLABD"])
        self.client.force_authenticate(self.dean)
        rooms = self.client.get("/api/rooms/preview-choices/").data["rooms"]
        got = {room_key(r["name"]) for r in rooms if r["room_type"] == "lab"}
        self.assertTrue({"COMPLABC", "COMPLABD"} <= got, got)
        self.assertTrue(all(r["capacity"] for r in rooms))

    def test_an_existing_record_under_another_spelling_is_reused(self):
        Room.objects.create(name="D-307", building="D", room_number="307", label="", capacity=35, room_type="lab")
        Room.objects.create(name="Computer Lab D", building="", room_number="", label="Computer Lab D", capacity=28, room_type="lab")
        before = Room.objects.count()
        self._run()
        self.assertEqual(Room.objects.count(), before)
        self.assertEqual(Room.objects.get(name="D-307").capacity, 35)

    def test_registrar_list_includes_the_labs_too(self):
        self._run()
        self.client.force_authenticate(self.registrar)
        names = [r["name"] for r in self.client.get("/api/rooms/preview-choices/").data["rooms"]]
        self.assertIn("Comp Lab C", names); self.assertIn("Comp Lab D", names)


class OwnedLabForLectureTests(Base):
    def test_a_lecture_subject_may_pick_its_own_departments_lab_but_not_a_shared_lab(self):
        sub = Subject.objects.get(code="TST100")
        own = Room.objects.create(name="Comp Lab C", building="D", room_number="307", label="Comp Lab C", capacity=40, room_type="lab", department=DEPT)
        other = Room.objects.create(name="LAB-S", capacity=40, room_type="lab")
        self.assertEqual(self.gen(room_choices={str(sub.id): other.id}).status_code, 400)
        r = self.gen(room_choices={str(sub.id): own.id})
        self.assertEqual(r.status_code, 201, r.data)


class RoomRecordsAdminOnlyTests(Base):
    def setUp(self):
        self.admin = User(username="itadmin", school_id="IA", role="admin")
        self.admin.set_password("pw"); self.admin.save()

    def test_only_the_admin_can_create_edit_or_delete_room_records(self):
        body = {"building": "D", "room_number": "311", "capacity": 35, "room_type": "lecture", "equipment": "", "department": ""}
        for who in (self.dean, self.registrar):
            self.client.force_authenticate(who)
            self.assertEqual(self.client.post("/api/rooms/admin/rooms/", body, format="json").status_code, 403)
            self.assertEqual(self.client.post("/api/rooms/dean/rooms/", body, format="json").status_code, 403)
            self.assertEqual(self.client.post("/api/rooms/", {"name": "X", "capacity": 10, "room_type": "lecture"}, format="json").status_code, 403)
            self.assertEqual(self.client.delete(f"/api/rooms/{self.rooms[0].id}/").status_code, 403)
            self.assertEqual(self.client.patch(f"/api/rooms/dean/rooms/{self.rooms[0].id}/", {"capacity": 5}, format="json").status_code, 403)
            self.assertEqual(self.client.get("/api/rooms/").status_code, 200)         # dropdowns still read the records
        self.assertEqual(Room.objects.get(pk=self.rooms[0].id).capacity, 60)

    def test_admin_adds_edits_and_cannot_delete_a_room_with_classes(self):
        self.client.force_authenticate(self.admin)
        body = {"building": "D", "room_number": "311", "capacity": 35, "room_type": "lab", "equipment": "PCs", "department": DEPT, "label": "Comp Lab Z"}
        r = self.client.post("/api/rooms/admin/rooms/", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        rid = r.data["id"]
        self.assertEqual(self.client.post("/api/rooms/admin/rooms/", body, format="json").status_code, 400)       # duplicate
        r = self.client.patch(f"/api/rooms/admin/rooms/{rid}/", {"capacity": 42}, format="json")
        self.assertEqual((r.status_code, r.data["capacity"]), (200, 42))
        self.assertTrue(any(x["id"] == rid for x in self.client.get("/api/rooms/admin/rooms/").data["rooms"]))
        self.assertEqual(self.client.delete(f"/api/rooms/admin/rooms/{rid}/").status_code, 204)
        used = self.rooms[0]
        self.row(room=used)
        self.assertEqual(self.client.delete(f"/api/rooms/admin/rooms/{used.id}/").status_code, 409)
        self.assertTrue(Room.objects.filter(pk=used.id).exists())

    def test_dean_still_chooses_rooms_and_sets_subject_preferences(self):
        self.client.force_authenticate(self.dean)
        self.assertEqual(self.client.get("/api/rooms/preview-choices/").status_code, 200)
        o = self.client.get("/api/rooms/dean/overview/")
        self.assertEqual(o.status_code, 200)
        self.assertEqual(o.data["subjects"], [])                                       # nothing until a program is chosen
        o = self.client.get("/api/rooms/dean/overview/", {"program_id": self.prog.id})
        self.assertTrue(len(o.data["subjects"]) > 0)


class DashboardStatsTests(Base):
    """Home numbers come from the database on every call and fall back to zero once the schedules are gone."""

    def stats(self, who):
        self.client.force_authenticate(who)
        r = self.client.get("/api/engine/dashboard-stats/")
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        self.assertEqual(r["Cache-Control"], "no-store")
        return r.data

    def test_counts_follow_the_schedules_through_partial_and_full_deletion(self):
        from notifications.models import Notification
        a = self.row(subj=0, h=7)
        b = self.row(subj=1, h=8, sec=self.sec[1], teacher=self.teachers[1], room=self.rooms[1])
        c = self.row(subj=2, h=9, sec=self.sec[1], teacher=self.teachers[2], room=self.rooms[2])
        odd, _ = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))
        Schedule.objects.create(subject=Subject.objects.get(code="TST103"), section=self.sec[0], teacher=self.teachers[0], room=self.rooms[3],
                                timeslot=odd)                                  # overlaps `a` (same teacher and section): a real conflict
        Schedule.objects.filter(pk=c.pk).update(status="approved")
        Schedule.objects.filter(pk=b.pk).update(status="published")
        ConflictLog.objects.create(conflict_type="teacher_double_booking", description="old", section=self.sec[0])
        ConflictLog.objects.create(conflict_type="teacher_double_booking", description="old2", section=self.sec[1])
        Notification.objects.create(recipient=self.dean, notif_type="schedule_update", message="Schedule changed")
        for who in (self.dean, self.registrar):
            s = self.stats(who)
            self.assertEqual((s["class_periods"], s["draft"], s["approved"], s["published"]), (4, 2, 1, 1))
            self.assertTrue(s["conflicts"] >= 1)
        # delete one row through the API (a Dean removes a period): counts follow immediately
        self.client.force_authenticate(self.dean)
        self.assertEqual(self.client.delete(f"/api/engine/schedules/{a.id}/").status_code, 204)
        s = self.stats(self.dean)
        self.assertEqual((s["class_periods"], s["draft"]), (3, 1))
        self.assertEqual(s["conflicts"], 0)                                   # the clash partner is gone: recomputed, not remembered
        # the remaining sections still have classes: their log lines stay, a section with no classes loses them
        Schedule.objects.filter(section=self.sec[0]).delete()
        from engine.housekeeping import cleanup_after_delete
        cleanup_after_delete()
        self.assertEqual(list(ConflictLog.objects.values_list("description", flat=True)), ["old2"])
        # clear everything
        Schedule.objects.all().delete()
        cleanup_after_delete()
        for who in (self.dean, self.registrar):
            s = self.stats(who)
            self.assertEqual((s["class_periods"], s["draft"], s["approved"], s["published"], s["conflicts"], s["overloaded"]), (0, 0, 0, 0, 0, 0))
        self.assertEqual(ConflictLog.objects.count(), 0)
        self.assertFalse(Notification.objects.filter(notif_type="schedule_update").exists())
        # permanent data is untouched
        self.assertEqual(Subject.objects.filter(program=self.prog).count(), 6)
        self.assertEqual(Room.objects.count() >= 4, True)
        self.assertEqual(len(self.teachers), 6)

    def test_admin_clear_resets_the_numbers_and_keeps_permanent_data(self):
        admin = User(username="adm2", school_id="AD2", role="admin"); admin.set_password("pw"); admin.save()
        self.row(subj=0, h=7); self.row(subj=1, h=8)
        self.client.force_authenticate(admin)
        r = self.client.post("/api/accounts/admin/clear-generated/", {"scope": "classes", "include_approved": True, "apply": True}, format="json")
        self.assertEqual((r.status_code, r.data["count"]), (200, 2))
        s = self.stats(self.dean)
        self.assertEqual((s["class_periods"], s["draft"], s["conflicts"], s["overloaded"]), (0, 0, 0, 0))
        self.assertEqual(Subject.objects.filter(program=self.prog).count(), 6)

    def test_teachers_cannot_read_the_dean_numbers(self):
        self.client.force_authenticate(self.teachers[0].user)
        self.assertEqual(self.client.get("/api/engine/dashboard-stats/").status_code, 403)


class SmartResolveTests(Base):
    """Resolve lists only real free days/times for the class's OWN room; Apply re-checks and changes nothing else."""

    def opts(self, row, user=None, **extra):
        self.client.force_authenticate(user or self.dean)
        return self.client.post("/api/engine/slot-options/", {"ids": [row.id], "limit": 300, **extra}, format="json")

    def test_options_keep_room_and_skip_busy_times(self):
        a = self.row(subj=0, h=7)
        self.row(subj=1, h=8, sec=self.sec[1], teacher=self.teachers[1])                # same ROOM busy Mon 8
        self.row(subj=2, h=9, sec=self.sec[1], teacher=self.teachers[0], room=self.rooms[1])   # same TEACHER busy Mon 9
        self.row(subj=3, h=10, sec=self.sec[0], teacher=self.teachers[2], room=self.rooms[2])  # same SECTION busy Mon 10
        r = self.opts(a)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["room"]["kept"]); self.assertEqual(r.data["room"]["name"], "N-101")
        got = {(o["day"], o["start"]) for o in r.data["options"]}
        for bad in (("Mon", "07:00"), ("Mon", "08:00"), ("Mon", "09:00"), ("Mon", "10:00")):
            self.assertNotIn(bad, got)
        self.assertIn(("Mon", "11:00"), got)
        self.assertTrue(all(o["room"] == "N-101" and o["teacher_id"] == self.teachers[0].id for o in r.data["options"]))

    def test_teacher_availability_is_respected(self):
        from engine import views as ev
        a = self.row(subj=0, h=7)
        real = ev._build_availability_rules
        blocked = TimeSlot.objects.get(day="Tue", start_time=dtime(9))
        ev._build_availability_rules = lambda t, ts, *a_, **k: {x.id: {blocked.id} for x in t}
        try:
            r = self.opts(a)
        finally:
            ev._build_availability_rules = real
        self.assertNotIn(("Tue", "09:00"), {(o["day"], o["start"]) for o in r.data["options"]})
        self.assertIn(("Tue", "10:00"), {(o["day"], o["start"]) for o in r.data["options"]})

    def test_apply_moves_only_this_class_and_keeps_room(self):
        a = self.row(subj=0, h=7)
        other = self.row(subj=1, h=8, sec=self.sec[1], teacher=self.teachers[1], room=self.rooms[1])
        key = next(o["key"] for o in self.opts(a).data["options"] if (o["day"], o["start"]) == ("Wed", "13:00"))
        r = self.client.post("/api/engine/slot-options/apply/", {"ids": [a.id], "key": key}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        row = Schedule.objects.get(subject__code="TST100")
        self.assertEqual((row.timeslot.day, row.timeslot.start_time, row.room_id), ("Wed", dtime(13), self.rooms[0].id))
        o2 = Schedule.objects.get(pk=other.pk)
        self.assertEqual((o2.timeslot_id, o2.room_id), (other.timeslot_id, other.room_id))
        self.assertEqual(scan()["total"], 0)

    def test_apply_refuses_a_time_taken_since_listing(self):
        a = self.row(subj=0, h=7)
        key = next(o["key"] for o in self.opts(a).data["options"] if (o["day"], o["start"]) == ("Thu", "09:00"))
        self.row(subj=1, h=9, day="Thu", sec=self.sec[1], teacher=self.teachers[1])      # someone takes the room
        r = self.client.post("/api/engine/slot-options/apply/", {"ids": [a.id], "key": key}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Schedule.objects.get(pk=a.pk).timeslot.start_time, dtime(7))

    def test_no_free_time_explains_and_never_switches_room(self):
        a = self.row(subj=0, h=7)
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in range(7, 20):
                if (d, h) != ("Mon", 7):
                    self.row(subj=1, h=h, day=d, sec=self.sec[1], teacher=self.teachers[1])      # room N-101 booked all week
        r = self.opts(a)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["options"], [])
        self.assertIn("N-101", r.data["reason"])
        # a major of a college without designated rooms MAY be offered other free rooms, flagged, never applied by itself
        self.assertTrue(r.data["room_change_allowed"])
        self.assertTrue(all(o["room_changed"] and o["room"] != "N-101" for o in r.data["room_options"]))
        self.assertEqual(Schedule.objects.get(pk=a.pk).room_id, self.rooms[0].id)

    def test_locked_or_foreign_classes_are_refused(self):
        a = self.row(subj=0, h=7)
        Schedule.objects.filter(pk=a.pk).update(status="approved")
        self.assertEqual(self.opts(a).status_code, 403)
        Schedule.objects.filter(pk=a.pk).update(status="draft")
        self.assertEqual(self.opts(a, user=self.registrar).status_code, 403)               # major subject: Dean's, not Registrar's

    def test_unplaced_class_uses_its_preferred_room(self):
        self.client.force_authenticate(self.dean)
        r = self.client.post("/api/engine/slot-options/", {"section_id": self.sec[0].id, "subject_id": Subject.objects.get(code="TST100").id,
                                                          "room_id": self.rooms[2].id}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["mode"], "place")
        self.assertTrue(r.data["options"] and all(o["room"] == "N-103" for o in r.data["options"]))
        key = r.data["options"][0]["key"]
        ap = self.client.post("/api/engine/slot-options/apply/", {"section_id": self.sec[0].id, "subject_id": Subject.objects.get(code="TST100").id,
                                                                "room_id": self.rooms[2].id, "key": key}, format="json")
        self.assertEqual(ap.status_code, 200, ap.data)
        self.assertEqual(scan()["total"], 0)


class GenerationRulesTests(Base):
    """Chosen room kept, other days searched, qualified faculty only, half-hour windows."""

    def _sub(self, i=0):
        return Subject.objects.get(code=f"TST10{i}")

    def test_chosen_room_is_kept_and_other_days_are_searched(self):
        sub = self._sub()
        # both sections need this subject in N-102 between 7:00 and 10:00 (a 3 h block): only ONE slot per day fits
        r = self.gen(room_choices={str(sub.id): self.rooms[1].id}, time_windows={str(sub.id): {"start": "07:00", "end": "10:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        rows = Schedule.objects.filter(subject=sub)
        self.assertEqual({x.room_id for x in rows}, {self.rooms[1].id})
        self.assertEqual({x.section_id for x in rows}, {self.sec[0].id, self.sec[1].id})
        self.assertEqual(len({x.timeslot.day for x in rows}), 2)            # same room, so the second section got ANOTHER day
        self.assertEqual(r.data["conflicts"], [])
        self.assertEqual(scan()["total"], 0)

    def test_room_is_not_swapped_when_it_is_full_inside_the_window(self):
        sub = self._sub()
        other = Program.objects.create(name="BS Other", department=DEPT)
        sec2 = Section.objects.create(name="O1A", program=other, year_level="2nd Year", semester="1st Sem", student_count=30)
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in (7, 8, 9):
                self.row(subj=1, day=d, h=h, sec=sec2, teacher=self.teachers[1], room=self.rooms[2])
        Schedule.objects.filter(section=sec2).update(status="approved")                # approved classes are never moved
        r = self.gen(room_choices={str(sub.id): self.rooms[2].id}, time_windows={str(sub.id): {"start": "07:00", "end": "10:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(Schedule.objects.filter(subject=sub).exists())               # never moved to another room instead
        self.assertTrue(r.data["conflicts"])
        self.assertEqual(scan()["total"], 0)

    def test_generate_does_not_move_other_draft_classes_and_suggests_free_times_in_the_chosen_room(self):
        sub = self._sub()
        other = Program.objects.create(name="BS Other", department=DEPT)
        sec2 = Section.objects.create(name="O1A", program=other, year_level="2nd Year", semester="1st Sem", student_count=30)
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in (7, 8, 9):                                                        # DRAFT classes fill N-103 7-10 every day
                self.row(subj=1, day=d, h=h, sec=sec2, teacher=self.teachers[1], room=self.rooms[2])
        before = list(Schedule.objects.filter(section=sec2).order_by("id").values_list("id", "timeslot_id", "room_id", "teacher_id"))
        r = self.gen(room_choices={str(sub.id): self.rooms[2].id}, time_windows={str(sub.id): {"start": "07:00", "end": "10:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        # nothing was re-arranged behind the Dean's back
        self.assertEqual(before, list(Schedule.objects.filter(section=sec2).order_by("id").values_list("id", "timeslot_id", "room_id", "teacher_id")))
        self.assertFalse(Schedule.objects.filter(subject=sub).exists())
        self.assertEqual(r.data["auto_resolved"], [])
        rows = [c for c in r.data["conflicts"] if c["subject_id"] == sub.id]
        self.assertEqual(len(rows), 2)                                                 # one row per class (section), not per block
        self.assertEqual((rows[0]["chosen_room"], rows[0]["chosen_start"], rows[0]["chosen_end"]), ("N-103", "07:00", "10:00"))
        # the pop-up's suggestions: same room, outside the window (nothing is free inside it), nothing saved until confirmed
        self.client.force_authenticate(self.dean)
        s = self.client.post("/api/engine/slot-options/", {"section_id": self.sec[0].id, "subject_id": sub.id, "room_id": self.rooms[2].id,
                                                          "start": "07:00", "end": "10:00"}, format="json")
        self.assertEqual(s.status_code, 200, s.data)
        self.assertEqual(s.data["options"], [])
        self.assertTrue(s.data["outside_options"])
        self.assertEqual({o["room_id"] for o in s.data["outside_options"]}, {self.rooms[2].id})
        self.assertFalse(Schedule.objects.filter(subject=sub).exists())

    def _lec_lab(self):
        lab_room = Room.objects.create(name="Lab Q", capacity=40, room_type="lab", department=DEPT)
        lec = Subject.objects.create(code="CS7103", title="Fundamentals of Information Management - Lec", program=self.prog, lec_units=2,
                                     lab_units=0, year_level="1st Year", semester="1st Sem", classification="major")
        lab = Subject.objects.create(code="CS7103L", title="Fundamentals of Information Management - Lab", program=self.prog, lec_units=0,
                                     lab_units=1, year_level="1st Year", semester="1st Sem", classification="major")
        return lec, lab, lab_room

    def test_lec_and_lab_of_one_subject_get_the_same_teacher(self):
        lec, lab, _room = self._lec_lab()
        # the lecture's teacher is the busiest, so load balancing alone would hand the lab to someone else
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        for sec in self.sec:
            t_lec = set(Schedule.objects.filter(section=sec, subject=lec).values_list("teacher_id", flat=True))
            t_lab = set(Schedule.objects.filter(section=sec, subject=lab).values_list("teacher_id", flat=True))
            self.assertEqual(len(t_lec), 1); self.assertEqual(t_lec, t_lab)
        self.assertEqual(scan()["total"], 0)

    def test_lab_waits_for_its_lecture_teacher_and_resolve_offers_only_that_teacher(self):
        lec, lab, room = self._lec_lab()
        self.gen()
        row = Schedule.objects.filter(section=self.sec[0], subject=lec).first()
        Schedule.objects.filter(section=self.sec[0], subject=lab).delete()
        self.client.force_authenticate(self.dean)
        s = self.client.post("/api/engine/slot-options/", {"section_id": self.sec[0].id, "subject_id": lab.id, "room_id": room.id}, format="json")
        self.assertEqual(s.status_code, 200, s.data)
        self.assertTrue(s.data["options"])
        self.assertEqual({o["teacher_id"] for o in s.data["options"]}, {row.teacher_id})
        # a manual edit may not split them either
        lab_row = Schedule.objects.filter(section=self.sec[1], subject=lab).first()
        other = next(t for t in self.teachers if t.id != lab_row.teacher_id)
        e = self.client.patch(f"/api/engine/schedules/{lab_row.id}/", {"teacher": other.id}, format="json")
        self.assertEqual(e.status_code, 400, e.data); self.assertIn("same teacher", str(e.data))

    def test_lecture_stays_before_its_lab_in_every_path(self):
        from engine.lecorder import _di, _m
        lec, lab, room = self._lec_lab()
        self.assertEqual(self.gen().status_code, 201)
        sec = self.sec[0]
        lec_rows = list(Schedule.objects.filter(section=sec, subject=lec).select_related("timeslot"))
        lab_rows = list(Schedule.objects.filter(section=sec, subject=lab).select_related("timeslot"))
        pos = lambda r, which: (_di(r.timeslot.day), _m(getattr(r.timeslot, which)))
        lab_start = min(pos(r, "start_time") for r in lab_rows)
        lec_end = max(pos(r, "end_time") for r in lec_rows)
        self.assertLessEqual(lec_end, lab_start)                                       # the solver already keeps the order
        from engine.pdf_export import build_schedule_pdf
        pdf = build_schedule_pdf(list(Schedule.objects.filter(section=sec).select_related("subject", "teacher__user", "room", "section", "timeslot")),
                                 "Test", departments=[DEPT])
        self.assertTrue(pdf.read(4) == b"%PDF")                                      # the printed table renders with the Lec / Lab note
        self.client.force_authenticate(self.dean)
        # 1. Resolve: every suggested time for the Lecture ends before its Lab starts
        opts = self.client.post("/api/engine/slot-options/", {"ids": [r.id for r in lec_rows], "limit": 300}, format="json").data
        for o in opts["options"] + opts["outside_options"]:
            d = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun").index(o["days"][-1])
            h, m = map(int, o["end"].split(":"))
            self.assertLessEqual((d, h * 60 + m), lab_start, o)
        # 2. Change day / time: moving the Lecture after its Lab is refused with the reason, nothing saved
        before = [r.timeslot_id for r in lec_rows]
        r = self.client.post("/api/engine/reschedule/", {"day": "Sat", "start_time": "16:00", "items": [{"ids": [x.id for x in lec_rows]}]}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
        self.assertIn("before its Lab", str(r.data))
        self.assertEqual(before, [x.timeslot_id for x in Schedule.objects.filter(pk__in=[x.id for x in lec_rows]).order_by("id")])
        # ... but moving BOTH in one request, Lecture first, is fine
        r = self.client.post("/api/engine/reschedule/", {"preview": True, "items": [
            {"ids": [x.id for x in lec_rows], "day": "Sat", "start_time": "07:00"},
            {"ids": [x.id for x in lab_rows], "day": "Sat", "start_time": "13:00"}]}, format="json")
        self.assertFalse(any("Lab" in m and "Lecture" in m for it in r.data["items"] for m in it["messages"]), r.data)
        # 3. Edit window: a Lab period put before its Lecture is refused
        from engine.conflicts import find_conflicts
        lr = lab_rows[0]
        early = next(t for t in TimeSlot.objects.order_by("id") if (_di(t.day), _m(t.end_time)) <= lec_end
                     and _m(t.end_time) - _m(t.start_time) == 60
                     and not find_conflicts(teacher=lr.teacher, room=lr.room, section=sec, timeslot=t, semester="1st Sem", exclude_pk=lr.pk))
        e = self.client.patch(f"/api/engine/schedules/{lr.id}/", {"timeslot": early.id}, format="json")
        self.assertEqual(e.status_code, 400, e.data); self.assertIn("after its Lecture", str(e.data))

    def test_major_with_no_field_is_not_given_to_an_unrelated_teacher_of_the_college(self):
        from engine.qualification import is_qualified
        sub = Subject.objects.create(code="NF1", title="Seminar", program=Program.objects.create(name="BS Nursing Test", department="Nursing"),
                                     lec_units=3, lab_units=0, year_level="1st Year", semester="1st Sem", classification="major")
        sec = Section.objects.create(name="N1", program=sub.program, year_level="1st Year", semester="1st Sem", student_count=20)
        t = make_teacher(93)
        User.objects.filter(pk=t.user_id).update(department="Nursing")
        FacultyProfile.objects.filter(pk=t.pk).update(degree="BS Accountancy")
        t = FacultyProfile.objects.select_related("user").get(pk=t.pk)
        self.assertFalse(is_qualified(t, sub, sec, set()))                            # same college is not enough
        f = AcademicField.objects.create(name="Nursing")
        Subject.objects.filter(pk=sub.pk).update(field=f)
        sub = Subject.objects.get(pk=sub.pk)
        self.assertTrue(is_qualified(t, sub, sec, {f.id}))                            # a recorded specialization is

    def test_unrelated_department_faculty_never_teach_a_major(self):
        from curriculum.models import AcademicField
        cs = AcademicField.objects.create(name="Computer Science")
        sub = self._sub()
        Subject.objects.filter(pk=sub.pk).update(field=cs)
        FacultyProfile.objects.filter(pk__in=[t.id for t in self.teachers]).update(degree="")   # nobody in the college is related
        other = make_teacher(90)
        User.objects.filter(pk=other.user_id).update(department="Nursing")
        other.specializations.clear()
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(Schedule.objects.filter(subject=sub).exists())     # nobody holds the specialization: nothing is assigned
        why = " ".join(c["reason"] for c in r.data["conflicts"] if c["subject_id"] == sub.id)
        self.assertIn("No qualified faculty", why); self.assertIn("specialization", why)
        self.assertFalse(Schedule.objects.filter(teacher=other).exists())

    def test_specialist_is_chosen_over_other_available_teachers(self):
        from curriculum.models import AcademicField
        cs = AcademicField.objects.create(name="Computer Science")
        sub = self._sub()
        Subject.objects.filter(pk=sub.pk).update(field=cs)
        FacultyProfile.objects.filter(pk__in=[t.id for t in self.teachers]).update(degree="")   # only the specialist is related
        self.teachers[4].specializations.add(cs)
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual({x.teacher_id for x in Schedule.objects.filter(subject=sub)}, {self.teachers[4].id})

    def test_computing_degree_qualifies_for_cs_and_it_majors_in_own_college_only(self):
        from engine.qualification import is_qualified
        sub = Subject.objects.create(code="CS9", title="Computer Programming 1", program=self.prog, lec_units=3, lab_units=0,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        a, b = make_teacher(91), make_teacher(92)
        FacultyProfile.objects.filter(pk=a.pk).update(degree="BSIT, MSIT")
        FacultyProfile.objects.filter(pk=b.pk).update(degree="BSIT")
        User.objects.filter(pk=b.user_id).update(department="Business")
        a, b = FacultyProfile.objects.select_related("user").get(pk=a.pk), FacultyProfile.objects.select_related("user").get(pk=b.pk)
        sub.field = None
        from curriculum.models import AcademicField
        f = AcademicField.objects.create(name="Information Technology"); sub.field = f; sub.save()
        self.assertTrue(is_qualified(a, sub, self.sec[0], set()))
        self.assertFalse(is_qualified(b, sub, self.sec[0], set()))           # other college, no explicit specialization

    def test_specialization_counts_for_a_major_only_inside_the_subjects_college(self):
        from engine.qualification import is_qualified
        from curriculum.models import AcademicField
        math = AcademicField.objects.create(name="Major in Mathematics")
        sub = Subject.objects.create(code="CS3X", title="Fundamentals of Accounting", program=self.prog, lec_units=3, lab_units=0,
                                     year_level="3rd Year", semester="1st Sem", classification="major", field=math)
        own, other = make_teacher(94), make_teacher(95)
        FacultyProfile.objects.filter(pk__in=[own.pk, other.pk]).update(degree="Doctorate of Mathematics")
        User.objects.filter(pk=other.user_id).update(department="Arts and Sciences")
        own, other = (FacultyProfile.objects.select_related("user").get(pk=x.pk) for x in (own, other))
        self.assertTrue(is_qualified(own, sub, self.sec[0], {math.id}))       # the college's own mathematics teacher
        self.assertFalse(is_qualified(other, sub, self.sec[0], {math.id}))    # same specialization, other college: not for a major
        gened = Subject.objects.create(code="GEM", title="Mathematics in the Modern World", program=self.prog, lec_units=3,
                                       lab_units=0, year_level="1st Year", semester="1st Sem", classification="minor", field=math)
        self.assertTrue(is_qualified(other, gened, self.sec[0], {math.id}))   # Gen Ed is unchanged: any college

    def test_half_hour_window_places_at_half_hour_without_overlap(self):
        sub = Subject.objects.create(code="HH1", title="Half Hour Test", program=self.prog, lec_units=2, lab_units=0,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in range(7, 20):
                for m in (0, 30):
                    TimeSlot.objects.get_or_create(day=d, start_time=dtime(h, m), end_time=dtime(h, 30) if m == 0 else dtime(h + 1, 0))
        r = self.gen(time_windows={str(sub.id): {"start": "07:30", "end": "09:30"}}, room_choices={str(sub.id): self.rooms[0].id})
        self.assertEqual(r.status_code, 201, r.data)
        rows = Schedule.objects.filter(subject=sub, section=self.sec[0])
        self.assertTrue(rows.exists(), r.data["conflicts"])
        self.assertEqual((min(x.timeslot.start_time for x in rows), max(x.timeslot.end_time for x in rows)), (dtime(7, 30), dtime(9, 30)))
        self.assertEqual(scan()["total"], 0)


class SharedMinorClassTests(Base):
    """Shared minor classes chosen before generating: validation, confirmation, one class for 2-3 programs, exclusive, no duplicates."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Section.objects.filter(name__in=["T1A", "T1B"]).delete()            # only the minor-sharing sections matter here
        cls.p2 = Program.objects.create(name="BS Two", department="Dept Two")
        cls.p3 = Program.objects.create(name="BS Three", department="Dept Three")
        cls.p4 = Program.objects.create(name="BS Four", department="Dept Four")
        cls.progs = [cls.prog, cls.p2, cls.p3, cls.p4]
        cls.msecs, cls.msubs = {}, {}
        for p, n in zip(cls.progs, (20, 20, 15, 15)):
            cls.msecs[p.id] = Section.objects.create(name="M1", program=p, year_level="1st Year", semester="1st Sem", student_count=n)
            cls.msubs[p.id] = Subject.objects.create(code="GE100", title="Understanding the Self", program=p, lec_units=3, lab_units=0,
                                                     year_level="1st Year", semester="1st Sem", classification="minor")
        cls.cas = [make_cas_teacher(400 + i) for i in range(4)]             # Gen Ed teachers (College of Arts and Science rule)

    def call(self, user, name, body=None, get=False):
        self.client.force_authenticate(user)
        url = f"/api/engine/shared-classes/{name}/"
        return self.client.get(url, body) if get else self.client.post(url, body or {}, format="json")

    def share(self, ids, user=None):
        return self.call(user or self.registrar, "save", {"subject_id": self.msubs[ids[0].id].id, "program_ids": [p.id for p in ids[1:]]})

    def regen(self, prog):
        self.client.force_authenticate(self.registrar)
        return self.client.post("/api/engine/generate-schedule/", {"program_id": prog.id, "year_level": "1st Year", "semester": "1st Sem",
                                                                  "school_year": SY}, format="json")

    def test_only_compatible_programs_and_2_or_3_may_share(self):
        sub = self.msubs[self.prog.id]
        r = self.call(self.registrar, "validate", {"subject_id": sub.id, "program_ids": []})
        self.assertFalse(r.data["ok"]); self.assertIn("2 or 3", " ".join(r.data["errors"]))
        r = self.call(self.registrar, "validate", {"subject_id": sub.id, "program_ids": [self.p2.id, self.p3.id, self.p4.id]})
        self.assertFalse(r.data["ok"])                                                  # four programs
        Subject.objects.filter(pk=self.msubs[self.p3.id].pk).update(lec_units=2)         # curriculum differs
        r = self.call(self.registrar, "validate", {"subject_id": sub.id, "program_ids": [self.p2.id, self.p3.id]})
        self.assertFalse(r.data["ok"]); self.assertIn("curriculum differs", " ".join(r.data["errors"]))
        Subject.objects.filter(pk=self.msubs[self.p3.id].pk).update(lec_units=3)
        Subject.objects.filter(pk=self.msubs[self.p2.id].pk).update(title="Something else")
        r = self.call(self.registrar, "validate", {"subject_id": sub.id, "program_ids": [self.p2.id]})
        self.assertFalse(r.data["ok"])
        Subject.objects.filter(pk=self.msubs[self.p2.id].pk).update(title="Understanding the Self")
        r = self.call(self.registrar, "validate", {"subject_id": sub.id, "program_ids": [self.p2.id, self.p3.id]})
        self.assertTrue(r.data["ok"], r.data); self.assertEqual(r.data["total_students"], 55)

    def test_enrollment_must_fit_the_room(self):
        Section.objects.filter(pk=self.msecs[self.p2.id].pk).update(student_count=50)
        r = self.call(self.registrar, "validate", {"subject_id": self.msubs[self.prog.id].id, "program_ids": [self.p2.id]})
        self.assertFalse(r.data["ok"]); self.assertIn("do not fit", " ".join(r.data["errors"]))

    def test_lab_subject_cannot_be_shared(self):
        Subject.objects.filter(pk__in=[s.pk for s in self.msubs.values()]).update(lab_units=1)
        r = self.call(self.registrar, "validate", {"subject_id": self.msubs[self.prog.id].id, "program_ids": [self.p2.id]})
        self.assertFalse(r.data["ok"])

    def test_only_the_registrar_chooses_shared_classes(self):
        Program.objects.filter(pk=self.p2.pk).update(department=DEPT)
        # minor subjects belong to the Registrar: a Dean cannot save, make exclusive, clear or confirm, even for own-college programs
        self.assertEqual(self.share([self.prog, self.p2], user=self.dean).status_code, 403)
        sid = self.msubs[self.prog.id].id
        self.assertEqual(self.call(self.dean, "exclusive", {"subject_id": sid}).status_code, 403)
        self.assertEqual(self.call(self.dean, "clear", {"subject_id": sid}).status_code, 403)
        from engine.models import SharedClassGroup
        from engine.shared_classes import share_rules
        self.assertFalse(SharedClassGroup.objects.exists())
        # a group saved by a Dean before this rule (unconfirmed) is kept and still waits for the Registrar
        old = SharedClassGroup.objects.create(code="GE100", title=self.msubs[self.prog.id].title, lec_units=self.msubs[self.prog.id].lec_units,
                                              lab_units=0, year_level="1st Year", semester="1st Sem", created_by=self.dean, confirmed=False)
        old.programs.set([self.prog, self.p3])
        self.assertEqual(share_rules("1st Year", "1st Sem"), {})                            # unconfirmed groups are not used
        self.assertEqual(self.call(self.dean, "confirm", {"group_id": old.id}).status_code, 403)
        self.assertEqual(self.call(self.registrar, "confirm", {"group_id": old.id}).status_code, 200)
        self.assertTrue(share_rules("1st Year", "1st Sem"))
        # the Registrar's own choice is confirmed at once (across colleges too)
        r = self.share([self.prog, self.p2])
        self.assertEqual(r.status_code, 200, r.data); self.assertTrue(r.data["confirmed"])
        # a Dean can still READ the choices of own programs
        self.assertEqual(self.call(self.dean, "options", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem"}, get=True).status_code, 200)

    def test_generation_makes_one_shared_class_for_the_chosen_programs(self):
        self.assertEqual(self.share([self.prog, self.p2, self.p3]).status_code, 200)
        r = self.regen(self.prog)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["shared_classes"]), 1)
        rows = Schedule.objects.filter(subject__code="GE100")
        self.assertEqual({x.section.program_id for x in rows}, {self.prog.id, self.p2.id, self.p3.id})
        self.assertEqual(len({(x.teacher_id, x.room_id, x.timeslot_id) for x in rows}), rows.values("timeslot_id").distinct().count())
        self.assertEqual(len({x.merge_key for x in rows}), 1); self.assertNotEqual(rows[0].merge_key, "")
        self.assertFalse(Schedule.objects.filter(subject__code="GE100", section__program=self.p4).exists())
        self.assertEqual(r.data["shared_classes"][0]["students"], 55)
        self.assertEqual(scan()["total"], 0)
        # generating again does not stack duplicates
        n = rows.count()
        self.assertEqual(self.regen(self.prog).status_code, 201)
        self.assertEqual(Schedule.objects.filter(subject__code="GE100").count(), n)
        self.assertEqual(scan()["total"], 0)

    def test_exclusive_program_keeps_its_own_class(self):
        self.assertEqual(self.share([self.prog, self.p3]).status_code, 200)
        self.assertEqual(self.call(self.registrar, "exclusive", {"subject_id": self.msubs[self.p2.id].id}).status_code, 200)
        self.assertEqual(self.regen(self.prog).status_code, 201)
        self.assertEqual(self.regen(self.p2).status_code, 201)
        mine = Schedule.objects.filter(subject__code="GE100", section__program=self.p2)
        self.assertTrue(mine.exists()); self.assertEqual({x.merge_key for x in mine}, {""})
        self.assertEqual(scan()["total"], 0)

    def test_shared_time_avoids_a_member_sections_other_classes(self):
        self.assertEqual(self.share([self.prog, self.p2]).status_code, 200)
        other = Subject.objects.create(code="ZZ1", title="Other", program=self.p2, lec_units=3, lab_units=0, year_level="1st Year",
                                       semester="1st Sem", classification="major")
        for d in ("Mon", "Tue", "Wed"):
            for h in (7, 8, 9):
                slot, _ = TimeSlot.objects.get_or_create(day=d, start_time=dtime(h), end_time=dtime(h + 1))
                Schedule.objects.create(subject=other, section=self.msecs[self.p2.id], teacher=self.teachers[5], room=self.rooms[3], timeslot=slot)
        r = self.regen(self.prog)
        self.assertEqual(r.status_code, 201, r.data)
        shared = Schedule.objects.filter(subject__code="GE100")
        self.assertEqual({x.section.program_id for x in shared}, {self.prog.id, self.p2.id})
        self.assertTrue(all(not (x.timeslot.day in ("Mon", "Tue", "Wed") and 7 <= x.timeslot.start_time.hour <= 9) for x in shared))
        self.assertEqual(scan()["total"], 0)

    def test_options_list_shows_candidates_and_current_choice(self):
        self.share([self.prog, self.p2])
        r = self.call(self.registrar, "options", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem"}, get=True)
        self.assertEqual(r.status_code, 200, r.data)
        item = next(s for s in r.data["subjects"] if s["code"] == "GE100")
        self.assertEqual(item["mode"], "shared"); self.assertTrue(item["group"]["confirmed"])
        self.assertEqual({c["id"] for c in item["candidates"]}, {self.p2.id, self.p3.id, self.p4.id})
        self.assertEqual({"department", "year_level", "semester"} <= set(item["candidates"][0]), True)


class DesignatedRoomTests(APITestCase):
    """Computer Studies majors use Comp Lab C / D only; Dean assigns majors, Registrar minors; Resolve keeps the rules."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = "Computer Studies"
        cls.dean = User(username="CD", school_id="CD", first_name="Cs", last_name="Dean", role="faculty", faculty_type="dean", department=cls.dept)
        cls.dean.set_password("pw"); cls.dean.save(); FacultyProfile.objects.create(user=cls.dean)
        cls.reg = User(username="RG", school_id="RG", first_name="Reg", last_name="Istrar", role="registrar"); cls.reg.set_password("pw"); cls.reg.save()
        cls.teachers = []
        for i in range(4):
            u = User(username=f"CT{i}", school_id=f"CT{i}", first_name="C", last_name=f"T{i}", role="faculty", faculty_type="full_time", department=cls.dept)
            u.set_password("pw"); u.save(); cls.teachers.append(FacultyProfile.objects.create(user=u, degree="BS Computer Science"))
        cls.cas = [make_cas_teacher(500 + i) for i in range(2)]             # Gen Ed teachers (College of Arts and Science rule)
        Room.objects.filter(name__startswith="Comp Lab").delete()          # rooms a migration may have added: this test builds its own
        cls.labC = Room.objects.create(name="Comp Lab C", capacity=40, room_type="lab", department=cls.dept)
        cls.labD = Room.objects.create(name="Comp Lab D", capacity=40, room_type="lab", department=cls.dept)
        cls.lect = [Room.objects.create(name=f"L-{i}", capacity=45, room_type="lecture") for i in range(3)]
        cls.prog = Program.objects.create(name="BS CS Test", department=cls.dept)
        cls.sec = Section.objects.create(name="A", program=cls.prog, year_level="1st Year", semester="1st Sem", student_count=30)
        cls.lec = Subject.objects.create(code="CSX1", title="Programming", program=cls.prog, lec_units=2, lab_units=0, year_level="1st Year",
                                         semester="1st Sem", classification="major")
        cls.lab = Subject.objects.create(code="CSX1L", title="Programming Lab", program=cls.prog, lec_units=0, lab_units=1, year_level="1st Year",
                                         semester="1st Sem", classification="major")
        cls.gen_ed = Subject.objects.create(code="GEX1", title="Ethics", program=cls.prog, lec_units=3, lab_units=0, year_level="1st Year",
                                            semester="1st Sem", classification="minor")
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in range(7, 20):
                TimeSlot.objects.get_or_create(day=d, start_time=dtime(h), end_time=dtime(h + 1))

    def gen(self, user, **extra):
        self.client.force_authenticate(user)
        return self.client.post("/api/engine/generate-schedule/", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem",
                                                                  "school_year": SY, **extra}, format="json")

    def test_cs_majors_only_use_comp_lab_c_and_d(self):
        r = self.gen(self.dean)
        self.assertEqual(r.status_code, 201, r.data)
        names = {x.room.name for x in Schedule.objects.filter(subject__classification="major")}
        self.assertTrue(names and names <= {"Comp Lab C", "Comp Lab D"}, names)
        self.assertEqual(scan()["total"], 0)

    def test_full_labs_leave_the_class_unplaced_with_the_real_reason(self):
        other = Section.objects.create(name="Z", program=Program.objects.create(name="Other Prog", department="Dept X"), year_level="1st Year",
                                       semester="1st Sem", student_count=10)
        sub = Subject.objects.create(code="ZZ9", title="Busy", program=other.program, lec_units=3, lab_units=0, year_level="1st Year",
                                     semester="1st Sem", classification="major")
        other2 = Section.objects.create(name="Z2", program=other.program, year_level="1st Year", semester="1st Sem", student_count=10)
        for room in (self.labC, self.labD):
            for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
                for h in range(7, 20):
                    sl = TimeSlot.objects.get(day=d, start_time=dtime(h))
                    Schedule.objects.create(subject=sub, section=other if room == self.labC else other2, teacher=self.teachers[3] if room == self.labC else self.teachers[2],
                                            room=room, timeslot=sl, status="approved", merge_key=f"x{room.id}")
        r = self.gen(self.dean)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(Schedule.objects.filter(subject=self.lec).exists())              # not moved to a lecture room
        self.assertTrue(any("already booked" in c["reason"] for c in r.data["conflicts"]), r.data["conflicts"])

    def test_dean_cannot_choose_an_ordinary_room_for_cs_majors_or_a_room_for_gen_ed(self):
        r = self.gen(self.dean, room_choices={str(self.lec.id): self.lect[0].id})
        self.assertEqual(r.status_code, 400, r.data); self.assertIn("designated rooms", r.data["detail"])
        self.assertFalse(Schedule.objects.exists())
        self.client.force_authenticate(self.dean)
        r = self.client.put("/api/rooms/dean/subject-room/", {"subject": self.gen_ed.id, "preferred_room": self.lect[0].id}, format="json")
        self.assertEqual(r.status_code, 403); self.assertIn("Registrar", r.data["detail"]); self.assertIn("action", r.data)
        r = self.client.put("/api/rooms/dean/subject-room/", {"subject": self.lec.id, "preferred_room": self.lect[0].id}, format="json")
        self.assertEqual(r.status_code, 400); self.assertIn("designated rooms", r.data["detail"])
        r = self.client.put("/api/rooms/dean/subject-room/", {"subject": self.lec.id, "preferred_room": self.labC.id}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.client.force_authenticate(self.reg)
        r = self.client.put("/api/rooms/dean/subject-room/", {"subject": self.lec.id, "preferred_room": self.labD.id}, format="json")
        self.assertEqual(r.status_code, 403); self.assertIn("Dean of Computer Studies", r.data["detail"])
        r = self.client.put("/api/rooms/dean/subject-room/", {"subject": self.gen_ed.id, "preferred_room": self.lect[1].id}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_resolve_never_offers_an_ordinary_room_for_cs_majors(self):
        self.assertEqual(self.gen(self.dean).status_code, 201)
        row = Schedule.objects.filter(subject=self.lec).first()
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):                                      # make the lab busy everywhere else
            for h in range(7, 20):
                sl = TimeSlot.objects.get(day=d, start_time=dtime(h))
                if not Schedule.objects.filter(room=row.room, timeslot=sl).exists():
                    Schedule.objects.create(subject=self.gen_ed, section=Section.objects.create(name=f"B{d}{h}", program=self.prog, year_level="2nd Year", semester="1st Sem"),
                                            teacher=self.teachers[3], room=row.room, timeslot=sl, status="approved", merge_key=f"k{d}{h}")
        self.client.force_authenticate(self.dean)
        r = self.client.post("/api/engine/slot-options/", {"ids": [x.id for x in Schedule.objects.filter(subject=self.lec, section=self.sec)], "limit": 300}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["options"], []); self.assertFalse(r.data["room_options"]); self.assertFalse(r.data["room_change_allowed"])
        self.assertIn("designated rooms", r.data["reason"])

    def test_registrar_gets_alternative_rooms_for_a_gen_ed_class(self):
        self.client.force_authenticate(self.reg)
        r = self.client.post("/api/engine/generate-schedule/", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem",
                                                                "school_year": SY, "room_choices": {str(self.gen_ed.id): self.lect[0].id}}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        rows = list(Schedule.objects.filter(subject=self.gen_ed))
        self.assertEqual({x.room_id for x in rows}, {self.lect[0].id})
        other = Section.objects.create(name="Q", program=self.prog, year_level="3rd Year", semester="1st Sem", student_count=10)
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in range(7, 20):
                sl = TimeSlot.objects.get(day=d, start_time=dtime(h))
                if not Schedule.objects.filter(room=self.lect[0], timeslot=sl).exists():
                    Schedule.objects.create(subject=self.lec, section=other, teacher=self.teachers[2], room=self.lect[0], timeslot=sl, status="approved", merge_key=f"m{d}{h}")
        r = self.client.post("/api/engine/slot-options/", {"ids": [x.id for x in rows], "limit": 300}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["options"], [])
        self.assertTrue(r.data["room_options"])
        self.assertTrue(all(o["room_changed"] and o["room"] != "L-0" and not o["room"].startswith("Comp Lab") for o in r.data["room_options"]))
        key = r.data["room_options"][0]["key"]
        ap = self.client.post("/api/engine/slot-options/apply/", {"ids": [x.id for x in rows], "key": key}, format="json")
        self.assertEqual(ap.status_code, 200, ap.data)
        self.assertEqual(scan()["total"], 0)

    def test_outside_window_times_are_offered_with_the_same_room(self):
        self.assertEqual(self.gen(self.dean).status_code, 201)
        rows = list(Schedule.objects.filter(subject=self.lec, section=self.sec))
        self.client.force_authenticate(self.dean)
        r = self.client.post("/api/engine/slot-options/", {"ids": [x.id for x in rows], "limit": 300, "start": "07:00", "end": "09:00"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        room = rows[0].room.name
        self.assertTrue(r.data["options"] or r.data["outside_options"])
        for o in r.data["options"] + r.data["outside_options"]:
            self.assertEqual(o["room"], room)
        for o in r.data["options"]:
            self.assertTrue("07:00" <= o["start"] and o["end"] <= "09:00")


class ScheduleActionsTests(Base):
    """Schedules tab: approve only what is conflict-free, remove only drafts (with Undo), back to draft, edits locked, history."""

    def post(self, name, body, user=None):
        self.client.force_authenticate(user or self.dean)
        return self.client.post(f"/api/engine/schedules/{name}/", body, format="json")

    def test_approve_selected_only_and_conflicting_classes_stay_draft_with_the_reason(self):
        ok = self.row(subj=0, h=7)
        other = self.row(subj=2, h=13, sec=self.sec[1], teacher=self.teachers[2], room=self.rooms[2])   # draft NOT selected
        a = self.row(subj=1, h=9, sec=self.sec[0], teacher=self.teachers[1], room=self.rooms[1])
        half, _ = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(9, 30), end_time=dtime(10, 30))
        Schedule.objects.create(subject=Subject.objects.get(code="TST103"), section=self.sec[1], teacher=self.teachers[1], room=self.rooms[3], timeslot=half)
        r = self.post("approve_bulk", {"ids": [ok.id, a.id], "to_status": "approved"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["updated"], 1)
        self.assertEqual([c["code"] for c in r.data["ready"]], ["TST100"])
        self.assertEqual([c["code"] for c in r.data["blocked"]], ["TST101"])
        self.assertIn("Teacher", r.data["blocked"][0]["reasons"][0])
        ok.refresh_from_db(); a.refresh_from_db(); other.refresh_from_db()
        self.assertEqual((ok.status, a.status, other.status), ("approved", "draft", "draft"))   # only the selection moved
        self.assertEqual(ok.approved_by_id, self.dean.id); self.assertIsNotNone(ok.approved_at)

    def test_back_to_draft_only_for_approved_without_coverage(self):
        a, b = self.row(subj=0, h=7), self.row(subj=1, h=9)
        Schedule.objects.filter(pk=a.pk).update(status="approved", approved_by=self.dean)
        Schedule.objects.filter(pk=b.pk).update(status="published")
        self.assertEqual(self.post("approve_bulk", {"ids": [b.id], "to_status": "draft"}).status_code, 409)       # published stays
        r = self.post("approve_bulk", {"ids": [a.id], "to_status": "draft"})
        self.assertEqual((r.status_code, r.data["updated"]), (200, 1), r.data)
        a.refresh_from_db(); self.assertEqual((a.status, a.approved_by_id), ("draft", None))
        from faculty.models import Absence, CoverageSuggestion
        Schedule.objects.filter(pk=a.pk).update(status="approved")
        ab = Absence.objects.create(faculty=self.teachers[0], date="2026-08-03")
        CoverageSuggestion.objects.create(absence=ab, schedule=a)
        r = self.post("approve_bulk", {"ids": [a.id], "to_status": "draft"})
        self.assertEqual(r.data["updated"], 0); self.assertTrue(r.data["blocked"])                              # something depends on it

    def test_remove_only_drafts_and_undo_restores_the_exact_rows(self):
        a, b = self.row(subj=0, h=7), self.row(subj=0, h=8)
        appr = self.row(subj=1, h=10)
        Schedule.objects.filter(pk=appr.pk).update(status="approved")
        # approved: refused by the bulk remove AND by the single DELETE
        self.assertEqual(self.post("remove_bulk", {"ids": [appr.id]}).status_code, 409)
        self.client.force_authenticate(self.dean)
        self.assertEqual(self.client.delete(f"/api/engine/schedules/{appr.id}/").status_code, 400)
        self.assertTrue(Schedule.objects.filter(pk=appr.pk).exists())
        prev = self.post("remove_preview", {"ids": [a.id, b.id, appr.id]}).data
        self.assertEqual((prev["periods"], len(prev["locked"])), (2, 1))
        before = {x["id"]: x for x in Schedule.objects.filter(pk__in=[a.id, b.id]).values()}
        r = self.post("remove_bulk", {"ids": [a.id, b.id]})
        self.assertEqual((r.status_code, r.data["removed"]), (200, 2), r.data)
        self.assertFalse(Schedule.objects.filter(pk__in=[a.id, b.id]).exists())
        token = r.data["undo_token"]
        self.assertEqual(self.post("undo_remove", {"token": token}, user=self.registrar).status_code, 403)       # only the same person
        u = self.post("undo_remove", {"token": token})
        self.assertEqual((u.status_code, u.data["restored"]), (200, 2), u.data)
        after = {x["id"]: x for x in Schedule.objects.filter(pk__in=[a.id, b.id]).values()}
        self.assertEqual(before, after)                                                    # same ids, same fields
        self.assertEqual(self.post("undo_remove", {"token": token}).status_code, 404)        # once only

    def test_undo_is_refused_when_the_time_was_taken_or_expired(self):
        a = self.row(subj=0, h=7)
        token = self.post("remove_bulk", {"ids": [a.id]}).data["undo_token"]
        taker = self.row(subj=2, h=7, sec=self.sec[1], teacher=self.teachers[0], room=self.rooms[2])   # same teacher, same time
        r = self.post("undo_remove", {"token": token})
        self.assertEqual(r.status_code, 409, r.data); self.assertFalse(Schedule.objects.filter(pk=a.id).exists())
        taker.delete()
        from datetime import timedelta
        from django.utils import timezone
        from engine.models import Log
        Log.objects.filter(pk=token).update(timestamp=timezone.now() - timedelta(minutes=10))
        self.assertEqual(self.post("undo_remove", {"token": token}).status_code, 410)

    def test_shared_class_needs_confirmation_and_owner_rules_hold(self):
        a = self.row(subj=0, h=7, merge="mk1")
        self.row(subj=0, h=7, sec=self.sec[1], merge="mk1")
        prev = self.post("remove_preview", {"ids": [a.id]}).data
        self.assertTrue(prev["shared"]); self.assertIn("SHARED", prev["warnings"][0])
        r = self.post("remove_bulk", {"ids": [a.id]})
        self.assertEqual(r.status_code, 409); self.assertTrue(r.data["needs_confirm"])
        self.assertEqual(self.post("remove_bulk", {"ids": [a.id]}, user=self.registrar).status_code, 403)   # a major: the Dean's
        self.assertEqual(self.post("remove_bulk", {"ids": [a.id], "confirm_shared": True}).status_code, 200)

    def test_edit_refuses_an_unqualified_teacher(self):
        a = self.row(subj=0, h=7)
        nurse = make_teacher(70)
        User.objects.filter(pk=nurse.user_id).update(department="Nursing")
        FacultyProfile.objects.filter(pk=nurse.pk).update(degree="BS Nursing")
        self.client.force_authenticate(self.dean)
        r = self.client.patch(f"/api/engine/schedules/{a.id}/", {"teacher": nurse.id}, format="json")
        self.assertEqual(r.status_code, 400, r.data); self.assertIn("not qualified", str(r.data))

    def test_generate_keeps_hand_edited_classes_and_history_is_recorded(self):
        self.assertEqual(self.gen().status_code, 201)
        sub = Subject.objects.get(code="TST100")
        rows = list(Schedule.objects.filter(section=self.sec[0], subject=sub))
        self.client.force_authenticate(self.dean)
        opts = self.client.post("/api/engine/slot-options/", {"ids": [r.id for r in rows]}, format="json").data
        done = self.client.post("/api/engine/slot-options/apply/", {"ids": [r.id for r in rows], "key": opts["options"][0]["key"]}, format="json")
        self.assertEqual(done.status_code, 200, done.data)
        self.assertIn("→", done.data["changes"]); self.assertIn("room stays", done.data["changes"])
        edited = sorted(Schedule.objects.filter(section=self.sec[0], subject=sub).values_list("id", "timeslot_id"))
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(any("TST100" in k for k in r.data["kept_edited"]))
        self.assertEqual(edited, sorted(Schedule.objects.filter(section=self.sec[0], subject=sub).values_list("id", "timeslot_id")))
        self.assertEqual(scan()["total"], 0)
        # keep_edited=false: it is placed again by the generator
        self.assertEqual(self.gen(keep_edited=False).status_code, 201)
        self.assertNotEqual(edited, sorted(Schedule.objects.filter(section=self.sec[0], subject=sub).values_list("id", "timeslot_id")))
        # history of a class: created, then approved (who + when)
        ids = list(Schedule.objects.filter(section=self.sec[0], subject=sub).values_list("id", flat=True))
        self.post("approve_bulk", {"ids": ids, "to_status": "approved"})
        self.client.force_authenticate(self.dean)
        h = self.client.get("/api/engine/schedules/history/", {"ids": ",".join(map(str, ids))}).data
        self.assertEqual(h["events"][0]["action"], "Created")
        self.assertTrue(any("Approved" in e["details"] for e in h["events"]), h)

    def test_approved_classes_cannot_be_edited_or_moved(self):
        a = self.row(subj=0, h=7)
        Schedule.objects.filter(pk=a.pk).update(status="approved")
        self.client.force_authenticate(self.dean)
        self.assertEqual(self.client.patch(f"/api/engine/schedules/{a.id}/", {"room": self.rooms[1].id}, format="json").status_code, 400)
        r = self.client.post("/api/engine/reschedule/", {"day": "Tue", "start_time": "09:00", "items": [{"ids": [a.id]}]}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
        a.refresh_from_db(); self.assertEqual((a.room_id, a.timeslot.day), (self.rooms[0].id, "Mon"))


class ApproveCheckTests(Base):
    """Part 2 (Approve): the server runs the conflict check on the selection first; ready classes move on, blocked ones stay as they are."""

    def post(self, body, user=None):
        self.client.force_authenticate(user or self.dean)
        return self.client.post("/api/engine/schedules/approve_bulk/", body, format="json")

    def _clash_on(self, row, minutes_late=30):
        """A second class of the same TEACHER that overlaps `row` by 30 minutes (section B, another room)."""
        st = row.timeslot.start_time
        s = dtime(st.hour, minutes_late)
        e = dtime(st.hour + 1, minutes_late)
        slot, _ = TimeSlot.objects.get_or_create(day=row.timeslot.day, start_time=s, end_time=e)
        return Schedule.objects.create(subject=Subject.objects.get(code="TST105"), section=self.sec[1], teacher=row.teacher,
                                       room=self.rooms[3], timeslot=slot)

    def test_a_class_is_blocked_as_a_whole_with_the_reason_and_stays_draft(self):
        p1 = self.row(subj=0, h=7)                      # one class, two periods (Mon 7-8, Mon 8-9)
        p2 = self.row(subj=0, h=8)
        self._clash_on(p2)                               # only the SECOND period clashes
        r = self.post({"ids": [p1.id, p2.id], "to_status": "approved"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["updated"], len(r.data["ready"]), len(r.data["blocked"])), (0, 0, 1))
        b = r.data["blocked"][0]
        self.assertEqual((b["code"], sorted(b["ids"])), ("TST100", sorted([p1.id, p2.id])))
        self.assertTrue(b["reasons"] and "Teacher" in b["reasons"][0] and "overlap" in b["reasons"][0], b)
        self.assertEqual(set(Schedule.objects.filter(pk__in=[p1.id, p2.id]).values_list("status", flat=True)), {"draft"})   # never half approved

    def test_students_overlap_is_a_reason_too(self):
        a = self.row(subj=0, h=7)
        half, _ = TimeSlot.objects.get_or_create(day="Mon", start_time=dtime(7, 30), end_time=dtime(8, 30))
        Schedule.objects.create(subject=Subject.objects.get(code="TST104"), section=a.section, teacher=self.teachers[4], room=self.rooms[2], timeslot=half)
        r = self.post({"ids": [a.id], "to_status": "approved"})
        self.assertEqual(r.data["updated"], 0)
        self.assertIn("Students", r.data["blocked"][0]["reasons"][0])

    def test_publish_is_checked_too_and_only_ready_teachers_are_notified(self):
        from notifications.models import Notification
        ok = self.row(subj=0, h=7)
        bad = self.row(subj=1, h=10, teacher=self.teachers[1], room=self.rooms[1])
        Schedule.objects.filter(pk__in=[ok.id, bad.id]).update(status="approved", approved_by=self.dean)
        self._clash_on(bad)
        r = self.post({"ids": [ok.id, bad.id], "to_status": "published"})
        self.assertEqual((r.status_code, r.data["updated"]), (200, 1), r.data)
        self.assertEqual([c["code"] for c in r.data["blocked"]], ["TST101"])
        self.assertEqual(Schedule.objects.get(pk=bad.id).status, "approved")          # blocked: stays where it was
        self.assertEqual(Schedule.objects.get(pk=ok.id).status, "published")
        self.assertTrue(Notification.objects.filter(recipient=ok.teacher.user).exists())
        self.assertFalse(Notification.objects.filter(recipient=bad.teacher.user).exists())

    def test_whole_filter_form_runs_the_same_check(self):
        ok = self.row(subj=0, h=7)
        bad = self.row(subj=1, h=10, teacher=self.teachers[1], room=self.rooms[1])
        clash = self._clash_on(bad)
        Schedule.objects.filter(pk=clash.pk).update(subject=Subject.objects.get(code="TST105"))
        r = self.post({"program_id": self.prog.id, "to_status": "approved"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Schedule.objects.get(pk=ok.id).status, "approved")
        self.assertEqual(Schedule.objects.get(pk=bad.id).status, "draft")
        self.assertIn("TST101", [c["code"] for c in r.data["blocked"]])

    def test_who_and_when_are_recorded_and_blocked_classes_are_logged(self):
        from engine.models import Log
        ok = self.row(subj=0, h=7)
        bad = self.row(subj=1, h=10, teacher=self.teachers[1], room=self.rooms[1])
        self._clash_on(bad)
        self.post({"ids": [ok.id, bad.id], "to_status": "approved"})
        ok.refresh_from_db(); bad.refresh_from_db()
        self.assertEqual(ok.approved_by_id, self.dean.id); self.assertIsNotNone(ok.approved_at)
        self.assertIsNone(bad.approved_by_id); self.assertIsNone(bad.approved_at)
        self.assertTrue(Log.objects.filter(schedule_id=ok.id, details__startswith="Approved").exists())
        self.assertTrue(Log.objects.filter(details__startswith="Not approved (conflict)", details__contains="TST101").exists())

    def test_only_the_owner_can_approve(self):
        major = self.row(subj=0, h=7)
        r = self.post({"ids": [major.id], "to_status": "approved"}, user=self.registrar)       # a major: the Dean's
        self.assertEqual((r.status_code, r.data["updated"]), (200, 0))
        self.assertEqual(Schedule.objects.get(pk=major.id).status, "draft")
        self.client.force_authenticate(self.teachers[0].user)
        self.assertEqual(self.client.post("/api/engine/schedules/approve_bulk/", {"ids": [major.id], "to_status": "approved"},
                                          format="json").status_code, 403)

    def test_a_clean_selection_is_all_ready(self):
        a, b = self.row(subj=0, h=7), self.row(subj=1, h=10, teacher=self.teachers[1], room=self.rooms[1])
        r = self.post({"ids": [a.id, b.id], "to_status": "approved"})
        self.assertEqual((r.data["updated"], len(r.data["ready"]), r.data["blocked"]), (2, 2, []))


class ProfessorChoiceTests(Base):
    """Optional Professor per subject in the Dean's Generate preview: qualified own-college faculty only, fixed for the run like a
    chosen room, re-checked by the server, a specific reason when the professor cannot take a class."""
    URL = "/api/engine/generate/professor-options/"

    def opts(self, user=None, **q):
        self.client.force_authenticate(user or self.dean)
        params = {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem"}
        params.update(q)
        return self.client.get(self.URL, params)

    def _sub(self, code="TST100"):
        return Subject.objects.get(code=code)

    def _outsiders(self):
        unq = make_teacher(80)                                                      # Computer Studies, unrelated degree
        FacultyProfile.objects.filter(pk=unq.pk).update(degree="BS Nursing")
        other = make_teacher(81)                                                    # computing degree, other college
        User.objects.filter(pk=other.user_id).update(department="Nursing")
        return unq, other

    def test_options_list_only_qualified_faculty_of_the_deans_college(self):
        unq, other = self._outsiders()
        r = self.opts()
        self.assertEqual(r.status_code, 200, r.data)
        row = next(x for x in r.data["subjects"] if x["code"] == "TST100")
        self.assertEqual(set(row["qualified"]), {t.id for t in self.teachers})
        self.assertNotIn(unq.id, row["qualified"]); self.assertNotIn(other.id, row["qualified"])
        self.assertNotIn(str(other.id), {str(k) for k in r.data["teachers"]})
        self.assertEqual((row["hours_per_section"], row["sections"], row["total_hours"]), (3.0, 2, 6.0))
        self.assertEqual(r.data["teachers"][self.teachers[0].id]["label"], "Er1, T.")

    def test_load_figures_count_kept_classes_but_not_drafts_generate_replaces(self):
        t0, t1 = self.teachers[0], self.teachers[1]
        prog2 = Program.objects.create(name="BS CS Other Year", department=DEPT)
        sec2 = Section.objects.create(name="O1", program=prog2, year_level="2nd Year", semester="1st Sem", student_count=20)
        s2 = Subject.objects.create(code="OTH1", title="Other", program=prog2, lec_units=2, lab_units=0, year_level="2nd Year",
                                    semester="1st Sem", classification="major")
        for h in (7, 8):                                                            # 2 h elsewhere: counted
            Schedule.objects.create(subject=s2, section=sec2, teacher=t0, room=self.rooms[3], term="1st Sem",
                                    timeslot=TimeSlot.objects.get(day="Tue", start_time=dtime(h)))
        self.row(teacher=t1, h=9)                                                   # a draft in scope: replaced, not counted
        kept = self.row(teacher=t1, h=10, subj=1)                                   # hand-edited (locked): counted
        Schedule.objects.filter(teacher=t1).update(term="1st Sem")
        Schedule.objects.filter(pk=kept.pk).update(is_manual_override=True)
        d = self.opts().data
        self.assertEqual(d["teachers"][t0.id]["current_hours"], 2.0)
        self.assertEqual(d["teachers"][t1.id]["current_hours"], 1.0)
        self.assertEqual(d["teachers"][t0.id]["max_hours"], 24)
        self.assertEqual(next(x for x in d["subjects"] if x["code"] == "TST101")["sections"], 1)   # A is locked for TST101

    def test_options_endpoint_writes_nothing_and_is_dean_only(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.opts().status_code, 200)
        writes = [q["sql"] for q in ctx.captured_queries if q["sql"].split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]
        self.assertEqual(writes, [])
        self.assertEqual(self.opts(self.registrar).status_code, 403)
        self.assertEqual(self.opts(self.teachers[0].user).status_code, 403)
        nurse_dean = User.objects.create(username="DN", school_id="DN", role="faculty", faculty_type="dean", department="Nursing")
        self.assertEqual(self.opts(nurse_dean).status_code, 403)

    def test_other_college_or_unqualified_teacher_is_rejected_and_drafts_are_kept(self):
        unq, other = self._outsiders()
        draft = self.row()
        for t, word in ((other, "not a faculty member"), (unq, "not qualified")):
            r = self.gen(teacher_choices={str(self._sub().id): t.id})
            self.assertEqual(r.status_code, 400, r.data)
            self.assertIn(word, r.data["detail"])
        self.assertTrue(Schedule.objects.filter(pk=draft.pk).exists())             # refused before anything was replaced
        self.assertEqual(Schedule.objects.count(), 1)

    def test_chosen_professor_is_used_for_every_section(self):
        t = self.teachers[3]
        r = self.gen(teacher_choices={str(self._sub().id): t.id})
        self.assertEqual(r.status_code, 201, r.data)
        rows = Schedule.objects.filter(subject=self._sub())
        self.assertEqual(rows.values("section").distinct().count(), 2)
        self.assertEqual({x.teacher_id for x in rows}, {t.id})
        self.assertEqual(scan()["total"], 0)

    def test_specific_reason_when_the_chosen_professor_is_busy(self):
        t = self.teachers[3]
        prog2 = Program.objects.create(name="BS CS Busy", department=DEPT)
        sec2 = Section.objects.create(name="B1", program=prog2, year_level="2nd Year", semester="1st Sem", student_count=20)
        s2 = Subject.objects.create(code="BSY1", title="Busy", program=prog2, lec_units=3, lab_units=0, year_level="2nd Year",
                                    semester="1st Sem", classification="major")
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for h in (7, 8, 9):
                Schedule.objects.create(subject=s2, section=sec2, teacher=t, room=self.rooms[3], term="1st Sem", status="approved",
                                        timeslot=TimeSlot.objects.get(day=d, start_time=dtime(h)))
        sub = self._sub()
        r = self.gen(teacher_choices={str(sub.id): t.id}, time_windows={str(sub.id): {"start": "07:00", "end": "10:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        reasons = [c["reason"] for c in r.data["conflicts"] if c["subject_id"] == sub.id]
        self.assertTrue(reasons)
        # each reason is specific: the chosen professor is busy, or (for a section whose other subjects took those mornings) the section is
        self.assertTrue(any("your chosen professor" in x and "already teaching" in x for x in reasons), reasons)
        self.assertTrue(all("your chosen professor" in x or "this section's other classes" in x for x in reasons), reasons)
        self.assertFalse(Schedule.objects.filter(subject=sub).exclude(teacher=t).exists())   # nobody swapped in
        self.assertEqual(Schedule.objects.filter(subject=s2, status="approved").count(), 15)  # approved classes untouched

    def test_specific_reason_when_the_weekly_limit_is_reached_under_strict_policy(self):
        from engine.models import SchedulingConfig
        SchedulingConfig.objects.update_or_create(pk=1, defaults={"workload_policy": "strict", "max_weekly_hours_full_time": 3})
        t, sub = self.teachers[3], self._sub()
        r = self.gen(teacher_choices={str(sub.id): t.id})
        self.assertEqual(r.status_code, 201, r.data)
        reasons = [c["reason"] for c in r.data["conflicts"] if c["subject_id"] == sub.id]
        self.assertEqual(len(reasons), 1, r.data["conflicts"])                         # one section fits in 3 h, the other not
        self.assertIn("weekly limit", reasons[0]); self.assertIn("your chosen professor", reasons[0])
        self.assertEqual({x.teacher_id for x in Schedule.objects.filter(subject=sub)}, {t.id})

    def test_no_available_time_is_rejected_before_generating(self):
        from faculty.models import Availability
        t = self.teachers[3]
        for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
            Availability.objects.create(faculty=t, day=d, start_time=dtime(7), end_time=dtime(20), preference="unavailable",
                                        school_year=SY, semester="1st Sem")
        r = self.gen(teacher_choices={str(self._sub().id): t.id})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("no available teaching time", r.data["detail"])

    def test_registrar_cannot_choose_professors(self):
        gsub = Subject.objects.create(code="GE9", title="Gen Ed", program=self.prog, lec_units=3, lab_units=0,
                                      year_level="1st Year", semester="1st Sem", classification="minor")
        r = self.gen(user=self.registrar, teacher_choices={str(gsub.id): self.teachers[0].id})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("Only a Dean", r.data["detail"])

    def test_lecture_and_lab_keep_one_professor(self):
        lec = Subject.objects.create(code="LL1", title="Programming", program=self.prog, lec_units=2, lab_units=0,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        lab = Subject.objects.create(code="LL1L", title="Programming Lab", program=self.prog, lec_units=0, lab_units=1,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        for i in range(2):
            Room.objects.create(name=f"LB-{i}", capacity=60, room_type="lab")
        a, b = self.teachers[2], self.teachers[4]
        r = self.gen(teacher_choices={str(lec.id): a.id, str(lab.id): b.id})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("same professor", r.data["detail"])
        r = self.gen(teacher_choices={str(lec.id): a.id})                           # one choice covers the pair
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual({x.teacher_id for x in Schedule.objects.filter(subject__in=[lec, lab])}, {a.id})
        row = next(x for x in self.opts().data["subjects"] if x["code"] == "LL1")
        self.assertEqual(row["partner_id"], lab.id)


class TimeWindowRuleTests(Base):
    """The preview's in-row hint uses Subject.need_minutes; it must be exactly the window length Generate accepts."""

    def _need(self, sub, user=None):
        self.client.force_authenticate(user or self.dean)
        r = self.client.get(f"/api/curriculum/subjects/{sub.id}/")
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        return r.data["need_minutes"]

    @staticmethod
    def _hhmm(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    def _accepts(self, sub, minutes, user=None, program=None):
        r = self.gen(user=user, program_id=(program or self.prog).id,
                     time_windows={str(sub.id): {"start": "07:00", "end": self._hhmm(420 + minutes)}})
        if r.status_code == 400:
            self.assertIn("unbroken", r.data["detail"])
            return False
        self.assertEqual(r.status_code, 201, r.data)
        return True

    def test_need_minutes_matches_what_generate_accepts(self):
        lec2 = Subject.objects.create(code="W2", title="Two Hour", program=self.prog, lec_units=2, lab_units=0,
                                      year_level="1st Year", semester="1st Sem", classification="major")
        lab = Subject.objects.create(code="W3L", title="Lab", program=self.prog, lec_units=0, lab_units=1,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        Room.objects.create(name="LB-W", capacity=60, room_type="lab")
        for sub, want in ((lec2, 120), (lab, 180), (Subject.objects.get(code="TST100"), 180)):
            need = self._need(sub)
            self.assertEqual(need, want)
            self.assertFalse(self._accepts(sub, need - 30))            # 30 minutes short: refused, as the hint says
            self.assertTrue(self._accepts(sub, need))                  # exactly the need: accepted, the hint is silent

    def test_nursing_pair_lecture_needs_one_and_a_half_hours(self):
        nprog = Program.objects.create(name="BS Nursing T", department="Nursing")
        Section.objects.create(name="N1", program=nprog, year_level="1st Year", semester="1st Sem", student_count=20)
        sub = Subject.objects.create(code="NCM9", title="Care", program=nprog, lec_units=3, lab_units=0,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        ndean = User.objects.create(username="DNW", school_id="DNW", role="faculty", faculty_type="dean", department="Nursing")
        need = self._need(sub, ndean)
        self.assertEqual(need, 90)                                     # the old browser rule said 180 and hid valid windows
        self.assertFalse(self._accepts(sub, 60, ndean, nprog))
        self.assertTrue(self._accepts(sub, 90, ndean, nprog))


class RoomFreeHoursTests(Base):
    """Room dropdown of the Generate preview: free hours per room in the semester (read-only, a shared class once) and, per subject,
    only the rooms Generate accepts."""
    URL = "/api/rooms/preview-choices/"

    def get(self, user=None, **q):
        self.client.force_authenticate(user or self.dean)
        r = self.client.get(self.URL, q)
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        return r.data

    def _room(self, data, room):
        return next(x for x in data["rooms"] if x["id"] == room.id)

    def test_free_hours_count_a_shared_class_once_and_only_this_semester(self):
        week = TimeSlot.objects.count()                                   # Mon-Fri 7:00-20:00, hourly: 65 hours
        room = self.rooms[1]
        self.row(room=room, day="Mon", h=7); self.row(room=room, day="Mon", h=8)          # 2 h
        for sec in self.sec:                                                                # a SHARED class: 2 sections, 1 slot -> 1 h
            self.row(sec=sec, room=room, day="Tue", h=10, subj=1, merge="shared-x", teacher=self.teachers[2])
        sec2 = Section.objects.create(name="Z", program=self.prog, year_level="1st Year", semester="2nd Sem", student_count=10)
        self.row(sec=sec2, room=room, day="Wed", h=9, subj=2, teacher=self.teachers[3])  # 2nd Sem: not counted for 1st Sem
        d = self.get(semester="1st Sem")
        self.assertEqual(d["week_hours"], week)
        self.assertEqual(self._room(d, room)["free_hours"], week - 3)
        self.assertEqual(self._room(d, self.rooms[0])["free_hours"], week)              # no class: fully free
        self.assertEqual(self._room(self.get(semester="2nd Sem"), room)["free_hours"], week - 1)

    def test_half_hour_slots_do_not_double_the_week(self):
        week = TimeSlot.objects.count()
        TimeSlot.objects.create(day="Mon", start_time=dtime(7), end_time=dtime(7, 30))   # overlaps an hourly slot
        self.assertEqual(self.get(semester="1st Sem")["week_hours"], week)

    def test_extras_are_read_only_and_optional(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.row(room=self.rooms[1])
        with CaptureQueriesContext(connection) as ctx:
            self.get(program_id=self.prog.id, year_level="1st Year", semester="1st Sem")
        writes = [q["sql"] for q in ctx.captured_queries if q["sql"].split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]
        self.assertEqual(writes, [])
        plain = self.get()
        self.assertNotIn("free_hours", plain["rooms"][0]); self.assertNotIn("allowed", plain)   # old callers unchanged

    def test_allowed_rooms_are_exactly_what_generate_accepts(self):
        lab = Room.objects.create(name="LAB-Y", capacity=40, room_type="lab")
        nurse = Room.objects.create(name="NR-1", capacity=40, room_type="lecture", department="Nursing")
        lab_sub = Subject.objects.create(code="TL1L", title="Lab", program=self.prog, lec_units=0, lab_units=1, year_level="1st Year",
                                         semester="1st Sem", classification="major")
        d = self.get(program_id=self.prog.id, year_level="1st Year", semester="1st Sem")
        lec_ok = set(d["allowed"][Subject.objects.get(code="TST100").id])
        self.assertIn(self.rooms[0].id, lec_ok); self.assertNotIn(lab.id, lec_ok); self.assertNotIn(nurse.id, lec_ok)
        self.assertEqual(set(d["allowed"][lab_sub.id]) & {r.id for r in self.rooms}, set())
        sub = Subject.objects.get(code="TST100")
        for rid in [x["id"] for x in d["rooms"]]:                                 # each listed room: allowed <=> Generate accepts it
            r = self.gen(room_choices={str(sub.id): rid})
            self.assertEqual(r.status_code != 400, rid in lec_ok, (rid, getattr(r, "data", None)))
            Schedule.objects.all().delete()


class DesignatedRoomFreeHoursTests(DesignatedRoomTests):
    """Computer Studies majors: the Room dropdown offers only Comp Lab C / D, for lectures and labs alike."""

    def test_cs_majors_are_offered_only_the_designated_rooms(self):
        self.client.force_authenticate(self.dean)
        d = self.client.get("/api/rooms/preview-choices/", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem"}).data
        for sub in (self.lec, self.lab):
            self.assertEqual(set(d["allowed"][sub.id]), {self.labC.id, self.labD.id})
        self.assertNotIn(self.gen_ed.id, d["allowed"])                            # the Dean does not choose Gen Ed rooms
        self.client.force_authenticate(self.reg)
        r = self.client.get("/api/rooms/preview-choices/", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem"}).data
        self.assertEqual(set(r["allowed"]), {self.gen_ed.id})
        self.assertTrue(set(r["allowed"][self.gen_ed.id]) >= {x.id for x in self.lect})   # the Registrar's Gen Ed: ordinary rooms offered


class RejectedChoiceKeepsDraftsTests(Base):
    """A Generate refused because of a bad Room / Start / End choice changes nothing: the earlier drafts stay."""

    def test_bad_room_or_time_choice_keeps_the_existing_drafts(self):
        r = self.gen()
        self.assertEqual(r.status_code, 201, r.data)
        before = sorted(Schedule.objects.values_list("pk", flat=True))
        self.assertTrue(before)
        sub = Subject.objects.get(code="TST100")
        lab = Room.objects.create(name="LAB-R", capacity=40, room_type="lab")
        for body in ({"room_choices": {str(sub.id): lab.id}},                                   # a lecture in a lab
                     {"room_choices": {str(sub.id): 999999}},                                   # no such room
                     {"time_windows": {str(sub.id): {"start": "07:00", "end": "08:00"}}},     # too short for 3 h
                     {"time_windows": {str(sub.id): {"start": "15:00", "end": "09:00"}}}):    # end before start
            r = self.gen(**body)
            self.assertEqual(r.status_code, 400, r.data)
            self.assertEqual(sorted(Schedule.objects.values_list("pk", flat=True)), before, body)


class AlliedHealthQualificationTests(APITestCase):
    """Allied Health majors match teachers by discipline (Physical / Occupational / Respiratory Therapy, Anatomy, Pharmacology ...),
    inside the subject's own college only; Gen Ed and other colleges keep their behaviour."""
    AH = "College of Allied Health"

    def teacher(self, n, specs, dept=None, degree=""):
        u = User.objects.create(username=f"AH{n}", school_id=f"AH{n}", first_name="A", last_name=f"H{n}", role="faculty",
                                faculty_type="full_time", department=dept or self.AH)
        p = FacultyProfile.objects.create(user=u, degree=degree)
        p.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in specs])
        return FacultyProfile.objects.select_related("user").prefetch_related("specializations").get(pk=p.pk)

    def subject(self, prog, code, title, kind="major"):
        return Subject.objects.create(code=code, title=title, program=prog, lec_units=3, lab_units=0, year_level="1st Year",
                                      semester="1st Sem", classification=kind)

    def ok(self, t, s):
        from engine.qualification import is_qualified
        sec = Section(name="X", program=s.program, year_level="1st Year", semester="1st Sem", student_count=20)
        return is_qualified(t, s, sec, {f.id for f in t.specializations.all()})

    def setUp(self):
        self.pt = Program.objects.create(name="BS Physical Therapy", department=self.AH)
        self.ot = Program.objects.create(name="BS Occupational Therapy", department=self.AH)
        self.rt = Program.objects.create(name="BS Respiratory Therapy", department=self.AH)
        self.rad = Program.objects.create(name="BS Radiologic Technology", department="College of Radiologic Technology")

    def test_program_discipline_matches_its_specialists(self):
        ptx = self.teacher(1, ["Musculoskeletal Physical Therapy", "Kinesiology"])
        otx = self.teacher(2, ["Occupational Therapy", "Mental Health OT"])
        pt_sub = self.subject(self.pt, "PT3116", "Musculoskeletal Physical Therapy - Lec")
        ot_sub = self.subject(self.ot, "OT2210", "OT in Mental Health 1 - Lec")
        pt_intro = self.subject(self.pt, "PT1101A", "Introduction to Physical Therapy")
        self.assertTrue(self.ok(ptx, pt_sub)); self.assertTrue(self.ok(ptx, pt_intro))
        self.assertTrue(self.ok(otx, ot_sub))
        self.assertFalse(self.ok(otx, pt_intro))                         # an OT specialist is not a Physical Therapy teacher
        self.assertFalse(self.ok(ptx, ot_sub))
        rt_sub = self.subject(self.rt, "RT1101", "Introduction to Respiratory Therapy")
        self.assertFalse(self.ok(ptx, rt_sub)); self.assertFalse(self.ok(otx, rt_sub))
        self.assertTrue(self.ok(self.teacher(3, [], degree="BS Respiratory Therapy, RRT"), rt_sub))

    def test_basic_science_specialists_match_those_subjects_in_any_allied_health_program(self):
        ana = self.teacher(4, ["Anatomy", "Physiology"])
        pharm = self.teacher(5, ["Pathophysiology", "Pharmacology"])
        gross = self.subject(self.ot, "MOTPT1203", "Gross and Organ System Anatomy - Lec")
        cr_ap = self.subject(self.rt, "RT2104", "Cardio-Respiratory Anatomy and Physiology")
        rt_ph = self.subject(self.rt, "RT2108", "Cardio-Respiratory Pharmacology")
        neuro_patho = self.subject(self.rt, "RT2109", "Neuroanatomy and Pathophysiology")
        self.assertTrue(self.ok(ana, gross)); self.assertTrue(self.ok(ana, cr_ap))
        self.assertTrue(self.ok(pharm, rt_ph)); self.assertTrue(self.ok(pharm, neuro_patho))
        self.assertFalse(self.ok(ana, rt_ph)); self.assertFalse(self.ok(pharm, gross))
        self.assertFalse(self.ok(ana, self.subject(self.ot, "OT2210", "OT in Mental Health 1 - Lec")))

    def test_other_colleges_and_gen_ed_are_not_affected(self):
        rad_sub = self.subject(self.rad, "RAD3118", "Radiologic Pathology")
        self.assertFalse(self.ok(self.teacher(6, ["Pathophysiology"]), rad_sub))             # Allied Health teacher, RadTech major
        outsider = self.teacher(7, ["Physical Therapy"], dept="College of Nursing")
        self.assertFalse(self.ok(outsider, self.subject(self.pt, "PT1101A", "Introduction to Physical Therapy")))
        from engine.qualification import _subject_info
        pathfit = self.subject(self.pt, "PATHFIT1", "Physical Activities Toward Health and Fitness 1", kind="minor")
        self.assertNotIn("physical_therapy", _subject_info(pathfit)["fams"])                  # PE is not Physical Therapy
        cs = Program.objects.create(name="BS Computer Science", department="College of Computer Studies")
        self.assertFalse(self.ok(self.teacher(8, ["Research Methods"], dept="College of Computer Studies"),
                                 self.subject(cs, "CS3122", "Fundamentals of Accounting")))


class FacultyAvailabilityGenerationTests(Base):
    """Generation follows each teacher's submitted availability (hard), tries "preferred" windows first (soft), skips what cannot
    be placed with a specific reason, and "Generate only the missing ones" leaves everything already placed alone."""

    def setUp(self):
        from faculty.models import Availability
        self.Av = Availability
        self.prog2 = Program.objects.create(name="BS CS Avail", department=DEPT)
        self.sec2 = Section.objects.create(name="V1", program=self.prog2, year_level="1st Year", semester="1st Sem", student_count=30)
        self.subs = [Subject.objects.create(code=f"AV{i}", title=f"Avail Subject {i}", program=self.prog2, lec_units=3, lab_units=0,
                                            year_level="1st Year", semester="1st Sem", classification="major") for i in range(3)]
        self.t = self.teachers[0]
        FacultyProfile.objects.filter(pk__in=[x.pk for x in self.teachers[1:]]).update(degree="")   # only one qualified teacher

    def gen2(self, **over):
        return self.gen(program_id=self.prog2.id, **over)

    def window(self, day, a, b, pref="available", sy=SY, sem="1st Sem"):
        return self.Av.objects.create(faculty=self.t, day=day, start_time=dtime(a), end_time=dtime(b), preference=pref,
                                      school_year=sy, semester=sem)

    def rows(self):
        return list(Schedule.objects.filter(section=self.sec2).select_related("timeslot"))

    def test_classes_stay_inside_the_teachers_windows_and_the_rest_are_skipped_with_the_reason(self):
        self.window("Tuesday", 8, 14)                                           # 6 hours: room for two 3-hour lectures
        r = self.gen2()
        self.assertEqual(r.status_code, 201, r.data)
        rows = self.rows()
        self.assertTrue(rows)
        for x in rows:
            self.assertEqual(x.timeslot.day, "Tue"); self.assertGreaterEqual(x.timeslot.start_time, dtime(8))
            self.assertLessEqual(x.timeslot.end_time, dtime(14))
        self.assertEqual(len({x.subject_id for x in rows}), 2)                  # two placed as drafts ...
        self.assertTrue(all(x.status == "draft" for x in rows))
        reasons = [c["reason"] for c in r.data["conflicts"]]
        self.assertEqual(len(reasons), 1)                                        # ... one skipped, with a specific reason
        self.assertIn("available only Tue 8:00 AM-2:00 PM", reasons[0])
        self.assertIn("3-hour block", reasons[0])
        self.assertNotIn("suggest", reasons[0].lower())                          # the reason only: no suggested times
        self.assertEqual(scan()["total"], 0)

    def test_an_unavailable_window_blocks(self):
        for d in ("Monday", "Tuesday", "Wednesday", "Thursday"):
            self.window(d, 7, 20, pref="unavailable")
        r = self.gen2()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(self.rows())
        self.assertEqual({x.timeslot.day for x in self.rows()}, {"Fri"})

    def test_preferred_window_is_tried_first_but_never_excludes(self):
        for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
            self.window(d, 7, 20)
        self.window("Thursday", 14, 17, pref="preferred")
        Subject.objects.filter(pk__in=[x.pk for x in self.subs[1:]]).delete()     # one 3-hour class
        r = self.gen2()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual({(x.timeslot.day, x.timeslot.start_time.hour) for x in self.rows()}, {("Thu", 14), ("Thu", 15), ("Thu", 16)})
        Schedule.objects.all().delete()
        for sl in TimeSlot.objects.filter(day="Thu", start_time__gte=dtime(14), start_time__lt=dtime(17)):  # preferred time taken
            Schedule.objects.create(subject=Subject.objects.get(code="TST100"), section=self.sec[0], teacher=self.t, room=self.rooms[0],
                                    timeslot=sl, status="approved", term="1st Sem")
        r = self.gen2()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(self.rows()), 3)                                    # still placed, outside the preferred window
        self.assertFalse(r.data["conflicts"])

    def test_no_submission_means_free_at_any_time(self):
        r = self.gen2()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len({x.subject_id for x in self.rows()}), 3)
        self.assertFalse(r.data["conflicts"])

    def test_availability_saved_without_a_term_still_applies(self):
        self.window("Wednesday", 7, 20, sy="", sem="")                            # e.g. a Saturday-only teacher's row with no term
        r = self.gen2()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(self.rows())
        self.assertEqual({x.timeslot.day for x in self.rows()}, {"Wed"})

    def test_generate_only_the_missing_ones_leaves_placed_classes_alone(self):
        self.window("Tuesday", 8, 14)
        self.gen2()
        placed = {x.pk: (x.subject_id, x.timeslot_id, x.teacher_id, x.room_id) for x in self.rows()}
        subs_placed = sorted({v[0] for v in placed.values()})
        Schedule.objects.filter(subject_id=subs_placed[0], section=self.sec2).update(status="approved")
        Schedule.objects.filter(subject_id=subs_placed[1], section=self.sec2).update(is_manual_override=True)
        shared = Subject.objects.create(code="GEX9", title="Shared GE", program=self.prog2, lec_units=1, lab_units=0,
                                        year_level="1st Year", semester="1st Sem", classification="minor")
        sh = Schedule.objects.create(subject=shared, section=self.sec2, teacher=self.teachers[5], room=self.rooms[3], merge_key="sh-1",
                                     timeslot=TimeSlot.objects.get(day="Fri", start_time=dtime(15)), term="1st Sem")
        self.Av.objects.all().delete()                                           # the teacher is free again
        r = self.gen2(only_missing=True)
        self.assertEqual(r.status_code, 201, r.data)                             # approved classes do not block this mode
        self.assertTrue(r.data["only_missing"])
        now = {x.pk: (x.subject_id, x.timeslot_id, x.teacher_id, x.room_id) for x in self.rows()}
        for pk, v in placed.items():
            self.assertEqual(now.get(pk), v)                                     # every placed class exactly where it was
        self.assertEqual(Schedule.objects.get(pk=sh.pk).merge_key, "sh-1")
        self.assertEqual(len({v[0] for v in now.values() if v[0] != shared.id}), 3)   # the missing one is now placed
        self.assertFalse(r.data["conflicts"])
        self.assertEqual(scan()["total"], 0)

    def test_not_generated_list_gives_the_reason(self):
        self.window("Tuesday", 8, 14)
        self.gen2()
        self.client.force_authenticate(self.dean)
        d = self.client.get("/api/engine/unplaced/", {"semester": "1st Sem", "program_id": self.prog2.id, "year_level": "1st Year"}).data
        self.assertEqual(d["total"], 1)
        self.assertIn("available only Tue", d["items"][0]["reason"])
        Section.objects.create(name="V2", program=self.prog2, year_level="2nd Year", semester="1st Sem", student_count=10)
        Subject.objects.create(code="AV9", title="Later", program=self.prog2, lec_units=2, lab_units=0, year_level="2nd Year",
                               semester="1st Sem", classification="major")
        d = self.client.get("/api/engine/unplaced/", {"semester": "1st Sem", "program_id": self.prog2.id, "year_level": "2nd Year"}).data
        self.assertEqual(d["items"][0]["reason"], "Not generated yet.")


class FacultyTimeEndpointTests(Base):
    """GET /api/engine/generate/faculty-time/: a teacher's availability, load and classes; read-only and role-limited."""
    URL = "/api/engine/generate/faculty-time/"

    def get(self, user, fid, **q):
        self.client.force_authenticate(user)
        return self.client.get(self.URL, {"faculty_id": fid, "semester": "1st Sem", **q})

    def test_dean_sees_own_college_registrar_sees_all_others_refused(self):
        t = self.teachers[0]
        self.assertEqual(self.get(self.dean, t.id).status_code, 200)
        self.assertEqual(self.get(self.registrar, t.id).status_code, 200)
        self.assertEqual(self.get(self.teachers[1].user, t.id).status_code, 403)
        nurse = make_teacher(70)
        User.objects.filter(pk=nurse.user_id).update(department="Nursing")
        self.assertEqual(self.get(self.dean, nurse.id).status_code, 403)              # another college's teacher
        self.assertEqual(self.get(self.registrar, nurse.id).status_code, 200)
        self.assertEqual(self.get(self.dean, 999999).status_code, 404)

    def test_contents_and_no_writes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from faculty.models import Availability
        t = self.teachers[0]
        d = self.get(self.dean, t.id).data
        self.assertFalse(d["submitted"]); self.assertEqual(d["teaching"], []); self.assertEqual(d["current_hours"], 0)
        Availability.objects.create(faculty=t, day="Saturday", start_time=dtime(7), end_time=dtime(16, 30), preference="available")
        Availability.objects.create(faculty=t, day="Monday", start_time=dtime(8), end_time=dtime(12), preference="preferred",
                                    school_year=SY, semester="1st Sem")
        Availability.objects.create(faculty=t, day="Tuesday", start_time=dtime(8), end_time=dtime(12), preference="available",
                                    school_year=SY, semester="2nd Sem")                       # other semester: not shown
        for h in (9, 10, 11):                                                              # one 3-hour class: one block
            self.row(teacher=t, day="Wed", h=h)
        for sec in self.sec:                                                               # a shared class: counted once
            self.row(sec=sec, teacher=t, day="Thu", h=13, subj=1, merge="shared-t", room=self.rooms[1])
        Schedule.objects.filter(teacher=t).update(term="1st Sem")
        with CaptureQueriesContext(connection) as ctx:
            d = self.get(self.dean, t.id).data
        self.assertEqual([q["sql"] for q in ctx.captured_queries if q["sql"].split()[0].upper() in ("INSERT", "UPDATE", "DELETE")], [])
        self.assertTrue(d["submitted"])
        self.assertEqual({(w["day"], w["start"], w["end"], w["preference"]) for w in d["availability"]},
                         {("Sat", "07:00", "16:30", "available"), ("Mon", "08:00", "12:00", "preferred")})
        self.assertEqual(d["current_hours"], 4.0); self.assertEqual(d["max_hours"], 24)
        self.assertEqual([(b["day"], b["start"], b["end"], b["code"]) for b in d["teaching"]],
                         [("Wed", "09:00", "12:00", "TST100"), ("Thu", "13:00", "14:00", "TST101")])     # Mon -> Sat order
        # with the Generate scope: the drafts that Generate would replace are not counted (same as the Professor list)
        d = self.get(self.dean, t.id, program_id=self.prog.id, year_level="1st Year").data
        self.assertEqual(d["current_hours"], 0); self.assertEqual(d["teaching"], [])


class SuggestedProfessorDataTests(Base):
    """The Professor list sends each qualified teacher's free week (availability minus their classes) and each subject's blocks,
    so the dropdown can suggest who fits. Read-only; the server still re-checks every choice on Generate."""

    def opts(self):
        self.client.force_authenticate(self.dean)
        r = self.client.get("/api/engine/generate/professor-options/", {"program_id": self.prog.id, "year_level": "1st Year", "semester": "1st Sem"})
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def test_free_week_and_blocks(self):
        from faculty.models import Availability
        t0, t1, t2 = self.teachers[0], self.teachers[1], self.teachers[2]
        Availability.objects.create(faculty=t0, day="Tuesday", start_time=dtime(8), end_time=dtime(12), preference="preferred",
                                    school_year=SY, semester="1st Sem")
        Availability.objects.create(faculty=t2, day="Wednesday", start_time=dtime(7), end_time=dtime(20), preference="unavailable")
        prog2 = Program.objects.create(name="BS CS Other", department=DEPT)
        sec2 = Section.objects.create(name="Z1", program=prog2, year_level="2nd Year", semester="1st Sem", student_count=10)
        s2 = Subject.objects.create(code="ZZ1", title="Z", program=prog2, lec_units=1, lab_units=0, year_level="2nd Year",
                                    semester="1st Sem", classification="major")
        Schedule.objects.create(subject=s2, section=sec2, teacher=t0, room=self.rooms[3], term="1st Sem",
                                timeslot=TimeSlot.objects.get(day="Tue", start_time=dtime(9)))       # busy Tue 9-10
        d = self.opts()
        a = d["teachers"][t0.id]
        self.assertTrue(a["submitted"])
        self.assertEqual(a["free"], {"Tue": [[480, 540], [600, 720]]})                     # 8-9 and 10-12 only
        self.assertEqual(a["preferred"], {"Tue": [[480, 720]]})
        b = d["teachers"][t1.id]
        self.assertFalse(b["submitted"])
        self.assertEqual(b["free"]["Mon"], [[420, 1200]])                                  # nothing submitted: the whole grid
        self.assertNotIn("Wed", d["teachers"][t2.id]["free"])                              # an unavailable day is not free
        row = next(x for x in d["subjects"] if x["code"] == "TST100")
        self.assertEqual(row["blocks"], [180])


class CandidateBlockerReportTests(Base):
    """A class skipped inside the Dean's Start / End range: the reason comes from engine.blockers, which checks every candidate period
    on the 30-minute grid and names the rule that rules each one out. It never blames the professor's time when the professor is
    free and a missing time slot, a booked room or the section's own class is the blocker. (Reporting only: placement is unchanged.)"""

    def setUp(self):
        from faculty.models import Availability
        TimeSlot.objects.filter(start_time=dtime(12)).delete()                  # a hole at 12:00-1:00 PM (a table seeded the OLD way)
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri"):
            for m in list(range(420, 720, 30)) + list(range(780, 1200, 30)):
                TimeSlot.objects.get_or_create(day=d, start_time=dtime(m // 60, m % 60), end_time=dtime((m + 30) // 60, (m + 30) % 60))
        self.prog3 = Program.objects.create(name="BS CS Blockers", department=DEPT)
        self.sec3 = Section.objects.create(name="Z4", program=self.prog3, year_level="4th Year", semester="1st Sem", student_count=20)
        self.sub = Subject.objects.create(code="ZZ131", title="Project Management - Lec", program=self.prog3, lec_units=2, lab_units=0,
                                          year_level="4th Year", semester="1st Sem", classification="major")
        self.t = self.teachers[0]
        for day, a, b in (("Monday", (10, 0), (13, 0)), ("Friday", (7, 0), (16, 30))):     # like Mazo: Mon 10-1, Sat 7-4:30
            Availability.objects.create(faculty=self.t, day=day, start_time=dtime(*a), end_time=dtime(*b), preference="preferred",
                                        school_year=SY, semester="1st Sem")

    def gen3(self, start, end, teacher=True):
        body = {"time_windows": {str(self.sub.id): {"start": start, "end": end}}}
        if teacher:
            body["teacher_choices"] = {str(self.sub.id): self.t.id}
        return self.gen(program_id=self.prog3.id, year_level="4th Year", **body)

    def test_missing_noon_slot_is_named_and_the_free_professor_is_not_blamed(self):
        r = self.gen3("10:30", "13:00")                                         # 2.5 h range, professor free Mon and Fri in it
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(Schedule.objects.filter(section=self.sec3).exists())    # nothing forced in
        reason = r.data["conflicts"][0]["reason"]
        self.assertIn("class time slot at 12:00 PM", reason)
        self.assertNotIn("lunch", reason)                                       # lunch is not a rule any more
        self.assertIn("Mon, Tue, Wed, Thu, Fri 10:30 AM-12:30 PM: there is no 30-minute class time slot at 12:00 PM-12:30 PM", reason)
        self.assertIn("Mon, Tue, Wed, Thu, Fri 11:00 AM-1:00 PM: there is no hourly class time slot at 12:00 PM-1:00 PM", reason)
        self.assertNotIn("not available", reason)                               # he IS free then: the old message blamed him
        self.assertNotIn("available only", reason)

    def test_a_range_that_fits_is_placed_as_before(self):
        r = self.gen3("10:00", "13:00")                                         # 10:00-12:00 Mon fits everything
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data["conflicts"])
        rows = Schedule.objects.filter(section=self.sec3).select_related("timeslot")
        self.assertEqual({(x.timeslot.day, x.timeslot.start_time) for x in rows}, {("Mon", dtime(10)), ("Mon", dtime(11))})

    def test_three_hour_range_over_a_missing_noon_slot_says_why_no_period_fits(self):
        r = self.gen3("10:30", "13:30", teacher=False)
        self.assertEqual(r.status_code, 201, r.data)
        reason = r.data["conflicts"][0]["reason"]
        self.assertIn("fits inside your 10:30 AM-1:30 PM range on any day", reason)
        self.assertIn("class time slot at 12:00 PM", reason)
        self.assertNotIn("lunch", reason)

    def _report(self, assigned, window=(480, 600), availability_rules=None):
        from engine import blockers, scheduler as sc
        ts = list(TimeSlot.objects.all())
        blocks = sc.with_half_blocks(sc.build_block_slots(ts, 2), window)
        rep = blockers.report(self.sec3, self.sub, 2, window, ts, blocks, assigned, [self.t], self.rooms[:2],
                              availability_rules or {}, chosen=self.t)
        return {(c["day"], c["start"]): c["blockers"] for c in rep}, rep

    def test_report_lists_every_candidate_with_the_failing_rule(self):
        from engine import scheduler as sc
        from engine.views import _build_availability_rules
        ts = list(TimeSlot.objects.all())
        fri = {h: TimeSlot.objects.get(day="Fri", start_time=dtime(h), end_time=dtime(h + 1)) for h in (8, 9)}
        tue8 = TimeSlot.objects.get(day="Tue", start_time=dtime(8), end_time=dtime(9))
        other = Subject.objects.get(code="TST100")
        assigned = [sc.Assignment(other, self.sec[0], self.teachers[1], self.rooms[i], fri[h]) for i in (0, 1) for h in (8, 9)]
        assigned.append(sc.Assignment(other, self.sec3, self.teachers[1], self.rooms[3], tue8))      # the section's own class
        rules = _build_availability_rules([self.t], ts, SY, "1st Sem")
        by, rep = self._report(assigned, availability_rules=rules)
        self.assertEqual(len(rep), 5 * 1)                                       # 8:00-10:00 is the only 2-hour start in 8-10, each day
        cat = lambda d: [b[0] for b in by[(d, 480)]]
        self.assertEqual(cat("Fri"), ["room busy"])                             # professor free (Fri 7-4:30), both allowed rooms taken
        self.assertIn("N-101 has TST100 (T1A)", by[("Fri", 480)][0][1])
        self.assertIn("N-102 has TST100 (T1A)", by[("Fri", 480)][0][1])
        self.assertEqual(cat("Tue")[0], "section busy")                         # the section's own class is named first
        self.assertIn("Z4 already has TST100", by[("Tue", 480)][0][1])
        self.assertEqual(cat("Mon"), ["teacher availability"])                  # Mon 8-10 is outside his Mon 10-1: only then is it his time
        from engine import blockers
        msg = blockers.summary(rep, 2, (480, 600), what="Lecture", chosen_name="Teach Er1")
        self.assertIn("Fri 8:00 AM-10:00 AM: N-101 has TST100 (T1A); N-102 has TST100 (T1A)", msg)
        self.assertIn("Mon, Tue, Wed, Thu 8:00 AM-10:00 AM: Teach Er1 is not available then", msg)   # every blocker is listed, Tue too

    def test_report_names_the_professors_own_class(self):
        from engine import scheduler as sc
        fri = [TimeSlot.objects.get(day="Fri", start_time=dtime(h), end_time=dtime(h + 1)) for h in (8, 9)]
        assigned = [sc.Assignment(Subject.objects.get(code="TST101"), self.sec[1], self.t, self.rooms[2], s) for s in fri]
        by, _ = self._report(assigned)
        self.assertEqual(by[("Fri", 480)], [("teacher already teaching", f"{self.t.user.get_full_name()} is already teaching TST101 (T1B)")])
        self.assertEqual(by[("Tue", 480)], [])                                  # nothing blocks Tue: summary() then gives no text
        from engine import blockers
        self.assertEqual(blockers.summary(_, 2, (480, 600)), "")

    def test_the_exact_cs4131_case_names_the_missing_slot_and_only_then_his_time(self):
        TimeSlot.objects.create(day="Thu", start_time=dtime(12), end_time=dtime(13))   # the one extra noon slot (live data has it)
        r = self.gen3("10:30", "13:00")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(Schedule.objects.filter(section=self.sec3).exists())
        reason = r.data["conflicts"][0]["reason"]
        self.assertIn("Mon, Tue, Wed, Fri 11:00 AM-1:00 PM: there is no hourly class time slot at 12:00 PM-1:00 PM", reason)
        self.assertNotIn("lunch", reason)                                        # Mon/Fri, his days: the missing slot, not his time
        self.assertIn("Thu 11:00 AM-1:00 PM: Teach Er1 is not available then", reason)
        self.assertNotIn("Mon 10:30 AM-12:30 PM: Teach Er1", reason)


class DepartmentTeacherScopeTests(Base):
    """engine.teacher_scope: a Dean's major class goes only to qualified faculty of the Dean's own department(s) -- listed, suggested
    and accepted -- on every endpoint that sets a teacher; Gen Ed (the Registrar's) keeps "any qualified teacher"."""

    def setUp(self):
        from django.db import connection
        self.conn = connection
        self.other = make_teacher(90)                                   # a computing degree (would qualify) but another college
        self.other.user.department = "College of Allied Health"
        self.other.user.save()
        self.unq = make_teacher(91)                                     # own college, unrelated degree
        self.unq.degree = "BS Tourism"
        self.unq.save()
        field = AcademicField.objects.create(name="Scope Field")       # a recorded specialization: qualified under every rule
        Subject.objects.filter(program=self.prog).update(field=field)
        for p in list(self.teachers) + [self.other]:
            p.specializations.add(field)
        self.sub = Subject.objects.get(code="TST100")
        self.rows = [Schedule.objects.create(subject=self.sub, section=self.sec[0], teacher=self.teachers[0], room=self.rooms[0],
                                             timeslot=TimeSlot.objects.get(day="Mon", start_time=dtime(h)), term="1st Sem")
                     for h in (7, 8, 9)]
        self.ids = ",".join(str(r.id) for r in self.rows)

    def opts(self, user=None, ids=None):
        self.client.force_authenticate(user or self.dean)
        return self.client.get("/api/engine/teacher-options/", {"schedule_ids": ids or self.ids})

    def test_dean_list_is_own_department_qualified_only(self):
        r = self.opts()
        self.assertEqual(r.status_code, 200, r.data)
        ids = {t["id"] for t in r.data["teachers"]}
        self.assertNotIn(self.other.id, ids)                             # other college: not listed at all
        self.assertNotIn(self.unq.id, ids)                               # own college, not qualified: not listed
        self.assertTrue({t.id for t in self.teachers} <= ids)
        t1 = next(t for t in r.data["teachers"] if t["id"] == self.teachers[1].id)
        self.assertTrue(t1["suggested"])
        self.assertIn("max_hours", t1)
        self.assertEqual(t1["school_id"], "T2")

    def test_update_rejects_a_teacher_from_another_department(self):
        self.client.force_authenticate(self.dean)
        r = self.client.patch(f"/api/engine/schedules/{self.rows[0].id}/", {"teacher": self.other.id}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("not a faculty member of Computer Studies", str(r.data))
        self.assertEqual(Schedule.objects.get(pk=self.rows[0].id).teacher_id, self.teachers[0].id)
        r = self.client.patch(f"/api/engine/schedules/{self.rows[0].id}/", {"teacher": self.unq.id}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("not qualified", str(r.data))

    def test_generate_rejects_a_teacher_from_another_department(self):
        Schedule.objects.all().delete()
        r = self.gen(teacher_choices={str(self.sub.id): self.other.id})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("not a faculty member of Computer Studies", r.data["detail"])

    def test_dean_of_two_departments_sees_both(self):
        ah = Program.objects.create(name="BS RT Scope", department="College of Allied Health")
        sec = Section.objects.create(name="R1", program=ah, year_level="1st Year", semester="1st Sem", student_count=20)
        sub = Subject.objects.create(code="RTX1", title="Computing for Therapists", program=ah, lec_units=1, lab_units=0,
                                     year_level="1st Year", semester="1st Sem", classification="major")
        row = Schedule.objects.create(subject=sub, section=sec, teacher=self.other, room=self.rooms[1],
                                      timeslot=TimeSlot.objects.get(day="Tue", start_time=dtime(7)), term="1st Sem")
        self.assertEqual(self.opts(ids=str(row.id)).status_code, 403)    # not their department yet
        self.dean.extra_departments = "College of Allied Health"
        self.dean.save()
        r = self.opts(ids=str(row.id))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual({t["id"] for t in r.data["teachers"]}, {self.other.id})        # Allied Health faculty for an Allied Health major
        self.assertNotIn(self.other.id, {t["id"] for t in self.opts().data["teachers"]})  # Computer Studies faculty for a CS major

    def test_registrar_gen_ed_list_is_unchanged(self):
        ge = Subject.objects.create(code="GEX1", title="Living in the IT Era", program=self.prog, lec_units=1, lab_units=0,
                                    year_level="1st Year", semester="1st Sem", classification="minor")
        row = Schedule.objects.create(subject=ge, section=self.sec[1], teacher=self.teachers[2], room=self.rooms[2],
                                      timeslot=TimeSlot.objects.get(day="Wed", start_time=dtime(7)), term="1st Sem")
        r = self.opts(self.registrar, str(row.id))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn(self.other.id, {t["id"] for t in r.data["teachers"]})             # any qualified teacher, any college
        self.assertEqual(self.opts(ids=str(row.id)).status_code, 403)                   # a Dean cannot edit Gen Ed rows

    def test_overload_suggestions_never_include_another_department(self):
        self.client.force_authenticate(self.dean)
        r = self.client.get("/api/engine/workload/replacements/", {"faculty_id": self.teachers[0].id, "subject_id": self.sub.id,
                                                                   "section_id": self.sec[0].id})
        self.assertEqual(r.status_code, 200, r.data)
        got = [s["faculty_id"] for s in r.data["suggestions"]]
        self.assertTrue(got)
        self.assertNotIn(self.other.id, got)
        loads = [s["current_hours"] for s in r.data["suggestions"]]
        self.assertEqual(loads, sorted(loads))                                            # lower load first
        from engine import workload as wl
        sugg = wl.suggest_replacements(self.sub, "1st Sem", [x.timeslot for x in self.rows], exclude_teacher_ids=[self.teachers[0].id],
                                       limit=50)
        self.assertNotIn(self.other.id, [s["faculty_id"] for s in sugg])                  # with no user too (Smart Resolve, warnings)
        ids = [x.id for x in self.rows]
        r = self.client.post("/api/engine/workload/overload-assign/", {"schedule_ids": ids, "teacher": self.other.id}, format="json")
        self.assertEqual(r.status_code, 422, r.data)
        self.assertIn("not a faculty member", r.data["detail"])
        r = self.client.post("/api/engine/replacements/assign/", {"schedule_ids": ids, "teacher": self.other.id}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("not a faculty member", r.data["detail"])
        self.assertTrue(all(x.teacher_id == self.teachers[0].id for x in Schedule.objects.filter(pk__in=ids)))

    def test_no_available_faculty_in_department_with_reasons(self):
        busy_sub = Subject.objects.get(code="TST101")
        for i, t in enumerate(self.teachers[1:], start=1):              # every other qualified teacher is teaching then
            sec = Section.objects.create(name=f"X{i}", program=self.prog, year_level="1st Year", semester="1st Sem", student_count=5)
            room = Room.objects.create(name=f"BZ-{i}", capacity=60, room_type="lecture")
            for h in (7, 8, 9):
                Schedule.objects.create(subject=busy_sub, section=sec, teacher=t, room=room,
                                        timeslot=TimeSlot.objects.get(day="Mon", start_time=dtime(h)), term="1st Sem")
        self.client.force_authenticate(self.dean)
        r = self.client.get("/api/engine/workload/replacements/", {"faculty_id": self.teachers[0].id, "subject_id": self.sub.id,
                                                                   "section_id": self.sec[0].id})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["suggestions"], [])
        why = r.data["reason_none"]
        self.assertIn("No available faculty in your department (Computer Studies)", why)
        self.assertIn("not free at that time (already teaching TST101", why)
        self.assertIn(f"{self.unq.user.get_full_name()} - not qualified for TST100", why)
        self.assertNotIn(self.other.user.get_full_name(), why)                            # other colleges are not even mentioned

    def test_teacher_options_endpoint_writes_nothing(self):
        from django.test.utils import CaptureQueriesContext
        from engine.models import SchedulingConfig
        SchedulingConfig.objects.all().delete()
        self.client.force_authenticate(self.dean)
        with CaptureQueriesContext(self.conn) as q:
            self.assertEqual(self.opts().status_code, 200)
        writes = [x["sql"] for x in q.captured_queries if x["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [])
        self.assertFalse(SchedulingConfig.objects.exists())


class CasGenEdRuleTests(Base):
    """Gen Ed (minor) subjects go to College of Arts and Science faculty of the subject's area; another department's teacher only with
    an explicit specialization (or the subject's own discipline). Majors unchanged. Existing classes are never changed."""
    CAS = "College of Arts and Science"

    def setUp(self):
        from engine.qualification import is_qualified
        self.q = lambda t, s: is_qualified(t, s, s.program and self.sec[0], {f.id for f in t.specializations.all()})
        self.ge = {code: Subject.objects.create(code=code, title=title, program=self.prog, lec_units=3, lab_units=0, year_level="1st Year",
                                                semester="1st Sem", classification="minor")
                   for code, title in (("GEC108", "Science, Technology & Society"), ("GE602", "World Literature"),
                                       ("GE401", "Filipino Christian Living 1"), ("GEC101", "Art Appreciation"),
                                       ("GEC105", "Mathematics in the Modern World"), ("GE301", "Physical Education 1"))}

    def person(self, sid, dept, specs, ftype="full_time", degree=""):
        u = User(username=f"U-{sid}", school_id=sid, first_name="T", last_name=sid, role="faculty", faculty_type=ftype, department=dept)
        u.set_password("pw")
        u.save()
        p = FacultyProfile.objects.create(user=u, degree=degree)
        p.specializations.set([AcademicField.objects.get_or_create(name=s)[0] for s in specs])
        return p

    def test_non_cas_without_matching_specialization_is_not_qualified(self):
        rt = self.person("X1", "College of Radiologic Technology", ["Radiation Physics"])
        cs = self.teachers[0]                                             # Computer Studies, BS Computer Science
        for code in ("GE602", "GE401", "GEC101", "GEC108", "GE301"):
            self.assertFalse(self.q(rt, self.ge[code]), code)
            self.assertFalse(self.q(cs, self.ge[code]), code)

    def test_cas_teacher_with_the_matching_area_is_qualified(self):
        lit = self.person("C1", self.CAS, ["Major in English Literature"])
        fcl = self.person("C2", self.CAS, ["FCL"], ftype="part_time")
        pe = self.person("C3", self.CAS, ["Physical Education"])
        self.assertTrue(self.q(lit, self.ge["GE602"]))
        self.assertTrue(self.q(fcl, self.ge["GE401"]))
        self.assertTrue(self.q(pe, self.ge["GE301"]))
        self.assertFalse(self.q(lit, self.ge["GE401"]))                   # CAS, but not the subject's area
        self.assertFalse(self.q(fcl, self.ge["GEC108"]))

    def test_non_cas_with_an_explicit_sts_specialization_is_qualified_for_sts(self):
        rt = self.person("X2", "College of Radiologic Technology", ["Radiation Physics", "Science, Technology and Society"])
        self.assertTrue(self.q(rt, self.ge["GEC108"]))
        self.assertFalse(self.q(rt, self.ge["GE602"]))                    # only that area
        mathx = self.person("X3", "College of Computer Studies", ["Major in Mathematics"])
        self.assertTrue(self.q(mathx, self.ge["GEC105"]))                 # the subject's own discipline, any department

    def test_untagged_gen_ed_is_offered_only_to_cas(self):
        odd = Subject.objects.create(code="GEX7", title="Seminar in Leadership", program=self.prog, lec_units=3, lab_units=0,
                                     year_level="1st Year", semester="1st Sem", classification="minor")
        cas_lead = self.person("C4", self.CAS, ["Leadership"])
        other_lead = self.person("X4", "College of Business Administration", ["Leadership"])
        self.assertTrue(self.q(cas_lead, odd))
        self.assertFalse(self.q(other_lead, odd))                          # the old "no field -> anyone" fallback is gone
        self.assertFalse(self.q(self.teachers[0], odd))
        from engine.qualification import why_nobody
        why = why_nobody(self.ge["GEC101"], self.sec[0], list(FacultyProfile.objects.all()), {})
        self.assertIn("No CAS faculty with a Arts / Humanities specialization is available for GEC101", why)

    def test_generation_places_gen_ed_only_with_cas(self):
        Subject.objects.filter(classification="minor").exclude(code="GE602").delete()
        lit = self.person("C5", self.CAS, ["Literature"])
        r = self.gen(user=self.registrar)
        self.assertEqual(r.status_code, 201, r.data)
        rows = Schedule.objects.filter(subject=self.ge["GE602"])
        self.assertTrue(rows.exists())
        self.assertEqual({x.teacher_id for x in rows}, {lit.id})
        lit.specializations.clear()                                                    # nobody in CAS has Literature now
        Schedule.objects.filter(subject=self.ge["GE602"]).delete()
        r = self.gen(user=self.registrar)
        self.assertFalse(Schedule.objects.filter(subject=self.ge["GE602"]).exists())    # nobody else is put in
        self.assertIn("No CAS faculty with a Literature specialization", " ".join(c["reason"] for c in r.data["conflicts"]))

    def test_majors_are_unaffected(self):
        from engine.qualification import is_qualified
        sub = Subject.objects.get(code="TST100")
        self.assertTrue(is_qualified(self.teachers[0], sub, self.sec[0], set()))         # Computer Studies, computing degree
        cas = self.person("C6", self.CAS, ["Literature"], degree="BS Computer Science")
        self.assertFalse(is_qualified(cas, sub, self.sec[0], set()))                     # other college: never a Dean's major

    def test_registrar_gen_ed_overload_suggestions_come_from_cas(self):
        lit = self.person("C7", self.CAS, ["Literature"])
        self.person("X5", "College of Nursing", ["Nursing"])
        row = Schedule.objects.create(subject=self.ge["GE602"], section=self.sec[0], teacher=self.teachers[0], room=self.rooms[0],
                                      timeslot=TimeSlot.objects.get(day="Mon", start_time=dtime(7)), term="1st Sem")
        self.client.force_authenticate(self.registrar)
        r = self.client.get("/api/engine/workload/replacements/", {"faculty_id": self.teachers[0].id, "subject_id": self.ge["GE602"].id,
                                                                   "section_id": self.sec[0].id})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([s["faculty_id"] for s in r.data["suggestions"]], [lit.id])
        r = self.client.get("/api/engine/teacher-options/", {"schedule_ids": str(row.id)})
        self.assertEqual({t["id"] for t in r.data["teachers"]}, {lit.id})                 # Edit dialog list: the same rule
        r = self.client.patch(f"/api/engine/schedules/{row.id}/", {"teacher": self.teachers[1].id}, format="json")
        self.assertEqual(r.status_code, 400, r.data)                                       # Save re-checks it on the server

    def test_audit_changes_nothing_and_lists_the_non_cas_class(self):
        from io import StringIO
        from django.core.management import call_command
        row = Schedule.objects.create(subject=self.ge["GE401"], section=self.sec[0], teacher=self.teachers[0], room=self.rooms[0],
                                      timeslot=TimeSlot.objects.get(day="Tue", start_time=dtime(7)), term="1st Sem", status="approved")
        before = list(Schedule.objects.values_list("id", "teacher_id", "status", "timeslot_id", "room_id"))
        out = StringIO()
        call_command("audit_gened_teachers", stdout=out)
        text = out.getvalue()
        self.assertIn("GE401", text)
        self.assertIn("[approved]", text)
        self.assertIn("NO qualified teacher", text)
        self.assertEqual(list(Schedule.objects.values_list("id", "teacher_id", "status", "timeslot_id", "room_id")), before)
        self.assertEqual(Schedule.objects.get(pk=row.pk).teacher_id, self.teachers[0].id)


class CasGenEdFacultyCommandTests(APITestCase):
    """add_cas_gened_faculty: dry run saves nothing; --apply adds only what is missing; re-running adds nothing; no duplicate IDs;
    no dean / registrar; STS goes to an existing related teacher as a specialization only."""

    def setUp(self):
        self.taken = User(username="UPHM-F2000", school_id="F2000", role="faculty", faculty_type="full_time", department="Nursing")
        self.taken.set_password("x")
        self.taken.save()
        FacultyProfile.objects.create(user=self.taken)
        rt = User(username="UPHM-F2001", school_id="F2001", first_name="Rad", last_name="Phys", role="faculty", faculty_type="full_time",
                  department="College of Radiologic Technology")
        rt.set_password("keep-me")
        rt.save()
        self.rt = FacultyProfile.objects.create(user=rt)
        self.rt.specializations.add(AcademicField.objects.create(name="Radiation Physics"))
        for n in ("FCL", "Literature", "Science", "Physical Education", "Biochemistry", "Religious Education", "Major in Literature",
                  "BA in Physical Education"):
            AcademicField.objects.get_or_create(name=n)

    def run_cmd(self, *a):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("add_cas_gened_faculty", *a, stdout=out)
        return out.getvalue()

    def test_dry_run_apply_and_rerun(self):
        n_users = User.objects.count()
        text = self.run_cmd()
        self.assertIn("DRY RUN", text)
        self.assertEqual(User.objects.count(), n_users)                                    # nothing saved
        self.assertIn("tag    Rad Phys (F2001", text)
        self.run_cmd("--apply")
        cas = User.objects.filter(department="College of Arts and Science")
        self.assertEqual(cas.filter(faculty_type="full_time").count(), 4)                  # FCL, Literature, Science, PE
        self.assertEqual(cas.filter(faculty_type="part_time").count(), 5)                  # + STS part-time (no existing PT to tag)
        self.assertFalse(User.objects.filter(role__in=["registrar"]).exists())
        self.assertFalse(User.objects.filter(faculty_type="dean").exists())
        ids = list(User.objects.values_list("school_id", flat=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("F2000", cas.values_list("school_id", flat=True))
        new = cas.first()
        self.assertTrue(new.must_change_password)
        self.assertTrue(new.check_password(new.school_id))
        self.rt.refresh_from_db()
        self.assertIn("Science, Technology and Society", [f.name for f in self.rt.specializations.all()])
        self.assertEqual(self.rt.user.department, "College of Radiologic Technology")     # not moved
        self.assertTrue(User.objects.get(school_id="F2001").check_password("keep-me"))     # account unchanged
        count = User.objects.count()
        text = self.run_cmd("--apply")
        self.assertEqual(User.objects.count(), count)                                      # idempotent
        self.assertIn("Saved: 0 account(s) created, 0 teacher(s) tagged", text)
        self.assertEqual(AcademicField.objects.filter(name__iexact="Science, Technology and Society").count(), 1)

    def test_one_per_area_makes_five_and_five_once(self):
        self.run_cmd("--apply")                                                            # the "only missing" accounts first
        before = set(User.objects.values_list("school_id", flat=True))
        text = self.run_cmd("--one-per-area")
        self.assertIn("DRY RUN", text)
        self.assertEqual(set(User.objects.values_list("school_id", flat=True)), before)    # dry run saves nothing
        self.run_cmd("--one-per-area", "--apply")
        new = User.objects.exclude(school_id__in=before)
        names = {u.get_full_name() for u in new}
        self.assertEqual(new.filter(faculty_type="full_time").count() + new.filter(faculty_type="part_time").count(), new.count())
        self.assertFalse(new.exclude(department="College of Arts and Science").exists())
        self.assertFalse(new.filter(role__in=["registrar", "admin"]).exists())
        self.assertEqual(len(set(User.objects.values_list("school_id", flat=True))), User.objects.count())
        total_demo = User.objects.filter(department="College of Arts and Science").count()
        self.assertEqual(total_demo, 10)                                                  # 5 full-time + 5 part-time demo accounts
        self.assertTrue(names)
        self.run_cmd("--one-per-area", "--apply")
        self.assertEqual(User.objects.filter(department="College of Arts and Science").count(), 10)   # re-run: nothing new


class NoFixedLunchTests(Base):
    """Lunch is not a fixed period: 12:00-1:00 PM is ordinary class time on every day (Mon-Sat). "Reserve lunch gap (optional)" is a
    soft preference that never skips a class and only warns. Other hard rules are unchanged."""

    def setUp(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("seed_timeslots", stdout=StringIO())                        # the generator: hourly + 30-minute, noon included
        self.prog5 = Program.objects.create(name="BS CS Noon", department=DEPT)
        self.sec5 = Section.objects.create(name="A4", program=self.prog5, year_level="4th Year", semester="1st Sem", student_count=20)

    def subject(self, code, units):
        return Subject.objects.create(code=code, title=f"Noon {code}", program=self.prog5, lec_units=units, lab_units=0,
                                      year_level="4th Year", semester="1st Sem", classification="major")

    def gen5(self, **over):
        return self.gen(program_id=self.prog5.id, year_level="4th Year", **over)

    def placed(self, sub):
        rows = Schedule.objects.filter(section=self.sec5, subject=sub).select_related("timeslot")
        days = {r.timeslot.day for r in rows}
        return days, min((r.timeslot.start_time for r in rows), default=None), max((r.timeslot.end_time for r in rows), default=None)

    def test_three_hour_class_with_range_1130_to_230_is_placed_1130_to_230(self):
        sub = self.subject("CS4129", 3)                                          # like CS4129 Social Issues, BS CS 4th Year A4
        r = self.gen5(time_windows={str(sub.id): {"start": "11:30", "end": "14:30"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data["conflicts"], r.data["conflicts"])
        days, a, b = self.placed(sub)
        self.assertEqual(len(days), 1)
        self.assertEqual((a, b), (dtime(11, 30), dtime(14, 30)))
        self.assertEqual(scan()["total"], 0)

    def test_noon_is_ordinary_time_on_every_day_mon_to_sat(self):
        from engine.scheduler import build_block_slots, _slot_minutes
        ts = list(TimeSlot.objects.all())
        for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"):
            self.assertTrue(TimeSlot.objects.filter(day=day, start_time=dtime(12), end_time=dtime(13)).exists(), day)
            three = {(_slot_minutes(b.start_time), _slot_minutes(b.end_time)) for b in build_block_slots(ts, 3) if b.day == day}
            self.assertIn((660, 840), three)                                       # runs through noon: 11:00 AM-2:00 PM
            self.assertIn((720, 900), three)                                       # starts at noon
            self.assertIn((540, 720), three)                                       # ends at noon
        sub = self.subject("NN1", 2)
        r = self.gen5(time_windows={str(sub.id): {"start": "12:00", "end": "14:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.placed(sub)[1:], (dtime(12), dtime(14)))

    def test_an_irregular_overlapping_slot_no_longer_breaks_a_period(self):
        from engine.scheduler import build_block_slots, _slot_minutes
        TimeSlot.objects.create(day="Wed", start_time=dtime(11, 30), end_time=dtime(12, 30))   # like the live Wed 11:30-12:30 row
        blocks = build_block_slots(list(TimeSlot.objects.all()), 2)
        self.assertIn((660, 780), {(_slot_minutes(b.start_time), _slot_minutes(b.end_time)) for b in blocks if b.day == "Wed"})

    def busy_until_noon(self):
        """The section's kept class Mon 10:00 AM-12:00 PM (edited by hand: Generate keeps it), and Monday as the only day."""
        TimeSlot.objects.exclude(day="Mon").delete()
        other = self.subject("KEEP1", 2)
        for h in (10, 11):
            Schedule.objects.create(subject=other, section=self.sec5, teacher=self.teachers[5], room=self.rooms[3], term="1st Sem",
                                    timeslot=TimeSlot.objects.get(day="Mon", start_time=dtime(h), end_time=dtime(h + 1)),
                                    is_manual_override=True)

    def set_gap(self, on):
        from engine.models import SchedulingConfig
        cfg = SchedulingConfig.get_solo()
        cfg.reserve_lunch_gap = on
        cfg.save()

    def test_lunch_gap_off_by_default_places_at_the_earliest_time(self):
        from engine.models import SchedulingConfig
        self.assertFalse(SchedulingConfig.get_solo().reserve_lunch_gap)
        self.busy_until_noon()
        sub = self.subject("GAP1", 2)
        r = self.gen5(time_windows={str(sub.id): {"start": "12:00", "end": "16:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.placed(sub)[1:], (dtime(12), dtime(14)))       # no free hour left between 10:30 and 2:30 -- allowed
        self.assertEqual(r.data["lunch_gap_warnings"], [])

    def test_lunch_gap_on_prefers_leaving_a_free_hour(self):
        self.set_gap(True)
        self.busy_until_noon()
        sub = self.subject("GAP2", 2)
        r = self.gen5(time_windows={str(sub.id): {"start": "12:00", "end": "16:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.placed(sub)[1:], (dtime(13), dtime(15)))       # 12:00-1:00 PM stays free for lunch
        self.assertEqual(r.data["lunch_gap_warnings"], [])

    def test_lunch_gap_on_never_skips_a_class_and_warns_instead(self):
        self.set_gap(True)
        self.busy_until_noon()
        sub = self.subject("GAP3", 2)
        r = self.gen5(time_windows={str(sub.id): {"start": "12:00", "end": "14:00"}})   # the only possible time leaves no gap
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data["conflicts"])                                  # placed, not skipped
        self.assertEqual(self.placed(sub)[1:], (dtime(12), dtime(14)))
        self.assertTrue(any("BS CS Noon A4, Mon: no free hour between 10:30 AM and 2:30 PM" in w for w in r.data["lunch_gap_warnings"]),
                        r.data["lunch_gap_warnings"])

    def test_other_hard_rules_are_unchanged_at_noon(self):
        self.set_gap(True)
        TimeSlot.objects.exclude(day="Mon").delete()
        sub = self.subject("HR1", 2)
        for t in self.teachers:                                               # every qualified teacher teaches Mon 12-2 already
            sec = Section.objects.create(name=f"Z{t.id}", program=self.prog, year_level="1st Year", semester="1st Sem", student_count=5)
            for h in (12, 13):
                Schedule.objects.create(subject=Subject.objects.get(code="TST100"), section=sec, teacher=t, room=Room.objects.create(
                    name=f"HR-{t.id}-{h}", capacity=40, room_type="lecture"), term="1st Sem", status="approved",
                    timeslot=TimeSlot.objects.get(day="Mon", start_time=dtime(h), end_time=dtime(h + 1)))
        r = self.gen5(time_windows={str(sub.id): {"start": "12:00", "end": "14:00"}})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(Schedule.objects.filter(subject=sub).exists())        # professor conflicts still block (nothing forced)
        self.assertTrue(r.data["conflicts"])
        self.assertNotIn("lunch", " ".join(c["reason"] for c in r.data["conflicts"]).lower())
        self.assertEqual(scan()["total"], 0)
