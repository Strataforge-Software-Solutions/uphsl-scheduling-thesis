"""Why each candidate period of an UNPLACED class was refused, for the skip message only.

This never places or refuses anything: the Greedy search (scheduler.generate_schedule) has already decided. It only re-checks,
for a class whose Dean picked a Start / End range, every period of the needed length on the 30-minute grid inside that range,
day by day, and names the exact rule that rules each one out, so the message never blames the professor when the professor is
free and something else (a missing time slot, a booked lab, the section's other class) is the blocker.
"""
from .scheduler import BlockSlot, PairHours, _clock, _slot_minutes, _slots_overlap, _teacher_available, _DAY_INDEX

STEP = 30

# category order = which blocker is named first for a candidate (the first one that applies is the "main" blocker)
NO_PERIOD, SHARED, SECTION, AVAILABILITY, TEACHING, LIMIT, CAPACITY, ROOM = (
    "no time slot", "shared class", "section busy", "teacher availability", "teacher already teaching", "weekly hour limit",
    "room capacity", "room busy")
ORDER = (NO_PERIOD, SHARED, SECTION, AVAILABILITY, TEACHING, LIMIT, CAPACITY, ROOM)


def _name(t):
    return t.user.get_full_name().strip() or t.user.username


def _gap_text(day, a, b, timeslots):
    """Why no class period exists on `day` from a to b: the uncovered stretch of the time-slot table, or a run
    the table cannot form."""
    # the same slots the period builder uses (scheduler.build_block_slots): a period starting on the half hour is made of 30-minute
    # slots, one starting on the hour of hourly slots
    mine = [t for t in timeslots if t.day[:3].lower() == day[:3].lower()]
    unit = 60 if (a % 60 == 0 and (b - a) % 60 == 0) else STEP
    kind = [t for t in mine if (_slot_minutes(t.end_time) - _slot_minutes(t.start_time) == STEP) == (unit == STEP)]
    have = {(_slot_minutes(t.start_time), _slot_minutes(t.end_time)) for t in kind}
    holes = [m for m in range(a, b, unit) if (m, m + unit) not in have]
    if holes:
        lo, hi = holes[0], holes[-1] + unit
        return (f"there is no {'30-minute' if unit == STEP else 'hourly'} class time slot at {_clock(lo)}-{_clock(hi)} "
                "(add it: python manage.py seed_timeslots)")
    odd = sorted({(_slot_minutes(t.start_time), _slot_minutes(t.end_time)) for t in kind
                  if min(_slot_minutes(t.end_time), b) - max(_slot_minutes(t.start_time), a) > 0}
                 - {(m, m + unit) for m in range(a, b, unit)})
    if odd:
        many = len(odd) > 1
        return (f"the irregular time slot{'s' if many else ''} " + ", ".join(f"{day[:3].title()} {_clock(x)}-{_clock(y)}" for x, y in odd)
                + f" break{'' if many else 's'} this period up (check Settings > Time slots)")
    return "the time-slot table has no unbroken period here"


def candidates(window, need):
    a, b = window
    first = a + (-a) % STEP
    return [(s, s + need) for s in range(first, b - need + 1, STEP)]


def report(section, subject, hours, window, timeslots, blocks, assigned, teachers, rooms, availability_rules,
           chosen=None, caps=None, size=0, share_busy=None):
    """[{"day", "start", "end", "blockers": [(category, text), ...]}] for every candidate period inside `window` on every school day.
    `teachers`: the teachers that may take this block (the chosen professor / the Lec-Lab partner's teacher / every qualified one).
    `rooms`: the rooms the rules allow (designated labs for Computer Studies majors, a fixed room, ...). An empty `blockers` list
    means the period is free of every rule checked here (the class may still have failed on a rule this report does not cover)."""
    if isinstance(hours, PairHours):
        return None                                     # paired-day lectures (Nursing) are not reported per period
    need = int(round(float(hours) * 60))
    days = sorted({t.day for t in timeslots}, key=lambda d: _DAY_INDEX.get(d[:3].lower(), 99))
    caps_lim, caps_used = (caps or (None, None))
    caps_lim, caps_used = caps_lim or {}, caps_used or {}
    fit = [r for r in rooms if not ((getattr(r, "capacity", 0) or 0) and size and r.capacity < size)]
    out = []
    for day in days:
        for a, b in candidates(window, need):
            blk = next((x for x in blocks if x.day == day and _slot_minutes(x.start_time) == a and _slot_minutes(x.end_time) == b), None)
            if blk is None:            # the period does not exist: that is the whole reason (other clashes there would not matter)
                out.append({"day": day[:3].title(), "start": a, "end": b, "blockers": [(NO_PERIOD, _gap_text(day, a, b, timeslots))]})
                continue
            span = blk
            why = []
            if share_busy and any(k[0] == _DAY_INDEX.get(day[:3].lower()) and min(k[2], b) - max(k[1], a) > 0 for k in share_busy):
                why.append((SHARED, "a section that shares this class already has another class then"))
            over = [x for x in assigned if _slots_overlap(x.timeslot, span)]
            sec = sorted({x.subject.code for x in over if x.section.id == section.id})
            if sec:
                why.append((SECTION, f"{section.name} already has {', '.join(sec)}"))
            free_teachers = []
            for t in teachers:
                if blk is not None and not _teacher_available(t, blk, availability_rules):
                    if chosen is not None or len(teachers) == 1:
                        from . import availability as _av
                        why.append((AVAILABILITY, f"{_name(t)} is not available then"
                                    + (f" ({_av.text_for(t.id)})" if _av.text_for(t.id) else "")))
                    continue
                busy = sorted({f"{x.subject.code} ({x.section.name})" for x in over if x.teacher.id == t.id})
                if busy:
                    if chosen is not None or len(teachers) == 1:
                        why.append((TEACHING, f"{_name(t)} is already teaching {', '.join(busy)}"))
                    continue
                if t.id in caps_lim and caps_used.get(t.id, 0) + float(hours) > caps_lim[t.id] + 1e-9:
                    if chosen is not None or len(teachers) == 1:
                        why.append((LIMIT, f"{_name(t)} would go over the weekly limit of {caps_lim[t.id]:g} hours"))
                    continue
                free_teachers.append(t)
            if teachers and not free_teachers and not (chosen is not None or len(teachers) == 1):
                why.append((TEACHING, f"none of the {len(teachers)} qualified teachers is free (outside their availability, "
                                      "already teaching, or at their weekly limit)"))
            if rooms and not fit:
                why.append((CAPACITY, f"no allowed room seats {size} students"))
            elif fit:
                booked = {}
                for x in over:
                    if x.room.id in {r.id for r in fit}:
                        booked.setdefault(x.room.id, set()).add(f"{x.subject.code} ({x.section.name})")
                if all(r.id in booked for r in fit):
                    from rooms.rules import room_text
                    why.append((ROOM, "; ".join(f"{room_text(r)} has {', '.join(sorted(booked[r.id]))}" for r in fit)))
            why.sort(key=lambda w: ORDER.index(w[0]))
            out.append({"day": day[:3].title(), "start": a, "end": b, "blockers": why})
    return out


def summary(rep, hours, window, what="class", chosen_name="", designated=False, max_items=8):
    """Readable text from report(): one sentence per kind of blocker (in ORDER), each listing the periods it rules out with the class
    or room named; periods with the same text are merged ("Mon, Fri 10:30 AM-12:30 PM"). Every blocker of a period is listed, not
    only the first. "" when some period has no blocker (then the report cannot explain the skip and the caller keeps its message)."""
    if not rep or any(not c["blockers"] for c in rep):
        return ""
    by_cat = {}
    for c in rep:
        for cat, text in c["blockers"]:
            by_cat.setdefault(cat, {}).setdefault(text, []).append(c)
    sentences, shown, hidden = [], 0, 0
    for cat in ORDER:
        if cat not in by_cat:
            continue
        items = []
        for text, cs in by_cat[cat].items():
            per_day = {}
            for c in cs:
                per_day.setdefault(c["day"], []).append(f"{_clock(c['start'])}-{_clock(c['end'])}")
            merged = {}
            for d, ts in per_day.items():
                merged.setdefault(tuple(ts), []).append(d)
            where = "; ".join(f"{', '.join(ds)} {' and '.join(ts)}" for ts, ds in merged.items())
            if cat == ROOM and designated:
                text += " (Computer Studies majors use Comp Lab C / D only)"
            items.append(f"{where}: {text}")
        keep = items[:max(1, max_items - shown)]
        hidden += len(items) - len(keep)
        shown += len(keep)
        sentences.append(". ".join(keep))
    head = (f"No {float(hours):g}-hour {what} period inside your {_clock(window[0])}-{_clock(window[1])} range can be used"
            + (f" with {chosen_name} (your chosen professor)" if chosen_name else "") + ". ")
    return head + ". ".join(sentences) + "." + (f" ({hidden} more not listed.)" if hidden else "")
