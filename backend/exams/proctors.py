"""
Who proctors which exam.

  Major (program) subjects ... the faculty of the subject's own college, Dean included (Computer Studies exams: Computer Studies
                               faculty and their Dean; the same for Nursing, Allied Health, Business Administration ...).
  Minor (Gen Ed) subjects .... College of Arts and Science (CAS) faculty whose SPECIALIZATION matches the subject (English,
                               Filipino, Mathematics, Social Science, FCL, Communication ...). When the subject has an academic
                               field it must be one of the teacher's specializations; otherwise the field is read from the title.

Tiers (best first). The generator takes the first tier that has a free person that hour, so an exam is never left without a proctor,
but the saved-exam check reports every proctor who came from a lower tier.
  major: 0 = own college (a teacher of the subject's field first)      1 = anybody else
  minor: 0 = CAS + matching specialization   1 = any other faculty with a matching specialization   2 = other CAS   3 = anybody
"""
import re
from collections import defaultdict

# Gen Ed title keywords -> specialization keywords of the teachers who may proctor it (first matching rule wins)
GENED_RULES = [
    (("filipino christian living", "fcl"), ("fcl", "christian", "theology", "religion", "values", "filipino christian")),
    (("filipino",), ("filipino",)),
    (("literature", "english", "purposive communication", "technical writing", "grammar"), ("english", "literature", "communication")),
    (("communication",), ("communication", "english")),
    (("mathematics", "statistics", "calculus", "algebra"), ("mathematics", "math", "statistics")),
    (("environmental science", "science"), ("science", "biology", "chemistry", "physics", "environment", "social science")),
    (("history", "contemporary world", "understanding the self", "rizal", "ethics", "gender", "society", "art appreciation",
      "popular culture", "anthropology", "antropology"), ("social science", "history", "philosophy", "humanities", "psychology", "sociology")),
    (("physical education", "pathfit", "nstp", "rotc"), ("physical education", "pe", "nstp", "rotc", "sports")),
]


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def is_cas(dept):
    d = _norm(dept)
    return "arts" in d and "science" in d


def wanted_specializations(subject):
    """Keywords a teacher's specialization must contain for this Gen Ed subject; () = any CAS teacher may proctor it."""
    field = getattr(subject, "field", None)
    if field is not None:
        return (_norm(field.name),)
    title = _norm(getattr(subject, "title", ""))
    for keys, wants in GENED_RULES:
        if any(k in title for k in keys):
            return wants
    return ()


class ProctorPool:
    def __init__(self, faculty):
        self.faculty = list(faculty)
        self.depts, self.specs = {}, {}
        for f in self.faculty:
            u = f.user
            self.depts[f.id] = [_norm(d) for d in (u.departments if hasattr(u, "departments") else [u.department])]
            self.specs[f.id] = [_norm(a.name) for a in f.specializations.all()]
        self._tiers = {}

    def _match(self, f, wants):
        return any(w in s or s in w for w in wants for s in self.specs[f.id])

    def tiers(self, subject):
        key = subject.id
        if key in self._tiers:
            return self._tiers[key]
        if subject.classification == "minor":
            wants = wanted_specializations(subject)
            cas = [f for f in self.faculty if any(is_cas(d) for d in self.depts[f.id])]
            t0 = [f for f in cas if (not wants) or self._match(f, wants)]
            t1 = [f for f in self.faculty if wants and f not in t0 and self._match(f, wants)]
            used = {f.id for f in t0 + t1}
            t2 = [f for f in cas if f.id not in used]
            t3 = [f for f in self.faculty if f.id not in used and f not in t2]
            tiers = [t0, t1, t2, t3]
        else:
            dept = _norm(getattr(subject.program, "department", ""))
            own = [f for f in self.faculty if dept in self.depts[f.id]]
            fld = getattr(subject, "field_id", None)
            field_first = [f for f in own if fld is not None and any(a.id == fld for a in f.specializations.all())]
            t0 = field_first + [f for f in own if f not in field_first]
            tiers = [t0, [f for f in self.faculty if f not in t0]]
        self._tiers[key] = tiers
        return tiers

    def pick(self, subject, busy, load):
        """The least-loaded free person of the best tier that has one, or None."""
        for tier in self.tiers(subject):
            free = [f for f in tier if f.id not in busy]
            if free:
                return min(free, key=lambda f: (load.get(f.id, 0), f.id))
        return None

    def acceptable(self, subject, faculty_id):
        """True when this person is in the tiers the rules allow (major: own college; minor: CAS or matching specialization)."""
        tiers = self.tiers(subject)
        ok = tiers[:1] if subject.classification != "minor" else tiers[:2]
        return any(f.id == faculty_id for t in ok for f in t)
