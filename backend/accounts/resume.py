"""Best-effort extraction of faculty details from an uploaded resume / CV (PDF, DOCX or TXT).
Nothing is saved: the result only pre-fills the Add Faculty form for the Dean to review and edit."""
import io
import re

MAX_BYTES = 5 * 1024 * 1024
TITLES = r"(?:dr|engr|prof|atty|mr|mrs|ms|mx|arch|rev|sir|ma'am)\.?"
SUFFIX = re.compile(r",?\s+(?:ph\.?d|ed\.?d|mit|mba|mba|maed|man|ms|ma|lpt|cpa|rn|rmt|phd|jr|sr|ii|iii)\.?\s*$", re.I)
DEGREE = re.compile(r"\b(bachelor(?:'s)? of [A-Za-z ,&\-]+|master(?:'s)? of [A-Za-z ,&\-]+|doctor(?:ate)? (?:of|in) [A-Za-z ,&\-]+|"
                    r"ph\.?\s?d\.?[^\n]*|ed\.?\s?d\.?[^\n]*|b\.?s\.? in [A-Za-z ,&\-]+|m\.?s\.? in [A-Za-z ,&\-]+|"
                    r"b\.?a\.? in [A-Za-z ,&\-]+|m\.?a\.? in [A-Za-z ,&\-]+)", re.I)
# abbreviations are matched case-sensitively so ordinary words ("Manila", "Maria") are never mistaken for degrees
DEGREE_ABBR = re.compile(r"\b(?:BSIT|BSCS|BSEd|BEEd|BSBA|BSHM|BSTM|BS|AB|BA|MIT|MBA|MAEd|MAT|MPA|MS|MA|PhD|EdD|DIT|DBA)\b[^\n]{0,70}")
SECTION_QUAL = re.compile(r"licen[sc]|certif|eligib|training|seminar|credential|board|award", re.I)
SECTION_STOP = re.compile(r"^(?:work|employment|experience|education|skills|references|personal|objective|profile|"
                          r"teaching|publications|affiliations|interests|summary)\b", re.I)


def extract_text(name, data):
    name = (name or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in r.pages[:15])
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append("  ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if name.endswith((".txt", ".md", ".rtf")):
        return data.decode("utf-8", "ignore")
    raise ValueError("Please upload a PDF, Word (.docx) or text file.")


def _clean_name(raw):
    raw = re.sub(TITLES + r"\s+", "", raw.strip(), flags=re.I)
    raw = SUFFIX.sub("", raw).strip(" ,.-")
    if "," in raw:                                   # "DELA CRUZ, Juan A."
        last, first = [x.strip() for x in raw.split(",", 1)]
        first = re.sub(r"(?:\s+[A-Za-z]\.?)+$", "", first)       # drop middle initial
        raw = f"{first} {last.title() if last.isupper() else last}"
    parts = [p.title() if p.isupper() and len(p) > 1 else p for p in raw.split()]
    while len(parts) > 2 and re.fullmatch(r"[A-Za-z]\.?", parts[-1]):      # trailing middle initial
        parts.pop()
    raw = " ".join(parts)
    if not 2 <= len(parts) <= 5:
        return None
    if any(re.search(r"\d|@", p) for p in parts):
        return None
    if raw.isupper() or raw.islower():
        raw = raw.title()
    parts = raw.split()
    first = " ".join(parts[:-1])
    last = parts[-1]
    if len(parts) >= 3 and parts[-2].lower() in ("de", "dela", "del", "san", "santa", "van", "von", "de la", "delos"):
        first, last = " ".join(parts[:-2]), " ".join(parts[-2:])
    return first, last


def parse(text, known_fields=()):
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    out = {"first_name": "", "last_name": "", "email": "", "degree": "", "specializations": [], "qualifications": ""}
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    if m:
        out["email"] = m.group(0).lower()
    # name: explicit "Name:" line, else the first line that looks like a person's name
    cand = None
    for l in lines[:40]:
        mm = re.match(r"(?:full\s+)?name\s*[:\-]\s*(.+)", l, re.I)
        if mm:
            cand = _clean_name(mm.group(1)); break
    if not cand:
        for l in lines[:8]:
            if re.search(r"resume|curriculum|vitae|\bcv\b|@|http|phone|address|objective", l, re.I) or len(l) > 45:
                continue
            cand = _clean_name(l)
            if cand:
                break
    if cand:
        out["first_name"], out["last_name"] = cand
    # degrees
    degs = []
    for l in lines:
        for dm in list(DEGREE.finditer(l)) + list(DEGREE_ABBR.finditer(l)):
            d = re.sub(r"\s+", " ", dm.group(0)).strip(" ,;.-")
            d = re.split(r"\s{2,}|\s[-–—|]\s|\s\(?(?:19|20)\d\d", d)[0].strip(" ,;.-")
            if 6 < len(d) <= 110 and d.lower() not in (x.lower() for x in degs):
                degs.append(d)
    out["degree"] = "; ".join(degs[:4])
    # specializations: existing fields mentioned in the resume + "in/major in X" of each degree
    low = text.lower()
    specs = [f for f in known_fields if f and re.search(r"\b" + re.escape(f.lower()) + r"\b", low)]
    for d in degs:
        for pat in (r"major(?:ing)? in ([A-Za-z &]+)", r"\bin ([A-Za-z &]+)$", r"\bof (?:science|arts|education) in ([A-Za-z &]+)"):
            mm = re.search(pat, d, re.I)
            if mm:
                s = re.split(r"\s+(?:major|minor|with|from)\b", mm.group(1).strip(" ,.&"), flags=re.I)[0].strip().title()
                if 3 < len(s) < 60 and s.lower() not in (x.lower() for x in specs):
                    specs.append(s)
    out["specializations"] = specs[:6]
    # licences / certifications / trainings: the lines under such a heading
    quals = []
    for i, l in enumerate(lines):
        if len(l) < 45 and SECTION_QUAL.search(l) and (l.isupper() or l.endswith(":") or l.istitle()):
            for nxt in lines[i + 1:i + 9]:
                if SECTION_STOP.match(nxt) or (nxt.isupper() and len(nxt) < 40):
                    break
                quals.append(nxt.lstrip("•-*· ").strip())
            if quals:
                break
    out["qualifications"] = "; ".join(q for q in quals if 3 < len(q) < 140)[:600]
    out["found"] = [k for k in ("first_name", "last_name", "email", "degree", "specializations", "qualifications") if out[k]]
    return out
