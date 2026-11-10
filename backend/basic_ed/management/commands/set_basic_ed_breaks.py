"""
Gives every JHS / SHS grade level a RECESS and a LUNCH. No class is ever placed in them, and they appear in the timetable, the PDF and
the validation.

    python manage.py set_basic_ed_breaks --dry-run
    python manage.py set_basic_ed_breaks               # only grade levels that have no breaks yet
    python manage.py set_basic_ed_breaks --reset       # put the defaults back everywhere

Defaults (break start times can be changed in Settings > Daily time windows; durations are fixed):
  JHS Grades 7-10  45-min periods   recess 10:15-10:35   lunch 12:00-12:45   day 8:00 AM-3:00 PM (7 available periods)
  SHS Grade 11     50-min periods   ONE 15-minute break 9:30-9:45   day 7:00 AM-12:30 PM   6 periods a day
  SHS Grade 12     50-min periods   ONE 15-minute break 3:00-3:15 PM  day 12:30-6:30 PM       6 periods a day
SHS has no separate recess / lunch. JHS keeps both (its hours are not changed by this command except for the original JHS default).
Existing timetables are not touched; regenerate them (or press Revalidate) to see the effect.
"""
from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed.models import GradeWindow, ScheduleRun, SchoolLevelConfig

DEFAULTS = {
    ("JHS", None): dict(recess=(time(10, 15), time(10, 35)), lunch=(time(12, 0), time(12, 45))),
    # SHS: ONE 15-minute break, school hours unchanged: Grade 11 7:00-12:30, Grade 12 12:30-6:30 PM
    ("SHS", 11): dict(single=(time(9, 30), time(9, 45))),
    ("SHS", 12): dict(single=(time(15, 0), time(15, 15))),
}


def defaults_for(level, grade):
    return DEFAULTS.get((level, grade)) or DEFAULTS.get((level, None))


def apply_defaults(w, reset=False):
    """Sets the breaks on GradeWindow w (not saved). Returns a text describing the change, or '' when nothing changes."""
    d = defaults_for(w.level, w.grade_level)
    if d and d.get("single"):
        if not reset and w.break_start:
            return ""
        w.break_start, w.break_end = d["single"]
        w.recess_start = w.recess_end = w.lunch_start = w.lunch_end = None
        return f"one 15-minute break {d['single'][0]:%H:%M}-{d['single'][1]:%H:%M} (no recess / lunch)"
    if not d or (not reset and (w.recess_start or w.lunch_start)):
        return ""
    w.recess_start, w.recess_end = d["recess"]
    w.lunch_start, w.lunch_end = d["lunch"]
    note = f"recess {d['recess'][0]:%H:%M}-{d['recess'][1]:%H:%M}, lunch {d['lunch'][0]:%H:%M}-{d['lunch'][1]:%H:%M}"
    if d.get("start") and w.start_time == d["old_start"]:
        w.start_time = d["start"]
        note += f", day now starts {d['start']:%H:%M}"
    return note


class Command(BaseCommand):
    help = "Set recess and lunch on every JHS / SHS grade level."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--reset", action="store_true")

    @transaction.atomic
    def handle(self, *a, **o):
        n = 0
        for w in GradeWindow.objects.all().order_by("level", "grade_level"):
            note = apply_defaults(w, o["reset"])
            if note:
                n += 1
                self.stdout.write(f"{w.level} Grade {w.grade_level}: {note}")
                if not o["dry_run"]:
                    w.save()
        if not o["dry_run"]:
            SchoolLevelConfig.objects.update(break_minutes=0)           # the old "break after every 2 periods" is replaced by recess + lunch
        self.stdout.write(self.style.SUCCESS(f"{'Would update' if o['dry_run'] else 'Updated'} {n} grade level(s)."))
        old = ScheduleRun.objects.exclude(status="superseded").count()
        if n and old:
            self.stdout.write(self.style.WARNING(
                f"{old} existing timetable(s) were built WITHOUT these breaks. Regenerate them: python manage.py clear_basic_ed_schedules "
                f"--level JHS --apply (and --level SHS), then Generate again for every grade (all grades must use the same new periods)."))
        if o["dry_run"]:
            transaction.set_rollback(True)
