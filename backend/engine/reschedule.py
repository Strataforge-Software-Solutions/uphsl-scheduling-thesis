"""Smart Resolve: the days and times a class can move to (or be placed at) WITHOUT changing its room.

suggest()  lists only options that pass every rule at this moment: the teacher is qualified (already the class's teacher, or chosen by
           the same qualification rule as the generator), submitted availability allows the time, neither the teacher, the room nor
           the section's students are booked, and a new placement keeps the teacher inside the weekly limit. The room is NEVER
           switched: a class that already has a room keeps it; a class with none uses the subject's preferred room (the Dean's room
           assignment or the room picked in the preview) and only when there is no such room is the best suitable free room named.
apply()    re-derives the options on the server, checks the chosen one is still among them, then inside a database lock changes only
           this class, re-checks every clash on what was saved and rolls everything back if anything is wrong.
Nothing else is moved: no other class, no other room."""
from collections import defaultdict

from django.db import transaction

from . import scheduler as S
from . import workload as wl
from .conflict_report import scan
from .conflicts import class_tolerance_minutes, find_conflicts
from .models import ConflictLog, Log, Schedule, TimeSlot
from .placement import _can_edit, _mins

DAY_ORDER = {d: i for i, d in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))}
MAX_OPTIONS = 20
PER_DAY = 4          # the short list shows a few times on each day so the Dean has real choice of DAY


class RescheduleError(Exception):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra or {}


def _fmt(m):
    h, mm = divmod(int(m), 60)
    return f"{((h + 11) % 12) + 1}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def _owns(user, subject, section):
    role = getattr(user, "role", "")
    minor = subject.classification == "minor"
    if role == "registrar":
        return minor
    if role == "faculty" and getattr(user, "faculty_type", "") == "dean":
        return (not minor) and section.program.department in (user.departments or [])
    return False


def _minutes_of(h):
    return int(round(float(h) * 60)) * (2 if isinstance(h, S.PairHours) else 1)


def _runs(rows):
    """Rows of one class -> back-to-back runs on one day (a block)."""
    rows = sorted(rows, key=lambda r: (DAY_ORDER.get(r.timeslot.day[:3], 9), _mins(r.timeslot.start_time)))
    out = []
    for r in rows:
        if out and out[-1][-1].timeslot.day == r.timeslot.day and _mins(out[-1][-1].timeslot.end_time) == _mins(r.timeslot.start_time) \
                and out[-1][-1].room_id == r.room_id and out[-1][-1].teacher_id == r.teacher_id:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def _when(rows):
    parts = []
    for run in _runs(rows):
        parts.append(f"{run[0].timeslot.day[:3]} {_fmt(_mins(run[0].timeslot.start_time))}–{_fmt(_mins(run[-1].timeslot.end_time))}")
    return "; ".join(parts)


def _class_info(subject, section, rows):
    return {"subject_id": subject.id, "code": subject.code, "title": subject.title, "section_id": section.id,
            "section": f"{section.program.name} {section.name}", "year_level": section.year_level, "semester": section.semester,
            "room": rows[0].room.name if rows else "", "when": _when(rows) if rows else "",
            "teacher": (rows[0].teacher.user.get_full_name().strip() or rows[0].teacher.user.username) if rows else ""}


def _load(ids, section_id, subject_id):
    from .models import Section
    from curriculum.models import Subject
    if ids:
        rows = list(Schedule.objects.filter(pk__in=ids).select_related("subject__program", "section__program", "timeslot", "room", "teacher__user"))
        if not rows or len(rows) != len(set(ids)):
            raise RescheduleError("That class was changed or removed. Reload the schedule and try again.", 409)
        if len({(r.section_id, r.subject_id) for r in rows}) != 1:
            raise RescheduleError("These periods belong to different classes.", 400)
        return rows[0].section, rows[0].subject, rows, "move"
    section = Section.objects.select_related("program").filter(pk=section_id).first()
    subject = Subject.objects.select_related("program", "field").filter(pk=subject_id).first()
    if section is None or subject is None:
        raise RescheduleError("Class not found.", 404)
    rows = list(Schedule.objects.filter(section=section, subject=subject, term=section.semester)
                .select_related("subject__program", "section__program", "timeslot", "room", "teacher__user"))
    return section, subject, rows, "place"


def suggest(user, *, ids=None, section_id=None, subject_id=None, room_id=None, school_year="", limit=MAX_OPTIONS, _full=False, window=None, _rooms=None, _inner=False):
    from rooms import rules as rr
    from rooms.models import Room
    from faculty.models import FacultyProfile
    from .views import _build_availability_rules
    section, subject, rows, mode = _load(ids, section_id, subject_id)
    if not _owns(user, subject, section):
        raise RescheduleError("This class belongs to another owner. Only its own Dean (program subjects) or the Registrar (Gen Ed) can move it.", 403)
    if any(not _can_edit(user, r) for r in rows):
        raise RescheduleError("This class cannot be moved from here: it is approved / published, or shared with other sections. "
                              "Move it back to draft first.", 403)
    term = section.semester
    expected = list(S.blocks_for_subject(subject))
    # ---- which block is being moved / placed
    if mode == "move":
        total = sum(_mins(r.timeslot.end_time) - _mins(r.timeslot.start_time) for r in rows)
        hours = next((h for h in expected if _minutes_of(h) == total), None)
        if hours is None:
            hours = next((h for h in expected if isinstance(h, S.PairHours) and _minutes_of(h) == total), None)
        if hours is None:
            hours = total / 60.0
        skip_ids = {r.id for r in rows}
        teacher_rows = rows
    else:
        left = list(expected)
        for run in _runs(rows):
            m = sum(_mins(r.timeslot.end_time) - _mins(r.timeslot.start_time) for r in run)
            hit = next((h for h in left if _minutes_of(h) == m), None)
            if hit is not None:
                left.remove(hit)
        if not left:
            raise RescheduleError("This class is already placed (all of its periods are in the schedule), so there is nothing left to resolve. "
                                  "The list is out of date and will be refreshed.", 409, {"already_placed": True})
        hours = sorted(left, key=lambda h: -float(h))[0]
        skip_ids = set()
        teacher_rows = rows
    # ---- fixed teacher / room for the class
    teacher = teacher_rows[0].teacher if teacher_rows else None
    room = rows[0].room if rows else None
    asg = rr.load_assignments({subject.id}).get(subject.id)
    all_rooms = list(Room.objects.all())
    gym = any(getattr(r, "room_type", "") == "gym" for r in all_rooms)
    room_note = ""
    dept = section.program.department
    major = subject.classification != "minor"
    designated = rr.designated_rooms(all_rooms, dept) if major else None
    if room is not None:
        candidate_rooms = [room]
    else:
        pick = next((r for r in all_rooms if r.id == room_id), None) if room_id else None
        pref = next((r for r in all_rooms if asg and r.id == asg.get("preferred")), None)
        base = pick or pref
        if base is not None and designated is not None and base.id not in {d.id for d in designated}:
            raise RescheduleError(rr.designated_message(subject, dept, all_rooms), 422)
        if base is not None:
            candidate_rooms = [base]
            room = base
        else:
            comp = [r for r in all_rooms if S._room_matches_subject(r, subject, gym)]
            comp = rr.allowed_rooms(comp, section.program.department, lab_subject=subject.lab_units > 0, major=subject.classification != "minor")
            size = rr.effective_size(section, subject)
            fit = [r for r in comp if not (size and (r.capacity or 0) and r.capacity < size)]
            candidate_rooms = fit or comp
            if designated is not None:
                candidate_rooms = [r for r in candidate_rooms if r.id in {d.id for d in designated}] or designated
            room_note = "This class has no room yet, so the best suitable free room is offered with each time."
    if _rooms:
        candidate_rooms = list(_rooms)
    if room is not None:
        gym_ok = S._room_matches_subject(room, subject, gym) or rows
        if not gym_ok:
            raise RescheduleError(f"{room.name} is not a suitable room for {subject.code}.", 422)
        size = rr.effective_size(section, subject)
        if size and (room.capacity or 0) and room.capacity < size and not rows:
            raise RescheduleError(f"{room.name} seats {room.capacity}, fewer than the {size} students of this section.", 422)
    # ---- teachers
    teachers_all = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(user__is_active=True))
    if teacher is None:
        # the Lec / Lab partner of this section already has a teacher: one teacher teaches both parts
        partner = next((p for p in Schedule.objects.filter(section=section, term=term).select_related("subject", "teacher__user")
                        if S._is_lab_of(subject, p.subject) or S._is_lab_of(p.subject, subject)), None)
        if partner is not None:
            teacher = partner.teacher
    if teacher is not None:
        teachers = [teacher]
    else:
        spec = {t.id: {f.id for f in t.specializations.all()} for t in teachers_all}
        from .qualification import qualified_teachers, why_nobody
        teachers = qualified_teachers(subject, section, teachers_all, spec)
        if not teachers:
            from .workload import _qualification_match
            near = []
            for t in teachers_all:
                pts, why = _qualification_match(subject, t)
                if pts and (not major or dept in (t.user.departments or [])):
                    near.append((pts, t, why))
            near.sort(key=lambda x: -x[0])
            raise RescheduleError(why_nobody(subject, section, teachers_all, spec), 422, {"replacements": [
                {"faculty_id": t.id, "name": t.user.get_full_name().strip() or t.user.username, "department": t.user.department or "",
                 "fit": "; ".join(w) + " (not yet a recorded specialization: the Dean can add it in the Faculty tab)"} for _p, t, w in near[:5]]})
    timeslots = list(TimeSlot.objects.all())
    rules = _build_availability_rules(teachers, timeslots, school_year or (rows[0].school_year if rows else None), term or None)
    blocks = S.with_half_blocks(S.build_block_slots(timeslots, hours), window)
    if window:               # the Start / End Time the Dean chose for this subject stays a hard limit
        blocks = [b for b in blocks if window[0] <= _mins(b.start_time) and _mins(b.end_time) <= window[1]]
    # ---- what is already booked (everything except the class being moved)
    tol = class_tolerance_minutes()
    t_ids, r_ids = {t.id for t in teachers}, {r.id for r in candidate_rooms}
    from django.db.models import Q
    booked = Schedule.objects.filter(term=term).exclude(pk__in=skip_ids).filter(
        Q(teacher_id__in=t_ids) | Q(room_id__in=r_ids) | Q(section_id=section.id)).select_related("timeslot")
    by_t, by_r, by_s = defaultdict(list), defaultdict(list), defaultdict(list)
    day_load = defaultdict(int)
    for b in booked:
        iv = (b.timeslot.day[:3], _mins(b.timeslot.start_time), _mins(b.timeslot.end_time))
        if b.merge_key and rows and b.merge_key == rows[0].merge_key:
            continue
        by_t[b.teacher_id].append(iv); by_r[b.room_id].append(iv)
        if b.section_id == section.id:
            by_s[0].append(iv)
            day_load[iv[0]] += iv[2] - iv[1]

    def overlap(ivs, day, s, e):
        return sum(max(0, min(e, ie) - max(s, is_)) for d, is_, ie in ivs if d == day)

    counts = {"possible": 0, "teacher_unavailable": 0, "teacher_busy": 0, "room_busy": 0, "students_busy": 0, "teacher_overload": 0, "same_place": 0,
              "lec_lab_order": 0}
    from . import lecorder
    order = lecorder.bounds(subject, section.id, term, exclude_ids=skip_ids)      # Lecture before Lab (the solver's rule)
    cur_key = tuple(sorted(r.timeslot_id for r in rows)) if mode == "move" else None
    found = []
    for blk in blocks:
        real = list(blk.slots)
        key_slots = tuple(sorted(sl.id for sl in real))
        if cur_key is not None and key_slots == cur_key:
            counts["same_place"] += 1
            continue
        counts["possible"] += 1
        ivs = [(sl.day[:3], _mins(sl.start_time), _mins(sl.end_time)) for sl in real]
        if lecorder.violates(order, ivs):
            counts["lec_lab_order"] += 1
            continue
        ok_t = [t for t in teachers if not any(sl.id in rules.get(t.id, set()) for sl in real)]
        if not ok_t:
            counts["teacher_unavailable"] += 1
            continue
        free_t = [t for t in ok_t if not any(overlap(by_t[t.id], d, s, e) > 0 for d, s, e in ivs)]
        if not free_t:
            counts["teacher_busy"] += 1
            continue
        free_r = [r for r in candidate_rooms if not any(overlap(by_r[r.id], d, s, e) > 0 for d, s, e in ivs)]
        if not free_r:
            counts["room_busy"] += 1
            continue
        if sum(overlap(by_s[0], d, s, e) for d, s, e in ivs) > tol:
            counts["students_busy"] += 1
            continue
        load = sum(day_load[d] for d, _s, _e in ivs[:1])
        found.append((load, DAY_ORDER.get(ivs[0][0], 9), ivs[0][1], blk, real, free_t, free_r))
    found.sort(key=lambda x: (x[0], x[1], x[2]))
    options = []
    per_day = defaultdict(int)
    hours_by_t = wl.hours_by_teacher_term([t.id for t in teachers]) if mode == "place" and len(teachers) > 1 else {}
    for load, di, start, blk, real, free_t, free_r in found:
        if limit < 100 and not _full and per_day[real[0].day[:3]] >= PER_DAY:
            continue
        t = free_t[0]
        if mode == "place":
            order = sorted(free_t, key=lambda x: hours_by_t[x.id][term] if x.id in hours_by_t else 0)
            t = None
            for cand in order[:6]:
                if wl.check_assignment(cand, term, real, []) is None:
                    t = cand
                    break
            if t is None:
                counts["teacher_overload"] += 1
                continue
        r = free_r[0] if len(free_r) == 1 or room is not None else sorted(free_r, key=lambda x: (S._room_preference(x, section, subject, {}), x.id))[0]
        days = sorted({sl.day[:3] for sl in real}, key=lambda d: DAY_ORDER.get(d, 9))
        s0, e0 = _mins(real[0].start_time), _mins(real[-1].end_time)
        if len(days) == 1:
            label = f"{days[0]} {_fmt(s0)} – {_fmt(e0)}"
        else:
            first = [sl for sl in real if sl.day[:3] == days[0]]
            label = f"{' & '.join(days)} {_fmt(_mins(first[0].start_time))} – {_fmt(_mins(first[-1].end_time))}"
        options.append({"key": f"{t.id}:{r.id}:{'-'.join(str(i) for i in sorted(sl.id for sl in real))}", "slot_ids": [sl.id for sl in real],
                        "day": days[0], "days": days, "start": f"{s0 // 60:02d}:{s0 % 60:02d}", "end": f"{e0 // 60:02d}:{e0 % 60:02d}", "label": label,
                        "teacher_id": t.id, "teacher": t.user.get_full_name().strip() or t.user.username, "room_id": r.id, "room": r.name})
        per_day[days[0]] += 1
        if not _full and len(options) >= limit:
            break
    who = (teacher.user.get_full_name().strip() or teacher.user.username) if teacher else "a qualified teacher"
    reason = ""
    if not options:
        rn = room.name if room is not None else "a suitable room"
        bits = []
        if counts["teacher_unavailable"]:
            bits.append(f"{counts['teacher_unavailable']} are outside {who}'s submitted availability")
        if counts["teacher_busy"]:
            bits.append(f"{counts['teacher_busy']} overlap {who}'s other classes")
        if counts["room_busy"]:
            bits.append(f"{counts['room_busy']} find {rn} already booked")
        if counts["students_busy"]:
            bits.append(f"{counts['students_busy']} clash with the section's other classes")
        if counts["lec_lab_order"]:
            bits.append(f"{counts['lec_lab_order']} would put the Lab before its Lecture ({lecorder.message(order, subject)})")
        if counts["teacher_overload"]:
            bits.append(f"{counts['teacher_overload']} would push the teacher over the weekly limit")
        reason = (f"No other day or time works while keeping {rn}" + (f" and {who}" if teacher else "") + f". Of {counts['possible']} possible "
                  f"period(s), " + ("; ".join(bits) if bits else "none are free") + ".")
        if not counts["possible"]:
            reason = f"There is no {float(hours):g}-hour period in the time-slot table to move to. Check Settings > Time slots."
    outside, room_options = [], []
    asg_fixed = bool(asg and asg.get("fixed"))
    may_change_room = bool(room is not None and not _inner and (not major or (designated is None and not asg_fixed)))
    if not options and not _inner:
        kw = dict(ids=ids, section_id=section_id, subject_id=subject_id, room_id=room_id, school_year=school_year, limit=limit, _full=_full, _inner=True)
        if window:
            # step 3: the window the Dean chose has no free time in this room -> other times in the SAME room
            outside = suggest(user, window=None, **kw)["options"]
            if outside:
                reason = ("No day works inside the Start / End Time you chose while keeping " + (room.name if room else "the room") +
                          ". These times outside it are free in the same room (each is checked against the teacher, the room and the students).")
        if not outside and may_change_room:
            # step 4: only when the subject permits a room change, name the other free rooms (the Dean / Registrar must choose and confirm)
            alts = [r for r in all_rooms if r.id != room.id and S._room_matches_subject(r, subject, gym)]
            alts = rr.allowed_rooms(alts, dept, lab_subject=subject.lab_units > 0, major=major)
            size = rr.effective_size(section, subject)
            alts = [r for r in alts if not (size and (r.capacity or 0) and r.capacity < size) and not (rr.is_owned_lab(r) and subject.lab_units == 0)]
            alts.sort(key=lambda r: (S._room_preference(r, section, subject, {}), r.id))
            for r in alts[:8]:
                got = suggest(user, window=window, _rooms=[r], **kw)["options"]
                for o in got[:3]:
                    o["room_changed"] = True
                room_options += got[:3]
            if room_options:
                reason += (" " if reason else "") + (f"{room.name} has no free time that works, and this subject may use another room. "
                                                       "These rooms are free (choose one and confirm; nothing changes until you do).")
        elif not outside and room is not None and major and designated is not None:
            reason += f" {subject.code} must stay in the department's designated rooms ({', '.join(sorted(d.name for d in designated))}); no ordinary lecture room is offered."
    if not _inner and not (options or outside or room_options) and counts["possible"]:
        reason += (" The other rooms this subject may use were checked as well and none is free at a time that works." if may_change_room else
                   " This subject keeps its room, so no other room was tried.") + " The conflict stays active and nothing was changed."
    return {"mode": mode, "class": _class_info(subject, section, rows), "room": {"id": room.id if room else None, "name": room.name if room else "",
            "kept": bool(rows) or room is not None, "note": room_note}, "hours": float(hours), "options": options, "checked": counts,
            "outside_options": outside, "room_options": room_options, "room_change_allowed": may_change_room,
            "reason": reason, "can_apply": bool(options or outside or room_options)}


def apply(user, *, key, ids=None, section_id=None, subject_id=None, room_id=None, school_year="", window=None):
    from . import locks
    from notifications.models import Notification
    res = suggest(user, ids=ids, section_id=section_id, subject_id=subject_id, room_id=room_id, school_year=school_year, _full=True, window=window)
    opt = next((o for o in res["options"] + res["outside_options"] + res["room_options"] if o["key"] == key), None)
    if opt is None:
        raise RescheduleError("That day and time is no longer available (something changed). The list has been refreshed. Pick another option.", 409,
                              {"refresh": True})
    section, subject, rows, mode = _load(ids, section_id, subject_id)
    from faculty.models import FacultyProfile
    from rooms.models import Room
    teacher = FacultyProfile.objects.select_related("user").get(pk=opt["teacher_id"])
    room = Room.objects.get(pk=opt["room_id"])
    slots = list(TimeSlot.objects.filter(pk__in=opt["slot_ids"]))
    term = section.semester
    year = school_year or (rows[0].school_year if rows else "") or Schedule.objects.filter(term=term).values_list("school_year", flat=True).first() or ""
    old_ids = [r.id for r in rows] if mode == "move" else []
    # "what changed", in words, for the confirmation note: "Mon 8:00 AM–9:00 AM → Tue 9:30 AM–10:30 AM, room stays 307D"
    old_when = _when(rows) if (mode == "move" and rows) else "not placed"
    old_room = rows[0].room if (mode == "move" and rows) else None
    old_teacher = rows[0].teacher if (mode == "move" and rows) else None
    with transaction.atomic():
        if not locks.try_lock("classes"):
            raise RescheduleError(locks.BUSY, 409)
        fresh = list(Schedule.objects.select_for_update().filter(pk__in=old_ids))
        if mode == "move" and (len(fresh) != len(old_ids) or any(f.status != "draft" for f in fresh)):
            raise RescheduleError("This class was changed by someone else. Reload and try again.", 409)
        Schedule.objects.filter(pk__in=old_ids).delete()
        for sl in slots:
            msgs = find_conflicts(teacher=teacher, room=room, section=section, timeslot=sl, semester=term)
            if msgs:
                transaction.set_rollback(True)
                raise RescheduleError(f"{sl.day[:3]} {_fmt(_mins(sl.start_time))} is no longer free: {msgs[0]} Nothing was changed.", 409)
        if mode == "place":
            over = wl.check_assignment(teacher, term, slots, [])
            if over:
                transaction.set_rollback(True)
                raise RescheduleError(over["message"], 409, {"workload_overload": over})
        made = Schedule.objects.bulk_create([Schedule(subject=subject, teacher=teacher, room=room, section=section, timeslot=sl, school_year=year,
                                                      status="draft", term=term, is_manual_override=True) for sl in slots])
        new_ids = [m.id for m in made if m.id is not None] or list(
            Schedule.objects.filter(section=section, subject=subject, term=term, timeslot__in=slots).values_list("id", flat=True))
        shared = []
        if mode == "place" and subject.classification == "minor" and subject.lab_units == 0:
            # a Gen Ed class placed here keeps the shared-class programs the Registrar chose: the confirmed members join the same time
            from . import shared_classes as sc
            members, _total = sc.plan_members(section, subject, sc.share_rules(section.year_level, term))
            if members:
                shared = sc.extend_to_members([(section, subject, members)], made, year)
                for m in shared:
                    new_ids += m["schedule_ids"]
        clashes = scan(semester=term, involving_ids=set(new_ids), limit=50)
        if clashes["total"]:
            transaction.set_rollback(True)
            raise RescheduleError("The saved change would create a scheduling conflict, so nothing was changed.", 409, {"conflicts": clashes["conflicts"][:5]})
        ConflictLog.objects.filter(section=section, conflict_type="unresolved_csp", description__contains=subject.code, resolved=False).update(resolved=True)
        Log.objects.create(action="UPDATE", schedule_id=new_ids[0] if new_ids else None, user=user,
                           details=f"Smart Resolve: {subject.code} ({section.name}) {'moved' if mode == 'move' else 'placed'} at {opt['label']} in {room.name}")
        if teacher.user_id != getattr(user, "id", None):
            Notification.objects.create(recipient=teacher.user, notif_type="schedule_update",
                                        message=f"{subject.code} ({section.program.name} {section.name}) is now {opt['label']} in {room.name}.")
    return {"ok": True, "mode": mode, "shared": [{k: v for k, v in m.items() if k != "schedule_ids"} for m in shared],
            "summary": f"{subject.code} — {section.program.name} {section.name} is now {opt['label']} in {room.name} "
            f"({teacher.user.get_full_name().strip() or teacher.user.username}). Room unchanged; no other class was moved.",
            "changes": (f"{old_when} → {opt['label']}, "
                        + (f"room stays {room.name}" if old_room is not None and old_room.id == room.id else
                           f"room {old_room.name} → {room.name}" if old_room is not None else f"room {room.name}")
                        + (f", teacher stays {teacher.user.get_full_name().strip() or teacher.user.username}"
                           if old_teacher is not None and old_teacher.id == teacher.id else
                           f", teacher {teacher.user.get_full_name().strip() or teacher.user.username}")),
            "new_ids": new_ids, "removed_ids": old_ids}
