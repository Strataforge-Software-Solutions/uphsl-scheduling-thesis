"""
Exam conflict resolver (the pop-up behind "Resolve"): an exam that could not be placed is blocked by PROGRAM (major) exams of the
same section / room. Classes never move. This module finds, for each blocked exam,
  1. the hour where it fits best -- the hour its subject's other sections already use (same subject, same time, different room, as
     in the college's exam-week schedule) first, then the earliest hour that needs the fewest changes,
  2. the major exam(s) standing in the way, and a NEW free date / hour (and room / proctor) for each of them in the exam week,
and either returns that plan (preview) or applies it in one transaction after re-checking for double-bookings.
"""
from collections import defaultdict

from django.db import IntegrityError, transaction

from engine.conflicts import _get_tolerance_minutes
from engine.models import Log, Schedule, Section, TimeSlot
from engine.scheduler import _room_preference
from curriculum.models import Subject
from faculty.models import FacultyProfile
from rooms.models import Room, DepartmentBuilding
from rooms.rules import fits_size

from .models import ExamSchedule
from .room_rules import check_exams, exam_rooms
from .services import _minutes

MAX_MOVES = 3


def _hm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


class _World:
    def __init__(self, semester, exam_period, dates, school_year):
        self.dates = list(dates)
        self.tol = _get_tolerance_minutes()
        self.rooms = list(Room.objects.filter(room_type__in=["lecture", "lab"]))
        self.faculty = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations"))
        from .proctors import ProctorPool
        self.pool = ProctorPool(self.faculty)
        self.dept_building = {d.department: d.building for d in DepartmentBuilding.objects.all()}
        self.classes = defaultdict(list)                       # weekday -> (s0, s1, teacher, room, section)
        for r in Schedule.objects.filter(section__semester=semester).select_related("timeslot"):
            t = r.timeslot
            self.classes[t.day].append((_minutes(t.start_time), _minutes(t.end_time), r.teacher_id, r.room_id, r.section_id))
        self.exams = {}                                        # exam id -> ExamSchedule
        self.by_date = defaultdict(dict)                       # date -> {exam id: (s0, s1, proctor, room, section)}
        for e in ExamSchedule.objects.select_related("timeslot", "subject", "section__program", "room"):
            self.exams[e.id] = e
            self.by_date[e.exam_date][e.id] = (_minutes(e.timeslot.start_time), _minutes(e.timeslot.end_time),
                                               e.proctor_id, e.room_id, e.section_id)
        self._slots = {}

    def slots(self, d):
        code = d.strftime("%a")[:3]
        if code not in self._slots:
            qs = [t for t in TimeSlot.objects.filter(day=code) if _minutes(t.end_time) - _minutes(t.start_time) >= 60]
            qs = qs or [t for t in TimeSlot.objects.all() if _minutes(t.end_time) - _minutes(t.start_time) >= 60]
            self._slots[code] = sorted(qs, key=lambda x: (_minutes(x.start_time), x.id))
        return self._slots[code]

    def at(self, d, s0, s1, ignore=()):
        """(class rows, {exam id: row}) overlapping the hour."""
        cls = [r for r in self.classes.get(d.strftime("%a")[:3], []) if min(s1, r[1]) > max(s0, r[0])]
        ex = {i: r for i, r in self.by_date.get(d, {}).items() if i not in ignore and min(s1, r[1]) > max(s0, r[0])}
        return cls, ex

    def is_major(self, exam_id):
        return self.exams[exam_id].subject.classification != "minor"

    def rooms_for(self, subject, section):
        ordered, _hard, _n = exam_rooms(self.rooms, section, subject,
                                        lambda r: _room_preference(r, section, subject, self.dept_building))
        return ordered

    def section_ok(self, section, cls, ex, s0, s1):
        used = sum(min(s1, r[1]) - max(s0, r[0]) for r in cls if r[4] == section.id)
        used += sum(min(s1, r[1]) - max(s0, r[0]) for r in ex.values() if r[4] == section.id)
        return used <= self.tol

    def free_room(self, rooms, cls, ex, prefer=None):
        busy = {r[3] for r in cls} | {r[3] for r in ex.values()}
        if prefer is not None and prefer not in busy:
            return prefer
        return next((r.id for r in rooms if r.id not in busy), None)

    def free_proctor(self, cls, ex, subject, prefer=None):
        """A free proctor for this subject by the rules in exams.proctors; keeps `prefer` when he/she is free and still allowed."""
        busy = {r[2] for r in cls} | {r[2] for r in ex.values()}
        if prefer is not None and prefer not in busy and self.pool.acceptable(subject, prefer):
            return prefer
        load = defaultdict(int)
        for rows in self.by_date.values():
            for r in rows.values():
                load[r[2]] += 1
        f = self.pool.pick(subject, busy, load)
        return f.id if f else None


def _relocate(w, exam, forbid, taken):
    """A new (date, slot, room id, proctor id) for a MAJOR exam that must leave `forbid` = (date, s0)."""
    rooms = w.rooms_for(exam.subject, exam.section)
    own = (exam.exam_date, exam.id)
    for d in w.dates:
        for slot in w.slots(d):
            s0, s1 = _minutes(slot.start_time), _minutes(slot.end_time)
            if (d, s0) == forbid:
                continue
            cls, ex = w.at(d, s0, s1, ignore={exam.id})
            ex = {i: r for i, r in ex.items()}
            for t in taken:                                # places already given to other exams of this plan
                if t[0] == d and min(s1, t[2]) > max(s0, t[1]):
                    ex[("t", t[5])] = (t[1], t[2], t[4], t[3], t[6])
            if not w.section_ok(exam.section, cls, ex, s0, s1):
                continue
            room = w.free_room(rooms, cls, ex)
            proc = w.free_proctor(cls, ex, exam.subject, prefer=exam.proctor_id)
            if room is not None and proc is not None:
                return d, slot, s0, s1, room, proc
    return None


def _describe(e):
    t = e.timeslot
    return {"exam_id": e.id, "subject": f"{e.subject.code} - {e.subject.title}", "section": str(e.section),
            "date": e.exam_date.isoformat(), "start": _hm(_minutes(t.start_time)), "end": _hm(_minutes(t.end_time)), "room": e.room.name}


def plan(w, pair):
    """Plan for one blocked (subject, section). Returns {"ok", "place", "moves", "reason"}."""
    subject, section = pair
    rooms = w.rooms_for(subject, section)
    sibling = {(e.exam_date, _minutes(e.timeslot.start_time)) for e in w.exams.values()
               if e.subject_id == subject.id and e.exam_date in set(w.dates)}
    cands = []
    for di, d in enumerate(w.dates):
        for slot in w.slots(d):
            s0, s1 = _minutes(slot.start_time), _minutes(slot.end_time)
            cls, ex = w.at(d, s0, s1)
            class_used = sum(min(s1, r[1]) - max(s0, r[0]) for r in cls if r[4] == section.id)
            if class_used > w.tol:
                continue                                    # a class is there: classes never move
            moves = []
            mine = {i: r for i, r in ex.items() if r[4] == section.id}
            rest = {i: r for i, r in ex.items() if i not in mine}
            if sum(min(s1, r[1]) - max(s0, r[0]) for r in mine.values()) + class_used > w.tol:
                if not all(w.is_major(i) for i in mine):
                    continue
                moves += list(mine)
                mine = {}
            room_ex = {i: r for i, r in rest.items()}
            busy_cls = {r[3] for r in cls}
            room = next((r for r in rooms if r.id not in busy_cls and r.id not in {x[3] for x in room_ex.values()}), None)
            if room is None:                                # a major exam holds the room: take it over
                for r in rooms:
                    if r.id in busy_cls:
                        continue
                    holder = [i for i, x in room_ex.items() if x[3] == r.id]
                    if holder and all(w.is_major(i) for i in holder):
                        moves += holder
                        room = r
                        break
            if room is None:
                continue
            gone = set(moves)
            cls2, ex2 = w.at(d, s0, s1, ignore=gone)
            if w.free_proctor(cls2, ex2, subject) is None:
                continue
            if len(moves) <= MAX_MOVES:
                cands.append((0 if (d, s0) in sibling else 1, len(moves), di, s0, d, slot, s0, s1, room, moves))
    cands.sort(key=lambda c: c[:4])
    for *_k, d, slot, s0, s1, room, moves in cands:
        taken, relocs, ok = [], [], True
        for i in moves:
            e = w.exams[i]
            res = _relocate(w, e, (d, s0), taken)
            if res is None:
                ok = False
                break
            nd, nslot, n0, n1, nroom, nproc = res
            taken.append((nd, n0, n1, nroom, nproc, i, e.section_id))
            relocs.append((e, nd, nslot, n0, n1, nroom, nproc))
        if not ok:
            continue
        cls2, ex2 = w.at(d, s0, s1, ignore=set(moves))
        proc = w.free_proctor(cls2, ex2, subject)
        return {"ok": True, "place": (subject, section, d, slot, s0, s1, room, proc), "moves": relocs}
    return {"ok": False, "reason": "No hour in the exam week lets this exam be placed even after moving program exams "
                                   "(classes in the way cannot move). Widen the exam week by a day or two."}


def _apply_in_memory(w, p):
    subject, section, d, slot, s0, s1, room, proc = p["place"]
    for e, nd, nslot, n0, n1, nroom, nproc in p["moves"]:
        w.by_date[e.exam_date].pop(e.id, None)
        w.by_date[nd][e.id] = (n0, n1, nproc, nroom, e.section_id)
    w.by_date[d][("new", subject.id, section.id)] = (s0, s1, proc, room.id, section.id)


def _dept_of(exam):
    return getattr(exam.subject.program, "department", None)


def pending_minor_items(semester, exam_period, school_year):
    """Gen Ed (subject, section) pairs of the semester that still have no exam in this period."""
    have = set(ExamSchedule.objects.filter(exam_period=exam_period, school_year=school_year, section__semester=semester)
               .values_list("subject_id", "section_id"))
    out = []
    for sub in Subject.objects.filter(semester=semester, classification="minor"):
        for sec in Section.objects.filter(program_id=sub.program_id, semester=semester, year_level=sub.year_level):
            if (sub.id, sec.id) not in have:
                out.append({"subject_id": sub.id, "section_id": sec.id})
    return out


def _notify_deans(registrar, moves_by_dept, semester):
    """Ask each Dean to move the program exams that block Gen Ed exams (a Dean changes only the exams of their own college)."""
    from accounts.models import User
    from notifications.models import Notification
    sent = 0
    for dept, moves in moves_by_dept.items():
        msg = (f"Registrar request ({semester}): please change the date/time of {len(moves)} {dept} exam(s) that block Gen Ed exams "
               f"(e.g. {moves[0]}). Open Exam Schedule > Registrar requests.")[:255]
        for dean in User.objects.filter(role="faculty", faculty_type="dean"):
            if dept in dean.departments:
                Notification.objects.create(recipient=dean, notif_type="conflict_alert", message=msg)
                sent += 1
    return sent


def resolve(user, *, semester, exam_period, dates, school_year, items, apply):
    """The Registrar owns the Gen Ed (minor) exams and a Dean the program (major) exams of their college:
      Registrar -> places the Gen Ed exams that need no major exam to move; for the others the Dean(s) concerned are asked
                   (notification) to change the date/time of their exams.
      Dean      -> changes the date/time of THEIR OWN major exams that block Gen Ed exams (items may be empty = every blocked one);
                   the Registrar then places the Gen Ed exams."""
    is_dean = user.role == "faculty" and getattr(user, "faculty_type", "") == "dean"
    w = _World(semester, exam_period, dates, school_year)
    if is_dean and not items:
        items = pending_minor_items(semester, exam_period, school_year)
    subjects = {s.id: s for s in Subject.objects.filter(id__in={i["subject_id"] for i in items}).select_related("program")}
    sections = {s.id: s for s in Section.objects.filter(id__in={i["section_id"] for i in items}).select_related("program")}
    plans, out, entries = [], [], []
    for it in items:
        subject, section = subjects.get(it["subject_id"]), sections.get(it["section_id"])
        if subject is None or section is None:
            continue
        if is_dean and subject.classification != "minor":
            continue
        if not is_dean and subject.classification != "minor":
            out.append({"subject": f"{subject.code} - {subject.title}", "section": str(section), "status": "blocked", "moves": [],
                        "reason": "Program (major) exams are placed by the Dean of the college."})
            continue
        if ExamSchedule.objects.filter(subject=subject, section=section, exam_period=exam_period, school_year=school_year).exists():
            continue
        p = plan(w, (subject, section))
        label = {"subject": f"{subject.code} - {subject.title}", "section": str(section)}
        if not p["ok"]:
            if not is_dean:
                out.append({**label, "status": "blocked", "reason": p["reason"], "moves": []})
            continue
        mine = [m for m in p["moves"] if _dept_of(m[0]) in (user.departments if is_dean else [])]
        if is_dean and (not p["moves"] or len(mine) != len(p["moves"])):
            continue                                        # nothing of this Dean's to move, or another college's exam is also in the way
        _apply_in_memory(w, p)
        plans.append(p)
        _s, _c, d, slot, s0, s1, room, proc = p["place"]
        moves = [{**_describe(e), "department": _dept_of(e),
                  "to": {"date": nd.isoformat(), "start": _hm(n0), "end": _hm(n1), "room": next((r.name for r in w.rooms if r.id == nroom), "")}}
                 for e, nd, nslot, n0, n1, nroom, nproc in p["moves"]]
        status_ = ("dean_moves" if is_dean else ("needs_dean" if moves else "can_place"))
        o = {**label, "status": status_, "place": {"date": d.isoformat(), "start": _hm(s0), "end": _hm(s1), "room": room.name},
             "moves": moves}
        out.append(o)
        entries.append((o, p))
    result = {"role": "dean" if is_dean else "registrar", "items": out, "applied": False, "placed": 0}
    if not apply or not plans:
        return result
    try:
        with transaction.atomic():
            for p in plans:
                subject, section = p["place"][0], p["place"][1]
                for e, nd, nslot, n0, n1, nroom, nproc in p["moves"]:
                    if not is_dean:
                        continue                              # the Registrar never changes a major exam
                    e.exam_date, e.timeslot_id, e.room_id, e.proctor_id, e.is_manual_override = nd, nslot.id, nroom, nproc, True
                    e.save(update_fields=["exam_date", "timeslot", "room", "proctor", "is_manual_override"])
                    Log.objects.create(action="UPDATE", schedule_id=e.id, user=user,
                                       details=f"Exam moved to {nd} {_hm(n0)} to free the hour for Gen Ed {subject.code} ({section.name})")
            new = []
            if not is_dean:
                for o, p in entries:
                    subject, section, d, slot, s0, s1, room, proc = p["place"]
                    if not p["moves"]:
                        new.append(ExamSchedule(subject=subject, section=section, proctor_id=proc, room=room, timeslot=slot, exam_date=d,
                                                exam_period=exam_period, school_year=school_year, created_by=user))
                        o["status"] = "placed"
                ExamSchedule.objects.bulk_create(new)
                by_dept = defaultdict(list)
                for o, p in entries:
                    for e, *_r in p["moves"]:
                        by_dept[_dept_of(e)].append(f"{e.subject.code} ({e.section.name})")
                result["requested"] = _notify_deans(user, by_dept, semester) if by_dept else 0
                for o in out:
                    if o["status"] == "needs_dean":
                        o["status"] = "requested"
            touched = ExamSchedule.objects.filter(exam_period=exam_period, school_year=school_year, section__semester=semester) \
                .select_related("subject", "section__program", "room", "timeslot")
            bad = check_exams(list(touched))["room_conflicts"]
            if bad:
                raise ValueError("; ".join(bad[:3]))
    except (IntegrityError, ValueError) as exc:
        return {**result, "detail": f"The change would create a double-booking, so nothing was changed: {exc}"}
    result.update(applied=True, placed=sum(1 for o in out if o["status"] == "placed"),
                  moved=sum(len(o["moves"]) for o in out) if is_dean else 0)
    if is_dean:
        for o in out:
            o["status"] = "moved"
    return result
