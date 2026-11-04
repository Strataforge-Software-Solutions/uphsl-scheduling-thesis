"""
Merge duplicate programs, e.g. "BS Physical Theraphy" (typo) into "BS Physical Therapy".

  python manage.py merge_duplicate_programs                  # preview only
  python manage.py merge_duplicate_programs --apply          # do it

Duplicates are programs of the same department whose names are equal after fixing known typos and ignoring
case / spaces / punctuation. The correctly spelled (or, failing that, the fuller) program is kept. Its duplicate's
sections, subjects, schedules, exams, class lists ... are MOVED to it (nothing is deleted with the duplicate), then the
empty duplicate program is removed. Everything runs in one transaction: any problem undoes it all.
"""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from curriculum.models import Program, Subject
from engine.models import Section

TYPOS = {"THERAPHY": "THERAPY", "PHYSICALTHERAPHY": "PHYSICALTHERAPY"}


def _key(name):
    k = re.sub(r"[^A-Z0-9]", "", (name or "").upper())
    for bad, good in TYPOS.items():
        k = k.replace(bad, good)
    return k


def _spelled_ok(name):
    return not any(b in re.sub(r"[^A-Z0-9]", "", name.upper()) for b in TYPOS)


def _move_refs(old, new):
    """Point every row that references `old` at `new` instead (generic over all related models)."""
    n = 0
    for rel in old._meta.related_objects:
        if not rel.one_to_many:
            continue
        n += rel.related_model._default_manager.filter(**{rel.field.name: old}).update(**{rel.field.name: new})
    return n


class Command(BaseCommand):
    help = "Merge duplicate programs (e.g. a misspelt copy) into one."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="Make the change (default: preview).")

    def handle(self, *a, **o):
        apply_ = o["apply"]
        groups = defaultdict(list)
        for pr in Program.objects.all():
            groups[(pr.department.strip().upper(), _key(pr.name))].append(pr)
        dups = [g for g in groups.values() if len(g) > 1]
        if not dups:
            self.stdout.write("No duplicate programs found.")
            return
        try:
            with transaction.atomic():
                for g in dups:
                    g.sort(key=lambda x: (not _spelled_ok(x.name), -x.subjects.count(), x.id))
                    keep, extra = g[0], g[1:]
                    for dup in extra:
                        self.stdout.write(f"{dup.name!r} (id {dup.id}, {dup.subjects.count()} subjects, {dup.sections.count()} sections)"
                                          f" -> merge into {keep.name!r} (id {keep.id})")
                        # subjects: same code/year/semester already in the kept program -> move that subject's rows onto it
                        for sub in list(dup.subjects.all()):
                            twin = Subject.objects.filter(program=keep, code=sub.code, year_level=sub.year_level, semester=sub.semester).first()
                            if twin:
                                _move_refs(sub, twin)
                                sub.delete()
                            else:
                                sub.program = keep
                                sub.save(update_fields=["program"])
                        for sec in list(dup.sections.all()):
                            twin = Section.objects.filter(program=keep, name=sec.name, year_level=sec.year_level, semester=sec.semester).first()
                            if twin:
                                _move_refs(sec, twin)
                                sec.delete()
                            else:
                                sec.program = keep
                                sec.save(update_fields=["program"])
                        _move_refs(dup, keep)
                        dup.delete()
                if not apply_:
                    transaction.set_rollback(True)
        except Exception as e:
            raise CommandError(f"Nothing was changed: {e}")
        self.stdout.write(self.style.SUCCESS("Merged." if apply_ else "Preview only. Run again with --apply to merge."))
