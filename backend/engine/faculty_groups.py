"""The Professor list in three groups, computed on the SERVER for the Generate dialog, the Edit dialog and the "not placed" pop-up.

  Suggested  -- qualified for the subject (engine.teacher_scope.teacher_allowed: department + specialization / degree, the engine's own
                rule), free then, and within their weekly limit. Best first: same teacher as the Lec / Lab partner, a "preferred" time,
                then lower load. At most SUGGESTED_MAX here; the other free qualified faculty are listed under Qualified.
  Qualified  -- every other qualified teacher. Free ones are selectable. Those who cannot take the class are listed but NOT selectable,
                with the reason (busy then, marked unavailable, over the weekly limit). Outside their submitted window is allowed
                (availability is a preference), marked "Outside preferred time".
  Other available (not connected) -- for a Dean's MAJOR subject, only the Dean's own department:
                faculty NOT connected to the subject who are free INSIDE their submitted availability (or have submitted none), not
                marked unavailable, and within their weekly limit. Choosing one is a manual "Assign anyway" with a reason (never done by
                the engine). This group remains visible alongside qualified groups. Not-connected faculty who are over the limit are
                named in one muted "Full:" line.

Every person appears in one group only. Loads are the Workload page numbers (Schedule hours of that semester); in the Generate dialog the
hours that would remain after Generate replaces this program's drafts are added as "after Generate: X hrs" when they differ.
READ-ONLY: nothing here writes to the database.
"""
from datetime import datetime

SUGGESTED_MAX = 5
APPROVAL = {"dean": "Not connected to this subject. Dean approval required.",
            "principal": "Not connected to this subject. Principal approval required."}
EMPTY_TEXT = "No faculty in your department is free at this time."


def _mins(t):
    return t.hour * 60 + t.minute


def _fmt_h(h):
    return f"{round(float(h), 2):g}"


def _merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _minus(iv, cut):
    out = []
    for a, b in iv:
        pieces = [[a, b]]
        for c, d in cut:
            nxt = []
            for x, y in pieces:
                if d <= x or c >= y:
                    nxt.append([x, y])
                    continue
                if c > x:
                    nxt.append([x, c])
                if d < y:
                    nxt.append([d, y])
            pieces = nxt
        out += pieces
    return [p for p in out if p[1] > p[0]]


def _intersect(iv, other):
    return _merge([[max(a, c), min(b, d)] for a, b in iv for c, d in other if min(b, d) > max(a, c)])


def fits(free_by_day, blocks, sections=1):
    """Can every block (each section needs all of them) be laid in the free time without overlap? Longest first (as the dialog did)."""
    need = sorted([b for _ in range(max(1, sections)) for b in blocks], reverse=True)
    left = [[a, b] for iv in free_by_day.values() for a, b in iv]
    for length in need:
        slot = next((x for x in left if x[1] - x[0] >= length), None)
        if slot is None:
            return False
        slot[0] += length
    return True


def is_dean(user):
    return getattr(user, "role", "") == "faculty" and getattr(user, "faculty_type", "") == "dean"


def override_possible(user, subject, section):
    """Assign anyway is offered only to a Dean, for a MAJOR subject of their own department (no Gen Ed for now)."""
    dept = getattr(getattr(section, "program", None), "department", None)
    return is_dean(user) and subject.classification != "minor" and dept in (getattr(user, "departments", None) or [])


def _pool(user, subject, section):
    """Active faculty who may be listed at all: the subject's department(s) the user may use (never another department)."""
    from faculty.models import FacultyProfile
    from .teacher_scope import allowed_departments
    allowed = allowed_departments(user, subject, section)
    out = []
    for p in FacultyProfile.objects.filter(user__is_active=True).select_related("user").prefetch_related("specializations"):
        deps = set(p.user.departments or ([p.user.department] if p.user.department else []))
        if allowed is None or deps & set(allowed):
            out.append(p)
    return out


def build(user, subject, section, *, term, school_year=None, exact_slots=None, blocks=None, sections=1, window=None, day=None,
          exclude_ids=(), need_hours=0.0, partner_teacher_id=None, after_label=False):
    """The three groups for one class. exact_slots: the class's TimeSlots (Edit dialog). Otherwise blocks (minutes per meeting) are
    fitted into each person's free week, inside window (start, end minutes) and day ("Mon") when given."""
    from . import availability as av
    from .models import Schedule, TimeSlot
    from .professor_choice import limits_readonly, short_name
    from .teacher_scope import teacher_allowed
    from .workload import hours_by_teacher_term, limit_for

    pool = _pool(user, subject, section)
    qualified = [t for t in pool if not teacher_allowed(user, t, subject, section)]
    q_ids = {t.id for t in qualified}
    can_override = override_possible(user, subject, section)
    # the Dean never assigns themselves to a subject they are not connected to (they stay in Suggested / Qualified when connected)
    others = [t for t in pool if t.id not in q_ids and t.user_id != getattr(user, "id", None)] if can_override else []
    people = qualified + others
    ids = [t.id for t in people]
    lim = limits_readonly()
    hrs_all = hours_by_teacher_term(ids)
    hrs_proj = hours_by_teacher_term(ids, exclude_schedule_ids=list(exclude_ids)) if exclude_ids else hrs_all

    wins = {}
    for w in av.rows(ids, school_year, term):
        wins.setdefault(w.faculty_id, []).append(w)
    busy = {}                                                    # (teacher, day) -> [[a, b, code]]
    for tid, d, a, b, code in (Schedule.objects.filter(teacher_id__in=ids, term=term).exclude(pk__in=list(exclude_ids))
                               .values_list("teacher_id", "timeslot__day", "timeslot__start_time", "timeslot__end_time", "subject__code")):
        busy.setdefault((tid, d[:3].title()), []).append([_mins(a), _mins(b), code])

    grid = {}
    if exact_slots is None:
        from .college_break import overlaps as overlaps_college_break
        for d, a, b in TimeSlot.objects.values_list("day", "start_time", "end_time"):
            if overlaps_college_break(a, b):
                continue
            grid.setdefault(d[:3].title(), []).append([_mins(a), _mins(b)])
        grid = {d: _merge(v) for d, v in grid.items()}
        if day:
            grid = {d: v for d, v in grid.items() if d == day}
        if window:
            grid = {d: _intersect(v, [list(window)]) for d, v in grid.items()}
        blocks = [int(b) for b in (blocks or [60])]
    ivs = [(s.day[:3].title(), _mins(s.start_time), _mins(s.end_time)) for s in (exact_slots or [])]

    def per_day(ws, kind):
        out = {}
        for w in ws:
            if kind == "good" and w.preference == "unavailable":
                continue
            if kind == "bad" and w.preference != "unavailable":
                continue
            if kind == "preferred" and w.preference != "preferred":
                continue
            out.setdefault(w.day[:3].title(), []).append([_mins(w.start_time), _mins(w.end_time)])
        return {d: _merge(v) for d, v in out.items()}

    rows = []
    for t in people:
        ws = wins.get(t.id, [])
        good, bad, pref = per_day(ws, "good"), per_day(ws, "bad"), per_day(ws, "preferred")
        submitted_good = bool(good)
        cur = round(hrs_all.get(t.id, {}).get(term, 0.0), 2)
        proj = round(hrs_proj.get(t.id, {}).get(term, 0.0), 2)
        mx = limit_for(t, lim)
        after = proj + float(need_hours or 0)
        full = mx > 0 and after > mx + 1e-9
        if exact_slots is not None:
            hit_bad = any(min(e, d_) - max(s, c) > 0 for dd, s, e in ivs for c, d_ in bad.get(dd, []))
            codes = sorted({code for dd, s, e in ivs for a, b, code in busy.get((t.id, dd), []) if min(e, b) - max(s, a) > 0})
            inside = all(any(c <= s and e <= d_ for c, d_ in good.get(dd, [])) for dd, s, e in ivs) if submitted_good else True
            preferred = bool(pref) and all(any(c <= s and e <= d_ for c, d_ in pref.get(dd, [])) for dd, s, e in ivs)
            free_any = not hit_bad and not codes
            free_strict = free_any and inside
            busy_text = f"Busy at this time ({', '.join(codes)})" if codes else ""
        else:
            lenient, strict = {}, {}
            for dd, iv in grid.items():
                base = _minus(iv, bad.get(dd, []))
                base = _minus(base, _merge([[a, b] for a, b, _c in busy.get((t.id, dd), [])]))
                if base:
                    lenient[dd] = base
                s_iv = _intersect(base, good.get(dd, [])) if submitted_good else base
                if s_iv:
                    strict[dd] = s_iv
            free_any = fits(lenient, blocks, sections)
            free_strict = fits(strict, blocks, sections)
            inside = free_strict
            pref_iv = {dd: _intersect(v, pref.get(dd, [])) for dd, v in lenient.items()}
            preferred = bool(pref) and fits({d: v for d, v in pref_iv.items() if v}, blocks, sections)
            hit_bad = False
            busy_text = "No free time long enough " + ("in the chosen time" if (window or day) else "this week")
        load = f"{_fmt_h(cur)}/{_fmt_h(mx)} hrs"
        rows.append({
            "t": t, "qualified": t.id in q_ids, "free_any": free_any, "free_strict": free_strict, "inside": inside,
            "preferred": preferred, "full": full, "hit_bad": hit_bad, "busy_text": busy_text,
            "current_hours": cur, "projected_hours": proj, "max_hours": mx, "after_hours": round(after, 2),
            "out": {"id": t.id, "label": short_name(t), "full_name": t.user.get_full_name().strip() or t.user.username,
                    "school_id": t.user.school_id, "username": t.user.username, "faculty_type": t.user.faculty_type,
                    "current_hours": cur, "max_hours": mx, "load_text": load,
                    "after_generate_hours": proj if (after_label and abs(proj - cur) > 1e-9) else None,
                    "specializations": ", ".join(sorted(f.name for f in t.specializations.all())) or (t.degree or "none recorded")},
        })

    def full_text(r):
        return (f"Full: {_fmt_h(r['current_hours'])}/{_fmt_h(r['max_hours'])} hrs" if r["projected_hours"] >= r["max_hours"] - 1e-9
                else f"Over the limit with this class: {_fmt_h(r['after_hours'])}/{_fmt_h(r['max_hours'])} hrs")

    free_q = [r for r in rows if r["qualified"] and r["free_any"] and not r["full"]]
    free_q.sort(key=lambda r: (r["t"].id != partner_teacher_id, not r["inside"], not r["preferred"], r["projected_hours"],
                               r["out"]["label"].lower()))
    suggested, qualified_rows = free_q[:SUGGESTED_MAX], free_q[SUGGESTED_MAX:]
    low = min((r["projected_hours"] for r in suggested), default=None)
    partner_word = "lecture" if (subject.code.endswith("L") or (subject.lab_units and not subject.lec_units)) else "lab"

    def tag_free(r, in_suggested):
        if r["t"].id == partner_teacher_id:
            return f"Same teacher as {partner_word}"
        if not r["inside"]:
            return "Outside preferred time"
        if r["preferred"]:
            return "Preferred time"
        if in_suggested and low is not None and abs(r["projected_hours"] - low) < 1e-9:
            return "Lowest load"
        return "Free at this time"

    out_s = [{**r["out"], "group": "suggested", "selectable": True, "tag": tag_free(r, True), "not_connected": False} for r in suggested]
    out_q = [{**r["out"], "group": "qualified", "selectable": True, "tag": tag_free(r, False), "not_connected": False} for r in qualified_rows]
    for r in sorted((r for r in rows if r["qualified"] and r not in free_q), key=lambda r: r["out"]["label"].lower()):
        why = full_text(r) if r["full"] and r["free_any"] else ("Marked unavailable" if r["hit_bad"] else r["busy_text"] or full_text(r))
        out_q.append({**r["out"], "group": "qualified", "selectable": False, "tag": why, "not_connected": False})
    out_o, full_line = [], []
    # Keep the manual, explicitly approved fallback visible alongside qualified
    # candidates. Qualification is advisory for this manual choice; department,
    # availability and workload checks still apply when the Dean confirms it.
    show_other = can_override
    if show_other:
        for r in sorted((r for r in rows if not r["qualified"]), key=lambda r: (r["projected_hours"], r["out"]["label"].lower())):
            if r["full"]:
                full_line.append({"id": r["t"].id, "label": r["out"]["label"], "current_hours": r["current_hours"], "max_hours": r["max_hours"]})
            elif r["free_strict"]:
                out_o.append({**r["out"], "group": "other", "selectable": True, "not_connected": True,
                              "tag": "Not connected" + (" · Preferred time" if r["preferred"] else "")})
    any_pick = any(o["selectable"] for o in out_s + out_q + out_o)
    return {
        "subject_id": subject.id, "code": subject.code, "title": subject.title,
        "suggested": out_s, "qualified": out_q, "other": out_o, "other_shown": show_other,
        "full_line": full_line, "full_text": ("Full: " + ", ".join(f"{f['label']} {_fmt_h(f['current_hours'])}/{_fmt_h(f['max_hours'])} hrs"
                                                                   for f in full_line)) if full_line else "",
        "approval_text": APPROVAL["dean"], "override_possible": can_override,
        "empty_text": "" if any_pick else EMPTY_TEXT,
    }


# ------------------------------------------------------------------ override checks (shared by Generate, Edit and the pop-up)
class OverrideError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def override_meta(user, reason):
    return {"reason": reason, "by_id": user.id, "by_name": user.get_full_name().strip() or user.username, "role": "Dean",
            "at": datetime.now().astimezone().isoformat(timespec="seconds")}


def badge_text(meta):
    return f"Assigned by {(meta or {}).get('role') or 'Dean'} (not connected)" if meta else ""


def check_override(user, subject, section, teacher, reason, groups):
    """'' when this manual Assign anyway is allowed, else raises OverrideError with a clear message. `groups` = build(...) for the SAME
    class and time, computed now (never trusted from the browser)."""
    reason = (reason or "").strip()
    name = teacher.user.get_full_name().strip() or teacher.user.username
    if not is_dean(user):
        raise OverrideError("Only a Dean can assign a faculty member who is not connected to the subject.", 403)
    if subject.classification == "minor":
        raise OverrideError(f"{subject.code} is a Gen Ed subject. Assign anyway is only for the program (major) subjects of your college.", 403)
    dept = section.program.department
    if dept not in (user.departments or []):
        raise OverrideError(f"{subject.code} belongs to {dept}, which is not your department.", 403)
    if not set(teacher.user.departments or []) & {dept}:
        raise OverrideError(f"{name} is not a faculty member of {dept}. Only your own department's faculty can be assigned.", 403)
    if not teacher.user.is_active:
        raise OverrideError(f"{name} is not an active account.", 400)
    if len(reason) < 3:
        raise OverrideError("Write a short reason for assigning a faculty member who is not connected to this subject.", 400)
    if not any(o["id"] == teacher.id for o in groups["other"]):
        full = next((f for f in groups["full_line"] if f["id"] == teacher.id), None)
        if full:
            raise OverrideError(f"{name} is at the weekly limit ({_fmt_h(full['current_hours'])}/{_fmt_h(full['max_hours'])} hrs).", 409)
        raise OverrideError(f"{name} is not free then inside their submitted availability, or already teaches at that time.", 409)
    return reason


def strict_blocked_slots(teacher_id, timeslots, school_year=None, semester=None):
    """TimeSlot ids an Assign-anyway person may NOT be given: outside every window they submitted (when they submitted one) or
    overlapping a time they marked unavailable. Someone with no submission is blocked only by nothing."""
    from . import availability as av
    ws = list(av.rows([teacher_id], school_year, semester))
    good = [w for w in ws if w.preference != "unavailable"]
    bad = [w for w in ws if w.preference == "unavailable"]
    out = set()
    for sl in timeslots:
        d = sl.day[:3].lower()
        if any(w.day[:3].lower() == d and w.start_time < sl.end_time and w.end_time > sl.start_time for w in bad):
            out.add(sl.id)
        elif good and not any(w.day[:3].lower() == d and w.start_time <= sl.start_time and sl.end_time <= w.end_time for w in good):
            out.add(sl.id)
    return out


def log_overrides(user, rows, where, action="CREATE"):
    """One audit entry (engine.models.Log, shown in the audit trail) per class assigned anyway: who, subject, faculty, reason, time."""
    from .models import Log
    seen = set()
    for r in rows:
        key = (r.section_id, r.subject_id)
        if key in seen or not r.qualification_override:
            continue
        seen.add(key)
        m = r.qualification_override
        teacher = r.teacher.user.get_full_name().strip() or r.teacher.user.username
        Log.objects.create(action=action, schedule_id=r.id, user=user,
                           details=(f"ASSIGN ANYWAY (not connected): {teacher} for {r.subject.code} ({r.section.program.name} {r.section.name}) "
                                    f"by {m.get('role', 'Dean')} {m.get('by_name', '')} via {where}. Reason: {m.get('reason', '')}"))
