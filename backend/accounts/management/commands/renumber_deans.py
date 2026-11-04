"""
Give every Dean the standard login UPHM-D####  (D1001, D1002, D1003 ...).

  python manage.py renumber_deans            # preview only
  python manage.py renumber_deans --apply    # do it

Deans whose School ID is already D#### are left alone. The others (e.g. CAS, CBA, NURS -> DeanCAS ...)
get the next free number, in the order their accounts were created. The username becomes UPHM-<new ID>.
If a dean is still on the default password (never changed it) the default becomes the NEW School ID; a dean who
already chose their own password keeps it. Nothing else about the account (name, college, schedules) changes.
"""
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.views import next_school_id

User = get_user_model()


class Command(BaseCommand):
    help = "Renumber Dean accounts to UPHM-D1001, D1002, D1003 ..."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")

    def handle(self, *a, **o):
        out = self.stdout.write
        with transaction.atomic():
            for u in User.objects.filter(role="faculty", faculty_type="dean").order_by("id"):
                if re.fullmatch(r"D\d+", u.school_id or ""):
                    out(f"  ok       {u.username} {u.get_full_name()!r}")
                    continue
                new = next_school_id(prefix="D")
                out(f"  renumber {u.username} ({u.school_id}) -> UPHM-{new}   {u.get_full_name()!r}   {u.department}")
                u.school_id, u.username = new, f"UPHM-{new}"
                if u.must_change_password:                       # still on the default: default follows the ID
                    u.set_password(new)
                u.save()
            if not o["apply"]:
                transaction.set_rollback(True)
        out(self.style.SUCCESS("Applied.") if o["apply"] else self.style.WARNING("Preview only. Add --apply to make the change."))
