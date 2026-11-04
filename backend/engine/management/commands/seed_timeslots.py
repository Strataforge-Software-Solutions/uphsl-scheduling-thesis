"""
Creates the class time slots the scheduler can use: hourly (plus 30-minute ones for Nursing's 1.5 h x 2 day lectures), Monday-Saturday,
7:00 AM - 8:00 PM, INCLUDING 12:00-1:00 PM: lunch is not a fixed period in the college (students and professors eat in their free
time between classes), so classes may start, end or run through noon. Re-running it on a database that was seeded with the old
lunch hour adds the missing 12:00-1:00 PM slots (hourly and 30-minute) and changes nothing else.

    python manage.py seed_timeslots
    python manage.py seed_timeslots --start 7 --end 21 --days Mon,Tue,Wed,Thu,Fri,Sat
    python manage.py seed_timeslots --lunch 12     # the old behaviour: leave 12:00-1:00 PM out

Why this matters: each class is now one continuous block (a 3-unit lecture is
3 hours in a row, a lab unit is 3 hours). The original demo only had five
short slots a day (8-11 and 1-3), which leaves room for just five 3-hour blocks
a week -- labs could not be placed. Safe to re-run; existing slots are kept.
"""
from datetime import time

from django.core.management.base import BaseCommand

from engine.models import TimeSlot


class Command(BaseCommand):
    help = "Create hourly (and 30-minute) Mon-Sat time slots, 7AM-8PM, noon included. Safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=int, default=7)
        parser.add_argument("--end", type=int, default=20)
        parser.add_argument("--lunch", type=int, default=-1, help="An hour to leave out (default: none; 12 = the old lunch hour).")
        parser.add_argument("--no-half", action="store_true", help="Skip the 30-minute slots (needed only for Nursing's 1.5-hour two-day classes).")
        parser.add_argument("--days", default="Mon,Tue,Wed,Thu,Fri,Sat")

    def handle(self, *args, **o):
        made = 0
        for day in [d.strip() for d in o["days"].split(",") if d.strip()]:
            for h in range(o["start"], o["end"]):
                if h == o["lunch"]:
                    continue
                _, created = TimeSlot.objects.get_or_create(day=day, start_time=time(h, 0), end_time=time(h + 1, 0))
                made += created
        if not o["no_half"]:
            # 30-minute slots: used ONLY by Nursing-style 1.5 h x 2 days lectures.
            # Ordinary classes keep using the hourly slots above.
            for day in [d.strip() for d in o["days"].split(",") if d.strip()]:
                for h in range(o["start"], o["end"]):
                    if h == o["lunch"]:
                        continue
                    for m in (0, 30):
                        st = time(h, m)
                        en = time(h, 30) if m == 0 else time(h + 1, 0)
                        _, created = TimeSlot.objects.get_or_create(day=day, start_time=st, end_time=en)
                        made += created
        self.stdout.write(self.style.SUCCESS(f"Done. {made} time slots created ({TimeSlot.objects.count()} total)."))
