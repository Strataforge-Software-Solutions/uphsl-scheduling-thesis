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
        for w in m.GradeWindow.objects.filter(level="SHS"):          # SHS: one 30-minute break, no recess / lunch
            self.assertTrue(w.break_start and w.break_end, w)
            self.assertEqual((w.break_end.hour * 60 + w.break_end.minute) - (w.break_start.hour * 60 + w.break_start.minute), 30)
            self.assertFalse(w.recess_start or w.recess_end or w.lunch_start or w.lunch_end, w)

    def test_jhs_day_is_eight_periods_with_recess_and_lunch(self):
        w, rows = self._rows("JHS", 7)
        kinds = [r[0] for r in rows]
        self.assertEqual(kinds.count("period"), 8)
        self.assertEqual([k for k in kinds if k != "period"], ["Recess", "Lunch"])
        self.assertLess(kinds.index("Recess"), kinds.index("Lunch"))
        self.assertEqual((w.start_time.hour, w.end_time.hour), (8, 15))

    def test_shs_has_one_30_minute_break_and_original_hours(self):
        for grade, hours in ((11, ((7, 0), (12, 30))), (12, ((12, 30), (18, 30)))):
            w, rows = self._rows("SHS", grade)
            self.assertEqual(((w.start_time.hour, w.start_time.minute), (w.end_time.hour, w.end_time.minute)), hours)
            self.assertEqual([r[0] for r in rows if r[0] != "period"], ["Break"])
            self.assertEqual(sum(1 for r in rows if r[0] == "period"), 6)
            brk = next(r for r in rows if r[0] == "Break")
            self.assertEqual(brk[2] - brk[1], 30)
            self.assertTrue(w.start_time.hour * 60 + w.start_time.minute <= brk[1] and brk[2] <= w.end_time.hour * 60 + w.end_time.minute)

    def test_jhs_keeps_recess_and_lunch_and_never_a_single_break(self):
        w, rows = self._rows("JHS", 8)
        self.assertEqual([r[0] for r in rows if r[0] != "period"], ["Recess", "Lunch"])
        self.assertIsNone(w.break_start)

    def test_serializer_enforces_the_shs_rule_and_leaves_jhs_alone(self):
        from basic_ed.serializers import GradeWindowSerializer
        from datetime import time
        w11 = m.GradeWindow.objects.get(level="SHS", grade_level=11)
        bad = GradeWindowSerializer(w11, data={"break_start": "09:30", "break_end": "10:15"}, partial=True)
        self.assertFalse(bad.is_valid())
        outside = GradeWindowSerializer(w11, data={"break_start": "12:15", "break_end": "12:45"}, partial=True)
        self.assertFalse(outside.is_valid())
        ok = GradeWindowSerializer(w11, data={"break_start": "09:00", "break_end": "09:30", "lunch_start": "11:00", "lunch_end": "11:30"}, partial=True)
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertIsNone(ok.validated_data["lunch_start"])           # SHS never keeps a separate lunch
        j = m.GradeWindow.objects.get(level="JHS", grade_level=7)
        okj = GradeWindowSerializer(j, data={"break_start": "09:00", "break_end": "09:30"}, partial=True)
        self.assertTrue(okj.is_valid(), okj.errors)
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
        w.break_start, w.break_end = time(9, 30), time(10, 0)
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

    def test_command_adds_breaks_once_and_only_extends_the_day_once(self):
        m.GradeWindow.objects.update(recess_start=None, recess_end=None, lunch_start=None, lunch_end=None, break_start=None, break_end=None)
        m.GradeWindow.objects.filter(level="JHS").update(end_time="14:00")
        call_command("set_basic_ed_breaks", "--dry-run", stdout=StringIO())
        self.assertFalse(m.GradeWindow.objects.filter(recess_start__isnull=False).exists())
        call_command("set_basic_ed_breaks", stdout=StringIO())
        call_command("set_basic_ed_breaks", stdout=StringIO())
        self.assertEqual(m.GradeWindow.objects.get(level="JHS", grade_level=9).end_time.hour, 15)
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
