"""
READ-ONLY comparison of the old greedy SHS / JHS generator and the new backtracking search, on the SAME data with the SAME seed.

    python manage.py compare_basic_ed_solvers                 (every level, grade and term / semester of the active school year)
    python manage.py compare_basic_ed_solvers --level SHS

For each grade and term it prints: periods placed / total, unplaced periods, run time, and hard-rule violations found by the independent
checker (basic_ed/checker.py), for both generators. Nothing is saved: no timetable, no run, no log.
"""
import time

from django.core.management.base import BaseCommand
from django.db import transaction

from basic_ed import models as m
from basic_ed.checker import check
from basic_ed.engine import Problem, solve, solve_greedy
from basic_ed.services import core_anchor
from basic_ed.structure import structure


def total_periods(P):
    return sum(sub.sessions_per_week for sec in P.sections for sub in P.subjects_for(sec))


def measure(fn, P, seed):
    t0 = time.perf_counter()
    assignments, unresolved = fn(P, seed=seed)
    sec = time.perf_counter() - t0
    return {"placed": len(assignments), "unplaced": sum(u["needed"] for u in unresolved), "seconds": sec,
            "violations": check(P, assignments)}


class Command(BaseCommand):
    help = "Compare the old greedy and the new backtracking SHS/JHS generators (read only)."

    def add_arguments(self, parser):
        parser.add_argument("--level", choices=["SHS", "JHS"])

    def handle(self, *args, **o):
        ay = m.AcademicYear.objects.filter(is_active=True).first() or m.AcademicYear.objects.order_by("-label").first()
        if ay is None:
            self.stdout.write("No school year found.")
            return
        rows = []
        with transaction.atomic():                      # read only; rolled back at the end in any case
            for level in ([o["level"]] if o["level"] else ["SHS", "JHS"]):
                if not m.SchoolLevelConfig.objects.filter(level=level).exists():
                    continue
                for w in m.GradeWindow.objects.filter(level=level).order_by("grade_level"):
                    g = w.grade_level
                    if not m.Section.objects.filter(level=level, academic_year=ay, grade_level=g, is_active=True).exists():
                        continue
                    for gp in range(1, structure(level, g)[1] + 1):
                        P = Problem(level, ay, gp, g)
                        P.anchor = core_anchor(level, ay, gp, g)
                        total = total_periods(P)
                        if not total:
                            continue
                        seed = g * 7 + gp
                        old = measure(solve_greedy, P, seed)
                        new = measure(solve, P, seed)
                        rows.append((level, g, gp, total, old, new))
            transaction.set_rollback(True)
        self.stdout.write(f"School year {ay.label}. Same data and seed for both generators. Times are wall-clock on this computer.\n")
        head = (f"{'Level':5} {'Grade':>5} {'Term':>4} {'Total':>6} | {'Greedy placed':>13} {'unplaced':>8} {'time s':>7} {'viol.':>5} | "
                f"{'Search placed':>13} {'unplaced':>8} {'time s':>7} {'viol.':>5}")
        self.stdout.write(head)
        self.stdout.write("-" * len(head))
        sums = {"total": 0, "o": [0, 0, 0.0, 0], "n": [0, 0, 0.0, 0]}
        for level, g, gp, total, old, new in rows:
            self.stdout.write(f"{level:5} {g:>5} {gp:>4} {total:>6} | {old['placed']:>13} {old['unplaced']:>8} {old['seconds']:>7.2f} "
                              f"{len(old['violations']):>5} | {new['placed']:>13} {new['unplaced']:>8} {new['seconds']:>7.2f} {len(new['violations']):>5}")
            sums["total"] += total
            for k, r in (("o", old), ("n", new)):
                sums[k][0] += r["placed"]; sums[k][1] += r["unplaced"]; sums[k][2] += r["seconds"]; sums[k][3] += len(r["violations"])
        o, n = sums["o"], sums["n"]
        self.stdout.write("-" * len(head))
        self.stdout.write(f"{'All':5} {'':>5} {'':>4} {sums['total']:>6} | {o[0]:>13} {o[1]:>8} {o[2]:>7.2f} {o[3]:>5} | "
                          f"{n[0]:>13} {n[1]:>8} {n[2]:>7.2f} {n[3]:>5}")
        for level, g, gp, total, old, new in rows:
            for label, r in (("greedy", old), ("search", new)):
                for v in r["violations"][:5]:
                    self.stdout.write(f"  {level} G{g} T{gp} {label}: {v}")
