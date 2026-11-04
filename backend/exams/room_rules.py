"""
Which rooms an EXAM may use (GTI class program + the Registrar's/Deans' room rules). The result is an ordered list: the generator takes
the first room that is free at the chosen date and hour. `hard` means no other room may ever be used for that exam.

  Computer Studies lab subjects ....... Comp Lab C / Comp Lab D only (hard) -- lecture AND laboratory subjects both get an exam.
  Other departments' lab subjects ..... their own laboratories first (Nursing: Nursing Arts 4FA/4FB/7F, Chem Lab, Zoo Lab, then the
                                         other Nursing labs), then lecture rooms if every lab is taken.
  Minor (Gen Ed) subjects ............. the rooms of the real Prelim exam history (HISTORY_MINOR_ROOMS), Main Building floors 1-3, Alta (D) floor 3 (never a laboratory) and New Building (N) floors 2-3.
                                         Those three groups take turns, so the exams are spread over the buildings. A Nursing minor lab
                                         subject uses Chem Lab / Zoo Lab / Nursing Arts. Other rooms are only a last resort.
  Major lecture subjects .............. the department's rooms as in the class program; a department laboratory only as a last resort,
                                         so the labs stay free for lab exams.
Room ownership (a room reserved to another department) and capacity always apply (rooms.rules.allowed_rooms / fits_size).
"""
from rooms import rules as rr

# Rooms the real "1st Sem Prelim Exam 2026-2027" schedule used for Gen Ed (minor) exams, by building -> room numbers.
# They are tried first (Main building 301/304/305/306/307/501, Alta 203/206/301/302/308/401, New Building 201/301/601).
HISTORY_MINOR_ROOMS = {"M": ("301", "304", "305", "306", "307", "501"),
                       "D": ("203", "206", "301", "302", "308", "401"),
                       "N": ("201", "301", "601")}

COMP_LAB_KEYS = ("complabc", "complabd", "labc", "labd")


def _key(room):
    return rr.norm(getattr(room, "name", "")).replace(" ", "").replace("-", "")


def _is_lab(room):
    return getattr(room, "room_type", "") == "lab"


def _bld(room):
    return (getattr(room, "building", "") or "").upper()


def _floor(room):
    return rr.floor_of(room)


def _is_comp_lab(room):
    return _is_lab(room) and _key(room) in COMP_LAB_KEYS


def is_computer_studies(section):
    return "comput" in (getattr(section.program, "department", "") or "").lower()


def is_nursing(section):
    d = (getattr(section.program, "department", "") or "").lower()
    n = (getattr(section.program, "name", "") or "").lower()
    return "nurs" in d or "nurs" in n


def _nursing_arts(r):
    return "narts" in _key(r) or "nursingarts" in _key(r)


def _chem_zoo(r):
    return any(k in _key(r) for k in ("chemlab", "zoolab", "zoologylab", "chemistrylab"))


def _interleave(groups, start):
    """Take rooms from each group in turn (starting with group `start`) so the load is spread over all of them."""
    groups = [list(g) for g in groups if g]
    if not groups:
        return []
    start %= len(groups)
    groups = groups[start:] + groups[:start]
    out, i = [], 0
    while any(groups):
        g = groups[i % len(groups)]
        if g:
            out.append(g.pop(0))
        i += 1
    return out


def exam_rooms(rooms, section, subject, pref_key, turn=0):
    """Ordered rooms for this subject's exam. pref_key(room) -> sort key (the class scheduler's room preference).
    Returns (rooms, hard, n_preferred): the first n_preferred rooms are tried over the whole exam week before any other room."""
    dept = getattr(section.program, "department", None)
    minor = subject.classification == "minor"
    lab_subj = (subject.lab_units or 0) > 0
    allowed = rr.allowed_rooms(rooms, dept, lab_subject=False, major=True)          # ownership only (no lab narrowing here)
    allowed = [r for r in allowed if rr.may_use(r, dept)]
    fit = lambda r: rr.fits_size(r, section)
    srt = lambda lst: sorted(lst, key=lambda r: (not fit(r), pref_key(r), r.id))
    lecture = [r for r in allowed if not _is_lab(r)]
    own_labs = [r for r in allowed if _is_lab(r) and getattr(r, "department", None) and rr.norm(r.department) == rr.norm(dept)]
    free_labs = [r for r in allowed if _is_lab(r) and not getattr(r, "department", None)]

    # ---- laboratory subjects ---------------------------------------------------------------------------------------------------
    if lab_subj:
        if is_computer_studies(section):
            labs = [r for r in own_labs if _is_comp_lab(r)] or own_labs
            labs = srt(labs)
            return labs, True, len(labs)                     # LAB C / LAB D, always
        if is_nursing(section):
            arts = [r for r in own_labs if _nursing_arts(r)]
            chem = [r for r in free_labs + own_labs if _chem_zoo(r)]
            rest = [r for r in own_labs if r not in arts and r not in chem]
            first = (chem + arts) if minor else (arts + chem)
            seen, order = set(), []
            for r in srt(first) + srt(rest):
                if r.id not in seen:
                    seen.add(r.id); order.append(r)
            return order + _minor_lecture_rooms(lecture, srt, turn, minor), False, len(order)
        if own_labs:
            return srt(own_labs) + _minor_lecture_rooms(lecture, srt, turn, minor), False, len(own_labs)
        # a lab subject of a department with no laboratory of its own (e.g. a minor science lab)
        fl = srt(free_labs)
        return fl + _minor_lecture_rooms(lecture, srt, turn, minor), False, len(fl) + (len(_tier_rooms(lecture, turn, srt)) if minor else 0)

    # ---- lecture subjects ------------------------------------------------------------------------------------------------------
    if minor:
        rooms_ = _minor_lecture_rooms(lecture, srt, turn, True)
        npref = len(_tier_rooms(lecture, turn, srt))
        if is_nursing(section):                              # a Nursing Gen Ed class may use the Nursing labs when nothing else is free
            rooms_ += srt(own_labs + [r for r in free_labs if _chem_zoo(r)])
        return rooms_, False, npref
    plain = [r for r in allowed if not (_is_lab(r) and getattr(r, "department", None))]     # keep department labs free for lab exams
    labs_last = [r for r in allowed if _is_lab(r) and getattr(r, "department", None)]
    return srt(plain) + srt(labs_last), False, len(plain)


def _in_history(room):
    return (getattr(room, "room_number", "") or "") in HISTORY_MINOR_ROOMS.get(_bld(room), ())


def is_minor_room(room):
    """True for a room a Gen Ed exam may use as a first choice: the rooms of the exam history, Main 1-3, Alta 3rd floor, New 2-3."""
    if _is_lab(room) or getattr(room, "department", None):
        return False
    b, f = _bld(room), _floor(room)
    return _in_history(room) or (b == "M" and (f or 99) <= 3) or (b == "D" and f == 3) or (b == "N" and f in (2, 3))


def _tier_rooms(lecture, turn, srt):
    """The preferred Gen Ed rooms: the history rooms first, then Main 1-3, Alta (D) 3rd floor, New Building 2-3.
    Main takes two turns out of four, so it carries about half of the exams, as in the history."""
    ok = [r for r in lecture if is_minor_room(r)]
    ordered = lambda lst: sorted(srt(lst), key=lambda r: not _in_history(r))      # stable: history rooms first
    main = ordered([r for r in ok if _bld(r) == "M"])
    alta = ordered([r for r in ok if _bld(r) == "D"])
    new = ordered([r for r in ok if _bld(r) == "N"])
    return _interleave([main[0::2], alta, main[1::2], new], turn)


def _minor_lecture_rooms(lecture, srt, turn, minor):
    """Gen Ed lecture rooms: the preferred tiers first, then any other lecture room as a last resort."""
    if not minor:
        return srt(lecture)
    tier = _tier_rooms(lecture, turn, srt)
    listed = {r.id for r in tier}
    other_open = [r for r in lecture if r.id not in listed and not getattr(r, "department", None)]
    owned = [r for r in lecture if r.id not in listed and getattr(r, "department", None)]
    return tier + srt(other_open) + srt(owned)


def check_exams(exams, expected_pairs=None):
    """Re-checks saved exams against the rules above and against double-booking.
    exams: ExamSchedule rows (select_related subject, section__program, room, timeslot).
    expected_pairs: {(subject_id, section_id)} that must have an exam.
    Returns {"missing": [...], "room_conflicts": [...], "rule_violations": [...], "counts": {...}}."""
    from collections import defaultdict
    from .services import _minutes
    out = {"missing": [], "room_conflicts": [], "rule_violations": []}
    have = {(e.subject_id, e.section_id) for e in exams}
    for sid, secid in sorted(expected_pairs or ()):
        if (sid, secid) not in have:
            out["missing"].append({"subject_id": sid, "section_id": secid})
    by_room = defaultdict(list)
    for e in exams:
        by_room[(e.room_id, e.exam_date)].append(e)
        sub, sec, room = e.subject, e.section, e.room
        label = f"{sub.code} ({sec.name}) in {room.name}"
        if (sub.lab_units or 0) > 0 and is_computer_studies(sec) and not _is_comp_lab(room):
            out["rule_violations"].append(f"{label}: Computer Studies lab subjects must use Comp Lab C or D.")
        if sub.classification == "minor" and (sub.lab_units or 0) == 0:
            b, f = _bld(room), _floor(room)
            ok = is_minor_room(room)
            if _is_lab(room) and not is_nursing(sec):
                out["rule_violations"].append(f"{label}: a Gen Ed lecture is in a laboratory.")
            elif not ok and not _is_lab(room):
                out["rule_violations"].append(f"{label}: outside the Gen Ed exam rooms (history rooms, Main 1st-3rd floor, Alta 3rd floor, New Building 2nd-3rd floor); used because those rooms were full.")
    for (rid, d), rows in by_room.items():
        seen_keys, one = set(), []
        for e in rows:                                       # sections sitting one merged exam together are ONE booking
            k = getattr(e, "merge_key", "")
            if k:
                if k in seen_keys:
                    continue
                seen_keys.add(k)
            one.append(e)
        rows = sorted(one, key=lambda e: _minutes(e.timeslot.start_time))
        for a, b in zip(rows, rows[1:]):
            if _minutes(b.timeslot.start_time) < _minutes(a.timeslot.end_time):
                out["room_conflicts"].append(f"{a.room.name} on {d}: {a.subject.code} and {b.subject.code} overlap.")
    try:
        from faculty.models import FacultyProfile
        from .proctors import ProctorPool
        pool = ProctorPool(FacultyProfile.objects.select_related("user").prefetch_related("specializations"))
        for e in exams:
            if not pool.acceptable(e.subject, e.proctor_id):
                who = e.proctor.user.get_full_name().strip() or e.proctor.user.username
                need = "own-college faculty or Dean" if e.subject.classification != "minor" else "CAS faculty with a matching specialization"
                out["rule_violations"].append(f"{e.subject.code} ({e.section.name}): proctor {who} is not {need} (used because none was free).")
    except Exception:
        pass
    out["counts"] = {"exams": len(exams), "missing": len(out["missing"]), "room_conflicts": len(out["room_conflicts"]),
                     "rule_violations": len(out["rule_violations"])}
    return out
