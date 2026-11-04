"""
Show the real names of the college deans and the SHS/JHS principal on their dashboards.

Changes ONLY first_name / last_name of these existing accounts. Usernames, School IDs, passwords, roles, departments and
permissions are never touched, and an account that does not exist is reported, not created.

    python manage.py set_leadership_names            # apply
    python manage.py set_leadership_names --dry-run  # show what would change
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

# (usernames to try, department keywords of the dean's college, first_name, last_name, label)
# Real databases differ in how a dean's LOGIN is spelled (DeanRT, UPHM-D1005, ...), so a dean is found by login name
# first and otherwise by role (dean) + college -- never by guessing across colleges.
LEADERSHIP = [
    (["DeanRT", "DeanRadtech"],   ["radiolog"],                  "Dr. Noel Juan", "Acosta",  "Dean, Radiologic Technology"),
    (["DeanCAS", "DeanCas"],      ["arts and science", "arts & sciences", "arts and sciences"], "Dr. Marivic D.", "Tañedo", "Dean, College of Arts and Science"),
    (["DeanCBA", "DeanBA"],       ["business"],                  "Julius", "Mesina",         "Dean, CBA & ITHM"),
    (["DeanNursing"],             ["nursing"],                   "Darwin D.", "Aznar",       "Dean, Nursing"),
]
PRINCIPALS = (["PrincipalSHS", "PrincipalJHS"], "Sheryl B.", "Gamboa", "SHS & JHS Principal")


def _find(User, usernames, keywords):
    found = list(User.objects.filter(username__in=usernames))
    if found or not keywords:
        return found
    deans = User.objects.filter(role="faculty", faculty_type="dean", is_active=True)
    return [u for u in deans if any(k in (" ; ".join(u.departments)).lower() for k in keywords)]


class Command(BaseCommand):
    help = "Set the displayed names of the deans and the SHS/JHS principal (names only)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        jobs = [(u, k, f, l, lab) for u, k, f, l, lab in LEADERSHIP]
        jobs.append((PRINCIPALS[0], None, PRINCIPALS[1], PRINCIPALS[2], PRINCIPALS[3]))
        for usernames, keywords, first, last, label in jobs:
            if keywords is None:     # principals: by login name, or any active principal account
                found = list(User.objects.filter(username__in=usernames)) or list(User.objects.filter(role="principal", is_active=True))
            else:
                found = _find(User, usernames, keywords)
            if not found:
                self.stdout.write(self.style.WARNING(f"{label}: no matching active account found -- nothing changed."))
                continue
            for u in found:
                before = u.get_full_name()
                if (u.first_name, u.last_name) == (first, last):
                    self.stdout.write(f"{u.username} ({label}): already {before}")
                    continue
                u.first_name, u.last_name = first, last
                if not opts["dry_run"]:
                    u.save(update_fields=["first_name", "last_name"])
                self.stdout.write(self.style.SUCCESS(f"{u.username} ({label}): {before or '(no name)'} -> {u.get_full_name()}"))
        if opts["dry_run"]:
            transaction.set_rollback(True)
            self.stdout.write("Dry run: nothing was saved.")
