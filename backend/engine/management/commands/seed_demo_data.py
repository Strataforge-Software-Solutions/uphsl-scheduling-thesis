"""
Seeds infrastructure needed to run the scheduling engine -- rooms, timeslots,
and one login per role. Deliberately does NOT create any Program/Subject/
Section anymore: that used to collide with seed_bscs_curriculum (both wrote
into the same "BS Computer Science" program, creating duplicate subjects
like CS101 alongside the real CS1101, and duplicate sections "1A" alongside
"A"), which is what caused Generate Schedule to blow up with thousands of
false conflicts. Run seed_bscs_curriculum separately for real curriculum data.

Run with:  python manage.py seed_demo_data
"""
from datetime import time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from faculty.models import FacultyProfile
from rooms.models import Room
from engine.models import TimeSlot

User = get_user_model()


class Command(BaseCommand):
    help = "Seed rooms, timeslots, and one login per role (no curriculum -- see seed_bscs_curriculum)."

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        room_lecture, _ = Room.objects.get_or_create(
            name="Room 201", defaults={"capacity": 45, "room_type": "lecture", "department": "Computer Studies"}
        )
        room_lab, _ = Room.objects.get_or_create(
            name="Comp Lab C", defaults={"capacity": 30, "room_type": "lab", "department": "Computer Studies",
                                         "building": "D", "room_number": "307", "label": "Comp Lab C"}
        )
        Room.objects.get_or_create(
            name="Comp Lab D", defaults={"capacity": 30, "room_type": "lab", "department": "Computer Studies",
                                         "building": "D", "room_number": "309", "label": "Comp Lab D"}
        )

        days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        hours = [(8, 9), (9, 10), (10, 11), (13, 14), (14, 15)]
        for day in days:
            for start_h, end_h in hours:
                TimeSlot.objects.get_or_create(
                    day=day, start_time=time(start_h, 0), end_time=time(end_h, 0)
                )

        def make_user(school_id, first, last, role, faculty_type=None, department=None):
            user, created = User.objects.get_or_create(
                school_id=school_id,
                defaults={
                    "first_name": first, "last_name": last,
                    "role": role, "faculty_type": faculty_type, "department": department,
                    "must_change_password": True,
                },
            )
            if created:
                user.set_password(school_id)  # default password = school ID
                user.save()
                if role == "faculty":
                    FacultyProfile.objects.get_or_create(user=user)
            return user

        make_user("R1001", "Ana", "Reyes", "registrar")
        make_user("D1001", "Miguel", "Santos", "faculty", "dean", "Computer Studies")
        make_user("F1001", "Liza", "Cruz", "faculty", "full_time", "Computer Studies")
        # Part-time faculty get a "P"-prefixed school_id/username -- was "F1002",
        # sharing the full-time "F" prefix, which made it impossible to tell the
        # two faculty types apart at a glance from the ID alone.
        make_user("P1001", "Carlo", "Dizon", "faculty", "part_time", "Computer Studies")
        make_user("S1001", "Jomar", "Torres", "student")

        self.stdout.write(self.style.SUCCESS(
            "Done. Sample logins (username = UPHM-<school_id>, password = <school_id>):\n"
            "  UPHM-R1001 / R1001  (Registrar)\n"
            "  UPHM-D1001 / D1001  (Dean, Computer Studies)\n"
            "  UPHM-F1001 / F1001  (Full-time Faculty)\n"
            "  UPHM-P1001 / P1001  (Part-time Faculty)\n"
            "  UPHM-S1001 / S1001  (Student)\n"
            "All will be prompted to change password on first login.\n"
            "Run 'python manage.py seed_bscs_curriculum' separately for real curriculum data."
        ))
