"""
Resolve for SHS / JHS timetables: fixes the errors the validation finds (teacher / room / section double-booking, a class in recess or
lunch, outside the grade window, unqualified or unavailable teacher, wrong room, missing periods) one at a time.

For each error it tries, in order, the changes that can fix it -- another teacher, another room, another day / period, or (for a
missing period) a new free period -- and KEEPS a change only when the timetable is re-validated with every hard rule and ends with
fewer problems and no new one. Otherwise the change is undone. Nothing is forced and no rule is relaxed. What cannot be fixed is
returned with the reason (e.g. "no other qualified teacher is free").
"""
import time as _time
from collections import defaultdict

from django.db import transaction

from .engine import DAY_KEYS, build_grid, eligible, to_min, to_time
from .models import Faculty, GradeWindow, Room, ScheduleEntry, SchoolLevelConfig, Section, CurriculumSubject
from .services import log, refresh_validation, validate_run

TEACHER_KINDS = {"teacher_conflict", "not_qualified", "teacher_unavailable", "no_teacher", "inactive_teacher"}
ROOM_KINDS = {"room_conflict", "room_type", "room_capacity", "no_room", "bad_room"}
MOVE_KINDS = {"section_conflict", "outside_window", "during_break", "teacher_conflict", "room_conflict", "teacher_unavailable"}
BUDGET_SECONDS = 40


class _Undo(Exception):
    pass


def _errors(run):
    return [i for i in validate_run(run) if i["severity"] == "error"]


def _score(errs):
    """(set of (kind, message) of every error except missing periods, number of periods still missing)."""
    return ({(i["kind"], i["message"]) for i in errs if i["kind"] != "missing_sessions"},
            sum(i.get("missing", 1) for i in errs if i["kind"] == "missing_sessions"))


def _better(old, new):
    """Fewer problems and not a single new one."""
    o_set, o_miss = old
    n_set, n_miss = new
    return n_set <= o_set and (len(n_set) + n_miss) < (len(o_set) + o_miss)


class _Run:
    def __init__(self, run):
        self.run = run
        self.cfg = SchoolLevelConfig.objects.get(level=run.level)
        self.window = GradeWindow.objects.get(level=run.level, grade_level=run.grade_level)
        self.grid = build_grid(self.cfg, self.window)
        self.faculty = list(Faculty.objects.filter(level=run.level, is_active=True, user__is_active=True).select_related("user"))
        floor = self.cfg.floor
        self.rooms = [r for r in Room.objects.filter(level=run.level, building=self.cfg.building, is_active=True)
                      if floor is None or r.floor == floor]

    def teachers_for(self, subject, exclude=None):
        load = defaultdict(int)
        for e in self.run.entries.all():
            if e.teacher_id:
                load[e.teacher_id] += to_min(e.end_time) - to_min(e.start_time)
        c = [f for f in self.faculty if f.id != exclude and eligible(f, subject)]
        return sorted(c, key=lambda f: (load[f.id], f.id))

    def rooms_for(self, subject, section, exclude=None):
        c = [r for r in self.rooms if r.id != exclude and r.room_type == subject.required_room_type and r.capacity >= section.student_count]
        return sorted(c, key=lambda r: (r.capacity, r.id))

    def slots(self):
        return [(d, s, e) for d in DAY_KEYS for s, e in self.grid]


def _attempt(run, change, before):
    """Apply change() inside a savepoint; keep it only when the re-validated timetable is strictly better."""
    try:
        with transaction.atomic():
            change()
            after = _score(_errors(run))
            if not _better(before, after):
                raise _Undo()
        return True
    except _Undo:
        return False


def _fix_entry(ctx, entry, kind, before):
    """Returns a description of the change that fixed `entry`, or None."""
    run, subject, section = ctx.run, entry.subject, entry.section
    if subject is None:
        return None
    t_old, r_old = entry.teacher, entry.room
    d0, s0, e0 = entry.day, entry.start_time, entry.end_time

    def save(**kw):
        if "teacher" in kw and getattr(kw["teacher"], "id", None) != entry.teacher_id:
            entry.qualification_override = None
        for k, v in kw.items():
            setattr(entry, k, v)
        entry.save()

    if kind in TEACHER_KINDS:
        for f in ctx.teachers_for(subject, exclude=entry.teacher_id):
            if _attempt(run, lambda f=f: save(teacher=f), before):
                return f"{entry.subject_code} {section.name} {d0}: teacher {t_old.full_name if t_old else '(none)'} -> {f.full_name}"
            entry.teacher = t_old
    if kind in ROOM_KINDS:
        for r in ctx.rooms_for(subject, section, exclude=entry.room_id):
            if _attempt(run, lambda r=r: save(room=r), before):
                return f"{entry.subject_code} {section.name} {d0}: room {r_old.name if r_old else '(none)'} -> {r.name}"
            entry.room = r_old
    if kind in MOVE_KINDS or kind in TEACHER_KINDS or kind in ROOM_KINDS:
        busy = {(e.day, to_min(e.start_time)) for e in run.entries.filter(section=section).exclude(pk=entry.pk)}
        for d, s, e in ctx.slots():
            if (d, s) in busy or (d, s) == (d0, to_min(s0)):
                continue
            if _attempt(run, lambda d=d, s=s, e=e: save(day=d, start_time=to_time(s), end_time=to_time(e)), before):
                return f"{entry.subject_code} {section.name}: {d0} {s0:%H:%M} -> {d} {to_time(s):%H:%M}"
            entry.day, entry.start_time, entry.end_time = d0, s0, e0
    return None


def _place_missing(ctx, section_id, code, before):
    run = ctx.run
    section = Section.objects.get(pk=section_id)
    subject = run.entries.filter(section_id=section_id, subject_code=code).select_related("subject").first()
    subject = subject.subject if subject else None
    if subject is None:
        subject = CurriculumSubject.objects.filter(level=run.level, academic_year=run.academic_year, grade_level=run.grade_level,
                                                   code=code, is_active=True, grading_period__in=[0, run.grading_period]).first()
    if subject is None:
        return None
    mine = list(run.entries.filter(section=section, subject=subject))
    same_day = {e.day for e in mine}
    busy = {(e.day, to_min(e.start_time)) for e in run.entries.filter(section=section)}
    teachers = ([mine[0].teacher] if mine and mine[0].teacher_id else []) + [f for f in ctx.teachers_for(subject) if not mine or f.id != mine[0].teacher_id]
    rooms = ([mine[0].room] if mine and mine[0].room_id else []) + [r for r in ctx.rooms_for(subject, section) if not mine or r.id != mine[0].room_id]
    slots = sorted(ctx.slots(), key=lambda x: (x[0] in same_day, DAY_KEYS.index(x[0]), x[1]))
    for d, s, e in slots:
        if (d, s) in busy:
            continue
        for f in teachers[:6]:
            for r in rooms[:4]:
                made = []

                def add(d=d, s=s, e=e, f=f, r=r):
                    made.append(ScheduleEntry.objects.create(
                        run=run, section=section, subject=subject, subject_code=subject.code, subject_name=subject.name,
                        learning_area=subject.learning_area, teacher=f, room=r, day=d, start_time=to_time(s), end_time=to_time(e)))
                if _attempt(run, add, before):
                    return f"{subject.code} {section.name}: added a missing period on {d} {to_time(s):%H:%M} ({f.full_name}, {r.name})"
    return None


def resolve_run(run, user, only=None):
    """Fix as many errors of `run` as possible. only = {"kind", "section", "subject_code"} limits it to one problem.
    Returns {"resolved": [str], "unresolved": [{"message", "reason"}], "issues": [...]}."""
    ctx = _Run(run)
    resolved, unresolved, tried = [], [], set()
    started = _time.monotonic()
    while _time.monotonic() - started < BUDGET_SECONDS:
        errs = _errors(run)
        if only:
            errs = [i for i in errs if i["kind"] == only.get("kind") and (not only.get("section") or i.get("section") == int(only["section"]))
                    and (not only.get("subject_code") or i.get("subject_code") == only["subject_code"])]
        todo = next((i for i in errs if (i["kind"], i["message"]) not in tried), None)
        if todo is None:
            break
        tried.add((todo["kind"], todo["message"]))
        before = _score(_errors(run))
        done = None
        if todo["kind"] == "missing_sessions":
            for _ in range(todo.get("missing", 1)):
                before = _score(_errors(run))
                fx = _place_missing(ctx, todo["section"], todo["subject_code"], before)
                if fx is None:
                    break
                done = (done + "; " if done else "") + fx
        elif todo.get("entry"):
            entry = ScheduleEntry.objects.select_related("section", "subject", "teacher__user", "room").filter(pk=todo["entry"]).first()
            if entry:
                done = _fix_entry(ctx, entry, todo["kind"], before)
        if done:
            resolved.append(done)
            tried.discard((todo["kind"], todo["message"]))
        else:
            unresolved.append({"message": todo["message"], "reason": _why(todo)})
    if resolved:
        log(run, "resolved", user, f"{len(resolved)} problem(s) fixed automatically")
    issues = refresh_validation(run)
    return {"resolved": resolved, "unresolved": unresolved, "issues": issues}


def _why(i):
    k = i["kind"]
    if k == "missing_sessions":
        return "No free period exists where this section, a qualified teacher and a suitable room are all free. Free another period of this section first, add a teacher with the right specialization, or lengthen the day."
    if k in TEACHER_KINDS:
        return ("No other qualified teacher is free at that time, and no other period works. Add a teacher with the right specialization or "
                "change the teacher's availability. If the clash is with another grade's timetable that was made before recess/lunch were "
                "set, regenerate that grade too.")
    if k in ROOM_KINDS:
        return "No other room of the right type and size is free. Add a room for this level or reduce the section size."
    if k == "overload":
        return "A teacher teaches more than the weekly limit. Assign some of their classes to another qualified teacher (Teacher on a period) or raise the limit in Faculty."
    return "No other period fixes this without breaking another rule."
