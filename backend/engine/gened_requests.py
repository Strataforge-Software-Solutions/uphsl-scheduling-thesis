"""Gen Ed move requests: a Dean asks the Registrar to move a Gen Ed (minor) class of their own program to another day / time, e.g. to
free a time for a major subject.

  options()  READ-ONLY. The times the Gen Ed class could move to, exactly as the Registrar would see them in "Choose a new day and
             time" (engine.reschedule.suggest): same teacher and room, every attending section, the teacher and the room free, Lecture
             before Lab kept. Listed even when the class is already approved (asking is allowed; moving is not, see approve()).
  create()   the Dean picks one of those times and gives a reason. Nothing moves. The Registrar is notified.
  approve()  the Registrar. Re-checks everything at THAT moment (engine.reschedule.apply: the time must still be in the clash-free list,
             a database lock, every saved row re-checked, a conflict scan; any clash undoes everything). It moves ONLY this Gen Ed class
             (all sections of a shared class together): no other class -- another Dean's major or another Gen Ed class -- is ever
             moved or overwritten. A class that is approved / published must be moved back to Draft first (it is never moved by itself).
             If the time is no longer free, the request is marked "could not be applied" and nothing changes.
  reject() / cancel()   the Registrar declines / the Dean withdraws a pending request.
"""
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from .models import GenEdMoveRequest, Schedule

# the Registrar's point of view, used ONLY to list the times (read-only) so the Dean sees exactly what the Registrar could approve
_REGISTRAR_VIEW = SimpleNamespace(role="registrar", faculty_type=None, departments=[], is_authenticated=True, id=None)


class RequestError(Exception):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra or {}


def _is_dean(u):
    return getattr(u, "role", "") == "faculty" and getattr(u, "faculty_type", "") == "dean"


def _name(u):
    return (u.get_full_name().strip() or u.username) if u else ""


def _notify(users, text):
    from notifications.models import Notification
    Notification.objects.bulk_create([Notification(recipient=u, notif_type="schedule_update", message=text[:255]) for u in users])


def _rows_for_dean(user, ids):
    if not _is_dean(user):
        raise RequestError("Only a Dean can request a Gen Ed schedule change.", 403)
    rows = list(Schedule.objects.filter(pk__in=ids or []).select_related("subject", "section__program", "timeslot"))
    if not rows or len(rows) != len(set(ids)):
        raise RequestError("That class was changed or removed. Reload the schedule and try again.", 409)
    if len({(r.section_id, r.subject_id) for r in rows}) != 1:
        raise RequestError("These periods belong to different classes.", 400)
    r0 = rows[0]
    if r0.subject.classification != "minor":
        raise RequestError("Only Gen Ed (minor) classes are requested from the Registrar; you change your program subjects yourself.", 400)
    if r0.section.program.department not in (user.departments or []):
        raise RequestError("You can only request changes for Gen Ed classes of your own college's sections.", 403)
    return rows


def options(user, ids):
    """READ-ONLY: {"class": ..., "options": [...], "reason": ...} -- the times this Gen Ed class could move to."""
    from . import reschedule
    rows = _rows_for_dean(user, ids)
    try:
        res = reschedule.suggest(_REGISTRAR_VIEW, ids=[r.id for r in rows], limit=300, _any_status=True)
    except reschedule.RescheduleError as e:
        raise RequestError(e.message, e.status, e.extra)
    status = rows[0].status
    return {"class": res["class"], "options": res["options"] + res.get("outside_options", []), "reason": res["reason"],
            "status": status,
            "note": "" if status == "draft" else
            f"This Gen Ed class is {status}. You can still ask; the Registrar must move it back to Draft before it can be moved."}


def create(user, ids, key, reason=""):
    rows = _rows_for_dean(user, ids)
    r0 = rows[0]
    if GenEdMoveRequest.objects.filter(subject=r0.subject, section=r0.section, status="pending").exists():
        raise RequestError("There is already a pending request for this class. Wait for the Registrar, or cancel it first.", 409)
    opt = next((o for o in options(user, ids)["options"] if o["key"] == key), None)
    if opt is None:
        raise RequestError("That time is no longer free for this class. Reload the list and pick another.", 409, {"refresh": True})
    from .reschedule import _when
    req = GenEdMoveRequest.objects.create(
        schedule_ids=[r.id for r in rows], subject=r0.subject, section=r0.section, current_label=_when(rows), option_key=key,
        target_label=opt["label"], reason=(reason or "").strip()[:2000], requested_by=user)
    from accounts.models import User
    _notify(User.objects.filter(role="registrar", is_active=True),
            f"{_name(user)} asks to move {r0.subject.code} ({r0.section.program.name} {r0.section.name}) from {req.current_label} to "
            f"{opt['label']}. See Schedules > Gen Ed move requests.")
    return serialize(req)


def _current_rows(req):
    if req.section is None or req.subject is None:
        return []
    return list(Schedule.objects.filter(section=req.section, subject=req.subject, term=req.section.semester))


def approve(user, req_id, note=""):
    from . import reschedule
    if getattr(user, "role", "") != "registrar":
        raise RequestError("Only the Registrar approves Gen Ed schedule changes.", 403)
    req = GenEdMoveRequest.objects.select_related("subject", "section__program", "requested_by").filter(pk=req_id).first()
    if req is None:
        raise RequestError("Request not found.", 404)
    if req.status != "pending":
        raise RequestError(f"This request is already {req.get_status_display().lower()}.", 409)
    rows = _current_rows(req)
    if not rows:
        return _finish(req, user, "failed", "The class no longer exists (it was removed or regenerated).")
    if any(r.status != "draft" for r in rows) or (rows[0].merge_key and Schedule.objects.filter(merge_key=rows[0].merge_key)
                                                                      .exclude(status="draft").exists()):
        raise RequestError("This Gen Ed class is approved or published. Move it back to Draft first, then approve the request "
                           "(an approved class is never moved by itself). The request stays pending.", 409)
    try:
        res = reschedule.apply(user, key=req.option_key, ids=[r.id for r in rows])
    except reschedule.RescheduleError as e:
        # the time is no longer free (another class took it) or the change would clash: NOTHING was changed
        return _finish(req, user, "failed", f"Not applied: {e.message}")
    return _finish(req, user, "approved", (note or "").strip(), summary=res.get("summary", ""))


def _finish(req, user, status, note, summary=""):
    with transaction.atomic():
        req.status, req.decided_by, req.decided_at = status, user, timezone.now()
        req.decision_note = note[:2000]
        req.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    if req.requested_by_id:
        what = {"approved": "approved: the class was moved", "rejected": "declined", "failed": "could not be applied (nothing was changed)"}
        _notify([req.requested_by], f"Your request to move {req.subject.code if req.subject else 'a Gen Ed class'} to {req.target_label} was "
                                    f"{what.get(status, status)}." + (f" {note}" if note else ""))
    out = serialize(req)
    out["summary"] = summary
    return out


def reject(user, req_id, note=""):
    if getattr(user, "role", "") != "registrar":
        raise RequestError("Only the Registrar decides Gen Ed schedule changes.", 403)
    req = GenEdMoveRequest.objects.select_related("subject", "section__program", "requested_by").filter(pk=req_id).first()
    if req is None:
        raise RequestError("Request not found.", 404)
    if req.status != "pending":
        raise RequestError(f"This request is already {req.get_status_display().lower()}.", 409)
    return _finish(req, user, "rejected", (note or "").strip())


def cancel(user, req_id):
    req = GenEdMoveRequest.objects.select_related("subject", "section__program").filter(pk=req_id, requested_by=user).first()
    if req is None:
        raise RequestError("Request not found.", 404)
    if req.status != "pending":
        raise RequestError(f"This request is already {req.get_status_display().lower()}.", 409)
    req.status, req.decided_at = "cancelled", timezone.now()
    req.save(update_fields=["status", "decided_at"])
    return serialize(req)


def listing(user, status=""):
    qs = GenEdMoveRequest.objects.select_related("subject", "section__program", "requested_by", "decided_by")
    if getattr(user, "role", "") == "registrar":
        pass
    elif _is_dean(user):
        qs = qs.filter(section__program__department__in=user.departments)
    else:
        raise RequestError("Not allowed.", 403)
    if status:
        qs = qs.filter(status=status)
    items = [serialize(r) for r in qs[:200]]
    items.sort(key=lambda x: (x["status"] != "pending", ))
    return {"items": items, "pending": sum(1 for x in items if x["status"] == "pending")}


def serialize(r):
    return {
        "id": r.id, "status": r.status, "status_label": r.get_status_display(),
        "subject": f"{r.subject.code} — {r.subject.title}" if r.subject else "(removed)",
        "section": f"{r.section.program.name} {r.section.name}" if r.section else "(removed)",
        "department": r.section.program.department if r.section else "",
        "current": r.current_label, "target": r.target_label, "reason": r.reason,
        "requested_by": _name(r.requested_by), "requested_by_id": r.requested_by_id,
        "decided_by": _name(r.decided_by), "decision_note": r.decision_note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    }
