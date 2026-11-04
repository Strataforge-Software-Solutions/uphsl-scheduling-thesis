"""
Printable exam schedule, laid out like the school's own printed sheet:

    <Prelim|Midterm|Final> Exam Schedule
    2nd Semester, AY 2025-2026
    TIME | ROOM | SUBJECT CODE | SUBJECT NAME/DESCRIPTION | FACULTY
    ---- February 16, 2026 (Monday) ----   (one banner row per exam date)
    ...
    Prepared by / Approved by, and the printed date and time.
"""
import io
from collections import OrderedDict
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engine.pdf_export import SCHOOL_DIRECTOR_NAME, SCHOOL_DIRECTOR_TITLE

NAVY = colors.HexColor("#003366")
GOLD = colors.HexColor("#b8860b")
SCHOOL_NAME = "PERPETUAL HELP COLLEGE OF MANILA"
SCHOOL_ADDRESS = "1240 V. Concepcion St., Sampaloc, Manila"
PERIOD_TITLE = {"prelim": "Prelim", "midterm": "Midterm", "final": "Final"}


def _t(t):
    """9:30 style (no leading zero, no AM/PM -- the printed sheet shows 1:00-2:00)."""
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d}"


def _semester_words(sem):
    s = (sem or "").strip()
    return s.replace(" Sem", " Semester") if s else ""


def build_exam_pdf(rows, exam_period=None, semester=None, prepared_by_user=None, prepared_title="", departments=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11)
    cell = ParagraphStyle("cell", parent=base, fontSize=8.5, leading=10.5)
    head = ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=8.5, alignment=1)
    day = ParagraphStyle("day", parent=base, fontName="Helvetica-Bold", fontSize=9, alignment=1)
    school = ParagraphStyle("school", parent=base, fontName="Helvetica-Bold", fontSize=15, alignment=1, textColor=NAVY, leading=18)
    addr = ParagraphStyle("addr", parent=base, fontSize=8, alignment=1, textColor=colors.HexColor("#475569"))
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=15, alignment=1, leading=18)
    sub = ParagraphStyle("sub", parent=base, fontSize=11, alignment=1, leading=14)
    sig = ParagraphStyle("sig", parent=base, fontName="Times-Roman", fontSize=10.5, leading=13)
    sigb = ParagraphStyle("sigb", parent=sig, fontName="Times-Bold")

    years = sorted({r.school_year for r in rows if r.school_year})
    ay = years[-1] if years else ""
    period_name = PERIOD_TITLE.get(exam_period) or ""
    sem_text = _semester_words(semester) or ", ".join(sorted({_semester_words(r.section.semester) for r in rows}))
    from engine.pdf_export import scope_parts, scope_html
    scope_line = scope_html(scope_parts([r.section.year_level for r in rows], [semester] if semester else [r.section.semester for r in rows],
                                        [ay] if ay else []))
    dept_line = " & ".join(departments) if departments else "General Education (all departments)"

    els = [Paragraph(SCHOOL_NAME, school), Paragraph(SCHOOL_ADDRESS, addr), Spacer(1, 4),
           Table([[""]], colWidths=[7.3 * inch], rowHeights=[3],
                 style=[("BACKGROUND", (0, 0), (-1, -1), GOLD)]),
           Spacer(1, 12),
           Paragraph(f"{period_name + ' ' if period_name else ''}Exam Schedule", title),
           Paragraph(dept_line, ParagraphStyle("dept", parent=sub, fontName="Helvetica-Bold", textColor=NAVY)),
           Paragraph(scope_line, sub), Spacer(1, 10)]

    by_date = OrderedDict()
    for r in sorted(rows, key=lambda r: (r.exam_date or datetime.max.date(), r.timeslot.start_time, r.room.name, r.subject.code)):
        by_date.setdefault(r.exam_date, []).append(r)

    data = [[Paragraph(h, head) for h in ["TIME", "ROOM", "SUBJECT CODE", "SUBJECT NAME/DESCRIPTION", "FACULTY"]]]
    style = [
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for d, items in by_date.items():
        label = d.strftime("%B %d, %Y (%A)") if d else "Date to be set"
        data.append([Paragraph(label, day), "", "", "", ""])
        i = len(data) - 1
        style += [("SPAN", (0, i), (-1, i)), ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f3f4f6"))]
        for r in items:
            u = r.proctor.user
            data.append([
                Paragraph(f"{_t(r.timeslot.start_time)}-{_t(r.timeslot.end_time)}", cell),
                Paragraph(r.room.name, cell), Paragraph(r.subject.code, cell),
                Paragraph(r.subject.title, cell), Paragraph(u.get_full_name().strip() or u.username, cell)])
    table = Table(data, repeatRows=1, colWidths=[0.85 * inch, 0.9 * inch, 1.15 * inch, 2.9 * inch, 1.5 * inch])
    table.setStyle(TableStyle(style))
    els.append(table)

    # --- signatures + print stamp ---
    name = ""
    if prepared_by_user is not None:
        name = prepared_by_user.get_full_name().strip() or prepared_by_user.username
    role_line = prepared_title
    if prepared_title == "Dean" and departments:
        role_line = "Dean, " + " & ".join(departments)
    stamp = datetime.now().strftime("%d-%b-%y &nbsp; %I:%M:%S %p")
    left = [Paragraph("Prepared by:", sig), Spacer(1, 24), Paragraph(name or "_______________________", sigb),
            Paragraph(role_line, sig)]
    right = [Paragraph("Approved by:", sig), Spacer(1, 24), Paragraph(SCHOOL_DIRECTOR_NAME, sigb),
             Paragraph(SCHOOL_DIRECTOR_TITLE, sig)]
    sigs = Table([[left, right]], colWidths=[3.65 * inch, 3.65 * inch])
    sigs.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    els += [Spacer(1, 16), KeepTogether([sigs, Spacer(1, 8),
                                         Paragraph(f"Printed: {stamp}", ParagraphStyle("st", parent=base, fontSize=8, alignment=2, textColor=colors.grey))])]
    doc.build(els)
    buf.seek(0)
    return buf
