"""Shared minor (Gen Ed) classes chosen BEFORE generating.

The Registrar (who owns the minor subjects) can say, for one minor lecture subject of a year level and semester, either
  * "exclusive": this program keeps its own class (never merged, not even automatically), or
  * "shared":    2 or 3 programs attend ONE class (same teacher, room and time; Schedule.merge_key).
A shared group is only accepted when the programs' subjects are the same curriculum requirement (code, title, lecture/lab units, minor,
year level, semester), a qualified teacher exists, and the sections' students fit the largest room all of them may use. Anything else is
refused with the specific reason; nothing is merged automatically when the details differ. Curriculum rows, sections and students are never
changed: a shared class only gives the participating sections the same teacher / room / time.
Only CONFIRMED groups are used by the generator. A group the Registrar saves is confirmed at once. Deans only READ the choice (their
programs' Gen Ed subjects are owned by the Registrar); a group a Dean saved before this rule stays stored and still waits for the
Registrar's Confirm."""
from collections import defaultdict

from django.db import transaction

from curriculum.models import Program, Subject
from rooms import rules as rr
from rooms.models import Room
from .models import Schedule, Section, SharedClassExclusive, SharedClassGroup

MIN_PROGRAMS, MAX_PROGRAMS = 2, 3


class SharedError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def _norm(t):
    return " ".join((t or "").lower().split())


def key_of(subject):
    return (subject.code, subject.lec_units, subject.lab_units, _norm(subject.title))


def _owns_program(user, program):
    return getattr(user, "role", "") == "registrar" or (
        getattr(user, "role", "") == "faculty" and getattr(user, "faculty_type", "") == "dean" and program.department in (user.departments or []))


def _can_configure(user, kind, program):
    if kind == "minor":
        return getattr(user, "role", "") == "registrar"
    return (getattr(user, "role", "") == "faculty" and getattr(user, "faculty_type", "") == "dean"
            and program.department in (user.departments or []))


def _group_capacity(programs):
    """Seats of the largest ordinary lecture room that every one of these programs may use."""
    deps = {p.department for p in programs}
    caps = [r.capacity or 0 for r in Room.objects.filter(room_type="lecture")
            if all(rr.may_use(r, d) for d in deps) and not rr.is_owned_lab(r)]
    return max([c for c in caps if c] or [0])


def _subject_of(program, code, lec, lab, title, year, sem, kind="minor"):
    for s in Subject.objects.filter(program=program, code=code, year_level=year, semester=sem, classification=kind):
        if key_of(s) == (code, lec, lab, _norm(title)):
            return s
    return None


def _sections(program, year, sem):
    return list(Section.objects.filter(program=program, year_level=year, semester=sem).order_by("name"))


def _teacher_fits_section(teacher, subject, section):
    from .qualification import qualified_teachers
    specializations = set(teacher.specializations.values_list("id", flat=True))
    return bool(qualified_teachers(subject, section, [teacher], {teacher.id: specializations}))


def program_card(program, year, sem):
    secs = _sections(program, year, sem)
    return {"id": program.id, "name": program.name, "department": program.department, "year_level": year, "semester": sem,
            "sections": len(secs), "students": sum(s.student_count for s in secs)}


def options(user, program_id, year, sem, kind=None):
    """Per minor lecture subject of the program: its current choice and the programs that could share it (compatible only)."""
    program = Program.objects.filter(pk=program_id).first()
    if program is None:
        raise SharedError("Program not found.", 404)
    kind = kind or ("major" if getattr(user, "faculty_type", "") == "dean" else "minor")
    if kind not in ("major", "minor") or (kind == "major" and not _can_configure(user, kind, program)):
        raise SharedError("You cannot view sharing choices for these subjects.", 403)
    if kind == "minor" and getattr(user, "role", "") not in ("registrar", "faculty"):
        raise SharedError("You cannot view sharing choices for these subjects.", 403)
    out = []
    groups = list(SharedClassGroup.objects.filter(subject_kind=kind, year_level=year, semester=sem, programs=program).prefetch_related("programs"))
    excl = set(SharedClassExclusive.objects.filter(subject_kind=kind, program=program, year_level=year, semester=sem).values_list("code", flat=True))
    for sub in Subject.objects.filter(program=program, year_level=year, semester=sem, classification=kind).order_by("code"):
        item = {"subject_id": sub.id, "code": sub.code, "title": sub.title, "lec_units": sub.lec_units, "lab_units": sub.lab_units,
                "shareable": sub.lab_units == 0, "mode": "auto", "group": None, "candidates": []}
        if sub.lab_units:
            item["why_not"] = "A laboratory class is always held by its own program."
        else:
            candidates = Program.objects.exclude(pk=program.pk)
            if kind == "major":
                candidates = candidates.filter(department=program.department)
            for p in candidates.order_by("name"):
                other = _subject_of(p, sub.code, sub.lec_units, sub.lab_units, sub.title, year, sem, kind)
                if other is not None and _sections(p, year, sem):
                    item["candidates"].append(program_card(p, year, sem))
        g = next((x for x in groups if x.code == sub.code and key_of(sub) == (x.code, x.lec_units, x.lab_units, _norm(x.title))), None)
        if g:
            item["mode"] = "shared"
            item["group"] = {"id": g.id, "confirmed": g.confirmed, "programs": [program_card(p, year, sem) for p in g.programs.order_by("name")]}
        elif sub.code in excl:
            item["mode"] = "exclusive"
        out.append(item)
    return {"program": program_card(program, year, sem), "subjects": out,
            "can_edit": _can_configure(user, kind, program), "role": getattr(user, "role", ""), "subject_kind": kind}


def batch_options(user, semester, year_level=""):
    """Registrar view of sharing choices across the programs included in Generate All Minors."""
    if getattr(user, "role", "") != "registrar":
        raise SharedError("Only the Registrar can configure all minor schedules.", 403)
    from .minor_batch import target_programs
    programs = [p for _label, p in target_programs()]
    qs = Subject.objects.filter(program__in=programs, semester=semester, classification="minor", lab_units=0)
    if year_level and year_level != "All":
        qs = qs.filter(year_level=year_level)
    grouped = {}
    for sub in qs.select_related("program").order_by("year_level", "code", "program__name"):
        k = (sub.year_level, sub.code, _norm(sub.title), sub.lec_units, sub.lab_units)
        grouped.setdefault(k, []).append(sub)
    out = []
    for (year, code, _title, lec, lab), matches in grouped.items():
        if len(matches) < 2:
            continue
        sub = matches[0]
        pids = [s.program_id for s in matches]
        groups = list(SharedClassGroup.objects.filter(subject_kind="minor", code=code, year_level=year, semester=semester,
                                                       programs__in=pids).distinct().prefetch_related("programs"))
        groups = [g for g in groups if key_of(sub) == (g.code, g.lec_units, g.lab_units, _norm(g.title))]
        exclusive_ids = set(SharedClassExclusive.objects.filter(subject_kind="minor", code=code, year_level=year, semester=semester,
                                                                  program_id__in=pids).values_list("program_id", flat=True))
        departments = sorted({s.program.department for s in matches})
        selected = sorted({p.department for g in groups for p in g.programs.all()})
        mode = "shared" if groups else ("exclusive" if set(pids) <= exclusive_ids else "auto")
        out.append({"subject_id": sub.id, "code": code, "title": sub.title, "lec_units": lec, "lab_units": lab,
                    "year_level": year, "semester": semester, "mode": mode, "departments": departments,
                    "selected_departments": selected,
                    "programs": [program_card(s.program, year, semester) for s in matches],
                    "groups": [{"programs": [p.name for p in g.programs.order_by("name")]} for g in groups]})
    return {"subjects": out, "departments": sorted({s.program.department for v in grouped.values() for s in v})}


@transaction.atomic
def batch_choice(user, subject_id, mode="auto", departments=None):
    """Save one Registrar all-minors sharing preference, expanding selected departments to all matching programs."""
    if getattr(user, "role", "") != "registrar":
        raise SharedError("Only the Registrar can configure all minor schedules.", 403)
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification="minor", lab_units=0).first()
    if sub is None:
        raise SharedError("Eligible minor subject not found.", 404)
    if mode not in ("auto", "exclusive", "shared"):
        raise SharedError("Choose automatic, exclusive, or shared mode.", 400)
    from .minor_batch import target_programs
    allowed = [p for _label, p in target_programs()]
    matches = [s for s in Subject.objects.filter(program__in=allowed, code=sub.code, year_level=sub.year_level,
                                                    semester=sub.semester, classification="minor", lab_units=0).select_related("program")
               if key_of(s) == key_of(sub)]
    if len(matches) < 2:
        raise SharedError("No other program has this exact subject in the selected semester and year.", 422)
    match_programs = {s.program_id: s.program for s in matches}
    departments = set(departments or [])
    unknown = departments - {p.department for p in match_programs.values()}
    if unknown:
        raise SharedError("One or more selected departments do not offer this exact subject.", 400)
    if mode == "shared":
        selected = [p for p in match_programs.values() if p.department in departments]
        if sub.program_id not in {p.id for p in selected}:
            selected.append(sub.program)
        selected = sorted({p.id: p for p in selected}.values(), key=lambda p: (p.department, p.name))
        if len(selected) < 2:
            raise SharedError("Select at least one matching program department to share with.", 422)
        chunks, remaining = [], list(selected)
        while len(remaining) >= 2:
            take = 2 if len(remaining) == 4 else min(MAX_PROGRAMS, len(remaining))
            chunks.append(remaining[:take]); remaining = remaining[take:]
        if remaining:
            raise SharedError("The selected programs cannot be divided into groups of 2 or 3.", 422)
        checks = [validate([p.id for p in chunk], sub.code, sub.lec_units, sub.lab_units, sub.title, sub.year_level, sub.semester, "minor")
                  for chunk in chunks]
        bad = [err for check in checks for err in check["errors"]]
        if bad:
            raise SharedError(" ".join(bad), 422)
    else:
        selected, chunks, checks = [], [], []

    all_programs = list(match_programs.values())
    for group in SharedClassGroup.objects.filter(subject_kind="minor", code=sub.code, year_level=sub.year_level, semester=sub.semester,
                                                   programs__in=all_programs).distinct():
        group.delete()
    SharedClassExclusive.objects.filter(subject_kind="minor", code=sub.code, year_level=sub.year_level, semester=sub.semester,
                                         program__in=all_programs).delete()
    if mode == "exclusive":
        SharedClassExclusive.objects.bulk_create([SharedClassExclusive(program=p, code=sub.code, year_level=sub.year_level,
                                                                         semester=sub.semester, subject_kind="minor", created_by=user)
                                                   for p in all_programs])
    elif mode == "shared":
        selected_ids = {p.id for p in selected}
        SharedClassExclusive.objects.bulk_create([SharedClassExclusive(program=p, code=sub.code, year_level=sub.year_level,
                                                                         semester=sub.semester, subject_kind="minor", created_by=user)
                                                   for p in all_programs if p.id not in selected_ids])
        for chunk in chunks:
            group = SharedClassGroup.objects.create(code=sub.code, title=sub.title, lec_units=sub.lec_units, lab_units=sub.lab_units,
                                                     subject_kind="minor", year_level=sub.year_level, semester=sub.semester,
                                                     created_by=user, confirmed=True, confirmed_by=user)
            group.programs.set(chunk)
    return {"mode": mode, "groups": len(chunks), "message": {"auto": "Automatic sharing restored.",
            "exclusive": "These matching subjects will remain separate.", "shared": f"Saved {len(chunks)} selected shared group(s)."}[mode]}


def validate(program_ids, code, lec, lab, title, year, sem, kind="minor"):
    """-> {"ok", "errors": [...], "warnings": [...], "programs": [...], "total_students", "capacity", "classes": n shared / n separate sections}"""
    errors, warnings = [], []
    progs = list(Program.objects.filter(pk__in=set(program_ids)).order_by("name"))
    if len(progs) != len(set(program_ids)):
        raise SharedError("One of the chosen programs does not exist.", 404)
    if not MIN_PROGRAMS <= len(progs) <= MAX_PROGRAMS:
        errors.append(f"Choose {MIN_PROGRAMS} or {MAX_PROGRAMS} programs for a shared class (you chose {len(progs)}).")
    cards, subs = [], {}
    for p in progs:
        sub = _subject_of(p, code, lec, lab, title, year, sem, kind)
        card = program_card(p, year, sem)
        cards.append(card)
        if sub is None:
            errors.append(f"{p.name} has no matching {kind} subject {code} - {title} ({lec} lec / {lab} lab units) in {year}, {sem}: its curriculum differs, so it cannot share this class.")
            continue
        subs[p.id] = sub
        if not card["sections"]:
            errors.append(f"{p.name} has no section in {year}, {sem}.")
    if lab:
        errors.append("Laboratory classes are not shared.")
    cap = _group_capacity(progs)
    secs = {p.id: _sections(p, year, sem) for p in progs}
    total = sum(c["students"] for c in cards)
    shared_n, separate = 0, []
    if not errors:
        if not cap:
            errors.append("No lecture room that all these programs may use has a recorded capacity.")
        else:
            # how the sections pair up: each section of the first program starts a class, sections of the others join it while the room has seats
            order = sorted(progs, key=lambda p: (-sum(s.student_count for s in secs[p.id]), p.name))
            bins = [[s] for s in secs[order[0].id]]
            for p in order[1:]:
                for s in sorted(secs[p.id], key=lambda s: -s.student_count):
                    for b in bins:
                        if p.id not in {x.program_id for x in b} and sum(x.student_count for x in b) + s.student_count <= cap:
                            b.append(s)
                            break
                    else:
                        bins.append([s])
            shared_n = sum(1 for b in bins if len(b) > 1)
            separate = [f"{x.program.name} {x.name}" for b in bins if len(b) == 1 for x in b]
            if not shared_n:
                errors.append(f"Even the smallest sections together do not fit: the largest room these programs may use seats {cap}, "
                              f"and the enrolment is {total}. They cannot share one class; keep the subject exclusive.")
            elif separate:
                warnings.append(f"{shared_n} shared class(es) fit in a {cap}-seat room; {len(separate)} section(s) would still have their own class: " + ", ".join(separate) + ".")
    # a qualified teacher must exist (faculty qualification)
    if subs and not errors:
        from faculty.models import FacultyProfile
        from .qualification import qualified_teachers, why_nobody
        teachers = list(FacultyProfile.objects.select_related("user").prefetch_related("specializations").filter(user__is_active=True))
        spec = {t.id: {f.id for f in t.specializations.all()} for t in teachers}
        eligible = None
        first = next(iter(subs.values()))
        first_section = None
        for pid, subject in subs.items():
            for section in secs[pid]:
                if first_section is None:
                    first, first_section = subject, section
                ids = {t.id for t in qualified_teachers(subject, section, teachers, spec)}
                eligible = ids if eligible is None else eligible & ids
        if not eligible:
            errors.append(why_nobody(first, first_section, teachers, spec))
    warnings.append("Teacher availability, the room and a time free for every section are checked again when you generate.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "programs": cards, "total_students": total, "capacity": cap,
            "shared_classes": shared_n, "separate_sections": separate}


@transaction.atomic
def save_group(user, program_id, subject_id, other_program_ids):
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification__in=("minor", "major")).first()
    if sub is None:
        raise SharedError("Subject not found.", 404)
    kind = sub.classification
    own = sub.program
    if not _can_configure(user, kind, own):
        raise SharedError("Only the Registrar can configure minor sharing; Deans can configure major sharing for their own department.", 403)
    ids = [own.id] + [int(i) for i in other_program_ids if int(i) != own.id]
    if kind == "major" and any(p.department != own.department for p in Program.objects.filter(pk__in=ids)):
        raise SharedError("Major classes can only be shared between programs in your own department.", 403)
    res = validate(ids, sub.code, sub.lec_units, sub.lab_units, sub.title, sub.year_level, sub.semester, kind)
    if not res["ok"]:
        raise SharedError(" ".join(res["errors"]), 422)
    progs = list(Program.objects.filter(pk__in=ids))
    # a program belongs to ONE group per subject: older groups of these programs for the same subject are dissolved
    for g in SharedClassGroup.objects.filter(subject_kind=kind, code=sub.code, year_level=sub.year_level, semester=sub.semester, programs__in=progs).distinct():
        g.delete()
    SharedClassExclusive.objects.filter(subject_kind=kind, program__in=progs, code=sub.code, year_level=sub.year_level, semester=sub.semester).delete()
    mine = kind == "major" or getattr(user, "role", "") == "registrar"
    g = SharedClassGroup.objects.create(code=sub.code, title=sub.title, lec_units=sub.lec_units, lab_units=sub.lab_units,
                                        subject_kind=kind, year_level=sub.year_level, semester=sub.semester, created_by=user,
                                        confirmed=mine, confirmed_by=user if mine else None)
    g.programs.set(progs)
    return {"group_id": g.id, "confirmed": g.confirmed, "validation": res,
            "message": ("Shared class confirmed. Generate to create the one shared schedule." if g.confirmed else
                        "Saved. It includes another college's program, so the Registrar must confirm it before it is used.")}


@transaction.atomic
def confirm_group(user, group_id):
    g = SharedClassGroup.objects.filter(pk=group_id).first()
    if g is None:
        raise SharedError("Shared class not found.", 404)
    programs = list(g.programs.all())
    if g.subject_kind == "minor" and getattr(user, "role", "") != "registrar":
        raise SharedError("Only the Registrar confirms shared minor classes.", 403)
    if g.subject_kind == "major" and (getattr(user, "role", "") != "faculty" or getattr(user, "faculty_type", "") != "dean"
                                       or any(p.department not in (user.departments or []) for p in programs)):
        raise SharedError("Only the Dean of these programs can confirm this major class.", 403)
    res = validate([p.id for p in programs], g.code, g.lec_units, g.lab_units, g.title, g.year_level, g.semester, g.subject_kind)
    if not res["ok"]:
        raise SharedError(" ".join(res["errors"]), 422)
    g.confirmed, g.confirmed_by = True, user
    g.save(update_fields=["confirmed", "confirmed_by"])
    return {"group_id": g.id, "confirmed": True}


@transaction.atomic
def set_exclusive(user, program_id, subject_id):
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification__in=("minor", "major")).first()
    if sub is None:
        raise SharedError("Subject not found.", 404)
    kind = sub.classification
    if not _can_configure(user, kind, sub.program):
        raise SharedError("You do not have permission to change sharing for this subject.", 403)
    for g in SharedClassGroup.objects.filter(subject_kind=kind, code=sub.code, year_level=sub.year_level, semester=sub.semester, programs=sub.program):
        g.programs.remove(sub.program)
        if g.programs.count() < MIN_PROGRAMS:
            g.delete()
    SharedClassExclusive.objects.get_or_create(program=sub.program, code=sub.code, year_level=sub.year_level, semester=sub.semester, subject_kind=kind,
                                               defaults={"created_by": user})
    return {"mode": "exclusive"}


@transaction.atomic
def clear_choice(user, program_id, subject_id):
    """Back to automatic (the generator may still join equal classes when they fit)."""
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification__in=("minor", "major")).first()
    if sub is None:
        raise SharedError("Subject not found.", 404)
    kind = sub.classification
    if not _can_configure(user, kind, sub.program):
        raise SharedError("You do not have permission to change sharing for this subject.", 403)
    SharedClassExclusive.objects.filter(subject_kind=kind, program=sub.program, code=sub.code, year_level=sub.year_level, semester=sub.semester).delete()
    for g in SharedClassGroup.objects.filter(subject_kind=kind, code=sub.code, year_level=sub.year_level, semester=sub.semester, programs=sub.program):
        g.programs.remove(sub.program)
        if g.programs.count() < MIN_PROGRAMS:
            g.delete()
    return {"mode": "auto"}


# ----------------------------------------------------------------------------- used by the generator
def share_rules(year, sem, kind="minor"):
    """{(program_id, code): ("exclusive", None) | ("group", frozenset(program ids))} for confirmed choices of this year level / semester."""
    out = {}
    for e in SharedClassExclusive.objects.filter(subject_kind=kind, year_level=year, semester=sem):
        out[(e.program_id, e.code)] = ("exclusive", None)
    for g in SharedClassGroup.objects.filter(subject_kind=kind, year_level=year, semester=sem, confirmed=True).prefetch_related("programs"):
        ids = frozenset(p.id for p in g.programs.all())
        for pid in ids:
            out[(pid, g.code)] = ("group", ids)
    return out


def may_share(rules, prog_a, prog_b, code):
    """May these two programs' sections of one minor subject be merged? The explicit choice of either side wins; no choice = automatic."""
    for me, other in ((prog_a, prog_b), (prog_b, prog_a)):
        r = rules.get((me, code))
        if r:
            if r[0] == "exclusive":
                return False
            if other not in r[1]:
                return False
    return True


def plan_members(host_section, subject, rules, claimed_sections=None):
    """Sections of the other programs of the host's confirmed group that should join the host's class. -> ([sections], total students)"""
    r = rules.get((host_section.program_id, subject.code))
    if r and r[0] == "exclusive":
        return [], host_section.student_count
    if r and r[0] == "group":
        progs = list(Program.objects.filter(pk__in=r[1]))
    elif subject.classification == "major":
        candidates = [p for p in Program.objects.filter(department=host_section.program.department).exclude(pk=host_section.program_id).order_by("name")
                      if _subject_of(p, subject.code, subject.lec_units, subject.lab_units, subject.title, subject.year_level, subject.semester, "major")]
        progs = [host_section.program]
        for p in candidates:
            if len(progs) >= MAX_PROGRAMS:
                break
            if not may_share(rules, host_section.program_id, p.id, subject.code):
                continue
            progs.append(p)
    else:
        return [], host_section.student_count
    if len(progs) < MIN_PROGRAMS:
        return [], host_section.student_count
    cap = _group_capacity(progs)
    members, total = [], host_section.student_count
    already = set(Schedule.objects.filter(subject__code=subject.code, subject__classification=subject.classification,
                                          section__semester=host_section.semester,
                                          section__year_level=host_section.year_level).values_list("section_id", flat=True))
    already.update(sid for sid, subject_id in (claimed_sections or set()) if subject_id == subject.id)
    others = [s for pid in [p.id for p in progs] if pid != host_section.program_id
              for s in Section.objects.filter(program_id=pid, year_level=host_section.year_level, semester=host_section.semester).select_related("program")
              if s.id not in already and _subject_of(s.program, subject.code, subject.lec_units, subject.lab_units, subject.title,
                                                    s.year_level, s.semester, subject.classification) is not None]
    for s in sorted(others, key=lambda s: (-s.student_count, s.program.name, s.name)):
        if any(m.program_id == s.program_id for m in members):
            continue
        if cap and total + s.student_count <= cap:
            members.append(s); total += s.student_count
            if claimed_sections is not None:
                claimed_sections.add((s.id, subject.id))
    return members, total


def busy_intervals(section_ids, ignore_subject_id=None):
    """[(day index, start min, end min)] of everything these sections already have in the semester (the host's time must avoid them)."""
    from .scheduler import _slot_key
    out = []
    for r in Schedule.objects.filter(section_id__in=section_ids).exclude(subject_id=ignore_subject_id).select_related("timeslot"):
        out.append(_slot_key(r.timeslot))
    return out


def extend_to_members(plans, created_rows, school_year):
    """After the host sections were scheduled: give each member section the SAME teacher, room and time (one shared class).
    plans: [(host_section, subject, [member sections])]. Returns a report; a section that cannot join stays unscheduled for its own program."""
    from .scheduler import _slot_key
    report = []
    for host, subject, members in plans:
        host_rows = [r for r in created_rows if r.section_id == host.id and r.subject_id == subject.id]
        entry = {"subject": f"{subject.code} - {subject.title}", "host": f"{host.program.name} {host.name}", "joined": [], "skipped": [],
                 "room": "", "capacity": 0, "students": host.student_count, "schedule_ids": []}
        if not host_rows or not members:
            if members and not host_rows:
                entry["skipped"] = [f"{m.program.name} {m.name}: the host class could not be placed" for m in members]
                report.append(entry)
            continue
        room = host_rows[0].room
        entry["room"], entry["capacity"] = room.name, room.capacity
        mk = f"{subject.code}|{host.year_level}|{host.semester}|{host.id}"[:80]
        total = host.student_count
        for m in members:
            msub = _subject_of(m.program, subject.code, subject.lec_units, subject.lab_units, subject.title, m.year_level, m.semester, subject.classification)
            if msub is None:
                entry["skipped"].append(f"{m.program.name} {m.name}: its curriculum differs")
                continue
            if not _teacher_fits_section(host_rows[0].teacher, msub, m):
                entry["skipped"].append(f"{m.program.name} {m.name}: the assigned teacher is not qualified for this section")
                continue
            if room.capacity and total + m.student_count > room.capacity:
                entry["skipped"].append(f"{m.program.name} {m.name}: {total + m.student_count} students would not fit the {room.capacity}-seat room {room.name}")
                continue
            busy = busy_intervals([m.id])
            clash = any(_slot_key(r.timeslot)[0] == b[0] and min(_slot_key(r.timeslot)[2], b[2]) - max(_slot_key(r.timeslot)[1], b[1]) > 0
                        for r in host_rows for b in busy)
            if clash:
                entry["skipped"].append(f"{m.program.name} {m.name}: already has a class at that time")
                continue
            new = Schedule.objects.bulk_create([Schedule(subject=msub, teacher=r.teacher, room=r.room, section=m, timeslot=r.timeslot,
                                                         school_year=school_year, status="draft", merge_key=mk, term=m.semester) for r in host_rows])
            entry["joined"].append(f"{m.program.name} {m.name}")
            entry["schedule_ids"] += [x.id for x in new if x.id is not None]
            total += m.student_count
        if entry["joined"]:
            Schedule.objects.filter(pk__in=[r.pk for r in host_rows]).update(merge_key=mk)
        entry["students"] = total
        report.append(entry)
    return report
