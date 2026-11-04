"""
Seeds the actual BS Computer Science curriculum (College of Computer Studies)
transcribed from the UPHSL student residency evaluation screenshots.

Each row is (code, title, units, year_level, semester, classification).
Lecture/Lab pairs (e.g. CS1102 / CS1102L) are kept as SEPARATE Subject rows,
matching how the source system codes them, rather than merged into one row
with combined lec_units/lab_units -- this preserves the real codes as-is.
classification: "major" for CS-prefixed technical subjects (Dean-owned exams),
"minor" for GE/GEC gen-ed subjects (Registrar-owned exams).

Run with: python manage.py seed_bscs_curriculum
"""
from django.core.management.base import BaseCommand
from curriculum.models import Program, Subject
from engine.models import Section
from curriculum.section_codes import section_name

CURRICULUM = [
    # --- 1st Year, 1st Sem ---
    ("CS1101", "Introduction to Computing", 3.0, "1st Year", "1st Sem", "major"),
    ("CS1102", "Computer Programming 1 - Lec", 2.0, "1st Year", "1st Sem", "major"),
    ("CS1102L", "Computer Programming 1 - Lab", 1.0, "1st Year", "1st Sem", "major"),
    ("CS1103", "Fundamentals of Information Management - Lec", 2.0, "1st Year", "1st Sem", "major"),
    ("CS1103L", "Fundamentals of Information Management - Lab", 1.0, "1st Year", "1st Sem", "major"),
    ("GE201", "Filipino 1", 3.0, "1st Year", "1st Sem", "minor"),
    ("GE301", "Physical Education 1", 2.0, "1st Year", "1st Sem", "minor"),
    ("GE401", "Filipino Christian Living 1", 2.0, "1st Year", "1st Sem", "minor"),
    ("GE501", "National Service Training Program/ROTC 1", 3.0, "1st Year", "1st Sem", "minor"),
    ("GEC106", "Purposive Communication", 3.0, "1st Year", "1st Sem", "minor"),
    ("GEC109", "Understanding the Self", 3.0, "1st Year", "1st Sem", "minor"),

    # --- 1st Year, 2nd Sem ---
    ("CS1204", "Computer Programming 2 - Lec", 2.0, "1st Year", "2nd Sem", "major"),
    ("CS1204L", "Computer Programming 2 - Lab", 1.0, "1st Year", "2nd Sem", "major"),
    ("CS1205", "Data Structure and Algorithm - Lec", 2.0, "1st Year", "2nd Sem", "major"),
    ("CS1205L", "Data Structure and Algorithm - Lab", 1.0, "1st Year", "2nd Sem", "major"),
    ("CS1206", "Discrete Structure 1", 3.0, "1st Year", "2nd Sem", "major"),
    ("GE202", "Filipino 2", 3.0, "1st Year", "2nd Sem", "minor"),
    ("GE302", "Physical Education 2", 2.0, "1st Year", "2nd Sem", "minor"),
    ("GE402", "Filipino Christian Living 2", 2.0, "1st Year", "2nd Sem", "minor"),
    ("GE502", "National Service Training Program/ROTC 2", 3.0, "1st Year", "2nd Sem", "minor"),
    ("GEC104", "Readings in Philippine History", 3.0, "1st Year", "2nd Sem", "minor"),
    ("GEC105", "Mathematics in the Modern World", 3.0, "1st Year", "2nd Sem", "minor"),

    # --- 2nd Year, 1st Sem ---
    ("CS2107", "Applications Development and Emerging Technologies - Lec", 2.0, "2nd Year", "1st Sem", "major"),
    ("CS2107L", "Applications Development and Emerging Technologies - Lab", 1.0, "2nd Year", "1st Sem", "major"),
    ("CS2108", "Operating System", 3.0, "2nd Year", "1st Sem", "major"),
    ("CS2109", "Architecture and Organization", 3.0, "2nd Year", "1st Sem", "major"),
    ("CS2110", "Algorithms and Complexity - Lec", 2.0, "2nd Year", "1st Sem", "major"),
    ("CS2110L", "Algorithms and Complexity - Lab", 1.0, "2nd Year", "1st Sem", "major"),
    ("CS2111", "Fundamentals of Database - Lec", 2.0, "2nd Year", "1st Sem", "major"),
    ("CS2111L", "Fundamentals of Database - Lab", 1.0, "2nd Year", "1st Sem", "major"),
    ("GE203", "Filipino 3", 3.0, "2nd Year", "1st Sem", "minor"),
    ("GE303", "Physical Education 3", 2.0, "2nd Year", "1st Sem", "minor"),
    ("GE403", "Filipino Christian Living 3", 2.0, "2nd Year", "1st Sem", "minor"),
    ("GEC103", "The Contemporary World", 3.0, "2nd Year", "1st Sem", "minor"),

    # --- 2nd Year, 2nd Sem ---
    ("CS2212", "Software Engineering 1", 3.0, "2nd Year", "2nd Sem", "major"),
    ("CS2213", "Human Computer Interaction", 1.0, "2nd Year", "2nd Sem", "major"),
    ("CS2214", "Automata Theory and Formal Language", 3.0, "2nd Year", "2nd Sem", "major"),
    ("CS2215", "Discrete Structure 2", 3.0, "2nd Year", "2nd Sem", "major"),
    ("GE304", "Physical Education 4", 2.0, "2nd Year", "2nd Sem", "minor"),
    ("GE404", "Filipino Christian Living 4", 2.0, "2nd Year", "2nd Sem", "minor"),
    ("GEC102", "Ethics", 3.0, "2nd Year", "2nd Sem", "minor"),
    ("GEC107", "Life and Works of Rizal", 3.0, "2nd Year", "2nd Sem", "minor"),
    ("GEC108", "Science, Technology & Society", 3.0, "2nd Year", "2nd Sem", "minor"),

    # --- 3rd Year, 1st Sem ---
    ("CS3116", "Object Oriented Programming 1 - Lec", 2.0, "3rd Year", "1st Sem", "major"),
    ("CS3116L", "Object Oriented Programming 1 - Lab", 1.0, "3rd Year", "1st Sem", "major"),
    ("CS3117", "Software Engineering 2", 3.0, "3rd Year", "1st Sem", "major"),
    ("CS3118", "Information Assurance and Security", 2.0, "3rd Year", "1st Sem", "major"),
    ("CS3119", "Programming Languages - Lec", 2.0, "3rd Year", "1st Sem", "major"),
    ("CS3119L", "Programming Languages - Lab", 1.0, "3rd Year", "1st Sem", "major"),
    ("CS3120", "Parallel and Distributed Computing", 3.0, "3rd Year", "1st Sem", "major"),
    ("CS3121", "Embedded System - Lec", 2.0, "3rd Year", "1st Sem", "major"),
    ("CS3121L", "Embedded System - Lab", 1.0, "3rd Year", "1st Sem", "major"),
    ("CS3122", "Fundamentals of Accounting", 3.0, "3rd Year", "1st Sem", "major"),
    ("GE405", "Filipino Christian Living 5", 2.0, "3rd Year", "1st Sem", "minor"),
    ("GEC101", "Art Appreciation", 3.0, "3rd Year", "1st Sem", "minor"),

    # --- 3rd Year, 2nd Sem ---
    ("CS3223", "Networks and Communications - Lec", 2.0, "3rd Year", "2nd Sem", "major"),
    ("CS3223L", "Networks and Communications - Lab", 1.0, "3rd Year", "2nd Sem", "major"),
    ("CS3224", "Intelligent Systems - Lec", 2.0, "3rd Year", "2nd Sem", "major"),
    ("CS3224L", "Intelligent Systems - Lab", 1.0, "3rd Year", "2nd Sem", "major"),
    ("CS3225", "Graphics and Visual Computing - Lec", 2.0, "3rd Year", "2nd Sem", "major"),
    ("CS3225L", "Graphics and Visual Computing - Lab", 1.0, "3rd Year", "2nd Sem", "major"),
    ("CS3226", "Software Quality Assurance", 3.0, "3rd Year", "2nd Sem", "major"),
    ("CS3227", "Mobile Computing - Lec", 2.0, "3rd Year", "2nd Sem", "major"),
    ("CS3227L", "Mobile Computing - Lab", 1.0, "3rd Year", "2nd Sem", "major"),
    ("CS3228", "CS Thesis Writing 1", 3.0, "3rd Year", "2nd Sem", "major"),
    ("GE406", "Filipino Christian Living 6", 2.0, "3rd Year", "2nd Sem", "minor"),
    ("GE601", "Philippine Literature", 3.0, "3rd Year", "2nd Sem", "minor"),

    # --- 4th Year, 1st Sem ---
    ("CS4129", "Social Issues and Professional Practice", 3.0, "4th Year", "1st Sem", "major"),
    ("CS4130", "Object Oriented Programming 2 - Lec", 2.0, "4th Year", "1st Sem", "major"),
    ("CS4130L", "Object Oriented Programming 2 - Lab", 1.0, "4th Year", "1st Sem", "major"),
    ("CS4131", "Software Project Management and Deployment - Lec", 2.0, "4th Year", "1st Sem", "major"),
    ("CS4131L", "Software Project Management and Deployment - Lab", 1.0, "4th Year", "1st Sem", "major"),
    ("CS4132", "CS Thesis Writing 2", 3.0, "4th Year", "1st Sem", "major"),
    ("GE407", "Filipino Christian Living 7", 2.0, "4th Year", "1st Sem", "minor"),
    ("GE602", "World Literature", 3.0, "4th Year", "1st Sem", "minor"),

    # --- 4th Year, 2nd Sem ---
    ("CS4233", "Seminars and Tours", 3.0, "4th Year", "2nd Sem", "major"),
    ("CS4234", "On-the-Job Training (180 hrs)", 3.0, "4th Year", "2nd Sem", "major"),
    ("GE408", "Filipino Christian Living 8", 2.0, "4th Year", "2nd Sem", "minor"),
]


# Number of students per year level in Computer Science (given by the registrar).
CS_SIZES = {"1": 30, "2": 28, "3": 20, "4": 21}


class Command(BaseCommand):
    help = "Seed the real BS Computer Science curriculum (College of Computer Studies)."

    def handle(self, *args, **options):
        program, created = Program.objects.get_or_create(
            name="BS Computer Science", department="Computer Studies"
        )
        self.stdout.write(("Created" if created else "Using existing") + f" program: {program}")

        made, skipped = 0, 0
        for code, title, units, year_level, semester, classification in CURRICULUM:
            # Units go in lec_units for lecture-only/standalone rows, lab_units
            # for rows explicitly marked "- Lab", matching the source codes exactly.
            is_lab = title.strip().endswith("- Lab")
            lec_units = 0 if is_lab else int(units)
            lab_units = int(units) if is_lab else 0

            subj, was_created = Subject.objects.get_or_create(
                code=code, program=program,
                defaults={
                    "title": title,
                    "lec_units": lec_units,
                    "lab_units": lab_units,
                    "year_level": year_level,
                    "semester": semester,
                    "classification": classification,
                },
            )
            if was_created:
                made += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {made} subjects created, {skipped} already existed and were skipped.\n"
            f"Total in curriculum list: {len(CURRICULUM)}."
        ))

        # One section per year_level/semester combo actually present, so
        # there's something to attach class/exam schedules to. Named "A1",
        # "A2", "A3", "A4" (block letter + year number) instead of a bare
        # "A" for every year -- a plain "A" made the 1st-Sem and 2nd-Sem row
        # for the SAME year level look identical at a glance in the admin
        # list (Section.__str__ doesn't show semester), on top of all four
        # year levels sharing the same section letter.
        YEAR_NUMBER = {"1st Year": "1", "2nd Year": "2", "3rd Year": "3", "4th Year": "4"}
        combos = {(row[3], row[4]) for row in CURRICULUM}  # (year_level, semester)
        sections_made = 0
        for year_level, semester in combos:
            if Section.objects.filter(program=program, year_level=year_level, semester=semester).exists():
                continue
            Section.objects.create(
                name=section_name(program, year_level), program=program, year_level=year_level, semester=semester,
                student_count=CS_SIZES.get(YEAR_NUMBER.get(year_level, ""), 30),
            )
            was_created = True
            if was_created:
                sections_made += 1
        self.stdout.write(self.style.SUCCESS(f"{sections_made} sections created (e.g. 'A1' for 1st Year, 'A2' for 2nd Year, ...)."))
