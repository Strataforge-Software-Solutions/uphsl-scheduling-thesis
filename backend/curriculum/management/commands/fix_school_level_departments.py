"""
Undo a "College of" prefix that was added to a SCHOOL LEVEL by mistake (an older prefix_departments renamed "SHS" to "College of SHS").
SHS / JHS are a different school level, not a college, so "College of SHS" goes back to "SHS" (and likewise for JHS, Senior / Junior
High School, Basic Education, Elementary ...), in the same places prefix_departments changes: accounts (department and extra
departments), programs, rooms, constraints and building preferences. Nothing else is touched.

    python manage.py fix_school_level_departments            # preview only
    python manage.py fix_school_level_departments --apply    # do it
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.management.commands.prefix_departments import SCHOOL_LEVELS

_PREFIX = re.compile(r"^\s*(college|school|institute) of\s+(.+?)\s*$", re.I)


def original(name):
    """'College of SHS' -> 'SHS' when the rest is a school level; otherwise None."""
    m = _PREFIX.match(name or "")
    return m.group(2) if m and m.group(2).strip().lower() in SCHOOL_LEVELS else None


class Command(BaseCommand):
    help = "Remove a mistaken 'College of' prefix from school-level departments (e.g. 'College of SHS' -> 'SHS')."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *a, **o):
        from accounts.models import User
        from curriculum.models import Program
        from engine.models import Constraint
        from rooms.models import DepartmentBuilding, Room

        models = ((User, "accounts"), (Program, "programs"), (Room, "rooms"), (Constraint, "constraints"),
                  (DepartmentBuilding, "building preferences"))
        names = set()
        for model, _label in models:
            names |= {d for d in model.objects.values_list("department", flat=True) if original(d)}
        extra = [u for u in User.objects.exclude(extra_departments="") if any(original(x.strip()) for x in u.extra_departments.split(";"))]
        mapping = {n: original(n) for n in sorted(names)}
        if not mapping and not extra:
            self.stdout.write("Nothing to fix: no school level has a 'College of' prefix.")
            return
        for old, new in mapping.items():
            self.stdout.write(f"  {old!r} -> {new!r}")
        for model, label in models:
            rows = list(model.objects.filter(department__in=list(mapping)))
            if rows:
                who = ", ".join(getattr(r, "school_id", None) or getattr(r, "name", None) or str(r.pk) for r in rows[:10])
                self.stdout.write(f"  {label}: {len(rows)} ({who})")
        for u in extra:
            self.stdout.write(f"  extra departments of {u.school_id}: {u.extra_departments!r}")
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to make the change."))
            return
        with transaction.atomic():
            for old, new in mapping.items():
                for model, _label in models:
                    if model is DepartmentBuilding and DepartmentBuilding.objects.filter(department=new).exists():
                        DepartmentBuilding.objects.filter(department=old).delete()     # the level already has its own preference
                        continue
                    model.objects.filter(department=old).update(department=new)
            for u in extra:
                u.extra_departments = ";".join(original(x.strip()) or x.strip() for x in u.extra_departments.split(";") if x.strip())
                u.save(update_fields=["extra_departments"])
        self.stdout.write(self.style.SUCCESS("Done. Sign out and back in so the dashboards reload."))
