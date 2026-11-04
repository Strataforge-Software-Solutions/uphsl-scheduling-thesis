"""
Seeds real exam schedule data from the "1st Sem Prelim Exam 2026-2027" docx --
but ONLY the rows whose section code starts with "CS" (Computer Studies
students taking centrally-administered GE courses). The docx also contains
Nursing (N), Radiologic Tech (RAD), IT, HRDM, and other colleges' sections --
those are intentionally skipped since this system currently only models the
BS Computer Science program. Extend this command (or write a sibling one)
once other colleges/programs are added to the system.

Data quality note: the source docx's heading for the second row below reads
"AUGUST 25, 2026 TUESDAY, 11:00PM-12:00NN" -- almost certainly a typo for
11:00AM given the surrounding sequence (10-11AM, [this], 1-2PM). Treated as
11:00AM-12:00NN here; flagged in case the original document is corrected later.

Run with: python manage.py seed_cas_docx_exam_history
"""
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from curriculum.models import Subject
from engine.models import Section, TimeSlot
from faculty.models import FacultyProfile
from rooms.models import Room
from exams.models import ExamSchedule

User = get_user_model()

# (date, start, end, subject_title_to_match, proctor_full_name, room)
ROWS = [
    ("2026-08-25", "11:00", "12:00", "Art Appreciation", "Mary Ann Abundo", "301M"),
    ("2026-08-25", "14:00", "15:00", "Purposive Communication", "Christine Andrea De Lara", "206D"),
    ("2026-08-25", "15:00", "16:00", "Mathematics in the Modern World", "Edgar Paul Arrogante", "206D"),
]


class Command(BaseCommand):
    help = "Seed real CS-prefixed (Computer Studies) exam rows from the CAS docx exam schedule (AY 2026-2027)."

    def get_or_create_proctor(self, full_name):
        import re
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

    def handle(self, *args, **options):
        created_count, skipped = 0, 0

        for date_str, start_str, end_str, subject_title, proctor_name, room_name in ROWS:
            subject = Subject.objects.filter(title__iexact=subject_title).first()
            if not subject:
                self.stdout.write(self.style.WARNING(f"Skipping '{subject_title}' -- no matching Subject found."))
                skipped += 1
                continue

            section = Section.objects.filter(
                program=subject.program, year_level=subject.year_level, semester=subject.semester
            ).first()
            if not section:
                self.stdout.write(self.style.WARNING(f"Skipping '{subject_title}' -- no matching Section."))
                skipped += 1
                continue

            exam_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            day_abbrev = exam_date.strftime("%a")[:3]

            timeslot, _ = TimeSlot.objects.get_or_create(day=day_abbrev, start_time=start_time, end_time=end_time)
            proctor = self.get_or_create_proctor(proctor_name)
            room, _ = Room.objects.get_or_create(
                name=room_name, defaults={"capacity": 40, "room_type": "lecture", "department": "Computer Studies"}
            )

            exam, was_created = ExamSchedule.objects.get_or_create(
                subject=subject, section=section, timeslot=timeslot, exam_date=exam_date,
                defaults={"proctor": proctor, "room": room, "exam_period": "prelim", "school_year": "2026-2027"},
            )
            if was_created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created_count} exam records created, {skipped} skipped.\n"
            f"Only CS-prefixed (Computer Studies) rows from this docx were imported -- "
            f"other colleges (Nursing, Radtech, IT, HRDM, etc.) were intentionally left out."
        ))
