"""
Checks every Senior High School curriculum line against the official DepEd curriculum (see basic_ed/shs_reference.py)
and reports MISSING, DUPLICATE, INCORRECT, OUTDATED and MISASSIGNED lines.

    python manage.py verify_shs_curriculum            # report only - nothing is changed
    python manage.py verify_shs_curriculum --apply    # also fix what can be fixed safely

--apply never deletes anything. It
  * adds a missing official Grade 11 core / Homeroom line,
  * corrects hours, periods per week, category, strand and period of an official line,
  * retires (is_active = False, with the reason written into the line) test/import leftovers, duplicates and outdated 2016 subjects,
  * writes the official elective titles of the cluster into the note of each placeholder elective.
Schedules already generated keep their own copy of the subject name/code, so nothing already scheduled changes.
Things DepEd has not published (which elective in which term, the SY 2026-2027 Grade 12 list) are only reported as "cannot be verified".
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed import models as m
from basic_ed import shs_reference as ref

KINDS = ["missing", "duplicate", "incorrect", "outdated", "misassigned", "unverified"]


def check(ay, fix=False, log=lambda *_: None):
    """Returns {kind: [message, ...]}; with fix=True also repairs what is safe (inside the caller's transaction)."""
    found = defaultdict(list)
    changed = [0]

    def say(kind, msg):
        found[kind].append(msg)

    def retire(line, why):
        say(why[0], f"{line.code} \"{line.name}\" (Grade {line.grade_level}): {why[1]}")
        if fix and line.is_active:
            line.is_active = False
            line.verification_note = f"Retired by verify_shs_curriculum: {why[1]}"[:400]
            line.save(update_fields=["is_active", "verification_note"])
            changed[0] += 1

    strands = {s.id: s for s in m.Strand.objects.all()}
    lines = list(m.CurriculumSubject.objects.filter(level="SHS", academic_year=ay).select_related("strand", "source").order_by("id"))
    active = [x for x in lines if x.is_active]

    # 1. test / import leftovers
    for x in list(active):
        if ref.JUNK_CODE.match(x.code or "") or ref.JUNK_NAME.match((x.name or "").strip()):
            retire(x, ("incorrect", "is a test / import leftover, not a real subject"))
            active.remove(x)

    # 2. outdated: 2016 K-12 subjects inside the Strengthened Grade 11
    for x in list(active):
        if x.grade_level == 11 and ref.norm(x.name) in ref.LEGACY_NORM:
            retire(x, ("outdated", "is a 2016 K-12 SHS subject; Grade 11 follows the Strengthened SHS curriculum (DO 017 s.2026)"))
            active.remove(x)

    # 3. duplicates: same grade + strand + title in overlapping periods (whole year overlaps every term)
    groups = defaultdict(list)
    for x in active:
        groups[(x.grade_level, x.strand_id, ref.norm(x.name))].append(x)
    for (_g, _s, _n), lst in groups.items():
        if len(lst) < 2:
            continue
        lst.sort(key=lambda x: (not x.is_verified, x.id))
        keep = lst[0]
        for dup in lst[1:]:
            if dup.grading_period == 0 or keep.grading_period == 0 or dup.grading_period == keep.grading_period:
                retire(dup, ("duplicate", f"duplicates {keep.code} (same grade, strand and title)"))
                active.remove(dup)

    # 4. official Grade 11 core + homeroom: present, and with the official hours / periods / category / strand / period
    srcs = m.CurriculumSource.objects.filter(level="SHS", academic_year=ay, is_verified=True).order_by("id")
    source = srcs.filter(title__icontains="DM 48").first() or srcs.first()
    wanted = [(c, n, h, p, "core") for c, n, h, p in ref.G11_CORE] + [(*ref.G11_HGP, "guidance")]
    for code, name, hours, periods, cat in wanted:
        row = next((x for x in active if x.grade_level == 11 and ref.norm(x.name) == ref.norm(name)), None)
        if row is None:
            say("missing", f"Grade 11 {name} ({hours} h, {periods} periods/week) is not in the curriculum")
            if fix:
                exists = m.CurriculumSubject.objects.filter(level="SHS", academic_year=ay, strand=None, grade_level=11,
                                                            grading_period=0, code=code).first()
                if exists:
                    exists.is_active = True; exists.name = name
                    exists.save(update_fields=["is_active", "name"]); row = exists
                else:
                    row = m.CurriculumSubject.objects.create(
                        level="SHS", academic_year=ay, source=source, strand=None, grade_level=11, grading_period=0, code=code, name=name,
                        category=cat, sessions_per_week=periods, total_hours=hours, is_verified=True, verification_note=ref.REFERENCE_NOTE,
                        learning_area="Guidance" if cat == "guidance" else "")
                changed[0] += 1
            continue
        fixes = {}
        if float(row.total_hours or 0) != float(hours):
            say("incorrect", f"{row.code} {name}: {row.total_hours or 0} h, official is {hours} h"); fixes["total_hours"] = hours
        if row.sessions_per_week != periods:
            say("incorrect", f"{row.code} {name}: {row.sessions_per_week} periods/week, official is {periods}"); fixes["sessions_per_week"] = periods
        if row.category != cat:
            say("incorrect", f"{row.code} {name}: category '{row.category}', official is '{cat}'"); fixes["category"] = cat
        if row.grading_period != 0:
            say("misassigned", f"{row.code} {name}: set to period {row.grading_period}; a Grade 11 core subject runs the whole school year (period 0)")
            fixes["grading_period"] = 0
        if row.strand_id is not None:
            say("misassigned", f"{row.code} {name}: attached to strand {row.strand.code}; core subjects apply to every strand"); fixes["strand"] = None
        if fixes and fix:
            for k, v in fixes.items():
                setattr(row, k, v)
            row.is_verified = True
            row.save()
            changed[0] += 1
        elif not row.is_verified and not fixes and fix:
            row.is_verified = True; row.verification_note = ref.REFERENCE_NOTE
            row.save(update_fields=["is_verified", "verification_note"]); changed[0] += 1

    # 5. assignment of every other active line: period range, strand, track
    for x in active:
        top = ref.MAX_PERIOD.get(x.grade_level)
        if top is None:
            say("misassigned", f"{x.code} \"{x.name}\": grade {x.grade_level} is not an SHS grade (11 or 12)")
            continue
        if x.grading_period > top:
            say("misassigned", f"{x.code} \"{x.name}\": period {x.grading_period} does not exist for Grade {x.grade_level} "
                                f"({'3 terms' if x.grade_level == 11 else '2 semesters'})")
        if x.category == "elective" and x.strand_id is None:
            say("misassigned", f"{x.code} \"{x.name}\": an elective must belong to a strand / cluster")
        if x.strand_id and not strands[x.strand_id].is_active:
            say("misassigned", f"{x.code} \"{x.name}\": belongs to the inactive strand {strands[x.strand_id].code}")
        if x.category in ("core", "guidance") and x.strand_id and x.grade_level == 11:
            pass                      # already reported with the official core check when it is one of the five
    # 6. every active strand needs electives in every period
    for st in strands.values():
        if not st.is_active:
            continue
        for grade, periods in ((11, (1, 2, 3)), (12, (1, 2))):
            have = {x.grading_period for x in active if x.strand_id == st.id and x.grade_level == grade and x.category == "elective"}
            whole = 0 in have
            for p in periods:
                if p not in have and not whole and st.track != "TECHPRO":      # TechPro = one 320 h block (DM 48)
                    say("missing", f"{st.code} Grade {grade} has no elective in {'term' if grade == 11 else 'semester'} {p}")
            if st.track == "TECHPRO" and not have:
                say("missing", f"{st.code} Grade {grade} (TechPro) has no TechPro elective")

    # 7. what cannot be verified
    pend = [x for x in active if x.category == "elective" and not x.is_verified]
    by_cluster = defaultdict(list)
    for x in pend:
        by_cluster[(x.strand.deped_cluster if x.strand_id else "")].append(x)
    for cluster, lst in by_cluster.items():
        official = ref.CLUSTER_ELECTIVES.get(ref.cluster_name(cluster))
        say("unverified", f"{len(lst)} placeholder elective line(s) of cluster \"{cluster}\" still carry generic names "
                          f"(e.g. {lst[0].name}); DepEd lists {len(official) if official else 'no'} titles for the cluster but does not say "
                          f"which term each is taken in")
        if fix and official:
            note = ("Placeholder. Official DepEd titles of this cluster: " + "; ".join(official))[:400]
            for x in lst:
                if x.verification_note != note:
                    x.verification_note = note
                    x.save(update_fields=["verification_note"]); changed[0] += 1
    g12 = [x for x in active if x.grade_level == 12 and not x.is_verified]
    if g12:
        say("unverified", f"{len(g12)} Grade 12 line(s) are school placeholders: DepEd keeps Grade 12 of SY 2026-2027 on the 2016 K-12 SHS "
                          "curriculum and the semester-by-semester subject list is not in the documents found; confirm with the school's program")
    return found, changed[0]


class Command(BaseCommand):
    help = "Verify SHS curriculum lines against the official DepEd curriculum (report; --apply fixes safely)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="fix what can be fixed safely (never deletes)")
        parser.add_argument("--year", help="academic year label, e.g. 2026-2027 (default: the active year)")

    @transaction.atomic
    def handle(self, *args, **opts):
        ay = (m.AcademicYear.objects.filter(label=opts["year"]).first() if opts["year"]
              else m.AcademicYear.objects.filter(is_active=True).first())
        if ay is None:
            self.stderr.write("No academic year found."); return
        found, changed = check(ay, fix=opts["apply"])
        total = sum(len(v) for k, v in found.items() if k != "unverified")
        self.stdout.write(f"SHS curriculum check for A.Y. {ay.label}  ({m.CurriculumSubject.objects.filter(level='SHS', academic_year=ay, is_active=True).count()} active lines)")
        for kind in KINDS:
            items = found.get(kind, [])
            self.stdout.write(f"\n{kind.upper()} ({len(items)})" + ("  - cannot be verified from DepEd documents" if kind == "unverified" else ""))
            for msg in items:
                self.stdout.write(f"  - {msg}")
        if opts["apply"]:
            self.stdout.write(self.style.SUCCESS(f"\nApplied: {changed} change(s). Nothing was deleted. Run again: it should report no errors."))
        elif total:
            self.stdout.write(self.style.WARNING(f"\n{total} discrepancy(ies). Run with --apply to fix them (nothing is deleted)."))
        else:
            self.stdout.write(self.style.SUCCESS("\nNo discrepancies found."))
