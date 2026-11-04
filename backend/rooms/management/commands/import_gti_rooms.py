"""
Loads the university's rooms from the GTI class program workbook
(GTI_class_prog_2021-2026.xlsx) so rooms carry a real building + room number
("D-307") instead of free text.

    python manage.py import_gti_rooms "C:\\path\\to\\GTI_class_prog_2021-2026.xlsx"            (preview only)
    python manage.py import_gti_rooms "C:\\path\\to\\GTI_class_prog_2021-2026.xlsx" --apply    (write to database)

By default only rooms used in the 4 most recent terms are imported (--terms N
or --all to change). Symbols such as '#', '*' and '###' in the workbook's room
column are stripped. Rooms whose building can't be determined from the
workbook are NOT guessed -- they are listed under "NEEDS REVIEW" and skipped.

Capacities are the registrar's rough figures (Alta/D 30, Main/M 30, New/N 20,
Alfredo/A 30, allied-health & nursing labs 40), stored with
capacity_is_estimate=True so they can be corrected in the admin. Existing rooms
are never overwritten.
"""
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from rooms.models import Room, DepartmentBuilding

# Alias for the Computer Studies labs, confirmed by the registrar:
# Lab B = D-303, Lab C = D-307, Lab D = D-309, network lab = D-304.
CS_LAB_ALIASES = {
    "LAB-B": "D-303", "LAB-C": "D-307", "LAB-D": "D-309", "NET-LAB": "D-304",
    "LAB-C1": "D-307", "LAB-D1": "D-309", "LAB-D2": "D-309",
}
CS_LAB_LABELS = {
    "D-303": "Comp Lab B", "D-307": "Comp Lab C", "D-309": "Comp Lab D", "D-304": "Network Lab",
}
# Rooms the registrar named explicitly.
ROOM_LABELS = {"D-203": "BA Comm room", "D-204": "RadTech room", "D-206": "RadTech / BA room"}
ROOM_DEPARTMENT = {
    "D-303": "Senior High / Junior High", "D-304": "Computer Studies", "D-307": "Computer Studies",
    "D-309": "Computer Studies", "D-204": "Radiologic Technology", "D-206": "Radiologic Technology",
}
BUILDING_CAPACITY = {"D": 30, "M": 40, "N": 20, "A": 30}   # registrar's figures (Main building = 40)
LAB_CAPACITY_BIG = 40                                         # allied-health / nursing labs

# Named (non-numbered) rooms: (regex on cleaned text) -> (name, label, type, building, capacity)
NAMED = [
    (r"^GYM$", "GYM", "Gym", "gym", "", 50),
    (r"^N\.ARTS(\w+)$", None, "Nursing Arts {0}", "lab", "M", LAB_CAPACITY_BIG),   # Nursing Arts rooms are in the Main building
    (r"^(?:ANA-LAB|ANATOMY-LAB)(?:M1?)?$", "M-ANATOMY-LAB", "Anatomy Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^ZOO-LABM1?$", "M-ZOO-LAB", "Zoology Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^CHEM-LAB(?:M1?|1M)?$", "M-CHEM-LAB", "Chemistry Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^PHYSICLAB1?$|^PHYSICSM1$", "M-PHYSICS-LAB", "Physics Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^MICRO-LAB$", "M-MICRO-LAB", "Microbiology Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^XRAY-LABM1$", "M-XRAY-LAB", "X-ray Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^AUDI-A$", "M-AUDI-A", "Auditorium A", "lecture", "M", 100),
    (r"^KITCHEN1$", "M-KITCHEN-1", "Kitchen 1", "lab", "M", LAB_CAPACITY_BIG),
    (r"^KITCHEN2$", "M-KITCHEN-2", "Kitchen 2", "lab", "M", LAB_CAPACITY_BIG),
    (r"^HJ1?$", "M-HJ", "HJ room", "lecture", "M", 40),
    (r"^MC-LAB$", "M-MC-LAB", "MC Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^RT LAB$", "M-RT-LAB", "RT Lab", "lab", "M", LAB_CAPACITY_BIG),
    (r"^LIBM1?$", "M-LIBRARY", "Library", "lecture", "M", 40),
]
OFFSITE = re.compile(r"^(FIELD|ONLINE|CLINICAL.*|HOSPITAL.*|AREA-.*|CLINAREH)$")
SKIP = re.compile(r"^(TBA|101|602M|303M\(OFFICE\))$")


def clean(raw):
    s = str(raw).strip().upper().replace("#", "").replace("*", "")
    return re.sub(r"\s+", " ", s).strip(" -")


def normalize(raw):
    """-> dict(name, label, room_type, building, number, capacity, department) or ('review', reason)."""
    c = clean(raw)
    if not c or SKIP.match(c):
        return ("review", "no usable room (TBA / office / no building)")
    if OFFSITE.match(c):
        return dict(name=c.title().replace(" ", " "), label="Off-site / online", room_type="offsite",
                    building="", number="", capacity=100, department=None)
    if c in CS_LAB_ALIASES:
        code = CS_LAB_ALIASES[c]
        b, n = code.split("-")
        return dict(name=code, label=CS_LAB_LABELS[code], room_type="lab", building=b, number=n,
                    capacity=BUILDING_CAPACITY[b], department=ROOM_DEPARTMENT.get(code))
    for pat, name, label, rtype, bld, cap in NAMED:
        m = re.match(pat, c)
        if m:
            if name is None:
                suffix = m.group(1)
                name = f"M-NARTS-{suffix}"
                label = label.format(suffix)
            return dict(name=name, label=label, room_type=rtype, building=bld, number="", capacity=cap, department=None)
    # numbered rooms: 203D, 307D(LAB-C), 301M1, 402N-OT, 404-D1, BA102A ...
    m = re.match(r"^BA(\d{3})([MDNA])\d?$", c)
    if m:
        num, b = m.group(1), m.group(2)
        return dict(name=f"{b}-{num}", label="BA room", room_type="lecture", building=b, number=num,
                    capacity=BUILDING_CAPACITY[b], department=None)
    m = re.match(r"^(\d{3})-?([MDNA])(H\d?)?(\d?)\b(.*)$", c)
    if m:
        num, b, ah, _digit, rest = m.groups()
        if ah:
            return ("review", f"'{c}': 'AH' suffix -- which building is this?")
        name = f"{b}-{num}"
        label = ROOM_LABELS.get(name, "")
        low = rest.upper()
        rtype = "lecture"
        if name in CS_LAB_LABELS:
            label, rtype = CS_LAB_LABELS[name], "lab"
        elif "LAB" in low or "NET" in low:
            rtype = "lab"
        if "(BACOM)" in low:
            label = "BA Comm room"
        elif "(RAD)" in low:
            label = label or "RadTech room"
        elif "-OT" in low:
            label = label or "OT room"
        elif "-RT" in low:
            label = label or "RT room"
        elif "-PT" in low:
            label = label or "PT room"
        elif "-BLS" in low:
            label = label or "BLS room"
        cap = LAB_CAPACITY_BIG if (rtype == "lab" and b != "D") else BUILDING_CAPACITY[b]
        return dict(name=name, label=label, room_type=rtype, building=b, number=num, capacity=cap,
                    department=ROOM_DEPARTMENT.get(name))
    return ("review", f"'{c}': building not clear from the workbook")


class Command(BaseCommand):
    help = "Import rooms (building + number) from the GTI class program workbook."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path")
        parser.add_argument("--apply", action="store_true", help="Write to the database (default: preview only).")
        parser.add_argument("--terms", type=int, default=4, help="Only rooms used in the N most recent terms (default 4).")
        parser.add_argument("--all", action="store_true", help="Use every term in the workbook.")

    def handle(self, *args, **opts):
        try:
            import openpyxl
        except ImportError:
            raise CommandError("openpyxl is required: pip install openpyxl")
        wb = openpyxl.load_workbook(opts["xlsx_path"], read_only=True, data_only=True)
        sheets = wb.worksheets if opts["all"] else wb.worksheets[: opts["terms"]]

        usage = Counter()
        for ws in sheets:
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i == 0 or len(row) < 5 or row[4] is None:
                    continue
                usage[str(row[4])] += 1

        rooms, review, merged = {}, defaultdict(int), defaultdict(set)
        for raw, count in usage.items():
            res = normalize(raw)
            if isinstance(res, tuple):
                review[res[1]] += count
                continue
            key = res["name"]
            merged[key].add(clean(raw))
            rooms.setdefault(key, res)

        self.stdout.write(f"Terms read: {[ws.title for ws in sheets]}")
        self.stdout.write(f"{len(usage)} distinct room spellings -> {len(rooms)} rooms after cleaning.\n")
        by_b = defaultdict(list)
        for r in rooms.values():
            by_b[r["building"] or "(none)"].append(r)
        for b in sorted(by_b):
            self.stdout.write(f"== Building {b}: {len(by_b[b])} rooms")
            for r in sorted(by_b[b], key=lambda x: x["name"]):
                spell = sorted(merged[r["name"]])
                extra = f"   <- merged spellings: {', '.join(spell)}" if len(spell) > 1 else ""
                self.stdout.write(f"   {r['name']:16} {r['room_type']:8} cap~{r['capacity']:<4} {r['label']}{extra}")
        if review:
            self.stdout.write(self.style.WARNING("\nNEEDS REVIEW (not imported):"))
            for reason, n in sorted(review.items(), key=lambda x: -x[1]):
                self.stdout.write(f"   {n:3} uses -- {reason}")

        if not opts["apply"]:
            self.stdout.write(self.style.WARNING("\nPreview only. Re-run with --apply to write these to the database."))
            return

        made = 0
        for r in rooms.values():
            _, created = Room.objects.get_or_create(
                name=r["name"],
                defaults=dict(
                    building=r["building"], room_number=r["number"], label=r["label"], capacity=r["capacity"],
                    capacity_is_estimate=True, room_type=r["room_type"], department=r["department"],
                ),
            )
            made += created
        # Department -> building defaults, derived from where those departments' classes
        # are held in the workbook. A preference only; edit in the admin if wrong.
        for dept, b in [("Computer Studies", "D"), ("Radiologic Technology", "N"), ("Tourism and Hospitality Management", "M")]:
            DepartmentBuilding.objects.get_or_create(department=dept, defaults={"building": b})
        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {made} new rooms created, {len(rooms) - made} already existed (left unchanged)."
            "\nDepartment buildings set (derived from the workbook -- please confirm in the admin):"
            "\n   Computer Studies -> D,  Radiologic Technology -> N,  Tourism and Hospitality Management -> M"
        ))
