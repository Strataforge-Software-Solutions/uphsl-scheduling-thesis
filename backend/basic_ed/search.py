"""
SHS / JHS timetable search: backtracking with MRV and forward checking (replaces the plain greedy as the generator).

Variables  -- every period of every (section, subject). Periods of one subject are handled as one task: they share one teacher and at
              most PER_DAY of them fall on one day, as before.
Values     -- (day, period slot, teacher). The room is taken when the period is placed (home room first, then any free room of the
              right type and size, as before); forward checking also checks that a free room is left, so a time without rooms is never
              offered.
Order      -- variable: pinned teachers first, then the fewest valid choices left (MRV), then the fewest qualified teachers.
              value: the teacher's Preferred times first (engine.teacher_time_rule), then the old greedy preferences -- lightest-loaded
              teacher, a day this subject is not on yet, the section's lightest day, the earliest period.
Forward checking -- after each placement every task that shares the section, the teacher or a room is re-filtered; if a period that still
              had valid choices has none left, the placement is undone and the next value is tried (backtracking).
All or nothing per subject -- a subject that cannot get ALL its periods is not placed at all (as before) and is reported with the reason.
Grade 11 whole-year subjects -- one linked unit: all periods repeat the other term's day, time, teacher and room, placed first and never
              moved by the search. If any of them cannot repeat, the subject is reported, NOT placed at new times.
Left out    -- a subject is left out only as a last resort. When a complete pass still leaves something out, the search keeps looking for
              a timetable that leaves out fewer periods (branch and bound: a branch that already leaves out as much is not explored).
              Subjects that cannot be completed in any timetable are left out at once.
Budget     -- a step limit and a time limit (settings.BASIC_ED_SEARCH); when one runs out the best result so far is kept.
Fallback   -- only when the search leaves out something that could be placed: the old greedy with its shuffled restarts (accepted only if it
              keeps every hard rule; Grade 11 whole-year subjects must repeat exactly), then shuffled searches that must beat the best.
              The result that places the most periods is used, so the generator is never worse than the old one. One seed per run.

Hard rules (never relaxed): one class at a time per teacher / room / section, qualified (or pinned) teacher, teacher availability, other
grades' timetables, weekly hours limit, daily period limit, room type and size, the grade's periods (never on a break).
"""
import random
import sys
import time
from collections import defaultdict

from django.conf import settings

from .engine import DAY_KEYS, _free_for_teacher, eligible, teacher_time_rule, to_min

DEFAULT_LIMITS = {"max_steps": 100_000, "time_seconds": 10.0, "restarts": 2}
PER_DAY = 2                     # at most 2 periods of one subject for one section on one day (unchanged rule)
DAY_INDEX = {d: i for i, d in enumerate(DAY_KEYS)}


def limits():
    """The search limits, from settings.BASIC_ED_SEARCH (one place), with the defaults above."""
    out = dict(DEFAULT_LIMITS)
    out.update(getattr(settings, "BASIC_ED_SEARCH", None) or {})
    return out


class _Budget(Exception):
    pass


class Task:
    __slots__ = ("idx", "section", "subject", "need", "cands", "pinned", "n_qual", "values", "rooms", "placed", "teacher",
                 "day_count", "fixed", "skipped", "fixed_teacher", "fixed_rows", "tier")

    def __init__(self, idx, section, subject, need, cands, pinned, n_qual):
        self.idx, self.section, self.subject, self.need = idx, section, subject, need
        self.cands, self.pinned, self.n_qual = cands, pinned, n_qual
        self.values, self.rooms = [], []
        self.placed = []                  # [(day, si, fac, room)] (the fixed ones first)
        self.fixed = 0                    # how many of `placed` are fixed (Grade 11 repeats)
        self.teacher = None
        self.fixed_teacher = None         # set by a Grade 11 repeat: the remaining periods keep that teacher
        self.fixed_rows = []              # the repeated (Grade 11) periods: never moved by the search
        self.tier = {}                    # value -> availability tier (engine.teacher_time_rule): Preferred times are tried first
        self.day_count = defaultdict(int)
        self.skipped = False

    @property
    def left(self):
        return self.need - len(self.placed)


class _State:
    def __init__(self, P, grid):
        self.P, self.grid = P, grid
        self.taken_sec = defaultdict(set)
        self.taken_teacher = defaultdict(set)
        self.taken_room = defaultdict(set)
        for rid, v in P.busy_room.items():
            self.taken_room[rid] |= v
        self.minutes = defaultdict(int, P.teacher_minutes)
        self.teacher_day = defaultdict(int)
        self.sec_day = defaultdict(int)
        self.cap_day = P.config.max_periods_per_teacher_day
        self.max_min = {}

    def max_minutes(self, fac):
        m = self.max_min.get(fac.id)
        if m is None:
            m = self.max_min[fac.id] = (fac.max_weekly_hours or self.P.config.max_teacher_hours) * 60
        return m

    def free_room(self, task, key):
        for r in task.rooms:
            if key not in self.taken_room[self.P.canon(r.id)]:
                return r
        return None

    def why_not(self, task, v):
        """'' when the value can be used now, else the rule that blocks it (used for the reasons)."""
        day, si, fac = v
        s, e = self.grid[si]
        key = (day, s)
        if task.teacher is not None and fac.id != task.teacher.id:
            return "teacher"
        if task.day_count[day] >= PER_DAY:
            return "per_day"
        if key in self.taken_sec[task.section.id]:
            return "section"
        if key in self.taken_teacher[fac.id]:
            return "teacher_busy"
        if self.minutes[fac.id] + (e - s) > self.max_minutes(fac):
            return "weekly"
        if self.teacher_day[(fac.id, day)] >= self.cap_day:
            return "daily"
        if self.free_room(task, key) is None:
            return "room"
        return ""

    def valid(self, task, v):
        return not self.why_not(task, v)

    def place(self, task, v, room=None):
        day, si, fac = v
        s, e = self.grid[si]
        key = (day, s)
        room = room or self.free_room(task, key)
        self.taken_sec[task.section.id].add(key)
        self.taken_teacher[fac.id].add(key)
        self.taken_room[self.P.canon(room.id)].add(key)
        self.minutes[fac.id] += e - s
        self.teacher_day[(fac.id, day)] += 1
        self.sec_day[(task.section.id, day)] += 1
        task.day_count[day] += 1
        task.placed.append((day, si, fac, room))
        if task.teacher is None:
            task.teacher = fac
        return room

    def unplace(self, task):
        day, si, fac, room = task.placed.pop()
        s, e = self.grid[si]
        key = (day, s)
        self.taken_sec[task.section.id].discard(key)
        self.taken_teacher[fac.id].discard(key)
        self.taken_room[self.P.canon(room.id)].discard(key)
        self.minutes[fac.id] -= e - s
        self.teacher_day[(fac.id, day)] -= 1
        self.sec_day[(task.section.id, day)] -= 1
        task.day_count[day] -= 1
        if len(task.placed) == 0:
            task.teacher = task.fixed_teacher


def _rooms_for(P, sec, sub):
    want = sub.required_room_type
    pool = [r for r in P.rooms if r.room_type == want and r.capacity >= sec.student_count]
    if sec.home_room_id and want == "classroom":
        pool.sort(key=lambda r: r.id != sec.home_room_id)
    return pool


def _period_label(P, run):
    try:
        from .structure import period_name
        return period_name(P.level, P.grade_level, run.grading_period)
    except Exception:
        return "the other term"


def _fmt_h(minutes):
    return f"{round(minutes / 60.0, 1):g}"


def build_tasks(P):
    """(tasks, unresolved, fixed_entries): every (section, subject) to place, the Grade 11 repeats placed as one linked unit, and the
    subjects that cannot even start (reported). Mirrors the old greedy's set-up (pins, homeroom adviser, eligible teachers)."""
    grid = P.grids.get(P.grade_level, [])
    st = _State(P, grid)
    tasks, unresolved = [], []
    slot_of = {s: i for i, (s, _e) in enumerate(grid)}

    # Grade 11 whole-year subjects: the other term's periods, grouped per (section, subject)
    anchor = defaultdict(list)
    sec_ids = {s.id for s in P.sections}
    for a in getattr(P, "anchor", []):
        if a.section_id in sec_ids and a.subject_id:
            anchor[(a.section_id, a.subject_id)].append(a)

    idx = 0
    for sec in P.sections:
        for sub in P.subjects_for(sec):
            cands = [f for f in P.faculty if eligible(f, sub)]
            pin = P.pinned.get((sec.id, sub.id))
            if sub.category == "guidance" and sec.adviser_id and not pin:
                pin = sec.adviser
            task = Task(idx, sec, sub, sub.sessions_per_week, [pin] if pin else cands, pin, len(cands))
            idx += 1
            task.rooms = _rooms_for(P, sec, sub)
            linked = anchor.get((sec.id, sub.id))
            if linked:
                # one linked unit: every period repeats exactly, or the subject is reported (never placed at new times)
                why = ""
                for a in sorted(linked, key=lambda x: (DAY_INDEX.get(x.day, 9), x.start_time)):
                    s0, e0 = to_min(a.start_time), to_min(a.end_time)
                    key = (a.day, s0)
                    when = f"{a.day} {a.start_time:%H:%M}"
                    if a.teacher is None or a.room is None or s0 not in slot_of or grid[slot_of[s0]][1] != e0:
                        why = f"its {when} period is no longer a class period of this grade's daily schedule"
                    elif not a.teacher.is_active:
                        why = f"{a.teacher.full_name} is no longer an active teacher"
                    elif key in st.taken_sec[sec.id]:
                        why = f"the section already has a class on {when}"
                    elif key in st.taken_room[P.canon(a.room_id)]:
                        why = f"room {a.room.name} is busy on {when}"
                    elif not _free_for_teacher(P, a.teacher, a.day, (s0, e0), st.taken_teacher):
                        why = f"{a.teacher.full_name} is not free on {when}"
                    elif st.minutes[a.teacher.id] + (e0 - s0) > st.max_minutes(a.teacher):
                        why = f"{a.teacher.full_name} has no free time left (weekly limit)"
                    elif st.teacher_day[(a.teacher.id, a.day)] >= st.cap_day:
                        why = f"{a.teacher.full_name} would exceed the daily period limit on {a.day}"
                    if why:
                        break
                    st.place(task, (a.day, slot_of[s0], a.teacher), room=a.room)
                if why:
                    while task.placed:
                        st.unplace(task)
                    unresolved.append(dict(section=sec, subject=sub, kind="anchor_conflict", needed=task.need, placed=0, message=(
                        f"{sub.code} {sub.name} for {sec.name}: cannot repeat it at the same day and time as "
                        f"{_period_label(P, linked[0].run)} ({why}). It was not placed at new times; free that time or change the other term.")))
                    continue
                task.fixed = len(task.placed)
                task.fixed_teacher = task.teacher
                task.fixed_rows = list(task.placed)
                if task.left <= 0:
                    tasks.append(task)        # fully repeated: kept as a placed task (never moved)
                    continue
            if not task.cands:
                unresolved.append(dict(section=sec, subject=sub, kind="no_eligible_teacher", needed=task.need, placed=0, message=(
                    f"{sub.code} {sub.name} for {sec.name}: no active {P.level} teacher is qualified for it "
                    f"(needs '{sub.specialization or sub.learning_area}').")))
                continue
            for fac in task.cands:
                for day in DAY_KEYS:
                    for si, slot in enumerate(grid):
                        if _free_for_teacher(P, fac, day, slot, defaultdict(set)):
                            task.values.append((day, si, fac))
                            task.tier[(day, si, fac)] = teacher_time_rule(P, fac, day, slot)
            tasks.append(task)
    return tasks, unresolved, st


class _Search:
    def __init__(self, P, tasks, st, rng, max_steps, deadline, beat_placed=None):
        self.P, self.st, self.rng = P, st, rng
        self.tasks = [t for t in tasks if t.left > 0]
        self.fixed_full = sum(t.need for t in tasks if t.left <= 0)     # Grade 11 subjects repeated whole (never searched)
        self.skipped_periods = 0          # periods of subjects left out so far on the current branch
        self.best_left_out = None         # fewest periods left out in a complete pass (branch and bound)
        self.max_steps, self.deadline = max_steps, deadline
        self.steps = 0
        self.limit_hit = False
        self.tie = {t.idx: rng.random() for t in self.tasks}
        self.alive = {t.idx: [v for v in t.values if st.valid(t, v)] for t in self.tasks}
        self.by_section, self.by_teacher, self.by_room = defaultdict(list), defaultdict(list), defaultdict(list)
        for t in self.tasks:
            self.by_section[t.section.id].append(t)
            for f in t.cands:
                self.by_teacher[f.id].append(t)
            for r in t.rooms:
                self.by_room[P.canon(r.id)].append(t)
        self.complete = 0
        self.best = (-1, None)
        for t in self.tasks:              # impossible even in an empty week: left out at once (they would only waste the time limit)
            if not self.feasible(t):
                t.skipped = True
        self.hopeless = sum(t.left for t in self.tasks if t.skipped)
        if beat_placed is not None:
            # only a timetable that places MORE than the best one already found is worth finding (a safe, slightly high bound)
            searchable = sum(t.left for t in self.tasks if not t.skipped)
            partial_fixed = sum(t.fixed for t in self.tasks)
            self.best_left_out = max(0, searchable - (beat_placed - self.fixed_full) + partial_fixed)
        self._snapshot()

    # ---- bookkeeping
    def _score(self):
        return sum(t.need for t in self.tasks if t.left == 0)

    def _snapshot(self):
        sc = self._score()
        if sc > self.best[0]:
            self.best = (sc, {t.idx: list(t.placed) for t in self.tasks if t.left == 0})

    def feasible(self, t):
        """Could the task still get all its remaining periods (an upper bound: distinct free slots, at most PER_DAY a day)?"""
        if t.left <= 0:
            return True
        alive = self.alive[t.idx]
        if not alive:
            return False
        by_day = defaultdict(set)
        for day, si, _f in alive:
            by_day[day].add(si)
        return sum(min(PER_DAY - t.day_count[d], len(v)) for d, v in by_day.items()) >= t.left

    def select(self):
        open_ = [t for t in self.tasks if t.left > 0 and not t.skipped]
        if not open_:
            return None
        return min(open_, key=lambda t: (0 if (t.pinned or t.fixed_teacher) else 1, len(self.alive[t.idx]), t.n_qual, -t.left, self.tie[t.idx]))

    def order(self, t):
        st, sec = self.st, t.section

        def key(v):
            day, si, fac = v
            return (t.tier.get(v, 1), st.minutes[fac.id] if t.teacher is None else 0, t.day_count[day] >= 1, t.day_count[day],
                    st.sec_day[(sec.id, day)], si, DAY_INDEX[day], fac.id)
        return sorted(self.alive[t.idx], key=key)

    def forward(self, t, v, room):
        """Re-filter the tasks this placement touches. Returns (ok, pruned) -- ok is False when a period that still had valid choices has
        none left (then the placement is undone by the caller and the next value is tried)."""
        day, si, fac = v
        touched = {x.idx: x for x in self.by_section[t.section.id]}
        touched.update({x.idx: x for x in self.by_teacher[fac.id]})
        touched.update({x.idx: x for x in self.by_room[self.P.canon(room.id)]})
        touched[t.idx] = t
        pruned, ok = [], True
        for x in touched.values():
            if x.left <= 0 or x.skipped:
                continue
            before = self.alive[x.idx]
            if x is t:
                now = [w for w in before if self.st.valid(x, w)]
            else:
                # only a choice at the same day and time, or of the same teacher, can have been affected by this placement
                fid = fac.id
                now = [w for w in before if not ((w[1] == si and w[0] == day) or w[2].id == fid) or self.st.valid(x, w)]
            if len(now) != len(before):
                pruned.append((x.idx, before))
                self.alive[x.idx] = now
            if before and not now:
                ok = False                 # a period that still had choices has none left: undo this placement (backtrack)
        return ok, pruned

    def restore(self, pruned):
        for i, before in reversed(pruned):
            self.alive[i] = before

    # ---- the search
    def run(self):
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old, 20_000))
        try:
            self._go()
        except _Budget:
            self.limit_hit = True
        finally:
            sys.setrecursionlimit(old)
        self.exhausted = not self.limit_hit
        return self.best[1] or {}

    def _go(self):
        self.steps += 1
        if self.steps > self.max_steps or time.monotonic() > self.deadline:
            raise _Budget()
        if self.best_left_out is not None and self.skipped_periods >= self.best_left_out:
            return False                   # this branch already leaves out as much as the best timetable found: no better here
        t = self.select()
        if t is None:
            self._snapshot()
            if self.skipped_periods == 0:
                return True                # everything that can be placed is placed: done
            self.best_left_out = self.skipped_periods
            return False                   # keep searching for a timetable that leaves out less (until the limits)
        started = len(t.placed) > t.fixed
        if started or self.feasible(t):
            for v in self.order(t):
                if not self.st.valid(t, v):
                    continue
                room = self.st.place(t, v)
                ok, pruned = self.forward(t, v, room)
                if t.left == 0:
                    self._snapshot()
                if ok and self._go():
                    return True
                self.restore(pruned)
                self.st.unplace(t)
        if started:
            return False                   # a started subject is never left half placed: back up
        t.skipped = True                   # last resort: leave this subject out (reported), go on with the others
        self.skipped_periods += t.left
        try:
            if self._go():
                return True
        finally:
            t.skipped = False
            self.skipped_periods -= t.left
        return False


def _reason(P, st, t, limit_hit):
    """Plain words for the Principal: why this subject could not get all its periods."""
    sub, sec = t.subject, t.section
    head = f"{sub.code} {sub.name} for {sec.name}: "
    grid = st.grid
    if not t.values:
        wins = [f for f in t.cands if P.avail.get(f.id)]
        if wins and len(wins) == len(t.cands):
            g0, g1 = (grid[0][0], grid[-1][1]) if grid else (0, 0)
            names = ", ".join(f.full_name for f in wins[:3])
            return "no_slot", head + (f"the teacher's available time does not match the grade's daily schedule "
                                      f"({names}; classes run {g0 // 60}:{g0 % 60:02d}-{g1 // 60}:{g1 % 60:02d}).")
        return "no_slot", head + "no qualified teacher is free at any time (all are unavailable or busy in other grades' timetables)."
    count, blockers = defaultdict(int), defaultdict(int)
    for v in t.values:
        why = st.why_not(t, v)
        count[why] += 1
        blockers[(why, v[2].id)] += 1
    if count.get("") and limit_hit:
        return "search_limit", head + "the search time limit was reached before this subject could be placed. Generate again or raise the limit."
    if not any(r.room_type == sub.required_room_type for r in P.rooms):
        return "no_slot", head + f"there is no {sub.required_room_type.replace('_', ' ')} in {P.config.building} for it."
    if not t.rooms:
        return "no_slot", head + f"no room with enough capacity (the section has {sec.student_count} students)."
    # the whole subject must fit in a teacher's week: compare what it needs with each qualified teacher's hours left
    need_min = t.need * ((grid[0][1] - grid[0][0]) if grid else 60)
    if t.cands and all(st.max_minutes(f) - st.minutes[f.id] < need_min for f in t.cands):
        fac = max(t.cands, key=lambda f: st.max_minutes(f) - st.minutes[f.id])
        return "no_slot", head + (f"teacher {fac.full_name} has no free time left "
                                  f"(weekly limit {_fmt_h(st.minutes[fac.id])}/{_fmt_h(st.max_minutes(fac))} hrs; "
                                  f"this subject needs {_fmt_h(need_min)} hrs).")
    main = max((k for k in count if k), key=lambda k: count[k], default="")
    if main == "weekly":
        fac = min(t.cands, key=lambda f: st.minutes[f.id])
        return "no_slot", head + (f"teacher {fac.full_name} has no free time left "
                                  f"(weekly limit {_fmt_h(st.minutes[fac.id])}/{_fmt_h(st.max_minutes(fac))} hrs).")
    if main == "daily":
        fac = t.cands[0]
        return "no_slot", head + f"teacher {fac.full_name} already has the daily limit of {st.cap_day} periods on every day they are free."
    if main == "room":
        return "no_slot", head + "no free room of the right type and size is left at the times the teacher and section are free."
    if main == "section":
        return "no_slot", head + "the section has no free period left at the times its qualified teachers are free."
    if main == "teacher_busy":
        return "no_slot", head + "its qualified teachers are already teaching at every time the section is free."
    return "no_slot", head + f"not enough free periods to place all {t.need} periods (at most {PER_DAY} a day)."


def _better(a, b):
    """True when result a places more periods than b (on a tie the earlier one, the search, is kept)."""
    return b is None or len(a[0]) > len(b[0])


def _from_assignments(P, assignments):
    """An outside result (the old greedy) turned into this module's result: Grade 11 whole-year subjects are kept only when they repeat
    the other term exactly (otherwise they are reported, as in the search), and the reasons use the same plain words. Returns
    (assignments, unresolved) or None when the result breaks a hard rule (then it is not used)."""
    from .checker import check
    tasks, unresolved, _st = build_tasks(P)
    grid = P.grids.get(P.grade_level, [])
    slot_of = {s0: i for i, (s0, _e) in enumerate(grid)}
    by_key = {(t.section.id, t.subject.id): t for t in tasks}
    rows = defaultdict(list)
    for a in assignments:
        t = by_key.get((a["section"].id, a["subject"].id))
        if t is not None and a["start"] in slot_of:
            rows[t.idx].append((a["day"], slot_of[a["start"]], a["teacher"], a["room"]))
    placed = {}
    for t in tasks:
        got = rows.get(t.idx, [])
        if len(got) != t.need:
            continue
        if t.fixed_rows:
            want = {(d, si, f.id, P.canon(r.id)) for d, si, f, r in t.fixed_rows}
            if not want <= {(d, si, f.id, P.canon(r.id)) for d, si, f, r in got}:
                continue                  # a whole-year subject placed at new times: not accepted
        placed[t.idx] = got
    res = _materialize(P, tasks, unresolved, placed, False)
    return res if not check(P, res[0]) else None


def solve(P, seed=0, stats=None, max_steps=None, time_seconds=None, restarts=None):
    """Returns (assignments, unresolved) like the old engine.solve.
    1. the backtracking search (MRV + forward checking + branch and bound), with about half of the time limit;
    2. only when it leaves something out that could be placed: the old greedy with its shuffled restarts as a fallback (checked against
       every hard rule; Grade 11 whole-year subjects must repeat exactly), and then shuffled searches that must beat the best result;
    the result that places the most periods is kept. `stats` (a dict, optional) receives the figures of the run."""
    from .engine import solve_greedy
    lim = limits()
    max_steps = int(max_steps if max_steps is not None else lim["max_steps"])
    time_seconds = float(time_seconds if time_seconds is not None else lim["time_seconds"])
    restarts = int(restarts if restarts is not None else lim["restarts"])
    t0 = time.monotonic()
    end = t0 + time_seconds
    steps_total, attempts, any_limit, method = 0, 0, False, "search"

    def search(attempt, share, beat=None):
        nonlocal steps_total, attempts, any_limit
        rng = random.Random(seed + attempt)
        tasks, unresolved, st = build_tasks(P)
        if attempt:
            rng.shuffle(tasks)            # another order among equal choices
        S = _Search(P, tasks, st, rng, max_steps, time.monotonic() + max(0.0, share), beat_placed=beat)
        placed = S.run()
        attempts += 1
        steps_total += S.steps
        any_limit = any_limit or S.limit_hit
        return _materialize(P, tasks, unresolved, placed, S.limit_hit), S

    def avoidable(res):
        return [u for u in res[1] if u["kind"] not in ("no_eligible_teacher", "anchor_conflict")]

    best, S0 = search(0, (end - time.monotonic()) * 0.5)
    if avoidable(best) and not S0.exhausted:
        g = solve_greedy(P, seed=seed)                 # fallback 1: the old greedy (fast), only if it keeps every rule
        cand = _from_assignments(P, g[0])
        if cand is not None and _better(cand, best):
            best, method = cand, "greedy fallback"
        for k in range(1, restarts + 1):               # fallback 2: shuffled searches that must place more than the best so far
            left = end - time.monotonic()
            if left <= 0 or not avoidable(best):
                break
            res, _S = search(k, left / (restarts - k + 1), beat=len(best[0]))
            if _better(res, best):
                best, method = res, f"search restart {k}"
    assignments, unresolved = best
    if stats is not None:
        stats.update({"steps": steps_total, "seconds": round(time.monotonic() - t0, 3), "attempts": attempts, "limit_hit": any_limit,
                      "method": method, "placed": len(assignments), "total": sum(u["needed"] for u in unresolved) + len(assignments),
                      "max_steps": max_steps, "time_seconds": time_seconds})
    return assignments, unresolved


def _materialize(P, tasks, unresolved, placed, limit_hit):
    """The best result as assignment dicts (complete subjects only), plus a reason for every subject left out. The result is applied to
    a fresh state first, so the reasons describe the final timetable."""
    grid = P.grids.get(P.grade_level, [])
    st = _State(P, grid)
    out, unres = [], list(unresolved)
    for t in tasks:
        t.placed, t.day_count, t.teacher, t.skipped = [], defaultdict(int), t.fixed_teacher, False
    for t in tasks:
        rows = placed.get(t.idx) or (t.fixed_rows if len(t.fixed_rows) == t.need else None)
        for day, si, fac, room in rows or []:
            st.place(t, (day, si, fac), room=room)
    for t in tasks:
        if len(t.placed) == t.need:
            for n, (day, si, fac, room) in enumerate(t.placed):
                s0, e0 = grid[si]
                out.append(dict(section=t.section, subject=t.subject, teacher=fac, room=room, day=day, start=s0, end=e0,
                                anchored=n < len(t.fixed_rows)))
    for t in tasks:
        if len(t.placed) != t.need:
            kind, msg = _reason(P, st, t, limit_hit)
            unres.append(dict(section=t.section, subject=t.subject, kind=kind, needed=t.need, placed=0, message=msg))
    return out, unres
