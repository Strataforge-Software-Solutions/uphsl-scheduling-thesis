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


def _may_edit(user):
    """Gen Ed (minor) subjects belong to the Registrar, so only the Registrar chooses shared / exclusive classes."""
    return getattr(user, "role", "") == "registrar"


def _group_capacity(programs):
    """Seats of the largest ordinary lecture room that every one of these programs may use."""
    deps = {p.department for p in programs}
    caps = [r.capacity or 0 for r in Room.objects.filter(room_type="lecture")
            if all(rr.may_use(r, d) for d in deps) and not rr.is_owned_lab(r)]
    return max([c for c in caps if c] or [0])


def _subject_of(program, code, lec, lab, title, year, sem):
    for s in Subject.objects.filter(program=program, code=code, year_level=year, semester=sem, classification="minor"):
        if key_of(s) == (code, lec, lab, _norm(title)):
            return s
    return None


def _sections(program, year, sem):
    return list(Section.objects.filter(program=program, year_level=year, semester=sem).order_by("name"))


def program_card(program, year, sem):
    secs = _sections(program, year, sem)
    return {"id": program.id, "name": program.name, "department": program.department, "year_level": year, "semester": sem,
            "sections": len(secs), "students": sum(s.student_count for s in secs)}


def options(user, program_id, year, sem):
    """Per minor lecture subject of the program: its current choice and the programs that could share it (compatible only)."""
    program = Program.objects.filter(pk=program_id).first()
    if program is None:
        raise SharedError("Program not found.", 404)
    out = []
    groups = {g.code: g for g in SharedClassGroup.objects.filter(year_level=year, semester=sem, programs=program).prefetch_related("programs")}
    excl = set(SharedClassExclusive.objects.filter(program=program, year_level=year, semester=sem).values_list("code", flat=True))
    for sub in Subject.objects.filter(program=program, year_level=year, semester=sem, classification="minor").order_by("code"):
        item = {"subject_id": sub.id, "code": sub.code, "title": sub.title, "lec_units": sub.lec_units, "lab_units": sub.lab_units,
                "shareable": sub.lab_units == 0, "mode": "auto", "group": None, "candidates": []}
        if sub.lab_units:
            item["why_not"] = "A laboratory class is always held by its own program."
        else:
            for p in Program.objects.exclude(pk=program.pk).order_by("name"):
                other = _subject_of(p, sub.code, sub.lec_units, sub.lab_units, sub.title, year, sem)
                if other is not None and _sections(p, year, sem):
                    item["candidates"].append(program_card(p, year, sem))
        g = groups.get(sub.code)
        if g and key_of(sub) == (g.code, g.lec_units, g.lab_units, _norm(g.title)):
            item["mode"] = "shared"
            item["group"] = {"id": g.id, "confirmed": g.confirmed, "programs": [program_card(p, year, sem) for p in g.programs.order_by("name")]}
        elif sub.code in excl:
            item["mode"] = "exclusive"
        out.append(item)
    return {"program": program_card(program, year, sem), "subjects": out,
            "can_edit": _may_edit(user) and _owns_program(user, program), "role": getattr(user, "role", "")}


def validate(program_ids, code, lec, lab, title, year, sem):
    """-> {"ok", "errors": [...], "warnings": [...], "programs": [...], "total_students", "capacity", "classes": n shared / n separate sections}"""
    errors, warnings = [], []
    progs = list(Program.objects.filter(pk__in=set(program_ids)).order_by("name"))
    if len(progs) != len(set(program_ids)):
        raise SharedError("One of the chosen programs does not exist.", 404)
    if not MIN_PROGRAMS <= len(progs) <= MAX_PROGRAMS:
        errors.append(f"Choose {MIN_PROGRAMS} or {MAX_PROGRAMS} programs for a shared class (you chose {len(progs)}).")
    cards, subs = [], {}
    for p in progs:
        sub = _subject_of(p, code, lec, lab, title, year, sem)
        card = program_card(p, year, sem)
        cards.append(card)
        if sub is None:
            errors.append(f"{p.name} has no minor subject {code} - {title} ({lec} lec / {lab} lab units) in {year}, {sem}: its curriculum differs, so it cannot share this class.")
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
        first = next(iter(subs.values()))
        sec0 = secs[first.program_id][0]
        if not qualified_teachers(first, sec0, teachers, spec):
            errors.append(why_nobody(first, sec0, teachers, spec))
    warnings.append("Teacher availability, the room and a time free for every section are checked again when you generate.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "programs": cards, "total_students": total, "capacity": cap,
            "shared_classes": shared_n, "separate_sections": separate}


@transaction.atomic
def save_group(user, program_id, subject_id, other_program_ids):
    if not _may_edit(user):
        raise SharedError("Only the Registrar chooses shared Gen Ed classes (minor subjects belong to the Registrar).", 403)
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification="minor").first()
    if sub is None:
        raise SharedError("Minor subject not found.", 404)
    own = sub.program
    if not _owns_program(user, own):
        raise SharedError("You can only choose shared classes for programs of your own college.", 403)
    ids = [own.id] + [int(i) for i in other_program_ids if int(i) != own.id]
    res = validate(ids, sub.code, sub.lec_units, sub.lab_units, sub.title, sub.year_level, sub.semester)
    if not res["ok"]:
        raise SharedError(" ".join(res["errors"]), 422)
    progs = list(Program.objects.filter(pk__in=ids))
    # a program belongs to ONE group per subject: older groups of these programs for the same subject are dissolved
    for g in SharedClassGroup.objects.filter(code=sub.code, year_level=sub.year_level, semester=sub.semester, programs__in=progs).distinct():
        g.delete()
    SharedClassExclusive.objects.filter(program__in=progs, code=sub.code, year_level=sub.year_level, semester=sub.semester).delete()
    mine = all(_owns_program(user, p) for p in progs)
    g = SharedClassGroup.objects.create(code=sub.code, title=sub.title, lec_units=sub.lec_units, lab_units=sub.lab_units,
                                        year_level=sub.year_level, semester=sub.semester, created_by=user,
                                        confirmed=mine, confirmed_by=user if mine else None)
    g.programs.set(progs)
    return {"group_id": g.id, "confirmed": g.confirmed, "validation": res,
            "message": ("Shared class confirmed. Generate to create the one shared schedule." if g.confirmed else
                        "Saved. It includes another college's program, so the Registrar must confirm it before it is used.")}


@transaction.atomic
def confirm_group(user, group_id):
    if getattr(user, "role", "") != "registrar":
        raise SharedError("Only the Registrar confirms a shared class that spans colleges.", 403)
    g = SharedClassGroup.objects.filter(pk=group_id).first()
    if g is None:
        raise SharedError("Shared class not found.", 404)
    res = validate([p.id for p in g.programs.all()], g.code, g.lec_units, g.lab_units, g.title, g.year_level, g.semester)
    if not res["ok"]:
        raise SharedError(" ".join(res["errors"]), 422)
    g.confirmed, g.confirmed_by = True, user
    g.save(update_fields=["confirmed", "confirmed_by"])
    return {"group_id": g.id, "confirmed": True}


@transaction.atomic
def set_exclusive(user, program_id, subject_id):
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification="minor").first()
    if sub is None:
        raise SharedError("Minor subject not found.", 404)
    if not _may_edit(user) or not _owns_program(user, sub.program):
        raise SharedError("Only the Registrar changes shared Gen Ed classes (minor subjects belong to the Registrar).", 403)
    for g in SharedClassGroup.objects.filter(code=sub.code, year_level=sub.year_level, semester=sub.semester, programs=sub.program):
        g.programs.remove(sub.program)
        if g.programs.count() < MIN_PROGRAMS:
            g.delete()
    SharedClassExclusive.objects.get_or_create(program=sub.program, code=sub.code, year_level=sub.year_level, semester=sub.semester,
                                               defaults={"created_by": user})
    return {"mode": "exclusive"}


@transaction.atomic
def clear_choice(user, program_id, subject_id):
    """Back to automatic (the generator may still join equal classes when they fit)."""
    sub = Subject.objects.select_related("program").filter(pk=subject_id, classification="minor").first()
    if sub is None:
        raise SharedError("Minor subject not found.", 404)
    if not _may_edit(user) or not _owns_program(user, sub.program):
        raise SharedError("Only the Registrar changes shared Gen Ed classes (minor subjects belong to the Registrar).", 403)
    SharedClassExclusive.objects.filter(program=sub.program, code=sub.code, year_level=sub.year_level, semester=sub.semester).delete()
    for g in SharedClassGroup.objects.filter(code=sub.code, year_level=sub.year_level, semester=sub.semester, programs=sub.program):
        g.programs.remove(sub.program)
        if g.programs.count() < MIN_PROGRAMS:
            g.delete()
    return {"mode": "auto"}


# ----------------------------------------------------------------------------- used by the generator
def share_rules(year, sem):
    """{(program_id, code): ("exclusive", None) | ("group", frozenset(program ids))} for confirmed choices of this year level / semester."""
    out = {}
    for e in SharedClassExclusive.objects.filter(year_level=year, semester=sem):
        out[(e.program_id, e.code)] = ("exclusive", None)
    for g in SharedClassGroup.objects.filter(year_level=year, semester=sem, confirmed=True).prefetch_related("programs"):
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


def plan_members(host_section, subject, rules):
    """Sections of the other programs of the host's confirmed group that should join the host's class. -> ([sections], total students)"""
    r = rules.get((host_section.program_id, subject.code))
    if not r or r[0] != "group":
        return [], host_section.student_count
    progs = list(Program.objects.filter(pk__in=r[1]))
    cap = _group_capacity(progs)
    members, total = [], host_section.student_count
    already = set(Schedule.objects.filter(subject__code=subject.code, section__semester=host_section.semester,
                                          section__year_level=host_section.year_level).values_list("section_id", flat=True))
    others = [s for pid in r[1] if pid != host_section.program_id
              for s in Section.objects.filter(program_id=pid, year_level=host_section.year_level, semester=host_section.semester).select_related("program")
              if s.id not in already and _subject_of(s.program, subject.code, subject.lec_units, subject.lab_units, subject.title,
                                                    s.year_level, s.semester) is not None]
    for s in sorted(others, key=lambda s: (-s.student_count, s.program.name, s.name)):
        if any(m.program_id == s.program_id for m in members):
            continue
        if cap and total + s.student_count <= cap:
            members.append(s); total += s.student_count
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
            msub = _subject_of(m.program, subject.code, subject.lec_units, subject.lab_units, subject.title, m.year_level, m.semester)
            if msub is None:
                entry["skipped"].append(f"{m.program.name} {m.name}: its curriculum differs")
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
