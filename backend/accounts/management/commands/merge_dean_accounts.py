"""
Merge a duplicate dean account into the one that is kept: everything the old account owns is MOVED to the kept account, then the old
account is deleted. Optionally sets the kept account's displayed name.

    python manage.py merge_dean_accounts --from NURS --into D1006 --first "Darwin D." --last "Aznar"            # preview only
    python manage.py merge_dean_accounts --from NURS --into D1006 --first "Darwin D." --last "Aznar" --apply    # do it

Moved (found from the database's own relations, so nothing is missed): classes taught (Schedule.teacher / original_teacher),
availability, absences and coverage suggestions, workload records, constraints, conflict logs, exam proctoring, historical class
records, specializations, notifications, approvals (Schedule.approved_by), audit logs and exams created. The kept account's login,
password, school ID, role, department and permissions do not change (only its first / last name when --first / --last are given).
Everything happens in ONE transaction: if any moved row would break a rule (for example the same teacher twice at one time), nothing
is saved and the reason is printed.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from faculty.models import FacultyProfile


def _relations(model):
    """[(related model, field name, kind)] of every relation pointing at `model` (fk / o2o), plus reverse many-to-many accessors."""
    out = []
    for r in model._meta.related_objects:
        out.append((r.related_model, r.field.name, "o2o" if r.one_to_one else ("m2m" if r.many_to_many else "fk"), r))
    return out


class Command(BaseCommand):
    help = "Move everything of a duplicate dean account into the kept one, then delete the duplicate. Preview unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="src", required=True, help="School ID of the account to remove (e.g. NURS)")
        parser.add_argument("--into", dest="dst", required=True, help="School ID of the account to keep (e.g. D1006)")
        parser.add_argument("--first", default=None, help="New first name for the kept account")
        parser.add_argument("--last", default=None, help="New last name for the kept account")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *a, **o):
        User = get_user_model()
        src = User.objects.filter(school_id=o["src"]).first()
        dst = User.objects.filter(school_id=o["dst"]).first()
        if src is None or dst is None:
            raise CommandError(f"Account not found: {o['src'] if src is None else o['dst']}. Nothing changed.")
        if src.pk == dst.pk:
            raise CommandError("--from and --into are the same account. Nothing changed.")
        if not (src.role == dst.role == "faculty" and src.faculty_type == dst.faculty_type == "dean"):
            raise CommandError("Both accounts must be deans. Nothing changed.")
        if set(src.departments) - set(dst.departments):
            raise CommandError(f"{src.school_id} covers {src.departments}, but {dst.school_id} covers {dst.departments}: the kept dean "
                               "would lose a college. Nothing changed.")
        sp, dp = FacultyProfile.objects.filter(user=src).first(), FacultyProfile.objects.filter(user=dst).first()
        self.stdout.write(f"Remove: {src.school_id} / {src.username}  {src.get_full_name()}  ({src.department})")
        self.stdout.write(f"Keep:   {dst.school_id} / {dst.username}  {dst.get_full_name()}  ({dst.department})"
                          + (f"  -> renamed to {o['first'] or dst.first_name} {o['last'] or dst.last_name}" if o["first"] or o["last"] else ""))
        plan = []
        for model, field, kind, rel in _relations(User):
            if kind == "fk":
                n = model.objects.filter(**{field: src}).count()
                if n:
                    plan.append(("user", model, field, kind, rel, n))
            elif kind == "o2o" and model is not FacultyProfile and model.objects.filter(**{field: src}).exists():
                if model.objects.filter(**{field: dst}).exists():
                    raise CommandError(f"Both accounts have a {model.__name__} record; merge it by hand first. Nothing changed.")
                plan.append(("user", model, field, kind, rel, 1))
        if sp is not None:
            for model, field, kind, rel in _relations(FacultyProfile):
                if kind == "fk":
                    n = model.objects.filter(**{field: sp}).count()
                    if n:
                        plan.append(("profile", model, field, kind, rel, n))
            specs = list(sp.specializations.all())
            if specs:
                self.stdout.write(f"  specializations to copy: {[f.name for f in specs]}")
        for who, model, field, kind, _rel, n in plan:
            self.stdout.write(f"  move {n:4d} {model.__name__}.{field}")
        if not plan and not (sp and sp.specializations.exists()):
            self.stdout.write("  nothing stored for the removed account besides the account itself")
        # classes would clash with the kept dean's own classes at the same time: refuse before touching anything
        if sp is not None and dp is not None:
            from engine.models import Schedule
            mine = set(Schedule.objects.filter(teacher=dp).values_list("timeslot_id", "term"))
            clash = [s for s in Schedule.objects.filter(teacher=sp).select_related("subject", "timeslot") if (s.timeslot_id, s.term) in mine]
            if clash:
                raise CommandError("These classes of the removed account are at a time the kept dean already teaches: "
                                   + "; ".join(f"{c.subject.code} {c.timeslot.day} {c.timeslot.start_time:%H:%M}" for c in clash[:10])
                                   + ". Reassign them first. Nothing changed.")
        if not o["apply"]:
            self.stdout.write(self.style.WARNING("Preview only. Add --apply to move everything and delete the duplicate account."))
            return
        try:
            with transaction.atomic():
                if sp is not None and dp is None:
                    sp.user = dst                     # the kept dean had no faculty profile: the old one simply becomes theirs
                    sp.save(update_fields=["user"])
                    sp = None
                for who, model, field, kind, _rel, _n in plan:
                    if who == "user":
                        model.objects.filter(**{field: src}).update(**{field: dst})
                    elif sp is not None:
                        model.objects.filter(**{field: sp}).update(**{field: dp})
                if sp is not None:
                    dp.specializations.add(*sp.specializations.all())
                    changed = []
                    for f in ("degree", "qualifications"):
                        if not getattr(dp, f) and getattr(sp, f):
                            setattr(dp, f, getattr(sp, f))
                            changed.append(f)
                    if changed:
                        dp.save(update_fields=changed)
                    sp.delete()
                if o["first"] or o["last"]:
                    dst.first_name = o["first"] if o["first"] is not None else dst.first_name
                    dst.last_name = o["last"] if o["last"] is not None else dst.last_name
                    dst.save(update_fields=["first_name", "last_name"])
                src.delete()
        except IntegrityError as e:
            raise CommandError(f"Nothing was saved: a moved record would break a database rule ({str(e).splitlines()[0]}).")
        self.stdout.write(self.style.SUCCESS(f"Done. {o['src']} was merged into {dst.school_id} ({dst.get_full_name()}) and removed. "
                                             "Sign out and back in so the dashboard shows the new name."))
