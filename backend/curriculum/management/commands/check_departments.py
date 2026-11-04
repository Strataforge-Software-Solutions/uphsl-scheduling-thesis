"""
Find (and optionally fix) department-name mismatches between programs and accounts.
The system matches department names EXACTLY, so "College of Computer studies" on a program and
"College of Computer Studies" on the Dean means the Dean sees no programs.

  python manage.py check_departments            # report only
  python manage.py check_departments --apply    # make accounts / rooms use the PROGRAM's spelling
"""
import re
from django.core.management.base import BaseCommand
from django.db import transaction


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


class Command(BaseCommand):
    help = "Report/fix department names that differ only by case or spacing."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *a, **o):
        from accounts.models import User
        from curriculum.models import Program
        from rooms.models import Room, DepartmentBuilding

        prog = sorted(set(Program.objects.values_list("department", flat=True)))
        self.stdout.write("Program departments:")
        for d in prog:
            self.stdout.write(f"  {d!r}  ({Program.objects.filter(department=d).count()} program(s))")
        canon = {}
        for d in prog:
            canon.setdefault(norm(d), d)

        fixes = []          # (model, old, new)
        problems = 0
        users = User.objects.filter(role__in=["faculty", "registrar"])
        seen = {}
        for u in users:
            for field in ("department",):
                d = getattr(u, field)
                if d:
                    seen.setdefault(d, []).append(u.username)
        for d, names in sorted(seen.items()):
            if d in prog:
                continue
            if norm(d) in canon:
                fixes.append(("accounts", d, canon[norm(d)]))
                self.stdout.write(self.style.WARNING(f"Accounts with {d!r} ({len(names)}) -> should be {canon[norm(d)]!r}"))
            else:
                problems += 1
                self.stdout.write(self.style.ERROR(f"Accounts with {d!r} ({len(names)}, e.g. {names[0]}) match NO program department."))
        for rd in sorted({d for d in Room.objects.values_list("department", flat=True) if d}):
            if rd not in prog and norm(rd) in canon:
                fixes.append(("rooms", rd, canon[norm(rd)]))
                self.stdout.write(self.style.WARNING(f"Rooms with {rd!r} -> should be {canon[norm(rd)]!r}"))
        deans = User.objects.filter(role="faculty", faculty_type="dean")
        for u in deans:
            ok = [d for d in u.departments if d in prog]
            if not ok:
                self.stdout.write(self.style.ERROR(f"Dean {u.username} ({u.departments}) can see NO programs."))
        if not fixes:
            self.stdout.write("No case/spacing mismatches found." + (f" {problems} department name(s) match no program at all: rename them to an existing program department (or use prefix_departments)." if problems else ""))
            return
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("Report only. Add --apply to fix."))
            return
        with transaction.atomic():
            for kind, old, new in fixes:
                if kind == "accounts":
                    users.filter(department=old).update(department=new)
                else:
                    Room.objects.filter(department=old).update(department=new)
        self.stdout.write(self.style.SUCCESS(f"Fixed {len(fixes)} name(s)."))
