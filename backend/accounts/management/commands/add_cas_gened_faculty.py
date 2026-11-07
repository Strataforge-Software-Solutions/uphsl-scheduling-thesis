"""
DEMO Gen Ed faculty for the College of Arts and Science (names are made up), so that FCL, Literature, Science, Physical Education
and STS each have at least one FULL-TIME and one PART-TIME teacher who qualifies under the CAS rule (engine/qualification.py).

    python manage.py add_cas_gened_faculty            # DRY RUN: prints what would be created / tagged, saves nothing
    python manage.py add_cas_gened_faculty --apply    # saves it
    python manage.py add_cas_gened_faculty --one-per-area           # DRY RUN: 1 full-time + 1 part-time NEW account per area (5 + 5)
    python manage.py add_cas_gened_faculty --one-per-area --apply   # saves those (re-running skips the ones that exist)
    python manage.py add_cas_gened_faculty --social-humanities           # DRY RUN: 4 NEW CAS accounts (2 full-time + 2 part-time)
    python manage.py add_cas_gened_faculty --social-humanities --apply   #   specialized in Social Studies and Humanities; saves them

* Only what is missing is added: an area that already has a qualified CAS full-timer (or part-timer) gets no new one.
* STS: one full-time and one part-time EXISTING teacher of a related (science) department gets the STS specialization added to their
  profile -- nothing else about them changes (department, account, password, role stay). If none is found, CAS STS accounts are
  created instead.
* New accounts: role faculty, department "College of Arts and Science", the next free F / P school IDs, password = school ID,
  must_change_password = True (as add_gened_faculty). Never a dean or registrar. Specializations reuse the existing field records.
* Safe to re-run: a second run finds the areas covered and does nothing.
"""
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from curriculum.models import AcademicField
from engine.qualification import CAS, GEN_ED_AREAS, _areas_of
from faculty.models import FacultyProfile

User = get_user_model()
STS_FIELD = "Science, Technology and Society"          # the GEC108 title (no STS field record exists yet)
# area -> (specialization names to give a new teacher: existing field records, made-up full-time name, made-up part-time name)
AREAS = {
    "fcl": (["FCL", "Religious Education"], "Lorenzo Santiago", "Maria Theresa Javier"),
    "literature": (["Literature", "Major in Literature"], "Celeste Ramirez", "Adrian Velasco"),
    "science": (["Science", "Biochemistry"], "Dr. Leandro Castro", "Pauline Medina"),
    "pe": (["Physical Education", "BA in Physical Education"], "Ricardo Robles", "Janine Ocampo"),
    "sts": ([STS_FIELD, "Science"], "Dr. Rosalind Tan", "Victor Manansala"),
}
# --social-humanities: 4 demo CAS teachers (made-up names) with a Social Studies and Humanities background
SOCIAL_HUMANITIES = (["Social Studies", "Humanities"],
                     [("full_time", "Teresita Valdez"), ("full_time", "Ramon Aquino"), ("part_time", "Liza Mercado"), ("part_time", "Carlo Domingo")])
# STS samples: existing teachers of a related department whose specializations are science / physics
STS_RELATED = re.compile(r"physics|biochemistry|chemistry|biology|^science$", re.I)


def _creds(p):
    return [p.degree, p.qualifications] + [f.name for f in p.specializations.all()]


def _covered(area, ftype):
    """Active teachers of this type who already qualify for the area: CAS faculty with a related credential (STS: also another
    department's teacher with an explicit STS specialization -- the samples this command tags)."""
    out = []
    for p in FacultyProfile.objects.filter(user__is_active=True, user__faculty_type=ftype).select_related("user").prefetch_related("specializations"):
        cas = CAS in (p.user.departments or [])
        if not cas and area != "sts":
            continue
        if area in (_areas_of(_creds(p), "related") if cas else _areas_of([f.name for f in p.specializations.all()], "explicit")):
            out.append(p)
    return out


def _next_ids(prefix, n):
    used = set(User.objects.values_list("school_id", flat=True)) | set(User.objects.values_list("username", flat=True))
    nums = [int(x[1:]) for x in used if x and re.fullmatch(prefix + r"\d+", x)]
    cur, out = max(nums or [1000]), []
    while len(out) < n:
        cur += 1
        sid = f"{prefix}{cur}"
        if sid not in used and f"UPHM-{sid}" not in used:
            out.append(sid)
    return out


def _field(name, create):
    """The existing field record with this name (case / spacing / '&' vs 'and' ignored); created only if none exists."""
    key = lambda s: re.sub(r"\s+", " ", (s or "").lower().replace("&", "and")).strip()
    found = next((f for f in AcademicField.objects.all() if key(f.name) == key(name)), None)
    if found or not create:
        return found, found is None
    return AcademicField.objects.create(name=name), True


class Command(BaseCommand):
    help = "Demo CAS Gen Ed faculty (FCL, Literature, Science, PE, STS). Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Save (without it nothing is written).")

        parser.add_argument("--one-per-area", action="store_true",
                            help="Create one full-time + one part-time demo CAS account for EACH area (5 + 5), even if covered.")
        parser.add_argument("--social-humanities", action="store_true",
                            help="Create 4 demo CAS accounts (2 full-time + 2 part-time) specialized in Social Studies and Humanities.")

    @staticmethod
    def _sts_sample(ftype):
        """An existing teacher of a related (science) department, outside CAS, to receive the STS specialization."""
        return next((p for p in FacultyProfile.objects.filter(user__is_active=True, user__faculty_type=ftype)
                     .exclude(user__department=CAS).select_related("user").prefetch_related("specializations")
                     .order_by("user__department", "user__school_id")
                     if any(STS_RELATED.search(f.name) for f in p.specializations.all())), None)

    def handle(self, *args, **o):
        if o["apply"]:
            return self._run(True, o["one_per_area"], o["social_humanities"])
        from django.db import connection
        from engine.management.commands.audit_gened_teachers import _read_only
        with connection.execute_wrapper(_read_only):        # a dry run cannot write, whatever happens
            return self._run(False, o["one_per_area"], o["social_humanities"])

    def _run(self, apply, one_per_area=False, social_humanities=False):
        self.stdout.write(("APPLY" if apply else "DRY RUN (nothing is saved; add --apply to save)") + "\n")
        plan_new, plan_tag, ok = [], [], []
        if social_humanities:
            specs, people = SOCIAL_HUMANITIES
            for ftype, name in people:
                first, last = name.rsplit(" ", 1)
                ex = User.objects.filter(department=CAS, first_name=first, last_name=last).first()
                if ex:
                    ok.append(f"Social Studies / Humanities, {ftype.replace('_', '-')}: {name} already exists ({ex.school_id})")
                else:
                    plan_new.append(("social_humanities", ftype, name, specs))
        for area, (specs, ft_name, pt_name) in (AREAS.items() if not social_humanities else []):
            label = GEN_ED_AREAS[area][0]
            for ftype, name in (("full_time", ft_name), ("part_time", pt_name)):
                if one_per_area:
                    # --one-per-area: this area's demo account is created whatever the coverage (skipped once it exists)
                    first, last = name.rsplit(" ", 1)
                    ex = User.objects.filter(department=CAS, first_name=first, last_name=last).first()
                    if ex:
                        ok.append(f"{label}, {ftype.replace('_', '-')}: demo account {name} already exists ({ex.school_id})")
                    else:
                        plan_new.append((area, ftype, name, specs))
                    if area == "sts" and not [p for p in _covered("sts", ftype) if CAS not in (p.user.departments or [])]:
                        pick = self._sts_sample(ftype)
                        if pick is not None:
                            plan_tag.append((pick, ftype))
                    continue
                have = _covered(area, ftype)
                if have:
                    ok.append(f"{label}, {ftype.replace('_', '-')}: already covered by "
                              + ", ".join(f"{p.user.get_full_name()} ({p.user.school_id}, {p.user.department})" for p in have[:3])
                              + (f" and {len(have) - 3} more" if len(have) > 3 else ""))
                    continue
                if area == "sts":
                    pick = self._sts_sample(ftype)
                    if pick is not None:
                        plan_tag.append((pick, ftype))
                        continue
                plan_new.append((area, ftype, name, specs))
        f_ids = _next_ids("F", sum(1 for x in plan_new if x[1] == "full_time"))
        p_ids = _next_ids("P", sum(1 for x in plan_new if x[1] == "part_time"))
        for line in ok:
            self.stdout.write(f"  skip   {line}")
        for p, ftype in plan_tag:
            self.stdout.write(f"  tag    {p.user.get_full_name()} ({p.user.school_id}, {ftype.replace('_', '-')}, {p.user.department}): "
                              f"add specialization '{STS_FIELD}' (department, account and other specializations unchanged)")
        new = []
        for area, ftype, name, specs in plan_new:
            sid = (f_ids if ftype == "full_time" else p_ids).pop(0)
            new.append((sid, name, ftype, specs))
            self.stdout.write(f"  create {sid}  {name}  ({ftype.replace('_', '-')}, {CAS})  specializations {specs}  "
                              f"password = school ID, must change on first login")
        missing = [s for _sid, _n, _f, specs in new for s in specs] + ([STS_FIELD] if plan_tag else [])
        for s in sorted(set(missing)):
            f, is_new = _field(s, create=False)
            if is_new:
                self.stdout.write(f"  field  '{s}' does not exist yet: it will be created (no similar record found)")
        if not apply:
            self.stdout.write(self.style.SUCCESS(f"\nDry run: {len(new)} account(s) to create, {len(plan_tag)} teacher(s) to tag. Nothing saved."))
            return
        with transaction.atomic():
            for p, _ftype in plan_tag:
                p.specializations.add(_field(STS_FIELD, create=True)[0])
            for sid, name, ftype, specs in new:
                if User.objects.filter(school_id=sid).exists():
                    raise RuntimeError(f"{sid} was taken while this ran; nothing was saved. Run it again.")
                first, last = name.rsplit(" ", 1)
                u = User(school_id=sid, first_name=first, last_name=last, role="faculty", faculty_type=ftype, department=CAS,
                         must_change_password=True)
                u.set_password(sid)
                u.save()
                prof, _ = FacultyProfile.objects.get_or_create(user=u)
                prof.specializations.set([_field(s, create=True)[0] for s in specs])
        self.stdout.write(self.style.SUCCESS(f"\nSaved: {len(new)} account(s) created, {len(plan_tag)} teacher(s) tagged."))
