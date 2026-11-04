"""
Apply the room rules from the GTI class program workbook in ONE safe, repeatable pass.

  python manage.py setup_rooms                          # preview only
  python manage.py setup_rooms --apply                  # do it

  * Finds each room by building + number (so "307D", "D-307" and "Comp Lab C" are the SAME room), creates any that
    are missing, and gives them a clear label: Comp Lab C (307D), Comp Lab D (309D), ...
  * RESERVED rooms (exclusive to one department, from the workbook):
      Computer Studies: Comp Lab C 307D, Comp Lab D 309D, (304D NSTP office and 305D IT office are offices: never scheduled)
      IHM: HJ, Kitchen 1, Kitchen 2          Radiologic Technology: 204D, X-ray Lab
      Nursing: Nursing Arts, Physics/Micro/Anatomy labs, 601N, 602N       Allied Health: 302N, 401N, 402N
      Comp Lab B (303D): Senior High / Junior High
  * HOME rooms for every department's major subjects (a preference: tried first, not exclusive) -> Rooms tab
  * Each department's main building (DepartmentBuilding) as seen in the workbook
  * "Comp Lab 1" is retired (its bookings move to Comp Lab C / D first)
Departments are matched to the names on your programs, so run `prefix_departments` first if you use the
"College of ..." names. Nothing else is touched; running it twice changes nothing more.
"""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from rooms import gti_data as G
from rooms.rules import SHS_JHS, norm, room_key


def _find_dept(names, *needles):
    for n in names:
        if all(x in norm(n) for x in needles):
            return n
    return None


class Command(BaseCommand):
    help = "Apply the GTI class-program room assignments (reserved + home rooms, labels, missing rooms)."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")
        p.add_argument("--ihm-department", default=None)
        p.add_argument("--cs-department", default=None)
        p.add_argument("--cs-lecture-room", default="",
                       help="Number of Computer Studies' lecture room on the Alta 3rd floor (ignored: 305D is the IT office).")

    # ------------------------------------------------------------------ helpers
    def _style(self, Room):
        """How this database writes numbered room names: '307D' (number first) or 'D-307'."""
        a = b = 0
        for n in Room.objects.values_list("name", flat=True):
            a += bool(re.fullmatch(r"\d{3}[MDN]", n or ""))
            b += bool(re.fullmatch(r"[MDNA]-\d{3}", n or ""))
        return "number_first" if a > b else "building_first"

    def _find(self, rooms, aliases, b, n):
        keys = {room_key(x) for x in aliases}
        if n:
            keys |= {room_key(f"{n}{b}"), room_key(f"{b}{n}")}
        hits = []
        for r in rooms:
            if (n and r.building == b and str(r.room_number or "").strip() == n) or room_key(r.name) in keys or \
                    (r.label and room_key(r.label) in keys):
                hits.append(r)
        # the exact building + number match first
        hits.sort(key=lambda r: not (n and r.building == b and str(r.room_number or "").strip() == n))
        return hits

    def _merge(self, src, dst, out, apply_):
        """Move every booking of duplicate room `src` onto `dst`, then delete `src` (only if everything moved)."""
        from engine.models import Schedule, Constraint
        from exams.models import ExamSchedule
        from rooms.models import SubjectRoomAssignment, DepartmentRoom
        moved = stuck = 0
        for model in (Schedule, ExamSchedule):
            for row in model.objects.filter(room=src).select_related("timeslot"):
                if model.objects.filter(room=dst, timeslot=row.timeslot).exclude(pk=row.pk).exists():
                    stuck += 1
                    continue
                moved += 1
                if apply_:
                    row.room = dst
                    row.save(update_fields=["room"])
        out(f"      merge duplicate {src.name!r} (id {src.id}) into {dst.name!r}: {moved} booking(s) moved, {stuck} could not move")
        if apply_ and not stuck:
            Constraint.objects.filter(room=src).update(room=dst)
            SubjectRoomAssignment.objects.filter(preferred_room=src).update(preferred_room=dst)
            for a in SubjectRoomAssignment.objects.filter(alternative_rooms=src):
                a.alternative_rooms.remove(src)
                a.alternative_rooms.add(dst)
            DepartmentRoom.objects.filter(room=src).delete()
            src.delete()
        elif apply_:
            out(self.style.WARNING(f"      {src.name!r} kept: re-generate, then run again."))

    # ------------------------------------------------------------------ main
    def handle(self, *a, **o):
        from curriculum.models import Program
        from engine.models import Schedule, Constraint
        from exams.models import ExamSchedule
        from rooms.models import Room, DepartmentBuilding, DepartmentRoom
        out, apply_ = self.stdout.write, o["apply"]
        names = sorted({d for d in Program.objects.values_list("department", flat=True) if d})
        dept = {}
        for key, words in G.DEPT_KEYWORDS.items():
            dept[key] = _find_dept(names, *words)
        if o["ihm_department"]:
            dept["ihm"] = o["ihm_department"]
        if o["cs_department"]:
            dept["cs"] = o["cs_department"]
        out("Departments found: " + ", ".join(f"{k}={v!r}" for k, v in dept.items()))
        for k, v in dept.items():
            if not v:
                out(self.style.WARNING(f"  no department matched for '{k}': its rooms will be created but not reserved / assigned."))
        reserved_by = {}
        for key, rks in G.RESERVED.items():
            for rk in rks:
                reserved_by[rk] = dept.get(key)
        reserved_by["D303"] = SHS_JHS
        plan, made = [], {}
        with transaction.atomic():
            style = self._style(Room)
            rooms = list(Room.objects.all())
            for rk, (aliases, b, n, label, rtype, cap) in G.ROOMS.items():
                hits = self._find(rooms, list(aliases) + [rk], b, n)
                owner = reserved_by.get(rk)
                if not hits:
                    if n:
                        name = f"{n}{b}" if style == "number_first" else f"{b}-{n}"
                    else:
                        name = rk
                    plan.append(f"create  {name:<14} {label or '-':<20} {rtype:<8}" + (f" reserved: {owner!r}" if owner else ""))
                    if apply_:
                        r = Room.objects.create(name=name, building=b, room_number=n, label=label, capacity=cap,
                                                capacity_is_estimate=True, room_type=rtype, department=owner or None,
                                                equipment="Computers" if rtype == "lab" and b == "D" else "")
                        rooms.append(r)
                        made[rk] = r
                    continue
                r = hits[0]
                changes = []
                if label and (not (r.label or "").strip() or rk in ("D307", "D309", "D303", "D304", "D305") or r.label.lower().startswith("comp")):
                    if r.label != label:
                        changes.append(f"label {r.label!r} -> {label!r}")
                        r.label = label
                if b and r.building != b:
                    changes.append(f"building {r.building!r} -> {b!r}")
                    r.building = b
                if n and str(r.room_number or "").strip() != n:
                    changes.append(f"number {r.room_number!r} -> {n!r}")
                    r.room_number = n
                if rtype == "offsite":
                    # an office (NSTP office 304D, IT office 305D): never a class room, never reserved
                    if r.room_type != "offsite":
                        changes.append(f"type {r.room_type} -> office (not schedulable)")
                        r.room_type = "offsite"
                    if room_key(r.name) in {room_key(a) for a in aliases} and room_key(r.name) != rk:
                        nm = f"{n}{b}" if style == "number_first" else f"{b}-{n}"
                        changes.append(f"name {r.name!r} -> {nm!r}")
                        r.name = nm
                    if r.department:
                        changes.append(f"reservation {r.department!r} removed")
                        r.department = None
                elif rtype == "lab" and r.room_type != "lab":
                    changes.append(f"type {r.room_type} -> lab")
                    r.room_type = "lab"
                if owner and (r.department or "") != owner:
                    if r.department and r.department != owner and norm(r.department) != norm(owner):
                        out(self.style.WARNING(f"  {r.name}: already reserved for {r.department!r}; NOT changed to {owner!r}"))
                    else:
                        changes.append(f"reserved for {owner!r}")
                        r.department = owner
                plan.append(f"{'update ' if changes else 'ok     '} {r.name:<14} {r.label or '-':<20} {r.room_type:<8}" + ("  " + "; ".join(changes) if changes else ""))
                if apply_ and changes:
                    r.save()
                made[rk] = r
                for dup in hits[1:]:
                    if dup.id != r.id:
                        self._merge(dup, r, out, apply_)
            for line in plan:
                out("  " + line)
            plan = []

            if apply_:
                from engine.models import Schedule
                n_off = Schedule.objects.filter(room__room_type="offsite", room__building="D", room__room_number__in=["304", "305"]).count()
                if n_off:
                    out(self.style.WARNING(f"  {n_off} existing class(es) are still booked in the 304D / 305D offices: "
                                           "regenerate or move them (Schedules > edit) to a real classroom."))

            # Home rooms (preference) and each department's main building
            for key, rks in G.HOME.items():
                d = dept.get(key)
                if not d:
                    continue
                got = [made[rk] for rk in rks if rk in made]
                have = set(DepartmentRoom.objects.filter(department=d).values_list("room_id", flat=True))
                new = [r for r in got if r.id not in have]
                out(f"  home rooms for {d!r}: " + (", ".join(f"{r.label or r.name}" for r in got) or "(none found)")
                    + (f"   [{len(new)} new]" if new else ""))
                if apply_:
                    for r in new:
                        DepartmentRoom.objects.get_or_create(department=d, room=r)
                    DepartmentRoom.objects.filter(department=d, source="GTI class program").exclude(room_id__in=[r.id for r in got]).delete()
                bld = G.DEPT_BUILDING.get(key)
                cur = DepartmentBuilding.objects.filter(department=d).first()
                if bld and (not cur or cur.building != bld):
                    out(f"  main building for {d!r}: {cur.building if cur else '-'} -> {bld}")
                    if apply_:
                        DepartmentBuilding.objects.update_or_create(department=d, defaults={"building": bld})
            if apply_:
                from rooms.rules import clear_home_cache
                clear_home_cache()
            # Comp Lab 1
            old = Room.objects.filter(name__iexact="Comp Lab 1").first()
            if old:
                targets = [made.get("D307"), made.get("D309")]
                targets = [t for t in targets if t]
                moved = skipped = 0
                if not targets:                      # preview before the new labs exist: they start empty
                    moved = sum(model.objects.filter(room=old).count() for model in (Schedule, ExamSchedule))
                    targets = [None]
                    models_iter = ()
                else:
                    models_iter = (Schedule, ExamSchedule)
                for model in models_iter:
                    for row in model.objects.filter(room=old).select_related("timeslot"):
                        ok = None
                        for t in targets:
                            if not model.objects.filter(room=t, timeslot=row.timeslot).exclude(pk=row.pk).exists():
                                ok = t; break
                        if ok:
                            moved += 1
                            if apply_:
                                row.room = ok; row.save(update_fields=["room"])
                        else:
                            skipped += 1
                cons = Constraint.objects.filter(room=old).count()
                plan.append(f"Comp Lab 1: move {moved} booking(s) to Comp Lab C/D, {skipped} could not move, {cons} constraint(s) dropped; then delete it")
                if apply_:
                    if skipped or targets == [None]:
                        out(self.style.WARNING("Comp Lab 1 kept: some bookings could not be moved. Re-generate, then run again."))
                    else:
                        Constraint.objects.filter(room=old).delete(); old.delete()
            else:
                plan.append("Comp Lab 1 not present")
            # basic ed
            try:
                from basic_ed.models import Room as BRoom
                for lvl in ("SHS", "JHS"):
                    exists = BRoom.objects.filter(level=lvl, room_number="Comp Lab B").exists()
                    plan.append(f"{'ok' if exists else 'create'} basic-ed {lvl} Comp Lab B (Alta Building, floor 3, computer lab)")
                    if apply_ and not exists:
                        BRoom.objects.create(level=lvl, building="Alta Building", floor=3, room_number="Comp Lab B",
                                             capacity=40, room_type="computer_lab", notes="Shared by SHS and JHS")
            except Exception as e:                                   # basic_ed not installed/migrated
                plan.append(f"basic-ed rooms skipped ({e.__class__.__name__})")
            if not apply_:
                transaction.set_rollback(True)
        for line in plan:
            out("  " + line)
        out(self.style.SUCCESS("Applied.") if apply_ else self.style.WARNING("Preview only. Add --apply to make the change."))
