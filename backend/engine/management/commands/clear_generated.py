"""
Erase generated class schedules and/or exam schedules so they can be generated again.

Preview first (nothing is deleted):
    python manage.py clear_generated --year "3rd Year" --semester "1st Sem"
    python manage.py clear_generated --exams

Then add --apply to actually delete:
    python manage.py clear_generated --year "3rd Year" --semester "1st Sem" --apply
    python manage.py clear_generated --year "3rd Year" --semester "1st Sem" --exams --apply

Options
    --year / --semester   limit class schedules to one year level and/or semester
                          (leave both out to clear ALL class schedules)
    --program "BS Computer Science"   limit to one program
    --exams               also delete exam schedules (for that semester if --semester
                          is given, otherwise all exam schedules)
    --include-approved    also delete Approved/Published rows. Without it only Draft rows
                          are removed, so nothing already approved is lost by accident.
Class schedules are only deleted when --year, --semester or --program is given, or
no --exams flag is used; running with --exams alone clears only exams.
"""
import time

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from engine.models import Schedule
from exams.models import ExamSchedule


class Command(BaseCommand):
    help = "Delete generated class schedules (Draft by default) and/or exam schedules."

    def add_arguments(self, parser):
        parser.add_argument("--year")
        parser.add_argument("--semester")
        parser.add_argument("--program")
        parser.add_argument("--exams", action="store_true")
        parser.add_argument("--include-approved", action="store_true")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **o):
        # Say where the time goes: a slow/paused remote database (Supabase) is the usual reason
        # this seems to hang -- the first line below is the database connection itself.
        t0 = time.time()
        self.stdout.write("Connecting to the database ...")
        connection.ensure_connection()
        self.stdout.write(f"  connected in {time.time() - t0:.1f}s")
        with transaction.atomic():
            self._run(o)
        self.stdout.write(f"Finished in {time.time() - t0:.1f}s.")

    def _run(self, o):
        scoped = bool(o["year"] or o["semester"] or o["program"])
        do_classes = scoped or not o["exams"]

        plans = []
        if do_classes:
            qs = Schedule.objects.all()
            if o["year"]:
                qs = qs.filter(section__year_level=o["year"])
            if o["semester"]:
                qs = qs.filter(section__semester=o["semester"])
            if o["program"]:
                qs = qs.filter(section__program__name=o["program"])
            kept = 0
            if not o["include_approved"]:
                kept = qs.exclude(status="draft").count()
                qs = qs.filter(status="draft")
            plans.append(("class schedule rows", qs, kept))
        if o["exams"]:
            eq = ExamSchedule.objects.all()
            if o["semester"]:
                eq = eq.filter(section__semester=o["semester"])
            if o["year"]:
                eq = eq.filter(section__year_level=o["year"])
            if o["program"]:
                eq = eq.filter(section__program__name=o["program"])
            plans.append(("exam schedule rows", eq, 0))

        for label, qs, kept in plans:
            ids = list(qs.values_list("pk", flat=True))      # one simple query, then delete by id
            n = len(ids)
            msg = f"{n} {label} {'deleted' if o['apply'] else 'would be deleted'}"
            if kept:
                msg += f"  ({kept} approved/published row(s) kept -- add --include-approved to remove them too)"
            self.stdout.write(msg)
            if o["apply"] and ids:
                qs.model.objects.filter(pk__in=ids).delete()
                from engine.housekeeping import cleanup_after_delete
                cleanup_after_delete()
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to delete."))
