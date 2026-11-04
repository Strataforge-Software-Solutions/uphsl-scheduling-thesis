"""
Deletes faculty/registrar accounts EXCEPT a whitelist of school IDs, so test
accounts can be cleared out before a real staff list is bulk-imported.

SAFE BY DEFAULT: this only PRINTS what it would delete unless you pass --yes.

    python manage.py cleanup_non_essential_accounts
    python manage.py cleanup_non_essential_accounts --yes

Student accounts are never touched. The default keep-list is D1001, R1001,
F1001, P1001 -- override with --keep if you need different IDs:

    python manage.py cleanup_non_essential_accounts --keep D1001 R1001 F1001 P1001 --yes

IMPORTANT: deleting a faculty account cascades (FacultyProfile is
OneToOne->User, on_delete=CASCADE) to that teacher's current Schedule rows,
Availability, Absence, WorkloadRecord, and CoverageSuggestion history. If any
of the accounts being deleted have LIVE, in-use class schedules, those
schedules are deleted too -- this command warns you with counts before
asking you to re-run with --yes.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


DEFAULT_KEEP = ["D1001", "R1001", "F1001", "P1001"]


class Command(BaseCommand):
    help = "Delete all faculty/registrar accounts except a whitelist of school IDs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep", nargs="+", default=DEFAULT_KEEP,
            help=f"School IDs to NEVER delete (default: {' '.join(DEFAULT_KEEP)}).",
        )
        parser.add_argument("--yes", action="store_true", help="Actually delete. Without this flag, only reports what would be deleted.")

    def handle(self, *args, **options):
        from accounts.models import User
        from engine.models import Schedule

        keep = set(options["keep"])
        qs = User.objects.filter(role__in=["faculty", "registrar"]).exclude(school_id__in=keep)

        if not qs.exists():
            self.stdout.write(self.style.SUCCESS("Nothing to delete -- no faculty/registrar accounts outside the keep-list."))
            return

        self.stdout.write(f"Keep-list: {sorted(keep)}")
        self.stdout.write(f"Accounts that {'WILL BE' if options['yes'] else 'would be'} deleted ({qs.count()}):")
        schedule_count = 0
        for u in qs.select_related("faculty_profile").order_by("school_id"):
            has_profile = hasattr(u, "faculty_profile")
            sched_n = Schedule.objects.filter(teacher__user=u).count() if has_profile else 0
            schedule_count += sched_n
            flag = f" -- ⚠ {sched_n} live Schedule row(s) will be deleted too" if sched_n else ""
            self.stdout.write(f"  {u.school_id}  {u.username}  ({u.role}/{u.faculty_type or '-'})  {u.get_full_name()}{flag}")

        if schedule_count:
            self.stdout.write(self.style.WARNING(
                f"\n⚠ {schedule_count} total Schedule row(s) across these accounts will be deleted (cascade)."
            ))

        if not options["yes"]:
            self.stdout.write(self.style.WARNING("\nDry run only -- nothing was deleted. Re-run with --yes to actually delete."))
            return

        with transaction.atomic():
            deleted_count, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"\nDeleted {deleted_count} total row(s) (accounts + cascaded records)."))
