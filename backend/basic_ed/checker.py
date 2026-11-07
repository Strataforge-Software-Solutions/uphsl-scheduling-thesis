"""Independent check of a generated SHS / JHS timetable against every hard rule (used by the tests and the comparison command).

check(P, assignments) -> list of plain-language violations (empty = the timetable keeps every rule):
  * one class at a time per section, teacher and room (also against other grades' timetables)
  * a qualified teacher (or the one the Principal pinned / the homeroom adviser), inside their availability
  * the weekly hours limit and the daily period limit
  * a period of the grade's daily schedule (never on a break), a room of the right type and size of this level
  * every subject: all its periods, one teacher, at most 2 a day
  * Grade 11 whole-year subjects: exactly the other term's day, time, teacher and room
"""
from collections import defaultdict

from .engine import _free_for_teacher, eligible


def check(P, assignments):
    out = []
    grid = set(P.grids.get(P.grade_level, []))
    rooms = {r.id: r for r in P.rooms}
    cap_day = P.config.max_periods_per_teacher_day
    seen_sec, seen_t, seen_r = {}, {}, {}
    minutes = defaultdict(int, P.teacher_minutes)
    per_day = defaultdict(int)
    by_task = defaultdict(list)
    for a in assignments:
        sec, sub, fac, room, day, s, e = a["section"], a["subject"], a["teacher"], a["room"], a["day"], a["start"], a["end"]
        where = f"{sub.code} {sec.name} {day} {s // 60}:{s % 60:02d}"
        key = (day, s)
        if (s, e) not in grid:
            out.append(f"{where}: not a class period of the grade's schedule (break or outside the day)")
        for store, k, what in ((seen_sec, (sec.id, key), "section"), (seen_t, (fac.id, key), "teacher"),
                               (seen_r, (P.canon(room.id), key), "room")):
            if k in store:
                out.append(f"{where}: {what} double-booked (also {store[k]})")
            store[k] = where
        if key in P.busy_teacher[fac.id]:
            out.append(f"{where}: {fac.full_name} already teaches then in another grade's timetable")
        if key in P.busy_room[P.canon(room.id)]:
            out.append(f"{where}: room {room.name} is used then by another timetable")
        pin = P.pinned.get((sec.id, sub.id)) or (sec.adviser if sub.category == "guidance" and sec.adviser_id else None)
        if not (eligible(fac, sub) or (pin is not None and pin.id == fac.id)):
            out.append(f"{where}: {fac.full_name} is not qualified for {sub.code}")
        if not _free_for_teacher(P, fac, day, (s, e), defaultdict(set)):
            out.append(f"{where}: outside {fac.full_name}'s availability")
        if room.id not in rooms and P.canon(room.id) not in {P.canon(r) for r in rooms}:
            out.append(f"{where}: room {room.name} is not a room of this level")
        if room.room_type != sub.required_room_type:
            out.append(f"{where}: needs a {sub.required_room_type} but is in {room.room_type}")
        if room.capacity < sec.student_count:
            out.append(f"{where}: room {room.name} seats {room.capacity}, the section has {sec.student_count}")
        minutes[fac.id] += e - s
        per_day[(fac.id, day)] += 1
        by_task[(sec.id, sub.id)].append(a)
    for f in P.faculty:
        cap = (f.max_weekly_hours or P.config.max_teacher_hours) * 60
        if minutes[f.id] > cap:
            out.append(f"{f.full_name}: {minutes[f.id] / 60:.1f} h a week, over the limit of {cap / 60:g} h")
    for (fid, day), n in per_day.items():
        if n > cap_day:
            out.append(f"teacher #{fid} has {n} periods on {day}, over the daily limit of {cap_day}")
    for (sid, subid), rows in by_task.items():
        sub, sec = rows[0]["subject"], rows[0]["section"]
        if len(rows) != sub.sessions_per_week:
            out.append(f"{sub.code} {sec.name}: {len(rows)} of {sub.sessions_per_week} periods (a subject is placed whole or not at all)")
        if len({r["teacher"].id for r in rows}) > 1:
            out.append(f"{sub.code} {sec.name}: more than one teacher")
        days = defaultdict(int)
        for r in rows:
            days[r["day"]] += 1
        if any(n > 2 for n in days.values()):
            out.append(f"{sub.code} {sec.name}: more than 2 periods on one day")
    # Grade 11 whole-year subjects repeat the other term exactly
    src = defaultdict(set)
    for e in getattr(P, "anchor", []):
        if e.teacher_id and e.room_id:
            src[(e.section_id, e.subject_id)].add((e.day, e.start_time.hour * 60 + e.start_time.minute, e.teacher_id, P.canon(e.room_id)))
    for k, want in src.items():
        rows = by_task.get(k)
        if not rows:
            continue
        got = {(r["day"], r["start"], r["teacher"].id, P.canon(r["room"].id)) for r in rows}
        if not want <= got:
            out.append(f"{rows[0]['subject'].code} {rows[0]['section'].name}: a Grade 11 whole-year subject does not repeat the other term's "
                       "day, time, teacher and room")
    return out
