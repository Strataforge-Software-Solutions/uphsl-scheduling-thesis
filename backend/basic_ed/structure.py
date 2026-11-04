"""
Academic-term structure of the basic-education levels (ONE place, used by the curriculum import, validation,
schedule generation, calendar, dashboards and PDFs):

  * Junior High School (Grades 7-10) ..... 3 terms per school year   (the old 1st-4th quarters are retired)
  * Senior High, Grade 11 ................. 3 terms per school year   (core subjects stay the same all year;
                                            strand electives may change every term)
  * Senior High, Grade 12 ................. 2 semesters per school year (unchanged)

`grading_period` stored on curriculum lines and schedule runs is the NUMBER within that structure
(term 1-3, or semester 1-2); 0 on a curriculum line still means "the whole school year".
"""


def structure(level, grade=None):
    """(kind, count) for a grade: ("term", 3) or ("semester", 2)."""
    if level == "SHS" and grade is not None and int(grade) == 12:
        return "semester", 2
    return "term", 3


def label(level, grade=None):
    return structure(level, grade)[0].capitalize()


def period_name(level, grade, number):
    return f"{label(level, grade)} {number}"


def max_period(level, grade=None):
    """Largest valid period number for a grade (for SHS with no grade given: the largest of its grades)."""
    if level == "SHS" and grade is None:
        return max(structure(level, 11)[1], structure(level, 12)[1])
    return structure(level, grade)[1]


def weeks_per_period(level, grade, number):
    """Teaching weeks used to sanity-check curriculum hours."""
    return 20 if structure(level, grade)[0] == "semester" else 13


def as_dict(level, grades):
    return {str(g): {"kind": structure(level, g)[0], "count": structure(level, g)[1], "label": label(level, g)} for g in grades}
