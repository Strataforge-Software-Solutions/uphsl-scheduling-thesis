"""
Seeds two curricula transcribed from the UPHSL student residency evaluation sheets:

  College of Computer Studies (department "Computer Studies")
      BS Information Technology   (codes IT....)       section prefix A.b  (A.b1 ... A.b4)
  Allied Health (department "Allied Health")
      BS Physical Therapy         (codes PT.... / MOTPT....)   section prefix B (B1 ... B4)
      BS Occupational Therapy     (codes OT.... / MOTPT....)   section prefix B.b (B.b1 ... B.b4)

    python manage.py seed_it_pt_curricula                 # both
    python manage.py seed_it_pt_curricula --only IT       # or PT, or OT

Safe to re-run (existing subjects are kept).

Notes on how the sheets were turned into data
  * A code ending in L whose lecture code is in the same list is a lab subject (units go to
    lab_units, so the scheduler gives it a lab room). PT prints some lab codes that do not follow
    that pattern (PT2109LA, PT2210LA), so those are entered as (0, units) explicitly.
  * PT3229L (Research Implementation and Presentation) and PT3231L (Clinical Education / Intro to
    Clinics) are printed with an L but have no lecture partner; they are seeded as ordinary
    lecture-room subjects. Change them in Django admin > Subjects if they should use a lab.
  * IT uses the same Gen Ed codes as the BS Computer Science sheet (GE201, GE301, GEC106 ...), so
    Gen Ed classes can be shared between CS and IT. PT prints its own codes (EPP1B, EPP2A,
    ELEC1A, ELEC2A, MOTPTRT1102 ...); they are kept exactly as printed.
  * OT Fieldwork 1A / 1B (3 units each, "Introduction to Clinics") are seeded as ordinary lecture-room
    subjects; OT2208LA (lab) is entered as (0, 2) because its code does not follow the "L" pattern.
  * NOT seeded:
      - PT / OT "Summer" terms (1st Year Summer, 2nd Year Summer) -- the system schedules 1st Sem and
        2nd Sem only.
      - Off-campus training: IT4231 On-the-Job Training (486 hrs), PT4132 Internship 1 (15 units),
        PT4235 Internship 2 (15 units).
  * Student counts are demo figures (the sheets do not give class sizes); change them with
    python manage.py set_section_sizes ...  or in Django admin > Sections.
"""
from django.core.management.base import BaseCommand
from ._curriculum_loader import load

CS_DEPT = "Computer Studies"
AH_DEPT = "Allied Health"
Y1, Y2, Y3, Y4 = "1st Year", "2nd Year", "3rd Year", "4th Year"
S1, S2 = "1st Sem", "2nd Sem"
m, M = "minor", "major"

IT = [
    # ---- 1st Year, 1st Sem (25 units) ----
    ("GE201", "Filipino 1", 3, Y1, S1, m), ("GE301", "Physical Education 1", 2, Y1, S1, m),
    ("GE401", "Filipino Christian Living 1", 2, Y1, S1, m), ("GE501", "National Service Training Program/ROTC 1", 3, Y1, S1, m),
    ("GEC106", "Purposive Communication", 3, Y1, S1, m), ("GEC109", "Understanding the Self", 3, Y1, S1, m),
    ("IT1101", "Introduction to Computing", 3, Y1, S1, M),
    ("IT1102", "Computer Programming 1 - Lec", 2, Y1, S1, M), ("IT1102L", "Computer Programming 1 - Lab", 1, Y1, S1, M),
    ("IT1103", "Fundamentals of Information Management - Lec", 2, Y1, S1, M),
    ("IT1103L", "Fundamentals of Information Management - Lab", 1, Y1, S1, M),
    # ---- 1st Year, 2nd Sem (25) ----
    ("GE202", "Filipino 2", 3, Y1, S2, m), ("GE302", "Physical Education 2", 2, Y1, S2, m),
    ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m), ("GE502", "National Service Training Program/ROTC 2", 3, Y1, S2, m),
    ("GEC104", "Readings in Philippine History", 3, Y1, S2, m), ("GEC105", "Mathematics in the Modern World", 3, Y1, S2, m),
    ("IT1204", "Computer Programming 2 - Lec", 2, Y1, S2, M), ("IT1204L", "Computer Programming 2 - Lab", 1, Y1, S2, M),
    ("IT1205", "Data Structure and Algorithm - Lec", 2, Y1, S2, M), ("IT1205L", "Data Structure and Algorithm - Lab", 1, Y1, S2, M),
    ("IT1206", "Discrete Mathematics", 3, Y1, S2, M),
    # ---- 2nd Year, 1st Sem (22) ----
    ("GE203", "Filipino 3", 3, Y2, S1, m), ("GE303", "Physical Education 3", 2, Y2, S1, m),
    ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m), ("GEC103", "The Contemporary World", 3, Y2, S1, m),
    ("IT2107", "Applications Development and Emerging Technologies - Lec", 2, Y2, S1, M),
    ("IT2107L", "Applications Development and Emerging Technologies - Lab", 1, Y2, S1, M),
    ("IT2108", "Fundamentals of Database System - Lec", 2, Y2, S1, M), ("IT2108L", "Fundamentals of Database System - Lab", 1, Y2, S1, M),
    ("IT2109", "Object Oriented Programming - Lec", 2, Y2, S1, M), ("IT2109L", "Object Oriented Programming - Lab", 1, Y2, S1, M),
    ("IT2110", "Quantitative Methods", 3, Y2, S1, M),
    # ---- 2nd Year, 2nd Sem (25) ----
    ("GE304", "Physical Education 4", 2, Y2, S2, m), ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m),
    ("GEC102", "Ethics", 3, Y2, S2, m), ("GEC107", "Life and Works of Rizal", 3, Y2, S2, m),
    ("GEC108", "Science, Technology & Society", 3, Y2, S2, m),
    ("IT2211", "Networking 1 - Lec", 2, Y2, S2, M), ("IT2211L", "Networking 1 - Lab", 1, Y2, S2, M),
    ("IT2212", "Introduction to Human Computer Interaction - Lec", 2, Y2, S2, M),
    ("IT2212L", "Introduction to Human Computer Interaction - Lab", 1, Y2, S2, M),
    ("IT2213", "Web Systems and Technology", 3, Y2, S2, M),
    ("IT2214", "Integrative Programming and Technologies - Lec", 2, Y2, S2, M),
    ("IT2214L", "Integrative Programming and Technologies - Lab", 1, Y2, S2, M),
    # ---- 3rd Year, 1st Sem (23) ----
    ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m), ("GEC101", "Art Appreciation", 3, Y3, S1, m),
    ("IT3115", "Networking 2 - Lec", 2, Y3, S1, M), ("IT3115L", "Networking 2 - Lab", 1, Y3, S1, M),
    ("IT3116", "Information Assurance and Security 1", 3, Y3, S1, M),
    ("IT3117", "System Administration and Maintenance - Lec", 2, Y3, S1, M),
    ("IT3117L", "System Administration and Maintenance - Lab", 1, Y3, S1, M),
    ("IT3118", "Human Computer Interaction 2 - Lec", 2, Y3, S1, M), ("IT3118L", "Human Computer Interaction 2 - Lab", 1, Y3, S1, M),
    ("IT3119", "Web Enterprise", 3, Y3, S1, M),
    ("IT3120", "Web Design and Graphics - Lec", 2, Y3, S1, M), ("IT3120L", "Web Design and Graphics - Lab", 1, Y3, S1, M),
    # ---- 3rd Year, 2nd Sem (23) ----
    ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m), ("GE601", "Philippine Literature", 3, Y3, S2, m),
    ("IT3221", "System Integration and Architecture - Lec", 2, Y3, S2, M),
    ("IT3221L", "System Integration and Architecture - Lab", 1, Y3, S2, M),
    ("IT3222", "Platform Technologies - Lec", 2, Y3, S2, M), ("IT3222L", "Platform Technologies - Lab", 1, Y3, S2, M),
    ("IT3223", "Information Assurance and Security 2 - Lec", 2, Y3, S2, M),
    ("IT3223L", "Information Assurance and Security 2 - Lab", 1, Y3, S2, M),
    ("IT3224", "Capstone Project and Research 1", 3, Y3, S2, M),
    ("IT3225", "Web Development - Lec", 2, Y3, S2, M), ("IT3225L", "Web Development - Lab", 1, Y3, S2, M),
    ("IT3226", "Quality Assurance", 3, Y3, S2, M),
    # ---- 4th Year, 1st Sem (17) ----
    ("GE407", "Filipino Christian Living 7", 2, Y4, S1, m), ("GE602", "World Literature", 3, Y4, S1, m),
    ("IT4127", "Capstone Project and Research 2", 3, Y4, S1, M), ("IT4128", "Social and Professional Issues", 3, Y4, S1, M),
    ("IT4129", "Web Deployment and Management - Lec", 2, Y4, S1, M), ("IT4129L", "Web Deployment and Management - Lab", 1, Y4, S1, M),
    ("IT4130", "Web Server Administration - Lec", 2, Y4, S1, M), ("IT4130L", "Web Server Administration - Lab", 1, Y4, S1, M),
    # ---- 4th Year, 2nd Sem (11; IT4231 On-the-Job Training is off-campus and not seeded) ----
    ("GE408", "Filipino Christian Living 8", 2, Y4, S2, m), ("IT4232", "Seminars and Tours", 3, Y4, S2, M),
]

PT = [
    # ---- 1st Year, 1st Sem (25) ----
    ("EPP1B", "English Proficiency 1", 3, Y1, S1, m), ("GE401", "Filipino Christian Living 1", 2, Y1, S1, m),
    ("GE501", "National Service Training Program/ROTC 1", 3, Y1, S1, m), ("GEC104", "Readings in Philippine History", 3, Y1, S1, m),
    ("GEC105", "Mathematics in the Modern World", 3, Y1, S1, m), ("GEC109", "Understanding the Self", 3, Y1, S1, m),
    ("MOTPTRT1102", "Human Anatomy and Physiology", 3, Y1, S1, M),
    ("PATHFIT1", "Physical Activities Toward Health and Fitness 1", 2, Y1, S1, m),
    ("PT1101A", "Introduction to Physical Therapy", 3, Y1, S1, M),
    # ---- 1st Year, 2nd Sem (30) ----
    ("EPP2A", "English Proficiency 2", 3, Y1, S2, m), ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m),
    ("GE502", "National Service Training Program/ROTC 2", 3, Y1, S2, m), ("GEC101", "Art Appreciation", 3, Y1, S2, m),
    ("GEC102", "Ethics", 3, Y1, S2, m), ("GEC103", "The Contemporary World", 3, Y1, S2, m),
    ("GEC107", "Life and Works of Rizal", 3, Y1, S2, m), ("GEC108", "Science, Technology and Society", 3, Y1, S2, m),
    ("MOTPT1203", "Gross and Organ System Anatomy - Lec", 3, Y1, S2, M), ("MOTPT1203L", "Gross and Organ System Anatomy - Lab", 2, Y1, S2, M),
    ("PATHFIT2", "Physical Activities Toward Health and Fitness 2", 2, Y1, S2, m),
    # ---- 2nd Year, 1st Sem (27) ----
    ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m), ("GE602", "World Literature", 3, Y2, S1, m),
    ("GEC106", "Purposive Communication", 3, Y2, S1, m),
    ("MOTPT2106", "Applied Anatomy and Kinesiology - Lec", 3, Y2, S1, M), ("MOTPT2106L", "Applied Anatomy and Kinesiology - Lab", 2, Y2, S1, M),
    ("MOTPT2107", "Neurosciences for PT - Lec", 3, Y2, S1, M), ("MOTPT2107L", "Neurosciences for PT - Lab", 1, Y2, S1, M),
    ("MOTPT2108", "Physiology - Lec", 3, Y2, S1, M), ("MOTPT2108L", "Physiology - Lab", 2, Y2, S1, M),
    ("PATHFIT3", "Physical Activities Toward Health and Fitness 3", 2, Y2, S1, m),
    ("PT2109A", "Foundations and Techniques of Therapeutic Exercises - Lec", 2, Y2, S1, M),
    ("PT2109LA", "Foundations and Techniques of Therapeutic Exercises - Lab", (0, 1), Y2, S1, M),
    # ---- 2nd Year, 2nd Sem (29) ----
    ("ELEC1A", "Living in the IT Era - Lec", 2, Y2, S2, m), ("ELEC1AL", "Living in the IT Era - Lab", 1, Y2, S2, m),
    ("ELEC2A", "Gender and Society", 3, Y2, S2, m), ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m),
    ("MOTPT2211", "Psychiatric Foundation", 3, Y2, S2, M),
    ("MOTPT2212", "Physical and Electrotherapeutic Agents in Rehabilitation - Lec", 3, Y2, S2, M),
    ("MOTPT2212L", "Physical and Electrotherapeutic Agents in Rehabilitation - Lab", 2, Y2, S2, M),
    ("PATHFIT4", "Physical Activities Toward Health and Fitness 4", 2, Y2, S2, m),
    ("PT2210A", "Physical Therapy Examinations and Evaluation - Lec", 3, Y2, S2, M),
    ("PT2210LA", "Physical Therapy Examinations and Evaluation - Lab", (0, 2), Y2, S2, M),
    ("PT2213", "Wellness and Health Promotion in PT - Lec", 2, Y2, S2, M), ("PT2213L", "Wellness and Health Promotion in PT - Lab", 2, Y2, S2, M),
    ("PT2214", "Principles of Disease and Pathophysiology", 2, Y2, S2, M),
    # ---- 3rd Year, 1st Sem (27) ----
    ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m),
    ("MOTPT3118", "Assistive Technologies, Orthotics and Prosthetics - Lec", 3, Y3, S1, M),
    ("MOTPT3118L", "Assistive Technologies, Orthotics and Prosthetics - Lab", 1, Y3, S1, M),
    ("PT3116", "Musculoskeletal Physical Therapy - Lec", 3, Y3, S1, M), ("PT3116L", "Musculoskeletal Physical Therapy - Lab", 1, Y3, S1, M),
    ("PT3117", "Integumentary Physical Therapy - Lec", 2, Y3, S1, M), ("PT3117L", "Integumentary Physical Therapy - Lab", 1, Y3, S1, M),
    ("PT3119", "Specific Therapeutic Exercises - Lec", 2, Y3, S1, M), ("PT3119L", "Specific Therapeutic Exercises - Lab", 1, Y3, S1, M),
    ("PT3120", "Cardiopulmonary Physical Therapy - Lec", 2, Y3, S1, M), ("PT3120L", "Cardiopulmonary Physical Therapy - Lab", 1, Y3, S1, M),
    ("PT3121", "Organization and Administration in PT", 3, Y3, S1, M),
    ("PT3122", "Introduction to Research and Proposal Writing", 3, Y3, S1, M), ("PT3123", "Pharmacology", 2, Y3, S1, M),
    # ---- 3rd Year, 2nd Sem (24) ----
    ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m),
    ("PT3224", "Neurologic Physical Therapy - Lec", 3, Y3, S2, M), ("PT3224L", "Neurologic Physical Therapy - Lab", 1, Y3, S2, M),
    ("PT3225", "Pediatric Physical Therapy - Lec", 2, Y3, S2, M), ("PT3225L", "Pediatric Physical Therapy - Lab", 1, Y3, S2, M),
    ("PT3226", "Geriatric Physical Therapy - Lec", 2, Y3, S2, M), ("PT3226L", "Geriatric Physical Therapy - Lab", 1, Y3, S2, M),
    ("PT3227", "Industrial Rehabilitation", 2, Y3, S2, M),
    ("PT3228", "Therapeutic Exercises for Motor Control - Lec", 2, Y3, S2, M),
    ("PT3228L", "Therapeutic Exercises for Motor Control - Lab", 1, Y3, S2, M),
    ("PT3229L", "Research Implementation and Presentation", (2, 0), Y3, S2, M),
    ("PT3230", "Professional Ethics in Physical Therapy", 3, Y3, S2, M),
    ("PT3231L", "Clinical Education (Intro to Clinics)", (2, 0), Y3, S2, M),
    # ---- 4th Year, 1st Sem (PT4132 Internship 1 is off-campus; not seeded) ----
    ("GE407", "Filipino Christian Living 7", 2, Y4, S1, m),
    ("PT4133", "Clinical Conference 1", 3, Y4, S1, M), ("PT4134", "Evidence Based Practice 1", 3, Y4, S1, M),
    # ---- 4th Year, 2nd Sem (PT4235 Internship 2 is off-campus; not seeded) ----
    ("GE408", "Filipino Christian Living 8", 2, Y4, S2, m),
    ("PT4236", "Clinical Conference 2", 3, Y4, S2, M), ("PT4237", "Evidence Based Practice 2", 3, Y4, S2, M),
]

OT = [
    # ---- 1st Year, 1st Sem (25) ----
    ("EPP1B", "English Proficiency 1", 3, Y1, S1, m), ("GE401", "Filipino Christian Living 1", 2, Y1, S1, m),
    ("GE501", "National Service Training Program/ROTC 1", 3, Y1, S1, m), ("GEC104", "Readings in Philippine History", 3, Y1, S1, m),
    ("GEC105", "Mathematics in the Modern World", 3, Y1, S1, m), ("GEC109", "Understanding the Self", 3, Y1, S1, m),
    ("MOTPTRT1102", "Human Anatomy and Physiology", 3, Y1, S1, M), ("OT1101", "Foundations of Occupational Therapy 1", 3, Y1, S1, M),
    ("PATHFIT1", "Physical Activities Toward Health and Fitness 1", 2, Y1, S1, m),
    # ---- 1st Year, 2nd Sem (30) ----
    ("EPP2A", "English Proficiency 2", 3, Y1, S2, m), ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m),
    ("GE502", "National Service Training Program/ROTC 2", 3, Y1, S2, m), ("GEC101", "Art Appreciation", 3, Y1, S2, m),
    ("GEC102", "Ethics", 3, Y1, S2, m), ("GEC103", "The Contemporary World", 3, Y1, S2, m),
    ("GEC107", "Life and Works of Rizal", 3, Y1, S2, m), ("GEC108", "Science, Technology and Society", 3, Y1, S2, m),
    ("MOTPT1203", "Gross and Organ System Anatomy - Lec", 3, Y1, S2, M), ("MOTPT1203L", "Gross and Organ System Anatomy - Lab", 2, Y1, S2, M),
    ("PATHFIT2", "Physical Activities Toward Health and Fitness 2", 2, Y1, S2, m),
    # ---- 2nd Year, 1st Sem (29) ----
    ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m), ("GE602", "World Literature", 3, Y2, S1, m),
    ("GEC106", "Purposive Communication", 3, Y2, S1, m),
    ("MOTPT2106", "Applied Anatomy and Kinesiology - Lec", 3, Y2, S1, M), ("MOTPT2106L", "Applied Anatomy and Kinesiology - Lab", 2, Y2, S1, M),
    ("MOTPT2107", "Neurosciences for PT - Lec", 3, Y2, S1, M), ("MOTPT2107L", "Neurosciences for PT - Lab", 1, Y2, S1, M),
    ("MOTPT2108", "Physiology - Lec", 3, Y2, S1, M), ("MOTPT2108L", "Physiology - Lab", 2, Y2, S1, M),
    ("OT2103", "Development of Human Occupations 1 - Lec", 3, Y2, S1, M), ("OT2103L", "Development of Human Occupations 1 - Lab", 2, Y2, S1, M),
    ("PATHFIT3", "Physical Activities Toward Health and Fitness 3", 2, Y2, S1, m),
    # ---- 2nd Year, 2nd Sem (29) ----
    ("ELEC1A", "Living in the IT Era - Lec", 2, Y2, S2, m), ("ELEC1AL", "Living in the IT Era - Lab", 1, Y2, S2, m),
    ("ELEC2A", "Gender and Society", 3, Y2, S2, m), ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m),
    ("MOTPT2211", "Psychiatric Foundation", 3, Y2, S2, M), ("MOTPT3224", "Neurologic Conditions", 3, Y2, S2, M),
    ("OT2208", "Development of Human Occupations 2 - Lec", 3, Y2, S2, M),
    ("OT2208LA", "Development of Human Occupations 2 - Lab", (0, 2), Y2, S2, M),
    ("OT2210", "OT in Mental Health 1 - Lec", 3, Y2, S2, M), ("OT2210L", "OT in Mental Health 1 - Lab", 1, Y2, S2, M),
    ("OT2212", "OT in Neurological Rehabilitation 1 - Lec", 3, Y2, S2, M), ("OT2212L", "OT in Neurological Rehabilitation 1 - Lab", 1, Y2, S2, M),
    ("PATHFIT4", "Physical Activities Toward Health and Fitness 4", 2, Y2, S2, m),
    # ---- 3rd Year, 1st Sem (27) ----
    ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m),
    ("MOTPT3118", "Assistive Technologies, Orthotics and Prosthetics - Lec", 3, Y3, S1, M),
    ("MOTPT3118L", "Assistive Technologies, Orthotics and Prosthetics - Lab", 1, Y3, S1, M),
    ("OT3114", "OT in Mental Health 2 - Lec", 3, Y3, S1, M), ("OT3114L", "OT in Mental Health 2 - Lab", 1, Y3, S1, M),
    ("OT3115", "OT in Neurological Rehabilitation 2 - Lec", 3, Y3, S1, M), ("OT3115L", "OT in Neurological Rehabilitation 2 - Lab", 1, Y3, S1, M),
    ("OT3116", "Conditions in Musculoskeletal and Cardio-Pulmonary Rehabilitation", 3, Y3, S1, M),
    ("OT3117", "OT in Musculoskeletal and Cardio-Pulmonary Rehabilitation 1 - Lec", 3, Y3, S1, M),
    ("OT3117L", "OT in Musculoskeletal and Cardio-Pulmonary Rehabilitation 1 - Lab", 1, Y3, S1, M),
    ("OT3119", "Research 1 (Research Proposal)", 3, Y3, S1, M),
    ("OT3120", "Fieldwork 1A (Introduction to Clinics in Psychosocial Dysfunction)", 3, Y3, S1, M),
    # ---- 3rd Year, 2nd Sem (26) ----
    ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m),
    ("MOTPT2212", "Physical and Electrotherapeutic Agents in Rehabilitation - Lec", 3, Y3, S2, M),
    ("MOTPT2212L", "Physical and Electrotherapeutic Agents in Rehabilitation - Lab", 2, Y3, S2, M),
    ("OT3221", "OT in Musculoskeletal and Cardio-Pulmonary Rehabilitation 2 - Lec", 3, Y3, S2, M),
    ("OT3221L", "OT in Musculoskeletal and Cardio-Pulmonary Rehabilitation 2 - Lab", 1, Y3, S2, M),
    ("OT3223", "Leadership and Management in OT", 3, Y3, S2, M),
    ("OT3224", "OT in Pediatric Rehabilitation - Lec", 3, Y3, S2, M), ("OT3224L", "OT in Pediatric Rehabilitation - Lab", 1, Y3, S2, M),
    ("OT3225", "Fieldwork 1B (Introduction to Clinics in Physical Dysfunction)", 3, Y3, S2, M),
    ("OT3226", "Research 2 (Colloquium)", 2, Y3, S2, M), ("OT3227", "Professional Development and Ethics", 3, Y3, S2, M),
    # ---- 4th Year (OT4127 / OT4230 Fieldwork 2A / 2B, 12 units each, are off-campus; not seeded) ----
    ("GE407", "Filipino Christian Living 7", 2, Y4, S1, m), ("OT4128", "Research 3 (Paper Presentation and/or Publication)", 2, Y4, S1, M),
    ("OT4129", "OT Seminar 1", 3, Y4, S1, M),
    ("GE408", "Filipino Christian Living 8", 2, Y4, S2, m), ("OT4231", "Research 4 (Final Defense)", 2, Y4, S2, M),
    ("OT4232", "OT Seminar 2", 3, Y4, S2, M),
]

PROGRAMS = {
    "IT": ("BS Information Technology", CS_DEPT, IT, {1: 35, 2: 30, 3: 25, 4: 20}),
    "PT": ("BS Physical Therapy", AH_DEPT, PT, {1: 40, 2: 35, 3: 30, 4: 25}),
    "OT": ("BS Occupational Therapy", AH_DEPT, OT, {1: 30, 2: 28, 3: 25, 4: 20}),
}
NOTES = {
    "IT": "Not seeded (off-campus): IT4231 On-the-Job Training (486 hrs).",
    "PT": "Not seeded: the 1st/2nd Year Summer terms and PT4132 / PT4235 Internship 1 and 2 (off-campus).",
    "OT": "Not seeded: the 1st/2nd Year Summer terms and OT4127 / OT4230 Fieldwork 2A / 2B (12 units each, off-campus).",
}


class Command(BaseCommand):
    help = "Seed the BS Information Technology, BS Physical Therapy and BS Occupational Therapy curricula."

    def add_arguments(self, parser):
        parser.add_argument("--only", default="", help="IT, PT or OT (default: all three).")

    def handle(self, *args, **o):
        want = [x.strip().upper() for x in o["only"].split(",") if x.strip()] or list(PROGRAMS)
        for key in want:
            if key not in PROGRAMS:
                self.stdout.write(self.style.ERROR(f"Unknown key {key!r}; use IT, PT or OT."))
                continue
            name, dept, rows, sizes = PROGRAMS[key]
            self.stdout.write(f"\n== {name} ==")
            load(self, name, dept, rows, skipped_note=NOTES[key], sizes=sizes, fix_department=True)
