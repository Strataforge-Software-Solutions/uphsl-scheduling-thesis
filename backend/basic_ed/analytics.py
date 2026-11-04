"""
SHS / JHS teacher workload analytics for the Principal dashboard (the counterpart of the Dean's Analytics tab).

Everything is computed live from the LATEST generated timetables of ONE school level (every grade level's newest run that is not
superseded, for one grading period), so SHS and JHS never mix and a regenerated or edited timetable shows up on the next request.
Nothing is stored and nothing is changed here: recommendations are only suggestions.

Statuses (against the teacher's own weekly cap, Faculty.max_weekly_hours):
  over      hours > cap
  at_limit  hours >= 90 % of the cap
  under     no classes, or hours < 60 % of the cap AND at least 15 % below the level's average load
            (so a level where everybody is equally light is not flagged as a whole)
  balanced  everything else
Workload conflicts: overload, a day above the level's periods-per-teacher-day limit, two classes at the same time, a class
outside the teacher's availability / preferred hours, and a class whose subject is outside the teacher's specialization.
Recommendations move a whole subject-in-a-section (all its weekly periods) from an overloaded or at-limit teacher to a teacher who
(1) holds the subject's specialization, (2) is free at every one of those times and inside their availability, (3) stays within the
weekly cap and the daily limit after taking it, preferring the lightest-loaded. Moves are planned one after another, so two
suggestions never pile onto the same teacher beyond the limits.
"""
from collections import defaultdict
from statistics import pstdev

from . import models as m
from .engine import eligible, to_min

UNDER_PCT = 0.60
AT_LIMIT_PCT = 0.90
UNDER_BELOW_MEAN = 0.85
DAY_ORDER = [d for d, _ in m.DAYS]
DAY_NAME = dict(m.DAYS)


def _hours(e):
    return (to_min(e.end_time) - to_min(e.start_time)) / 60.0


def _fmt(h):
    return round(h, 1)


def latest_runs(level, academic_year, period):
    return list(m.ScheduleRun.objects.filter(level=level, academic_year=academic_year, grading_period=period)
                .exclude(status="superseded"))


def choose_period(level, academic_year, wanted=None):
    """(selected period, [periods that have a timetable])."""
    have = sorted(set(m.ScheduleRun.objects.filter(level=level, academic_year=academic_year).exclude(status="superseded")
                      .values_list("grading_period", flat=True)))
    if wanted and int(wanted) in have:
        return int(wanted), have
    if have:
        newest = (m.ScheduleRun.objects.filter(level=level, academic_year=academic_year).exclude(status="superseded")
                  .order_by("-created_at").first())
        return (newest.grading_period if newest else have[0]), have
    return (int(wanted) if wanted else 1), have


class _State:
    """Mutable what-if view of every teacher, used to plan non-clashing moves."""

    def __init__(self, faculty, entries, config):
        self.cap_day = config.max_periods_per_teacher_day or 99
        self.hours = defaultdict(float)
        self.day_periods = defaultdict(lambda: defaultdict(int))
        self.busy = defaultdict(list)           # fid -> [(day, start, end)]
        for e in entries:
            if e.teacher_id:
                self.hours[e.teacher_id] += _hours(e)
                self.day_periods[e.teacher_id][e.day] += 1
                self.busy[e.teacher_id].append((e.day, to_min(e.start_time), to_min(e.end_time)))
        self.avail, self.unavail = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
        for f in faculty:
            for a in f.availability.all():
                (self.avail if a.available else self.unavail)[f.id][a.day].append((to_min(a.start_time), to_min(a.end_time)))

    def in_window(self, fac, day, s, e):
        for us, ue in self.unavail[fac.id].get(day, []):
            if s < ue and e > us:
                return False
        if self.avail.get(fac.id) and not any(s >= ws and e <= we for ws, we in self.avail[fac.id].get(day, [])):
            return False
        if fac.preferred_start and fac.preferred_end and (s < to_min(fac.preferred_start) or e > to_min(fac.preferred_end)):
            return False
        return True

    def can_take(self, fac, group):
        """True when `fac` could teach every period of `group` without breaking the weekly cap, the day limit, a clash or availability."""
        add_h = sum(_hours(e) for e in group)
        if self.hours[fac.id] + add_h > fac.max_weekly_hours + 1e-9:
            return False
        per_day = defaultdict(int)
        for e in group:
            s, en = to_min(e.start_time), to_min(e.end_time)
            if not self.in_window(fac, e.day, s, en):
                return False
            if any(d == e.day and s < b and en > a for d, a, b in self.busy[fac.id]):
                return False
            per_day[e.day] += 1
        return all(self.day_periods[fac.id][d] + n <= self.cap_day for d, n in per_day.items())

    def move(self, src_id, dst_id, group):
        for e in group:
            s, en = to_min(e.start_time), to_min(e.end_time)
            h = _hours(e)
            self.hours[src_id] -= h
            self.hours[dst_id] += h
            self.day_periods[src_id][e.day] -= 1
            self.day_periods[dst_id][e.day] += 1
            try:
                self.busy[src_id].remove((e.day, s, en))
            except ValueError:
                pass
            self.busy[dst_id].append((e.day, s, en))


def build(level, academic_year, period=None):
    config = m.SchoolLevelConfig.objects.get(level=level)
    period, periods = choose_period(level, academic_year, period)
    runs = latest_runs(level, academic_year, period)
    faculty = list(m.Faculty.objects.filter(level=level, is_active=True, user__is_active=True)
                   .select_related("user", "strand").prefetch_related("availability").order_by("user__last_name", "user__first_name"))
    entries = list(m.ScheduleEntry.objects.filter(run__in=runs).select_related("section", "subject", "run")) if runs else []
    fac_by_id = {f.id: f for f in faculty}
    by_teacher = defaultdict(list)
    for e in entries:
        if e.teacher_id in fac_by_id:
            by_teacher[e.teacher_id].append(e)
    unassigned = [e for e in entries if not e.teacher_id]

    st = _State(faculty, entries, config)
    rows, conflicts = [], []

    def add_conflict(kind, severity, f, message, suggestion):
        conflicts.append({"kind": kind, "severity": severity, "teacher_id": f.id, "teacher": f.full_name,
                          "message": message, "suggestion": suggestion})

    for f in faculty:
        es = by_teacher[f.id]
        hours = sum(_hours(e) for e in es)
        subj = {}
        for e in es:
            k = e.subject_code
            d = subj.setdefault(k, {"code": e.subject_code, "name": e.subject_name, "learning_area": e.learning_area,
                                    "sections": set(), "periods": 0, "hours": 0.0})
            d["sections"].add(e.section.name)
            d["periods"] += 1
            d["hours"] += _hours(e)
        sections = {e.section_id for e in es}
        days = defaultdict(float)
        for e in es:
            days[e.day] += _hours(e)
        cap = f.max_weekly_hours or config.max_teacher_hours
        pct = hours / cap if cap else 0
        rows.append({
            "faculty_id": f.id, "full_name": f.full_name, "employee_id": f.employee_id, "department": f.department,
            "strand": f.strand.code if f.strand else "", "specializations": [x.strip() for x in (f.specializations or "").split(";") if x.strip()],
            "available_days": sorted({a.day for a in f.availability.all() if a.available}, key=DAY_ORDER.index),
            "hours": _fmt(hours), "max_hours": cap, "load_pct": round(pct * 100), "periods": len(es), "sections": len(sections),
            "subject_count": len(subj),
            "subjects": [{"code": d["code"], "name": d["name"], "sections": sorted(d["sections"]), "periods": d["periods"], "hours": _fmt(d["hours"])}
                         for d in sorted(subj.values(), key=lambda x: -x["hours"])],
            "hours_by_day": {d: _fmt(days[d]) for d in DAY_ORDER if d in days},
            "spare_hours": _fmt(max(0.0, cap - hours)), "over_hours": _fmt(max(0.0, hours - cap)),
        })

        # ---- conflicts
        if hours > cap + 1e-9:
            add_conflict("overload", "error", f, f"{f.full_name} teaches {_fmt(hours)} h a week; the limit is {cap} h (over by {_fmt(hours - cap)} h).",
                         "Move one of their subjects to a qualified teacher with free hours (see the recommendations).")
        for day, n in sorted(st.day_periods[f.id].items(), key=lambda kv: DAY_ORDER.index(kv[0])):
            if n > st.cap_day:
                add_conflict("daily_limit", "warning", f, f"{f.full_name} has {n} periods on {DAY_NAME[day]}; the limit is {st.cap_day} a day.",
                             "Move a period of theirs to another day, or give that class to a teacher with a lighter day (Schedules tab > Resolve).")
        ordered = sorted(es, key=lambda e: (DAY_ORDER.index(e.day), to_min(e.start_time)))
        for a, b in zip(ordered, ordered[1:]):
            if a.day == b.day and to_min(b.start_time) < to_min(a.end_time):
                add_conflict("double_booked", "error", f,
                             f"{f.full_name} is in two classes on {DAY_NAME[a.day]}: {a.subject_code} ({a.section.name}) and {b.subject_code} ({b.section.name}).",
                             "Open the Schedules tab and press Resolve on this clash, or change one teacher.")
        for e in es:
            if not st.in_window(f, e.day, to_min(e.start_time), to_min(e.end_time)):
                add_conflict("availability", "warning", f,
                             f"{f.full_name} is scheduled for {e.subject_code} ({e.section.name}) on {DAY_NAME[e.day]} {e.start_time:%H:%M}-{e.end_time:%H:%M}, outside their availability.",
                             "Move that period into their available hours or give the class to a teacher who is free then.")
                break          # one line per teacher is enough; the Schedules tab lists every period
        bad = sorted({(e.subject_code, e.subject_name) for e in es if e.subject and not eligible(f, e.subject)})
        if bad:
            add_conflict("specialization", "warning", f,
                         f"{f.full_name} teaches {', '.join(c for c, _ in bad[:4])}{'…' if len(bad) > 4 else ''} outside their specialization.",
                         "Assign these to a teacher whose specialization matches (see the recommendations), or update the teacher's specialization in the Faculty tab.")

    # ---- statuses
    loaded = [r for r in rows]
    mean_hours = sum(float(r["hours"]) for r in loaded) / len(loaded) if loaded else 0.0
    for r in rows:
        h, cap = float(r["hours"]), r["max_hours"]
        if h > cap + 1e-9:
            r["status"] = "over"
        elif cap and h >= AT_LIMIT_PCT * cap:
            r["status"] = "at_limit"
        elif h == 0 or (cap and h < UNDER_PCT * cap and h < UNDER_BELOW_MEAN * mean_hours):
            r["status"] = "under"
        else:
            r["status"] = "balanced"
        r["no_load"] = h == 0

    # ---- recommendations
    recs = []
    row_by_id = {r["faculty_id"]: r for r in rows}

    def groups_of(fid):
        g = defaultdict(list)
        for e in by_teacher[fid]:
            if e.subject_id:
                g[(e.section_id, e.subject_code)].append(e)
        return g

    moved = set()

    def plan_moves(donor_ids, target_for):
        for did in donor_ids:
            donor = fac_by_id[did]
            limit = target_for(donor)
            tries = 0
            while st.hours[did] > limit + 1e-9 and tries < 12:
                tries += 1
                excess = st.hours[did] - limit
                gs = [(k, v) for k, v in groups_of(did).items() if (did, k) not in moved and not any(x.id in moved for x in v)]
                # a group that removes the excess with least waste first, else the biggest group
                gs.sort(key=lambda kv: (0 if sum(_hours(x) for x in kv[1]) >= excess else 1,
                                         sum(_hours(x) for x in kv[1]) if sum(_hours(x) for x in kv[1]) >= excess else -sum(_hours(x) for x in kv[1])))
                done = False
                for key, grp in gs:
                    subject = grp[0].subject
                    cands = [f for f in faculty if f.id != did and eligible(f, subject) and st.can_take(f, grp)
                             and (st.hours[f.id] + sum(_hours(x) for x in grp)) <= AT_LIMIT_PCT * f.max_weekly_hours + 1e-9]
                    if not cands:
                        cands = [f for f in faculty if f.id != did and eligible(f, subject) and st.can_take(f, grp)]
                    if not cands:
                        continue
                    best = min(cands, key=lambda f: (st.hours[f.id] / (f.max_weekly_hours or 1), f.full_name))
                    gh = sum(_hours(x) for x in grp)
                    before_to = st.hours[best.id]
                    before_from = st.hours[did]
                    st.move(did, best.id, grp)
                    moved.add((did, key))
                    recs.append({
                        "from_id": did, "from": donor.full_name, "to_id": best.id, "to": best.full_name,
                        "subject": f"{grp[0].subject_code} {grp[0].subject_name}", "section": grp[0].section.name,
                        "periods": len(grp), "hours": _fmt(gh), "entry_ids": [x.id for x in grp],
                        "run_status": grp[0].run.status, "editable": grp[0].run.status in ("draft", "revision_requested"),
                        "from_hours_before": _fmt(before_from), "from_hours_after": _fmt(st.hours[did]),
                        "to_hours_before": _fmt(before_to), "to_hours_after": _fmt(st.hours[best.id]),
                        "reason": (f"{donor.full_name} is {'over the limit' if before_from > donor.max_weekly_hours else 'near the limit'} "
                                   f"({_fmt(before_from)}/{donor.max_weekly_hours} h). {best.full_name} matches the subject, is free at "
                                   f"{'all' if len(grp) > 1 else 'that'} time{'s' if len(grp) > 1 else ''}, and would have "
                                   f"{_fmt(st.hours[best.id])}/{best.max_weekly_hours} h."),
                    })
                    done = True
                    break
                if not done:
                    break

    over_ids = [r["faculty_id"] for r in sorted(rows, key=lambda r: -float(r["over_hours"])) if r["status"] == "over"]
    plan_moves(over_ids, lambda f: f.max_weekly_hours)
    unresolved_over = [fid for fid in over_ids if st.hours[fid] > fac_by_id[fid].max_weekly_hours + 1e-9]
    for fid in unresolved_over:
        add_conflict("no_replacement", "error", fac_by_id[fid],
                     f"No qualified, free teacher can take any more of {fac_by_id[fid].full_name}'s classes.",
                     "Hire or assign another teacher with this specialization, widen a teacher's availability, or reduce the sections.")
    # lighten teachers sitting at the limit when somebody qualified is clearly under-used
    under_exists = any(r["status"] == "under" for r in rows)
    if under_exists:
        at_ids = [r["faculty_id"] for r in sorted(rows, key=lambda r: -r["load_pct"]) if r["status"] == "at_limit"]
        plan_moves(at_ids, lambda f: AT_LIMIT_PCT * f.max_weekly_hours - 0.01)
    # a rebalance move out of an at-limit teacher must not push anyone over: can_take already guarantees the cap.

    # ---- final numbers after nothing was applied: report current state (what-if is only in recs)
    hrs = [float(r["hours"]) for r in rows]
    status_counts = defaultdict(int)
    for r in rows:
        status_counts[r["status"]] += 1
    day_hours = defaultdict(float)
    for e in entries:
        day_hours[e.day] += _hours(e)
    run_status = defaultdict(float)
    for e in entries:
        run_status[e.run.status] += _hours(e)
    newest = max((r.created_at for r in runs), default=None)
    if unassigned:
        conflicts.append({"kind": "no_teacher", "severity": "error", "teacher_id": None, "teacher": "",
                          "message": f"{len(unassigned)} class period(s) have no teacher.",
                          "suggestion": "Open the Schedules tab and press Resolve, or choose a teacher for them."})
    return {
        "level": level, "academic_year": academic_year.label, "period": period, "periods": periods,
        "has_schedule": bool(runs), "runs": [{"id": r.id, "grade_level": r.grade_level, "version": r.version, "status": r.status} for r in runs],
        "generated_at": newest.isoformat() if newest else None,
        "thresholds": {"under_pct": int(UNDER_PCT * 100), "at_limit_pct": int(AT_LIMIT_PCT * 100), "max_periods_per_day": st.cap_day,
                       "period_minutes": config.period_minutes},
        "summary": {
            "teachers": len(rows), "with_load": sum(1 for h in hrs if h > 0), "total_hours": _fmt(sum(hrs)),
            "average_hours": _fmt(mean_hours), "std_dev": _fmt(pstdev(hrs) if len(hrs) > 1 else 0.0),
            "over": status_counts["over"], "at_limit": status_counts["at_limit"], "under": status_counts["under"],
            "balanced": status_counts["balanced"], "conflicts": len(conflicts), "recommendations": len(recs),
            "classes": len(entries),
        },
        "teachers": rows, "conflicts": conflicts, "recommendations": recs,
        "hours_by_day": {d: _fmt(day_hours[d]) for d in DAY_ORDER if d in day_hours},
        "hours_by_status": {k: _fmt(v) for k, v in run_status.items()},
    }
