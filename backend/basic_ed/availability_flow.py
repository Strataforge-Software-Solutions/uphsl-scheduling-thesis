"""SHS / JHS teacher availability: the teacher SUBMITS it, the Principal VIEWS it (and may return it for correction or send reminders).

The grid  -- every class period of the grades the teacher could teach (the grades of their level where they are qualified for, or pinned
             to, a subject; all grades of the level when none), Monday to Friday. A time that is a break for EVERY one of those grades is a
             break row (cannot be marked). A time that is a break for some grades only stays selectable, with a note ("Break for Grade 11");
             the generator places a class only in its own grade's periods, so such a mark can never put a class in a break.
Submit    -- the teacher sends every cell (Preferred / Available / Unavailable); neighbouring cells with the same choice become one window.
             It replaces the previous submission and is used from the NEXT Generate on (approved or published timetables never move).
Status    -- Not submitted (free at any time) / Submitted on [date] / Returned for correction (last submission still in use), and
             "Updated since last generation" when the submission is newer than the level's latest timetable.
"""
from collections import defaultdict
from datetime import time as dtime

from django.db import transaction
from django.utils import timezone

from . import models as m
from .engine import build_grid, eligible, to_min, window_breaks

PREF_WORD = {"preferred": "Preferred", "available": "Available", "unavailable": "Unavailable"}
DAY_KEYS = [d for d, _ in m.DAYS]


class FlowError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def _hm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _active_year():
    return m.AcademicYear.objects.filter(is_active=True).first() or m.AcademicYear.objects.order_by("-label").first()


def relevant_grades(fac):
    windows = {w.grade_level: w for w in m.GradeWindow.objects.filter(level=fac.level)}
    ay = _active_year()
    pinned = set(m.TeachingAssignment.objects.filter(faculty=fac).values_list("subject__grade_level", flat=True))
    found = set(pinned)
    if ay is not None:
        for sub in m.CurriculumSubject.objects.filter(level=fac.level, academic_year=ay, is_active=True).exclude(category="guidance"):
            if sub.grade_level not in found and eligible(fac, sub):
                found.add(sub.grade_level)
    grades = sorted(g for g in found if g in windows) or sorted(windows)
    return grades, windows


def grid_for(fac):
    """{"grades": [...], "rows": [{"start", "end", "kind": "period" | "break", "label", "note", "outside_preferred"}]} for the teacher."""
    cfg = m.SchoolLevelConfig.objects.get(level=fac.level)
    grades, windows = relevant_grades(fac)
    periods, breaks = {}, {}
    for g in grades:
        periods[g] = build_grid(cfg, windows[g])
        breaks[g] = window_breaks(windows[g])
    pstart = to_min(fac.preferred_start) if fac.preferred_start and fac.preferred_end else None
    pend = to_min(fac.preferred_end) if pstart is not None else None
    rows = {}
    for g in grades:
        for s, e in periods[g]:
            rows[(s, e)] = {"start": _hm(s), "end": _hm(e), "kind": "period", "label": "", "grades": []}
    for (s, e), row in rows.items():
        row["grades"] = [g for g in grades if (s, e) in periods[g]]
        notes = [f"Break for Grade {g}" for g in grades if any(s < be and e > bs for _l, bs, be in breaks[g])]
        row["note"] = "; ".join(notes)
        row["outside_preferred"] = pstart is not None and (s < pstart or e > pend)
    for g in grades:                              # a break that is not a class time for ANY of the teacher's grades: a break row
        for label, bs, be in breaks[g]:
            if any(bs < e and be > s for (s, e) in rows if rows[(s, e)]["kind"] == "period"):
                continue
            if (bs, be) not in rows:
                rows[(bs, be)] = {"start": _hm(bs), "end": _hm(be), "kind": "break", "label": label, "note": "", "grades": [],
                                  "outside_preferred": False}
    out = [rows[k] for k in sorted(rows)]
    return {"grades": grades, "days": [{"key": d, "label": lbl} for d, lbl in m.DAYS], "rows": out,
            "preferred_start": fac.preferred_start.strftime("%H:%M") if fac.preferred_start else "",
            "preferred_end": fac.preferred_end.strftime("%H:%M") if fac.preferred_end else ""}


def cells_for(fac, grid):
    """The teacher's current submission shown as one value per (day, period row)."""
    rows = list(fac.availability.all())
    good = [a for a in rows if a.preference != "unavailable"]
    out = {}
    for d in DAY_KEYS:
        for r in grid["rows"]:
            if r["kind"] != "period":
                continue
            s, e = to_min(_t(r["start"])), to_min(_t(r["end"]))
            mine = [a for a in rows if a.day == d]
            if any(a.preference == "unavailable" and s < to_min(a.end_time) and e > to_min(a.start_time) for a in mine):
                v = "unavailable"
            elif any(a.preference == "preferred" and s >= to_min(a.start_time) and e <= to_min(a.end_time) for a in mine):
                v = "preferred"
            elif not good or any(s >= to_min(a.start_time) and e <= to_min(a.end_time) for a in mine if a.preference != "unavailable"):
                v = "available"
            else:
                v = "unavailable"                # outside the windows this teacher submitted: not usable (today's rule)
            out[f"{d}|{r['start']}"] = v
    return out


def _t(hhmm):
    h, mm = str(hhmm)[:5].split(":")
    return dtime(int(h), int(mm))


def status_info(fac, last_generated=None):
    st = fac.availability_status
    return {"status": st, "submitted_at": fac.availability_submitted_at.isoformat() if fac.availability_submitted_at else None,
            "note": fac.availability_note if st == "returned" else "",
            "updated_since_generation": bool(st != "not_submitted" and fac.availability_submitted_at and last_generated
                                            and fac.availability_submitted_at > last_generated)}


def last_generated(level):
    run = m.ScheduleRun.objects.filter(level=level).exclude(status="superseded").order_by("-created_at").first()
    return run.created_at if run else None


def windows_from_cells(fac, cells):
    """Validated cells -> merged windows [(day, start_min, end_min, preference)]."""
    grid = grid_for(fac)
    periods = {r["start"]: r for r in grid["rows"] if r["kind"] == "period"}
    breaks = {r["start"] for r in grid["rows"] if r["kind"] == "break"}
    by_day = defaultdict(list)
    if not isinstance(cells, list) or not cells:
        raise FlowError("Mark your availability in the grid before submitting.")
    for c in cells:
        if not isinstance(c, dict):
            raise FlowError("The availability grid could not be read. Reload the page and try again.")
        day, start, pref = c.get("day"), str(c.get("start") or "")[:5], c.get("preference")
        if day not in DAY_KEYS:
            raise FlowError("Unknown day in the availability grid.")
        if pref not in PREF_WORD:
            raise FlowError("Each time must be Preferred, Available or Unavailable.")
        if start in breaks and start not in periods:
            raise FlowError("A break cannot be marked as a class time.")
        row = periods.get(start)
        if row is None:
            raise FlowError(f"{start} is not a class period of your grades' daily schedule.")
        by_day[day].append((to_min(_t(row["start"])), to_min(_t(row["end"])), pref))
    out = []
    for day, items in by_day.items():
        items.sort()
        cur = None
        for s, e, p in items:
            if cur and p == cur[2] and s <= cur[1]:
                cur = (cur[0], max(cur[1], e), p)
            else:
                if cur:
                    out.append((day, *cur))
                cur = (s, e, p)
        if cur:
            out.append((day, *cur))
    return out


def _audit(user, fac, summary, new):
    from audit import recorder
    recorder.record("update", "SHS/JHS availability", fac.id, summary=f"{fac.full_name}: {summary}", user=user,
                    new={"level": fac.level, **new})


@transaction.atomic
def submit(user, fac, cells):
    wins = windows_from_cells(fac, cells)
    from audit import recorder
    with recorder.suppressed():                    # one audit entry for the submission, not one per window
        fac.availability.all().delete()
        m.Availability.objects.bulk_create([
            m.Availability(faculty=fac, day=d, start_time=dtime(s // 60, s % 60), end_time=dtime(e // 60, e % 60), preference=p,
                           available=p != "unavailable") for d, s, e, p in wins])
    now = timezone.now()
    m.Faculty.objects.filter(pk=fac.pk).update(availability_status="submitted", availability_submitted_at=now, availability_note="")
    fac.refresh_from_db()
    counts = defaultdict(int)
    for _d, s, e, p in wins:
        counts[p] += 1
    _audit(user, fac, "availability submitted", {"windows": len(wins), **{PREF_WORD[k]: v for k, v in counts.items()}})
    return fac


def _notify(fac, text):
    from notifications.models import Notification
    Notification.objects.create(recipient=fac.user, notif_type="schedule_update", message=text[:255])


@transaction.atomic
def return_for_correction(user, fac, note):
    note = (note or "").strip()
    if len(note) < 3:
        raise FlowError("Write a short note for the teacher (what to correct).")
    if fac.availability_status == "not_submitted":
        raise FlowError(f"{fac.full_name} has not submitted availability yet. Send a reminder instead.")
    m.Faculty.objects.filter(pk=fac.pk).update(availability_status="returned", availability_note=note[:300])
    fac.refresh_from_db()
    _notify(fac, f"Your availability was returned for correction: {note[:180]} Your last submission stays in use until you submit again.")
    _audit(user, fac, "returned for correction", {"note": note[:300]})
    return fac


def remind(user, level):
    todo = list(m.Faculty.objects.filter(level=level, is_active=True, user__is_active=True,
                                         availability_status__in=["not_submitted", "returned"]).select_related("user"))
    for f in todo:
        _notify(f, "Please submit your availability (My Profile > Availability) so the Principal can generate the timetable."
                if f.availability_status == "not_submitted" else
                f"Please correct and re-submit your availability: {f.availability_note[:150]}")
    if todo:
        from audit import recorder
        recorder.record("update", "SHS/JHS availability", "reminder", user=user,
                        summary=f"Reminder sent to {len(todo)} teacher(s) of {level}",
                        new={"level": level, "reminded": [f.full_name for f in todo]})
    return todo
