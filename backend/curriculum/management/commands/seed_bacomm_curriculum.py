"""
Seeds the BA Communication curriculum transcribed from the UPHSL student residency
evaluation screenshots. Lecture/lab pairs stay separate rows (a code ending in
"L" with a matching lecture code is a lab subject, so the scheduler gives it a lab room).

Run with: python manage.py seed_bacomm_curriculum
"""
from django.core.management.base import BaseCommand
from ._curriculum_loader import load

CURRICULUM = [
    # --- 1st Year, 1st Sem ---
    ('ABC1101A', 'Introduction to Communication Media', 3, '1st Year', '1st Sem', 'major'),
    ('GE301', 'Physical Education 1', 2, '1st Year', '1st Sem', 'minor'),
    ('GE401', 'Filipino Christian Living 1', 2, '1st Year', '1st Sem', 'minor'),
    ('GE501', 'National Service Training Program/ROTC 1', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC101', 'Art Appreciation', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC104', 'Readings in Philippine History', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC106', 'Purposive Communication', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC109', 'Understanding the Self', 3, '1st Year', '1st Sem', 'minor'),
    # --- 1st Year, 2nd Sem ---
    ('ABC1202A', 'Introduction to Film', 3, '1st Year', '2nd Sem', 'major'),
    ('ABC1203', 'Communication Theory', 3, '1st Year', '2nd Sem', 'major'),
    ('ABC1204', 'Broadcasting Principles and Practices', 3, '1st Year', '2nd Sem', 'major'),
    ('GE302', 'Physical Education 2', 2, '1st Year', '2nd Sem', 'minor'),
    ('GE402', 'Filipino Christian Living 2', 2, '1st Year', '2nd Sem', 'minor'),
    ('GE502', 'National Service Training Program/ROTC 2', 3, '1st Year', '2nd Sem', 'minor'),
    ('GEC103', 'The Contemporary World', 3, '1st Year', '2nd Sem', 'minor'),
    ('GEC105', 'Mathematics in the Modern World', 3, '1st Year', '2nd Sem', 'minor'),
    # --- 2nd Year, 1st Sem ---
    ('ABC2105', 'Film Production LEC', 3, '2nd Year', '1st Sem', 'major'),
    ('ABC2105L', 'Film Production LAB', 2, '2nd Year', '1st Sem', 'major'),
    ('ABC2106', 'Risk, Disaster & Humanitarian Communication', 3, '2nd Year', '1st Sem', 'major'),
    ('ELEC1', 'Living in the IT Era', 3, '2nd Year', '1st Sem', 'minor'),
    ('GE303', 'Physical Education 3', 2, '2nd Year', '1st Sem', 'minor'),
    ('GE403', 'Filipino Christian Living 3', 2, '2nd Year', '1st Sem', 'minor'),
    ('GEC102', 'Ethics', 3, '2nd Year', '1st Sem', 'minor'),
    ('GEC107', 'Life and Works of Rizal', 3, '2nd Year', '1st Sem', 'minor'),
    ('GEC108', 'Science, Technology & Society', 3, '2nd Year', '1st Sem', 'minor'),
    # --- 2nd Year, 2nd Sem ---
    ('ABC2207A', 'Knowledge Management', 3, '2nd Year', '2nd Sem', 'major'),
    ('ABC2208', 'Psychology', 3, '2nd Year', '2nd Sem', 'major'),
    ('ABC2209', 'Journalism Principles and Practices', 3, '2nd Year', '2nd Sem', 'major'),
    ('ABC2210', 'Organizational Culture & Communication', 3, '2nd Year', '2nd Sem', 'major'),
    ('ABC2211', 'Communication Media Laws and Media Ethics', 3, '2nd Year', '2nd Sem', 'major'),
    ('ELEC3A', 'Environmental Science', 3, '2nd Year', '2nd Sem', 'minor'),
    ('GE304', 'Physical Education 4', 2, '2nd Year', '2nd Sem', 'minor'),
    ('GE404', 'Filipino Christian Living 4', 2, '2nd Year', '2nd Sem', 'minor'),
    # --- 3rd Year, 1st Sem ---
    ('ABC3112', 'Communication Research', 3, '3rd Year', '1st Sem', 'major'),
    ('ABC3113', 'Public Information Principles and Practices', 3, '3rd Year', '1st Sem', 'major'),
    ('ABC3114', 'Advertising Principles & Practices', 3, '3rd Year', '1st Sem', 'major'),
    ('ABC3115', 'Social Media Principles & Practices', 3, '3rd Year', '1st Sem', 'major'),
    ('ABC3116', 'Communication, Culture and Society', 3, '3rd Year', '1st Sem', 'major'),
    ('ABC3117', 'Development Communication', 3, '3rd Year', '1st Sem', 'major'),
    ('GE405', 'Filipino Christian Living 5', 2, '3rd Year', '1st Sem', 'minor'),
    # --- 3rd Year, 2nd Sem ---
    ('ABC32118', 'Integrated Marketing Communication', 3, '3rd Year', '2nd Sem', 'major'),
    ('ABC3219', 'Thesis 1', 3, '3rd Year', '2nd Sem', 'major'),
    ('ABC4220A', 'Performance Media', 3, '3rd Year', '2nd Sem', 'major'),
    ('ELEC2A', 'Gender and Society', 3, '3rd Year', '2nd Sem', 'minor'),
    ('GE406', 'Filipino Christian Living 6', 2, '3rd Year', '2nd Sem', 'minor'),
    ('GE602', 'World Literature', 3, '3rd Year', '2nd Sem', 'minor'),
    # --- 4th Year, 1st Sem ---
    ('ABC4121', 'Practicum in Communication 1', 3, '4th Year', '1st Sem', 'major'),
    ('ABC4121L', 'Practicum in Communication 1 L', 2, '4th Year', '1st Sem', 'major'),
    ('ABC4122', 'Communication Planning', 3, '4th Year', '1st Sem', 'major'),
    ('ABC4123', 'Thesis 2', 3, '4th Year', '1st Sem', 'major'),
    ('GE407', 'Filipino Christian Living 7', 2, '4th Year', '1st Sem', 'minor'),
    # --- 4th Year, 2nd Sem ---
    ('ABC4224', 'Communication Management', 3, '4th Year', '2nd Sem', 'major'),
    ('ABC4225', 'Practicum in Communication 2', 3, '4th Year', '2nd Sem', 'major'),
    ('ABC4225L', 'Practicum in Communication 2 L', 2, '4th Year', '2nd Sem', 'major'),
    ('ABC4226', 'Web Content Management', 3, '4th Year', '2nd Sem', 'major'),
    ('GE408', 'Filipino Christian Living 8', 2, '4th Year', '2nd Sem', 'minor'),
]


class Command(BaseCommand):
    help = "Seed the BA Communication curriculum."

    def add_arguments(self, parser):
        parser.add_argument("--department", default="College of Arts and Science", help="Department name (must match faculty department exactly).")

    def handle(self, *args, **options):
        load(self, "BA Communication", options["department"], CURRICULUM)
