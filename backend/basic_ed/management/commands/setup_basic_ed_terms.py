"""
Move an existing SHS / JHS database to the new term structure.

  python manage.py setup_basic_ed_terms            # preview only
  python manage.py setup_basic_ed_terms --apply    # do it

  * Junior High (Grades 7-10): 3 terms per school year. The old 1st-4th quarter periods are hidden
    (nothing is deleted); whole-year curriculum lines already apply to every term.
  * SHS Grade 11: 3 terms per school year. The 5 core subjects (whole year) stay the same all year; the Academic
    strand electives that existed for semesters 1 and 2 become Term 1 and Term 2, and a Term 3 pair is added
    (copied from Term 2: replace them with the electives the school offers).
  * SHS Grade 12: unchanged (2 semesters).
Existing timetables are not touched; Grade 11 timetables for period 1/2 now read "Term 1/2".
Curriculum lines that fall outside the structure (e.g. a JHS line set for quarter 4) are listed, not changed.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed import models as m
from basic_ed.structure import structure


class Command(BaseCommand):
    help = "Apply the 3-term (Grade 11, JHS) / 2-semester (Grade 12) structure to existing basic-ed data."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")

    def handle(self, *a, **o):
        out = self.stdout.write
        with transaction.atomic():
            for ay in m.AcademicYear.objects.all():
                for lv in ("SHS", "JHS"):
                    have = set(m.CalendarPeriod.objects.filter(level=lv, academic_year=ay, kind="term").values_list("number", flat=True))
                    out(f"{ay.label} {lv}: terms present {sorted(have)}" + ("" if have >= {1, 2, 3} else "  <- add Terms 1-3 in the Calendar tab"))
                q = m.CalendarPeriod.objects.filter(academic_year=ay, kind="quarter").count()
                if q:
                    out(f"{ay.label}: {q} old JHS quarter period(s) are no longer shown (kept in the database)")
                # Grade 11 electives: Semester n -> Term n; add Term 3
                for st in m.CurriculumSubject.objects.filter(level="SHS", academic_year=ay, grade_level=11, category="elective",
                                                             grading_period__in=[1, 2], is_active=True):
                    new_name = st.name.replace("(Semester", "(Term")
                    if st.total_hours and float(st.total_hours) == 80:      # 80 h per semester -> about 40 h per 13-week term
                        st.total_hours = 40
                        st.save(update_fields=["total_hours"])
                    if new_name != st.name:
                        out(f"  rename {st.code}: {st.name!r} -> {new_name!r}")
                        st.name = new_name
                        st.save(update_fields=["name"])
                for st in m.CurriculumSubject.objects.filter(level="SHS", academic_year=ay, grade_level=11, category="elective",
                                                             grading_period=2, is_active=True, code__contains="-E2"):
                    code3 = st.code.replace("-E2", "-E3")
                    if not m.CurriculumSubject.objects.filter(level="SHS", academic_year=ay, strand=st.strand, grade_level=11,
                                                              grading_period=3, code=code3).exists():
                        out(f"  add    {code3} (Term 3 elective, copied from {st.code})")
                        st.pk = None
                        st.grading_period, st.code = 3, code3
                        st.name = st.name.replace("(Term 2)", "(Term 3)")
                        st.is_verified = False
                        st.verification_note = "Added with the 3-term structure: replace with the elective the school offers."
                        st.save()
                for lv in ("SHS", "JHS"):
                    for g in {x for x in m.GradeWindow.objects.filter(level=lv).values_list("grade_level", flat=True)}:
                        kind, n = structure(lv, g)
                        for s in m.CurriculumSubject.objects.filter(level=lv, academic_year=ay, grade_level=g, is_active=True, grading_period__gt=n):
                            out(self.style.WARNING(f"  outside structure: {lv} Grade {g} {s.code} is set for period {s.grading_period} "
                                                   f"(Grade {g} has {n} {kind}s). Correct it in the Curriculum tab."))
            if not o["apply"]:
                transaction.set_rollback(True)
        out(self.style.SUCCESS("Applied.") if o["apply"] else self.style.WARNING("Preview only. Add --apply to make the change."))
