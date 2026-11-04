"""
Shared (merged) minor classes.

A minor/Gen Ed subject (same code, same year level and semester) is normally
scheduled once PER program section. When another department already has that
class and its room still has seats for this section's students, this section
JOINS it instead of getting a class of its own: same teacher, same room, same
time. Only specific departments merge -- whichever fit in the room:
    8 BA Comm + 30 CS = 38 students  ->  fits a 40-seat room, so they share.
    20 + 30 + 25 = 75                 ->  too many for a 40-seat room, so not merged.

Only lecture-type minors join (not labs). Rows of one shared class carry the same
Schedule.merge_key. Nothing here relaxes any other rule: the joining section must
itself be free at that time.
"""
from collections import defaultdict

from .models import Schedule
from .scheduler import _slots_overlap
from rooms.rules import may_use


def _fits(section, rows_by_section, room, extra_students):
    cap = getattr(room, "capacity", 0) or 0
    if not cap:
        return False
    total = sum(sec.student_count for sec in rows_by_section) + extra_students
    return total <= cap


def join_minor_classes(subjects_by_section, school_year, rules=None):
    """Mutates subjects_by_section (removes the subjects that joined an existing
    class) and creates the joined Schedule rows. Returns a list of dicts
    describing each merge, for the Registrar's report."""
    report = []
    for section, subjects in list(subjects_by_section.items()):
        own_rows = list(Schedule.objects.filter(section=section).select_related("timeslot"))
        for subject in list(subjects):
            if subject.classification != "minor" or subject.lab_units > 0:
                continue
            host_rows = (Schedule.objects
                         .filter(subject__code=subject.code, subject__classification="minor",
                                 # truly the same course: same units and title (FCL 1 at 3 units is not FCL 1 at 2 units)
                                 subject__lec_units=subject.lec_units, subject__lab_units=subject.lab_units,
                                 subject__title__iexact=subject.title,
                                 section__year_level=section.year_level, section__semester=section.semester)
                         .exclude(section=section)
                         .exclude(section__program=section.program)
                         .select_related("section", "section__program", "room", "teacher", "timeslot"))
            groups = defaultdict(list)           # group id -> rows
            from .shared_classes import may_share
            for r in host_rows:
                if rules and not may_share(rules, section.program_id, r.section.program_id, subject.code):
                    continue                      # the Dean / Registrar chose exclusive, or a different group, for this subject
                groups[r.merge_key or f"host-{r.section_id}"].append(r)

            best = None
            for gid, rows in groups.items():
                first_section = rows[0].section_id
                block = [r for r in rows if r.section_id == first_section]
                if len({r.room_id for r in block}) != 1 or len({r.teacher_id for r in block}) != 1:
                    continue
                members = {r.section_id: r.section for r in rows}
                room = block[0].room
                if not may_use(room, getattr(section.program, "department", None)):
                    continue                      # the host class sits in a room reserved for another department
                if not _fits(section, members.values(), room, section.student_count):
                    continue
                if any(_slots_overlap(b.timeslot, o.timeslot) for b in block for o in own_rows):
                    continue                      # this section already has something at that time
                total = sum(m.student_count for m in members.values())
                key = (total, -min(members))
                if best is None or key > best[0]:
                    best = (key, gid, block, members)
            if best is None:
                continue

            _, gid, block, members = best
            merge_key = block[0].merge_key or \
                f"{subject.code}|{section.year_level}|{section.semester}|{min(members)}"[:80]
            if not block[0].merge_key:
                Schedule.objects.filter(pk__in=[r.pk for r in block]).update(merge_key=merge_key)
            new_rows = [
                Schedule(subject=subject, teacher=b.teacher, room=b.room, section=section, timeslot=b.timeslot,
                         school_year=school_year, status="draft", merge_key=merge_key, term=section.semester)
                for b in block
            ]
            created = Schedule.objects.bulk_create(new_rows)
            own_rows.extend(created)
            subjects.remove(subject)
            total = sum(m.student_count for m in members.values()) + section.student_count
            report.append({
                "subject": f"{subject.code} - {subject.title}",
                "section": str(section),
                "joined": [f"{m.program.name} {m.name}" for m in members.values()],
                "students": total,
                "room": block[0].room.name,
                "capacity": block[0].room.capacity,
                "schedule_ids": [r.id for r in created],
            })
    return report
