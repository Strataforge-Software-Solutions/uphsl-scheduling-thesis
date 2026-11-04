"""
Room assignments read from the GTI class program workbook (GTI_class_prog_2021-2026.xlsx, the 4 latest terms).

Each department's rooms were counted from where its sections actually meet. A room that one department uses
almost exclusively (>= 85 % of its bookings, 8 or more of them) is RESERVED to it (`reserved`); the rooms a
department mostly uses for its major subjects are its HOME rooms (`home`), tried first by the generator but not
exclusive. Departments are found by keyword in the program/department names that exist in your database.

Room spec fields: key (stable id), aliases (any spelling that means the same room), building, number, label,
type, capacity (used only when the room has to be created).
"""

# department key -> keywords that identify the department name in the database (all must appear)
DEPT_KEYWORDS = {
    "cs": ("computer",),
    "ihm": ("hospitality",),
    "radtech": ("radiolog",),
    "nursing": ("nursing",),
    "allied": ("allied",),
    "cba": ("business",),
    "cas": ("arts",),
}

SHS_JHS = "Senior High / Junior High"

# key: (aliases, building, number, label, type, capacity)
ROOMS = {
    # Computer Studies, Alta (D) building 3rd floor
    "D307": (["COMPLABC", "LABC", "COMPUTERLABC"], "D", "307", "Comp Lab C", "lab", 40),
    "D309": (["COMPLABD", "LABD", "COMPUTERLABD"], "D", "309", "Comp Lab D", "lab", 40),
    # 304D and 305D are OFFICES, not classrooms: type "offsite" is never handed out by the scheduler
    # and never appears in a room dropdown.
    "D304": (["NSTPOFFICE", "NETLAB", "NETWORKLAB", "COMPLABNET"], "D", "304", "NSTP Office", "offsite", 1),
    "D305": (["ITOFFICE", "CSLECTUREROOM", "COMPUTERSTUDIESLECTUREROOM"], "D", "305", "IT Office", "offsite", 1),
    "D303": (["COMPLABB", "LABB", "COMPUTERLABB"], "D", "303", "Comp Lab B", "lab", 40),
    # International Hospitality Management, Main (M) building
    "M-HJ": (["HJ", "HJ1", "MHJ", "MHJ1", "HJROOM"], "M", "", "HJ room", "lecture", 40),
    "M-KITCHEN-1": (["KITCHEN1", "MKITCHEN1", "KITCHEN"], "M", "", "Kitchen 1", "lab", 40),
    "M-KITCHEN-2": (["KITCHEN2", "MKITCHEN2"], "M", "", "Kitchen 2", "lab", 40),
    # Radiologic Technology
    "D204": ([], "D", "204", "RadTech room", "lecture", 40),
    "D206": ([], "D", "206", "RadTech / BA room", "lecture", 40),
    "M-XRAY-LAB": (["XRAYLABM1", "XRAYLAB", "MXRAYLAB"], "M", "", "X-ray Lab", "lab", 40),
    # Nursing
    "M-NARTS-4FA": (["NARTS4FA"], "M", "", "Nursing Arts 4FA", "lab", 40),
    "M-NARTS-4FB": (["NARTS4FB"], "M", "", "Nursing Arts 4FB", "lab", 40),
    "M-NARTS-7F": (["NARTS7F"], "M", "", "Nursing Arts 7F", "lab", 40),
    "M-PHYSICS-LAB": (["PHYSICLAB", "PHYSICLAB1", "PHYSICSM1", "PHYSICSLAB"], "M", "", "Physics Lab", "lab", 40),
    "M-MICRO-LAB": (["MICROLAB", "MMICROLAB"], "M", "", "Microbiology Lab", "lab", 40),
    "M-ANATOMY-LAB": (["ANATOMYLAB", "ANALAB", "ANALABM", "ANALABM1"], "M", "", "Anatomy Lab", "lab", 40),
    "M-CHEM-LAB": (["CHEMLAB", "CHEMLABM", "CHEMLABM1", "CHEMLAB1M"], "M", "", "Chemistry Lab", "lab", 40),
    "M-ZOO-LAB": (["ZOOLAB", "ZOOLABM", "ZOOLABM1"], "M", "", "Zoology Lab", "lab", 40),
    "N601": ([], "N", "601", "", "lecture", 40),
    "N602": ([], "N", "602", "", "lecture", 40),
    "M301": ([], "M", "301", "", "lecture", 40),
    "M304": ([], "M", "304", "", "lecture", 40),
    "M306": ([], "M", "306", "", "lecture", 40),
    "M307": ([], "M", "307", "", "lecture", 40),
    # Allied Health
    "N302": ([], "N", "302", "PT room", "lecture", 40),
    "N401": ([], "N", "401", "", "lecture", 40),
    "N402": (["402NOT"], "N", "402", "OT room", "lecture", 40),
    "N301": ([], "N", "301", "", "lecture", 40),
    "N201": ([], "N", "201", "", "lecture", 40),
    # Business Administration, Arts and Science
    "A101": ([], "A", "101", "", "lecture", 40),
    "M501": ([], "M", "501", "", "lecture", 40),
    "M503": ([], "M", "503", "", "lecture", 40),
    "D203": (["BACOMM", "BACOMMROOM"], "D", "203", "BA Comm room", "lecture", 40),
    "A204": ([], "A", "204", "", "lecture", 40),
    "M305": ([], "M", "305", "", "lecture", 40),
}

# department key -> room keys RESERVED to it (nobody else may be put there)
RESERVED = {
    "cs": ["D307", "D309"],
    "ihm": ["M-HJ", "M-KITCHEN-1", "M-KITCHEN-2"],
    "radtech": ["D204", "M-XRAY-LAB"],
    "nursing": ["M-NARTS-4FA", "M-NARTS-4FB", "M-NARTS-7F", "M-PHYSICS-LAB", "M-MICRO-LAB", "M-ANATOMY-LAB", "N601", "N602"],
    "allied": ["N302", "N401", "N402"],
}

# department key -> HOME rooms for its major subjects (a preference, in order)
HOME = {
    "cs": ["D307", "D309"],
    "ihm": ["M-HJ", "M-KITCHEN-1", "M-KITCHEN-2", "M503", "M501"],
    "radtech": ["D204", "D206", "M-XRAY-LAB", "M305"],
    "nursing": ["N601", "N602", "M301", "M304", "M306", "M307", "M-CHEM-LAB", "M-ZOO-LAB"],
    "allied": ["N302", "N401", "N402", "N301", "N201"],
    "cba": ["A101", "M501", "D206"],
    "cas": ["D203", "A204"],
}

# Building where each department's major classes are held (most bookings in the workbook)
DEPT_BUILDING = {"cs": "D", "ihm": "M", "radtech": "D", "nursing": "M", "allied": "N", "cba": "A", "cas": "D"}
