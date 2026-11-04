"""
Reference data for checking the Senior High School (SHS) curriculum lines stored in the system.

Sources (DepEd):
  * DepEd Order No. 017, s. 2026 and DM 012, s. 2026 - Strengthened SHS Curriculum: full implementation for Grade 11 from SY 2026-2027;
    Grade 12 learners of SY 2026-2027 stay on the 2016 K to 12 SHS curriculum and move over in SY 2027-2028.
  * DM 048, s. 2025 and the "Strengthened SHS Program" page (deped.gov.ph/strengthened-shs-program/) - the five Grade 11 core subjects
    (160 hours each), Homeroom Guidance (1 hour/week), elective clusters and elective subject titles.
Only what those documents state is treated as an error when it differs. Where DepEd has not published the detail (which elective is
taken in which term, the Grade 12 subject list for SY 2026-2027) the system data is reported as "cannot be verified", never rewritten.
"""
import re

REFERENCE_NOTE = ("DepEd Order 017 s.2026 / DM 48 s.2025 (Strengthened SHS: Grade 11 core 160 h each, 4 periods/week, whole school year)")

# Grade 11 (Strengthened SHS) core subjects: name, hours, periods per week
G11_CORE = [
    ("SHS11-EFFCOM", "Effective Communication / Mabisang Komunikasyon", 160, 4),
    ("SHS11-GENMATH", "General Mathematics", 160, 4),
    ("SHS11-GENSCI", "General Science", 160, 4),
    ("SHS11-LCS", "Life and Career Skills", 160, 4),
    ("SHS11-PKLP", "Pag-aaral ng Kasaysayan at Lipunang Pilipino", 160, 4),
]
G11_HGP = ("SHS11-HGP", "Homeroom Guidance Program", 40, 1)

# Valid grading-period numbers (0 = the whole school year). Grade 11: 3 terms; Grade 12: 2 semesters.
MAX_PERIOD = {11: 3, 12: 2}

# Elective subject titles DepEd lists per cluster (a school offers some of them; which term each is taken in is not published).
CLUSTER_ELECTIVES = {
    "Arts, Social Sciences, and Humanities": [
        "Arts 1", "Arts 2", "Citizenship and Civic Engagement", "Contemporary Literature 1", "Contemporary Literature 2",
        "Creative Composition 1", "Creative Composition 2", "Filipino 1", "Filipino 2", "Filipino Identity Through the Arts",
        "Introduction to Philosophy", "Leadership Management in the Arts", "Malikhaing Pagsulat", "Philippine Governance",
        "Social Sciences (Theory and Practice)"],
    "Business and Entrepreneurship": [
        "Business 1 (Basic Accounting)", "Business 2 (Business Finance and Income Taxation)", "Business 3 (Business Economics)",
        "Contemporary Marketing", "Entrepreneurship", "Introduction to Organization and Management"],
    "Science, Technology, Engineering, and Mathematics (STEM)": [
        "Biology 1", "Biology 2", "Chemistry 1", "Chemistry 2", "Earth and Space Science 1", "Earth and Space Science 2",
        "Finite Mathematics 1", "Finite Mathematics 2", "Physics 1", "Physics 2"],
    "Sports, Health, and Wellness": [
        "Human Movement 1", "Human Movement 2", "Physical Education 1", "Physical Education 2", "Sports Activity Management",
        "Sports Coaching", "Sports Officiating"],
    "ICT Support and Computer Programming Technologies": [
        "Broadband Installation", "Computer Programming (.NET Technology)", "Computer Programming (Java)",
        "Computer Programming (Oracle Database)", "Computer Systems Servicing", "Contact Center Services"],
    "Industrial Technologies": [
        "Commercial Air-Conditioning Installation and Servicing", "Domestic Refrigeration and Air-Conditioning Servicing",
        "Electrical Installation Maintenance", "Electronics Product and Assembly Servicing", "Mechatronics",
        "Photovoltaic Systems Installation"],
}
# Names of the clusters as stored on Strand.deped_cluster that are a spelling variant of the DepEd name above.
CLUSTER_ALIASES = {"arts, social science, and humanities": "Arts, Social Sciences, and Humanities",
                   "science, technology, engineering, and mathematics": "Science, Technology, Engineering, and Mathematics (STEM)"}

# Subjects of the 2016 K to 12 SHS curriculum. They are NOT part of the Strengthened Grade 11 curriculum, so a Grade 11 line with one
# of these names is outdated. (Names that also exist in the new curriculum -- General Mathematics, Entrepreneurship, Philippine
# Governance -- are deliberately left out.)
LEGACY_TITLES = [
    "Oral Communication", "Oral Communication in Context", "Reading and Writing Skills", "Reading and Writing",
    "Komunikasyon at Pananaliksik sa Wika at Kulturang Pilipino", "Pagbasa at Pagsusuri ng Iba't Ibang Teksto Tungo sa Pananaliksik",
    "21st Century Literature from the Philippines and the World", "Contemporary Philippine Arts from the Regions",
    "Media and Information Literacy", "Statistics and Probability", "Earth and Life Science", "Earth Science", "Physical Science",
    "Introduction to the Philosophy of the Human Person", "Physical Education and Health", "Understanding Culture, Society and Politics",
    "Personal Development", "English for Academic and Professional Purposes", "Practical Research 1", "Practical Research 2",
    "Filipino sa Piling Larang", "Empowerment Technologies", "Inquiries, Investigations and Immersion", "Pre-Calculus", "Basic Calculus",
    "General Biology 1", "General Biology 2", "General Physics 1", "General Physics 2", "General Chemistry 1", "General Chemistry 2",
    "Fundamentals of Accountancy, Business and Management 1", "Fundamentals of Accountancy, Business and Management 2",
    "Business Mathematics", "Business Ethics and Social Responsibility", "Applied Economics", "Business Finance",
    "Organization and Management", "Principles of Marketing", "Business Enterprise Simulation", "Creative Writing",
    "Introduction to World Religions and Belief Systems", "Disciplines and Ideas in the Social Sciences",
    "Disciplines and Ideas in the Applied Social Sciences", "Community Engagement, Solidarity and Citizenship", "Creative Nonfiction",
    "Trends, Networks and Critical Thinking in the 21st Century",
]

# Lines that are test / sample / import leftovers and not real subjects.
JUNK_CODE = re.compile(r"^(t-\d*|test\w*|imp-\d+|sample\w*|dummy\w*|xxx\w*)$", re.I)
JUNK_NAME = re.compile(r"^(test\w*|imported subject|sample\w*|dummy\w*|new subject|untitled\w*|subject \d*|n/?a)$", re.I)


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


LEGACY_NORM = {norm(t) for t in LEGACY_TITLES}


def cluster_name(text):
    return CLUSTER_ALIASES.get((text or "").strip().lower(), (text or "").strip())
