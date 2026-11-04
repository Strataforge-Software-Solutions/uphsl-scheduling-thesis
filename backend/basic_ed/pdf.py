"""Printable timetable: one page per section (periods down, days across) plus a summary page."""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from .engine import build_rows, to_time, to_min
from .models import DAYS, GradeWindow, SchoolLevelConfig
from .services import run_report

LEVEL_NAME = {"SHS": "Senior High School", "JHS": "Junior High School"}


def build_run_pdf(run, user):
    cfg = SchoolLevelConfig.objects.get(level=run.level)
    w = GradeWindow.objects.get(level=run.level, grade_level=run.grade_level)
    rows = build_rows(cfg, w)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=7.5, leading=9, alignment=1)
    head = ParagraphStyle("h", parent=ss["Title"], fontSize=14, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=9, alignment=1, textColor=colors.HexColor("#475569"))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    from .structure import label as _plabel
    period_word = _plabel(run.level, run.grade_level)          # Term (JHS, Grade 11) / Semester (Grade 12)
    story = []
    sections = sorted({e.section for e in run.entries.select_related("section__strand")}, key=lambda s: s.name)
    entries = list(run.entries.select_related("section", "teacher__user", "room"))
    for sec in sections:
        story += [Paragraph("PERPETUAL HELP COLLEGE OF MANILA", head),
                  Paragraph(f"<b>{LEVEL_NAME[run.level]}</b>", sub),
                  Paragraph(f"Year Level: <b>Grade {run.grade_level}</b> &nbsp;|&nbsp; {period_word}: <b>{run.grading_period}</b> &nbsp;|&nbsp; "
                            f"Academic Year: <b>{run.academic_year.label}</b>", sub),
                  Paragraph(f"{(sec.strand.code + ' - ') if sec.strand_id else ''}Section {sec.name} - {cfg.building} - "
                            f"{w.start_time:%I:%M %p}-{w.end_time:%I:%M %p} - Version {run.version} ({run.get_status_display()})", sub), Spacer(1, 8)]
        data = [["Time"] + [n for _, n in DAYS]]
        by = {(e.day, to_min(e.start_time)): e for e in entries if e.section_id == sec.id}
        break_rows = []
        for kind, s0, e0 in rows:
            row = [f"{to_time(s0):%I:%M}-{to_time(e0):%I:%M}"]
            if kind != "period":
                break_rows.append(len(data))
                data.append([f"{to_time(s0):%I:%M}-{to_time(e0):%I:%M}", kind.upper()] + [""] * 4)
                continue
            for d, _n in DAYS:
                e = by.get((d, s0))
                row.append(Paragraph(f"<b>{e.subject_code}</b><br/>{e.subject_name[:38]}<br/>{e.teacher.full_name if e.teacher_id else '-'}<br/>{e.room.name if e.room_id else '-'}", small) if e else "")
            data.append(row)
        t = Table(data, colWidths=[62] + [150] * 5, repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")])]
                              + [x for r in break_rows for x in (("SPAN", (1, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#fde68a")),
                                                                  ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"))]))
        story += [t, Spacer(1, 10),
                  Paragraph(f"Prepared by: {user.get_full_name() or user.username} &nbsp;&nbsp;&nbsp; Approved by: ______________________ (Principal) "
                            f"&nbsp;&nbsp;&nbsp; Printed: {datetime.now():%B %d, %Y %I:%M %p}", ss["Normal"]), PageBreak()]
    rep = run_report(run)
    story += [Paragraph("Summary", head), Spacer(1, 6)]
    tdata = [["Teacher", "Hours / week", "Limit", "Load %"]] + [[t["name"], t["hours"], t["max_hours"], f"{t['load_pct']}%"] for t in rep["teachers"]]
    t = Table(tdata, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
    story.append(t)
    doc.build(story)
    return buf.getvalue()
