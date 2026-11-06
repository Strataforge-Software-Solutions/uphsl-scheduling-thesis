"""
Section naming: each program has its own code and the year level number is appended (CS1 = Computer Science 1st year).

    College of Computer Studies       Computer Science            CS   (CS1, CS2, CS3, CS4)
                                      Information Technology      IT
    College of Radiologic Technology  Radiologic Technology       RAD
    College of Arts and Science       BA Communication            BAC
    Tourism and Hospitality Mgmt      Tourism Management          TM
                                      Hospitality Management      HM
    College of Business Admin.        Human Resource Dev. Mgmt    HRDM
                                      Marketing Management        MM
    College of Nursing                Nursing                     N
    College of Allied Health          Physical Therapy            PT
                                      Occupational Therapy        OT
                                      Respiratory Therapy         RT
    any other program                 I, J, K ... (in the order the programs were created)

When one program has more than one section in the same year level and semester, a letter is added: CS1A, CS1B
(curriculum/management/commands/apply_section_codes.py).
"""
import re

# (keyword that must appear in the lower-cased program name, code) -- first match wins
KEYWORD_PREFIX = [
    ("information technology", "IT"),
    ("computer science", "CS"),
    ("radiologic", "RAD"),
    ("communication", "BAC"),
    ("tourism", "TM"),
    ("hospitality", "HM"),
    ("human resource", "HRDM"),
    ("marketing", "MM"),
    ("nursing", "N"),
    ("occupational therap", "OT"),
    ("respiratory", "RT"),
    ("physical therap", "PT"),
]
EXTRA_LETTERS = "IJKLQUVWXYZ"          # never a letter that starts one of the codes above (N, ...)


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
