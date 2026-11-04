"""
Minor (Gen Ed) subjects for CCS, RadTech, Nursing, BAComm, Allied Health, IHM and BA (CBA) in ONE action.

1. GROUPING  Equivalent minor lectures (same code, units and title -- i.e. the same curriculum requirement) of the
             four departments are planned together. Sections are packed, largest department first, into shared
             classes whose total enrolment fits the biggest ordinary lecture room; the first section of a group
             is its host (its room is chosen for the whole group) and the others JOIN it (same teacher, room and
             time) when they are free then. Anything that does not fit, differs in units/title, or would clash gets
             its own separate section -- nothing is forced.
2. GENERATION  Runs the existing generator (engine.views.generate_schedule_view) per program, so every existing rule
             (teacher / room / student overlap, availability, room ownership, capacity, workload) still applies.
3. VALIDATION  Afterwards the whole semester is re-checked from the database. If any teacher / room / student clash
             involves a newly created class the WHOLE batch is rolled back and the clashes are reported -- an invalid
             schedule is never kept. "Resolved" is only ever reported from that fresh check.
Re-running replaces the earlier minor DRAFT classes of the chosen year level(s) and semester (no duplicates);
approved / published classes are never touched (the action is refused instead).
"""
from collections import defaultdict

from django.db import transaction
from rest_framework.test import APIRequestFactory, force_authenticate

from curriculum.models import Program, Subject
from rooms import rules as room_rules
from rooms.models import Room
from .conflict_report import DAY_ORDER, _blocks, _label, scan
from . import locks
from .models import Schedule, Section

YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
LABELS = ["CCS", "RadTech", "Nursing", "BAComm", "Allied Health", "IHM", "CBA"]
LABEL_NAME = {"CCS": "Computer Studies (CCS)", "RadTech": "Radiologic Technology (RadTech)", "Nursing": "Nursing",
              "BAComm": "BA Communication (BAComm)", "Allied Health": "Allied Health", "IHM": "International Hospitality Management (IHM)",
              "CBA": "Business Administration (BA)"}


def dept_label(program):
    d, n = (program.department or "").lower(), (program.name or "").lower()
    if "comput" in d:
        return "CCS"
    if "radiolog" in d or "radiolog" in n:
        return "RadTech"
    if "nurs" in d or "nurs" in n:
        return "Nursing"
    if "communication" in n:
        return "BAComm"
    if "allied" in d:
        return "Allied Health"
    if "hospitality" in d or "hospitality" in n or "tourism" in n:
        return "IHM"
    if "business" in d or "bsba" in n:
        return "CBA"
    return None


def target_programs():
    return [(dept_label(p), p) for p in Program.objects.order_by("name") if dept_label(p)]


def _key(subject):
    return (subject.code, subject.lec_units, subject.lab_units, " ".join((subject.title or "").lower().split()))


def _group_capacity():
    caps = list(Room.objects.filter(room_type="lecture", department__isnull=True).values_list("capacity", flat=True))
    caps = [c for c in caps if c] or [60]
    return max(caps)


def plan_groups(programs, year_levels, semester):
    """-> (sizes {(host_section_id, host_subject_id): total students}, bins, program order)."""
    sections = list(Section.objects.filter(program__in=[p for _l, p in programs], year_level__in=year_levels,
                                           semester=semester).select_related("program"))
    totals = defaultdict(int)
    for s in sections:
        totals[s.program_id] += s.student_count
    # Computer Studies programs (CS + IT) are packed and generated FIRST so their minors share one class with each other; the other
    # departments then take the seats that are left. Within each group the bigger program goes first.
    ccs = {p.id for l, p in programs if l == "CCS"}
    order = sorted([p for _l, p in programs], key=lambda p: (0 if p.id in ccs else 1, -totals[p.id], p.name))
    rank = {p.id: i for i, p in enumerate(order)}
    sections.sort(key=lambda s: (rank[s.program_id], s.name))
    limit = _group_capacity()
    subjects = defaultdict(dict)                                  # section_id -> {key: subject}
    for sub in Subject.objects.filter(program__in=order, year_level__in=year_levels, semester=semester,
                                      classification="minor", lab_units=0):
        subjects[(sub.program_id, sub.year_level)][_key(sub)] = sub
    bins = defaultdict(list)                                      # (year, key) -> [bin]
    from .shared_classes import may_share, share_rules
    rules = {y: share_rules(y, semester) for y in year_levels}    # choices made in the preview: exclusive / chosen programs only
    for sec in sections:
        for key, sub in subjects.get((sec.program_id, sec.year_level), {}).items():
            placed = False
            for b in bins[(sec.year_level, key)]:
                if sec.program_id in b["programs"]:
                    continue
                if not all(may_share(rules[sec.year_level], sec.program_id, pid, key[0]) for pid in b["programs"]):
                    continue
                if b["total"] + sec.student_count <= limit:
                    b["members"].append((sec, sub)); b["programs"].add(sec.program_id); b["total"] += sec.student_count
                    placed = True
                    break
            if not placed:
                bins[(sec.year_level, key)].append({"members": [(sec, sub)], "programs": {sec.program_id}, "total": sec.student_count})
    sizes, flat = {}, []
    for (yl, key), lst in bins.items():
        for b in lst:
            host, hsub = b["members"][0]
            if len(b["members"]) > 1:
                sizes[(host.id, hsub.id)] = b["total"]
            flat.append({"year_level": yl, "code": key[0], "title": hsub.title, "sections": len(b["members"]),
                         "students": b["total"], "planned_shared": len(b["members"]) > 1})
    return sizes, flat, order


def _call_generate(user, program, year_level, semester, school_year):
    from .views import generate_schedule_view
    req = APIRequestFactory().post("/api/engine/generate-schedule/", {
        "program_id": program.id, "year_level": year_level, "semester": semester, "school_year": school_year,
        "merge_minors": True}, format="json")
    force_authenticate(req, user=user)
    resp = generate_schedule_view(req)
    return resp.status_code, getattr(resp, "data", {}) or {}


class BatchError(Exception):
    def __init__(self, payload, status=400):
        super().__init__(payload.get("detail", ""))
        self.payload, self.status = payload, status


def generate_all(user, school_year, semester, year_level):
    """Returns (payload, http status)."""
    school_year = (school_year or "").strip()
    if not school_year or not semester or not year_level:
        return {"detail": "Choose the academic year, semester and year level."}, 400
    years = YEARS if year_level == "All" else [year_level]
    if any(y not in YEARS for y in years):
        return {"detail": f"Unknown year level: {year_level}."}, 400
    programs = target_programs()
    if not programs:
        return {"detail": "No programs of the supported departments were found."}, 400
    present = {l for l, _p in programs}
    scope = Section.objects.filter(program__in=[p for _l, p in programs], year_level__in=years, semester=semester)
    if not scope.exists():
        return {"detail": f"No sections exist for {year_level}, {semester} in these departments."}, 400
    locked = Schedule.objects.filter(section__in=scope, subject__classification="minor").exclude(status="draft").count()
    if locked:
        return {"detail": f"{locked} minor class period(s) of this scope are already approved/published. "
                          "Move them back to draft before generating again."}, 409
    before = scan(semester=semester, year_level=years, limit=300)
    try:
        with transaction.atomic():
            if not locks.try_lock("classes"):
                raise BatchError({"detail": locks.BUSY}, 409)
            replaced = Schedule.objects.filter(section__in=scope, subject__classification="minor").count()
            Schedule.objects.filter(section__in=scope, subject__classification="minor").delete()
            sizes, bins, order = plan_groups(programs, years, semester)
            token = room_rules.use_group_sizes(sizes)
            runs, created, unresolved, merged = [], [], 0, []
            try:
                for yl in years:
                    for prog in order:
                        status, data = _call_generate(user, prog, yl, semester, school_year)
                        if status == 201:
                            ids = list(data.get("created_schedule_ids") or [])
                            created += ids
                            unresolved += len(data.get("conflicts") or [])
                            merged += data.get("merged_classes") or []
                            runs.append({"department": dept_label(prog), "program": prog.name, "year_level": yl,
                                         "created": len(ids), "merged": len(data.get("merged_classes") or []),
                                         "unplaced": [c.get("subject") + " - " + c.get("reason", "") for c in data.get("conflicts") or []],
                                         "unplaced_items": data.get("conflicts") or [],
                                         "auto_resolved": len(data.get("auto_resolved") or []),
                                         "status": "generated"})
                        elif status == 400:
                            runs.append({"department": dept_label(prog), "program": prog.name, "year_level": yl, "created": 0,
                                         "merged": 0, "unplaced": [], "status": "skipped",
                                         "note": str(data.get("detail", ""))[:200]})
                        else:
                            raise BatchError({"detail": f"{prog.name} {yl}: {data.get('detail', 'generation failed')}"}, 500 if status >= 500 else status)
            finally:
                room_rules.release_group_sizes(token)
            # fresh validation of what is now in the database
            new_clashes = scan(semester=semester, involving_ids=set(created), limit=300) if created else {"total": 0, "conflicts": [], "counts": {}}
            if new_clashes["total"]:
                transaction.set_rollback(True)
                raise BatchError({"detail": "The generated minor schedule broke a scheduling rule, so nothing was saved.",
                                  "blocked": True, "conflicts": new_clashes["conflicts"], "counts": new_clashes["counts"]}, 422)
    except BatchError as e:
        return e.payload, e.status
    after = scan(semester=semester, year_level=years, limit=300)
    return {
        "capacity_warnings": capacity_warnings(set(created)),
        "school_year": school_year, "semester": semester, "year_level": year_level, "departments": sorted(present),
        "replaced_rows": replaced, "created_rows": len(created), "runs": runs, "unplaced": unresolved,
        "groups": {"planned": len(bins), "shared": sum(1 for b in bins if b["planned_shared"]),
                   "actually_shared": len(merged), "joined": merged},
        "conflicts_before": before["total"], "conflicts_after": after["total"],
        "report": after,
        "validated": after["total"] == 0 and unresolved == 0,
        "message": ("Validated: no teacher, room or student conflicts remain." if after["total"] == 0 and unresolved == 0 else
                    f"{after['total']} conflict(s) remain and {unresolved} class(es) could not be placed. Not validated."),
    }, 201


def capacity_warnings(schedule_ids):
    """Classes (of the just-generated ones) whose students outnumber the seats of their room. The generator keeps such a class
    when NO allowed room is big enough (e.g. a 50-student section when the largest shared room has 40 seats): it is placed and
    reported here instead of being dropped, so the section can be split or a bigger room added."""
    groups = defaultdict(list)
    rows = Schedule.objects.filter(pk__in=schedule_ids).select_related("room", "subject", "section__program", "timeslot")
    for r in rows:
        groups[(r.room_id, r.timeslot_id, r.merge_key or ("own", r.id))].append(r)
    seen, out = set(), []
    for lst in groups.values():
        cap = lst[0].room.capacity or 0
        total = sum(x.section.student_count for x in {y.section_id: y for y in lst}.values())
        if cap and total > cap:
            for x in lst:
                k = (x.section_id, x.subject_id)
                if k in seen:
                    continue
                seen.add(k)
                out.append({"subject": f"{x.subject.code} {x.subject.title}", "department": dept_label(x.section.program) or x.section.program.department,
                            "section": f"{x.section.program.name} {x.section.name}", "students": total, "room": x.room.name, "capacity": cap})
    return out[:100]


def comparison(semester, year_level):
    """Side-by-side minor schedules of the four departments, grouped by equivalent subject."""
    programs = target_programs()
    years = YEARS if year_level in (None, "", "All") else [year_level]
    sections = list(Section.objects.filter(program__in=[p for _l, p in programs], year_level__in=years, semester=semester)
                    .select_related("program").order_by("program__name", "name"))
    labels = {p.id: l for l, p in programs}
    subs = list(Subject.objects.filter(program__in=[p for _l, p in programs], year_level__in=years, semester=semester,
                                       classification="minor").select_related("program"))
    rows = list(Schedule.objects.filter(section__in=sections, subject__classification="minor")
                .select_related("subject", "section__program", "teacher__user", "room", "timeslot"))
    by_sec = defaultdict(lambda: defaultdict(list))               # section_id -> subject_id -> rows
    for r in rows:
        by_sec[r.section_id][r.subject_id].append(r)
    rep = scan(semester=semester, year_level=years, limit=2000)
    bad = defaultdict(set)                                        # schedule id -> conflict kinds
    for c in rep["conflicts"]:
        for side in (c["a"], c["b"]):
            for i in side["ids"]:
                bad[i].add(c["kind_label"])
    groups = {}
    for sec in sections:
        for sub in [s for s in subs if s.program_id == sec.program_id and s.year_level == sec.year_level]:
            key = (sec.year_level,) + _key(sub)
            g = groups.setdefault(key, {"code": sub.code, "title": sub.title, "units": sub.lec_units + sub.lab_units,
                                        "year_level": sec.year_level, "semester": semester, "cells": []})
            mine = by_sec[sec.id].get(sub.id, [])
            blocks = [{"day": b["day"], "time": f"{_label(b['start'])} - {_label(b['end'])}", "room": b["row"].room.name,
                       "teacher": b["row"].teacher.user.get_full_name().strip() or b["row"].teacher.user.username,
                       "ids": b["ids"]} for b in sorted(_blocks(mine), key=lambda b: (DAY_ORDER.get(b["day"], 9), b["start"]))] if mine else []
            mk = {r.merge_key for r in mine if r.merge_key}
            g["cells"].append({"department": labels[sec.program_id], "program": sec.program.name, "section": sec.name,
                               "section_id": sec.id, "students": sec.student_count, "blocks": blocks,
                               "merge_key": next(iter(mk), ""), "scheduled": bool(mine),
                               "conflicts": sorted({k for b in blocks for i in b["ids"] for k in bad.get(i, ())})})
    out = []
    for g in groups.values():
        by_mk = defaultdict(list)
        for c in g["cells"]:
            if c["merge_key"]:
                by_mk[c["merge_key"]].append(c)
        for c in g["cells"]:
            others = [f"{o['department']} {o['section']}" for o in by_mk.get(c["merge_key"], []) if o is not c] if c["merge_key"] else []
            c["mode"] = "not scheduled" if not c["scheduled"] else ("shared" if others else "separate")
            c["shared_with"] = others
            c.pop("merge_key", None)
        modes = {c["mode"] for c in g["cells"] if c["scheduled"]}
        g["mode"] = "shared" if modes == {"shared"} else "separate" if modes == {"separate"} else "mixed" if modes else "not scheduled"
        g["conflict"] = any(c["conflicts"] for c in g["cells"])
        g["departments"] = sorted({c["department"] for c in g["cells"]}, key=LABELS.index)
        out.append(g)
    out.sort(key=lambda g: (g["year_level"], g["code"]))
    return {"departments": [l for l in LABELS if any(lab == l for lab, _p in programs)], "groups": out,
            "total_conflicts": rep["total"], "semester": semester, "year_level": year_level or "All"}
