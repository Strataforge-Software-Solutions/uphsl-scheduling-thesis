"""
One-time cleanup: removes the old demo Subjects (CS101, CS102, CS103, GE101)
and the old demo Section ("1A") that were created by an earlier version of
seed_demo_data before it collided with seed_bscs_curriculum's real data under
the same Program. Safe to run once; does nothing if already cleaned up.

Run with: python manage.py cleanup_demo_overlap
"""
from django.core.management.base import BaseCommand
from curriculum.models import Subject
from engine.models import Section


class Command(BaseCommand):
    help = "Remove stale demo Subjects/Section that collide with the real BSCS curriculum."

    def handle(self, *args, **options):
        stale_codes = ["CS101", "CS102", "CS103", "GE101"]
        deleted_subjects, _ = Subject.objects.filter(code__in=stale_codes).delete()

        deleted_sections, _ = Section.objects.filter(
            name="1A", year_level="1st Year", semester="1st Sem"
        ).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Removed {deleted_subjects} stale subject row(s) (codes: {stale_codes}) "
            f"and {deleted_sections} stale section row(s) (name '1A').\n"
            "Re-check Curriculum Mgmt and Generate Schedule -- should now only show the real curriculum."
        ))
