"""
Generates a printable PDF of a class schedule, styled to match both UPHSL's
own printed schedules AND the reference workspace UI (workspace eyebrow label,
timestamp, badge-style status column, footer link). Uses reportlab -- pure
Python, no system-level dependencies, safe to install on Windows.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

NAVY = colors.HexColor("#003366")
LIGHT_BLUE = colors.HexColor("#f7fafc")
GOLD = colors.HexColor("#b8860b")

# engine.models.TimeSlot.DAYS short codes, in actual weekday order -- sorting
# rows by the raw day string (the previous behavior) sorted alphabetically
# ("Fri" < "Mon" < "Sat" < "Thu" < "Tue" < "Wed"), which is why the PDF's row
# order looked scrambled instead of running Monday through Saturday.
DAY_SORT_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5}


def _teacher_display_name(teacher):
    """Full name when we have one, falling back to the username -- matches
    what the rest of the app shows instead of the raw login id."""
    full_name = teacher.user.get_full_name().strip()
    return full_name or teacher.user.username


def _merge_by_day(schedules):
    """Same grouping logic as the frontend's mergeSchedules.js -- one row per
    subject+section+room+teacher+day, spanning earliest start to latest end,
    so the PDF matches what's shown on screen instead of listing every period
    as a separate line."""
    groups = {}
    for s in schedules:
        # Grouping key still uses the subject CODE (unique) rather than the
        # title (which can repeat, e.g. two different "Understanding the
        # Self" offerings) -- only the displayed "subject" value below drops
        # the code, per the request to show just the subject name in print.
        key = (s.subject.code, s.section.name, s.room.name, s.teacher.user.username, s.timeslot.day)
        if key not in groups:
            groups[key] = {
                "subject": s.subject.title,
                "code": s.subject.code,
                "section_id": s.section_id,
                "section": s.section.name,
                "room": s.room.name,
                "teacher": _teacher_display_name(s.teacher),
                "day": s.timeslot.day,
                "start": s.timeslot.start_time,
                "end": s.timeslot.end_time,
                "is_manual_override": False,
            }
        g = groups[key]
        if s.is_manual_override:
            g["is_manual_override"] = True
        if s.timeslot.start_time < g["start"]:
            g["start"] = s.timeslot.start_time
        if s.timeslot.end_time > g["end"]:
            g["end"] = s.timeslot.end_time
    return list(groups.values())


# ---------------------------------------------------------------------------------------------------------
# "Year Level | Semester/Term | Academic Year" line, printed directly under the department name on EVERY
# schedule preview / PDF (class, exam and basic-education) so a printed page says what it covers.
# ---------------------------------------------------------------------------------------------------------
def _ordinal_key(v):
    import re
    m = re.match(r"\s*(\d+)", str(v or ""))
    return (int(m.group(1)) if m else 99, str(v))


def default_academic_year(today=None):
    """School year that contains `today` (June starts a new one): 2026-2027."""
    today = today or datetime.now()
    y = today.year if today.month >= 6 else today.year - 1
    return f"{y}-{y + 1}"


def term_words(value):
    """'1st Sem' -> '1st Semester'; terms and anything else are kept as written."""
    v = (value or "").strip()
    return v.replace(" Sem", " Semester") if v.endswith(" Sem") else v


def scope_parts(year_levels=(), terms=(), academic_years=(), term_label=None):
    """[(label, text)] for Year Level, Semester/Term and Academic Year; blank values are shown as 'All'/'-'."""
    yl = sorted({str(x).strip() for x in year_levels if x}, key=_ordinal_key)
    tm = sorted({term_words(x) for x in terms if x}, key=_ordinal_key)
    ay = sorted({str(x).strip() for x in academic_years if x})
    label = term_label or ("Term" if any("term" in t.lower() for t in tm) else "Semester")
    yl_text = ", ".join(yl)
    if len(yl) >= 3 and all(_ordinal_key(x)[0] < 99 for x in yl):
        yl_text = f"{yl[0].split()[0]} to {yl[-1]}"          # 1st to 4th Year
    return [("Year Level", yl_text or "All year levels"),
            (label, ", ".join(tm) or f"All {label.lower()}s"),
            ("Academic Year", ", ".join(ay) or default_academic_year())]


def scope_html(parts):
    return " &nbsp;|&nbsp; ".join(f"{k}: <b>{v}</b>" for k, v in parts)



def _fmt_time(t):
    return t.strftime("%I:%M%p").lstrip("0")


# Printed under the table ("Approved by"). Change here if the School Director changes.
SCHOOL_DIRECTOR_NAME = "Dr. Rosalina R. Pangilinan"
SCHOOL_DIRECTOR_TITLE = "School Director"


def _dean_for(department):
    """(complete name, department) of the dean who heads `department`; name is blank if none is set up."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for u in User.objects.filter(role="faculty", faculty_type="dean").order_by("id"):
        if department in u.departments:
            return (u.get_full_name().strip() or u.username), department
    return "", department


def _signature_blocks(departments, styles):
    """'Prepared by' (the dean) on the left, 'Approved by' (school director) on the right --
    one row per department that appears in the schedule."""
    plain = ParagraphStyle("SigPlain", parent=styles["Normal"], fontName="Times-Roman", fontSize=10.5, leading=14)
    bold = ParagraphStyle("SigBold", parent=plain, fontName="Times-Bold")
    rows = []
    for dept in (departments or [""]):
        name, dept_label = _dean_for(dept) if dept else ("", "")
        left = [Paragraph("Prepared by:", plain), Spacer(1, 26),
                Paragraph(name or "_______________________", bold),
                Paragraph(f"Dean, {dept_label}" if dept_label else "Dean", plain)]
        right = [Paragraph("Approved by:", plain), Spacer(1, 26),
                 Paragraph(SCHOOL_DIRECTOR_NAME, bold), Paragraph(SCHOOL_DIRECTOR_TITLE, plain)]
        rows.append([left, right])
    t = Table(rows, colWidths=[4.4*inch, 4.4*inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
    return t


def build_schedule_pdf(schedules, title, subtitle="", workspace_label="REGISTRAR WORKSPACE", source_url="", departments=None,
                       year_level=None, semester=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(letter),
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    now_str = datetime.now().strftime("%m/%d/%y, %I:%M %p")

    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    eyebrow_style = ParagraphStyle("Eyebrow", parent=styles["Normal"], fontSize=9, textColor=GOLD, fontName="Helvetica-Bold")
    scope_style = ParagraphStyle("Scope", parent=styles["Normal"], fontSize=10.5, leading=14, textColor=colors.HexColor("#1f2937"), spaceBefore=2, spaceAfter=2)
    title_style = ParagraphStyle("TitleNavy", parent=styles["Title"], textColor=NAVY, fontSize=22, alignment=0, spaceAfter=2, leading=26)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"), spaceBefore=4)

    # Plain Python strings in a reportlab Table are NOT word-wrapped -- the
    # table only auto-sizes row height for genuine Flowables (Paragraphs).
    # Feeding it raw strings for long values (a full subject title, a two-word
    # teacher name) let a too-long line get clipped and visually bleed into
    # the next column/row, which is the "overlaying" / messy look being fixed
    # here. Every body cell is now wrapped in its own Paragraph so each
    # column wraps independently and the row grows to fit its tallest cell.
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#1f2937"),
    )
    header_style = ParagraphStyle(
        "CellHeader", parent=styles["Normal"], fontSize=9.5, leading=12,
        textColor=colors.white, fontName="Helvetica-Bold",
    )

    elements = [
        Paragraph(f"{now_str} &nbsp;&nbsp;&nbsp; <font color='#003366'><b>U-FAST Academic Scheduling</b></font>", meta_style),
        Spacer(1, 10),
        Paragraph(workspace_label, eyebrow_style),
        Paragraph(title, title_style),
        Paragraph(scope_html(scope_parts(
            [year_level] if year_level else [x.section.year_level for x in schedules],
            [semester] if semester else [x.section.semester for x in schedules],
            [x.school_year for x in schedules])), scope_style),
    ]
    if subtitle:
        elements.append(Paragraph(subtitle, sub_style))
    elements.append(Spacer(1, 18))

    grouped = _merge_by_day(schedules)
    # Chronological Mon->Sat, then by start time within each day -- NOT the
    # alphabetical string sort this used to do (see DAY_SORT_ORDER above).
    grouped.sort(key=lambda g: (DAY_SORT_ORDER.get(g["day"], 99), g["start"], g["section"]))

    # Status column removed -- Manual-vs-Generated provenance isn't something
    # the printed/exported copy needs to show. Column order is now Day & Time
    # first, then Subject, Room, Section, Teacher, per request.
    headers = ["Day & Time", "Subject", "Room", "Section", "Teacher"]
    data = [[Paragraph(h, header_style) for h in headers]]
    # Lec / Lab pairs (codes X and XL, same section): a small second line says which comes first, like the on-screen tag
    first = {}
    for g in grouped:                     # already in week order, so the first one seen is the earliest meeting
        first.setdefault((g["section_id"], g["code"]), g)

    def _pair_note(g):
        code = g["code"] or ""
        is_lab = len(code) > 1 and code.endswith("L")
        p = first.get((g["section_id"], code[:-1] if is_lab else code + "L"))
        if p is None:
            return ""
        when = f"{p['day']} {_fmt_time(p['start'])}-{_fmt_time(p['end'])}"
        return f'<br/><font size="7" color="#475569">{"Lab, after Lec " if is_lab else "Lec, then Lab "}{when}</font>'

    for g in grouped:
        data.append([
            Paragraph(f"{g['day']}&nbsp;&nbsp;{_fmt_time(g['start'])}-{_fmt_time(g['end'])}", cell_style),
            Paragraph(g["subject"] + _pair_note(g), cell_style),
            Paragraph(g["room"], cell_style),
            Paragraph(g["section"], cell_style),
            Paragraph(g["teacher"], cell_style),
        ])

    col_widths = [1.8*inch, 3.4*inch, 1.1*inch, 0.8*inch, 1.8*inch]
    table = Table(data, repeatRows=1, colWidths=col_widths)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BLUE]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)

    footer_text = f"{source_url}" if source_url else "U-FAST -- University - Faculty Academic Scheduling Tool"
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(footer_text, meta_style))

    # Signature block under the table: Prepared by (Dean) / Approved by (School Director).
    elements.append(Spacer(1, 14))
    elements.append(KeepTogether([_signature_blocks(departments, styles)]))

    doc.build(elements)
    buffer.seek(0)
    return buffer
