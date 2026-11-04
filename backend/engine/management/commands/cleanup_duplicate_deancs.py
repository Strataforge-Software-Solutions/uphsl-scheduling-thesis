"""
One-time cleanup: removes the "DeanCS" account created by an earlier version
of seed_college_deans, which duplicated UPHM-D1001 (the real Computer Studies
Dean). Safe to run even if DeanCS was never created.

Run with: python manage.py cleanup_duplicate_deancs
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Remove the duplicate 'DeanCS' account (UPHM-D1001 is the real Computer Studies Dean)."

    def handle(self, *args, **options):
        deleted, _ = User.objects.filter(username="DeanCS").delete()
        if deleted:
            self.stdout.write(self.style.SUCCESS("Removed the duplicate DeanCS account."))
        else:
            self.stdout.write("No DeanCS account found -- nothing to clean up.")
