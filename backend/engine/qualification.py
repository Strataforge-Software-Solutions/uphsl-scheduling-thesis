"""Who may teach a subject. One rule used by generation, Resolve, re-arranging and the explanations, so they never disagree.

MAJOR subjects (owned by the Dean) go only to a teacher of the subject's college who is related to the subject:
  1. the subject's academic field is one of the teacher's recorded specializations (the Dean's faculty record); or
  2. the teacher belongs to the subject's college AND the teacher's degree / specializations / qualifications are in the same
     discipline as the subject (e.g. BSIT, MSIT, "Artificial Intelligence" for Computer Science and Information Technology subjects;
     "Physical Therapy" / "Occupational Therapy" / "Respiratory Therapy" for those programs' subjects; "Anatomy", "Pharmacology" ...
     for subjects with those words in the title: see PHRASE_FAMILIES).
  Nothing weaker counts: a shared word between the subject title and a degree, or simply being in the same college, is NOT enough.
  A major with no field recorded and no same-discipline teacher is reported ("tag the subject's field"), never given to just anyone.
GEN ED (minor) subjects (owned by the Registrar) are taught by the College of Arts and Science (CAS):
  a. a CAS teacher whose specialization is the subject's field (1), or whose degree / specializations / qualifications are in the
     subject's discipline family or Gen Ed area (GEN_ED_AREAS: FCL, Literature, Science, PE, STS, ...), matched from the subject's
     field and title -- the curriculum's Gen Ed subjects have no field recorded, so the title decides;
  b. a teacher of ANOTHER department only with an EXPLICIT specialization for it (the subject's field, or a specialization that names
     the Gen Ed area, e.g. "Science, Technology and Society" for STS), or a discipline that genuinely is the subject's family (e.g. a
     mathematics specialist for Mathematics in the Modern World, a computing teacher for Living in the IT Era).
  There is no "no field recorded -> any teacher" fallback any more, and being free is never enough.
There is no "everybody" fallback for majors: when nobody qualifies, the caller reports it (see why_nobody)."""
import re

# discipline families: words found in a degree / specialization / qualification / subject text
FAMILIES = {
    "computing": {"computer", "computing", "information", "technology", "informatics", "software", "programming", "database", "network",
                  "networking", "web", "artificial", "intelligence", "cybersecurity", "cyber", "multimedia", "bsit", "bscs", "msit", "mscs",
                  "bsis", "mis", "cs", "it", "data", "analytics", "systems", "algorithm", "algorithms", "computation", "robotics", "game"},
    "mathematics": {"mathematics", "math", "statistics", "calculus", "algebra", "geometry", "trigonometry", "mathematical"},
}
# Allied Health disciplines, matched as PHRASES in the degree / specialization / qualification text and in the subject's field, title
# and (majors) program name -- e.g. "BS Physical Therapy" subjects <-> a "Musculoskeletal Physical Therapy" specialization. Phrases,
# not single words, so "Physical Activities" (PATHFIT) is not Physical Therapy and "RT" (also Radiologic Technology) is not used.
PHRASE_FAMILIES = {
    "physical_therapy": (r"physical therap", r"\bbspt\b", r"\bptrp\b", r"\bpt\b"),
    "occupational_therapy": (r"occupational therap", r"\bbsot\b", r"\botrp\b", r"\bot\b"),
    "respiratory_therapy": (r"respiratory (therap|care)", r"\bbsrt\b", r"\brrt\b"),
    "anatomy": (r"\banatomy\b",),
    "physiology": (r"\bphysiology\b",),
    "kinesiology": (r"\bkinesiology\b",),
    "neurosciences": (r"\bneuro(science|sciences|logic|logical|anatomy)\b",),
    "pathophysiology": (r"\bpathophysiology\b", r"\bpathology\b"),
    "pharmacology": (r"\bpharmacology\b",),
    "cardiopulmonary": (r"\bcardio-?pulmonary\b", r"\bcardio-?respiratory\b"),
    "psychiatry": (r"\bpsychiatr", r"\bmental health\b"),
    "orthotics_prosthetics": (r"\borthotics?\b", r"\bprosthetics?\b", r"\bassistive technolog"),
    "electrotherapy": (r"\belectrotherap",),
    "research": (r"\bresearch\b", r"\bevidence[- ]based practice\b"),
}
_PHRASES = {name: [re.compile(p) for p in pats] for name, pats in PHRASE_FAMILIES.items()}

CAS = "College of Arts and Science"
# Gen Ed areas: (label, patterns that find the area in a SUBJECT's field / title, patterns that find it in a TEACHER's degree /
# specialization / qualification, discipline family that also counts). A teacher of another department needs a specialization that
# matches the SUBJECT patterns (an explicit specialization naming the area) or the family; a CAS teacher may match either list.
GEN_ED_AREAS = {
    "fcl": ("FCL (Filipino Christian Living)", (r"filipino christian living", r"\bfcl\b"),
            (r"\bfcl\b", r"christian living", r"religious education", r"values education", r"theolog", r"religious studies"), None),
    "filipino": ("Filipino", (r"^filipino\s*\d", r"\bwika\b", r"panitikan", r"^filipino$"), (r"\bfilipino\b(?!\s+christian)",), None),
    "literature": ("Literature", (r"literature",), (r"literature", r"\bliterary\b"), None),
    "english": ("English", (r"\benglish\b", r"technical writing"), (r"\benglish\b", r"technical writing", r"linguistic"), None),
    "purposive": ("Purposive Communication", (r"purposive communication",), (r"\benglish\b", r"\bcommunication\b"), None),
    "mathematics": ("Mathematics", (r"mathematic", r"statistic"), (r"mathematic", r"statistic", r"\bmath\b"), "mathematics"),
    "science": ("Science", (r"environmental science", r"\bbiology\b", r"\bchemistry\b", r"\bphysics\b", r"natural science"),
                (r"^(general |natural |environmental |physical |life |earth )?sciences?$", r"biology", r"chemistry", r"physics",
                 r"environmental science"), None),
    "sts": ("STS (Science, Technology and Society)", (r"science,?\s+technology,?\s+(and|&)\s+society", r"\bsts\b"),
            (r"science,?\s+technology,?\s+(and|&)\s+society", r"\bsts\b"), None),
    "pe": ("Physical Education", (r"physical education", r"\bpathfit\b", r"physical activities toward"),
           (r"physical education", r"\bpathfit\b", r"\bbped\b", r"\bsports?\b", r"exercise science", r"physical fitness"), None),
    "nstp": ("NSTP / ROTC", (r"\bnstp\d*\b", r"national service training", r"\brotc\d*\b"),
             (r"\bnstp\b", r"\brotc\b", r"national service", r"military science"), None),
    "history": ("History / Social Science", (r"philippine history", r"\brizal\b", r"contemporary world"),
                (r"histor", r"social science", r"social studies", r"political science"), None),
    "self": ("Psychology", (r"understanding the self",), (r"psycholog",), None),
    "ethics": ("Philosophy / Ethics", (r"\bethics\b",), (r"philosoph", r"\bethics\b"), None),
    "art": ("Arts / Humanities", (r"art appreciation",), (r"fine arts?", r"\barts? education\b", r"humanities", r"^arts?$"), None),
    "gender": ("Sociology / Gender Studies", (r"gender and society",), (r"sociolog", r"gender", r"social science"), None),
    "it_era": ("Computing", (r"living in the it era", r"computer literacy"), (), "computing"),
}
_AREA_RX = {k: ([re.compile(x) for x in a[1]], [re.compile(x) for x in a[2]]) for k, a in GEN_ED_AREAS.items()}
# what counts as an EXPLICIT specialization for an area (another department's teacher), when it is narrower than the subject patterns:
# "Radiation Physics" is a physics specialty, not an Environmental Science specialization
_EXPLICIT_RX = {"science": [re.compile(x) for x in (r"environmental science", r"natural science", r"^(general )?sciences?$")]}


def subject_areas(subject):
    """The Gen Ed areas of a subject, from its field and title."""
    field = getattr(getattr(subject, "field", None), "name", "") if subject.field_id else ""
    out = set()
    for text in (field, subject.title):
        low = (text or "").lower().strip()
        out |= {k for k, (srx, _t) in _AREA_RX.items() if low and any(r.search(low) for r in srx)}
    return out


def _areas_of(texts, which):
    """Areas named in a teacher's credentials: "explicit" = a credential that names the area itself; "related" = also a related one."""
    out = set()
    for t in texts:
        low = (t or "").lower().strip()
        if not low:
            continue
        for k, (srx, trx) in _AREA_RX.items():
            pats = _EXPLICIT_RX.get(k, srx) if which == "explicit" else trx + srx
            if any(r.search(low) for r in pats):
                out.add(k)
    return out


def _phrase_fams(text):
    low = (text or "").lower()
    return {name for name, pats in _PHRASES.items() if any(p.search(low) for p in pats)}


# words too common to prove a family on their own
WEAK = {"systems", "data", "technology", "information", "game", "web", "network", "it", "mis"}
_STOP = {"and", "of", "the", "in", "for", "to", "a", "an", "i", "ii", "iii", "iv", "lec", "lab", "lecture", "laboratory", "introduction",
         "fundamentals", "principles", "basic", "advanced", "with", "on", "major", "bachelor", "master", "doctor", "science", "studies",
         "education", "management", "arts", "philosophy"}


def _words(text):
    return set(re.findall(r"[a-z]{2,}", (text or "").lower()))


def _fams(words):
    out = set()
    for name, vocab in FAMILIES.items():
        hits = words & vocab
        strong = hits - WEAK
        if strong or len(hits) >= 2:
            out.add(name)
    return out


def _teacher_info(t, spec_ids):
    info = getattr(t, "_qinfo", None)
    if info is None:
        specs = []
        try:
            specs = [f.name for f in t.specializations.all()]
        except Exception:
            pass
        text = f"{t.degree} {t.qualifications} {' '.join(specs)}"
        words = _words(text)
        user = getattr(t, "user", None)
        deps = set(getattr(user, "departments", None) or ([user.department] if getattr(user, "department", None) else [])) if user else set()
        creds = [t.degree, t.qualifications] + specs
        info = {"words": words, "fams": _fams(words) | _phrase_fams(text), "content": words - _STOP, "deps": deps,
                "areas": _areas_of(creds, "related"), "explicit": _areas_of(specs, "explicit")}
        t._qinfo = info
    return info


def _subject_info(subject):
    info = getattr(subject, "_qinfo", None)
    if info is None:
        field = getattr(getattr(subject, "field", None), "name", "") if subject.field_id else ""
        words = _words(f"{field} {subject.title}")
        prog = getattr(subject, "program", None)
        prog_name = getattr(prog, "name", "") if subject.classification != "minor" else ""
        info = {"fams": _fams(words | _words(prog_name)) | _phrase_fams(f"{field} {subject.title} {prog_name}"),
                "content": words - _STOP, "field": field}
        subject._qinfo = info
    return info


def is_qualified(teacher, subject, section, spec_ids):
    """spec_ids: the set of AcademicField ids of this teacher (the scheduler's specialization_map entry)."""
    major = subject.classification != "minor"
    dept = getattr(getattr(section, "program", None), "department", None) or getattr(getattr(subject, "program", None), "department", None)
    t, s = _teacher_info(teacher, spec_ids), _subject_info(subject)
    same_dept = (not dept) or dept in t["deps"]
    if major and not same_dept:
        return False          # a Dean's major goes only to that college's own faculty, even when a specialization matches
    if subject.field_id is not None and subject.field_id in spec_ids:
        return True
    if major:
        return bool(s["fams"] & t["fams"])   # specialization or same discipline only: no title-word match, no "same college" fallback
    # GEN ED: the College of Arts and Science, or an explicit specialization / the subject's own discipline elsewhere
    areas = subject_areas(subject)
    fams = s["fams"] | {GEN_ED_AREAS[a][3] for a in areas if GEN_ED_AREAS[a][3]}
    if fams & t["fams"]:
        return True                           # e.g. a mathematics specialist for Mathematics in the Modern World (any department)
    if CAS not in t["deps"]:
        return bool(areas & t["explicit"])    # other department: only a specialization that names this Gen Ed area
    if areas & t["areas"]:
        return True
    # a Gen Ed subject in no known area: a CAS teacher whose degree / specialization words appear in its title / field
    return (not areas) and bool(s["content"] & t["content"]) and bool(t["words"] - _STOP)


def qualified_teachers(subject, section, teachers, specialization_map):
    return [t for t in teachers if is_qualified(t, subject, section, specialization_map.get(t.id, set()))]


def area_label(subject):
    areas = subject_areas(subject)
    return " / ".join(GEN_ED_AREAS[a][0] for a in sorted(areas)) or (getattr(subject.field, "name", "") if subject.field_id else "")


def why_nobody(subject, section, teachers, specialization_map):
    """Plain-language reason for 'no qualified teacher' (a specific issue, never 'add faculty')."""
    if subject.classification == "minor":
        label = area_label(subject)
        cas = [t for t in teachers if CAS in _teacher_info(t, set())["deps"]]
        return (f"No CAS faculty with a {label or 'related'} specialization is available for {subject.code} {subject.title}. "
                f"Gen Ed subjects are taught by the College of Arts and Science ({len(cas)} CAS faculty checked); faculty of other "
                f"departments qualify only with an explicit {label or 'matching'} specialization. Add the specialization to a "
                "suitable teacher in the Faculty tab; nobody unrelated was assigned.")
    field = getattr(subject.field, "name", "") if subject.field_id else ""
    dept = getattr(section.program, "department", "")
    kind = "major" if subject.classification != "minor" else "Gen Ed"
    in_dept = [t for t in teachers if (not dept) or dept in _teacher_info(t, set())["deps"]]
    return (f"No qualified faculty for {subject.code} ({kind} subject{', field: ' + field if field else ', no field recorded'}). "
            f"{len(teachers)} faculty were checked" + (f", {len(in_dept)} of them in {dept}" if kind == "major" else "") +
            ": none has this specialization, or a degree / qualification in the same discipline. "
            f"The Dean of {dept} can add the specialization, degree or qualification in the Faculty tab "
            "(or tag the subject's field in the Curriculum tab); nobody unrelated was assigned." +
            (" This subject has no field recorded yet, so only a recorded specialization or a same-discipline degree can match it: "
             "tag its field in the Curriculum tab." if (kind == "major" and not field) else ""))
