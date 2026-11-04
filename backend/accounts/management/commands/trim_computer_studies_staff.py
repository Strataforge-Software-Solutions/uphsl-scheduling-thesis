"""
Keeps ONLY the real Computer Studies faculty: the Dean + the six teachers of setup_ccs_faculty.py (Ang, Olino, De Luna, Mazo,
Dr. Verano, Rodel Tungol). Every other faculty account of Computer Studies (for example the ones add_department_staff added) is removed.

    python manage.py trim_computer_studies_staff                  # preview: who stays, who goes, what they teach
    python manage.py trim_computer_studies_staff --apply          # remove the ones with NO classes / exams
    python manage.py trim_computer_studies_staff --apply --force  # also remove the ones with classes (their classes and exams are
                                                                  # deleted too; then Generate / Resolve the Computer Studies schedule again)
    python manage.py trim_computer_studies_staff --keep F1056,P1045   # accounts to keep as well (by School ID)

Never touched: the Dean, the IT admin / registrar / any non-faculty account, and anyone in another department.
Rodel Tungol (teacher AND the campus IT admin) stays as a teacher; his admin login is a different account and is not touched.
The Dean teaches only through the specializations set on the account (BS Information Technology), so the scheduler gives them
Computer Studies / IT subjects only.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import Collector

from accounts.management.commands.setup_ccs_faculty import PEOPLE

User = get_user_model()


def real_names():
    return {f"{f} {l}".lower() for f, l, *_ in PEOPLE}


def _counts(user):
    c = Collector(using="default")
    c.collect([user])
    out = {}
    for model, objs in c.data.items():
        out[model._meta.model_name] = len(objs)
    return out.get("schedule", 0), out.get("examschedule", 0)


class Command(BaseCommand):
    help = "Remove the Computer Studies faculty accounts that are not the Dean or the six real teachers."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")
        p.add_argument("--force", action="store_true", help="also remove accounts that have classes/exams (those are deleted too)")
        p.add_argument("--keep", default="", help="School IDs to keep, comma separated")

    @transaction.atomic
    def handle(self, *a, **o):
        keep_ids = {x.strip().lower() for x in o["keep"].split(",") if x.strip()}
        real = real_names()
        qs = (User.objects.filter(role="faculty").exclude(faculty_type="dean")
              .filter(Q(department__iexact="Computer Studies") | Q(department__icontains="computer studies")).order_by("faculty_type", "school_id"))
        stay, go = [], []
        for u in qs:
            name = u.get_full_name().strip().lower().replace("dr. ", "")
            (stay if (u.get_full_name().strip().lower() in real or name in {r.replace("dr. ", "") for r in real}
                      or (u.school_id or "").lower() in keep_ids) else go).append(u)
        self.stdout.write(f"Staying ({len(stay)}):")
        for u in stay:
            self.stdout.write(f"   {u.school_id:7} {u.get_full_name()}  ({u.faculty_type})")
        if len(stay) != len(real):
            self.stdout.write(self.style.WARNING(
                f"   Expected {len(real)} real teachers but found {len(stay)}: run  python manage.py setup_ccs_faculty --apply  first if one is missing."))
        self.stdout.write(f"To remove ({len(go)}):")
        removed = skipped = 0
        for u in go:
            sch, ex = _counts(u)
            busy = sch or ex
            tag = f"{sch} class(es), {ex} exam(s)" if busy else "no classes or exams"
            if o["apply"] and (not busy or o["force"]):
                u.delete()
                removed += 1
                self.stdout.write(f"   removed {u.school_id:7} {u.get_full_name()}  ({tag})")
            else:
                skipped += 1
                self.stdout.write(f"   {'KEPT (has classes; use --force)' if o['apply'] else 'would remove'} {u.school_id:7} {u.get_full_name()}  ({tag})")
        if not o["apply"]:
            transaction.set_rollback(True)
            self.stdout.write(self.style.SUCCESS("Preview only. Add --apply to remove."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Removed {removed}; {skipped} kept because they still have classes/exams."
                                                 + (" Generate the Computer Studies schedule again." if removed else "")))
