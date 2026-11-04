"""
Seeds four AY 2024-2025 curricula transcribed from the printed curriculum sheets:

  College of Business Administration
      BSBA Major in Marketing Management        (codes MM....)   section letter E
      BSBA Major in Human Resource Development Management (HRD....)   section letter F
  College of International Hospitality Management
      BS Hospitality Management                 (HM....)   section letter G
      BS Tourism Management                     (TM....)   section letter H

    python manage.py seed_cba_cihm_curricula                # all four
    python manage.py seed_cba_cihm_curricula --only HM,TM   # some of them

Safe to re-run (existing subjects are kept).

How the sheets were turned into data
  * Hospitality / Tourism list Lecture hrs + Lab hrs + Units. Lecture hours = lecture units;
    lab hours / 3 = lab units (1 lab unit = one 3-hour block in a lab/kitchen room), e.g.
    Bread and Pastry (1 lec, 6 lab hrs) = 1 lecture unit + 2 lab units.
  * "Living in the IT Era" is 2 lecture units + a 1-unit lab; stored like the Business sheets
    do, as ELEC1 + ELEC1L (HM/TM print it as one row with 2 lec / 3 lab hrs).
  * Codes that the sheets print inconsistently are unified so the same Gen Ed subject has
    the SAME code in every program (that is what lets minor classes be shared between
    departments):  English Proficiency 1/2 = EPP1/EPP2 (HM prints ELEC 1 / ELEC 5,
    TM prints ELEC 4 / ELEC 5), Environmental Science = ELEC3 (TM prints ELEC4),
    Gender and Society = ELEC2, PATH-FIT n = PATHFITn.
  * NOT seeded (off-campus, cannot be given a room): Internship (600 hrs) MM4226 / HRD4227,
    Practicum 1 (300 hrs) HM2215 / TM2215, Practicum 2 (600 hrs) HM4232 / TM4232.
    Printed codes with typos are kept as printed (HM3230, HM3231 in 4th year; TM327).
  * Student counts are rough demo figures from the GTI class program; change them with
    python manage.py set_section_sizes ...   or in Django admin > Sections.
"""
from django.core.management.base import BaseCommand
from ._curriculum_loader import load

CBA = "College of Business Administration"
CIHM = "College of International Hospitality Management"
Y1, Y2, Y3, Y4 = "1st Year", "2nd Year", "3rd Year", "4th Year"
S1, S2 = "1st Sem", "2nd Sem"
m, M = "minor", "major"

# ---------------- Gen Ed rows shared by the Business sheets ----------------
def business(prefix, majors):
    """The Gen Ed part is identical in MM and HRD; `majors` adds the program's own rows."""
    g = [
        ("EPP1", "English Proficiency 1", 3, Y1, S1, m), ("PATHFIT1", "Physical Education 1", 2, Y1, S1, m),
        ("GE401", "Filipino Christian Living 1", 2, Y1, S1, m), ("GE501", "National Service Training Program 1/ROTC 1", 3, Y1, S1, m),
        ("GEC109", "Understanding the Self", 3, Y1, S1, m),
        ("ELEC1", "Living in the IT Era", 2, Y1, S2, m), ("ELEC1L", "Living in the IT Era - Lab", 1, Y1, S2, m),
        ("EPP2", "English Proficiency 2", 3, Y1, S2, m), ("PATHFIT2", "Physical Education 2", 2, Y1, S2, m),
        ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m), ("GE502", "National Service Training Program 2/ROTC 2", 3, Y1, S2, m),
        ("GEC104", "Readings in the Philippine History", 3, Y1, S2, m), ("GEC105", "Mathematics in the Modern World", 3, Y1, S2, m),
        ("PATHFIT3", "Physical Education 3", 2, Y2, S1, m), ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m),
        ("GE602", "World Literature", 3, Y2, S1, m), ("GEC101", "Art Appreciation", 3, Y2, S1, m),
        ("GEC103", "The Contemporary World", 3, Y2, S1, m), ("GEC106", "Purposive Communication", 3, Y2, S1, m),
        ("ELEC2", "Gender and Society", 3, Y2, S2, m), ("PATHFIT4", "Physical Education 4", 2, Y2, S2, m),
        ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m), ("GEC107", "Life and Works of Rizal", 3, Y2, S2, m),
        ("GEC108", "Science, Technology and Society", 3, Y2, S2, m),
        ("ELEC3", "Environmental Science", 3, Y3, S1, m), ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m),
        ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m), ("GEC102", "Ethics", 3, Y3, S2, m),
        ("GE407", "Filipino Christian Living 7", 2, Y4, S1, m), ("GE408", "Filipino Christian Living 8", 2, Y4, S1, m),
    ]
    return g + [(prefix + code, title, units, y, s, M) for code, title, units, y, s in majors]


MM = business("MM", [
    ("1101", "Basic Microeconomics", 3, Y1, S1), ("1102", "Professional Salesmanship", 3, Y1, S1),
    ("1203", "Marketing Management", 3, Y1, S2), ("1204", "Consumer Behavior", 3, Y1, S2),
    ("2105", "E-commerce and Internet Marketing", 3, Y2, S1), ("2106", "Managerial Accounting", 3, Y2, S1),
    ("2207", "Business Law (Obligations & Contracts)", 3, Y2, S2), ("2208", "Taxation (Income Taxation)", 3, Y2, S2),
    ("2209", "Distribution Management", 3, Y2, S2),
    ("3110", "Strategic Management", 3, Y3, S1), ("3111", "Good Governance and Social Responsibility", 3, Y3, S1),
    ("3112", "Human Resource Management", 3, Y3, S1), ("3113", "International Business and Trade", 3, Y3, S1),
    ("3114", "Marketing Research", 3, Y3, S1), ("3115", "Advertising", 3, Y3, S1),
    ("3216", "Business Research", 3, Y3, S2), ("3217", "Operations Management (TQM)", 3, Y3, S2),
    ("3218", "Product Management", 3, Y3, S2), ("3219", "Retail Management", 3, Y3, S2),
    ("3220", "International Marketing", 3, Y3, S2),
    ("4121", "Pricing Strategy", 3, Y4, S1), ("4122", "Entrepreneurial Management", 3, Y4, S1),
    ("4123", "Strategic Marketing Management", 3, Y4, S1), ("4124", "Thesis or Feasibility Study", 3, Y4, S1),
    ("4225", "Personal Finance", 3, Y4, S2),
])

HRD = business("HRD", [
    ("1101", "Management", 3, Y1, S1), ("1102", "Administrative and Office Management", 3, Y1, S1),
    ("1203", "Marketing Management", 3, Y1, S2), ("1204", "Basic Microeconomics", 3, Y1, S2),
    ("2105", "Global/International Trade", 3, Y2, S1), ("2106", "Managerial Accounting", 3, Y2, S1),
    ("2207", "Business Law (Obligations & Contracts)", 3, Y2, S2), ("2208", "Taxation (Income Taxation)", 3, Y2, S2),
    ("2209", "Labor Law and Legislation", 3, Y2, S2), ("2210", "Recruitment and Selection", 3, Y2, S2),
    ("3111", "Strategic Management", 3, Y3, S1), ("3112", "Good Governance and Social Responsibility", 3, Y3, S1),
    ("3113", "Human Resource Management", 3, Y3, S1), ("3114", "International Business and Trade", 3, Y3, S1),
    ("3115", "Training and Development", 3, Y3, S1), ("3116", "Compensation Administration", 3, Y3, S1),
    ("3217", "Business Research", 3, Y3, S2), ("3218", "Operations Management (TQM)", 3, Y3, S2),
    ("3219", "Labor Relations and Negotiations", 3, Y3, S2), ("3220", "Special Topics in Human Resources", 3, Y3, S2),
    ("3221", "Logistics Management", 3, Y3, S2),
    ("4122", "Organizational Development", 3, Y4, S1), ("4123", "Environmental Management System", 3, Y4, S1),
    ("4124", "Project Management", 3, Y4, S1), ("4125", "Thesis or Feasibility Study", 3, Y4, S1),
    ("4226", "Personal Finance", 3, Y4, S2),
])

# ---------------- Hospitality (lecture units, lab units) ----------------
HM = [
    ("GEC105", "Mathematics in the Modern World", 3, Y1, S1, m), ("HM1101", "Philippine Culture, Tourism & Geography", 3, Y1, S1, M),
    ("HM1102", "Risk Management as Applied to Safety, Security, Sanitation", 3, Y1, S1, M),
    ("HM1103", "Macro Perspective of Tourism and Hospitality", 3, Y1, S1, M),
    ("EPP1", "English Proficiency 1: Intensive Grammar", 3, Y1, S1, m), ("GE401", "Filipino Christian Living 1: The Perpetualite", 2, Y1, S1, m),
    ("PATHFIT1", "Physical Activities Toward Health and Fitness 1", 2, Y1, S1, m), ("GE501", "NSTP / ROTC 1", 3, Y1, S1, m),
    ("HM1204", "Quality Service Management in Tourism & Hospitality", 3, Y1, S2, M),
    ("HM1205", "Micro Perspective of Tourism & Hospitality", 3, Y1, S2, M),
    ("HM1206", "Kitchen Essential & Basic Food Preparation", (1, 2), Y1, S2, M),
    ("HM1207", "Fundamentals in Food Service Operations", (2, 1), Y1, S2, M),
    ("GEC104", "Readings in the Philippine History", 3, Y1, S2, m),
    ("ELEC1", "Living in the IT Era", 2, Y1, S2, m), ("ELEC1L", "Living in the IT Era - Lab", 1, Y1, S2, m),
    ("EPP2", "English Proficiency 2: Technical Writing", 3, Y1, S2, m), ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m),
    ("PATHFIT2", "Physical Activities Toward Health and Fitness 2", 2, Y1, S2, m), ("GE502", "NSTP / ROTC 2", 3, Y1, S2, m),
    ("GEC106", "Purposive Communication", 3, Y2, S1, m), ("GEC102", "Ethics", 3, Y2, S1, m),
    ("GEC109", "Understanding the Self", 3, Y2, S1, m), ("GEC108", "Science, Technology and Society", 3, Y2, S1, m),
    ("HM2108", "Professional Development & Applied Ethics", 3, Y2, S1, M), ("HM2109", "Bread and Pastry", (1, 2), Y2, S1, M),
    ("HM2110", "Fundamentals in Lodging Operations", (2, 1), Y2, S1, M),
    ("HM2111", "Applied Business Tools & Technologies", (2, 1), Y2, S1, M),
    ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m), ("PATHFIT3", "Physical Activities Toward Health and Fitness 3", 2, Y2, S1, m),
    ("HM2212", "Bar and Beverage Management", (2, 1), Y2, S2, M), ("HM2213", "Legal Aspect in Tourism & Hospitality", 3, Y2, S2, M),
    ("HM2214", "Front Office Operations", (2, 1), Y2, S2, M),
    ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m), ("PATHFIT4", "Physical Activities Toward Health and Fitness 4", 2, Y2, S2, m),
    ("HM3116", "Supply Chain Mngt. in Hospitality Industry", 3, Y3, S1, M), ("HM3117", "Operational Management", 3, Y3, S1, M),
    ("GEC103", "The Contemporary World", 3, Y3, S1, m), ("HM3118", "F&B Cost Control", 3, Y3, S1, M),
    ("HM3119", "Multicultural Diversity in Workplace for Tourism Professional", 3, Y3, S1, M),
    ("HM3120", "Ergonomics and Facilities Planning for the Hospitality", (2, 1), Y3, S1, M),
    ("HM3121", "ASIAN and Regional Cuisines", (1, 2), Y3, S1, M), ("HM3122", "Foreign Language 1", 3, Y3, S1, M),
    ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m),
    ("HM3223", "Strategic Management", 3, Y3, S2, M), ("HM3224", "Tourism & Hospitality Marketing", 3, Y3, S2, M),
    ("HM3225", "Entrepreneurial in Tourism & Hospitality", 3, Y3, S2, M), ("HM3226", "Foreign Language 2", 3, Y3, S2, M),
    ("HM3227", "Introduction to Meeting, Incentives conferences & Events Management", (2, 1), Y3, S2, M),
    ("HM3228", "Catering Management", (1, 2), Y3, S2, M),
    ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m), ("GE407", "Filipino Christian Living 7", 2, Y3, S2, m),
    ("HM4129", "Research in Hospitality", (2, 1), Y4, S1, M), ("HM3230", "Specialty Cuisine", (1, 2), Y4, S1, M),
    ("HM3231", "Cruise Operations and Management", 3, Y4, S1, M), ("GE602", "World Literature", 3, Y4, S1, m),
    ("ELEC2", "Gender and Society", 3, Y4, S1, m), ("GEC101", "Art Appreciation", 3, Y4, S1, m),
    ("GEC107", "Life and Works of Rizal", 3, Y4, S1, m), ("GE408", "Filipino Christian Living 8", 2, Y4, S1, m),
]

# ---------------- Tourism ----------------
TM = [
    ("GEC105", "Mathematics in the Modern World", 3, Y1, S1, m), ("TM1101", "Philippine Culture, Tourism & Geography", 3, Y1, S1, M),
    ("TM1102", "Risk Management as Applied to Safety, Security, Sanitation", 3, Y1, S1, M),
    ("TM1103", "Macro Perspective of Tourism and Hospitality", 3, Y1, S1, M),
    ("TM1204", "Quality Service Management in Tourism & Hospitality", 3, Y1, S1, M),
    ("EPP1", "English Proficiency 1: Intensive Grammar", 3, Y1, S1, m), ("GE401", "Filipino Christian Living 1", 2, Y1, S1, m),
    ("PATHFIT1", "Physical Education 1", 2, Y1, S1, m), ("GE501", "NSTP 1 / ROTC 1", 3, Y1, S1, m),
    ("TM1205", "Global Tourism, Geography & Culture", 3, Y1, S2, M), ("TM1206", "Micro Perspective of Tourism & Hospitality", 3, Y1, S2, M),
    ("TM1207", "Professional Development & Applied Ethics", 3, Y1, S2, M),
    ("EPP2", "English Proficiency 2: Technical Writing", 3, Y1, S2, m), ("GEC104", "Reading in the Philippine History", 3, Y1, S2, m),
    ("GE402", "Filipino Christian Living 2", 2, Y1, S2, m), ("PATHFIT2", "Physical Education 2", 2, Y1, S2, m),
    ("GE502", "NSTP2/ROTC2", 3, Y1, S2, m),
    ("TM2108", "Sustainable Tourism", 3, Y2, S1, M), ("TM2109", "Tour & Travel Management", 3, Y2, S1, M),
    ("TM2110", "Specialized F&B Service Operations", 3, Y2, S1, M), ("TM2111", "Transport Management", 3, Y2, S1, M),
    ("GEC102", "Ethics", 3, Y2, S1, m), ("GEC109", "Understanding the Self", 3, Y2, S1, m),
    ("GEC108", "Science, Technology & Society", 3, Y2, S1, m), ("GEC106", "Purposive Communication", 3, Y2, S1, m),
    ("GE403", "Filipino Christian Living 3", 2, Y2, S1, m), ("PATHFIT3", "Physical Education 3", 2, Y2, S1, m),
    ("TM2212", "Tour Guiding", 3, Y2, S2, M), ("TM2213", "Foreign Language 1", 3, Y2, S2, M),
    ("TM2214", "Legal Aspects in Tourism & Hospitality", 3, Y2, S2, M),
    ("ELEC1", "Living in the IT Era", 2, Y2, S2, m), ("ELEC1L", "Living in the IT Era - Lab", 1, Y2, S2, m),
    ("GE404", "Filipino Christian Living 4", 2, Y2, S2, m), ("PATHFIT4", "Physical Education 4", 2, Y2, S2, m),
    ("TM3116", "Tourism Policy Planning & Development", 3, Y3, S1, M), ("TM3117", "Operational Management", 3, Y3, S1, M),
    ("TM3118", "Foreign Language 2", 3, Y3, S1, M),
    ("TM3119", "Multicultural Diversity in Workplace for Tourism Professional", 3, Y3, S1, M),
    ("TM3120", "Applied Business Tools & Technologies in Tourism", (2, 1), Y3, S1, M),
    ("TM3221", "Introduction to Meeting, Incentives Conferences & Events Management", (2, 1), Y3, S1, M),
    ("GEC103", "The Contemporary World", 3, Y3, S1, m), ("ELEC3", "Environmental Science", 3, Y3, S1, m),
    ("GE405", "Filipino Christian Living 5", 2, Y3, S1, m),
    ("TM3222", "Strategic Management", 3, Y3, S2, M), ("TM3223", "Tourism & Hospitality Marketing", 3, Y3, S2, M),
    ("TM3224", "Cruise Tourism", 3, Y3, S2, M), ("TM3225", "Entrepreneurship in Tourism & Hospitality", 3, Y3, S2, M),
    ("TM3126", "Eco-tourism Management", 3, Y3, S2, M), ("TM327", "Accommodation Operations and Management", 3, Y3, S2, M),
    ("TM3128", "Heritage Tourism", 3, Y3, S2, M),
    ("GE406", "Filipino Christian Living 6", 2, Y3, S2, m), ("GE407", "Filipino Christian Living 7", 2, Y3, S2, m),
    ("TM4129", "Destination Management and Marketing", 3, Y4, S1, M), ("TM4130", "Research in Tourism", (2, 1), Y4, S1, M),
    ("TM4131", "Philippine Gastronomical Tourism", 3, Y4, S1, M), ("GE602", "World Literature", 3, Y4, S1, m),
    ("ELEC2", "Gender and Society", 3, Y4, S1, m), ("GEC101", "Art Appreciation", 3, Y4, S1, m),
    ("GEC107", "Life & Works of Rizal", 3, Y4, S1, m), ("GE408", "Filipino Christian Living 8", 2, Y4, S1, m),
]

PROGRAMS = {
    "MM": ("BSBA Major in Marketing Management", CBA, MM, {1: 21, 2: 10, 3: 9, 4: 9}),
    "HRD": ("BSBA Major in Human Resource Development Management", CBA, HRD, {1: 9, 2: 7, 3: 14, 4: 9}),
    "HM": ("BS Hospitality Management", CIHM, HM, {1: 39, 2: 35, 3: 34, 4: 30}),
    "TM": ("BS Tourism Management", CIHM, TM, {1: 22, 2: 15, 3: 13, 4: 11}),
}

NOTE = ("Not seeded (off-campus, cannot be given a room): Internship (600 hrs) MM4226 / HRD4227, "
        "Practicum 1 HM2215 / TM2215, Practicum 2 HM4232 / TM4232.")


class Command(BaseCommand):
    help = "Seed the Marketing Mgmt, HRDM, Hospitality Mgmt and Tourism Mgmt curricula."

    def add_arguments(self, parser):
        parser.add_argument("--only", default="", help="Comma list of MM,HRD,HM,TM (default: all).")

    def handle(self, *args, **o):
        want = [x.strip().upper() for x in o["only"].split(",") if x.strip()] or list(PROGRAMS)
        for key in want:
            if key not in PROGRAMS:
                self.stdout.write(self.style.ERROR(f"Unknown program key {key!r}; use MM, HRD, HM, TM."))
                continue
            name, dept, rows, sizes = PROGRAMS[key]
            self.stdout.write(f"\n== {name} ==")
            load(self, name, dept, rows, skipped_note=NOTE, sizes=sizes, fix_department=True)
