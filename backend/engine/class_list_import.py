"""
Class list upload: a CSV / Excel file with three columns -- Full Name, Section, Year Level -- for ONE program and
semester chosen in the screen. No School ID is needed. Each row is matched to an existing section of that
program (same year level and section name); rows that cannot be matched are reported, never guessed.
"""
import csv
import io
import re
import zipfile
from collections import Counter

from .models import Section, Schedule, Student

MAX_IMPORT_BYTES = 4 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
MAX_IMPORT_COLUMNS = 40
MAX_CELL_CHARACTERS = 500
MAX_XLSX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_XLSX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 100

ORD = {1: "1st Year", 2: "2nd Year", 3: "3rd Year", 4: "4th Year", 5: "5th Year", 6: "6th Year"}
WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6}


def year_key(v):
    """'1', '1st', '1st Year', 'First Year', 'Year 1' -> '1st Year'; None when unreadable."""
    t = str(v or "").strip().lower()
    m = re.search(r"\d+", t)
    if m:
        return ORD.get(int(m.group()))
    for w, n in WORDS.items():
        if w in t:
            return ORD[n]
    return None


def name_key(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def read_rows(upload):
    """[(row number, [cells])] from a .csv or .xlsx upload."""
    if upload.size > MAX_IMPORT_BYTES:
        raise ValueError("The class list is larger than 4 MB. Choose a smaller file.")
    name = (upload.name or "").lower()
    data = upload.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("The class list is larger than 4 MB. Choose a smaller file.")
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        # XLSX is a ZIP archive. Reject highly compressed or oversized members
        # before openpyxl expands XML/shared-string data into memory.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            expanded_size = sum(member.file_size for member in members)
            if expanded_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise ValueError("The Excel workbook expands beyond the 32 MB import limit.")
            if any(member.file_size > MAX_XLSX_MEMBER_BYTES
                   or (member.file_size and not member.compress_size)
                   or (member.compress_size and member.file_size / member.compress_size > MAX_XLSX_COMPRESSION_RATIO)
                   for member in members):
                raise ValueError("The Excel workbook uses an unsupported compression ratio or file size.")
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            ws = workbook.active
            # Do not trust worksheet dimensions from an uploaded workbook. Bound
            # both axes and reject sheets that exceed the import's supported size.
            if ((ws.max_row or 0) > MAX_IMPORT_ROWS
                    or (ws.max_column or 0) > MAX_IMPORT_COLUMNS):
                raise ValueError("The class list may contain at most 10,000 rows and 40 columns.")
            rows = []
            for i, row in enumerate(ws.iter_rows(
                    min_row=1, max_row=MAX_IMPORT_ROWS + 1,
                    min_col=1, max_col=MAX_IMPORT_COLUMNS, values_only=True), 1):
                if i > MAX_IMPORT_ROWS:
                    raise ValueError("The class list may contain at most 10,000 rows.")
                cells = ["" if c is None else str(c).strip() for c in row]
                if any(len(cell) > MAX_CELL_CHARACTERS for cell in cells):
                    raise ValueError("Each class-list cell must be 500 characters or fewer.")
                rows.append((i, cells))
            return rows
        finally:
            workbook.close()
    if name.endswith((".csv", ".txt")):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        rows = []
        for i, row in enumerate(csv.reader(io.StringIO(text)), 1):
            if i > MAX_IMPORT_ROWS:
                raise ValueError("The class list may contain at most 10,000 rows.")
            if len(row) > MAX_IMPORT_COLUMNS:
                raise ValueError("The class list may contain at most 40 columns.")
            cells = [c.strip() for c in row]
            if any(len(cell) > MAX_CELL_CHARACTERS for cell in cells):
                raise ValueError("Each class-list cell must be 500 characters or fewer.")
            rows.append((i, cells))
        return rows
    raise ValueError("Upload a .csv or .xlsx file.")


def find_columns(rows):
    """(header row number, name col, section col, year col) from the first row that looks like a header."""
    for n, cells in rows:
        low = [c.lower() for c in cells]
        nm = next((i for i, c in enumerate(low) if "name" in c), None)
        sc = next((i for i, c in enumerate(low) if "section" in c), None)
        yr = next((i for i, c in enumerate(low) if "year" in c), None)
        if nm is not None and sc is not None and yr is not None:
            return n, nm, sc, yr
    raise ValueError("The first row must have the columns: Full Name, Section, Year Level.")


def default_semester(program):
    """The semester whose sections are actually scheduled; otherwise the first one the program has."""
    secs = Section.objects.filter(program=program)
    counts = Counter(Schedule.objects.filter(section__in=secs).values_list("section__semester", flat=True))
    if counts:
        return counts.most_common(1)[0][0]
    first = secs.order_by("semester").values_list("semester", flat=True).first()
    return first or ""


def run_import(upload, program, semester, commit):
    rows = read_rows(upload)
    header, c_name, c_sec, c_year = find_columns(rows)
    semester = semester or default_semester(program)
    sections = {}
    for s in Section.objects.filter(program=program, semester=semester):
        sections[(year_key(s.year_level), name_key(s.name))] = s
    existing = {(st.section_id, st.full_name.strip().lower()) for st in Student.objects.filter(section__program=program, section__semester=semester)}
    seen, to_add, errors, dups = set(), [], [], 0
    for n, cells in rows:
        if n <= header or not any(cells):
            continue
        get = lambda i: cells[i].strip() if i < len(cells) else ""
        full, sec, yr = " ".join(get(c_name).split()), get(c_sec), get(c_year)
        if not full:
            errors.append({"row": n, "name": "", "message": "Full name is empty."})
            continue
        y = year_key(yr)
        if not y:
            errors.append({"row": n, "name": full, "message": f"Year level '{yr}' is not valid (use 1st Year, 2nd Year ...)."})
            continue
        s = sections.get((y, name_key(sec)))
        if s is None:
            errors.append({"row": n, "name": full, "message": f"No section '{sec}' for {program.name} {y} in {semester}."})
            continue
        k = (s.id, full.lower())
        if k in existing or k in seen:
            dups += 1
            continue
        seen.add(k)
        to_add.append((full, s))
    by_section = Counter(f"{s.year_level} - {s.name}" for _f, s in to_add)
    resized = 0
    if commit and to_add:
        Student.objects.bulk_create([Student(full_name=f, section=s, school_id=_new_ref()) for f, s in to_add])
        # keep the section's size (used to pick rooms that seat the class) in step with its real class list
        for s in {s for _f, s in to_add}:
            n_students = Student.objects.filter(section=s, is_active=True).count()
            if n_students > s.student_count:
                s.student_count = n_students
                s.save(update_fields=["student_count"])
                resized += 1
    return {"commit": commit, "program": program.name, "semester": semester, "rows": len(seen) + dups + len(errors),
            "to_add": len(to_add), "added": len(to_add) if commit else 0, "duplicates": dups, "errors": errors[:200],
            "error_count": len(errors), "by_section": [{"section": k, "count": v} for k, v in sorted(by_section.items())],
            "sections_resized": resized}


def _new_ref():
    import uuid
    return f"CL-{uuid.uuid4().hex[:10].upper()}"
