"""
Imports IT's 2021-2026 class-program spreadsheet (one sheet per semester,
e.g. "1st 26-27", "2nd 25-26") into HistoricalClassRecord rows.

Usage:
    python manage.py import_historical_schedule /path/to/GTI_class_prog_2021-2026.xlsx
    python manage.py import_historical_schedule /path/to/file.xlsx --dry-run

Re-running is safe: each sheet's existing rows (same school_year+semester)
are deleted and reinserted, so nothing duplicates.
"""
import re
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


TIME_RANGE_RE = re.compile(
    r'^(?P<days>[A-Z]+)\s+(?P<start>\d{1,2}:\d{2}[AP]M)-(?P<end>\d{1,2}:\d{2}[AP]M)$'
)

# Longest-match-first day tokenizer. "SAT" and "TH" must be tried before
# their single-letter prefixes (S, T) or they'd never match.
# NOTE: this dataset also uses a bare "S" for what context (same GE/PE rows,
# same time blocks as "SAT" entries) makes clear means Saturday, not Sunday --
# the system has no Sunday timeslot at all (engine.models.TimeSlot.DAYS caps
# at Sat), and Philippine college schedules here don't run Sunday classes.
# If that assumption is ever wrong for a specific row, source_row + the raw
# sheet are kept so it's traceable and fixable.
DAY_TOKEN_MAP = {"SAT": "Sat", "TH": "Thu", "M": "Mon", "T": "Tue", "W": "Wed", "F": "Fri", "S": "Sat"}
TOKEN_ORDER = sorted(DAY_TOKEN_MAP.keys(), key=len, reverse=True)

SHEET_NAME_RE = re.compile(r'^(1st|2nd)\s+(\d{2})-(\d{2})$')


def decompose_days(day_code):
    """'WTH' -> ['Wed', 'Thu']; 'SAT' -> ['Sat']; 'MTH' -> ['Mon', 'Thu']."""
    code = day_code.strip().upper()
    days = []
    i = 0
    while i < len(code):
        for tok in TOKEN_ORDER:
            if code.startswith(tok, i):
                days.append(DAY_TOKEN_MAP[tok])
                i += len(tok)
                break
        else:
            i += 1  # unrecognized character -- skip rather than crash the import
    return days


def parse_time_day(raw):
    """'WTH 3:00PM-4:30PM' -> (['Wed','Thu'], time(15,0), time(16,30)) or None if unparseable."""
    if not raw or not isinstance(raw, str):
        return None
    m = TIME_RANGE_RE.match(raw.strip())
    if not m:
        return None
    try:
        start = datetime.strptime(m.group("start"), "%I:%M%p").time()
        end = datetime.strptime(m.group("end"), "%I:%M%p").time()
    except ValueError:
        return None
    return decompose_days(m.group("days")), start, end


def parse_sheet_name(name):
    """'1st 26-27' -> ('2026-2027', '1st Sem'); '2nd 25-26' -> ('2025-2026', '2nd Sem')."""
    m = SHEET_NAME_RE.match(name.strip())
    if not m:
        return None
    term, yy1, yy2 = m.groups()
    semester = "1st Sem" if term == "1st" else "2nd Sem"
    school_year = f"20{yy1}-20{yy2}"
    return school_year, semester


def match_teacher(teacher_name_raw, faculty_by_lastname):
    """Best-effort match of 'Lastname, Firstname M.' (or 'Lastname Jr., Firstname P.')
    against current FacultyProfile records, indexed by lowercased last name.
    Returns the matched FacultyProfile or None -- never guesses on ambiguity.

    A handful of real rows list several co-teachers/proctors in one cell
    (e.g. 'Gabon, Beatrix Charissa V. , Bergonia, Valiliean I. , ...', ~20
    names in one string). This function only ever reads the FIRST
    "Lastname, Firstname" pair out of a string like that -- it does not try
    to split and match each of the listed names -- so these rows reliably
    come back unmatched (teacher=None) rather than guessing one of the
    several people involved. teacher_name_raw still keeps the full original
    text regardless, so nothing is lost -- it just isn't linked to a single
    FacultyProfile for workload/pattern purposes."""
    if not teacher_name_raw or teacher_name_raw.strip().upper() == "TBA":
        return None
    if "," not in teacher_name_raw:
        return None
    last_part, first_part = teacher_name_raw.split(",", 1)
    last_key = last_part.strip().lower()
    candidates = faculty_by_lastname.get(last_key, [])
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        first_token = first_part.strip().split()[0].lower() if first_part.strip() else ""
        narrowed = [fp for fp in candidates if fp.user.first_name.strip().lower().startswith(first_token)] if first_token else []
        if len(narrowed) == 1:
            return narrowed[0]
    return None  # 0 matches, or still ambiguous -- don't guess


class Command(BaseCommand):
    help = "Import the historical (2021-2026) class-program xlsx into HistoricalClassRecord."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str)
        parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to the DB.")

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("openpyxl is required: pip install openpyxl")

        from analytics.models import HistoricalClassRecord
        from faculty.models import FacultyProfile

        path = options["xlsx_path"]
        dry_run = options["dry_run"]

        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except Exception as e:
            raise CommandError(f"Could not open '{path}': {e}")

        faculty_by_lastname = {}
        for fp in FacultyProfile.objects.select_related("user").all():
            key = fp.user.last_name.strip().lower()
            faculty_by_lastname.setdefault(key, []).append(fp)

        total_created = 0
        total_skipped_unparseable = 0
        total_matched_teacher = 0
        total_unmatched_teacher = 0
        sheets_skipped = []

        for sheet_name in wb.sheetnames:
            parsed_term = parse_sheet_name(sheet_name)
            if parsed_term is None:
                sheets_skipped.append(sheet_name)
                continue
            school_year, semester = parsed_term

            ws = wb[sheet_name]
            rows_to_create = []
            last = None  # carries code/desc/section/room/teacher/units/students for continuation rows

            for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                row = (row + (None,) * 8)[:8]
                code, desc, section, time_day, room, teacher_raw, units, students = row
                if all(v is None for v in row):
                    continue

                if code is None and time_day is not None and last is not None:
                    # Continuation row: this class ALSO meets at this other day/time.
                    code, desc, section, room, teacher_raw, units, students = (
                        last["code"], last["desc"], last["section"], last["room"],
                        last["teacher_raw"], last["units"], last["students"],
                    )
                elif code is None:
                    continue
                else:
                    last = {"code": code, "desc": desc, "section": section, "room": room,
                             "teacher_raw": teacher_raw, "units": units, "students": students}

                parsed = parse_time_day(time_day)
                if parsed is None:
                    total_skipped_unparseable += 1
                    continue
                days, start_t, end_t = parsed

                teacher_fp = match_teacher(teacher_raw if isinstance(teacher_raw, str) else None, faculty_by_lastname)
                if teacher_fp:
                    total_matched_teacher += 1
                elif teacher_raw and str(teacher_raw).strip().upper() != "TBA":
                    total_unmatched_teacher += 1

                for day in days:
                    rows_to_create.append(HistoricalClassRecord(
                        school_year=school_year, semester=semester,
                        subject_code=str(code).strip(),
                        description=(str(desc).strip() if desc else ""),
                        section_label=(str(section).strip() if section else ""),
                        day=day, start_time=start_t, end_time=end_t,
                        room_name=(str(room).strip() if room else ""),
                        teacher_name_raw=(str(teacher_raw).strip() if teacher_raw else ""),
                        teacher=teacher_fp,
                        units=units if isinstance(units, (int, float)) else None,
                        student_count=int(students) if isinstance(students, (int, float)) else None,
                        source_row=i,
                    ))

            if dry_run:
                self.stdout.write(f"[dry-run] {sheet_name} -> {school_year} {semester}: would import {len(rows_to_create)} rows")
                total_created += len(rows_to_create)
                continue

            with transaction.atomic():
                HistoricalClassRecord.objects.filter(school_year=school_year, semester=semester).delete()
                HistoricalClassRecord.objects.bulk_create(rows_to_create, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"{sheet_name} -> {school_year} {semester}: imported {len(rows_to_create)} rows"))
            total_created += len(rows_to_create)

        if sheets_skipped:
            self.stdout.write(self.style.WARNING(f"Skipped sheets with unrecognized names: {sheets_skipped}"))
        self.stdout.write(self.style.SUCCESS(
            f"\nTotal rows {'that would be ' if dry_run else ''}imported: {total_created}\n"
            f"Teacher name matched to an existing FacultyProfile: {total_matched_teacher}\n"
            f"Teacher name NOT matched (left null, raw text kept): {total_unmatched_teacher}\n"
            f"Rows skipped (unparseable TIME::DAY): {total_skipped_unparseable}"
        ))
