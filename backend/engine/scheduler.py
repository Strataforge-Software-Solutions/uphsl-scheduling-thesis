"""
Scheduling Engine — Constraint Satisfaction Problem formulation.

Variables : one per (Section, Subject-required-period) — i.e. each weekly
            period a subject must occupy for a given section.
Domains   : candidate (teacher, room, timeslot) triples valid for that variable.
Constraints (hard):
    - Faculty Conflict   : teacher not already booked at that timeslot
    - Room Conflict      : room not already booked at that timeslot
    - Section Conflict   : section not already booked at that timeslot
    - Faculty Availability: teacher must be free per their Constraint rows
    - Room Compatibility : subject's lab/lecture requirement matches room type

Uses MRV (Minimum Remaining Values) heuristic to pick the next variable and
forward checking to prune domains after each assignment — this is what
prevents the double-booking bug that fell out of the old ad hoc version
(where a fallback loop used a stale `teacher`/`room` from an outer loop
instead of one that had actually been checked against constraints).
"""
from collections import defaultdict


class Assignment:
    __slots__ = ("subject", "section", "teacher", "room", "timeslot")

    def __init__(self, subject, section, teacher, room, timeslot):
        self.subject = subject
        self.section = section
        self.teacher = teacher
        self.room = room
        self.timeslot = timeslot


LAB_HOURS_PER_UNIT = 3      # 1 lab unit = 3 contact hours (e.g. a 1-unit lab is one 3-hour block)
MAX_BLOCK_HOURS = 3         # a longer requirement is split into several blocks


# Programs whose 3-unit MAJOR lectures follow the GTI "two days, same time"
# pattern (e.g. Nursing: Mon+Tue 7:00-8:30). Match is by program name/department
# containing one of these words. Every other program keeps "units = hours" in
# one continuous block.
PAIR_PATTERN_KEYWORDS = ("nursing",)
PAIR_DAYS = (("Mon", "Tue"), ("Wed", "Thu"), ("Fri", "Sat"))
PAIR_SESSION_HOURS = 1.5


class PairHours(float):
    """Marks a lecture that meets TWICE a week at the same time on paired days
    (each session 1.5 h = 3 half-hour slots). Distinct from a plain 1.5."""
    def __hash__(self):
        return hash(("pair", float(self)))

    def __eq__(self, other):
        return isinstance(other, PairHours) and float(self) == float(other)

    def __ne__(self, other):
        return not self.__eq__(other)


def uses_pair_pattern(subject):
    if getattr(subject, "classification", "major") != "major" or subject.lec_units != 3:
        return False
    prog = getattr(subject, "program", None)
    text = f"{getattr(prog, 'name', '')} {getattr(prog, 'department', '')}".lower()
    return any(k in text for k in PAIR_PATTERN_KEYWORDS)


def blocks_for_subject(subject):
    """Hours of each continuous class block a subject needs per week.
    Lecture units = hours (2 units -> one 2-hour block, 3 units -> one 3-hour
    block); each lab unit = 3 hours. Anything longer than MAX_BLOCK_HOURS is
    split into several blocks. Every block is placed on ONE day, back to back,
    with one teacher and one room.
    Exception (Nursing-style programs): a 3-unit major lecture is ONE pair
    block -- two 1.5-hour sessions on paired days at the same time."""
    blocks = []
    pair = uses_pair_pattern(subject)
    for kind, hours in (("lec", subject.lec_units), ("lab", subject.lab_units * LAB_HOURS_PER_UNIT)):
        if kind == "lec" and pair:
            blocks.append(PairHours(PAIR_SESSION_HOURS))
            continue
        while hours > 0:
            take = min(hours, MAX_BLOCK_HOURS)
            blocks.append(take)
            hours -= take
    return blocks or [1]


def window_need_minutes(subject):
    """Shortest Start-End window (minutes) a subject's chosen time may have: its longest unbroken class period. The ONE rule used by
    Generate (views._preview_choices) and sent to the preview (Subject.need_minutes) so the in-row hint always matches the server."""
    return max(int(round(float(h) * 60)) for h in blocks_for_subject(subject))


class BlockSlot:
    """A run of back-to-back TimeSlots on one day, treated as ONE slot by the
    search (so a 2-hour lecture is a single 2-hour placement, not two separate
    hours). Quacks like a TimeSlot for the overlap/ordering logic."""
    __slots__ = ("slots", "day", "start_time", "end_time", "id", "_uf_key")

    def __init__(self, slots):
        self.slots = slots
        self.day = slots[0].day
        self.start_time = slots[0].start_time
        self.end_time = slots[-1].end_time
        self.id = ("block", slots[0].id, len(slots))


def _slot_minutes(t):
    if hasattr(t, "hour"):
        return t.hour * 60 + t.minute
    parts = [int(x) for x in str(t).split(":")]
    return parts[0] * 60 + (parts[1] if len(parts) > 1 else 0)


def _dur(t):
    return _slot_minutes(t.end_time) - _slot_minutes(t.start_time)


class PairSlot(BlockSlot):
    """Two same-time sessions on paired days (e.g. Mon 7:00-8:30 + Tue 7:00-8:30).
    `parts` are the two single-day BlockSlots; the search treats the pair as ONE
    placement and overlap checks look at both days."""
    __slots__ = ("parts",)

    def __init__(self, first, second):
        BlockSlot.__init__(self, list(first.slots) + list(second.slots))
        self.day = first.day
        self.start_time = first.start_time
        self.end_time = first.end_time          # key = first day's range; see _slots_overlap
        self.parts = (first, second)
        self.id = ("pair", first.slots[0].id, second.slots[0].id)


class BlockList(list):
    """The block slots of one length. `.half` holds the extra blocks that START ON THE HALF HOUR (7:30-9:30 ...), built from the
    30-minute time slots. They are used only for a subject whose Start / End Time chosen in the preview falls on a half hour."""
    half = ()


def _half_hour_blocks(timeslots, hours):
    need = int(round(float(hours) * 60))
    by_day = defaultdict(list)
    for t in timeslots:
        if _dur(t) == 30:
            by_day[t.day].append(t)
    out = []
    for day, slots in by_day.items():
        slots = sorted(slots, key=lambda t: _slot_minutes(t.start_time))
        for i in range(len(slots)):
            if _slot_minutes(slots[i].start_time) % 60 != 30:
                continue
            run = [slots[i]]
            for j in range(i + 1, len(slots)):
                if _slot_minutes(slots[j].start_time) != _slot_minutes(run[-1].end_time):
                    break
                run.append(slots[j])
                if _slot_minutes(run[-1].end_time) - _slot_minutes(run[0].start_time) >= need:
                    break
            if _slot_minutes(run[-1].end_time) - _slot_minutes(run[0].start_time) == need:
                out.append(BlockSlot(run))
    return out


def with_half_blocks(blocks, window):
    """The block list a subject may use: the normal one, plus the half-hour-start blocks when its chosen window is on a half hour."""
    if window and (window[0] % 60 or window[1] % 60):
        return list(blocks) + list(getattr(blocks, "half", ()))
    return blocks


def build_block_slots(timeslots, hours):
    """All runs of adjacent TimeSlots (same day, each starting where the
    previous ended) that add up to `hours` hours.
    * ordinary blocks use the normal (>= 60 min) slots only;
    * a PairHours block uses the 30-minute slots: a 1.5 h run on each of two
      paired days at the same start time (run `seed_timeslots` to create them)."""
    pair = isinstance(hours, PairHours)
    need = int(round(float(hours) * 60))
    by_day = defaultdict(list)
    for t in timeslots:
        short = _dur(t) < 60
        if short == pair:
            by_day[t.day].append(t)
    blocks = []
    per_day = {}
    for day, slots in by_day.items():
        slots = sorted(slots, key=lambda t: _slot_minutes(t.start_time))
        runs = []
        for i in range(len(slots)):
            run, total = [], 0
            for j in range(i, len(slots)):
                if run and _slot_minutes(slots[j].start_time) < _slot_minutes(run[-1].end_time):
                    continue          # an irregular slot overlapping the run (e.g. 11:30-12:30 between 11-12 and 12-1): skip it
                if run and _slot_minutes(slots[j].start_time) != _slot_minutes(run[-1].end_time):
                    break
                run.append(slots[j])
                total = _slot_minutes(run[-1].end_time) - _slot_minutes(run[0].start_time)
                if total >= need:
                    break
            if total >= need and run:
                runs.append(BlockSlot(run))
        per_day[day] = runs
        if not pair:
            blocks.extend(runs)
    if not pair:
        out = BlockList(blocks)
        out.half = _half_hour_blocks(timeslots, hours)
        return out
    if pair:
        for d1, d2 in PAIR_DAYS:
            second = {_slot_minutes(r.start_time): r for r in per_day.get(d2, [])}
            for r1 in per_day.get(d1, []):
                r2 = second.get(_slot_minutes(r1.start_time))
                if r2 is not None:
                    blocks.append(PairSlot(r1, r2))
    return blocks


def block_hours_of(slot):
    """Total class hours in a placed block (pairs count both sessions)."""
    if isinstance(slot, BlockSlot):
        return sum(_dur(t) for t in slot.slots) / 60.0
    return 1


class Var(tuple):
    """(section, subject, block_index) -- a plain tuple that can also carry a
    human-readable `reason` explaining why it could not be placed."""
    reason = ""


def build_variables(subjects_by_section):
    """One variable per (section, subject, block-index): each continuous
    class block a subject needs per week (see blocks_for_subject)."""
    variables = []
    for section, subjects in subjects_by_section.items():
        for subject in subjects:
            for i in range(len(blocks_for_subject(subject))):
                variables.append(Var((section, subject, i)))
    return variables


def _rr_designated(rooms, dept):
    from rooms.rules import designated_rooms
    return designated_rooms(rooms, dept)


def build_domain(section, subject, teachers, rooms, timeslots, availability_rules, specialization_map,
                 dept_building=None, max_rooms=12):
    """Valid (teacher, room, timeslot) triples for one variable, before other-variable conflicts.
    specialization_map: {teacher_id: set(academic_field_id, ...)} precomputed ONCE outside
    this function -- calling t.specializations.all() here (once per teacher per subject per
    variable) was an N+1 query bug that is nearly free locally but painfully slow (many
    seconds) over a remote DB like Supabase, since each call is a network round-trip.

    A teacher is "qualified" when subject.field is in their specialization set
    (specializations are AcademicField rows -- a discipline like "Computer
    Science", not individual Subject rows). A subject with no field tagged
    yet (field is None) matches any teacher, same as before this existed, so
    untagged curriculum data doesn't suddenly make scheduling fail."""
    domain = []
    from .qualification import qualified_teachers as _qual
    qualified_teachers = _qual(subject, section, teachers, specialization_map)      # no "everybody" fallback
    from rooms import rules as _rrt
    _chosen = _rrt.teacher_choice_for(subject.id)
    if _chosen is not None:          # the Dean's professor for this run: only that teacher (never a silent swap)
        qualified_teachers = [t for t in qualified_teachers if t.id == _chosen]
    _ov = _rrt.qualification_override_for(subject.id)
    if _ov is not None:              # the Dean's manual "Assign anyway" for this one subject: that one person only (never chosen by the engine)
        qualified_teachers = [t for t in teachers if t.id == _ov["teacher"]]
    gym_exists = any(getattr(r, "room_type", "") == "gym" for r in rooms)
    compatible_rooms = [r for r in rooms if _room_matches_subject(r, subject, gym_exists)]
    # Reserved rooms (M-HJ for IHM, Comp Lab C/D for Computer Studies, Comp Lab B for SHS/JHS) are
    # exclusive to their department, and a department that owns labs uses only its own labs.
    from rooms.rules import allowed_rooms
    compatible_rooms = allowed_rooms(compatible_rooms, getattr(section.program, "department", None),
                                     lab_subject=subject.lab_units > 0,
                                     major=subject.classification != "minor")
    if subject.classification != "minor":
        _des = _rr_designated(compatible_rooms, getattr(section.program, "department", None))
        if _des is not None:
            compatible_rooms = _des            # Computer Studies majors: Comp Lab C / D only, never an ordinary lecture room
    # The Dean's room assignment for this subject: a FIXED room is the only room allowed (and must seat the
    # section); otherwise the preferred room and alternatives simply sort first (see _room_preference).
    from rooms import rules as _rr
    _asg = _rr.assignment_for(subject.id)
    if _asg and _asg["fixed"]:
        compatible_rooms = [r for r in compatible_rooms if r.id == _asg["preferred"] and _rr.fits_size(r, section)]
    # Capacity is a hard rule: a room must seat the whole section. (If NO allowed room is big enough the list is kept
    # as it is, so the class is still placed and the Dean sees the shortage in the capacity check.)
    _size = _rr.effective_size(section, subject)           # a shared class is sized for the whole group
    if _size:
        _fit = [r for r in compatible_rooms if not ((getattr(r, "capacity", 0) or 0) and r.capacity < _size)]
        if _fit:
            compatible_rooms = _fit
    # Keep only the best-suited rooms (building / department / capacity preference).
    # Without this the domain is teachers x ALL rooms x timeslots (hundreds of
    # thousands of triples per class period once the real room list is loaded),
    # which made generation take 20-30 s and hit the time budget.
    if max_rooms and len(compatible_rooms) > max_rooms:
        compatible_rooms.sort(key=lambda r: (_lab_taken_by_lecture(r, subject), _room_preference(r, section, subject, dept_building), r.id))
        compatible_rooms = compatible_rooms[:max_rooms]

    win = _rr.time_window_for(subject.id)
    timeslots = with_half_blocks(timeslots, win)
    busy = _rr.share_busy_for(section, subject)
    if busy:          # a shared class: every member section must be free then too
        def _free(sl):
            return not any(k[0] == b[0] and min(k[2], b[2]) - max(k[1], b[1]) > 0 for k in _slot_keys(sl) for b in busy)
        timeslots = [sl for sl in timeslots if _free(sl)]
    if win:           # the start / end time chosen for this subject in the curriculum preview
        timeslots = [sl for sl in timeslots if win[0] <= _slot_minutes(sl.start_time) and _slot_minutes(sl.end_time) <= win[1]]
    _day = _rr.day_choice_for(subject.id)
    if _day:          # the day the Dean assigned from the Faculty time window
        timeslots = [sl for sl in timeslots if str(sl.day)[:3].title() == _day]
    for teacher in qualified_teachers:
        for room in compatible_rooms:
            for slot in timeslots:
                if _teacher_available(teacher, slot, availability_rules) and (
                        _ov is None or _teacher_available(teacher, slot, {teacher.id: _ov["blocked"]})):
                    domain.append((teacher, room, slot))
    return domain


_GYM_WORDS = ("physical education", "physical fitness", "national service", "nstp", "rotc", "p.e.", "pathfit")


def _is_gym_subject(subject):
    """PE / NSTP / ROTC classes are held in the gym."""
    title = (subject.title or "").lower()
    code = (subject.code or "").lower()
    return any(w in title for w in _GYM_WORDS) or code.startswith(("pe", "nstp", "rotc", "pathfit"))


def _room_matches_subject(room, subject, gym_exists=False):
    """Hard room rules. Off-site/online rooms are never auto-assigned. Gym rooms
    are only for PE/NSTP/ROTC (and PE/NSTP use the gym whenever one exists)."""
    rtype = getattr(room, "room_type", "lecture")
    if rtype == "offsite":
        return False
    is_gym_subject = _is_gym_subject(subject)
    if rtype == "gym":
        return is_gym_subject
    if is_gym_subject and gym_exists:
        return False
    needs_lab = subject.lab_units > 0
    return (rtype == "lab") == needs_lab if needs_lab else True


def _lab_taken_by_lecture(room, subject):
    """1 when a lecture-only subject would sit in a department's own laboratory (Comp Lab C / D). The GTI class program lets the
    department use them, but they are the only rooms its 3-hour lab blocks can use, so a lecture takes one only as a last resort."""
    return 1 if (subject.lab_units == 0 and getattr(room, "room_type", "") == "lab" and getattr(room, "department", None)) else 0


def _room_preference(room, section, subject, dept_building):
    """Soft room preferences (lower = better), never excludes a room:
    minor subjects -> Main building (M); major subjects -> their department's
    building; lab subjects -> their own department's labs; then room capacity
    covering the section's student count."""
    building = getattr(room, "building", "") or ""
    if _is_gym_subject(subject):
        return (0, 0, 0)
    if subject.classification == "minor":
        want = "M"
    else:
        # program (major) subjects: their college's building, Alta (D) unless the Dean chose another
        want = (dept_building or {}).get(getattr(section.program, "department", None)) or "D"
    dept_name = getattr(section.program, "department", None)
    if subject.classification != "minor" and getattr(room, "department", None) == dept_name:
        bld_miss = 0                      # a room assigned to this department (e.g. RadTech's D-204/D-206)
    else:
        bld_miss = 1 if (not want or building == want) else 2
    # Major subjects: the department's HOME rooms from the GTI class program come first. A department with none
    # (nothing recorded yet) falls back to its building, Alta's 3rd floor first.
    from rooms import rules as _hr
    home_miss, floor_miss = 0, 0
    if subject.classification != "minor":
        if _hr.home_ids(dept_name):
            home_miss = _hr.home_rank(room, dept_name)
        elif want == "D":
            floor_miss = 0 if _hr.floor_of(room) == 3 else 1
    lab_miss = 0
    if (subject.lab_units == 0 and getattr(room, "room_type", "") == "lab"
            and not (subject.classification != "minor" and getattr(room, "department", None) == dept_name)):
        lab_miss = 1  # keep labs free for lab subjects, before capacity is considered
    if subject.lab_units > 0:
        dept = getattr(section.program, "department", None)
        rd = getattr(room, "department", None)
        # own department's lab first, then an unowned lab, last another department's lab
        lab_miss = 0 if (rd and rd == dept) else (2 if rd else 1)
    from rooms import rules as _gr
    size = _gr.effective_size(section, subject)
    cap = getattr(room, "capacity", 0) or 0
    # too small OR wastefully large (an auditorium must not absorb every minor class)
    cap_miss = 1 if (size and cap and (cap < size or cap > 2 * size)) else 0
    shortage = max(0, size - cap) if (size and cap) else 0      # if nothing seats the section, the biggest room wins
    from rooms import rules as _rr
    if _rr.assignment_for(subject.id):
        # the Dean's preferred room, then the alternatives, then everything else by the usual preference
        return (_rr.assign_rank(room, section, subject), home_miss, bld_miss, floor_miss, lab_miss, cap_miss, shortage)
    return (home_miss, bld_miss, floor_miss, lab_miss, cap_miss, shortage)


def _teacher_available(teacher, slot, availability_rules):
    blocked = availability_rules.get(teacher.id, set())
    if isinstance(slot, BlockSlot):
        return not any(sl.id in blocked for sl in slot.slots)
    return slot.id not in blocked


_DAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _slot_key(slot):
    """(day index, start minute, end minute) for a TimeSlot, computed once and
    cached on the instance. The overlap check runs millions of times during a
    search; doing it with datetime objects each time made generation take
    minutes. Plain integers give exactly the same answer far faster."""
    k = getattr(slot, "_uf_key", None)
    if k is None:
        def to_min(t):
            if hasattr(t, "hour"):
                return t.hour * 60 + t.minute
            parts = [int(x) for x in str(t).split(":")]
            return parts[0] * 60 + (parts[1] if len(parts) > 1 else 0)
        k = (_DAY_INDEX.get(slot.day[:3].lower(), 99 + hash(slot.day[:3].lower()) % 1000),
             to_min(slot.start_time), to_min(slot.end_time))
        try:
            slot._uf_key = k
        except Exception:
            pass
    return k


def _slot_keys(slot):
    """Keys for every day-range a slot covers (two for a PairSlot)."""
    if type(slot) is PairSlot:
        return [_slot_key(p) for p in slot.parts]
    return [_slot_key(slot)]


def _slots_overlap(a, b):
    """True if two TimeSlots fall on the same day and their time ranges
    overlap at all (not just when they are the literal same row).

    History: this used to compare only exact TimeSlot ids, which let the
    engine double-book across two different but overlapping rows (e.g.
    9:00-14:00 vs 13:00-16:00). Same semantics as engine/conflicts.py
    (strictly positive overlap on the same day), implemented on cached
    integer minutes for speed."""
    if type(a) is PairSlot or type(b) is PairSlot:
        pa = a.parts if type(a) is PairSlot else (a,)
        pb = b.parts if type(b) is PairSlot else (b,)
        return any(_slots_overlap(x, y) for x in pa for y in pb)
    ka, kb = _slot_key(a), _slot_key(b)
    if ka[0] != kb[0]:
        return False
    return min(ka[2], kb[2]) - max(ka[1], kb[1]) > 0


def _week_pos(slot, which):
    """(day index, minute) position of a slot's start or end within the week,
    so 'earlier in the week' comparisons work across days, not only same-day."""
    if which == "end" and type(slot) is PairSlot:
        slot = slot.parts[-1]            # a pair ends with its LAST session
    d, st, en = _slot_key(slot)
    return (d, st if which == "start" else en)


def _is_lab_of(lab_subject, lec_subject):
    """True when lab_subject is the Lab companion of lec_subject, by the
    curriculum's own coding (e.g. CS1102 Lec / CS1102L Lab)."""
    return lab_subject.code == lec_subject.code + "L"


def is_consistent(triple, section, subject, assigned_so_far):
    """Same rules as before (lecture-before-lab, one day/teacher/room per minor subject and section, no teacher / room /
    section double-booking); the cheap time-overlap test now runs first so classes that do not touch the same hour are skipped
    without the rest of the checks (this function runs hundreds of thousands of times per generation)."""
    teacher, room, slot = triple
    tid, rid, sid = teacher.id, room.id, section.id
    is_minor = subject.classification == "minor"
    sk = None if type(slot) is PairSlot else _slot_key(slot)
    for a in assigned_so_far:
        same_sec = a.section.id == sid
        if same_sec:
            # Lecture-before-lab: for the same section, a subject's Lab meetings must come after its Lecture
            # meetings in the week (CS1102 Lec first, then CS1102L Lab) -- not the other way round.
            # One teacher for both: the Lec and the Lab of one subject (CS1103 / CS1103L) are taught by the SAME teacher
            # for the same section (hard rule, not only a preference).
            if _is_lab_of(subject, a.subject):            # candidate is the lab
                if a.teacher.id != tid or _week_pos(slot, "start") < _week_pos(a.timeslot, "end"):
                    return False
            elif _is_lab_of(a.subject, subject):          # candidate is the lec
                if a.teacher.id != tid or _week_pos(a.timeslot, "start") < _week_pos(slot, "end"):
                    return False
            # Minor-subject same-day lock: every period of the SAME minor subject for the SAME section shares the
            # same day, teacher and room (otherwise "Filipino 1" could land on Mon AND Wed AND Fri independently).
            if is_minor and a.subject.id == subject.id:
                if a.timeslot.day[:3].lower() != slot.day[:3].lower():
                    return False
                if a.teacher.id != tid or a.room.id != rid:
                    return False
                if _slots_overlap(a.timeslot, slot):
                    return False  # would double-book the exact same hour twice

        ats = a.timeslot
        if sk is not None and type(ats) is not PairSlot:
            ak = _slot_key(ats)
            if ak[0] != sk[0] or min(ak[2], sk[2]) - max(ak[1], sk[1]) <= 0:
                continue
        elif not _slots_overlap(ats, slot):
            continue
        if same_sec or a.teacher.id == tid or a.room.id == rid:    # Section / Faculty / Room conflict
            return False
    return True


def generate_schedule(subjects_by_section, teachers, rooms, timeslots, availability_rules, max_steps=50000,
                       locked_assignments=None, time_budget_seconds=8, dept_building=None, teacher_caps=None):
    """
    Returns (assignments, unresolved). On failure, returns the partial
    assignment plus a conflict report of variables that could not be placed.
    max_steps caps total backtracking attempts -- if a dataset is pathologically
    tight (e.g. required periods close to available timeslots) and backtracking
    blows up combinatorially, this stops the search and returns whatever was
    placed so far instead of hanging indefinitely.

    locked_assignments: a list of already-made Assignment objects (e.g. the
    Gen Ed/minor-subject schedule solved in an earlier phase) that this run
    must treat as already-occupying their teacher/room/section/timeslot --
    used by generate_schedule_two_phase() below so major subjects are built
    around a Gen Ed schedule that's already fixed, instead of the two being
    solved independently and possibly colliding.
    """
    variables = build_variables(subjects_by_section)

    # Precompute {teacher_id: set(academic_field_id, ...)} ONCE -- this is what fixes
    # the N+1 query bug (previously queried inside build_domain, once per teacher per
    # subject per variable, which is painfully slow over a remote DB).
    specialization_map = {
        t.id: {f.id for f in t.specializations.all()} for t in teachers   # uses the prefetch: no per-teacher query
    }

    # One list of candidate "block slots" per block length actually needed.
    block_slots = {h: build_block_slots(timeslots, h)
                   for h in {blocks_for_subject(v[1])[v[2]] for v in variables}}

    domains = {
        v: build_domain(v[0], v[1], teachers, rooms,
                        block_slots[blocks_for_subject(v[1])[v[2]]], availability_rules, specialization_map,
                        dept_building=dept_building)
        for v in variables
    }

    # Seed with the locked (already-solved) assignments from a prior phase so
    # is_consistent()/forward-checking treat their teacher/room/section/timeslot
    # as occupied, without re-placing them.
    assigned = list(locked_assignments) if locked_assignments else []

    # Per-teacher / per-room / per-section index of everything assigned so far (kept in step with `assigned`), so a
    # candidate is checked against only ITS teacher's, room's and section's bookings instead of every assignment.
    # Gives exactly the same answer as is_consistent(candidate, ..., assigned), only much faster.
    ix_t, ix_r, ix_s = {}, {}, {}

    def _ix_add(a_):
        ks = _slot_keys(a_.timeslot)
        ix_t.setdefault(a_.teacher.id, []).append(ks)
        ix_r.setdefault(a_.room.id, []).append(ks)
        ix_s.setdefault(a_.section.id, []).append(a_)

    def _ix_remove(a_):
        ix_t[a_.teacher.id].pop()
        ix_r[a_.room.id].pop()
        ix_s[a_.section.id].pop()

    def _hit(ks, booked):
        for bk in booked:
            for k in ks:
                for b_ in bk:
                    if b_[0] == k[0] and min(b_[2], k[2]) - max(b_[1], k[1]) > 0:
                        return True
        return False

    def consistent_ix(triple, section, subject):
        teacher, room, slot = triple
        ks = _slot_keys(slot)
        if _hit(ks, ix_t.get(teacher.id, ())) or _hit(ks, ix_r.get(room.id, ())):
            return False
        mine = ix_s.get(section.id)
        return not mine or is_consistent(triple, section, subject, mine)

    for _a in assigned:
        _ix_add(_a)
    if assigned:
        # Index the already-placed assignments by teacher / room / section so
        # each candidate is checked against only THAT teacher's, room's and
        # section's bookings, not every assignment in the database. Same
        # result as calling is_consistent() against all of them, but much
        # faster once several year levels/semesters are already scheduled.
        by_teacher, by_room, by_section = {}, {}, {}
        for a in assigned:
            aks = _slot_keys(a.timeslot)
            by_teacher.setdefault(a.teacher.id, []).extend(aks)
            by_room.setdefault(a.room.id, []).extend(aks)
            by_section.setdefault(a.section.id, []).append(a)

        def _clash(k, booked):
            for bk in booked:
                if bk[0] == k[0] and min(bk[2], k[2]) - max(bk[1], k[1]) > 0:
                    return True
            return False

        from types import SimpleNamespace as _NS
        _nobody = _NS(id=-1)
        for var in variables:
            section, subject, _ = var
            same_section = by_section.get(section.id, [])
            # Against the SAME section's bookings the answer depends only on the time slot (lecture-before-lab, no
            # overlap) unless this very subject is already booked for the section (minor same-day/teacher/room lock) --
            # so it is computed once per slot instead of once per teacher x room x slot.
            # (also not when its Lec / Lab partner is booked: then the teacher must match, so the teacher matters)
            by_slot_only = bool(same_section) and not any(
                a.subject.id == subject.id or _is_lab_of(subject, a.subject) or _is_lab_of(a.subject, subject) for a in same_section)
            slot_ok = {}
            kept = []
            for triple in domains[var]:
                teacher, room, slot = triple
                ks = _slot_keys(slot)
                if any(_clash(k, by_teacher.get(teacher.id, ())) or _clash(k, by_room.get(room.id, ())) for k in ks):
                    continue
                if same_section:
                    if by_slot_only:
                        ok = slot_ok.get(id(slot))
                        if ok is None:
                            ok = slot_ok[id(slot)] = is_consistent((_nobody, _nobody, slot), section, subject, same_section)
                        if not ok:
                            continue
                    elif not is_consistent(triple, section, subject, same_section):
                        continue
                kept.append(triple)
            domains[var] = kept

    unresolved = []
    step_count = [0]
    # periods already assigned per teacher (earlier years/semesters included),
    # kept up to date as the search assigns and un-assigns.
    teacher_load = {}
    section_day_load = {}
    # Optional HARD weekly-hour cap per teacher (strict workload policy): {teacher_id: max_hours}.
    # cap_used starts from the distinct hours already booked (a shared class counts once).
    cap_used = {}
    if teacher_caps:
        _seen_cap = set()
        for a in assigned:
            _ck = (a.teacher.id, getattr(a.timeslot, "id", None))
            if _ck in _seen_cap:
                continue
            _seen_cap.add(_ck)
            cap_used[a.teacher.id] = cap_used.get(a.teacher.id, 0) + _dur(a.timeslot) / 60.0

    def _over_cap(tid, slot):
        return bool(teacher_caps) and tid in teacher_caps and \
            cap_used.get(tid, 0) + block_hours_of(slot) > teacher_caps[tid] + 1e-9

    for a in assigned:
        teacher_load[a.teacher.id] = teacher_load.get(a.teacher.id, 0) + 1
        _k = (a.section.id, _slot_key(a.timeslot)[0])
        section_day_load[_k] = section_day_load.get(_k, 0) + 1
    import time as _time
    _deadline = _time.time() + time_budget_seconds

    # (section id, lecture code) for every lecture that has a Lab companion in
    # this run -- those labs are placed AFTER their lecture so the
    # lecture-before-lab rule guides the search instead of causing endless
    # dead ends when a lab happens to be picked first.
    lec_codes = {(v[0].id, v[1].code) for v in variables}

    def is_lab_companion(v):
        return v[1].code.endswith("L") and (v[0].id, v[1].code[:-1]) in lec_codes

    def select_unassigned_variable(remaining):
        # MRV heuristic: pick the variable with the fewest remaining valid
        # options -- but lectures before their own labs.
        return min(remaining, key=lambda v: (is_lab_companion(v), len(domains[v])))

    def backtrack(remaining):
        if not remaining:
            return True

        step_count[0] += 1
        # Wall-clock limit as well as a step limit: a tight or very large
        # dataset used to be able to keep one HTTP request busy for minutes.
        if step_count[0] > max_steps or _time.time() > _deadline:
            # Bail out -- whatever's left unassigned gets reported as a conflict
            # rather than the search hanging indefinitely.
            unresolved.extend(remaining)
            return True  # stop recursing; treat as "done, with leftovers"

        var = select_unassigned_variable(remaining)
        section, subject, _ = var
        rest = [v for v in remaining if v != var]

        # Value ordering: try the LEAST-LOADED teacher first, then the earliest
        # slot in the week. Without this the first teacher in the list won every
        # class (in practice one person -- the Dean -- ended up teaching the
        # whole curriculum), and because that teacher was already busy early in
        # the week, lectures got pushed late and their labs then had no room
        # left after them.
        # Also spread each section's classes across the week: prefer the day
        # on which this section has the fewest periods so far, and keep
        # Saturday/Sunday as a last resort. Otherwise a section's whole week
        # piled onto Monday (a 12-hour day, with the one-day-per-minor-subject
        # rule then running out of room and stalling the search).
        # Keep one teacher per subject+section: if this subject already has a
        # period placed for this section, keep using that teacher (otherwise
        # load balancing handed each period of one subject to a different person).
        _same = [a.teacher.id for a in assigned if a.section.id == section.id and a.subject.id == subject.id]
        if not _same:
            # a Lab prefers its Lecture's teacher (and vice versa)
            _same = [a.teacher.id for a in assigned if a.section.id == section.id
                     and (_is_lab_of(subject, a.subject) or _is_lab_of(a.subject, subject))]
        preferred_teacher = _same[0] if _same else None

        _rp = {}

        def _room_pref_cached(room):
            v = _rp.get(room.id)
            if v is None:
                v = _rp[room.id] = _room_preference(room, section, subject, dept_building)
            return v

        _ar = {}

        def _assign_rank_cached(room):
            v = _ar.get(room.id)
            if v is None:
                from rooms import rules as _rr
                v = _ar[room.id] = _rr.assign_rank(room, section, subject)
            return v

        has_lab = (section.id, subject.code + "L") in lec_codes
        from . import availability as _av
        from . import lunch_gap as _lg
        _lg_on = _lg.enabled()

        def _no_gap(t):
            """1 when this placement would leave the section or the professor no free hour between 10:30 AM and 2:30 PM that day
            ("Reserve lunch gap", optional, soft: it only orders placements, never removes one)."""
            if not _lg_on:
                return 0
            for k in _slot_keys(t[2]):
                if k[2] <= _lg.WINDOW[0] or k[1] >= _lg.WINDOW[1]:
                    continue
                sec = [(b[1], b[2]) for a_ in ix_s.get(section.id, []) for b in _slot_keys(a_.timeslot) if b[0] == k[0]]
                tea = [(b[1], b[2]) for bk in ix_t.get(t[0].id, []) for b in bk if b[0] == k[0]]
                if not _lg.has_gap(sec + [(k[1], k[2])]) or not _lg.has_gap(tea + [(k[1], k[2])]):
                    return 1
            return 0

        def _value_key(t):
            k = _slot_key(t[2])
            return (
                0 if t[0].id == preferred_teacher else 1,          # same teacher as this subject's other periods
                _assign_rank_cached(t[1]),                         # the Dean's preferred / alternative rooms first
                _lab_taken_by_lecture(t[1], subject),              # a lecture uses a department lab only when nothing else fits,
                                                                   # so the department's lab classes keep their rooms
                _av.outside_preferred(t[0].id, t[2]),              # inside the teacher's "preferred" window first (soft: never excludes)
                _no_gap(t),                                        # optional lunch gap kept first (soft: never excludes)
                k[0] >= 6,
                # a lecture that has a lab: keep it early in the week so its lab can follow it
                (k[0] >= 3) if has_lab else False,                                         # Sunday last
                # lightest day for this section; Saturday is a normal class day
                # (college students attend) but weekdays fill a little first.
                section_day_load.get((section.id, k[0]), 0) + (2 if k[0] == 5 else 0),
                _room_pref_cached(t[1]),  # minor->Main, major->dept building, capacity
                1 if (t[1].room_type == "lab" and subject.lab_units == 0) else 0,  # keep labs free for lab subjects
                teacher_load.get(t[0].id, 0),                      # least-loaded teacher
                k[1], k[0], t[1].id,                               # then earliest time
            )
        candidates = sorted(domains[var], key=_value_key)
        for triple in candidates:
            if _over_cap(triple[0].id, triple[2]):
                continue
            if not consistent_ix(triple, section, subject):
                continue

            teacher, room, slot = triple
            assignment = Assignment(subject, section, teacher, room, slot)
            assigned.append(assignment)
            _ix_add(assignment)
            _h = block_hours_of(slot)
            teacher_load[teacher.id] = teacher_load.get(teacher.id, 0) + _h
            cap_used[teacher.id] = cap_used.get(teacher.id, 0) + _h
            _dk = (section.id, _slot_key(slot)[0])
            section_day_load[_dk] = section_day_load.get(_dk, 0) + _h

            # Forward checking: prune this slot from other same-teacher/room/section domains.
            pruned = _forward_check(domains, rest, assignment)

            if backtrack(rest):
                return True

            # Backtrack: undo assignment and restore pruned domain values.
            _ix_remove(assigned.pop())
            teacher_load[teacher.id] -= _h
            cap_used[teacher.id] = cap_used.get(teacher.id, 0) - _h
            section_day_load[_dk] -= _h
            _restore_domains(domains, pruned)

        unresolved.append(var)
        return False

    locked_count = len(locked_assignments) if locked_assignments else 0

    success = backtrack(variables)
    if not success:
        # Continue trying to place whatever else is placeable, collecting a full conflict report
        # rather than aborting the whole run on the first failure.
        pass

    # `assigned` was seeded with locked_assignments (if any) purely so
    # is_consistent()/forward-checking treat them as occupied -- those rows
    # already belong to the caller (they're what was passed in), so only this
    # call's OWN newly-placed assignments are returned. Returning the seeded
    # ones too would double-count them when a caller does
    # `phase1_assigned + phase2_assigned` (generate_schedule_two_phase).
    placed_blocks = assigned[locked_count:]

    # `unresolved` above also collects variables from abandoned dead-end
    # branches that were later solved a different way -- so a fully successful
    # run could still report hundreds of phantom "conflicts". The real answer
    # is simply: required blocks minus blocks actually placed.
    placed_count = {}
    for a in placed_blocks:
        key = (a.section.id, a.subject.id)
        placed_count[key] = placed_count.get(key, 0) + 1
    real_unresolved = []
    for var in variables:
        key = (var[0].id, var[1].id)
        if placed_count.get(key, 0) > 0:
            placed_count[key] -= 1
        else:
            real_unresolved.append(var)

    # Repair pass: the backtracking search can stop early (time or step limit)
    # while a valid spot still exists for a leftover class. Place each leftover
    # block directly, best candidate first, against everything already placed.
    # Every placement still goes through is_consistent(), so no rule is relaxed.
    repaired = []
    for var in list(real_unresolved):
        section, subject, idx = var
        try:
            cands = build_domain(section, subject, teachers, rooms, block_slots[blocks_for_subject(subject)[idx]],
                                 availability_rules, specialization_map, dept_building=dept_building)
        except Exception:
            continue
        pref_teacher = next((a.teacher.id for a in assigned if a.section.id == section.id and a.subject.id == subject.id), None)
        rp = {}

        def _rk(t, section=section, subject=subject, rp=rp, pref_teacher=pref_teacher):
            k = _slot_key(t[2])
            pr = rp.get(t[1].id)
            if pr is None:
                pr = rp[t[1].id] = _room_preference(t[1], section, subject, dept_building)
            from rooms import rules as _rr
            from . import availability as _av
            return (0 if t[0].id == pref_teacher else 1, _rr.assign_rank(t[1], section, subject),
                    _lab_taken_by_lecture(t[1], subject), _av.outside_preferred(t[0].id, t[2]), k[0] >= 6,
                    section_day_load.get((section.id, k[0]), 0) + (2 if k[0] == 5 else 0),
                    pr, teacher_load.get(t[0].id, 0), k[1], k[0], t[1].id)

        cands.sort(key=_rk)
        for n, triple in enumerate(cands):
            if n > 4000:
                break
            if not _over_cap(triple[0].id, triple[2]) and is_consistent(triple, section, subject, assigned):
                teacher, room, slot = triple
                a = Assignment(subject, section, teacher, room, slot)
                assigned.append(a)
                placed_blocks.append(a)
                h = block_hours_of(slot)
                teacher_load[teacher.id] = teacher_load.get(teacher.id, 0) + h
                cap_used[teacher.id] = cap_used.get(teacher.id, 0) + h
                dk = (section.id, _slot_key(slot)[0])
                section_day_load[dk] = section_day_load.get(dk, 0) + h
                repaired.append(var)
                break
    if repaired:
        real_unresolved = [v for v in real_unresolved if v not in repaired]

    # Expand each placed block back into one Assignment per real hourly
    # TimeSlot (the database stores one Schedule row per TimeSlot; the UI
    # merges back-to-back rows into a single block).
    placed = []
    for a in placed_blocks:
        if isinstance(a.timeslot, BlockSlot):
            for real in a.timeslot.slots:
                placed.append(Assignment(a.subject, a.section, a.teacher, a.room, real))
        else:
            placed.append(a)
    for var in real_unresolved:
        try:
            var.reason = explain_unresolved(var, assigned, teachers, rooms, block_slots,
                                            availability_rules, specialization_map, caps=(teacher_caps, cap_used),
                                            timeslots=timeslots)
        except Exception:
            var.reason = ""
    return placed, real_unresolved


def _clock(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{((h + 11) % 12) + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"


def explain_unresolved(var, assigned, teachers, rooms, block_slots, availability_rules, specialization_map, caps=None,
                       timeslots=None):
    """Say WHICH resource ran out for a block that could not be placed, so the
    Registrar knows what to add (time slots, teachers or rooms).
    With a Start / End range chosen and `timeslots` given, the reason is built from engine.blockers: every candidate period in the
    range, each with the rule that rules it out (reporting only; the search has already decided)."""
    section, subject, idx = var
    hours = blocks_for_subject(subject)[idx]
    slots = block_slots.get(hours, [])
    from rooms import rules as _rr0
    _win = _rr0.time_window_for(subject.id)
    slots = with_half_blocks(slots, _win)
    if _win:
        inside = [sl for sl in slots if _win[0] <= _slot_minutes(sl.start_time) and _slot_minutes(sl.end_time) <= _win[1]]
        if not inside:
            from . import blockers as _bl
            _why_none = _bl.summary(_bl.report(section, subject, hours, _win, timeslots, slots, [], [], [], availability_rules),
                                    hours, _win) if timeslots else ""
            if _why_none:
                return (f"No {float(hours):g}-hour class period fits inside your {_clock(_win[0])}-{_clock(_win[1])} range on any day. "
                        + _why_none.split(". ", 1)[1] + " Widen the Start / End Time of this subject, or set it to 'Any time'.")
            return (f"No {hours}-hour class period fits between the chosen start and end time. Widen the Start / End Time of this subject "
                    "in the curriculum preview, or set it to 'Any time'.")
        slots = inside
    _day = _rr0.day_choice_for(subject.id)
    if _day:          # the Dean assigned this subject to one day (Faculty time window)
        slots = [sl for sl in slots if str(sl.day)[:3].title() == _day]
        if not slots:
            return (f"No {float(hours):g}-hour class period fits on {_day}"
                    + (f" inside your {_clock(_win[0])}-{_clock(_win[1])} range" if _win else "")
                    + ". Choose another time in the Faculty time window, or clear the Day.")
    if not slots:
        return (f"There are no {hours}-hour windows in the time-slot table (needs back-to-back hourly slots). "
                "Open Settings > Time slots and generate the hourly Mon-Sat slots (7AM-8PM), then press Resolve.")
    from .qualification import qualified_teachers as _qual, why_nobody as _why
    qteachers = _qual(subject, section, teachers, specialization_map)
    _ov = _rr0.qualification_override_for(subject.id)
    if _ov is not None:              # "Assign anyway": the pinned person, inside their submitted availability
        qteachers = [t for t in teachers if t.id == _ov["teacher"]]
        availability_rules = {**availability_rules, _ov["teacher"]: set(availability_rules.get(_ov["teacher"], set())) | set(_ov["blocked"])}
    if not qteachers:
        return _why(subject, section, teachers, specialization_map)
    # the professor the Dean chose for this subject in the Generate preview: only that teacher is used, and the reason names them
    chosen, cname = None, ""
    _ct = _rr0.teacher_choice_for(subject.id)
    if _ct is not None:
        chosen = next((t for t in teachers if t.id == _ct), None)
        cname = (chosen.user.get_full_name().strip() or chosen.user.username) if chosen else "The chosen professor"
        if chosen is None or chosen.id not in {t.id for t in qteachers}:
            return (f"{cname} (your chosen professor) is not qualified for {subject.code}. Choose another professor in the "
                    "Professor column, or leave it on Automatic.")
        qteachers = [chosen]
        if caps and caps[0] and chosen.id in caps[0] and (caps[1] or {}).get(chosen.id, 0) + float(hours) > caps[0][chosen.id] + 1e-9:
            return (f"{cname} (your chosen professor) would go over the weekly limit of {caps[0][chosen.id]:g} hours: "
                    f"{(caps[1] or {}).get(chosen.id, 0):g} hours are already assigned and this class needs {float(hours):g} more. "
                    "Choose another professor, or leave it on Automatic.")
    # the Lec / Lab partner already has a teacher: this part must have the same one
    partner = next((a for a in assigned if a.section.id == section.id
                    and (_is_lab_of(subject, a.subject) or _is_lab_of(a.subject, subject))), None)
    if partner is not None:
        pname = partner.teacher.user.get_full_name().strip() or partner.teacher.user.username
        if chosen is not None and partner.teacher.id != chosen.id:
            return (f"{partner.subject.code} is taught by {pname}, and its Lec and Lab must have the same teacher, but you chose "
                    f"{cname} for {subject.code}. Choose the same professor for both, or leave both on Automatic.")
        if partner.teacher.id not in {t.id for t in qteachers}:
            return (f"{partner.subject.code} is taught by {pname}, and its Lec and Lab must have the same teacher, but {pname} is not "
                    f"qualified for {subject.code}. Record the specialization in the Faculty tab.")
        qteachers = [t for t in qteachers if t.id == partner.teacher.id]
    gym_exists = any(getattr(r, "room_type", "") == "gym" for r in rooms)
    qrooms = [r for r in rooms if _room_matches_subject(r, subject, gym_exists)]
    _des = None
    if subject.classification != "minor":
        _des = _rr_designated(qrooms, getattr(section.program, "department", None))
        if _des is not None:
            qrooms = _des
    from rooms import rules as _rr
    _asg = _rr.assignment_for(subject.id)
    if _asg and _asg["fixed"]:
        fixed = next((r for r in rooms if r.id == _asg["preferred"]), None)
        if fixed is None or fixed not in qrooms or not _rr.fits_size(fixed, section):
            return (f"Fixed room {fixed.name if fixed else ''} cannot be used for this subject (wrong room type, reserved for "
                    "another department, or too small for the section). Choose another room in the Room dropdown of the curriculum preview.")
        qrooms = [fixed]
    if not qrooms:
        kind = "lab" if subject.lab_units > 0 else "suitable"
        return (f"No {kind} room is allowed for this subject (room type, department ownership or the Dean's fixed room). "
                "Choose another room for the subject in the curriculum preview (Generate Schedule) or its Room assignments.")

    if _win and timeslots:
        # every candidate period in the chosen range, with the rule that rules it out: never blame the professor's time when the
        # professor is free and the lunch break, a booked room or the section's own class is the blocker
        from . import blockers as _bl
        _kind = "Lab" if (subject.lab_units and not subject.lec_units) else ("Lecture" if subject.lab_units == 0 else "class")
        _txt = _bl.summary(
            _bl.report(section, subject, hours, _win, timeslots, slots, assigned, qteachers, qrooms, availability_rules,
                       chosen=chosen, caps=caps, size=_rr.effective_size(section, subject), share_busy=_rr.share_busy_for(section, subject)),
            hours, _win, what=_kind, chosen_name=cname if chosen is not None else "", designated=_des is not None)
        if _txt:
            if chosen is not None:
                return _txt + " Widen the Start / End Time, choose another professor, or leave it on Automatic."
            if partner is not None:
                return _txt + f" Its Lec and Lab must have the same teacher ({pname}). Widen the Start / End Time, or set it to 'Any time'."
            return _txt + " Widen the Start / End Time, or set it to 'Any time'."
    sec_free = [sl for sl in slots if not any(a.section.id == section.id and _slots_overlap(a.timeslot, sl) for a in assigned)]
    if not sec_free:
        hint = " The time-slot table is small; generate the hourly Mon-Sat slots." if len(slots) < 25 else ""
        return (f"Only {len(slots)} possible {hours}-hour windows exist in the week and this section's "
                f"other classes already occupy all of them.{hint}")
    teacher_ok = room_ok = both = 0
    for sl in sec_free:
        bt = {a.teacher.id for a in assigned if _slots_overlap(a.timeslot, sl)}
        br = {a.room.id for a in assigned if _slots_overlap(a.timeslot, sl)}
        t_free = any(t.id not in bt and _teacher_available(t, sl, availability_rules) for t in qteachers)
        r_free = any(r.id not in br for r in qrooms)
        teacher_ok += t_free
        room_ok += r_free
        both += (t_free and r_free)
    if both:
        return ("A teacher and a room are each free at some times, but the subject's rules "
                "(one day, one teacher, lecture before lab) leave no free arrangement right now. Pick one of the suggested free times, or change the room / time you chose.")
    if teacher_ok == 0 and room_ok == 0:
        return (f"No teacher AND no room is free in any {hours}-hour window where this section is free. "
                f"({len(qteachers)} teachers, {len(qrooms)} rooms considered.) The suggested free times (if any) are listed with this class.")
    from . import availability as _avt
    _what = "Lab" if (subject.lab_units and not subject.lec_units) else ("Lecture" if subject.lab_units == 0 else "class")
    _range = (f" inside your {_clock(_win[0])}-{_clock(_win[1])} range" if _win else "")
    _need = f"this {_what} needs one {float(hours):g}-hour block{_range} when the section is free"

    def _who(t):
        return t.user.get_full_name().strip() or t.user.username

    def _all_outside(t):
        return all(not _teacher_available(t, sl, availability_rules) for sl in sec_free)

    if teacher_ok == 0 and chosen is not None:
        if _all_outside(chosen):
            txt = _avt.text_for(chosen.id)
            return (f"{cname} (your chosen professor) is {txt or 'outside their submitted availability at every such time'}; {_need}. "
                    "Choose another professor, widen the time you chose, or leave it on Automatic.")
        return (f"{cname} (your chosen professor) is already teaching another class (or outside their availability) at every "
                f"{hours}-hour time when this section is free. Choose another professor, or leave it on Automatic.")
    if teacher_ok == 0 and partner is not None:
        return (f"Its Lec and Lab must have the same teacher, and {pname} (who teaches {partner.subject.code}) is busy or unavailable at every "
                f"{hours}-hour time when this section is free. Pick one of the suggested free times, or change the room / time you chose.")
    if teacher_ok == 0:
        limited = [t for t in qteachers if _all_outside(t)]
        if limited:
            named = "; ".join(f"{_who(t)} is {_avt.text_for(t.id) or 'outside their submitted availability'}" for t in limited[:3])
            more = len(limited) - 3
            busy = len(qteachers) - len(limited)
            return (f"No qualified teacher can take it: {named}" + (f" (and {more} more outside their availability)" if more > 0 else "")
                    + (f"; the other {busy} qualified teacher(s) are already teaching then" if busy else "") + f". {_need[0].upper() + _need[1:]}.")
        return (f"No teacher is free in any {hours}-hour window where this section is free "
                f"(only {len(qteachers)} qualified teachers considered, all busy or unavailable). The suggested free times (if any) are listed with this class.")
    if room_ok == 0 and _asg and _asg["fixed"]:
        return (f"{qrooms[0].name} is already booked at every {hours}-hour time (inside your chosen time) when this section is free. "
                "Pick one of the suggested free times for this room, or choose a different time.")
    if room_ok == 0:
        return (f"No suitable room is free in any {hours}-hour window where this section is free "
                f"({len(qrooms)} rooms considered, all already booked). The suggested free times (if any) are listed with this class.")
    return (f"A teacher is free in {teacher_ok} windows and a room in {room_ok}, but never at the same time. "
            "Pick one of the suggested free times, or change the room / time you chose.")


def _forward_check(domains, remaining_vars, assignment):
    """Remove now-invalid (teacher/room/timeslot) triples from other variables' domains."""
    pruned = defaultdict(list)
    for var in remaining_vars:
        section, subject, _ = var
        kept = []
        for triple in domains[var]:
            teacher, room, slot = triple
            conflict = (
                _slots_overlap(slot, assignment.timeslot) and (
                    teacher.id == assignment.teacher.id or
                    room.id == assignment.room.id or
                    section.id == assignment.section.id
                )
            ) or (
                # the Lec / Lab partner of the same section must keep the teacher just chosen
                section.id == assignment.section.id and teacher.id != assignment.teacher.id
                and (_is_lab_of(subject, assignment.subject) or _is_lab_of(assignment.subject, subject))
            )
            if conflict:
                pruned[var].append(triple)
            else:
                kept.append(triple)
        domains[var] = kept
    return pruned


def _restore_domains(domains, pruned):
    for var, triples in pruned.items():
        domains[var].extend(triples)


def generate_schedule_two_phase(subjects_by_section, teachers, rooms, timeslots, availability_rules, max_steps=50000,
                                 existing_assignments=None, dept_building=None, teacher_caps=None):
    """
    Dean Villanueva's interview: Gen Ed (minor) subjects are scheduled FIRST
    across the whole college, and major-subject schedules are then built
    around whatever Gen Ed slots land where they land -- which is exactly why
    a Gen Ed faculty availability change cascades into reshuffling majors
    ("pag gumalaw ang Gen Ed, gumagalaw din lahat"). Previously the engine
    solved every subject in one pass with no notion of this ordering.

    Splits subjects_by_section into minor-only and major-only versions, solves
    minors first (phase 1), then solves majors with the minor assignments
    locked in as already-occupied (phase 2) so majors are genuinely built
    around the Gen Ed schedule rather than solved independently.

    existing_assignments: already-persisted Schedule rows from EARLIER runs
    (a different program, year level, or semester, generated in a previous
    click) -- Schedule.teacher/.room/.section/.timeslot are real FK objects
    so a Schedule instance satisfies the same duck-typed interface as an
    Assignment and can be passed straight through. Without this, each
    "Generate" click only avoided conflicts among its OWN newly-placed
    assignments and had no idea a teacher/room/timeslot combo was already
    taken by an earlier run, which could pick that same combo again and then
    fail at the database's hard uniqueness constraint on bulk_create.

    Returns (assignments, unresolved, phase_breakdown) where phase_breakdown
    is {"minor": (placed_count, unresolved_count), "major": (...)} -- useful
    for showing the Dean/Registrar which phase any leftover conflicts came
    from, since that's the diagnostic she does manually today.
    """
    existing_assignments = list(existing_assignments) if existing_assignments else []

    minors_by_section = {
        section: [s for s in subjects if s.classification == "minor"]
        for section, subjects in subjects_by_section.items()
    }
    majors_by_section = {
        section: [s for s in subjects if s.classification != "minor"]
        for section, subjects in subjects_by_section.items()
    }
    minors_by_section = {k: v for k, v in minors_by_section.items() if v}
    majors_by_section = {k: v for k, v in majors_by_section.items() if v}

    minor_assigned, minor_unresolved = generate_schedule(
        minors_by_section, teachers, rooms, timeslots, availability_rules, max_steps=max_steps,
        locked_assignments=existing_assignments, dept_building=dept_building, teacher_caps=teacher_caps,
    )

    major_assigned, major_unresolved = generate_schedule(
        majors_by_section, teachers, rooms, timeslots, availability_rules, max_steps=max_steps,
        locked_assignments=existing_assignments + minor_assigned, dept_building=dept_building, teacher_caps=teacher_caps,
    )

    phase_breakdown = {
        "minor": (len(minor_assigned), len(minor_unresolved)),
        "major": (len(major_assigned), len(major_unresolved)),
    }
    return minor_assigned + major_assigned, minor_unresolved + major_unresolved, phase_breakdown


# ---------------------------------------------------------------------------
# Dynamic Substitution — priority-based (same-subject + free, else any free),
# tiebreak by minimum current workload.
# ---------------------------------------------------------------------------
def find_substitute(absent_teacher, timeslot, subject, all_teachers, current_workload, availability_rules,
                     busy_teacher_ids=None):
    """
    Dean Villanueva's interview explicitly asks that when a faculty becomes
    unavailable, the system "recommend" a stand-in -- this is framed as a
    same-department coverage suggestion drawn from CURRENT faculty (there are
    no dedicated substitute-teacher posts), picked by: same-subject + free
    first, else any free faculty, tiebroken by lowest current workload.

    busy_teacher_ids: optional set of teacher ids already booked (in the real
    Schedule table) at this exact timeslot -- in addition to availability_rules
    (which only reflects submitted weekly-availability blocks), so we don't
    suggest someone who is simply already teaching something else right then.
    """
    busy_teacher_ids = busy_teacher_ids or set()

    def is_free(t):
        return _teacher_available(t, timeslot, availability_rules) and t.id not in busy_teacher_ids

    same_subject_free = [
        t for t in all_teachers
        if t.id != absent_teacher.id
        and subject.field_id is not None
        and any(f.id == subject.field_id for f in t.specializations.all())
        and is_free(t)
    ]
    if same_subject_free:
        return min(same_subject_free, key=lambda t: current_workload.get(t.id, 0))

    any_free = [
        t for t in all_teachers
        if t.id != absent_teacher.id and is_free(t)
    ]
    if any_free:
        return min(any_free, key=lambda t: current_workload.get(t.id, 0))

    return None
