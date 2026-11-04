"""Select / Approve / Remove / Undo / History for the Schedules tab (Registrar and Dean).

The rules live here, on the server, so the buttons cannot be bypassed:
  * ownership: the Registrar acts on Gen Ed (minor) classes, a Dean on major classes of their own college(s) only
    (permissions.can_edit_schedule_kind, the same rule the rest of the app uses);
  * the status chain stays Draft -> Approved -> Published. Approving / publishing first runs the conflict check (conflict_report.scan,
    the same one the Conflicts tab uses) on the selected classes against the WHOLE schedule: a class in any conflict is "blocked" and
    stays where it is, with the reason; the others move on. Nothing is hidden or skipped.
  * back to Draft: only Approved classes (a Published class was already announced to its teachers), and only when nothing depends on
    them (no faculty-absence coverage was made for them);
  * remove: Draft classes only. A shared class (merge_key) affects other sections, so it needs an explicit confirmation;
  * undo: a removal can be undone for UNDO_MINUTES by the same person, restoring the exact rows (same ids and fields) -- refused if
    anything was booked into those times meanwhile. The snapshot is kept in the existing Log table (no migration).
"""
import json
from collections import defaultdict
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .conflict_report import scan
from .models import Log, Schedule
from .permissions import can_edit_schedule_kind

UNDO_MINUTES = 5
UNDO_TAG = "UNDO-SNAPSHOT "          # Log.details prefix of a removal snapshot (not shown in the activity history)


class ActionError(Exception):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra or {}


def _fmt(t):
    h, m = t.hour, t.minute
    return f"{((h + 11) % 12) + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _rows(ids):
    return list(Schedule.objects.filter(pk__in=list(ids or [])).select_related(
        "subject", "section__program", "teacher__user", "room", "timeslot", "approved_by"))


def _check_owner(user, rows):
    bad = [r for r in rows if not can_edit_schedule_kind(user, r.subject.classification, r.section.program.department)]
    if bad:
        r = bad[0]
        who = "the Registrar (Gen Ed)" if r.subject.classification == "minor" else f"the Dean of {r.section.program.department}"
        raise ActionError(f"{r.subject.code} ({r.section.program.name} {r.section.name}) belongs to {who}. Only its owner can change it.", 403)


def _classes(rows):
    """Rows -> one entry per class (section + subject): {key, label, ids, when, status}."""
    by = defaultdict(list)
    for r in rows:
        by[(r.section_id, r.subject_id)].append(r)
    out = []
    for (_sec, _sub), rs in by.items():
        rs.sort(key=lambda r: ("MonTueWedThuFriSatSun".find(r.timeslot.day[:3]), r.timeslot.start_time))
        r0 = rs[0]
        when = []
        for r in rs:
            txt = f"{r.timeslot.day[:3]} {_fmt(r.timeslot.start_time)}–{_fmt(r.timeslot.end_time)}"
            when.append(txt)
        out.append({"key": f"{r0.section_id}-{r0.subject_id}", "code": r0.subject.code, "title": r0.subject.title,
                    "section": f"{r0.section.program.name} {r0.section.name}", "ids": [r.id for r in rs],
                    "periods": when, "room": r0.room.name, "status": r0.status,
                    "label": f"{r0.subject.code} — {r0.section.program.name} {r0.section.name}"})
    out.sort(key=lambda c: c["label"])
    return out


# ------------------------------------------------------------------------------------------------ approve / publish / draft
def check_ready(rows):
    """Split rows into ready / blocked by the conflict check. A class (section + subject) with ANY selected period in a conflict is blocked
    as a whole, so a class is never half approved. Returns (ready_rows, blocked_classes)."""
    if not rows:
        return [], []
    ids = {r.id for r in rows}
    reasons = defaultdict(list)
    for sem in {r.section.semester for r in rows}:
        rep = scan(semester=sem, involving_ids=ids, limit=500)
        for c in rep["conflicts"]:
            for side in (c["a"], c["b"]):
                for i in side["ids"]:
                    if i in ids and c["message"] not in reasons[i]:
                        reasons[i].append(c["message"])
    bad_class = {(r.section_id, r.subject_id) for r in rows if reasons.get(r.id)}
    ready = [r for r in rows if (r.section_id, r.subject_id) not in bad_class]
    blocked = []
    for cls in _classes([r for r in rows if (r.section_id, r.subject_id) in bad_class]):
        why = []
        for i in cls["ids"]:
            for m in reasons.get(i, []):
                if m not in why:
                    why.append(m)
        cls["reasons"] = why
        blocked.append(cls)
    return ready, blocked


def change_status(user, rows, to_status):
    """rows: the candidate rows (already scoped to this user's kind). -> {updated, ready, blocked, status, skipped}"""
    _check_owner(user, rows)
    if to_status == "draft":
        return back_to_draft(user, rows)
    from_status = "draft" if to_status == "approved" else "approved"
    skipped = _classes([r for r in rows if r.status != from_status])
    rows = [r for r in rows if r.status == from_status]
    ready, blocked = check_ready(rows)
    ready_ids = [r.id for r in ready]
    teachers = defaultdict(int)
    if to_status == "published":
        for r in ready:
            teachers[r.teacher.user_id] += 1
    with transaction.atomic():
        # status=from_status in the filter: a row someone else moved a moment ago is not moved twice
        count = Schedule.objects.filter(pk__in=ready_ids, status=from_status).update(
            status=to_status, approved_by=user, approved_at=timezone.now())
        if teachers:
            from notifications.models import Notification
            Notification.objects.bulk_create([
                Notification(recipient_id=uid, notif_type="schedule_update",
                             message=f"{n} class period{'s' if n != 1 else ''} on your schedule {'were' if n != 1 else 'was'} just published and are now final.")
                for uid, n in teachers.items()])
        Log.objects.bulk_create([Log(action="UPDATE", schedule_id=r.id, user=user, details=f"{to_status.capitalize()}: {r.subject.code} "
                                     f"({r.section.program.name} {r.section.name}) {r.timeslot.day[:3]} {_fmt(r.timeslot.start_time)}")
                                 for r in ready])
        if blocked:
            Log.objects.create(action="UPDATE", schedule_id=0, user=user, details=(
                f"Not {to_status} (conflict): " + "; ".join(f"{b['label']}: {b['reasons'][0]}" for b in blocked))[:2000])
    return {"updated": count, "status": to_status, "ready": _classes(ready), "blocked": blocked, "skipped": skipped}


def back_to_draft(user, rows):
    _check_owner(user, rows)
    published = [r for r in rows if r.status == "published"]
    if published:
        raise ActionError("Published classes stay published: their teachers were already told the schedule is final. "
                          f"{published[0].subject.code} ({published[0].section.name}) is published.", 409)
    rows = [r for r in rows if r.status == "approved"]
    from faculty.models import CoverageSuggestion
    used = set(CoverageSuggestion.objects.filter(schedule_id__in=[r.id for r in rows]).values_list("schedule_id", flat=True))
    held = _classes([r for r in rows if r.id in used])
    for h in held:
        h["reasons"] = ["A faculty-absence coverage was made for this class, so it stays approved."]
    hold_keys = {(r.section_id, r.subject_id) for r in rows if r.id in used}
    ok = [r for r in rows if (r.section_id, r.subject_id) not in hold_keys]
    with transaction.atomic():
        count = Schedule.objects.filter(pk__in=[r.id for r in ok], status="approved").update(status="draft", approved_by=None, approved_at=None)
        Log.objects.bulk_create([Log(action="UPDATE", schedule_id=r.id, user=user,
                                     details=f"Moved back to draft: {r.subject.code} ({r.section.program.name} {r.section.name})") for r in ok])
    return {"updated": count, "status": "draft", "ready": _classes(ok), "blocked": held, "skipped": []}


# ------------------------------------------------------------------------------------------------ remove / undo
def remove_preview(user, ids):
    rows = _rows(ids)
    if len(rows) != len(set(ids or [])):
        raise ActionError("Some of these classes were already changed or removed. Reload the schedule.", 409)
    _check_owner(user, rows)
    locked = _classes([r for r in rows if r.status != "draft"])
    for c in locked:
        c["reasons"] = [f"{c['status'].capitalize()}: move it back to Draft first."]
    drafts = [r for r in rows if r.status == "draft"]
    warnings, shared = [], []
    for mk in {r.merge_key for r in drafts if r.merge_key}:
        others = list(Schedule.objects.filter(merge_key=mk).exclude(pk__in=[r.id for r in drafts])
                      .select_related("section__program").values_list("section__program__name", "section__name").distinct())
        mine = next(r for r in drafts if r.merge_key == mk)
        if others:
            shared.append(mk)
            warnings.append(f"{mine.subject.code} is a SHARED class: {', '.join(f'{p} {s}' for p, s in sorted(set(others)))} attend it too. "
                            "Removing it here leaves them without this section; their own periods are not removed.")
    from faculty.models import CoverageSuggestion
    cov = CoverageSuggestion.objects.filter(schedule_id__in=[r.id for r in drafts]).count()
    if cov:
        warnings.append(f"{cov} faculty-absence coverage suggestion(s) for these periods will be deleted and are not restored by Undo.")
    return {"remove": _classes(drafts), "locked": locked, "warnings": warnings, "shared": bool(shared),
            "periods": len(drafts), "undo_minutes": UNDO_MINUTES}


def _snapshot(r):
    return {"id": r.id, "subject": r.subject_id, "teacher": r.teacher_id, "room": r.room_id, "section": r.section_id,
            "timeslot": r.timeslot_id, "is_substitution": r.is_substitution, "original_teacher": r.original_teacher_id,
            "status": r.status, "approved_by": r.approved_by_id, "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            "is_manual_override": r.is_manual_override, "school_year": r.school_year, "merge_key": r.merge_key, "term": r.term,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None}


def remove(user, ids, confirm_shared=False):
    plan = remove_preview(user, ids)
    if plan["locked"]:
        raise ActionError("Approved or published classes cannot be removed. Move them back to Draft first: "
                          + ", ".join(c["label"] for c in plan["locked"]), 409, {"locked": plan["locked"]})
    if plan["shared"] and not confirm_shared:
        raise ActionError("This includes a shared class used by other sections. Confirm to remove it.", 409, {"needs_confirm": True, **plan})
    rows = _rows(ids)
    with transaction.atomic():
        fresh = list(Schedule.objects.select_for_update().filter(pk__in=[r.id for r in rows]))
        if len(fresh) != len(rows) or any(f.status != "draft" for f in fresh):
            raise ActionError("These classes were changed by someone else a moment ago. Reload and try again.", 409)
        snap = Log.objects.create(action="DELETE", schedule_id=0, user=user,
                                  details=UNDO_TAG + json.dumps({"rows": [_snapshot(r) for r in rows]}))
        Log.objects.bulk_create([Log(action="DELETE", schedule_id=r.id, user=user, details=f"Removed {r.subject.code} "
                                     f"({r.section.program.name} {r.section.name}) {r.timeslot.day[:3]} {_fmt(r.timeslot.start_time)}–"
                                     f"{_fmt(r.timeslot.end_time)}, room {r.room.name}") for r in rows])
        Schedule.objects.filter(pk__in=[r.id for r in rows]).delete()
    from .housekeeping import cleanup_after_delete
    cleanup_after_delete()
    return {"removed": len(rows), "classes": plan["remove"], "undo_token": snap.id, "undo_minutes": UNDO_MINUTES}


def undo_remove(user, token):
    from django.utils.dateparse import parse_datetime
    snap = Log.objects.filter(pk=token, action="DELETE", schedule_id=0, details__startswith=UNDO_TAG).first()
    if snap is None:
        raise ActionError("Nothing to undo (it was already undone or has expired).", 404)
    if snap.user_id != getattr(user, "id", None):
        raise ActionError("Only the person who removed these classes can undo it.", 403)
    if timezone.now() - snap.timestamp > timedelta(minutes=UNDO_MINUTES):
        raise ActionError(f"Undo is only possible for {UNDO_MINUTES} minutes after removing.", 410)
    rows = json.loads(snap.details[len(UNDO_TAG):])["rows"]
    from .conflicts import find_conflicts
    from .models import TimeSlot
    from faculty.models import FacultyProfile
    from rooms.models import Room
    from .models import Section
    if Schedule.objects.filter(pk__in=[r["id"] for r in rows]).exists():
        raise ActionError("These classes are already back in the schedule.", 409)
    try:
        with transaction.atomic():
            for r in rows:
                sec, ts = Section.objects.filter(pk=r["section"]).first(), TimeSlot.objects.filter(pk=r["timeslot"]).first()
                t, rm = FacultyProfile.objects.filter(pk=r["teacher"]).first(), Room.objects.filter(pk=r["room"]).first()
                if None in (sec, ts, t, rm):
                    raise ActionError("A teacher, room, section or time slot of these classes no longer exists, so they cannot be restored.", 409)
                msgs = find_conflicts(teacher=t, room=rm, section=sec, timeslot=ts, semester=sec.semester, merge_key=r["merge_key"])
                if msgs:
                    raise ActionError(f"Cannot undo: that time was booked meanwhile ({ts.day[:3]} {_fmt(ts.start_time)}). {msgs[0]} "
                                      "Nothing was restored.", 409)
                obj = Schedule(id=r["id"], subject_id=r["subject"], teacher_id=r["teacher"], room_id=r["room"], section_id=r["section"],
                               timeslot_id=r["timeslot"], is_substitution=r["is_substitution"], original_teacher_id=r["original_teacher"],
                               status=r["status"], approved_by_id=r["approved_by"],
                               approved_at=parse_datetime(r["approved_at"]) if r["approved_at"] else None,
                               is_manual_override=r["is_manual_override"], school_year=r["school_year"], merge_key=r["merge_key"],
                               term=r["term"])
                obj.save(force_insert=True)
                if r.get("generated_at"):        # keep the original creation time (auto_now_add sets "now" on insert)
                    Schedule.objects.filter(pk=obj.pk).update(generated_at=parse_datetime(r["generated_at"]))
            Log.objects.bulk_create([Log(action="CREATE", schedule_id=r["id"], user=user, details="Restored by Undo after removal")
                                     for r in rows])
            snap.details = "Undone: " + snap.details[len(UNDO_TAG):][:200]
            snap.save(update_fields=["details"])
    except IntegrityError:
        raise ActionError("Cannot undo: one of those times was booked meanwhile. Nothing was restored.", 409)
    return {"restored": len(rows)}


# ------------------------------------------------------------------------------------------------ history
def history(user, ids):
    rows = _rows(ids)
    if not rows:
        raise ActionError("Class not found.", 404)
    out = []
    first = min(rows, key=lambda r: r.generated_at)
    out.append({"when": first.generated_at, "user": "", "action": "Created",
                "details": "Created by the generator" if not first.is_manual_override else "Created (later changed by hand)"})
    for lg in Log.objects.filter(schedule_id__in=[r.id for r in rows]).exclude(details__startswith=UNDO_TAG).select_related("user").order_by("timestamp"):
        name = (lg.user.get_full_name().strip() or lg.user.username) if lg.user else ""
        out.append({"when": lg.timestamp, "user": name, "action": {"CREATE": "Created", "UPDATE": "Changed", "DELETE": "Removed"}.get(lg.action, lg.action),
                    "details": lg.details})
    r0 = rows[0]
    if r0.approved_at and not any("Approved" in e["details"] or "Published" in e["details"] for e in out):
        out.append({"when": r0.approved_at, "user": (r0.approved_by.get_full_name().strip() or r0.approved_by.username) if r0.approved_by else "",
                    "action": r0.status.capitalize(), "details": f"{r0.status.capitalize()} (recorded on the class)"})
    out.sort(key=lambda e: e["when"])
    for e in out:
        e["when"] = e["when"].isoformat()
    return {"class": _classes(rows)[0] if len(_classes(rows)) == 1 else None, "events": out}
