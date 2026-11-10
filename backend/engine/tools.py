"""
Dean/Registrar tools:
  * reschedule_view          -- move one or more classes to a new day / start time, all-or-nothing, with conflict
                                warnings and free-slot suggestions on the chosen day.
  * teacher_replacements     -- per class of a teacher who is leaving / unavailable: ranked qualified stand-ins.
  * assign_replacement       -- hand a whole class (all its periods) to the chosen replacement.
"""
from collections import defaultdict
from datetime import datetime, date, time as dtime, timedelta

from django.db import IntegrityError, transaction
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from faculty.models import FacultyProfile
from .conflicts import find_conflicts
from .models import Schedule, TimeSlot
from .permissions import can_edit_schedule_kind

DAY_START, DAY_END = 7 * 60, 21 * 60          # suggestion window: 7:00 AM - 9:00 PM
STEP = 30


def _min(t):
    return t.hour * 60 + t.minute


def _t(m):
    return dtime(m // 60, m % 60)


def _hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def _label(m):
    h, mm = divmod(m, 60)
    return f"{(h % 12) or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def _can_edit(user, row):
    return can_edit_schedule_kind(user, row.subject.classification, row.section.program.department)


def _class_label(rows):
    r = rows[0]
    return f"{r.subject.title} - {r.section.program.name} {r.section.name}"


def _shape(rows, end_shift=0):
    """[(start offset, end offset)] of a class block's periods; end_shift stretches / shrinks the last period."""
    first = min(_min(r.timeslot.start_time) for r in rows)
    shape = [(_min(r.timeslot.start_time) - first, _min(r.timeslot.end_time) - first) for r in rows]
    if end_shift:
        i = max(range(len(shape)), key=lambda k: shape[k][1])
        shape[i] = (shape[i][0], shape[i][1] + end_shift)
    return shape


# ---------------------------------------------------------------------------------------------------------
# Fast, read-only conflict checking.
#
# Everything a check needs (every class on the affected days of the affected semesters) is loaded with ONE
# query and compared in memory, so checking and suggesting times for any number of classes costs a handful of
# queries -- no per-period queries, no temporary writes. The rules are the same as engine.conflicts:
#   teacher / room / section (students): no overlap at all (same as the CSP solver)
#   rows of one merged (shared) class never clash with each other; only the same semester can clash.
# Suggestions are stricter (a suggested time never overlaps the students at all).
# ---------------------------------------------------------------------------------------------------------
def _placed(pl, start=None):
    """The periods of a planned class after the move: [(teacher, room, section, merge_key, start, end, row_id)]."""
    rows = pl["rows"]
    first = min(_min(r.timeslot.start_time) for r in rows)
    off = (pl["start"] if start is None else start) - first
    last = max(rows, key=lambda x: _min(x.timeslot.end_time))
    out = []
    for r in rows:
        s_ = _min(r.timeslot.start_time) + off
        e_ = _min(r.timeslot.end_time) + off + (pl["end_shift"] if r is last else 0)
        out.append((pl["teacher"].id if pl["teacher"] else r.teacher_id, pl["room"].id if pl["room"] else r.room_id,
                    r.section_id, r.merge_key, s_, e_, r.id))
    return out


def _load_pool(plans):
    """{(semester, day): [(teacher, room, section, merge_key, start, end, row_id)]} of every class NOT being moved."""
    moving = {r.id for pl in plans for r in pl["rows"]}
    sems = {pl["rows"][0].section.semester for pl in plans}
    days = {pl["day"] for pl in plans}
    pool = defaultdict(list)
    q = Schedule.objects.filter(section__semester__in=sems, timeslot__day__in=days).exclude(pk__in=moving).values_list(
        "teacher_id", "room_id", "section_id", "merge_key", "timeslot__start_time", "timeslot__end_time",
        "id", "section__semester", "timeslot__day")
    for t, r, sec, mk, st, en, rid, sem, day in q:
        pool[(sem, day)].append((t, r, sec, mk, _min(st), _min(en), rid))
    return pool


def _pool_for(pl, plans, pool):
    """Other classes on this plan's day/semester: the unmoved ones plus where the other planned classes will be."""
    sem = pl["rows"][0].section.semester
    mine = {r.id for r in pl["rows"]}
    rows = list(pool.get((sem, pl["day"]), []))
    for q in plans:
        if q is pl or {r.id for r in q["rows"]} == mine:
            continue
        if q["day"] == pl["day"] and q["rows"][0].section.semester == sem:
            rows += _placed(q)
    mk = pl["rows"][0].merge_key
    return [x for x in rows if not (mk and x[3] == mk)]


def _clashes(pl, placed, others, tol):
    """[(kind, other_row_id, minutes)] -- the first clash of each kind found for the planned class."""
    found, seen = [], set()
    for t, r, sec, mk, a, b, rid in placed:
        sec_total, sec_first = 0, None
        for t2, r2, sec2, mk2, a2, b2, id2 in others:
            ov = min(b, b2) - max(a, a2)
            if ov <= 0:
                continue
            if t == t2 and "teacher" not in seen:
                seen.add("teacher"); found.append(("teacher", id2, ov))
            if r == r2 and "room" not in seen:
                seen.add("room"); found.append(("room", id2, ov))
            if sec == sec2:
                sec_total += ov
                sec_first = sec_first or id2
        if sec_total > tol and "section" not in seen:
            seen.add("section"); found.append(("section", sec_first, sec_total))
    if max(e for *_, e, _id in placed) > DAY_END + 3 * 60:
        found.append(("late", None, 0))
    return found


def _options(pl, others, limit=6, order=None):
    """Start times on the planned day where the whole class block clashes with nothing (strict) and the Lecture stays before
    its Lab (order: lecorder.bounds of this class)."""
    from . import lecorder
    teachers, rooms, sections = _resources(pl)
    rel = [x for x in others if x[0] in teachers or x[1] in rooms or x[2] in sections]
    shape = _shape(pl["rows"], pl["end_shift"])
    span = max(e for _, e in shape)
    ok = []
    from .college_break import overlaps as overlaps_college_break
    for st in range(DAY_START, DAY_END - span + 1, STEP):
        if any(overlaps_college_break(st + a, st + b) for a, b in shape):
            continue
        if all(not any(st + a < x[5] and x[4] < st + b for x in rel) for a, b in shape)                 and not lecorder.violates(order, [(pl["day"], st + a, st + b) for a, b in shape]):
            ok.append(st)
    ok.sort(key=lambda x: abs(x - pl["start"]))
    return [{"start_time": _hhmm(x), "end_time": _hhmm(x + span), "label": f"{_label(x)} – {_label(x + span)}"}
            for x in sorted(ok[:limit])]


def _resources(pl):
    rows = pl["rows"]
    return ({pl["teacher"].id if pl["teacher"] else r.teacher_id for r in rows},
            {pl["room"].id if pl["room"] else r.room_id for r in rows},
            {r.section_id for r in rows})


def _describe_clashes(plans, results, tol):
    """Turn [(kind, row_id, minutes)] into readable sentences naming the other class (one query for all names)."""
    ids = {rid for _pl, found in results for _k, rid, _m in found if rid}
    own = {r.id: r for pl in plans for r in pl["rows"]}
    named = {r.id: r for r in Schedule.objects.filter(pk__in=ids - set(own)).select_related("subject", "section", "timeslot")}
    named.update(own)
    planned_at = {x[6]: (pl["day"], x[4], x[5]) for pl in plans for x in _placed(pl)}   # a class being moved: where it WILL be

    def what(rid):
        r = named.get(rid)
        if r is None:
            return "another class"
        if rid in planned_at:
            dd, a_, b_ = planned_at[rid]
            return f"{r.subject.title} ({r.section.name}, {dd} {_label(a_)}-{_label(b_)}, which you are also moving)"
        return f"{r.subject.title} ({r.section.name}, {r.timeslot.day} {_label(_min(r.timeslot.start_time))}-{_label(_min(r.timeslot.end_time))})"

    out = []
    for pl, found in results:
        room = pl["room"] or pl["rows"][0].room
        msgs = []
        for kind, rid, mins in found:
            if kind == "teacher":
                msgs.append(f"The teacher is already teaching {what(rid)} at this time.")
            elif kind == "room":
                msgs.append(f"Room {room.name} is already used by {what(rid)} at this time.")
            elif kind == "section":
                msgs.append(f"The students ({pl['rows'][0].section.name}) already have {what(rid)}, overlapping by {int(mins)} min "
                            + ("(students cannot be in two classes at once)." if not tol else f"(only {tol} min is allowed)."))
            else:
                msgs.append("The class would end too late in the day.")
        out.append(msgs)
    return out


def _evaluate(plans):
    """Check every planned class against everything else. Returns [(plan, messages, suggestions)] in plan order."""
    from .conflicts import class_tolerance_minutes
    tol = class_tolerance_minutes()            # weekly classes: no student overlap at all (the solver's rule)
    from . import lecorder
    pool = _load_pool(plans)
    moving_ids = {r.id for pl in plans for r in pl["rows"]}
    new_pos = [(pl["rows"][0].subject.code, pl["rows"][0].section_id, pl["day"], p[4], p[5]) for pl in plans for p in _placed(pl)]
    results, opts, order_msgs, break_msgs = [], [], [], []
    from .college_break import overlaps as overlaps_college_break, message as college_break_message
    for pl in plans:
        others = _pool_for(pl, plans, pool)
        placed = _placed(pl)
        has_break_overlap = any(overlaps_college_break(start, end) for _t, _r, _s, _mk, start, end, _id in placed)
        found = _clashes(pl, placed, others, tol)
        results.append((pl, found))
        break_msgs.append(college_break_message() if has_break_overlap else "")
        r0 = pl["rows"][0]
        # Lecture before Lab, the solver's rule; partners moved in the same request count at their NEW time
        mine = {r.id for r in pl["rows"]}
        order = lecorder.bounds(r0.subject, r0.section_id, r0.term or r0.section.semester, exclude_ids=moving_ids,
                                moving=[x for x in new_pos if not (x[0] == r0.subject.code and x[1] == r0.section_id)])
        ivs = [(pl["day"], p[4], p[5]) for p in _placed(pl)]
        order_msgs.append(lecorder.message(order, r0.subject) if lecorder.violates(order, ivs) else "")
        opts.append(_options(pl, others, order=order))
    msgs = _describe_clashes(plans, results, tol)
    msgs = [m + ([om] if om else []) + ([bm] if bm else []) for m, om, bm in zip(msgs, order_msgs, break_msgs)]
    return [(pl, m, o) for (pl, _f), m, o in zip(results, msgs, opts)]


def _payload(pl, msgs, suggestions):
    rows = pl["rows"]
    return {
        "ids": [r.id for r in rows], "label": _class_label(rows), "requested_start": _hhmm(pl["start"]),
        "day": pl["day"], "messages": msgs[:3], "ok": not msgs,
        "section_id": rows[0].section_id,
        "teacher_ids": sorted(_resources(pl)[0]), "room_ids": sorted(_resources(pl)[1]),
        "suggestions": suggestions,
    }


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reschedule_view(request):
    """body: {day, start_time, items:[{ids:[..], day?, start_time?, end_time?, room?, teacher?}], preview?, override_workload?}
    Moves every selected class (all its periods, keeping each period's length unless end_time stretches the last)
    to its day / start time, optionally also changing its room / teacher in the same step.
    preview=true: only CHECKS -- always 200 with, for every class, {ok, messages, suggestions}; nothing is saved.
    Otherwise anything that clashes -> 409 with the conflicts and suggested free start times; NOTHING is changed."""
    from rooms.models import Room
    from rooms.rules import may_use, reserved_message
    from .models import Log
    user = request.user
    if not (user.role == "registrar" or (user.role == "faculty" and user.faculty_type == "dean")):
        return Response({"detail": "Only a Dean or the Registrar can change schedules."}, status=403)
    d = request.data
    valid_days = {c for c, _ in TimeSlot.DAYS}
    day = d.get("day")                      # default day; every item may carry its own "day"
    items = d.get("items") or []
    if not items:
        return Response({"detail": "Select at least one class."}, status=400)
    if any((it.get("day") or day) not in valid_days for it in items):
        return Response({"detail": "Choose a day."}, status=400)
    preview = str(d.get("preview", "")).lower() in ("1", "true", "yes")

    def parse(v):
        try:
            h, m = str(v).split(":")[:2]
            return int(h) * 60 + int(m)
        except Exception:
            return None

    default_start = parse(d.get("start_time"))
    all_ids = {i for it in items for i in (it.get("ids") or [])}
    loaded = {r.id: r for r in Schedule.objects.filter(pk__in=all_ids).select_related(
        "timeslot", "subject", "section__program", "teacher__user", "room")}
    room_ids = {it["room"] for it in items if it.get("room")}
    teacher_ids = {it["teacher"] for it in items if it.get("teacher")}
    rooms_by_id = {r.id: r for r in Room.objects.filter(pk__in=room_ids)} if room_ids else {}
    teachers_by_id = {t.id: t for t in FacultyProfile.objects.select_related("user").filter(pk__in=teacher_ids)} if teacher_ids else {}
    plans = []
    for it in items:
        rows = [loaded[i] for i in (it.get("ids") or []) if i in loaded]
        if not rows:
            return Response({"detail": "A selected class no longer exists. Reload and try again."}, status=404)
        for r in rows:
            if not _can_edit(user, r):
                return Response({"detail": f"You are not allowed to change {r.subject.title}."}, status=403)
            if r.status != "draft":
                return Response({"detail": f"{r.subject.code} is {r.status}. Move it back to Draft before changing its day or time."}, status=409)
        start = parse(it.get("start_time")) if it.get("start_time") else default_start
        if start is None:
            return Response({"detail": "Choose a start time."}, status=400)
        end_shift = 0
        if it.get("end_time"):
            end = parse(it.get("end_time"))
            cur_end = max(_min(r.timeslot.end_time) for r in rows) - min(_min(r.timeslot.start_time) for r in rows)
            if end is None or end <= start:
                return Response({"detail": "The end time must be after the start time."}, status=400)
            end_shift = (end - start) - cur_end
        room = rooms_by_id.get(it["room"]) if it.get("room") else None
        teacher = teachers_by_id.get(it["teacher"]) if it.get("teacher") else None
        if room is not None and room.id != rows[0].room_id:
            from rooms.rules import fixed_room_message, room_kind_message
            fx = fixed_room_message(rows[0].subject, room) or room_kind_message(rows[0].subject, room)
            if fx:
                return Response({"detail": fx}, status=400)
        if teacher is not None and teacher.id != rows[0].teacher_id:
            from .teacher_scope import teacher_allowed
            _why = teacher_allowed(request.user, teacher, rows[0].subject, rows[0].section)
            if _why:
                return Response({"detail": _why}, status=400)
        if room is not None and not may_use(room, rows[0].section.program.department):
            return Response({"detail": reserved_message(room, rows[0].section.program.department)}, status=400)
        plans.append({"rows": rows, "start": start, "end_shift": end_shift, "room": room, "teacher": teacher,
                      "day": it.get("day") or day})

    evaluated = _evaluate(plans)
    if preview:
        return Response({"ok": not any(m for _p, m, _o in evaluated),
                         "items": [_payload(pl, m, o) for pl, m, o in evaluated]})
    if any(m for _p, m, _o in evaluated):
        return Response({"detail": "Some classes clash with another class at that time.", "day": plans[0]["day"],
                         "conflicts": [_payload(pl, m, o) for pl, m, o in evaluated if m]}, status=status.HTTP_409_CONFLICT)

    try:
        with transaction.atomic():
            slots = {(t.day, _min(t.start_time), _min(t.end_time)): t
                     for t in TimeSlot.objects.filter(day__in={pl["day"] for pl in plans})}
            for pl in plans:
                rows, off = pl["rows"], pl["start"] - min(_min(r.timeslot.start_time) for r in pl["rows"])
                last = max(rows, key=lambda x: _min(x.timeslot.end_time))
                # move the far end first so a block shifted by less than its own length never collides with itself
                for r in sorted(rows, key=lambda x: _min(x.timeslot.start_time), reverse=off > 0):
                    s_ = _min(r.timeslot.start_time) + off
                    e_ = _min(r.timeslot.end_time) + off + (pl["end_shift"] if r is last else 0)
                    if s_ < 0 or e_ > 24 * 60 or e_ <= s_:
                        continue
                    slot = slots.get((pl["day"], s_, e_))
                    if slot is None:
                        slot = TimeSlot.objects.get_or_create(day=pl["day"], start_time=_t(s_), end_time=_t(e_))[0]
                        slots[(pl["day"], s_, e_)] = slot
                    r.timeslot = slot
                    if pl["room"] is not None:
                        r.room = pl["room"]
                    if pl["teacher"] is not None:
                        r.teacher = pl["teacher"]
                    r.is_manual_override = True
                    r.save(update_fields=["timeslot", "room", "teacher", "is_manual_override"])
    except IntegrityError as _e:
        import logging; logging.getLogger(__name__).warning('reschedule integrity error: %s', _e)
        # someone booked the same teacher / room a moment ago: nothing was saved; show the fresh picture
        fresh = _evaluate(plans)
        gen = "That time was just taken by another change. Pick one of the free times."
        return Response({"detail": gen, "day": plans[0]["day"],
                         "conflicts": [_payload(pl, m or [gen], o) for pl, m, o in fresh]}, status=status.HTTP_409_CONFLICT)

    override = str(d.get("override_workload", "")).lower() in ("1", "true", "yes")
    logs = []
    for pl in plans:
        r0 = pl["rows"][0]
        logs.append(Log(action="UPDATE", schedule_id=r0.id, user=user,
                        details=f"Moved {r0.subject.title} ({r0.section}) to {pl['day']} {_label(pl['start'])}"))
        if override and pl["teacher"] is not None:
            logs.append(Log(action="UPDATE", schedule_id=r0.id, user=user,
                            details=f"WORKLOAD OVERRIDE: {pl['teacher'].user.get_full_name()} assigned {r0.subject.title}"))
    Log.objects.bulk_create(logs)
    return Response({"moved": sum(len(pl["rows"]) for pl in plans), "classes": len(plans)})


def _classes_of(profile, user):
    rows = Schedule.objects.filter(teacher=profile).select_related(
        "subject", "subject__field", "subject__program", "section__program", "timeslot", "room")
    groups = defaultdict(list)
    for r in rows:
        if not _can_edit(user, r):
            continue
        groups[(r.subject_id, r.section_id, r.term, r.merge_key or "")].append(r)
    return list(groups.values())


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def teacher_replacements(request):
    """?faculty_id=<teacher who is leaving / unavailable>  ->  each of their classes with ranked replacements."""
    from . import workload as wl
    user = request.user
    if not (user.role == "registrar" or (user.role == "faculty" and user.faculty_type == "dean")):
        return Response({"detail": "Only a Dean or the Registrar can look up replacements."}, status=403)
    profile = FacultyProfile.objects.select_related("user").filter(pk=request.query_params.get("faculty_id")).first()
    if profile is None:
        return Response({"detail": "Faculty not found."}, status=404)
    out = []
    for rows in _classes_of(profile, user):
        r0 = rows[0]
        diag = {}
        sugg = wl.suggest_replacements(r0.subject, r0.term, [r.timeslot for r in rows], exclude_teacher_ids=[profile.id],
                                       school_year=r0.school_year, limit=6, diag=diag, user=user, section=r0.section)
        days = sorted({r.timeslot.day for r in rows})
        out.append({
            "subject_id": r0.subject_id, "section_id": r0.section_id, "term": r0.term, "merge_key": r0.merge_key,
            "schedule_ids": [r.id for r in rows], "subject": r0.subject.title, "code": r0.subject.code,
            "section": f"{r0.section.program.name} {r0.section.name}",
            "when": ", ".join(f"{r.timeslot.day} {_label(_min(r.timeslot.start_time))}-{_label(_min(r.timeslot.end_time))}"
                              for r in sorted(rows, key=lambda x: (x.timeslot.day, x.timeslot.start_time))),
            "required_field": r0.subject.field.name if r0.subject.field_id else "",
            "hours": round(sum((_min(r.timeslot.end_time) - _min(r.timeslot.start_time)) / 60 for r in rows), 2),
            "suggestions": sugg, "reason_none": "" if sugg else wl.no_available_text(diag),
        })
    out.sort(key=lambda c: c["subject"])
    return Response({"faculty": {"id": profile.id, "full_name": profile.user.get_full_name() or profile.user.username,
                                 "school_id": profile.user.school_id},
                     "classes": out})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def assign_replacement(request):
    """body: {schedule_ids:[..], teacher:<FacultyProfile id>, override_workload?:bool}"""
    from . import workload as wl
    user = request.user
    if not (user.role == "registrar" or (user.role == "faculty" and user.faculty_type == "dean")):
        return Response({"detail": "Only a Dean or the Registrar can reassign classes."}, status=403)
    rows = list(Schedule.objects.filter(pk__in=request.data.get("schedule_ids") or []).select_related(
        "subject", "section__program", "timeslot"))
    teacher = FacultyProfile.objects.select_related("user").filter(pk=request.data.get("teacher")).first()
    if not rows or teacher is None:
        return Response({"detail": "Class or teacher not found."}, status=404)
    for r in rows:
        if not _can_edit(user, r):
            return Response({"detail": f"You are not allowed to change {r.subject.title}."}, status=403)
    from .teacher_scope import teacher_allowed           # department + qualification (this endpoint had no such check before)
    _why = teacher_allowed(user, teacher, rows[0].subject, rows[0].section)
    if _why:
        return Response({"detail": _why}, status=400)
    for r in rows:
        msgs = find_conflicts(teacher=teacher, timeslot=r.timeslot, exclude_model="Schedule", exclude_pk=r.pk,
                              merge_key=r.merge_key, semester=r.section.semester)
        if msgs:
            return Response({"detail": f"{teacher.user.get_full_name()} is not free: {msgs[0]}"}, status=400)
    term = rows[0].term
    over = wl.check_assignment(teacher, term, [r.timeslot for r in rows], [r.id for r in rows])
    flag = str(request.data.get("override_workload", "")).lower() in ("1", "true", "yes")
    policy = wl.limits()["policy"]
    if over and not (flag and policy != "strict"):
        return Response({"detail": over["message"], "workload_overload": over, "can_override": policy != "strict"}, status=409)
    with transaction.atomic():
        for r in rows:
            r.teacher = teacher
            r.is_manual_override = True
            r.save(update_fields=["teacher", "is_manual_override"])
    return Response({"updated": len(rows), "teacher": teacher.user.get_full_name()})
