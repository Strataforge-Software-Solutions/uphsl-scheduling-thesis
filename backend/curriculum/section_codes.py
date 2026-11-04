"""
Section naming: every program gets its own block letter so sections from
different departments never look alike (CS 1st year is "A1", BA Comm 1st year
is "C1", ...). The year level number is appended.

    Computer Science           A      (A1, A2, A3, A4)
    Information Technology     A.b    (A.b1, A.b2, ...)
    Allied Health / PT          B
    Occupational Therapy        B.b
    Respiratory Therapy (RT)    B.c
    BA Communication            C
    Radiologic Technology       D
    BSBA Marketing Mgmt         E
    BSBA Human Resource Dev.    F
    BS Hospitality Mgmt         G
    BS Tourism Mgmt             H
    any other program           I, J, K ... (in the order the programs were created)
"""
import re

# (keyword that must appear in the lower-cased program name, prefix) -- first match wins
KEYWORD_PREFIX = [
    ("information technology", "A.b"),
    ("computer science", "A"),
    ("occupational therapy", "B.b"),
    ("respiratory", "B.c"),
    ("physical therapy", "B"),
    ("medical technology", "B"),
    ("allied", "B"),
    ("communication", "C"),
    ("radiologic", "D"),
    ("marketing", "E"),
    ("human resource", "F"),
    ("hospitality", "G"),
    ("tourism", "H"),
]
EXTRA_LETTERS = "IJKLMNOPQRSTUVWXYZ"


def known_prefix(program_name):
    name = (program_name or "").lower()
    for keyword, prefix in KEYWORD_PREFIX:
        if keyword in name:
            return prefix
    return None


def year_number(year_level):
    m = re.search(r"\d+", year_level or "")
    return m.group(0) if m else ""


def prefix_for_program(program):
    """Prefix for a Program row. Programs without a fixed letter get the next
    free letter (E, F, ...) by creation order, so the result is stable."""
    k = known_prefix(program.name)
    if k:
        return k
    from curriculum.models import Program
    others = [p for p in Program.objects.order_by("id") if not known_prefix(p.name)]
    idx = [p.id for p in others].index(program.id) if program.id in [p.id for p in others] else len(others)
    return EXTRA_LETTERS[idx % len(EXTRA_LETTERS)]


def section_name(program, year_level):
    return f"{prefix_for_program(program)}{year_number(year_level)}"
