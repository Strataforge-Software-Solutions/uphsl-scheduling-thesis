"""
Let ONE dean head several departments, all in a single Dean dashboard.

    python manage.py share_dean --dean DeanCBA --also "College of International Hospitality Management"
    python manage.py share_dean --dean DeanCBA --also "College of International Hospitality Management" --remove-dean DeanCIHM
    python manage.py share_dean --dean DeanCBA --clear          # back to their own department only

What the dean then sees (curriculum, schedules, exam schedule, class lists, faculty roster,
faculty coverage, analytics): the programs and faculty of ALL their departments, with a
program drop-down to switch between them. --remove-dean deletes the now-unneeded second
dean login (only if you name it).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Make one dean cover more than one department."

    def add_arguments(self, parser):
        parser.add_argument("--dean", required=True, help="Dean's username, e.g. DeanCBA")
        parser.add_argument("--also", action="append", default=[], help="Extra department name (repeatable)")
        parser.add_argument("--remove-dean", help="Username of the second dean login to delete")
        parser.add_argument("--clear", action="store_true", help="Remove all extra departments")

    def handle(self, *args, **o):
        dean = User.objects.filter(username=o["dean"], role="faculty", faculty_type="dean").first()
        if not dean:
            raise CommandError(f"No dean login named {o['dean']!r}.")
        if o["clear"]:
            dean.extra_departments = ""
        else:
            extras = [d for d in dean.extra_departments.split(";") if d.strip()]
            for d in o["also"]:
                d = d.strip()
                if d and d != dean.department and d not in extras:
                    extras.append(d)
            dean.extra_departments = ";".join(extras)
        dean.save(update_fields=["extra_departments"])
        self.stdout.write(self.style.SUCCESS(f"{dean.username} now covers: {' + '.join(dean.departments)}"))
        if o["remove_dean"]:
            other = User.objects.filter(username=o["remove_dean"], role="faculty", faculty_type="dean").first()
            if not other:
                self.stdout.write(f"  (no dean login named {o['remove_dean']!r} to remove)")
            elif other.pk == dean.pk:
                raise CommandError("--remove-dean cannot be the same login.")
            else:
                other.delete()
                self.stdout.write(f"  removed dean login {o['remove_dean']}")
        self.stdout.write("The dean must sign out and in again to see the change.")
