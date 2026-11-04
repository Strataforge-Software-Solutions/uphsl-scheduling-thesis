"""
Seeds the BS Radiologic Technology curriculum transcribed from the UPHSL student residency
evaluation screenshots. Lecture/lab pairs stay separate rows (a code ending in
"L" with a matching lecture code is a lab subject, so the scheduler gives it a lab room).
Clinical Education 1 and 2 (RAD4130 / RAD4232, 18 units each, 1,056 hrs hospital internship) are
NOT seeded: 18 units would ask the scheduler for 18 class periods a week. They happen off campus.

Run with: python manage.py seed_radtech_curriculum
"""
from django.core.management.base import BaseCommand
from ._curriculum_loader import load

CURRICULUM = [
    # --- 1st Year, 1st Sem ---
    ('ELEC4A', 'English Proficiency 1', 3, '1st Year', '1st Sem', 'minor'),
    ('GE401', 'Filipino Christian Living 1', 2, '1st Year', '1st Sem', 'minor'),
    ('GE501A', 'NSTP/ROTC 1', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC103', 'The Contemporary World', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC104', 'Readings in Philippine History', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC105', 'Mathematics in the Modern World', 3, '1st Year', '1st Sem', 'minor'),
    ('GEC109', 'Understanding the Self', 3, '1st Year', '1st Sem', 'minor'),
    ('PATHFIT1', 'Physical Activities Toward Health and Fitness 1', 2, '1st Year', '1st Sem', 'minor'),
    ('RAD1101', 'Introduction to Radiologic Technology and Health Care', 3, '1st Year', '1st Sem', 'major'),
    # --- 1st Year, 2nd Sem ---
    ('ELEC1A', 'Living in the IT Era (lec)', 2, '1st Year', '2nd Sem', 'minor'),
    ('ELEC1AL', 'Living in the IT Era (lab)', 1, '1st Year', '2nd Sem', 'minor'),
    ('ELEC2A', 'Gender and Society', 3, '1st Year', '2nd Sem', 'minor'),
    ('GE402', 'Filipino Christian Living 2', 2, '1st Year', '2nd Sem', 'minor'),
    ('GE502A', 'NSTP/ROTC 2', 3, '1st Year', '2nd Sem', 'minor'),
    ('GE602', 'World Literature', 3, '1st Year', '2nd Sem', 'minor'),
    ('GEC101', 'Art Appreciation', 3, '1st Year', '2nd Sem', 'minor'),
    ('GEC102', 'Ethics', 3, '1st Year', '2nd Sem', 'minor'),
    ('GEC108', 'Science, Technology & Society', 3, '1st Year', '2nd Sem', 'minor'),
    ('PATHFIT2', 'Physical Activities Toward Health and Fitness 2', 2, '1st Year', '2nd Sem', 'minor'),
    ('RAD1202', 'Medical Terminology', 3, '1st Year', '2nd Sem', 'major'),
    # --- 2nd Year, 1st Sem ---
    ('ANA1001', 'Human Anatomy and Physiology (lec)', 3, '2nd Year', '1st Sem', 'major'),
    ('ANA1001L', 'Human Anatomy and Physiology (lab)', 2, '2nd Year', '1st Sem', 'major'),
    ('ELEC3A', 'Environmental Science', 3, '2nd Year', '1st Sem', 'minor'),
    ('GE403', 'Filipino Christian Living 3', 2, '2nd Year', '1st Sem', 'minor'),
    ('GEC106', 'Purposive Communication', 3, '2nd Year', '1st Sem', 'minor'),
    ('GEC107', 'Life and Works of Rizal', 3, '2nd Year', '1st Sem', 'minor'),
    ('PATHFIT3', 'Physical Activities Toward Health and Fitness 3', 2, '2nd Year', '1st Sem', 'minor'),
    ('RAD2103', 'Imaging Science and Informatics', 3, '2nd Year', '1st Sem', 'major'),
    ('RAD2104', 'Radiation Production and Characteristics-Lec', 2, '2nd Year', '1st Sem', 'major'),
    ('RAD2104L', 'Radiation Production and Characteristics-Lab', 1, '2nd Year', '1st Sem', 'major'),
    ('RAD2105', 'Principles of Imaging-Lec', 2, '2nd Year', '1st Sem', 'major'),
    ('RAD2105L', 'Principles of Imaging-Lab', 1, '2nd Year', '1st Sem', 'major'),
    ('RAD2106', 'Professional Ethics, Jurisprudence and Cultural Sensitivity', 3, '2nd Year', '1st Sem', 'major'),
    # --- 2nd Year, 2nd Sem ---
    ('ELEC5', 'English Proficiency 2', 3, '2nd Year', '2nd Sem', 'minor'),
    ('GE100', 'Statistics', 3, '2nd Year', '2nd Sem', 'minor'),
    ('GE404', 'Filipino Christian Living 4', 2, '2nd Year', '2nd Sem', 'minor'),
    ('PATHFIT4', 'Physical Activities Toward Health and Fitness 4', 2, '2nd Year', '2nd Sem', 'minor'),
    ('RAD2207', 'Radiobiology', 2, '2nd Year', '2nd Sem', 'major'),
    ('RAD2208', 'Radiographic Anatomy and Physiology-Lec', 3, '2nd Year', '2nd Sem', 'major'),
    ('RAD2208L', 'Radiographic Anatomy and Physiology-Lab', 1, '2nd Year', '2nd Sem', 'major'),
    ('RAD2209', 'Patient Care and Management-Lec', 2, '2nd Year', '2nd Sem', 'major'),
    ('RAD2209L', 'Patient Care and Management-Lab', 1, '2nd Year', '2nd Sem', 'major'),
    ('RAD2210', 'Pharmacology and Venipuncture-Lec', 2, '2nd Year', '2nd Sem', 'major'),
    ('RAD2210L', 'Pharmacology and Venipuncture-Lab', 1, '2nd Year', '2nd Sem', 'major'),
    ('RAD2211', 'Imaging Equipment and Maintenance', 2, '2nd Year', '2nd Sem', 'major'),
    ('RAD2212', 'Film-Screen Image Acquisition, Processing and Image Analysis-Lec', 2, '2nd Year', '2nd Sem', 'major'),
    ('RAD2212L', 'Film-Screen Image Acquisition, Processing and Image Analysis-Lab', 1, '2nd Year', '2nd Sem', 'major'),
    ('RAD2213', 'Computed and Digital Radiography', 3, '2nd Year', '2nd Sem', 'major'),
    # --- 3rd Year, 1st Sem ---
    ('GE405', 'Filipino Christian Living 5', 2, '3rd Year', '1st Sem', 'minor'),
    ('RAD3114', 'Radiographic Positioning and Radiological Procedures 1-Lec', 3, '3rd Year', '1st Sem', 'major'),
    ('RAD3114L', 'Radiographic Positioning and Radiological Procedures 1-Lab', 1, '3rd Year', '1st Sem', 'major'),
    ('RAD3115', 'Radiologic Contrast Examination-Lec', 2, '3rd Year', '1st Sem', 'major'),
    ('RAD3115L', 'Radiologic Contrast Examination-Lab', 1, '3rd Year', '1st Sem', 'major'),
    ('RAD3116', 'Ultrasonography', 3, '3rd Year', '1st Sem', 'major'),
    ('RAD3117', 'Radiation Protection', 2, '3rd Year', '1st Sem', 'major'),
    ('RAD3118', 'Radiologic Pathology', 3, '3rd Year', '1st Sem', 'major'),
    ('RAD3119', 'Quality Assurance and Quality Control-Lec', 2, '3rd Year', '1st Sem', 'major'),
    ('RAD3119L', 'Quality Assurance and Quality Control-Lab', 1, '3rd Year', '1st Sem', 'major'),
    ('RAD3120', 'Administration, Leadership and Entrepreneurship', 3, '3rd Year', '1st Sem', 'major'),
    ('RAD3121', 'Introduction to Research', 3, '3rd Year', '1st Sem', 'major'),
    # --- 3rd Year, 2nd Sem ---
    ('GE406', 'Filipino Christian Living 6', 2, '3rd Year', '2nd Sem', 'minor'),
    ('RAD3222', 'Radiographic Positioning and Radiological Procedures 2-Lec', 3, '3rd Year', '2nd Sem', 'major'),
    ('RAD3222L', 'Radiographic Positioning and Radiological Procedures 2-Lab', 1, '3rd Year', '2nd Sem', 'major'),
    ('RAD3223', 'Computed Tomography', 3, '3rd Year', '2nd Sem', 'major'),
    ('RAD3224', 'Magnetic Resonance Imaging', 3, '3rd Year', '2nd Sem', 'major'),
    ('RAD3225', 'Mammography', 2, '3rd Year', '2nd Sem', 'major'),
    ('RAD3226', 'Interventional Radiology', 3, '3rd Year', '2nd Sem', 'major'),
    ('RAD3227', 'Radiotherapy', 3, '3rd Year', '2nd Sem', 'major'),
    ('RAD3228', 'Nuclear Medicine', 3, '3rd Year', '2nd Sem', 'major'),
    ('RAD3229', 'Research Writing', 3, '3rd Year', '2nd Sem', 'major'),
    # --- 4th Year, 1st Sem ---
    ('GE407', 'Filipino Christian Living 7', 2, '4th Year', '1st Sem', 'minor'),
    ('RAD4131', 'Course Audit 1', 3, '4th Year', '1st Sem', 'major'),
    # --- 4th Year, 2nd Sem ---
    ('GE408', 'Filipino Christian Living 8', 2, '4th Year', '2nd Sem', 'minor'),
    ('RAD4233', 'Course Audit 2', 3, '4th Year', '2nd Sem', 'major'),
]


class Command(BaseCommand):
    help = "Seed the BS Radiologic Technology curriculum."

    def add_arguments(self, parser):
        parser.add_argument("--department", default="Radiologic Technology", help="Department name (must match faculty department exactly).")

    def handle(self, *args, **options):
        load(self, "BS Radiologic Technology", options["department"], CURRICULUM,
             "Not seeded: RAD4130 and RAD4232 (Clinical Education, 18 units, hospital internship) - off campus, not schedulable.")
