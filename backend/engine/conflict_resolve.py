"""
Conflict resolver: fixes a double-booking found by engine.conflict_report.scan by changing ONE of the two classes.

For the class that gets changed (a sample/demo class first, otherwise the one that was edited least) it tries, in order,
  teacher conflict -> another qualified teacher who is free at that time, then another day / time
  room conflict    -> another allowed room that fits the section and is free, then another day / time
  student conflict -> another day / time where the teacher, the room and the students are all free
and applies the first change that creates NO new conflict (checked with the same fast in-memory rules as the
"Change day / time" tool). Nothing is applied when no clean fix exists, and every change is written to the log.
"""
from django.db import IntegrityError, transaction

from . import tools as T
from .conflict_report import DEMO_TAG, scan
from .models import Log, Schedule, TimeSlot

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _plan(rows, day, start, room=None, teacher=None):
    return {"rows": rows, "start": start, "end_shift": 0, "room": room, "teacher": teacher, "day": day}


def _ok(plan):
    return not _evaluate_one(plan)[0]


def _evaluate_one(plan):
    pl, msgs, opts = T._evaluate([plan])[0]
    return msgs, opts


def _apply(plan, user, note):
    rows, off = plan["rows"], plan["start"] - min(T._min(r.timeslot.start_time) for r in plan["rows"])
    with transaction.atomic():
        for r in sorted(rows, key=lambda x: T._min(x.timeslot.start_time), reverse=off > 0):
            s_, e_ = T._min(r.timeslot.start_time) + off, T._min(r.timeslot.end_time) + off
            slot = TimeSlot.objects.get_or_create(day=plan["day"], start_time=T._t(s_), end_time=T._t(e_))[0]
            r.timeslot = slot
            if plan["room"] is not None:
                r.room = plan["room"]
            if plan["teacher"] is not None:
                r.teacher = plan["teacher"]
            r.is_manual_override = True
            r.save(update_fields=["timeslot", "room", "teacher", "is_manual_override"])
        r0 = rows[0]
        Log.objects.create(action="UPDATE", schedule_id=r0.id, user=user, details=f"Conflict resolved: {note}")


def _load(ids):
    return list(Schedule.objects.filter(pk__in=ids).select_related(
        "timeslot", "subject", "subject__program", "subject__field", "section__program", "teacher__user", "room"))


def _name(t):
    return t.user.get_full_name().strip() or t.user.username


def _choose_victim(a_rows, b_rows, user):
    """Which of the two clashing classes to change: a sample class, else the one nobody edited by hand, else the second."""
    def rank(rows):
        r = rows[0]
        return (0 if r.school_year == DEMO_TAG else 1, 1 if any(x.is_manual_override for x in rows) else 0)
    order = sorted([b_rows, a_rows], key=rank)
    for rows in order:
        if all(T._can_edit(user, r) for r in rows):
            return rows
    return None


def _time_fix(rows):
    """(plan, 'Mon 9:00 AM - 10:30 AM') for the nearest day/time where nothing clashes, or None."""
    r0 = rows[0]
    day0, start0 = r0.timeslot.day, min(T._min(r.timeslot.start_time) for r in rows)
    span = max(T._min(r.timeslot.end_time) for r in rows) - start0
    order = [day0] + [d for d in DAYS if d != day0]
    for day in order:
        pl = _plan(rows, day, start0)
        msgs, opts = _evaluate_one(pl)
        if not msgs:
            if day != day0:
                return pl, day
            continue
        for o in opts:
            h, m = o["start_time"].split(":")
            cand = _plan(rows, day, int(h) * 60 + int(m))
            if _ok(cand):
                return cand, day
    return None


def _teacher_fix(rows):
    from . import workload as wl
    r0 = rows[0]
    from .scheduler import _is_lab_of
    if any(_is_lab_of(r0.subject, p.subject) or _is_lab_of(p.subject, r0.subject)
           for p in Schedule.objects.filter(section_id=r0.section_id, term=r0.term).select_related("subject")):
        return None       # its Lec / Lab partner keeps this teacher (one teacher for both parts): only the time may change
    sugg = wl.suggest_replacements(r0.subject, r0.term, [r.timeslot for r in rows], exclude_teacher_ids=[r0.teacher_id],
                                   school_year=r0.school_year, limit=8, exclude_schedule_ids=[r.id for r in rows], section=r0.section)
    from faculty.models import FacultyProfile
    start = min(T._min(r.timeslot.start_time) for r in rows)
    for s in sugg:
        t = FacultyProfile.objects.select_related("user").filter(pk=s["faculty_id"]).first()
        if t is None:
            continue
        pl = _plan(rows, r0.timeslot.day, start, teacher=t)
        if _ok(pl):
            return pl, t
    return None


def _room_fix(rows):
    from rooms.models import Room
    from rooms import rules
    r0 = rows[0]
    dept = r0.section.program.department
    lab = (r0.subject.lab_units or 0) > 0
    major = r0.subject.classification != "minor"
    pool = Room.objects.filter(room_type__in=["lecture", "lab"]).exclude(pk=r0.room_id)
    cands = [x for x in rules.allowed_rooms(pool, dept, lab_subject=lab, major=major)
             if rules.fits_size(x, r0.section) and not rules.room_kind_message(r0.subject, x)
             and not rules.fixed_room_message(r0.subject, x)
             and (lab == (x.room_type == "lab") or not lab)]
    cands.sort(key=lambda x: (x.capacity or 0))                       # smallest room that fits
    start = min(T._min(r.timeslot.start_time) for r in rows)
    for room in cands:
        pl = _plan(rows, r0.timeslot.day, start, room=room)
        if _ok(pl):
            return pl, room
    return None


def _owner(row):
    """Who may change this class: the Registrar (Gen Ed) or the Dean of its college (program subjects)."""
    if row.subject.classification == "minor":
        return "the Registrar"
    return f"the Dean of {row.section.program.department}"


def _notify_owners(user, a_rows, b_rows, label):
    """Tell the owners of the two classes (not the person who pressed Resolve) that a clash needs their action."""
    from accounts.models import User
    from notifications.models import Notification
    sent = 0
    for rows in (a_rows, b_rows):
        r = rows[0]
        if r.subject.classification == "minor":
            owners = User.objects.filter(role="registrar")
        else:
            owners = [d for d in User.objects.filter(role="faculty", faculty_type="dean") if r.section.program.department in d.departments]
        for o in owners:
            if o.pk == user.pk:
                continue
            msg = (f"Conflict needs your action: {label}. Open the Conflict Checker and press Resolve "
                   f"(requested by {user.get_full_name().strip() or user.username}).")[:255]
            if not Notification.objects.filter(recipient=o, notif_type="conflict_alert", message=msg, is_read=False).exists():
                Notification.objects.create(recipient=o, notif_type="conflict_alert", message=msg)
                sent += 1
    return sent


def _still_conflicts(kind, a_ids, b_ids):
    ids = set(a_ids) | set(b_ids)
    rep = scan(involving_ids=ids, limit=200)
    key = (kind, frozenset(a_ids), frozenset(b_ids))
    return any((c["kind"], frozenset(c["a"]["ids"]), frozenset(c["b"]["ids"])) in (key, (kind, key[2], key[1])) for c in rep["conflicts"])


def resolve_pair(kind, a_ids, b_ids, user):
    """Fix one conflict. Returns {"ok", "summary"}."""
    a_rows, b_rows = _load(a_ids), _load(b_ids)
    if not a_rows or not b_rows:
        return {"ok": False, "summary": "One of the classes no longer exists. Run the check again."}
    if not _still_conflicts(kind, a_ids, b_ids):
        return {"ok": True, "summary": "This conflict is already gone (an earlier fix removed it). Nothing was changed."}
    rows = _choose_victim(a_rows, b_rows, user)
    if rows is None:
        la = f"{a_rows[0].subject.code} ({a_rows[0].section.program.name} {a_rows[0].section.name}) belongs to {_owner(a_rows[0])}"
        lb = f"{b_rows[0].subject.code} ({b_rows[0].section.program.name} {b_rows[0].section.name}) belongs to {_owner(b_rows[0])}"
        why = ""
        if any(r.status != "draft" for r in a_rows + b_rows):
            why = " A class that is approved or published is never moved."
        elif any(getattr(r, "merge_key", "") for r in a_rows + b_rows):
            why = " A shared (merged) class is never moved."
        sent = _notify_owners(user, a_rows, b_rows, f"{a_rows[0].subject.code} and {b_rows[0].subject.code}")
        note = f" {sent} owner(s) were notified." if sent else ""
        return {"ok": False, "summary": f"You may not change either class: {la}; {lb}.{why}{note}"}
    r0 = rows[0]
    label = f"{r0.subject.code} ({r0.section.program.name} {r0.section.name})"
    steps = {"teacher": ["teacher", "time"], "room": ["room", "time"]}.get(kind, ["time"])
    try:
        for step in steps:
            if step == "teacher":
                fx = _teacher_fix(rows)
                if fx:
                    pl, t = fx
                    note = f"{label}: teacher changed from {_name(r0.teacher)} to {_name(t)}"
                    _apply(pl, user, note)
                    return {"ok": True, "summary": note[0].upper() + note[1:] + "."}
            elif step == "room":
                fx = _room_fix(rows)
                if fx:
                    pl, room = fx
                    note = f"{label}: room changed from {r0.room.name} to {room.name}"
                    _apply(pl, user, note)
                    return {"ok": True, "summary": note[0].upper() + note[1:] + "."}
            else:
                fx = _time_fix(rows)
                if fx:
                    pl, day = fx
                    s = pl["start"]
                    note = f"{label}: moved to {day} {T._label(s)}"
                    _apply(pl, user, note)
                    return {"ok": True, "summary": note[0].upper() + note[1:] + "."}
    except IntegrityError:
        return {"ok": False, "summary": f"{label}: the free time was just taken by another change. Try again."}
    return {"ok": False, "summary": f"{label}: no teacher, room or time was found that is free of every conflict."}


def resolve_all(user, semester=None, departments=None, limit=200):
    """Fix conflicts one by one, rescanning after each so a fix never leaves a stale one behind."""
    done, failed, skip = [], [], set()
    for _ in range(limit):
        rep = scan(semester=semester, departments=departments, limit=300)
        nxt = next((c for c in rep["conflicts"] if (c["kind"], tuple(c["a"]["ids"]), tuple(c["b"]["ids"])) not in skip), None)
        if nxt is None:
            break
        res = resolve_pair(nxt["kind"], nxt["a"]["ids"], nxt["b"]["ids"], user)
        (done if res["ok"] else failed).append(res["summary"])
        if not res["ok"]:
            skip.add((nxt["kind"], tuple(nxt["a"]["ids"]), tuple(nxt["b"]["ids"])))
    return {"resolved": done, "unresolved": failed, "remaining": scan(semester=semester, departments=departments, limit=1)["total"]}
