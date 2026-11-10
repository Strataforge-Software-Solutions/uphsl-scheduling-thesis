from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from basic_ed import models as m
from basic_ed import shs_reference as ref
from basic_ed.management.commands.verify_shs_curriculum import check


class VerifyShsCurriculumTests(TestCase):
    def setUp(self):
        call_command("seed_basic_ed", stdout=StringIO())
        self.ay = m.AcademicYear.objects.get(label="2026-2027")
        self.qs = m.CurriculumSubject.objects.filter(level="SHS", academic_year=self.ay)

    def _core(self, name):
        return self.qs.get(is_active=True, grade_level=11, name__iexact=name)

    def test_seed_is_clean(self):
        found, _ = check(self.ay)
        for kind in ("missing", "duplicate", "incorrect", "outdated", "misassigned"):
            self.assertEqual(found.get(kind, []), [], kind)

    def test_report_mode_changes_nothing(self):
        row = self._core("General Science"); row.total_hours = 100; row.save()
        before = list(self.qs.values_list("id", "is_active", "total_hours"))
        found, changed = check(self.ay, fix=False)
        self.assertEqual(changed, 0)
        self.assertTrue(found["incorrect"])
        self.assertEqual(before, list(self.qs.values_list("id", "is_active", "total_hours")))

    def test_apply_fixes_hours_missing_duplicates_and_outdated_without_deleting(self):
        n = self.qs.count()
        row = self._core("General Science"); row.total_hours = 100; row.sessions_per_week = 2; row.save()
        self._core("General Mathematics").delete()
        strand = m.Strand.objects.filter(is_active=True).first()
        base = dict(level="SHS", academic_year=self.ay, grade_level=11, category="core", source=row.source, total_hours=160)
        m.CurriculumSubject.objects.create(code="OLD-1", name="Oral Communication", **base)
        m.CurriculumSubject.objects.create(code="IMP-9", name="Imported subject", strand=strand, **base)
        m.CurriculumSubject.objects.create(code="DUP-1", name="General Science", **base)
        found, _ = check(self.ay, fix=True)
        for kind in ("missing", "duplicate", "incorrect", "outdated"):
            self.assertTrue(found[kind], kind)
        self.assertEqual(float(self._core("General Science").total_hours), 160)
        self.assertEqual(self._core("General Science").sessions_per_week, 4)
        self.assertTrue(self._core("General Mathematics").is_verified)
        self.assertFalse(self.qs.get(code="OLD-1").is_active)
        self.assertFalse(self.qs.get(code="IMP-9").is_active)
        self.assertEqual(self.qs.filter(is_active=True, name__iexact="General Science", grade_level=11).count(), 1)
        self.assertEqual(self.qs.count(), n + 3)          # nothing deleted: -1 removed by the test, +1 re-created, +3 added by the test
        again, _ = check(self.ay)
        for kind in ("missing", "duplicate", "incorrect", "outdated", "misassigned"):
            self.assertEqual(again.get(kind, []), [], kind)

    def test_reference_lists_five_core_subjects(self):
        self.assertEqual(len(ref.G11_CORE), 5)
        self.assertTrue(all(h == 160 and p == 4 for _c, _n, h, p in ref.G11_CORE))


class RecessAndLunchTests(TestCase):
    """JHS / SHS days must contain recess and lunch; no class may overlap them."""

    def setUp(self):
        call_command("seed_basic_ed", stdout=StringIO())
        self.ay = m.AcademicYear.objects.get(label="2026-2027")

    def _rows(self, level, grade):
        from basic_ed.engine import build_rows
        w = m.GradeWindow.objects.get(level=level, grade_level=grade)
        return w, build_rows(m.SchoolLevelConfig.objects.get(level=level), w)

    def test_new_installs_have_recess_and_lunch_on_every_grade(self):
        for w in m.GradeWindow.objects.filter(level="JHS"):
            self.assertTrue(w.recess_start and w.recess_end and w.lunch_start and w.lunch_end, w)
        for w in m.GradeWindow.objects.filter(level="SHS"):          # SHS: one 15-minute break, no recess / lunch
            self.assertTrue(w.break_start and w.break_end, w)
            from basic_ed.engine import window_breaks
            self.assertEqual(window_breaks(w)[0][2] - window_breaks(w)[0][1], 15)
            self.assertFalse(w.recess_start or w.recess_end or w.lunch_start or w.lunch_end, w)
        for w in m.GradeWindow.objects.filter(level="JHS"):
            from basic_ed.engine import window_breaks
            self.assertEqual(window_breaks(w)[0][2] - window_breaks(w)[0][1], 20)

    def test_jhs_day_keeps_three_pm_end_and_has_seven_periods_with_recess_and_lunch(self):
        w, rows = self._rows("JHS", 7)
        kinds = [r[0] for r in rows]
        self.assertEqual(kinds.count("period"), 7)
        self.assertEqual([k for k in kinds if k != "period"], ["Recess", "Lunch"])
        self.assertLess(kinds.index("Recess"), kinds.index("Lunch"))
        self.assertEqual((w.start_time.hour, w.end_time.hour), (8, 15))

    def test_shs_has_one_15_minute_break_and_original_hours(self):
        for grade, hours in ((11, ((7, 0), (12, 30))), (12, ((12, 30), (18, 30)))):
            w, rows = self._rows("SHS", grade)
            self.assertEqual(((w.start_time.hour, w.start_time.minute), (w.end_time.hour, w.end_time.minute)), hours)
            self.assertEqual([r[0] for r in rows if r[0] != "period"], ["Break"])
            self.assertEqual(sum(1 for r in rows if r[0] == "period"), 6)
            brk = next(r for r in rows if r[0] == "Break")
            self.assertEqual(brk[2] - brk[1], 15)
            self.assertTrue(w.start_time.hour * 60 + w.start_time.minute <= brk[1] and brk[2] <= w.end_time.hour * 60 + w.end_time.minute)

    def test_jhs_keeps_recess_and_lunch_and_never_a_single_break(self):
        w, rows = self._rows("JHS", 8)
        self.assertEqual([r[0] for r in rows if r[0] != "period"], ["Recess", "Lunch"])
        self.assertIsNone(w.break_start)

    def test_serializer_enforces_the_shs_rule_and_leaves_jhs_alone(self):
        from basic_ed.serializers import GradeWindowSerializer
        from datetime import time
        w11 = m.GradeWindow.objects.get(level="SHS", grade_level=11)
        outside = GradeWindowSerializer(w11, data={"break_start": "12:20", "break_end": "12:45"}, partial=True)
        self.assertFalse(outside.is_valid())
        ok = GradeWindowSerializer(w11, data={"break_start": "09:00", "break_end": "09:45", "lunch_start": "11:00", "lunch_end": "11:30"}, partial=True)
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertEqual(ok.validated_data["break_end"], time(9, 15))
        self.assertIsNone(ok.validated_data["lunch_start"])           # SHS never keeps a separate lunch
        j = m.GradeWindow.objects.get(level="JHS", grade_level=7)
        okj = GradeWindowSerializer(j, data={"recess_start": "10:30", "recess_end": "10:35"}, partial=True)
        self.assertTrue(okj.is_valid(), okj.errors)
        self.assertEqual(okj.validated_data["recess_end"], time(10, 50))
        self.assertIsNone(okj.validated_data["break_start"])          # JHS never gets the single break

    def test_shs_validation_needs_the_break_and_flags_a_class_in_it(self):
        from basic_ed.services import validate_curriculum, validate_run
        from datetime import time
        w = m.GradeWindow.objects.get(level="SHS", grade_level=11)
        w.break_start = w.break_end = None
        w.save()
        res = validate_curriculum("SHS", self.ay, 1)
        issues = res["issues"] if isinstance(res, dict) else res
        self.assertTrue(any(i["kind"] == "no_break" for i in issues))
        w.break_start, w.break_end = time(9, 30), time(10, 0)  # legacy end is ignored; effective end is 09:45
        w.save()
        sec = m.Section.objects.filter(level="SHS", grade_level=11).first()
        sub = m.CurriculumSubject.objects.filter(level="SHS", grade_level=11).first()
        run = m.ScheduleRun.objects.create(level="SHS", academic_year=self.ay, grading_period=1, grade_level=11, version=1)
        m.ScheduleEntry.objects.create(run=run, section=sec, subject=sub, subject_code=sub.code, subject_name=sub.name, day="Mon",
                                       start_time=time(9, 30), end_time=time(10, 20))
        self.assertTrue(any(i["kind"] == "during_break" for i in validate_run(run)))

    def test_shs_days_keep_six_periods_and_do_not_overlap_each_other(self):
        w11, r11 = self._rows("SHS", 11)
        w12, r12 = self._rows("SHS", 12)
        self.assertEqual(sum(1 for r in r11 if r[0] == "period"), 6)
        self.assertEqual(sum(1 for r in r12 if r[0] == "period"), 6)
        self.assertLessEqual(w11.end_time, w12.start_time)          # Grade 11 (morning) and Grade 12 (afternoon) share rooms

    def test_no_period_overlaps_a_break(self):
        for w in m.GradeWindow.objects.all():
            _w, rows = self._rows(w.level, w.grade_level)
            brk = [r for r in rows if r[0] != "period"]
            for kind, s, e in rows:
                if kind == "period":
                    self.assertTrue(all(e <= b[1] or s >= b[2] for b in brk), (w, s, e))

    def test_validation_refuses_a_grade_without_recess_or_lunch(self):
        from basic_ed.services import validate_curriculum
        w = m.GradeWindow.objects.get(level="JHS", grade_level=7)
        w.lunch_start = w.lunch_end = None
        w.save()
        res = validate_curriculum("JHS", self.ay, 1)
        issues = res["issues"] if isinstance(res, dict) else res
        self.assertTrue(any(i["kind"] == "no_break" and "lunch" in i["message"].lower() for i in issues))

    def test_a_class_placed_in_lunch_is_an_error(self):
        from datetime import time
        from basic_ed.services import validate_run
        sec = m.Section.objects.filter(level="JHS", grade_level=7).first()
        sub = m.CurriculumSubject.objects.filter(level="JHS", grade_level=7).first()
        run = m.ScheduleRun.objects.create(level="JHS", academic_year=self.ay, grading_period=1, grade_level=7, version=1)
        m.ScheduleEntry.objects.create(run=run, section=sec, subject=sub, subject_code=sub.code, subject_name=sub.name, day="Mon",
                                       start_time=time(12, 0), end_time=time(12, 45))
        self.assertTrue(any(i["kind"] == "during_break" for i in validate_run(run)))

    def test_command_adds_breaks_once_without_changing_configured_day_hours(self):
        m.GradeWindow.objects.update(recess_start=None, recess_end=None, lunch_start=None, lunch_end=None, break_start=None, break_end=None)
        m.GradeWindow.objects.filter(level="JHS").update(end_time="14:00")
        call_command("set_basic_ed_breaks", "--dry-run", stdout=StringIO())
        self.assertFalse(m.GradeWindow.objects.filter(recess_start__isnull=False).exists())
        call_command("set_basic_ed_breaks", stdout=StringIO())
        call_command("set_basic_ed_breaks", stdout=StringIO())
        self.assertEqual(m.GradeWindow.objects.get(level="JHS", grade_level=9).end_time.hour, 14)
        self.assertEqual(str(m.GradeWindow.objects.get(level="SHS", grade_level=11).end_time)[:5], "12:30")     # SHS hours untouched
        self.assertEqual(str(m.GradeWindow.objects.get(level="SHS", grade_level=12).start_time)[:5], "12:30")
        self.assertIsNotNone(m.GradeWindow.objects.get(level="SHS", grade_level=11).break_start)


class BreakGenerationTests(TestCase):
    """Real generations: SHS uses its one break, JHS keeps recess + lunch, and no class touches a break or leaves the school hours."""

    def setUp(self):
        from accounts.models import User
        call_command("seed_basic_ed", stdout=StringIO())
        self.ay = m.AcademicYear.objects.get(label="2026-2027")
        specs = set()
        for s in m.CurriculumSubject.objects.all():
            specs.update(x.strip() for x in (s.specialization or s.learning_area or "").split("|") if x.strip())
        for lv in ("SHS", "JHS"):
            for i in range(14):
                u = User.objects.create(username=f"{lv}t{i}", role="faculty", faculty_type="full_time", first_name="T", last_name=f"{lv}{i}")
                m.Faculty.objects.create(user=u, level=lv, employee_id=f"{lv}{i}", specializations="; ".join(specs), max_weekly_hours=40)
        self.actor = User.objects.create(username="pp", role="principal", school_level="SHS")

    def _check(self, level, grade, labels):
        from basic_ed.engine import window_breaks, to_min
        from basic_ed.services import generate
        run, unresolved = generate(level, self.ay, 1, grade, self.actor)
        w = m.GradeWindow.objects.get(level=level, grade_level=grade)
        self.assertEqual([b[0] for b in window_breaks(w)], labels)
        entries = list(run.entries.all())
        self.assertTrue(entries)
        for e in entries:
            s, f = to_min(e.start_time), to_min(e.end_time)
            self.assertTrue(to_min(w.start_time) <= s and f <= to_min(w.end_time), (e.day, s, f))
            for _l, a, b in window_breaks(w):
                self.assertTrue(f <= a or s >= b, (level, grade, e.day, s, f))
        # JHS intentionally keeps the 3:00 PM dismissal, so seven available
        # periods may leave curriculum sessions unresolved. The generated rows
        # are still checked above for window, recess, and lunch violations.
        if level == "SHS":
            self.assertEqual(run.validation["errors"], 0, run.validation)
        return run

    def test_shs_grade_11_and_12_generate_around_the_single_break(self):
        self._check("SHS", 11, ["Break"])
        self._check("SHS", 12, ["Break"])

    def test_jhs_generates_around_recess_and_lunch(self):
        self._check("JHS", 7, ["Recess", "Lunch"])

    def test_principal_home_counts_are_live_and_return_to_zero_after_clearing(self):
        from rest_framework.test import APIClient
        from accounts.models import User
        run = self._check("SHS", 11, ["Break"])
        princ = User.objects.create(username="pshs", role="principal", school_level="SHS", school_id="PS1")
        admin = User.objects.create(username="itadm", role="admin", school_id="A9")
        c = APIClient()
        c.force_authenticate(princ)
        ov = c.get("/api/basic-ed/overview/", {"level": "SHS"}).data
        self.assertEqual(len(ov["runs"]), 1)
        self.assertEqual(sum(r["entry_count"] for r in ov["runs"]), run.entries.count())
        c.force_authenticate(admin)
        r = c.post("/api/basic-ed/clear-generated/", {"level": "SHS", "include_approved": True, "apply": True}, format="json")
        self.assertTrue(r.data["applied"])
        c.force_authenticate(princ)
        ov = c.get("/api/basic-ed/overview/", {"level": "SHS"}).data
        self.assertEqual((ov["runs"], ov["counts"]["runs"], ov["counts"]["pending_review"], ov["counts"]["open_conflicts"]), ([], 0, 0, 0))
        self.assertTrue(ov["counts"]["subjects"] > 0 and ov["counts"]["sections"] > 0 and ov["counts"]["faculty"] > 0)   # permanent data kept


class BasicEdResolveTests(TestCase):
    def setUp(self):
        call_command("seed_basic_ed", stdout=StringIO())
        self.ay = m.AcademicYear.objects.get(label="2026-2027")
        from accounts.models import User
        self.user = User.objects.create(username="princ", role="principal", school_level="JHS")

    def test_a_class_in_lunch_is_moved_to_a_real_period_and_nothing_else_is_forced(self):
        from datetime import time
        from basic_ed.resolve import resolve_run
        from basic_ed.services import validate_run
        sec = m.Section.objects.filter(level="JHS", grade_level=7).first()
        sub = m.CurriculumSubject.objects.filter(level="JHS", grade_level=7).first()
        run = m.ScheduleRun.objects.create(level="JHS", academic_year=self.ay, grading_period=1, grade_level=7, version=1)
        e = m.ScheduleEntry.objects.create(run=run, section=sec, subject=sub, subject_code=sub.code, subject_name=sub.name, day="Mon",
                                           start_time=time(12, 0), end_time=time(12, 45))
        self.assertTrue(any(i["kind"] == "during_break" for i in validate_run(run)))
        out = resolve_run(run, self.user, only={"kind": "during_break"})
        self.assertEqual(len(out["resolved"]), 1, out)
        e.refresh_from_db()
        self.assertFalse(any(i["kind"] == "during_break" for i in validate_run(run)))
        from basic_ed.engine import build_grid
        w = m.GradeWindow.objects.get(level="JHS", grade_level=7)
        grid = build_grid(m.SchoolLevelConfig.objects.get(level="JHS"), w)
        self.assertIn((e.start_time.hour * 60 + e.start_time.minute, e.end_time.hour * 60 + e.end_time.minute), grid)
        # the problems that cannot be fixed here (no teacher / room exist in this test) are reported, not hidden
        self.assertTrue(any(u["reason"] for u in out["unresolved"]) or out["unresolved"] == [])


class AdminClearGeneratedTests(TestCase):
    def setUp(self):
        from accounts.models import User
        from rest_framework.test import APIClient
        call_command("seed_basic_ed", stdout=StringIO())
        self.ay = m.AcademicYear.objects.get(label="2026-2027")
        self.admin = User.objects.create(username="itadmin", role="admin", school_id="A1")
        self.princ = User.objects.create(username="pjhs", role="principal", school_level="JHS", school_id="PR1")
        self.c = APIClient()
        mk = lambda g, st, lv="JHS": m.ScheduleRun.objects.create(level=lv, academic_year=self.ay, grading_period=1, grade_level=g, version=1, status=st)
        self.draft, self.approved, self.shs = mk(7, "draft"), mk(8, "approved"), mk(11, "draft", "SHS")

    def post(self, user, **body):
        self.c.force_authenticate(user)
        return self.c.post("/api/basic-ed/clear-generated/", {"level": "JHS", **body}, format="json")

    def test_preview_changes_nothing_and_apply_keeps_approved_and_other_levels(self):
        r = self.post(self.admin)
        self.assertEqual((r.status_code, r.data["runs"], r.data["kept_approved"]), (200, 1, 1))
        self.assertEqual(m.ScheduleRun.objects.count(), 3)
        self.post(self.admin, apply=True)
        self.assertFalse(m.ScheduleRun.objects.filter(pk=self.draft.pk).exists())
        self.assertTrue(m.ScheduleRun.objects.filter(pk=self.approved.pk).exists())
        self.assertTrue(m.ScheduleRun.objects.filter(pk=self.shs.pk).exists())
        self.post(self.admin, apply=True, include_approved=True)
        self.assertFalse(m.ScheduleRun.objects.filter(pk=self.approved.pk).exists())

    def test_only_the_it_admin_may_clear(self):
        self.assertEqual(self.post(self.princ, apply=True).status_code, 403)
        self.assertTrue(m.ScheduleRun.objects.filter(pk=self.draft.pk).exists())

    def test_account_directory_tells_the_school_level(self):
        self.c.force_authenticate(self.admin)
        rows = self.c.get("/api/accounts/directory/").data
        self.assertEqual({r["username"]: r["school_level"] for r in rows}["pjhs"], "JHS")


class PrincipalAnalyticsTests(TestCase):
    """Teacher workload analytics: per level, from the latest timetables, with sensible recommendations."""

    def setUp(self):
        from accounts.models import User
        from rest_framework.test import APIClient
        from basic_ed.services import generate
        call_command("seed_basic_ed", stdout=StringIO())
        call_command("setup_basic_ed_staff", stdout=StringIO())
        self.ay = m.AcademicYear.objects.get(label="2026-2027")
        self.jhs = User.objects.get(username="PrincipalJHS")
        self.shs = User.objects.get(username="PrincipalSHS")
        generate("JHS", self.ay, 1, 7, self.jhs)
        generate("SHS", self.ay, 1, 11, self.shs)
        self.c = APIClient()

    def _get(self, user, **params):
        self.c.force_authenticate(user)
        return self.c.get("/api/basic-ed/analytics/workload/", params)

    def test_levels_are_separate_and_numbers_match_the_timetable(self):
        r = self._get(self.jhs, level="JHS")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(d["level"], "JHS")
        names_shs = set(m.Faculty.objects.filter(level="SHS").values_list("user__username", flat=True))
        self.assertFalse(names_shs & {t["employee_id"] for t in d["teachers"]})
        e = m.ScheduleEntry.objects.filter(run__level="JHS", run__status="draft")
        total = sum((x.end_time.hour * 60 + x.end_time.minute - x.start_time.hour * 60 - x.start_time.minute) for x in e) / 60
        self.assertAlmostEqual(d["summary"]["total_hours"], round(total, 1), places=0)
        self.assertEqual(d["summary"]["classes"], e.count())
        t = next(t for t in d["teachers"] if t["periods"])
        self.assertTrue(t["subjects"] and t["sections"] >= 1 and t["hours"] > 0)

    def test_a_principal_cannot_read_the_other_level(self):
        self.assertEqual(self._get(self.jhs, level="SHS").status_code, 403)      # locked to their own level
        self.assertEqual(self._get(self.shs, level="JHS").status_code, 403)

    def test_teachers_are_denied(self):
        from accounts.models import User
        t = m.Faculty.objects.filter(level="JHS").first().user
        self.assertEqual(self._get(t, level="JHS").status_code, 403)

    def test_overload_is_flagged_and_a_qualified_free_teacher_is_suggested(self):
        busy = max(m.Faculty.objects.filter(level="JHS"), key=lambda f: m.ScheduleEntry.objects.filter(teacher=f).count())
        busy.max_weekly_hours = 3
        busy.save()
        d = self._get(self.jhs, level="JHS").json()
        row = next(t for t in d["teachers"] if t["faculty_id"] == busy.id)
        self.assertEqual(row["status"], "over")
        self.assertTrue(any(c["kind"] == "overload" and c["teacher_id"] == busy.id for c in d["conflicts"]))
        for rec in d["recommendations"]:
            self.assertNotEqual(rec["from_id"], rec["to_id"])
            to = m.Faculty.objects.get(pk=rec["to_id"])
            self.assertEqual(to.level, "JHS")
            self.assertLessEqual(rec["to_hours_after"], to.max_weekly_hours + 1e-6)
        if d["recommendations"]:
            rec = d["recommendations"][0]
            self.c.force_authenticate(self.jhs)
            for eid in rec["entry_ids"]:
                self.assertEqual(self.c.patch(f"/api/basic-ed/entries/{eid}/?level=JHS", {"teacher": rec["to_id"]}, format="json").status_code, 200)
            d2 = self._get(self.jhs, level="JHS").json()          # updates by itself after the change
            row2 = next(t for t in d2["teachers"] if t["faculty_id"] == busy.id)
            self.assertLess(row2["hours"], row["hours"])

    def test_no_timetable_is_reported_not_an_error(self):
        m.ScheduleRun.objects.filter(level="SHS").delete()
        d = self._get(self.shs, level="SHS").json()
        self.assertFalse(d["has_schedule"])
        self.assertEqual(d["summary"]["classes"], 0)

from datetime import time as dtime

from rest_framework.test import APIClient


class PrincipalAssignAnywayTests(TestCase):
    """SHS / JHS pins in three groups and the Principal's manual Assign anyway (basic_ed/teacher_groups.py)."""

    def setUp(self):
        from accounts.models import User
        from basic_ed.engine import eligible
        call_command("seed_basic_ed", stdout=StringIO())
        m.Faculty.objects.update(is_active=False)                          # only the teachers made here
        self.ay = m.AcademicYear.objects.get(label="2026-2027")
        self.sec = m.Section.objects.filter(level="SHS", grade_level=11, academic_year=self.ay).first()
        self.sub = next(s for s in m.CurriculumSubject.objects.filter(level="SHS", grade_level=11, academic_year=self.ay, is_active=True,
                                                                      grading_period__in=[0, 1]).exclude(category="guidance")
                        if s.strand_id in (None, self.sec.strand_id) and (s.specialization or s.learning_area))
        self.need = (self.sub.specialization or self.sub.learning_area).split("|")[0].strip()
        self.principal = User.objects.create(username="pshs", role="principal", school_level="SHS", school_id="PSX", first_name="Pia", last_name="Prin")
        self.admin = User.objects.create(username="itx", role="admin", school_id="AX")

        def fac(name, specs, hours=40, user=None):
            u = user or User.objects.create(username=name, role="teacher", school_level="SHS", school_id=name, first_name=name, last_name="T")
            return m.Faculty.objects.create(user=u, level="SHS", employee_id=name, specializations=specs, max_weekly_hours=hours)
        self.q1 = fac("q1", self.need)
        self.unq = fac("unq", "Nothing Related")
        self.unq_full = fac("unqfull", "Nothing Related", hours=1)
        self.unq_window = fac("unqwin", "Nothing Related")
        m.Availability.objects.create(faculty=self.unq_window, day="Mon", start_time=dtime(7), end_time=dtime(7, 30), available=True)
        self.own = fac("ownp", "Nothing Related", user=self.principal)        # the Principal also has a teacher profile
        self.assertTrue(eligible(self.q1, self.sub) and not eligible(self.unq, self.sub))
        self.c = APIClient()

    def _groups(self, user=None):
        from basic_ed import teacher_groups as tg
        return tg.build(user or self.principal, self.sec, self.sub)

    def _pin(self, user=None, faculty=None, **extra):
        self.c.force_authenticate(user or self.principal)
        body = {"level": "SHS", "faculty": (faculty or self.unq).id, "section": self.sec.id, "subject": self.sub.id, **extra}
        return self.c.post("/api/basic-ed/assignments/?level=SHS", body, format="json")

    def test_qualified_free_teacher_is_suggested_and_other_group_is_hidden(self):
        g = self._groups()
        self.assertEqual([o["id"] for o in g["suggested"]], [self.q1.id])
        self.assertFalse(g["other_shown"])
        self.assertEqual(g["other"], [])

    def test_qualified_full_shows_other_group_without_the_principal_window_or_full_people(self):
        m.Faculty.objects.filter(pk=self.q1.pk).update(max_weekly_hours=1)
        g = self._groups()
        self.assertEqual(g["suggested"], [])
        self.assertFalse(g["qualified"][0]["selectable"])
        self.assertTrue(g["qualified"][0]["tag"].startswith(("Full:", "Over the limit")))
        self.assertTrue(g["other_shown"])
        self.assertEqual(g["approval_text"], "Not connected to this subject. Principal approval required.")
        ids = [o["id"] for o in g["other"]]
        self.assertEqual(ids, [self.unq.id])
        self.assertNotIn(self.own.id, ids)                                         # never the Principal themself
        self.assertNotIn(self.unq_window.id, ids)                                  # not enough periods inside their availability
        self.assertEqual([x["id"] for x in g["full_line"]], [self.unq_full.id])
        all_ids = [o["id"] for o in g["suggested"] + g["qualified"] + g["other"]] + [x["id"] for x in g["full_line"]]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertFalse(self._groups(self.admin)["other_shown"])                  # IT admin: view only, no Assign anyway

    def test_pin_api_rejections_and_a_valid_assign_anyway(self):
        m.Faculty.objects.filter(pk=self.q1.pk).update(max_weekly_hours=1)
        self.assertEqual(self._pin().status_code, 400)                                       # not qualified, no flag
        self.assertEqual(self._pin(override_qualification=True, override_reason="").status_code, 400)   # no reason
        self.assertEqual(self._pin(user=self.admin, override_qualification=True, override_reason="no one free").status_code, 400)
        self.assertEqual(self._pin(faculty=self.own, override_qualification=True, override_reason="I can").status_code, 400)
        jhs = self.principal.__class__.objects.create(username="pjhs", role="principal", school_level="JHS", school_id="PJX")
        self.assertEqual(self._pin(user=jhs, override_qualification=True, override_reason="no one free").status_code, 403)
        r = self._pin(override_qualification=True, override_reason="no qualified teacher free")
        self.assertEqual(r.status_code, 201, r.data)
        pin = m.TeachingAssignment.objects.get(pk=r.data["id"])
        self.assertEqual((pin.qualification_override["reason"], pin.qualification_override["role"]), ("no qualified teacher free", "Principal"))
        self.c.force_authenticate(self.principal)
        d = self.c.get("/api/basic-ed/assignments/options/", {"level": "SHS", "section": self.sec.id}).data
        row = next(x for x in d["subjects"] if x["subject_id"] == self.sub.id)
        self.assertEqual(row["pin"]["badge"], "Assigned by Principal (not connected)")

    def test_refused_while_a_qualified_teacher_is_free(self):
        r = self._pin(override_qualification=True, override_reason="prefer this one")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Choose from Suggested", r.data["detail"])

    def test_generate_copies_the_note_onto_the_periods_and_writes_the_audit(self):
        from basic_ed.services import generate
        m.Faculty.objects.filter(pk=self.q1.pk).update(max_weekly_hours=1)
        self.assertEqual(self._pin(override_qualification=True, override_reason="no qualified teacher free").status_code, 201)
        run, _unresolved = generate("SHS", self.ay, 1, 11, self.principal)
        mine = list(run.entries.filter(section=self.sec, subject=self.sub))
        self.assertTrue(mine)
        self.assertTrue(all(e.teacher_id == self.unq.id and e.qualification_override["reason"] == "no qualified teacher free" for e in mine))
        self.assertFalse(run.conflicts.filter(kind="not_qualified").exists())          # a warning, not an error
        self.assertTrue(run.conflicts.filter(kind="assigned_anyway", severity="warning").exists())
        self.assertTrue(run.events.filter(action="assigned_anyway").exists())
        others = run.entries.exclude(section=self.sec, subject=self.sub).filter(teacher=self.unq)
        self.assertFalse(others.filter(qualification_override__isnull=False).exists())


# ---------------------------------------------------------------- Part A: backtracking search (basic_ed/search.py)
def _problem(level, ay, gp, grade):
    from basic_ed.engine import Problem
    from basic_ed.services import core_anchor
    P = Problem(level, ay, gp, grade)
    P.anchor = core_anchor(level, ay, gp, grade)
    return P


class GreedyTrapTests(TestCase):
    """A small timetable the OLD greedy cannot finish but the backtracking search can (thesis evidence)."""

    def setUp(self):
        from accounts.models import User
        from basic_ed.engine import build_grid, to_time
        call_command("seed_basic_ed", stdout=StringIO())
        m.Faculty.objects.filter(level="JHS").update(is_active=False)
        self.ay = m.AcademicYear.objects.create(label="2099-2100")
        cfg = m.SchoolLevelConfig.objects.get(level="JHS")
        grid = build_grid(cfg, m.GradeWindow.objects.get(level="JHS", grade_level=7))
        s0, e0 = to_time(grid[0][0]), to_time(grid[0][1])
        self.sec = m.Section.objects.create(level="JHS", academic_year=self.ay, grade_level=7, name="7-Trap", student_count=30)
        for code, spec in (("TMATH", "TrapMath"), ("TENG", "TrapEng")):
            m.CurriculumSubject.objects.create(level="JHS", academic_year=self.ay, grade_level=7, code=code, name=code, category="core",
                                               sessions_per_week=2, specialization=spec, required_room_type="classroom")

        def fac(name, spec, days, start=s0, end=e0):
            u = User.objects.create(username=name, role="teacher", school_level="JHS", school_id=name, first_name=name, last_name="T")
            f = m.Faculty.objects.create(user=u, level="JHS", employee_id=name, specializations=spec)
            for d in days:
                m.Availability.objects.create(faculty=f, day=d, start_time=start, end_time=end, available=True)
            return f
        self.a = fac("trapA", "TrapMath", ["Mon", "Tue", "Wed", "Thu", "Fri"])     # Math: free at the first period every day
        self.b = fac("trapB", "TrapEng", ["Mon", "Tue"])                           # English: ONLY Monday and Tuesday, first period
        fac("trapC", "TrapEng", ["Mon"], start=to_time(5 * 60), end=to_time(6 * 60))   # English too, but never free in school hours

    def test_greedy_fails_and_the_search_places_everything(self):
        from basic_ed.checker import check
        from basic_ed.engine import solve, solve_greedy
        P = _problem("JHS", self.ay, 1, 7)
        old, old_un = solve_greedy(P, seed=7)
        self.assertEqual(len(old), 2)                                         # greedy gives Math Mon+Tue, then English has no time
        self.assertEqual([u["subject"].code for u in old_un], ["TENG"])
        stats = {}
        new, new_un = solve(_problem("JHS", self.ay, 1, 7), seed=7, stats=stats)
        self.assertEqual((len(new), new_un), (4, []))
        self.assertEqual(check(P, new), [])
        eng = sorted(a["day"] for a in new if a["subject"].code == "TENG")
        self.assertEqual(eng, ["Mon", "Tue"])                                 # English took the only times its teacher has
        self.assertEqual(stats["placed"], 4)

    def test_reasons_are_plain(self):
        from basic_ed.engine import solve
        m.Availability.objects.filter(faculty=self.b).delete()
        m.Availability.objects.create(faculty=self.b, day="Mon", start_time=dtime(5), end_time=dtime(6), available=True)
        _a, un = solve(_problem("JHS", self.ay, 1, 7), seed=7)
        msg = next(u["message"] for u in un if u["subject"].code == "TENG")
        self.assertIn("available time does not match the grade's daily schedule", msg)
        m.Faculty.objects.filter(pk=self.a.pk).update(max_weekly_hours=1)
        _a, un = solve(_problem("JHS", self.ay, 1, 7), seed=7)
        msg = next(u["message"] for u in un if u["subject"].code == "TMATH")
        self.assertIn("weekly limit", msg)
        self.assertIn("trapA", msg)


class SearchOnSampleDataTests(TestCase):
    """The school's SHS / JHS sample data (seed_basic_ed + setup_basic_ed_staff): every timetable keeps every hard rule, the result is
    reproducible with the same seed, and the time limit is respected."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_basic_ed", stdout=StringIO())
        call_command("setup_basic_ed_staff", stdout=StringIO())
        cls.ay = m.AcademicYear.objects.get(label="2026-2027")

    def test_no_hard_rule_is_broken(self):
        from basic_ed.checker import check
        from basic_ed.engine import solve
        for level, grade in (("SHS", 11), ("SHS", 12), ("JHS", 7), ("JHS", 10)):
            P = _problem(level, self.ay, 1, grade)
            out, _un = solve(P, seed=grade * 7 + 1)
            self.assertTrue(out, (level, grade))
            self.assertEqual(check(P, out), [], (level, grade))

    def test_same_seed_same_timetable(self):
        from basic_ed.engine import solve
        def key(res):
            return sorted((a["section"].id, a["subject"].id, a["teacher"].id, a["room"].id, a["day"], a["start"]) for a in res[0])
        one = solve(_problem("SHS", self.ay, 1, 11), seed=78)
        two = solve(_problem("SHS", self.ay, 1, 11), seed=78)
        self.assertEqual(key(one), key(two))

    def test_time_limit_is_respected(self):
        import time as _t
        from basic_ed.search import solve
        stats = {}
        t0 = _t.monotonic()
        solve(_problem("SHS", self.ay, 1, 11), seed=1, stats=stats, time_seconds=0.3, max_steps=10_000_000)
        self.assertLess(_t.monotonic() - t0, 0.3 + 3.0)                    # + setting the problem up, which is outside the search
        self.assertLessEqual(stats["seconds"], 0.3 + 3.0)

    def test_grade_11_whole_year_subjects_repeat_or_are_reported(self):
        from accounts.models import User
        from basic_ed.checker import check
        from basic_ed.engine import solve
        from basic_ed.services import generate
        actor = User.objects.create(username="pA", role="principal", school_level="SHS", school_id="PA1")
        generate("SHS", self.ay, 1, 11, actor)                              # Term 1 exists: Term 2 must repeat its whole-year subjects
        P = _problem("SHS", self.ay, 2, 11)
        self.assertTrue(P.anchor)
        out, _un = solve(P, seed=79)
        self.assertEqual(check(P, out), [])                                # includes "repeats the other term exactly"
        # block one repeated time: that subject is reported, never placed at new times
        e = P.anchor[0]
        P2 = _problem("SHS", self.ay, 2, 11)
        P2.busy_room[P2.canon(e.room_id)].add((e.day, e.start_time.hour * 60 + e.start_time.minute))
        out2, un2 = solve(P2, seed=79)
        hit = [u for u in un2 if u["kind"] == "anchor_conflict" and u["subject"].id == e.subject_id and u["section"].id == e.section_id]
        self.assertTrue(hit)
        self.assertIn("cannot repeat it at the same day and time", hit[0]["message"])
        self.assertFalse([a for a in out2 if a["subject"].id == e.subject_id and a["section"].id == e.section_id])


# ---------------------------------------------------------------- Part B: teacher submits availability, Principal views it
class AvailabilityFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_basic_ed", stdout=StringIO())
        call_command("setup_basic_ed_staff", stdout=StringIO())
        cls.ay = m.AcademicYear.objects.get(label="2026-2027")

    def setUp(self):
        from accounts.models import User
        self.c = APIClient()
        self.p_shs = User.objects.get(username="PrincipalSHS")
        self.p_jhs = User.objects.get(username="PrincipalJHS")
        self.shs = list(m.Faculty.objects.filter(level="SHS").select_related("user").order_by("id"))
        self.jhs = list(m.Faculty.objects.filter(level="JHS").select_related("user").order_by("id"))
        self.registrar = User.objects.create(username="regX", role="registrar", school_id="RX1")
        self.admin = User.objects.create(username="admX", role="admin", school_id="AX1")

    def _grid(self, fac):
        self.c.force_authenticate(fac.user)
        return self.c.get("/api/basic-ed/my/availability/").data

    def _submit(self, fac, choose):
        """choose(day, row) -> preference; every class-period cell of the teacher's grid is sent."""
        g = self._grid(fac)["grid"]
        cells = [{"day": d["key"], "start": r["start"], "preference": choose(d["key"], r)} for d in g["days"] for r in g["rows"]
                 if r["kind"] == "period"]
        self.c.force_authenticate(fac.user)
        return self.c.post("/api/basic-ed/my/availability/", {"cells": cells}, format="json")

    # ---- old rows / migration
    def test_old_rows_load_as_available_unavailable_and_submitted(self):
        import importlib
        from django.apps import apps
        mig = importlib.import_module("basic_ed.migrations.0005_availability_tiers_and_submission")
        f = self.shs[0]
        m.Availability.objects.filter(faculty=f).delete()
        a1 = m.Availability.objects.create(faculty=f, day="Mon", start_time=dtime(7), end_time=dtime(9), available=True)
        a2 = m.Availability.objects.create(faculty=f, day="Tue", start_time=dtime(7), end_time=dtime(9), available=False)
        m.Availability.objects.filter(pk__in=[a1.pk, a2.pk]).update(preference="available")      # as before the migration
        m.Faculty.objects.filter(pk=f.pk).update(availability_status="not_submitted", availability_submitted_at=None)
        mig.forward(apps, None)
        self.assertEqual(m.Availability.objects.get(pk=a1.pk).preference, "available")
        self.assertEqual(m.Availability.objects.get(pk=a2.pk).preference, "unavailable")
        f.refresh_from_db()
        self.assertEqual(f.availability_status, "submitted")
        self.assertIsNotNone(f.availability_submitted_at)
        # an older caller that only says available=False still means Unavailable
        a3 = m.Availability.objects.create(faculty=f, day="Wed", start_time=dtime(7), end_time=dtime(8), available=False)
        self.assertEqual(a3.preference, "unavailable")

    # ---- permissions
    def test_who_may_read_and_write(self):
        t = self.shs[1]
        r = self._submit(t, lambda d, r: "available")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "submitted")
        # a teacher cannot write anyone else's (the only write is their own page), nor use the Principal's pages
        self.c.force_authenticate(t.user)
        self.assertEqual(self.c.post(f"/api/basic-ed/faculty/{self.shs[2].id}/availability/", {"rows": []}, format="json").status_code, 403)
        self.assertEqual(self.c.get("/api/basic-ed/availability/").status_code, 403)
        # the Principal cannot write a teacher's availability
        self.c.force_authenticate(self.p_shs)
        r = self.c.post(f"/api/basic-ed/faculty/{t.id}/availability/?level=SHS", {"rows": []}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertIn("submitted by each teacher", str(r.data))
        self.assertEqual(self.c.post("/api/basic-ed/my/availability/", {"cells": []}, format="json").status_code, 403)
        # the Principal sees only their own level
        ids = {x["faculty_id"] for x in self.c.get("/api/basic-ed/availability/").data["teachers"]}
        self.assertTrue(ids and ids <= {f.id for f in self.shs})
        self.assertNotEqual(self.c.get(f"/api/basic-ed/availability/{self.jhs[0].id}/").status_code, 200)
        self.c.force_authenticate(self.p_jhs)
        self.assertNotEqual(self.c.get(f"/api/basic-ed/availability/{t.id}/").status_code, 200)
        # Registrar: no access; IT Admin: read only
        self.c.force_authenticate(self.registrar)
        self.assertEqual(self.c.get("/api/basic-ed/availability/?level=SHS").status_code, 403)
        self.c.force_authenticate(self.admin)
        self.assertEqual(self.c.get("/api/basic-ed/availability/?level=SHS").status_code, 200)
        self.assertEqual(self.c.post(f"/api/basic-ed/availability/{t.id}/return/?level=SHS", {"note": "fix it"}, format="json").status_code, 403)
        self.assertEqual(self.c.post("/api/basic-ed/availability/remind/?level=SHS", {}, format="json").status_code, 403)

    def test_submit_saves_tiers_rejects_breaks_and_is_audited(self):
        from audit.models import AuditLog
        t = self.shs[1]
        g = self._grid(t)["grid"]
        brk = next((r for r in g["rows"] if r["kind"] == "break"), None)
        if brk is not None:
            self.c.force_authenticate(t.user)
            r = self.c.post("/api/basic-ed/my/availability/", {"cells": [{"day": "Mon", "start": brk["start"], "preference": "available"}]},
                            format="json")
            self.assertEqual(r.status_code, 400)
            self.assertIn("break", r.data["detail"])
        first = next(r for r in g["rows"] if r["kind"] == "period")
        r = self._submit(t, lambda d, row: "preferred" if (d == "Wed" and row["start"] == first["start"]) else
                         ("unavailable" if d == "Mon" else "available"))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["cells"][f"Wed|{first['start']}"], "preferred")
        self.assertEqual(r.data["cells"][f"Mon|{first['start']}"], "unavailable")
        prefs = set(m.Availability.objects.filter(faculty=t).values_list("preference", flat=True))
        self.assertEqual(prefs, {"preferred", "available", "unavailable"})
        self.assertTrue(AuditLog.objects.filter(entity="SHS/JHS availability", entity_id=str(t.id), new_values__level="SHS").exists())

    # ---- generator
    def test_preferred_first_unavailable_never_and_not_submitted_free(self):
        from basic_ed.engine import Problem, solve, teacher_time_rule, TIER_PREFERRED
        from basic_ed.checker import check
        # one teacher teaches one subject: make it the only qualified one
        P0 = Problem("SHS", self.ay, 1, 11)
        sec = P0.sections[0]
        sub = next(x for x in P0.subjects_for(sec) if x.category != "guidance")
        t = next(f for f in self.shs if True)
        m.TeachingAssignment.objects.create(faculty=t, section=sec, subject=sub)
        g = self._grid(t)["grid"]
        periods = [r for r in g["rows"] if r["kind"] == "period"]
        pref_starts = {periods[1]["start"], periods[2]["start"]}
        self._submit(t, lambda d, row: "unavailable" if d == "Mon" else ("preferred" if d in ("Thu", "Fri") and row["start"] in pref_starts
                                                                        else "available"))
        P = Problem("SHS", self.ay, 1, 11)
        out, _un = solve(P, seed=78)
        mine = [a for a in out if a["section"].id == sec.id and a["subject"].id == sub.id]
        self.assertEqual(len(mine), sub.sessions_per_week)
        self.assertFalse([a for a in out if a["teacher"].id == t.id and a["day"] == "Mon"])      # Unavailable never used
        tiers = [teacher_time_rule(P, t, a["day"], (a["start"], a["end"])) for a in mine]
        self.assertEqual(tiers.count(TIER_PREFERRED), min(len(mine), 4))                           # Preferred times taken first
        self.assertEqual(check(P, out), [])
        # a teacher who never submitted is not blocked at any time
        other = self.shs[-1]
        m.Availability.objects.filter(faculty=other).delete()
        m.Faculty.objects.filter(pk=other.pk).update(availability_status="not_submitted")
        P2 = Problem("SHS", self.ay, 1, 11)
        self.assertTrue(all(teacher_time_rule(P2, other, d, s) is not None for d in ("Mon", "Wed", "Fri") for s in P2.grids[11]))

    def test_resubmit_after_approval_does_not_move_placed_classes(self):
        from accounts.models import User
        from basic_ed.services import generate
        run, _u = generate("SHS", self.ay, 1, 11, self.p_shs)
        m.ScheduleRun.objects.filter(pk=run.pk).update(status="approved")
        before = sorted(m.ScheduleEntry.objects.filter(run=run).values_list("id", "teacher_id", "day", "start_time", "room_id"))
        busy = m.ScheduleEntry.objects.filter(run=run, teacher__isnull=False).values_list("teacher_id", flat=True).first()
        t = m.Faculty.objects.get(pk=busy)
        self.assertEqual(self._submit(t, lambda d, r: "unavailable" if d in ("Mon", "Tue") else "available").status_code, 200)
        after = sorted(m.ScheduleEntry.objects.filter(run=run).values_list("id", "teacher_id", "day", "start_time", "room_id"))
        self.assertEqual(before, after)
        self.assertEqual(m.ScheduleRun.objects.get(pk=run.pk).status, "approved")
        _ = User

    def test_return_for_correction_and_reminders(self):
        from audit.models import AuditLog
        from basic_ed.engine import Problem
        from notifications.models import Notification
        t = self.shs[1]
        self._submit(t, lambda d, r: "unavailable" if d == "Fri" else "available")
        self.c.force_authenticate(self.p_shs)
        self.assertEqual(self.c.post(f"/api/basic-ed/availability/{t.id}/return/", {"note": ""}, format="json").status_code, 400)
        r = self.c.post(f"/api/basic-ed/availability/{t.id}/return/", {"note": "Friday mornings are free now, please update"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        mine = self._grid(t)
        self.assertEqual((mine["status"], mine["note"]), ("returned", "Friday mornings are free now, please update"))
        self.assertTrue(Notification.objects.filter(recipient=t.user, message__contains="returned for correction").exists())
        self.assertTrue(Problem("SHS", self.ay, 1, 11).unavail[t.id].get("Fri"))          # the last submission stays in use
        self.c.force_authenticate(self.p_shs)
        lst = {x["faculty_id"]: x for x in self.c.get("/api/basic-ed/availability/").data["teachers"]}
        self.assertEqual(lst[t.id]["status"], "returned")
        waiting = [f for f in self.shs if m.Faculty.objects.get(pk=f.pk).availability_status in ("not_submitted", "returned")]
        r = self.c.post("/api/basic-ed/availability/remind/", {}, format="json")
        self.assertEqual(r.data["reminded"], len([f for f in waiting if f.is_active]))
        self.assertTrue(Notification.objects.filter(recipient=waiting[0].user, message__contains="availability").exists())
        self.assertFalse(Notification.objects.filter(recipient__in=[f.user for f in self.jhs]).exists())    # other level untouched
        self.assertTrue(AuditLog.objects.filter(entity="SHS/JHS availability", entity_id="reminder").exists())
        self.assertTrue(AuditLog.objects.filter(entity="SHS/JHS availability", summary__contains="returned for correction").exists())

    def test_break_for_one_grade_only_is_selectable_and_never_used_by_that_grade(self):
        from basic_ed.checker import check
        from basic_ed.engine import Problem, solve, to_min, window_breaks
        w11 = m.GradeWindow.objects.get(level="SHS", grade_level=11)
        b = window_breaks(w11)[0]
        # Grade 12 starts as early as Grade 11 here, so Grade 11's break is a class time for Grade 12
        w12 = m.GradeWindow.objects.get(level="SHS", grade_level=12)
        w12.start_time, w12.end_time, w12.break_start, w12.break_end = w11.start_time, w11.end_time, None, None
        w12.save()
        t = next(f for f in self.shs if f.specializations)
        g = self._grid(t)["grid"]
        self.assertEqual(g["grades"], [11, 12])                                    # a teacher of both grades
        noted = [r for r in g["rows"] if r["kind"] == "period" and "Break for Grade 11" in r["note"]]
        self.assertTrue(noted)                                                      # selectable, with the note
        self.assertEqual(self._submit(t, lambda d, r: "available").status_code, 200)
        P = Problem("SHS", self.ay, 1, 11)
        out, _un = solve(P, seed=78)
        self.assertFalse([a for a in out if a["start"] < b[2] and a["end"] > b[1]])     # no Grade 11 class in its break
        self.assertEqual(check(P, out), [])
        _ = to_min
