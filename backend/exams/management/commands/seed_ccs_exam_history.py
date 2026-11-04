"""
Seeds REAL exam schedule data transcribed from actual UPHSL CCS exam schedule
PDFs (Prelim Sept 2025, Midterm Oct 2025, Final Dec 2025, Prelim Feb 2026,
Prelim Lab Feb 2026) -- not synthetic demo data.

Only imports rows whose subject_code matches a Subject already created by
seed_bscs_curriculum (3rd Year CS-prefixed subjects overlap cleanly with
these real exam records). Rows for other colleges/programs (DCS/GIT/IT/N/
RAD/HRDM/etc. codes) are intentionally skipped -- they belong to programs
not yet represented in this system.

Creates a FacultyProfile (+ User) for each real proctor name found, if one
doesn't already exist, using a synthetic school_id derived from their name
(these are real staff names but not real school IDs, since exam PDFs don't
include those -- Registrar/HR would need to supply real IDs later to merge
these into proper accounts).

Run with: python manage.py seed_ccs_exam_history
"""
import re
from datetime import datetime, time as dtime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from curriculum.models import Subject
from engine.models import Section, TimeSlot
from faculty.models import FacultyProfile
from exams.models import ExamSchedule

User = get_user_model()

# (date "YYYY-MM-DD", start "HH:MM", end "HH:MM", subject_code, proctor_full_name, exam_period, school_year, semester)
EXAM_ROWS = [
    # --- Prelim, September 8-13 2025 (1st Sem AY 2025-2026) ---
    ("2025-09-10", "15:00", "16:00", "CS3117", "Anna Liza O. Villanueva", "prelim", "2025-2026", "1st Sem"),
    ("2025-09-10", "16:00", "17:00", "CS3119", "Anna Liza O. Villanueva", "prelim", "2025-2026", "1st Sem"),
    ("2025-09-12", "16:00", "17:00", "CS3120", "J. Olino", "prelim", "2025-2026", "1st Sem"),
    ("2025-09-12", "17:00", "18:00", "CS3121", "J. Olino", "prelim", "2025-2026", "1st Sem"),
    ("2025-09-08", "14:00", "15:00", "CS3122", "C. L. Verano", "prelim", "2025-2026", "1st Sem"),

    # --- Midterm, October 27-29 2025 (1st Sem AY 2025-2026) ---
    ("2025-10-27", "15:00", "16:00", "CS3122", "C. L. Verano", "midterm", "2025-2026", "1st Sem"),
    ("2025-10-29", "07:00", "08:00", "CS3121", "J. Olino", "midterm", "2025-2026", "1st Sem"),
    ("2025-10-29", "08:00", "09:00", "CS3120", "J. Olino", "midterm", "2025-2026", "1st Sem"),
    ("2025-10-28", "11:00", "12:00", "CS3119", "J. Olino", "midterm", "2025-2026", "1st Sem"),
    ("2025-10-29", "16:00", "17:00", "CS3117", "A. O. Villanueva", "midterm", "2025-2026", "1st Sem"),

    # --- Final, December 3-5 2025 (1st Sem AY 2025-2026) ---
    ("2025-12-03", "15:00", "16:00", "CS3122", "C. L. Verano", "final", "2025-2026", "1st Sem"),
    ("2025-12-04", "11:00", "12:00", "CS3119", "J. P. Olino", "final", "2025-2026", "1st Sem"),
    ("2025-12-05", "07:00", "08:00", "CS3121", "J. P. Olino", "final", "2025-2026", "1st Sem"),
    ("2025-12-05", "08:00", "09:00", "CS3120", "J. P. Olino", "final", "2025-2026", "1st Sem"),

    # --- Prelim, February 16-20 2026 (2nd Sem AY 2025-2026) ---
    ("2026-02-16", "14:00", "15:00", "CS3225", "Olino", "prelim", "2025-2026", "2nd Sem"),
    ("2026-02-18", "14:00", "15:00", "CS3226", "Verano", "prelim", "2025-2026", "2nd Sem"),
    ("2026-02-19", "16:00", "17:00", "CS3227", "De Luna", "prelim", "2025-2026", "2nd Sem"),
    ("2026-02-20", "15:30", "16:30", "CS3223", "Tungol", "prelim", "2025-2026", "2nd Sem"),

    # --- Prelim Lab, Feb 23-26 2026 (2nd Sem AY 2025-2026) ---
    ("2026-02-23", "13:00", "16:00", "CS3225L", "J. Olino", "prelim", "2025-2026", "2nd Sem"),
    ("2026-02-24", "10:00", "13:00", "CS3224L", "R. Tungol", "prelim", "2025-2026", "2nd Sem"),
    ("2026-02-26", "15:30", "18:30", "CS3227L", "J. De Luna", "prelim", "2025-2026", "2nd Sem"),
]

ROOM_BY_CODE = {
    "CS3117": "309D", "CS3119": "309D", "CS3120": "309D", "CS3121": "307D", "CS3122": "309D",
    "CS3223": "307D", "CS3224L": "304D", "CS3225": "309D", "CS3225L": "309D",
    "CS3226": "308D", "CS3227": "309D", "CS3227L": "309D",
}


class Command(BaseCommand):
    help = "Seed real historical exam schedule data (CCS, 2025-2026) transcribed from actual UPHSL exam PDFs."

    def get_or_create_proctor(self, full_name):
        # Synthetic school_id since exam PDFs don't include real school IDs --
        # Registrar/HR would need to supply those later to merge into proper accounts.
        slug = re.sub(r"[^A-Za-z]", "", full_name.split()[-1]).upper()[:10]
        school_id = f"PROC-{slug}"
        user, created = User.objects.get_or_create(
            school_id=school_id,
            defaults={
                "first_name": full_name.split()[0], "last_name": full_name.split()[-1],
                "role": "faculty", "faculty_type": "full_time", "department": "Computer Studies",
                "must_change_password": True,
            },
        )
        if created:
            user.set_password(school_id)
            user.save()
        profile, _ = FacultyProfile.objects.get_or_create(user=user)
        return profile

    def get_or_create_room(self, name):
        from rooms.models import Room
        room, _ = Room.objects.get_or_create(
            name=name, defaults={"capacity": 40, "room_type": "lecture", "department": "Computer Studies"}
        )
        return room

    def handle(self, *args, **options):
        from rooms.models import Room  # local import to avoid circulars at module load

        created_count, skipped_count = 0, 0

        for date_str, start_str, end_str, code, proctor_name, period, school_year, semester in EXAM_ROWS:
            subject = Subject.objects.filter(code=code).first()
            if not subject:
                self.stdout.write(self.style.WARNING(f"Skipping {code} -- no matching Subject in curriculum."))
                skipped_count += 1
                continue

            section = Section.objects.filter(
                program=subject.program, year_level=subject.year_level, semester=subject.semester
            ).first()
            if not section:
                self.stdout.write(self.style.WARNING(f"Skipping {code} -- no Section for {subject.year_level}/{subject.semester}."))
                skipped_count += 1
                continue

            exam_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            day_abbrev = exam_date.strftime("%a")[:3]  # Mon, Tue, Wed...

            timeslot, _ = TimeSlot.objects.get_or_create(
                day=day_abbrev, start_time=start_time, end_time=end_time
            )

            proctor = self.get_or_create_proctor(proctor_name)
            room = self.get_or_create_room(ROOM_BY_CODE.get(code, "309D"))

            exam, was_created = ExamSchedule.objects.get_or_create(
                subject=subject, section=section, timeslot=timeslot, exam_date=exam_date,
                defaults={
                    "proctor": proctor, "room": room, "exam_period": period,
                    "school_year": school_year,
                },
            )
            if was_created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created_count} exam records created, {skipped_count} rows skipped "
            f"(no matching Subject/Section yet -- likely a different program)."
        ))
