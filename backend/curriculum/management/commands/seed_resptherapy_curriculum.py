"""
BS Respiratory Therapy curriculum (Allied Health), transcribed from the UPHSL curriculum residency evaluation screenshots.

Respiratory Therapy is NOT Radiologic Technology: this command never reads or changes the BS Radiologic Technology program.

    python manage.py seed_resptherapy_curriculum            # DRY RUN: shows what would be added / updated / skipped
    python manage.py seed_resptherapy_curriculum --apply    # write it (safe to run again: nothing is duplicated)
    python manage.py seed_resptherapy_curriculum --sections [--apply] [--students 30,28,25,20]
        # one section per year level and semester (B.c1 ... B.c4), only the missing ones

What it does
  * program "BS Respiratory Therapy" in the department the existing Allied Health programs (BS Physical / Occupational Therapy)
    already use (e.g. "College of Allied Health"), or --department to name it;
  * one Subject row per code, exactly as printed (lecture/lab pairs stay separate rows; a code ending in "L" whose lecture code is
    in the list is a lab subject: its units go in lab_units, so the scheduler uses a lab room, 3 h per lab unit);
  * Gen Ed (minor, owned by the Registrar): EPP, GE, GEC, PATHFIT, ELEC1A/ELEC1AL. Majors (owned by the Allied Health Dean): RT codes
    and OTPTRT1102. Each program keeps its own Subject rows (Subject is unique per code AND program), as every other program does;
    the Gen Ed codes are the same codes the other programs use, so shared Gen Ed classes can be matched by code;
  * the RT major subjects get the field "Respiratory Therapy" (approved), only when a subject has no field yet (a Dean's tag is kept).
    OTPTRT1102 (Human Anatomy & Physiology) is left untagged, like MOTPTRT1102 in Physical / Occupational Therapy.
Not done: sections, rooms, faculty and schedules are NOT created.

Decisions (approved):
  * RT3118L "Test of Pulmonary Function (Lab)" is printed with the wrong number: imported as RT3117L, the lab of RT3117.
  * RT4128 / RT4231 Clinical Education 1 / 2 - Internship (15 units each) are off campus and NOT imported, like RadTech / PT / OT.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

PROGRAM_NAME = "BS Respiratory Therapy"
FIELD_NAME = "Respiratory Therapy"
FALLBACK_DEPARTMENT = "Allied Health"          # the seed spelling (seed_it_pt_curricula) when no Allied Health program exists yet
SIBLINGS = ("BS Physical Therapy", "BS Occupational Therapy")

Y1, Y2, Y3, Y4 = "1st Year", "2nd Year", "3rd Year", "4th Year"
S1, S2 = "1st Sem", "2nd Sem"
m, M = "minor", "major"

# (code, title, units, year level, semester, classification) -- exactly as printed (see the decisions above)
CURRICULUM = [
    # ---- 1st Year, 1st Sem (25 units) ----
    ("EPP1", "English Proficiency Program", 3, Y1, S1, m),
    ("GE401", "Filipino Christian Living 1", 2, Y1, S1, m),
    ("GE501", "National Service Training Program/ROTC 1", 3, Y1, S1, m),
    ("GEC104", "Readings in Philippine History", 3, Y1, S1, m),
    ("GEC105", "Mathematics in the Modern World", 3, Y1, S1, m),
    ("GEC109", "Understanding the Self", 3, Y1, S1, m),
    ("OTPTRT1102", "Human Anatomy & Physiology", 3, Y1, S1, M),
    ("PATHFIT1", "Physical Activities Toward Health and Fitness 1", 2, Y1, S1, m),
    ("RT1101", "Introduction to Respiratory Therapy", 3, Y1, S1, M),
    # ---- 1st Year, 2nd Sem (28 units) ----
    ("EPP2", "Technical Writing", 3, Y1, S2, m),
    ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m),
    ("GE502", "National Service Training Program/ROTC 2", 3, Y1, S2, m),
    ("GEC101", "Art Appreciation", 3, Y1, S2, m),
    ("GEC102", "Ethics", 3, Y1, S2, m),
    ("GEC103", "The Contemporary World", 3, Y1, S2, m),
    ("GEC107", "Life and Works of Rizal", 3, Y1, S2, m),
    ("GEC108", "Science, Technology & Society", 3, Y1, S2, m),
    ("PATHFIT2", "Physical Activities Toward Health and Fitness 2", 2, Y1, S2, m),
    ("RT1203", "Health Education for Respiratory Therapy", 3, Y1, S2, M),
    # ---- 2nd Year, 1st Sem (25 units) ----
    ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m),
    ("GE602", "World Literature", 3, Y2, S1, m),
    ("GE701", "Biostatistics", 3, Y2, S1, m),
    ("GEC106", "Purposive Communication", 3, Y2, S1, m),
    ("PATHFIT3", "Physical Activities Toward Health and Fitness 3", 2, Y2, S1, m),
    ("RT2104", "Cardio-Respiratory Anatomy and Physiology", 3, Y2, S1, M),
    ("RT2105", "Medical Terminology", 3, Y2, S1, M),
    ("RT2106", "Microbiology for Respiratory Therapy 1", 3, Y2, S1, M),
    ("RT2107", "Fundamentals for Respiratory Therapy 1", 3, Y2, S1, M),
    # ---- 2nd Year, 2nd Sem (25 units) ----
    ("ELEC1A", "Living in the IT Era (lec)", 2, Y2, S2, m),
    ("ELEC1AL", "Living in the IT Era (lab)", 1, Y2, S2, m),
    ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m),
    ("PATHFIT4", "Physical Activities Toward Health and Fitness 4", 2, Y2, S2, m),
    ("RT2108", "Cardio-Respiratory Pharmacology", 3, Y2, S2, M),
    ("RT2109", "Neuroanatomy and Pathophysiology", 3, Y2, S2, M),
    ("RT2110", "Fundamentals of Respiratory Therapy 2 (Lec)", 3, Y2, S2, M),
    ("RT2110L", "Fundamentals of Respiratory Therapy 2 (Lab)", 2, Y2, S2, M),
    ("RT2211", "Patient Assessment and ECG (Lec)", 3, Y2, S2, M),
    ("RT2211L", "Patient Assessment and ECG (Lab)", 1, Y2, S2, M),
    ("RT2212", "Cardiopulmonary Pathology", 3, Y2, S2, M),
    # ---- 3rd Year, 1st Sem (19 units) ----
    ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m),
    ("RT3113", "Airway Management (Lec)", 2, Y3, S1, M),
    ("RT3113L", "Airway Management (Lab)", 1, Y3, S1, M),
    ("RT3114", "Introduction to Polysomnography", 2, Y3, S1, M),
    ("RT3115", "Pulmonary Rehabilitation (Lec)", 2, Y3, S1, M),
    ("RT3115L", "Pulmonary Rehabilitation (Lab)", 1, Y3, S1, M),
    ("RT3116", "Ventilation & Gas Exchange Monitoring (Lec)", 2, Y3, S1, M),
    ("RT3116L", "Ventilation & Gas Exchange Monitoring (Lab)", 1, Y3, S1, M),
    ("RT3117", "Test of Pulmonary Function (Lec)", 2, Y3, S1, M),
    ("RT3117L", "Test of Pulmonary Function (Lab)", 1, Y3, S1, M),      # printed "RT3118L" (approved correction)
    ("RT3119", "Pulmonary Disease Management", 3, Y3, S1, M),
    # ---- 3rd Year, 2nd Sem (24 units) ----
    ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m),
    ("RT3220", "Neonatal Respiratory Care (Lec)", 2, Y3, S2, M),
    ("RT3220L", "Neonatal Respiratory Care (Lab)", 1, Y3, S2, M),
    ("RT3221", "Pediatric Respiratory Care (Lec)", 2, Y3, S2, M),
    ("RT3221L", "Pediatric Respiratory Care (Lab)", 1, Y3, S2, M),
    ("RT3222", "Mechanical Ventilation (Lec)", 3, Y3, S2, M),
    ("RT3222L", "Mechanical Ventilation (Lab)", 1, Y3, S2, M),
    ("RT3223", "Critical Care Management (Lec)", 3, Y3, S2, M),
    ("RT3223L", "Critical Care Management (Lab)", 1, Y3, S2, M),
    ("RT3224", "Hemodynamics", 2, Y3, S2, M),
    ("RT3225", "Management in Health Care Ethics", 3, Y3, S2, M),
    ("RT3226", "Introduction to Research", 3, Y3, S2, M),
    # ---- 4th Year, 1st Sem (21 units; RT4128 Clinical Education 1 - Internship, 15 units, not imported) ----
    ("GE407", "Filipino Christian Living 7", 2, Y4, S1, m),
    ("RT4127", "Respiratory Care Seminar 1", 2, Y4, S1, M),
    ("RT4129", "Clinical Research 1", 2, Y4, S1, M),
    # ---- 4th Year, 2nd Sem (21 units; RT4231 Clinical Education 2 - Internship, 15 units, not imported) ----
    ("GE408", "Filipino Christian Living 8", 2, Y4, S2, m),
    ("RT4230", "Respiratory Care Seminar 2", 2, Y4, S2, M),
    ("RT4232", "Clinical Research 2", 2, Y4, S2, M),
]
NOT_IMPORTED = [("RT4128", "Clinical Education 1 - Internship", 15, Y4, S1), ("RT4231", "Clinical Education 2 - Internship", 15, Y4, S2)]
# Units printed per term in the file ("TOTAL REQUIRED UNITS"), used as a transcription check.
PRINTED_TOTALS = {(Y1, S1): 25, (Y1, S2): 28, (Y2, S1): 25, (Y2, S2): 25, (Y3, S1): 19, (Y3, S2): 24, (Y4, S1): 21, (Y4, S2): 21}


def split_units(code, units, codes):
    """(lecture units, lab units): a code ending in 'L' whose lecture code is in the list is a lab subject."""
    return (0, units) if code.endswith("L") and code[:-1] in codes else (units, 0)


def takes_field(code, classification):
    return classification == "major" and code.startswith("RT")


def check_transcription():
    """Every term adds up to the printed total (internships included); no code twice."""
    codes = [r[0] for r in CURRICULUM]
    if len(codes) != len(set(codes)):
        raise CommandError("A subject code appears twice in the curriculum list.")
    sums = {}
    for _c, _t, units, y, s, _k in CURRICULUM:
        sums[(y, s)] = sums.get((y, s), 0) + units
    for _c, _t, units, y, s in NOT_IMPORTED:
        sums[(y, s)] = sums.get((y, s), 0) + units
    bad = {k: (sums.get(k), v) for k, v in PRINTED_TOTALS.items() if sums.get(k) != v}
    if bad:
        raise CommandError(f"Units do not match the printed totals: {bad}")


def department_for(explicit=None):
    from curriculum.models import Program
    if explicit:
        return explicit
    found = sorted(set(Program.objects.filter(name__in=SIBLINGS).values_list("department", flat=True)))
    if len(found) > 1:
        raise CommandError(f"Physical / Occupational Therapy are in different departments {found}: pass --department.")
    return found[0] if found else FALLBACK_DEPARTMENT


def plan(department):
    """[(action, code, changes)] without writing. action: add / update / skip."""
    from curriculum.models import AcademicField, Program, Subject
    program = Program.objects.filter(name=PROGRAM_NAME).first()
    existing = {s.code: s for s in Subject.objects.filter(program=program)} if program else {}
    field = AcademicField.objects.filter(name=FIELD_NAME).first()
    codes = {r[0] for r in CURRICULUM}
    out = []
    for code, title, units, y, s, kind in CURRICULUM:
        lec, lab = split_units(code, units, codes)
        want = {"title": title, "lec_units": lec, "lab_units": lab, "year_level": y, "semester": s, "classification": kind}
        row = existing.get(code)
        if row is None:
            out.append(("add", code, want))
            continue
        diff = {k: (getattr(row, k), v) for k, v in want.items() if getattr(row, k) != v}
        if takes_field(code, kind) and row.field_id is None:
            diff["field"] = (None, FIELD_NAME)
        out.append(("update" if diff else "skip", code, diff))
    program_change = None
    if program is None:
        program_change = f"create program '{PROGRAM_NAME}' in '{department}'"
    elif program.department != department:
        program_change = f"program '{PROGRAM_NAME}' is in '{program.department}' (kept; pass --department to choose)"
    return program_change, (field is None), out


@transaction.atomic
def apply(department):
    from curriculum.models import AcademicField, Program, Subject
    program, _ = Program.objects.get_or_create(name=PROGRAM_NAME, defaults={"department": department})
    field, _ = AcademicField.objects.get_or_create(name=FIELD_NAME)
    codes = {r[0] for r in CURRICULUM}
    counts = {"add": 0, "update": 0, "skip": 0}
    for code, title, units, y, s, kind in CURRICULUM:
        lec, lab = split_units(code, units, codes)
        want = {"title": title, "lec_units": lec, "lab_units": lab, "year_level": y, "semester": s, "classification": kind}
        row = Subject.objects.filter(program=program, code=code).first()
        if row is None:
            Subject.objects.create(program=program, code=code, field=field if takes_field(code, kind) else None, **want)
            counts["add"] += 1
            continue
        changed = [k for k, v in want.items() if getattr(row, k) != v]
        for k in changed:
            setattr(row, k, want[k])
        if takes_field(code, kind) and row.field_id is None:          # never replaces a field the Dean already set
            row.field = field
            changed.append("field")
        if changed:
            row.save(update_fields=changed)
        counts["update" if changed else "skip"] += 1
    return program, counts


DEFAULT_STUDENTS = "30,28,25,20"     # students per section, 1st-4th Year (same as BS Occupational Therapy; the Dean sets the real enrollment)


def section_plan(students):
    """[(year, semester, name, students, exists)] for one section per year level and semester (names B.c1 ... B.c4)."""
    from curriculum.models import Program
    from curriculum.section_codes import section_name
    from engine.models import Section
    program = Program.objects.filter(name=PROGRAM_NAME).first()
    if program is None:
        raise CommandError("The BS Respiratory Therapy program does not exist yet: run the command with --apply (without --sections) first.")
    sizes = [int(x) for x in students.split(",")]
    if len(sizes) != 4 or any(n < 1 or n > 500 for n in sizes):
        raise CommandError("--students needs 4 numbers (1st-4th Year), each 1-500, e.g. 30,28,25,20")
    out = []
    for y, sem in sorted({(r[3], r[4]) for r in CURRICULUM}):
        exists = Section.objects.filter(program=program, year_level=y, semester=sem).exists()
        out.append((y, sem, section_name(program, y), sizes[int(y[0]) - 1], exists))
    return program, out


@transaction.atomic
def apply_sections(program, rows):
    from engine.models import Section
    made = 0
    for y, sem, name, n, exists in rows:
        if not exists and not Section.objects.filter(program=program, year_level=y, semester=sem).exists():
            Section.objects.create(program=program, name=name, year_level=y, semester=sem, student_count=n)
            made += 1
    return made


class Command(BaseCommand):
    help = "Add the BS Respiratory Therapy curriculum (Allied Health). Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run, nothing is written)")
        parser.add_argument("--department", default="", help="department name (default: the one BS Physical / Occupational Therapy use)")
        parser.add_argument("--sections", action="store_true",
                            help="only add the missing sections: one per year level and semester (B.c1 ... B.c4); existing ones are kept")
        parser.add_argument("--students", default=DEFAULT_STUDENTS, help="students per section for 1st-4th Year (default %(default)s)")

    def handle(self, *args, **o):
        if o["sections"]:
            program, rows = section_plan(o["students"])
            self.stdout.write(f"Sections of {program.name} ({program.department}):")
            for y, sem, name, n, exists in rows:
                self.stdout.write(f"  {'keep' if exists else 'add':5} {name:6} {y}, {sem}: {n} students")
            missing = [r for r in rows if not r[4]]
            self.stdout.write(f"Summary: {len(missing)} to add, {len(rows) - len(missing)} already exist. Subjects, rooms, faculty and schedules are not touched.")
            if not o["apply"]:
                self.stdout.write(self.style.WARNING("DRY RUN: nothing was written. Run again with --sections --apply to write it."))
                return
            self.stdout.write(self.style.SUCCESS(f"Done: {apply_sections(program, rows)} sections added."))
            return
        check_transcription()
        dept = department_for(o["department"] or None)
        program_change, new_field, rows = plan(dept)
        self.stdout.write(f"Department: {dept}")
        if program_change:
            self.stdout.write(f"Program: {program_change}")
        if new_field:
            self.stdout.write(f"Field: create '{FIELD_NAME}' (for the RT major subjects)")
        self.stdout.write(f"{'ACTION':8} {'CODE':11} {'YEAR / SEM':20} {'KIND':6} {'LEC':>3} {'LAB':>3}  TITLE / CHANGES")
        info = {r[0]: r for r in CURRICULUM}
        codes = set(info)
        for action, code, diff in rows:
            _c, title, units, y, s, kind = info[code]
            lec, lab = split_units(code, units, codes)
            extra = title if action == "add" else ("; ".join(f"{k}: {a!r} -> {b!r}" for k, (a, b) in diff.items()) or "no change")
            self.stdout.write(f"{action:8} {code:11} {y + ', ' + s:20} {kind:6} {lec:>3} {lab:>3}  {extra}")
        tally = {a: sum(1 for r in rows if r[0] == a) for a in ("add", "update", "skip")}
        self.stdout.write(f"Summary: {tally['add']} to add, {tally['update']} to update, {tally['skip']} unchanged "
                          f"({len(rows)} subjects in the list).")
        self.stdout.write("Not imported (off campus, approved): " + ", ".join(f"{c} {t} ({u} units)" for c, t, u, _y, _s in NOT_IMPORTED))
        self.stdout.write("Not created: sections (use --sections), rooms, faculty, schedules.")
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN: nothing was written. Run again with --apply to write it."))
            return
        program, counts = apply(dept)
        self.stdout.write(self.style.SUCCESS(f"Done: program '{program.name}' ({program.department}); {counts['add']} subjects added, "
                                             f"{counts['update']} updated, {counts['skip']} unchanged."))
