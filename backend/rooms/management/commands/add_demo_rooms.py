"""
Adds extra demo classrooms to the Main (M), Alta (D), Alfredo (A) and New (N)
buildings so the demo has room to spare. They are plain lecture rooms, labelled
"Demo room", with estimated capacities (M 40, D 30, A 32, N 25).

    python manage.py add_demo_rooms            (add them)
    python manage.py add_demo_rooms --remove   (delete the demo rooms again)

Existing rooms are never touched; only room numbers that don't exist yet are added.
Rooms that are already used by a schedule are not deleted by --remove.
"""
from django.core.management.base import BaseCommand

from rooms.models import Room

CAPACITY = {"M": 40, "D": 30, "A": 32, "N": 25}
LABEL = "Demo room"
# floor x room-on-floor: 101..104, 201..204, ... 601..604 (24 per building)
NUMBERS = [f"{floor}{n:02d}" for floor in range(1, 7) for n in range(1, 5)]


class Command(BaseCommand):
    help = "Add (or remove) demo lecture rooms in buildings M, D, A and N."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, **o):
        if o["remove"]:
            qs = Room.objects.filter(label=LABEL, schedule__isnull=True, examschedule__isnull=True).distinct()
            n = qs.count()
            qs.delete()
            self.stdout.write(self.style.SUCCESS(f"{n} demo room(s) removed."))
            return
        made = 0
        for b, cap in CAPACITY.items():
            for num in NUMBERS:
                _, created = Room.objects.get_or_create(
                    name=f"{b}-{num}",
                    defaults=dict(building=b, room_number=num, label=LABEL, capacity=cap,
                                  capacity_is_estimate=True, room_type="lecture"),
                )
                made += created
        self.stdout.write(self.style.SUCCESS(
            f"{made} demo rooms added ({Room.objects.count()} rooms total). "
            "Up to 24 per building (101-104 ... 601-604); room numbers that already existed were skipped."))
