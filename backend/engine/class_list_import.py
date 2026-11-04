"""
Class list upload: a CSV / Excel file with three columns -- Full Name, Section, Year Level -- for ONE program and
semester chosen in the screen. No School ID is needed. Each row is matched to an existing section of that
program (same year level and section name); rows that cannot be matched are reported, never guessed.
"""
import csv
import io
import re
from collections import Counter

from .models import Section, Schedule, Student

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
    name = (upload.name or "").lower()
    data = upload.read()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        return [(i, ["" if c is None else str(c).strip() for c in row]) for i, row in enumerate(ws.iter_rows(values_only=True), 1)]
    if name.endswith((".csv", ".txt")):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        return [(i, [c.strip() for c in row]) for i, row in enumerate(csv.reader(io.StringIO(text)), 1)]
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
