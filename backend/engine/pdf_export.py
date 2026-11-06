"""
Generates a printable PDF of a class schedule, styled to match both UPHSL's
own printed schedules AND the reference workspace UI (workspace eyebrow label,
timestamp, badge-style status column, footer link). Uses reportlab -- pure
Python, no system-level dependencies, safe to install on Windows.
"""
import io
from datetime import datetime
from reportlab.lib import colors
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


def _signature_blocks(departments, styles, width, scale=1.0):
    """'Prepared by' (the dean) on the left, 'Approved by' (school director) on the right --
    one row per department that appears in the schedule. Printed ONCE, at the very end of the document."""
    plain = ParagraphStyle("SigPlain", parent=styles["Normal"], fontName="Times-Roman", fontSize=10.5, leading=14)
    bold = ParagraphStyle("SigBold", parent=plain, fontName="Times-Bold")
    rows = []
    for dept in (departments or [""]):
        name, dept_label = _dean_for(dept) if dept else ("", "")
        left = [Paragraph("Prepared by:", plain), Spacer(1, 26 * max(scale, 0.75)),
                Paragraph(name or "_______________________", bold),
                Paragraph(f"Dean, {dept_label}" if dept_label else "Dean", plain)]
        right = [Paragraph("Approved by:", plain), Spacer(1, 26 * max(scale, 0.75)),
                 Paragraph(SCHOOL_DIRECTOR_NAME, bold), Paragraph(SCHOOL_DIRECTOR_TITLE, plain)]
        rows.append([left, right])
    t = Table(rows, colWidths=[width / 2, width / 2])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 12 * scale)]))
    return t


# ---------------------------------------------------------------------------------------------------------
# Layout (portrait A4).
#   * ONE year level per page: "All year levels" prints page 1 = 1st Year, page 2 = 2nd Year, ... (a year level without classes is
#     skipped, no blank page). Every page repeats the school header and has its own heading (program, year, semester, A.Y.).
#   * ONE signatory block, directly below the table of the LAST page. A single year level is one page with its signatory.
#   * Each page is MEASURED before the PDF is built: font and row padding are reduced step by step (text never under 8 pt) until the
#     page fits. A table that still cannot fit continues on the next page (rows never split, column header repeated) and the
#     signatory travels with its last rows, never alone; the year level and its row count are reported (build_schedule_pdf.fit_info).
# ---------------------------------------------------------------------------------------------------------
import logging

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import PageBreak

log = logging.getLogger(__name__)

PAGE = A4
MARGIN = 0.5 * inch
FRAME_PAD = 6                                   # SimpleDocTemplate's frame padding (each side)
CONTENT_W = PAGE[0] - 2 * MARGIN
AVAIL_W = CONTENT_W - 2 * FRAME_PAD
AVAIL_H = PAGE[1] - 2 * MARGIN - 2 * FRAME_PAD
# (body font pt, vertical row padding pt): the padding shrinks first, the text never goes under 8 pt
FIT_STEPS = ((9, 7), (9, 5), (9, 3.5), (8.5, 3), (8.5, 2.2), (8, 2), (8, 1.5))
TAIL_ROWS = 3                                   # rows kept with the signatory if a page cannot be fitted
OTHER_COLS = (0.46, 0.13, 0.13, 0.28)           # Subject, Room, Section, Teacher share what Day & Time leaves


def _group_tables(schedules):
    """[(program name, year level, semester, academic year, [rows])] in program order, then 1st, 2nd, 3rd, 4th year."""
    by = {}
    for s in schedules:
        key = (s.section.program.name if s.section.program_id else "", s.section.year_level or "")
        by.setdefault(key, []).append(s)
    out = []
    for (prog, yl), rows in sorted(by.items(), key=lambda kv: (kv[0][0], _ordinal_key(kv[0][1]))):
        sems = sorted({r.section.semester for r in rows if r.section.semester}, key=_ordinal_key)
        ays = sorted({r.school_year for r in rows if r.school_year})
        out.append((prog, yl, ", ".join(term_words(x) for x in sems), ", ".join(ays) or default_academic_year(), rows))
    return out


def _day_time(g):
    return f"{g['day']} {_fmt_time(g['start'])}-{_fmt_time(g['end'])}"


def _col_widths(all_groups, font):
    """Day & Time wide enough for its longest text on ONE line ("Wed 10:00AM-12:00PM"); the rest is shared by the other columns."""
    longest = max([stringWidth(_day_time(g), "Helvetica", font) for g in all_groups] + [stringWidth("Day & Time", "Helvetica-Bold", font + 0.5)])
    dt = min(longest + 2 * 6 + 4, AVAIL_W * 0.32)
    rest = AVAIL_W - dt
    return [dt] + [f * rest for f in OTHER_COLS]


def _rows(grouped, font, header_style, cell_style, note_style):
    header = [Paragraph(h, header_style) for h in ("Day &amp; Time", "Subject", "Room", "Section", "Teacher")]
    first = {}
    for g in grouped:                     # already in week order, so the first one seen is the earliest meeting
        first.setdefault((g["section_id"], g["code"]), g)
    body = []
    for g in grouped:
        code = g["code"] or ""
        is_lab = len(code) > 1 and code.endswith("L")
        p = first.get((g["section_id"], code[:-1] if is_lab else code + "L"))
        subject = [Paragraph(g["subject"], cell_style)]
        if p is not None:                 # the small Lec / Lab note: its own tight line, no extra spacing
            subject.append(Paragraph(f'{"Lab, after Lec " if is_lab else "Lec, then Lab "}{_day_time(p)}', note_style))
        body.append([Paragraph(_day_time(g).replace(" ", "&nbsp;"), cell_style), subject,
                     Paragraph(g["room"], cell_style), Paragraph(g["section"], cell_style), Paragraph(g["teacher"], cell_style)])
    return header, body


def _table(rows, widths, pad_v, pad_h, with_header=True, first_stripe=0):
    t = Table(rows, repeatRows=1 if with_header else 0, colWidths=widths, splitByRow=1)
    stripes = [colors.white, LIGHT_BLUE] if first_stripe % 2 == 0 else [LIGHT_BLUE, colors.white]
    cmds = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), pad_h), ("RIGHTPADDING", (0, 0), (-1, -1), pad_h),
            ("TOPPADDING", (0, 0), (-1, -1), pad_v), ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v)]
    if with_header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), stripes)]
    else:
        cmds += [("ROWBACKGROUNDS", (0, 0), (-1, -1), stripes)]
    t.setStyle(TableStyle(cmds))
    return t


def _height(flowables):
    total = 0
    for f in flowables:
        _w, h = f.wrap(AVAIL_W, AVAIL_H)
        total += h + f.getSpaceBefore() + f.getSpaceAfter()
    return total


def build_schedule_pdf(schedules, title, subtitle="", workspace_label="REGISTRAR WORKSPACE", source_url="", departments=None,
                       year_level=None, semester=None):
    styles = getSampleStyleSheet()
    now_str = datetime.now().strftime("%m/%d/%y, %I:%M %p")
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    eyebrow_style = ParagraphStyle("Eyebrow", parent=styles["Normal"], fontSize=9, textColor=GOLD, fontName="Helvetica-Bold")
    scope_style = ParagraphStyle("Scope", parent=styles["Normal"], fontSize=10.5, leading=14, textColor=colors.HexColor("#1f2937"), spaceBefore=2, spaceAfter=2)
    title_style = ParagraphStyle("TitleNavy", parent=styles["Title"], textColor=NAVY, fontSize=20, alignment=0, spaceAfter=2, leading=24)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"), spaceBefore=4)
    heading_style = ParagraphStyle("TableHeading", parent=styles["Normal"], fontSize=11.5, leading=15, textColor=NAVY,
                                   fontName="Helvetica-Bold", spaceBefore=2, spaceAfter=6)
    footer_text = f"{source_url}" if source_url else "U-FAST -- University - Faculty Academic Scheduling Tool"

    tables = _group_tables(schedules)
    single = len(tables) <= 1
    merged = {}
    for t in tables:
        g = _merge_by_day(t[4])
        g.sort(key=lambda x: (DAY_SORT_ORDER.get(x["day"], 99), x["start"], x["section"]))     # Mon->Sat, then by start time
        merged[(t[0], t[1])] = g
    fit_info = {"pages": [], "overflow": []}

    def school_header(scope_line):
        out = [Paragraph(f"{now_str} &nbsp;&nbsp;&nbsp; <font color='#003366'><b>U-FAST Academic Scheduling</b></font>", meta_style),
               Spacer(1, 6), Paragraph(workspace_label, eyebrow_style), Paragraph(title, title_style)]
        if scope_line:
            out.append(Paragraph(scope_line, scope_style))
        if subtitle:
            out.append(Paragraph(subtitle, sub_style))
        out.append(Spacer(1, 8))
        return out

    def closing():
        return [Spacer(1, 6), Paragraph(footer_text, meta_style), Spacer(1, 10), _signature_blocks(departments, styles, AVAIL_W)]

    def page(t, last, font, pad_v):
        prog, yl, sem, ay, _rows_ = t
        cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=font, leading=font * 1.2, textColor=colors.HexColor("#1f2937"))
        head = ParagraphStyle("CellHeader", parent=styles["Normal"], fontSize=font + 0.5, leading=(font + 0.5) * 1.2,
                              textColor=colors.white, fontName="Helvetica-Bold")
        note = ParagraphStyle("CellNote", parent=cell, fontSize=font - 1, leading=(font - 1) * 1.1, textColor=colors.HexColor("#475569"))
        widths = _col_widths([g for gs in merged.values() for g in gs], font)
        header, body = _rows(merged[(prog, yl)], font, head, cell, note)
        if single:
            top = school_header(scope_html(scope_parts([year_level] if year_level else [yl], [semester] if semester else [sem], [ay])))
        else:            # "BS Computer Science - 1st Year - 1st Semester, A.Y. 2026-2027"
            top = school_header("") + [Paragraph(" - ".join(x for x in (prog, yl or "Year level not set", sem) if x) + f", A.Y. {ay}",
                                                 heading_style)]
        pad_h = 6 if font < 9 else 8
        return top, header, body, widths, pad_h

    story = []
    for i, t in enumerate(tables):
        last = i == len(tables) - 1
        chosen = None
        for font, pad_v in FIT_STEPS:
            top, header, body, widths, pad_h = page(t, last, font, pad_v)
            flow = top + [_table([header] + body, widths, pad_v, pad_h)] + (closing() if last else [])
            if _height(flow) <= AVAIL_H:
                chosen = (font, pad_v, flow)
                break
        if i:
            story.append(PageBreak())                  # every year level starts on its own page
        if chosen:
            fit_info["pages"].append({"year_level": t[1], "program": t[0], "rows": len(merged[(t[0], t[1])]), "font": chosen[0]})
            story += chosen[2]
            continue
        # cannot fit on one page even at 8 pt: rows continue on the next page (never split, header repeated); on the last page the
        # signatory travels with the final rows so it is never alone
        font, pad_v = FIT_STEPS[-1]
        top, header, body, widths, pad_h = page(t, last, font, pad_v)
        n = len(body)
        fit_info["overflow"].append({"year_level": t[1], "program": t[0], "rows": n})
        log.warning("Schedule PDF: %s %s has %d rows and does not fit on one page at 8 pt", t[0], t[1], n)
        if not last:
            story += top + [_table([header] + body, widths, pad_v, pad_h)]
            continue
        k = min(TAIL_ROWS, n)
        story += top
        if n > k:
            story.append(_table([header] + body[:n - k], widths, pad_v, pad_h))
        story.append(KeepTogether([_table([header] + body[n - k:], widths, pad_v, pad_h)] + closing()))
    if not tables:
        story += school_header(scope_html(scope_parts([year_level], [semester], []))) + closing()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=PAGE, topMargin=MARGIN, bottomMargin=MARGIN, leftMargin=MARGIN, rightMargin=MARGIN)
    doc.build(story)
    fit_info["page_count"] = doc.page
    buf.seek(0)
    out = io.BytesIO(buf.getvalue())
    out.fit_info = fit_info
    return out
