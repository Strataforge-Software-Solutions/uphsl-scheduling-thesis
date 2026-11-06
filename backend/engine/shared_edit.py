"""Edit a SHARED (merged) class as ONE class: the teacher or room chosen in the Edit dialog is applied to every section that attends
it, so the sharing never breaks (all of its rows keep one teacher, one room and one time, Schedule.merge_key). The day / time is moved
with "Choose a new day and time" (engine.reschedule), which moves the whole group the same way.

Every rule is checked for the WHOLE group before anything is saved, and the change is saved in one transaction:
  * only the owner of the class may change it (the Registrar for Gen Ed), and only while every row is still a Draft;
  * teacher: the qualification rule (engine.teacher_scope) for every attending section's subject, no other class at that time, the
    weekly limit (the shared class counts once); their submitted availability is a preference here (a hand change may go outside it);
  * room: the right kind of room, allowed for every attending college, seats all attending students together, not booked then;
  * a conflict scan before and after: the change may not add a single clash, otherwise it is undone.
"""
from django.db import transaction

from .models import Log, Schedule, TimeSlot
from .permissions import can_edit_schedule_kind


class SharedEditError(Exception):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra or {}


def _name(t):
    return t.user.get_full_name().strip() or t.user.username


def group_rows(rows_or_key):
    """Every row of the shared class (all attending sections)."""
    key = rows_or_key if isinstance(rows_or_key, str) else rows_or_key[0].merge_key
    return list(Schedule.objects.filter(merge_key=key).select_related(
        "subject", "subject__program", "subject__field", "section__program", "teacher__user", "room", "timeslot"))


def check_group(user, group, ignore_status=False):
    """The group is one consistent class the user may change. Returns the member (section, subject, rows) list.
    ignore_status: READ-ONLY listing of times (a Dean's Gen Ed move request); applying a move always requires Draft."""
    if not group:
        raise SharedEditError("That class no longer exists. Reload the schedule.", 404)
    members = {}
    for r in group:
        members.setdefault(r.section_id, (r.section, r.subject, []))[2].append(r)
    for section, subject, _rows in members.values():
        if not can_edit_schedule_kind(user, subject.classification, section.program.department):
            raise SharedEditError("Only the owner of this class can change it (Gen Ed: the Registrar).", 403)
    if not ignore_status and any(r.status != "draft" for r in group):
        raise SharedEditError("Part of this shared class is approved or published. Move it back to Draft before editing it.", 409)
    first = members[group[0].section_id][2]
    want = sorted(r.timeslot_id for r in first)
    if len({r.teacher_id for r in group}) != 1 or len({r.room_id for r in group}) != 1 or \
            any(sorted(r.timeslot_id for r in rows) != want for _s, _sub, rows in members.values()):
        raise SharedEditError("The sections of this shared class no longer have the same teacher, room and time (an older change split it). "
                              "Remove it and Generate again; nothing was changed.", 409)
    return list(members.values())


def students(members):
    return sum(int(getattr(s, "student_count", 0) or 0) for s, _sub, _rows in members)


def edit(user, ids, teacher_id=None, room_id=None, override_workload=False):
    """Apply a new teacher and / or room to the whole shared class of these rows. Raises SharedEditError; returns a summary."""
    from faculty.models import FacultyProfile
    from rooms.models import Room
    from rooms.rules import fixed_room_message, may_use, reserved_message, room_kind_message
    from . import locks
    from . import workload as wl
    from .conflict_report import scan
    from .conflicts import find_conflicts
    from .teacher_scope import teacher_allowed
    from .views import _build_availability_rules
    seed = list(Schedule.objects.filter(pk__in=ids or []))
    if not seed or not seed[0].merge_key:
        raise SharedEditError("This is not a shared class.", 400)
    mk = seed[0].merge_key
    group = group_rows(mk)
    members = check_group(user, group)
    cur_t, cur_r = group[0].teacher, group[0].room
    teacher = cur_t if teacher_id in (None, "", cur_t.id, str(cur_t.id)) else \
        FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(pk=teacher_id, user__is_active=True).first()
    room = cur_r if room_id in (None, "", cur_r.id, str(cur_r.id)) else Room.objects.filter(pk=room_id).first()
    if teacher is None or room is None:
        raise SharedEditError("That teacher or room does not exist (or the teacher is no longer active).", 404)
    if teacher.id == cur_t.id and room.id == cur_r.id:
        return {"updated": 0, "summary": "Nothing to change."}
    slots = sorted({r.timeslot_id: r.timeslot for r in members[0][2]}.values(), key=lambda s: (s.day, s.start_time))
    term = group[0].term or members[0][0].semester
    over = None
    outside_avail = False
    if teacher.id != cur_t.id:
        for section, subject, _rows in members:
            why = teacher_allowed(user, teacher, subject, section)
            if why:
                raise SharedEditError(why, 400)
        # a change BY HAND may put a teacher outside their submitted availability (it is a preference); only clashes refuse it
        rules = _build_availability_rules([teacher], list(TimeSlot.objects.all()), group[0].school_year or None, term or None)
        outside_avail = any(s.id in rules.get(teacher.id, set()) for s in slots)
        for s in slots:
            msgs = find_conflicts(teacher=teacher, timeslot=s, exclude_model="Schedule", merge_key=mk, semester=members[0][0].semester)
            if msgs:
                raise SharedEditError(f"{_name(teacher)} is not free: {msgs[0]}", 400)
        over = wl.check_assignment(teacher, term, slots, [r.id for r in group])
        if over:
            policy = wl.limits()["policy"]
            if policy == "strict" or not override_workload:
                raise SharedEditError(over["message"], 409, {"workload_overload": over, "can_override": policy != "strict"})
    if room.id != cur_r.id:
        n = students(members)
        for section, subject, _rows in members:
            msg = fixed_room_message(subject, room) or room_kind_message(subject, room)
            if msg:
                raise SharedEditError(msg, 400)
            if not may_use(room, section.program.department):
                raise SharedEditError(reserved_message(room, section.program.department), 400)
        if (room.capacity or 0) and n and room.capacity < n:
            raise SharedEditError(f"{room.name} seats {room.capacity}, fewer than the {n} students of this shared class "
                                  f"({', '.join(f'{s.program.name} {s.name}' for s, _sub, _r in members)}).", 400)
        for s in slots:
            msgs = find_conflicts(room=room, timeslot=s, exclude_model="Schedule", merge_key=mk, semester=members[0][0].semester)
            if msgs:
                raise SharedEditError(f"{room.name} is not free: {msgs[0]}", 400)
    ids_all = [r.id for r in group]
    with transaction.atomic():
        if not locks.try_lock("classes"):
            raise SharedEditError(locks.BUSY, 409)
        fresh = list(Schedule.objects.select_for_update().filter(pk__in=ids_all))
        if len(fresh) != len(ids_all) or any(f.status != "draft" or f.teacher_id != cur_t.id or f.room_id != cur_r.id for f in fresh):
            raise SharedEditError("This class was changed by someone else. Reload and try again.", 409)
        before = scan(semester=members[0][0].semester, involving_ids=set(ids_all), limit=200)["total"]
        Schedule.objects.filter(pk__in=ids_all).update(teacher=teacher, room=room, is_manual_override=True)
        after = scan(semester=members[0][0].semester, involving_ids=set(ids_all), limit=200)
        if after["total"] > before:
            transaction.set_rollback(True)
            raise SharedEditError("The change would create a scheduling conflict, so nothing was changed.", 409,
                                  {"conflicts": after["conflicts"][:5]})
        what = []
        if teacher.id != cur_t.id:
            what.append(f"teacher {_name(cur_t)} → {_name(teacher)}"
                        + (" (a time they marked unavailable)" if outside_avail else ""))
        if room.id != cur_r.id:
            what.append(f"room {cur_r.name} → {room.name}")
        sections = ", ".join(f"{s.program.name} {s.name}" for s, _sub, _r in members)
        Log.objects.create(action="UPDATE", schedule_id=ids_all[0], user=user,
                           details=f"Shared class {group[0].subject.code} ({sections}): {'; '.join(what)}"
                           + (f" -- WORKLOAD OVERRIDE: {over['message']}" if over else ""))
        if teacher.id != cur_t.id and teacher.user_id != getattr(user, "id", None):
            from notifications.models import Notification
            Notification.objects.create(recipient=teacher.user, notif_type="schedule_update",
                                        message=f"You now teach the shared class {group[0].subject.code} ({sections}).")
    return {"updated": len(ids_all), "sections": len(members),
            "summary": f"{group[0].subject.code} (shared: {sections}): {'; '.join(what)}. All {len(members)} sections changed together."}
