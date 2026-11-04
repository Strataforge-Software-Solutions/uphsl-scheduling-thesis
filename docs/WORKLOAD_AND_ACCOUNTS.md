# Faculty workload, account management and dashboard updates

## Run after updating
    cd backend
    python manage.py migrate        # adds the workload limits to SchedulingConfig (engine 0007)
Then restart the backend, and sign out / sign in once in the browser.

## Faculty workload
* Workload = distinct teaching hours per week in a semester. A shared minor class (several sections, one teacher/room/time) is counted once.
* Limits are settings, not code: Registrar > Analytics > "Workload limits" (Full-time, Part-time, and the policy). Defaults 24 h / 12 h.
* Policy `override` (default): an overloaded manual assignment is stopped with the warning
  "Faculty Workload Overload: <name> is assigned X hours per week, exceeding the permitted maximum of Y hours per week by Z hours."
  The Dean/Registrar can then pick a suggested replacement or "Assign anyway" - recorded in the audit log (Log, details start with `WORKLOAD OVERRIDE`).
  Policy `strict`: the assignment is refused, and the generator treats the limit as a hard rule.
* Generation always checks the result and returns `workload_warnings` (with the class that pushes the teacher over and replacement ideas).
* Replacements must match the subject's specialization, be inside their availability, have no clash with a class they already teach, and have hours left under their own limit.
* Views: Dean > Faculty (workload table + roster), Registrar > Analytics, Generate panel, Edit-schedule dialog.
* API: GET /api/engine/workload/, /workload/<faculty_id>/, /workload/replacements/, POST /workload/check/.

## Accounts
* Dean > Faculty > "+ Add Faculty": Full-time / Part-time, School ID generated automatically (F#### / P####, unique), shown after creation.
  API: POST /api/accounts/dean/create-faculty/.
* Account management (directory, reset password, bulk create, add account) is IT Admin only. The Registrar no longer has People & Accounts.
* IT Admin > People & Accounts: scrollable directory with search (School ID, name, email, role, Full-time/Part-time, department) and Clear.
* IT Admin > Activity: independently scrollable list (200 most recent) with a sticky header.

## Room reservations (M-HJ, Comp Lab B / C / D)

Run once after updating (after `prefix_departments`, so department names match):

    python manage.py setup_rooms            # preview
    python manage.py setup_rooms --apply

* M-HJ is reserved for the IHM department. Comp Lab C and D (Alta Building, 3rd floor) belong to Computer Studies.
  Comp Lab B is reserved for SHS and JHS. "Comp Lab 1" is retired; its bookings move to Comp Lab C / D.
* Any room with a department is exclusive to it: the generator, merged minor classes, exam scheduler and manual
  edits all refuse other departments. A department that owns labs uses only its own labs for lab subjects.
* If a department name is not found, pass `--ihm-department "..."` / `--cs-department "..."`.
* Re-generate schedules afterwards so existing drafts follow the rules.

## Schedule moves, replacements, resume upload

Run `python manage.py migrate` (adds degree / qualifications to faculty profiles) and `pip install -r requirements.txt`
(pypdf, python-docx for resume reading).

* Schedules tab: tick classes -> "Change day / time". Clashes show a warning with free times on that day; nothing moves until all fit.
* Faculty tab -> "Find replacement": ranks qualified faculty per class by specialization, degree, qualifications, availability and workload.
* Faculty tab -> Add Faculty -> "Upload resume": fills the form (PDF text, Word, TXT; scanned images are not readable). Review before saving; the file itself is not stored.

## Labels, PDF type option, day/time edits

* Minor subjects are shown as "Gen Ed"; major subjects show the program name (e.g. "BS Computer Science").
* Print / Preview follows the type dropdown: program subjects only, Gen Ed only, or both.
* Edit dialog: day / start / end changes are checked together; a clash opens a warning with free times on that day to pick and apply.
* "Comp Lab 1" disappears once `python manage.py setup_rooms --apply` has been run (its bookings move to Comp Lab C / D).

## Room Assignment Management (Dean -> Rooms)

Run `python manage.py migrate` (adds the room-assignment table).

* Building preference: the building (M / D / N) your program subjects try first. Gen Ed subjects default to the Main Building.
* Subject rooms: per program subject choose a preferred room, alternative rooms and optionally "Fixed".
  Generate Schedule uses the preferred room first, then the alternatives, then any other suitable room; a fixed room is
  the only room allowed (and, if busy, the class is reported as unplaced with the reason). The result lists any class
  that had to leave its preferred room.
* Rooms: add or edit your college's rooms (building, number, capacity, type, equipment). A room you add is reserved for your college.
* Checks: room type (lab subjects need labs), capacity versus the section size, rooms reserved for other departments, and
  the "own labs" rule. Manual edits (Schedules -> Edit) list preferred/alternative rooms first and refuse another room for a fixed subject.

## Alta (D) 3rd-floor rooms, lecture vs lab, login

* Major (program) subjects prefer Alta (D) Building, 3rd floor; Gen Ed subjects use Main (M).
* Alta 3rd floor, Computer Studies: **307 = Comp Lab C**, **309 = Comp Lab D**; **304D = NSTP office** and **305D = IT office** are offices (type Off-site, never scheduled, not in dropdowns).
  Run `python manage.py setup_rooms` (preview) then `python manage.py setup_rooms --apply`
* Lecture classes never go into a department's lab (generation, manual edit and bulk move all refuse it); lab classes use Comp Lab C/D.
* Room dropdown is grouped into "Lecture rooms" and "Computer laboratories".
* Login accepts `UPHM-<ID>`, `UPHSM-<ID>` or the bare School ID; the password is checked exactly as before.
  The first-login screen now confirms the password, shows the validator messages, and clears the "must change" flag.

## Computer Studies Dean and faculty list

`python manage.py setup_ccs_faculty` (preview) / `--apply` renames the Dean to Dr. Anna Liza O. Villanueva and replaces the
college's faculty with the six listed in the command (old accounts are renamed in place where possible, extras deleted).
Use `--part-time Tungol,Mazo` to mark anyone as part-time (default: full-time).

## Change day / time with several classes

In the clash pop-up, a time that overlaps the time already chosen for another selected class of the same section,
teacher or room is greyed out, so two picks can no longer collide with each other.

## Automatic School IDs for new Deans and Registrars

IT Admin > Add account: for Dean and Registrar the School ID box is disabled and the next free ID is assigned
(D1002, D1003 ...; R1002 ...), never duplicating an existing one. Login is UPHM-<ID>.
`python manage.py renumber_deans` (preview) / `--apply` moves the older deans (CAS, CBA, NURS ...) to D1002, D1003 ...

## SHS / JHS term structure

* JHS (Grades 7-10): 3 terms per school year (the 1st-4th quarters are retired and hidden).
* SHS Grade 11: 3 terms. The 5 core subjects (stored as "Whole school year") keep the same teacher, room, day and time in every term
  (the first generated term is copied into the others); strand electives are set per term (Term 1-3).
* SHS Grade 12: 2 semesters, unchanged.
* One place defines this: `backend/basic_ed/structure.py` (and `frontend/src/utils/terms.js`). Curriculum import / entry, validation,
  schedule generation, the dropdowns, run lists and the PDF header all follow it. Existing data is kept.
* Existing database: `python manage.py setup_basic_ed_terms` (preview) then `--apply` (renames Grade 11 electives Semester -> Term,
  adds Term 3 electives to edit, lists lines outside the structure).
* Curriculum import template: `grading_period` = term 1-3 (JHS, Grade 11) or semester 1-2 (Grade 12); 0 = whole year.

## Rooms by department (GTI class program), student headcount, navigation

**New tables** (run `python manage.py migrate`, rooms 0004): `DepartmentRoom` (a department's home/preferred rooms)
and `DepartmentEnrollment`.

**Rooms.** `rooms/gti_data.py` holds the room assignments read from the GTI Class Program workbook, so the XLSX is
not needed at run time. `python manage.py setup_rooms` previews; `python manage.py setup_rooms --apply` creates any
missing room, labels it (Comp Lab C (307D), Comp Lab D (309D), HJ, Kitchen 1/2 ...), reserves it for its department
and records each department's home rooms. It is idempotent. 304D (NSTP office) and 305D (IT office) are kept as offices and never scheduled. Capacities of newly created rooms are estimates: correct them in Admin > Rooms.
Reserved: Computer Studies (307D, 309D), IHM (HJ, Kitchen 1, Kitchen 2), Radiologic Technology, Nursing,
Allied Health rooms per the workbook. Other departments prefer their GTI rooms but may use shared rooms.

**Capacity.** Dean > Rooms > "Students per year level": enter the headcount per year, press "Update section sizes".
The scheduler only uses rooms that seat the section; if none does, the largest room is used and the class is flagged.

**Navigation.** Admin, Dean and Registrar sidebars are grouped: Plan, Academics, People, Insights (Admin: Insights, People, Data).

**Major lectures in the department's own rooms.** A MAJOR lecture of a department that owns labs (Computer Studies: Comp Lab C / D)
is placed in those rooms first; Gen Ed lectures never use a department lab. Run `setup_rooms --apply` before generating.

**Change day / time, one class at a time.** Tick classes > "Change day / time". Click a class, pick its day and a free time, click "Next class".
Each choice is checked live (`POST /engine/reschedule/` with `preview: true`, which never saves) against teacher, room and students,
including the other classes being moved in the same window. "Save" is enabled only when nothing conflicts; untouched classes stay as they were.

**Duplicate programs.** `python manage.py merge_duplicate_programs` (preview) / `--apply` merges a misspelt copy
(e.g. "BS Physical Theraphy") into the correct program, moving its subjects, sections and schedules first.

**Speed of Change day / time.** Checks are now read-only and in memory: one query loads every class on the affected days, so a
check of any number of classes takes about 3 queries (was dozens per class, inside a temporary write that was rolled back).
Saving re-checks the same way and then writes once. Messages name the other class ("Room X is already used by ...").

**Schedule previews and PDFs.** Class, exam and basic-education PDFs print "Year Level | Semester (or Term) | Academic Year"
directly under the department name (exam PDFs also print the department name). The preview tab is the same PDF.

**Class list upload (Dean > Class Lists).** Choose program and semester, upload a .csv/.xlsx with the columns Full Name, Section, Year Level
(a template can be downloaded), press "Check file" to see what will be added and which rows have problems, then "Import".
No School ID is asked for (an internal reference is generated). Rows are matched to existing sections of that program, year level
and semester; unmatched rows are reported, never guessed; names already on a section's list are skipped. A section's size is raised to
its real class list size when that is larger (it is never lowered). The schedule PDF now prints the
"Year Level | Semester | Academic Year" line under the title, above the table.

**Errors.** A failed request no longer crashes the page with the red "Uncaught runtime errors" overlay: `utils/globalErrors.js` shows a small
message naming the request (e.g. "You are not allowed to do that (403) - GET /engine/students/"). An expired session (401) returns to the sign-in page.
Screens that load data in an effect no longer return a promise from the effect (React expects a cleanup function there).
