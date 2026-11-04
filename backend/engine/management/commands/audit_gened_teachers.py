"""
READ-ONLY report on Gen Ed (minor) teaching under the College of Arts and Science rule (engine/qualification.py).

    python manage.py audit_gened_teachers              # both parts
    python manage.py audit_gened_teachers --coverage   # only: each Gen Ed subject and its qualified teachers
    python manage.py audit_gened_teachers --classes    # only: existing Gen Ed classes held by a teacher the rule does not allow

Nothing is changed: generated, approved, published and shared classes stay exactly as they are (the database connection refuses
any write while this runs), so you can decide what to do with each one.
"""
import re
from collections import OrderedDict, defaultdict

from django.core.management.base import BaseCommand
from django.db import connection

from curriculum.models import Subject
from engine.models import Schedule
from engine.qualification import CAS, area_label, is_qualified
from faculty.models import FacultyProfile

_WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP)\b", re.I)


def _read_only(execute, sql, params, many, context):
    if _WRITE.match(sql):
        raise RuntimeError("audit_gened_teachers is read-only: a write was refused")
    return execute(sql, params, many, context)


def _name(p):
    return f"{p.user.get_full_name().strip() or p.user.username} ({p.user.school_id}, {(p.user.faculty_type or '').replace('_', '-')})"


def coverage():
    """[(code, title, label, [CAS teachers], [other-department teachers])] per distinct Gen Ed subject (code + title)."""
    teachers = list(FacultyProfile.objects.filter(user__is_active=True).exclude(user__faculty_type="dean")
                    .select_related("user").prefetch_related("specializations"))
    spec = {t.id: {f.id for f in t.specializations.all()} for t in teachers}
    seen = OrderedDict()
    for s in Subject.objects.filter(classification="minor").select_related("field", "program").order_by("code", "title"):
        seen.setdefault((s.code, s.title.strip()), s)
    out = []
    for (code, title), s in seen.items():
        ok = [t for t in teachers if is_qualified(t, s, None, spec[t.id])]
        cas = [t for t in ok if CAS in (t.user.departments or [])]
        out.append((code, title, area_label(s), cas, [t for t in ok if t not in cas]))
    return out


def bad_classes():
    """Existing Gen Ed classes whose teacher the rule does not allow: {(teacher, subject, section): [status, ...]}."""
    rows = Schedule.objects.filter(subject__classification="minor").select_related(
        "subject", "subject__field", "subject__program", "section__program", "teacher__user").prefetch_related("teacher__specializations")
    bad = defaultdict(set)
    for r in rows:
        t = r.teacher
        if not is_qualified(t, r.subject, r.section, {f.id for f in t.specializations.all()}):
            bad[(t, r.subject, r.section)].add(r.status + (" shared" if r.merge_key else ""))
    return bad


class Command(BaseCommand):
    help = "READ-ONLY: Gen Ed coverage by CAS faculty, and existing Gen Ed classes held by a teacher the CAS rule does not allow."

    def add_arguments(self, parser):
        parser.add_argument("--coverage", action="store_true")
        parser.add_argument("--classes", action="store_true")

    def handle(self, *args, **o):
        both = not (o["coverage"] or o["classes"])
        with connection.execute_wrapper(_read_only):
            if both or o["coverage"]:
                rows = coverage()
                self.stdout.write(f"GEN ED COVERAGE ({len(rows)} distinct subjects: code + title)")
                gaps = []
                for code, title, label, cas, other in rows:
                    names = ", ".join(_name(t) for t in cas[:4]) + (f" and {len(cas) - 4} more" if len(cas) > 4 else "")
                    extra = f" | other dept. with explicit specialization: {', '.join(_name(t) for t in other[:3])}" if other else ""
                    mark = "  " if cas or other else "!!"
                    self.stdout.write(f" {mark} {code:9s} {title[:46]:46s} [{label or 'no area'}] CAS {len(cas):2d}: {names or '-'}{extra}")
                    if not cas and not other:
                        gaps.append(f"{code} {title}")
                self.stdout.write(self.style.WARNING(f"\nNO qualified teacher ({len(gaps)}): " + ("; ".join(gaps) or "none")))
            if both or o["classes"]:
                bad = bad_classes()
                self.stdout.write(f"\nEXISTING GEN ED CLASSES held by a teacher the CAS rule does not allow: {len(bad)} (nothing changed)")
                by_t = defaultdict(list)
                for (t, sub, sec), st in bad.items():
                    by_t[t].append(f"{sub.code} {sec.program.name} {sec.name} [{'/'.join(sorted(st))}]")
                for t in sorted(by_t, key=lambda x: (x.user.department or "", x.user.school_id or "")):
                    self.stdout.write(f"  {_name(t)} - {t.user.department or 'no department'}: {'; '.join(sorted(by_t[t]))}")
        self.stdout.write(self.style.SUCCESS("\nRead-only report: nothing was changed."))
