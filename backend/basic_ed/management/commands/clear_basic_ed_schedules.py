"""
Erase generated SHS / JHS schedules (all versions) so they can be generated again.

    python manage.py clear_basic_ed_schedules --level SHS            # preview
    python manage.py clear_basic_ed_schedules --level SHS --apply    # delete
    python manage.py clear_basic_ed_schedules --level JHS --period 1 --apply
Curriculum, sections, rooms and teachers are never touched.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed.models import ScheduleRun


class Command(BaseCommand):
    help = "Delete generated SHS/JHS schedules (not the curriculum, sections, rooms or teachers)."

    def add_arguments(self, p):
        p.add_argument("--level", choices=["SHS", "JHS"])
        p.add_argument("--period", type=int)
        p.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *a, **o):
        qs = ScheduleRun.objects.all()
        if o["level"]:
            qs = qs.filter(level=o["level"])
        if o["period"]:
            qs = qs.filter(grading_period=o["period"])
        n = qs.count()
        self.stdout.write(f"{n} schedule version(s) {'deleted' if o['apply'] else 'would be deleted'}.")
        if o["apply"]:
            qs.delete()
        else:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to delete."))
