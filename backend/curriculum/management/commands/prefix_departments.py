"""
Rename every college department to "College of <name>" in ONE consistent pass, so programs, deans,
faculty, rooms and building preferences all keep matching (the system matches department names exactly).

  python manage.py prefix_departments            # preview only: shows what would change
  python manage.py prefix_departments --apply    # do it
  python manage.py prefix_departments --skip "Allied Health" --skip "Nursing"   # leave some as they are

Only departments used by programs, deans or college faculty are renamed; nothing is deleted.
Names that already start with "College of" / "School of" are left alone. School levels (SHS, JHS, Senior / Junior High School,
Basic Education, Elementary) are NEVER renamed, whatever role the account has: they are a different school level, not a college.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

PREFIXES = ("college of", "school of", "institute of")
# school levels, not colleges: never prefixed (e.g. a faculty account whose department is "SHS" stays "SHS")
SCHOOL_LEVELS = {"shs", "jhs", "senior high school", "junior high school", "senior high", "junior high", "basic education",
                 "basic ed", "elementary", "grade school", "integrated school"}


class Command(BaseCommand):
    help = "Prefix department names with 'College of' everywhere, consistently."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--skip", action="append", default=[], help="department name to leave unchanged (repeatable)")
        parser.add_argument("--prefix", default="College of ")

    def handle(self, *a, **o):
        from accounts.models import User
        from curriculum.models import Program
        from rooms.models import Room, DepartmentBuilding
        from engine.models import Constraint

        college_users = User.objects.filter(role__in=["faculty", "registrar"])
        names = set(Program.objects.values_list("department", flat=True))
        names |= {d for d in college_users.values_list("department", flat=True) if d}
        for ed in college_users.values_list("extra_departments", flat=True):
            names |= {x.strip() for x in (ed or "").split(";") if x.strip()}
        skip = {s.strip().lower() for s in o["skip"]}
        mapping = {n: o["prefix"] + n.strip() for n in sorted(names)
                   if n and not n.strip().lower().startswith(PREFIXES) and n.strip().lower() not in skip
                   and n.strip().lower() not in SCHOOL_LEVELS}
        if not mapping:
            self.stdout.write("Nothing to rename: every department already has a prefix.")
            return

        self.stdout.write("Departments to rename:")
        for k, v in mapping.items():
            self.stdout.write(f"  {k!r} -> {v!r}")

        def count(model, field):
            return model.objects.filter(**{f"{field}__in": list(mapping)}).count()
        self.stdout.write(f"Rows affected: programs={count(Program,'department')}, "
                          f"users={User.objects.filter(role__in=['faculty','registrar'], department__in=list(mapping)).count()}, "
                          f"rooms={count(Room,'department')}, building prefs={count(DepartmentBuilding,'department')}")
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to make the change."))
            return

        with transaction.atomic():
            for old, new in mapping.items():
                Program.objects.filter(department=old).update(department=new)
                Room.objects.filter(department=old).update(department=new)
                Constraint.objects.filter(department=old).update(department=new)
                college_users.filter(department=old).update(department=new)
                b = DepartmentBuilding.objects.filter(department=old).first()
                if b:
                    if DepartmentBuilding.objects.filter(department=new).exists():
                        b.delete()          # the prefixed name already has its own building preference
                    else:
                        b.department = new
                        b.save(update_fields=["department"])
            for u in college_users.exclude(extra_departments=""):
                parts = [x.strip() for x in u.extra_departments.split(";") if x.strip()]
                new_parts = [mapping.get(p, p) for p in parts]
                if new_parts != parts:
                    u.extra_departments = ";".join(new_parts)
                    u.save(update_fields=["extra_departments"])
        self.stdout.write(self.style.SUCCESS("Done. Sign out and back in so the dashboards reload."))
