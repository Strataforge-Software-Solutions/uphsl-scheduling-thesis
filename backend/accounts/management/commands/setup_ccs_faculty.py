"""
Set the College of Computer Studies Dean's name and replace its faculty list.

  python manage.py setup_ccs_faculty            # preview only
  python manage.py setup_ccs_faculty --apply    # do it

* The Dean (the Dean account of Computer Studies, normally UPHM-D1001) is renamed
  "Dr. Anna Liza O. Villanueva". The login and password are NOT changed.
* The college's six faculty members below replace the old ones. Old faculty accounts are CHANGED in
  place where possible (so their schedules/availability stay and the College keeps working), in this order:
  full-time first, then part-time; any old account left over is deleted, and a new account (F####/P####,
  default password = School ID) is created if there are fewer old accounts than people.
* A reused account keeps its login (School ID) and its specializations, so the scheduler still has a teacher for
  each subject. Change specializations afterwards in the Faculty tab. The degree is stored as given.
Safe to run twice: people already in place are left alone.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.views import next_school_id
from curriculum.models import AcademicField
from faculty.models import FacultyProfile

User = get_user_model()
DEPT = "Computer Studies"
DEAN = ("Dr. Anna Liza O.", "Villanueva")
DEAN_DEGREE = "Doctor of Philosophy, major in Educational Management; MSIT"
DEAN_SPECS = ["Educational Management", "BS Information Technology"]
# (first name(s), last name, faculty type, degree, specializations to add)
PEOPLE = [
    # BSIT / MSIT map onto the existing "BS Information Technology" field and Mathematics onto "Major in Mathematics",
    # so the scheduler can match these teachers to subjects; the degree text is stored as the Dean wrote it.
    ("Vincent D.", "Ang", "full_time", "BSIT", ["BS Information Technology"]),
    ("Juan Emerson P.", "Olino", "full_time", "BSIT", ["BS Information Technology"]),
    ("Dr. Jeusuel Nonnatus N.", "De Luna", "part_time", "MSIT, Doctorate in Industrial Education Management", ["Industrial Education Management"]),
    ("Joseph Albert E.", "Mazo", "part_time", "Master of Business Administration", ["Artificial Intelligence"]),
    ("Dr. Celia", "Verano", "full_time", "Doctorate of Mathematics", ["Major in Mathematics"]),
    ("Rodel", "Tungol", "full_time", "MSIT", ["BS Information Technology"]),
]


class Command(BaseCommand):
    help = "Rename the Computer Studies Dean and replace the Computer Studies faculty."

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")
        p.add_argument("--department", default=None,
                       help="Exact department name of the college's faculty. Default: the Dean's own department.")
        p.add_argument("--part-time", default="", help="Extra last names to mark part-time, e.g. Tungol (De Luna and Mazo already are)")

    def handle(self, *a, **o):
        from engine.models import Schedule
        out, apply_ = self.stdout.write, o["apply"]
        part = {x.strip().lower() for x in o["part_time"].split(",") if x.strip()}
        with transaction.atomic():
            dean = (User.objects.filter(school_id__in=["D1001"]).first()
                    or User.objects.filter(role="faculty", faculty_type="dean", department__icontains="computer").first())
            dept = o["department"] or (dean.department if dean and dean.department else DEPT)
            out(f"College (department name used): {dept!r}")
            if dean:
                out(f"Dean {dean.username}: {dean.get_full_name()!r} -> {' '.join(DEAN)!r}")
                dean.first_name, dean.last_name = DEAN
                dean.save(update_fields=["first_name", "last_name"])
                dprof, _ = FacultyProfile.objects.get_or_create(user=dean)
                dprof.degree = DEAN_DEGREE
                dprof.save(update_fields=["degree"])
                dprof.specializations.set([AcademicField.objects.get_or_create(name=x)[0] for x in DEAN_SPECS])
            else:
                out(self.style.WARNING("No Computer Studies Dean account found; name not changed."))

            # the college's faculty: its own department name, or any spelling of "Computer Studies"
            from django.db.models import Q
            old = list(User.objects.filter(role="faculty").exclude(faculty_type="dean")
                       .filter(Q(department__iexact=dept) | Q(department__icontains="computer studies"))
                       .order_by("faculty_type", "school_id"))
            out(f"Current faculty found in this college: {len(old)}")
            old.sort(key=lambda u: (u.faculty_type != "full_time", u.school_id))
            wanted = {f"{f} {l}".lower() for f, l, *_ in PEOPLE}
            keep = {u.id: u for u in old if u.get_full_name().lower() in wanted}   # already correct: untouched
            pool = [u for u in old if u.id not in keep]
            for first, last, ftype, degree, specs in PEOPLE:
                ftype = "part_time" if last.lower() in part else ftype
                name = f"{first} {last}"
                u = next((x for x in keep.values() if x.get_full_name().lower() == name.lower()), None)
                if u is not None:
                    out(f"  ok       {name} (already in place" + (f"; type {u.faculty_type} -> {ftype}" if u.faculty_type != ftype else "") + ")")
                else:
                    u = self._pick(pool, ftype, name, out, dept)
                    if u is None:
                        continue
                u.first_name, u.last_name, u.faculty_type, u.department = first, last, ftype, dept
                u.save()
                prof, _ = FacultyProfile.objects.get_or_create(user=u)
                prof.degree = degree                       # exactly as listed (blank = none)
                prof.save(update_fields=["degree"])
                prof.specializations.set([AcademicField.objects.get_or_create(name=sp)[0] for sp in specs])
                continue
                same = [x for x in pool if x.faculty_type == ftype]      # keep F#### for full-time, P#### for part-time
                u = (same or pool or [None])[0]
                if u is not None:
                    pool.remove(u)
                if u is None:
                    sid = next_school_id(ftype)
                    u = User(school_id=sid, role="faculty", must_change_password=True)
                    u.set_password(sid)
                    action = f"create   {name} -> {sid} ({ftype})"
                else:
                    action = f"change   {u.username} {u.get_full_name()!r} -> {name!r} ({ftype})"
                out("  " + action)
                u.first_name, u.last_name, u.faculty_type, u.department = first, last, ftype, dept
                u.save()
                prof, _ = FacultyProfile.objects.get_or_create(user=u)
                if degree:
                    prof.degree = degree
                    prof.save(update_fields=["degree"])
                for s in specs:
                    prof.specializations.add(AcademicField.objects.get_or_create(name=s)[0])
            for u in pool:                                        # left over: delete
                n = Schedule.objects.filter(teacher__user=u).count()
                out(f"  delete   {u.username} {u.get_full_name()!r} ({n} schedule row(s) go with it; re-generate to refill)")
                u.delete()
            if not apply_:
                transaction.set_rollback(True)
        out(self.style.SUCCESS("Applied.") if apply_ else self.style.WARNING("Preview only. Add --apply to make the change."))

    def _pick(self, pool, ftype, name, out, dept):
        same = [x for x in pool if x.faculty_type == ftype]      # keep F#### for full-time, P#### for part-time
        u = (same or pool or [None])[0]
        if u is not None:
            pool.remove(u)
            out(f"  change   {u.username} {u.get_full_name()!r} -> {name!r} ({ftype})")
            return u
        sid = next_school_id(ftype)
        u = User(school_id=sid, role="faculty", must_change_password=True)
        u.set_password(sid)
        out(f"  create   {name} -> {sid} ({ftype})")
        return u
