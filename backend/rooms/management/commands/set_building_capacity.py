"""
Raise the seat count of the ordinary classrooms in one building.

    python manage.py set_building_capacity --building M --capacity 40            (preview)
    python manage.py set_building_capacity --building M --capacity 40 --apply

Only rooms in that building that currently hold FEWER seats than the new number
are changed, and they are marked as estimates. Rooms that already hold more
(labs, the auditorium) are left alone.
"""
from django.core.management.base import BaseCommand

from rooms.models import Room


class Command(BaseCommand):
    help = "Raise classroom capacity for one building (M, D, A or N)."

    def add_arguments(self, parser):
        parser.add_argument("--building", required=True, choices=["M", "D", "A", "N"])
        parser.add_argument("--capacity", required=True, type=int)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        qs = Room.objects.filter(building=o["building"], room_type__in=["lecture", "lab"], capacity__lt=o["capacity"])
        for r in qs:
            self.stdout.write(f"  {r.name:16} {r.capacity} -> {o['capacity']}")
        n = qs.count()
        if o["apply"]:
            qs.update(capacity=o["capacity"], capacity_is_estimate=True)
        self.stdout.write(self.style.SUCCESS(f"{n} room(s) {'updated' if o['apply'] else 'would be updated'}."))
        if n and not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to save."))
