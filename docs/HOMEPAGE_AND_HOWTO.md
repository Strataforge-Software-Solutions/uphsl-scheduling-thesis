# Homepage, How-to panels, Rooms and the curriculum preview

**Homepage** ("Welcome to U-FAST Scheduling System") is the first tab for the Dean, Registrar, SHS Principal and JHS Principal.
It shows statistics, pending tasks, scheduling status, the latest notifications and a quick-link card per tab with step-by-step help.
Code: `HomePage.js`, `HomeWrappers.js`. Data comes from existing endpoints (schedules, conflicts, overload-summary, basic-ed overview, notifications).

**How to Use This Tab**: a collapsed panel under every tab's header (`HowToUse.js`). All text lives in `howto.js`, which the Homepage cards also read.

**Rooms tab removed** from the Dean and Principal navigation (the Admin dashboard keeps its Rooms tab). Room data is unchanged:
- Dean: Schedules tab, section "Room assignments" (preferred / alternative / fixed rooms and the college's room records).
- Principal: Settings tab, section "Rooms" (room records).
- Generate preview: every subject has a **Room** dropdown (existing room records; lab subjects list labs, lectures list non-lab rooms), **Start Time** and **End Time** (7 AM – 8 PM, "Any time" by default).
  Sent as `room_choices` and `time_windows`; the server validates them (room exists, may be used by the department, right kind; End later than Start) and rejects with 400 before saving anything. A window that nothing fits is reported as an unplaced class with the reason. The window is also respected by the automatic re-arrangement.
  Endpoint for the dropdown: `GET /api/rooms/preview-choices/?program_id=`.

**Pop-up after Generate**: conflicts, unplaced classes, overloaded teachers or a failure open a visible dialog with buttons (Resolve conflicts, Fix unplaced classes, View Suggestions). Confirmed changes refresh the schedule, workloads and analytics through the existing `workload-changed` event.

## Break time (SHS vs JHS)
- **SHS**: one 30-minute break per day (`GradeWindow.break_start/break_end`), no separate recess / lunch. Defaults: Grade 11 9:30-10:00, Grade 12 3:00-3:30 PM. School hours: Grade 11 7:00 AM-12:30 PM, Grade 12 12:30-6:30 PM (6 periods of 50 min each). Migration `0003_shs_single_break` converts existing SHS windows (and restores the 12:45 stretch to 12:30) without touching anything else.
- **JHS**: recess and lunch unchanged.
- The generator never places a class in a break (periods skip it), the validator flags any class overlapping a break, a break outside school hours, a missing break, and an SHS break that is not exactly 30 minutes. The Settings API refuses these too, and drops recess / lunch for SHS and the single break for JHS.
- Homepage, per-tab instructions, pop-ups and Rooms-in-Settings already apply to both Principal dashboards (see above).

## Room dropdown (all scheduling screens)
`RoomSelect.js` replaces the plain Room selects in: Generate preview (Dean / Registrar), schedule edit modal, Dean Room assignments (preferred room), exam room, and the SHS / JHS period editor. It has a search box (name, label, building, room number: "309", "D-309", "309D", "lab c", "alta"), shows `name (capacity)`, keeps the Automatic option and the preferred / alternative / fixed markers, and changes nothing by itself: the server still checks availability, capacity and conflicts on save.
Migration `rooms/0005_ensure_computer_labs_c_d` makes sure Comp Lab C (D-307) and Comp Lab D (D-309) exist: found by name, label or building + number, reused as they are, created (lab, 40 seats) only if missing.

## Room records: IT Admin only
- Admin dashboard -> **Rooms** (`AdminRooms.js`, API `/api/rooms/admin/rooms/`): add, edit, view, search and delete room records. A room with scheduled classes cannot be deleted (it would delete those classes).
- Deans and the Registrar can only read rooms: every write on `/api/rooms/` and the old `/api/rooms/dean/rooms/` endpoints now returns 403. Their dropdowns (Generate preview, edit window, Room assignments) read the same records.
- Dean -> Schedules -> Room assignments: the "Subject rooms" table is empty until a program is chosen in its own dropdown; then it lists that program's subjects with year/semester, preferred, alternative and fixed room. Building preference and students-per-year stay.

## Live statistics and deletion
- Dean / Registrar Home: `GET /api/engine/dashboard-stats/` counts class periods (by status), conflicts and overloaded teachers from the database on every call (`Cache-Control: no-store`); with no schedules it returns 0 without scanning. SHS / JHS Home: the existing `basic-ed/overview/` (runs, periods, pending, open conflicts), reloaded the same way.
- The Home pages refresh when the tab opens, after ANY successful schedule change (generate, edit, approve, delete, resolve, clear: `schedules-changed` fired by the API client), when the window regains focus, and every 30 s.
- Deleting classes (Remove, Admin > Data Tools, `clear_generated`) now calls `engine/housekeeping.py`: conflict-log lines of sections with no classes left are deleted (all of them when no classes remain) and schedule / conflict / substitute notifications are deleted when no classes remain (exam-assignment ones when no exams remain). Curriculum, faculty, rooms, accounts and historical workload records are never touched.

## Schedule problems pop-up and Smart Resolve

After **Generate**, any unplaced class or clash opens one pop-up (also reachable from the "Review N problem(s) in a pop-up" button). Each row shows subject
code and name, year level, section, why it is a problem, and the room and time it has now ("Not placed yet" for unplaced classes).

**Resolve** lists the days and times that are really free for that class **in its current room**:
- the teacher is available (submitted availability) and has no other class then;
- the room has no other class then;
- the section's students have no other class then (within the configured tolerance);
- for a class that is not placed yet, the teacher also stays within the weekly workload limit.

The Dean picks one and presses **Apply / Confirm**. The server derives the options again, takes the scheduling lock, saves only this class, re-scans
for clashes and rolls everything back if anything is wrong (a time taken meanwhile gives "no longer available" and a refreshed list).
The room is never changed; a class with no room yet uses its preferred / selected room. If nothing is free the pop-up says why (counts of
times lost to teacher availability, teacher, room, students, workload) and the conflict stays active. Approved/published/shared classes
and classes owned by another account are refused. Dashboards, notifications and the problem lists refresh after applying.

Endpoints: `POST /api/engine/slot-options/` and `POST /api/engine/slot-options/apply/` (code in `engine/reschedule.py`).

## Generation rules: chosen room, qualified faculty, half-hour windows

* **Chosen room stays.** A room picked in the curriculum preview is a hard rule for that run (also while unplaced classes are re-arranged). The engine searches
  every other day and time inside the chosen Start/End window in that room, around Gen Ed, other majors, teachers and sections. Approved/published classes are
  never moved. A class is reported only when no valid day/time exists, with the specific reason (window too short for an unbroken 3 h lab, no qualified teacher
  free inside the window, room taken at every such time). It is never put in a different room.
* **Qualified faculty only** (`engine/qualification.py`, one rule for generate / Resolve / re-arrange / explanations): the subject's field is in the teacher's
  specializations; or the teacher's degree / specialization / qualification belongs to the same discipline (BSIT, MSIT, AI ... for Computer Science and
  Information Technology; Physical / Occupational / Respiratory Therapy for those programs; Anatomy, Physiology, Kinesiology,
  Neurosciences, Pathophysiology, Pharmacology, Cardiopulmonary, Psychiatry / Mental Health, Orthotics & Prosthetics, Electrotherapy,
  Research for subjects with those words, matched as phrases: `PHRASE_FAMILIES`) or relates to the subject. A MAJOR subject goes only to a teacher of its own college, even when another college's teacher has
  the matching specialization (Gen Ed subjects may use any college's qualified teacher). The old "if nobody matches, use everybody" fallback is gone: when nobody qualifies the report says
  so ("No qualified faculty for CS1102 ...: add the specialization / degree in the Faculty tab or tag the subject's field").
* **Start/End follow each other** (`utils/timeWindow.js`): with a Start picked, End offers only Start + the subject's need and later (30-minute steps, to
  8:00 PM); with an End picked, Start offers only times at least the need before it. Picking a Start fills an "Any time" or too-short End with the earliest
  valid End (with a short note); "Any time" stays available for both. The hint under the row reads e.g. "Needs 2 hrs - earliest end 12:30 PM", plus the chosen
  professor's free windows ("Mazo, J. free Mon 10:00 AM-1:00 PM ..."); times outside them are marked "(outside professor's time)" but stay selectable, and a
  (The former 'lunch break' note was removed: noon is ordinary class time.) Advice only: the server's checks are unchanged.
* **Why a class in a chosen range was skipped** (`engine/blockers.py`, reporting only): every period of the needed length on the 30-minute grid inside the
  range, each day, is checked and the message names what rules each one out: a missing or irregular time slot, the section's own class,
  the professor's availability (only where a period exists and the professor is outside it), the professor's other class, the weekly limit, room capacity,
  or the allowed rooms being booked (each room and class named). The professor's time is never blamed when the professor is free in that range.
* **Start/End dropdowns** list every 30 minutes (7:00 AM, 7:30 AM ... 8:00 PM); the End list only offers times after the Start. When the range is shorter than
  the subject's longest unbroken period, the row turns red with e.g. "Needs 3 hrs in one block; this range is 2 hrs." and Generate is disabled, naming the
  rows to fix. The length comes from the server (`Subject.need_minutes`, read-only, from `engine.scheduler.window_need_minutes`): a lab = 3 h, a lecture = its
  units up to 3 h, a Nursing-style 3-unit lecture = 1.5 h (two sessions). The server still rejects a too-short window before anything runs; the hint only
  shows the same rule early (`frontend/src/utils/timeWindow.js`, tests in `timeWindow.test.js` and `engine.tests.TimeWindowRuleTests`). A window on a half hour uses extra
  blocks built from the 30-minute time slots (run `seed_timeslots`, without `--no-half`, if they are missing); hourly windows behave exactly as before.
  College lunch/closed hours are not time slots, so a class never crosses them. SHS/JHS dashboards use their own Basic Ed engine and are unchanged.

## Needs column and room free hours (Generate preview, read-only)

* **Needs**: per subject, hours per week (lecture units + 3 h per lab unit), Lecture / Lab / Lecture + Lab, and the number of sections of that year level
  and semester (all sections; the Professor column's hours leave out sections locked by hand).
* **Room list**: `GET /api/rooms/preview-choices/?program_id=&year_level=&semester=` (Dean / Registrar, no database writes) now also returns
  - `free_hours` / `total_hours` per room and `week_hours` (`rooms/usage.py`): the week is the time-slot grid with each day's slots merged (hourly and
    half-hour slots count once); used = the times the room is booked by classes of that semester (any status), merged the same way, so a shared class counts once;
  - `allowed: {subject_id: [room ids]}`: the rooms Generate accepts for each subject of the run, from the same check Generate uses
    (`engine.views.room_choice_error`: role, designated Comp Lab C / D for Computer Studies majors, reserved rooms, room type). Nothing about the rules changed.
  Without these parameters the endpoint answers exactly as before. Basic Ed (SHS/JHS) timetables are not counted in the free hours.
* Tests: `engine.tests.RoomFreeHoursTests`, `engine.tests.DesignatedRoomFreeHoursTests`.

## BS Respiratory Therapy curriculum (Allied Health)

`python manage.py seed_resptherapy_curriculum` (dry run) / `--apply`: 68 subjects in the department BS Physical / Occupational Therapy use
("College of Allied Health" live). RT3118L is imported as RT3117L (lab of RT3117); RT4128 / RT4231 internships (15 units, off campus) are
not imported; the RT majors get the field "Respiratory Therapy"; no rooms, faculty or schedules are created.
`--sections` (dry run) / `--sections --apply [--students 30,28,25,20]` adds only the missing sections, one per year level and semester
(B.c1 ... B.c4); existing sections and their student counts are kept. Live: added with 30 / 28 / 25 / 20 students (placeholder, same as
BS Occupational Therapy; the Dean sets the real enrollment). Separate from
BS Radiologic Technology. Tests: `curriculum.tests`.

## Faculty availability and skipped classes (Generate)

* **Availability is a hard rule** (`engine.views._build_availability_rules`): a teacher is placed only inside their submitted
  "preferred" / "available" windows and never inside an "unavailable" one; a teacher with no submission is free at any time.
  Availability saved without a school year / semester now applies to every term (it used to be ignored once the term was known, so
  such a teacher was treated as free all week). Read through `engine/availability.py`, used by Generate, the Gen Ed batch, the day /
  time picker and the replacement suggestions alike.
* **Preferred first (soft)**: among the times that are already allowed, a time inside the teacher's "preferred" window is tried first
  (`availability.outside_preferred`, part of the value ordering only). It never removes a time and does not change the Greedy order in
  which subjects are placed.
* **Skipped, never forced**: every class that can be placed validly is saved as Draft; a class that cannot is skipped. One pop-up,
  "Some classes were not placed", lists code, subject, section, year and the specific reason (`explain_unresolved`), e.g.
  "No qualified teacher can take it: J. Mazo is available only Sat 7:00 AM-4:30 PM. This Lecture needs one 2-hour block inside your
  1:00 PM-5:00 PM range when the section is free." It has only an OK button: no suggested times, rooms or professors, and nothing that
  changes the schedule (`engine.views.plain_reason` drops the "pick a suggested time" sentences from these reasons).
* **Real clashes** found by the scan after generating (which should not happen) are shown in a red box with "Review conflicts".
* **Not generated yet**: the Generate dialog and the Dean's Schedules tab list the program's classes that still lack hours, with the
  reason recorded the last time they could not be placed (`GET /api/engine/unplaced/` now returns `code`, `title`, `section_name`,
  `reason`; read-only). "Not generated yet." means no attempt was made.
* **Generate only the missing ones** (`only_missing: true` on Generate): places only the classes still missing hours. Complete classes
  stay exactly where they are (draft, hand-edited, approved, published, shared) and count as booked; a partly placed draft is redone
  as a whole; a partly placed locked / approved / published / shared class is reported, not changed.
* **Smart Resolve is still there** (not opened by Generate any more): Conflicts tab > Review / fix; Schedules tab > Edit > "Choose a new
  day and time"; "Review conflicts" in the red clash box; Registrar > Gen Ed schedules > place the unplaced classes (`UnplacedResolve`).
* Tests: `engine.tests.FacultyAvailabilityGenerationTests`.
* **Faculty time (info button next to each Professor dropdown)**: a pop-over with the teacher's week as a table, one row per day
  (Monday-Saturday): submitted availability, classes already taught, and the suggested free time (available / preferred windows
  minus unavailable time and their classes; nothing submitted = 7 AM-8 PM minus classes; ★ = preferred). Previously an hour grid:
  preferred / available / unavailable / outside their availability, "No availability submitted (free at any time)" when nothing was
  submitted, the classes they already teach (back-to-back hours merged, a shared class once) and weekly load vs limit. Read-only
  `GET /api/engine/generate/faculty-time/?faculty_id=&semester=[&program_id=&year_level=]`: a Dean only for faculty of their own
  college, the Registrar for any active faculty, nobody else; no database writes. With program + year level, the drafts this Generate
  would replace are not counted (same numbers as the Professor list). Tests: `engine.tests.FacultyTimeEndpointTests`.
* **Suggested professors**: the Professor dropdown groups the (already qualified) teachers into "Suggested" and "Other qualified".
  Suggested = this row (every section) plus the other rows chosen for them stays within their weekly limit, AND their free time holds
  every class block of the row for every section inside the row's Start-End range; ranked by overlap with their "preferred" time, then
  lower load, with why ("Free Tue 8:00 AM-12:00 PM · 11 of 24 hrs"). Others stay selectable with a badge ("No matching free time" /
  "Over weekly limit"). Free time comes from the Professor list endpoint (`free`, `preferred`, `submitted` per teacher; `blocks` per
  subject; `engine.professor_choice.free_week`): the time-slot grid inside their availability minus the classes they teach. Rooms and
  the section's other classes are NOT considered, so it is advice only; Generate re-checks everything and skips with the reason.
  Code: `frontend/src/utils/suggestProfessors.js` (tests `suggestProfessors.test.js`), `engine.tests.SuggestedProfessorDataTests`.

## Class schedule PDF (portrait)

* Print / Preview (Dean and Registrar, `PrintPreviewButton.js`) first asks for the year level: 1st, 2nd, 3rd, 4th Year, or
  "All year levels (1st - 4th)". The other filters (program, semester, status, Gen Ed / program, college) still apply.
* `backend/engine/pdf_export.py` (layout only): **A4 portrait**, 0.5 in margins.
  * "All year levels": ONE year level per page (page 1 = 1st Year, 2 = 2nd, ...; a year level without classes is skipped, no blank
    page). Every page has the school header and its heading ("BS Computer Science - 1st Year - 1st Semester, A.Y. 2026-2027").
    The signatory block appears ONCE, directly below the table of the last page.
  * One year level: one page with its signatory.
  * Each page is measured before printing: row padding, then the font, are reduced (text 9 pt down to 8 pt) until it fits. About
    24 rows with a Lec / Lab note on every row (28+ without notes) fit one page; a longer year level continues on the next page
    (rows never split, header row repeated) with the signatory kept with its last rows, and is logged (year level + row count).
  * Day & Time is sized to its longest text so "Wed 10:00AM-12:00PM" stays on one line (the width comes from Subject).
  * Signatories: "Prepared by" = the Dean account of each college in the PDF; "Approved by" = `SCHOOL_DIRECTOR_NAME` in that file.
  Tests: `engine.tests.SchedulePdfLayoutTests` (cases a-e), `PrintPreviewButton.test.js`.

## Gen Ed move requests (Dean -> Registrar)

* A Dean presses **Request move** on a Gen Ed class of their own college (Schedules tab), picks one of the times the Registrar could
  move it to (`POST /api/engine/gened-requests/options/`: the Registrar's own clash-free list -- same teacher and room, every attending
  section free) and gives a reason. Nothing moves; the Registrar is notified (`engine/gened_requests.py`, model `GenEdMoveRequest`).
* The Registrar sees "Gen Ed move requests from the Deans" on the Schedules tab: **Approve & move** re-checks every schedule at that
  moment (`engine.reschedule.apply`: lock, fresh rows, conflict scan, undo on any clash) and moves ONLY that Gen Ed class (all sections
  of a shared class together). Another Dean's major or any other class is never moved or overwritten: if the time was taken meanwhile,
  the request becomes "Could not be applied" and nothing changes. An approved / published class must be moved back to Draft first
  (the request stays pending). **Reject** declines; the Dean can **Cancel** a pending request. The Dean is notified of the outcome.
  Tests: `engine.tests.GenEdMoveRequestTests`, `GenEdRequests.test.js`. Run `python manage.py migrate` once (new table).

## Faculty availability is a preference (not a limit)

* A teacher's **preferred** and **available** windows no longer close the rest of the day. Generate tries, for each class, a time
  inside their preferred window first, then their available window, then any other open time (`engine/availability.py` tiers 0/1/2,
  used in the value ordering only). Only times the teacher marked **Unavailable** stay closed for Generate
  (`engine.views._build_availability_rules`).
* **By hand**, a Dean / the Registrar may place a class at any time where nothing clashes (teacher, room, students): "Choose a new day
  and time" lists every clash-free time, the teacher's preferred / available ones first, then those marked "outside their
  availability" and last "marked UNAVAILABLE by the teacher" (`engine/reschedule.py`). Changing a shared class's teacher works the same
  way (`engine/shared_edit.py`). Room, teacher, section and Lecture-before-Lab rules are unchanged.
* The Faculty time pop-over shows "Best time (their preference)" and "Also possible" for each day.
* **Assign from the Faculty time window (Dean):** each free time long enough for the subject is clickable; choose the start and
  "Assign to this time". It fills the row's Professor, **Day** and Start / End (nothing saved yet). Generate sends
  `time_windows[sid] = {start, end, day}`; the day is a hard choice for that subject only (`rooms.rules.day_choice_for`, used by
  `build_domain`, the skip reason and the blocker report). Tests: `AssignedDayTests`, `FacultyTimePopover.test.js`.
  Tests: `engine.tests.AvailabilityAsPreferenceTests` (and the updated availability tests).

## Editing a shared (merged) class

* A shared Gen Ed class (several sections, one `Schedule.merge_key`) is edited as ONE class by the Registrar: the Edit dialog says
  "Shared class: A.b2 + A2 · 51 students" and a new teacher or room (`POST /api/engine/shared-classes/edit/`, `engine/shared_edit.py`)
  or day / time ("Choose a new day and time", `engine/reschedule.py`) is applied to every attending section together, so it stays shared.
* Checked for the whole group before saving (all or nothing): owner (Registrar), all rows Draft, the teacher qualified for every section
  (CAS rule), available, free and within the weekly limit; the room allowed for every college and seating all students together; every
  section free at a new time (Lecture before Lab kept); a conflict scan before / after (no new clash) and the generation lock.
* A single row of a shared class is still never changed alone (PATCH is refused). Edited rows get the "Edited" lock so Generate keeps
  them. Tests: `engine.tests.SharedClassGroupEditTests`.

## Major subjects: discipline families for every college

* `engine/qualification.py` `MAJOR_FAMILIES` (majors only): Nursing, Radiologic Technology, Business, Hospitality / Tourism and
  Communication, next to Computing, Mathematics and Allied Health. A teacher of the subject's own college whose degree / specialization
  is in that discipline qualifies (e.g. "BS Radiologic Technology" / "Radiographic Positioning" for RAD1101). The same-college rule and
  the Gen Ed (CAS) rule are unchanged. Before this, 226 majors (BA Comm, BSBA, Hospitality, Tourism, Nursing, RadTech) had nobody
  qualified because none has a field recorded; after it, 0. Tests: `engine.tests.ProgramDisciplineFamilyTests`.
* Faculty saved as "Radiologic Technology" / "Nursing" (without "College of") are not counted in their college:
  `python manage.py prefix_departments` (preview) then `--apply` renames them consistently everywhere.

## No fixed lunch period (college)

* 12:00-1:00 PM is an ordinary class time on every day (Mon-Sat): classes may start, end or run through noon. Lunch is whatever free
  time a section or professor has between classes; no lunch entry is ever created. `seed_timeslots` now includes noon (`--lunch 12`
  gives the old behaviour); re-running it on an old database adds the missing 12:00-1:00 PM slots and changes nothing else.
* **Reserve lunch gap (optional)**, Workload settings, OFF by default (`SchedulingConfig.reserve_lunch_gap`, `engine/lunch_gap.py`):
  when on, among placements that already pass every hard rule the scheduler tries first those leaving the section and the professor
  a free hour between 10:30 AM and 2:30 PM that day. It never skips a class: where no gap is possible the class is placed and Generate
  shows an amber "Lunch gap" warning (`lunch_gap_warnings`). No skip reason mentions lunch any more.
* The period builder skips an irregular overlapping slot (e.g. Wed 11:30-12:30) instead of stopping, so it no longer hides valid periods.
  Tests: `engine.tests.NoFixedLunchTests`.

## Gen Ed subjects are taught by the College of Arts and Science

* **Rule** (`engine/qualification.py` `is_qualified`, used by generation, the skip reasons, Smart Resolve, the Edit dialog list, Save,
  and the Gen Ed overload / replacement suggestions): a Gen Ed (minor) subject goes to a **College of Arts and Science** teacher whose
  degree / specializations are in the subject's area (`GEN_ED_AREAS`: FCL, Filipino, Literature, English, Purposive Communication,
  Mathematics, Science, STS, PE, NSTP, History, Ethics, Arts, Psychology, Gender, Computing), matched from the subject's field and title
  (the curriculum's Gen Ed subjects have no field recorded). A teacher of another department qualifies only with an explicit
  specialization naming the area (e.g. "Science, Technology and Society") or the subject's own discipline (a mathematics specialist for
  Mathematics in the Modern World, a computing teacher for Living in the IT Era). The old "no field -> any teacher" fallback is gone.
  When nobody qualifies: "No CAS faculty with a Literature specialization is available for GE602 ...". Majors are unchanged.
* **Existing classes are not changed.** `python manage.py audit_gened_teachers` (read-only) lists each Gen Ed subject with its qualified
  teachers (`--coverage`, gaps marked `!!`) and every existing Gen Ed class held by a teacher the rule does not allow (`--classes`).
* **Demo CAS faculty**: `python manage.py add_cas_gened_faculty` (dry run; `--apply` saves) adds only what is missing so FCL,
  Literature, Science, PE and STS each have a full-time and a part-time teacher; STS tags existing related teachers with the
  "Science, Technology and Society" specialization. Next free F / P IDs, password = school ID, must change on first login, no deans.
  Tests: `engine.tests.CasGenEdRuleTests`, `CasGenEdFacultyCommandTests`.

## Teacher lists: department faculty only, searchable (Edit, Generate, overload)

* **One rule** (`engine/teacher_scope.py` `teacher_allowed`): a Dean's major class goes only to qualified faculty of the Dean's own
  department(s) (`User.departments`, incl. `extra_departments`) under `engine.qualification.is_qualified` (which also requires the
  subject's college; a Dean heading two colleges sees each college's faculty for that college's subjects). Gen Ed (the Registrar's)
  keeps "any qualified teacher". Checked on the server by Edit -> Save (`ScheduleViewSet.perform_update`), Generate's professor check,
  `workload/overload-assign/`, `replacements/assign/` (which had no qualification check before) and the Smart Resolve teacher edit.
  The other Save checks (clash, availability, weekly limit, designated rooms, locked / approved / published / shared) are unchanged.
* **Edit dialog teacher list**: `GET /api/engine/teacher-options/?schedule_ids=1,2` (read-only, writes nothing): only the allowed
  teachers, each "Santos, J. - 11 of 24 hrs", "Suggested" = free at that day / time and within their limit. A current teacher the rule
  no longer allows (older data) is named under the field, never offered.
* **Replacement suggestions** (`workload.suggest_replacements`: overload plan, workload replacements, teacher-leaving list, the Edit
  dialog's overload box, Generate warnings, Smart Resolve): for a major only qualified faculty of the same department, free then and
  within their own limit after the class, lower load first; nobody from another department, no fallback. When nobody fits:
  "No available faculty in your department (...): Name - not qualified for X; Name - not free at that time (already teaching ...);
  Name - would exceed their limit (...)". Gen Ed suggestions are unchanged.
* **Searchable picker** (`frontend/src/components/TeacherPicker.js`), shared by the Edit dialog, the Generate Professor column and the
  overload picker: type a name, employee ID or username (case, accents and extra spaces ignored); arrow keys, Enter, Esc;
  "No teacher found"; "Suggested" first. Tests: `TeacherPicker.test.js`, `engine.tests.DepartmentTeacherScopeTests`.
* Not changed (open decisions): absence coverage ("suggest substitute") still picks from every college; `/api/faculty/profiles/`
  still lists every teacher.

## Professor per subject (Dean's Generate preview, optional)

* The Professor column (default **Automatic**) lists, per major subject, only the qualified faculty of the Dean's own college, from the read-only
  `GET /api/engine/generate/professor-options/?program_id=&year_level=&semester=` (Dean only; no database writes). Each option shows the current weekly load
  and limit, e.g. "Santos, J. (11 of 24 hrs)", counted with `engine/workload.py` (shared classes once). Drafts that this Generate would replace are not counted;
  classes locked by hand, approved and published ones are.
* A choice is sent as `teacher_choices: {subject_id: faculty_id}` with Generate and is re-checked by the server BEFORE any draft is replaced: Dean only,
  teacher of the program's college, qualified (`engine/qualification.py`), has some available time in the semester, and a Lecture and its Lab get one
  professor (choosing one covers both; two different choices are refused). A refused choice changes nothing.
* For that run the chosen professor is FIXED for the subject's sections, like a fixed room: the engine may use that teacher and nobody else for it
  (`rooms.rules.teacher_choice_for`). When a class cannot be placed, the problems list names the professor and the reason (already teaching then, outside
  their availability, over the weekly limit under the strict policy, Lec/Lab partner has another teacher). Nobody is swapped in silently.
* The row warns before generating when the chosen professor's current hours plus every row chosen for them (hours per week x sections) would pass their limit.
  Under the "warn" policy Generate still places the classes and shows the usual overload warning; under "strict" the classes over the limit are not placed.
* If no qualified teacher exists the dropdown stays on Automatic and shows the "No qualified faculty ..." reason.
* Code: `engine/professor_choice.py`, `engine/views.py` (`professor_options_view`, Generate), `engine/scheduler.py` (`build_domain`, `explain_unresolved`),
  `frontend/src/components/GenerateSchedulePanel.js`. Tests: `engine.tests.ProfessorChoiceTests`.

## Shared minor classes (chosen before generating)

Every minor lecture subject can be set to **Automatic** (the original behaviour), **Exclusive** (this program keeps its own class) or **Shared** by 2 or 3 programs.
The Registrar sees a "Shared Class / Programs" column in the curriculum preview; a Dean sees a card of the Gen Ed subjects of the chosen program under the preview.
The pop-up lists every program that has the same subject (code, title, lecture/lab units, minor, year level and semester) with its department, year level, semester,
sections and enrolment, then checks the choice on the server: 2-3 programs, identical curriculum details (otherwise "its curriculum differs"), combined enrolment against
the largest lecture room all of them may use (sections are paired so each shared class fits; leftovers keep their own class and are listed), and that a qualified
teacher exists. Labs are never shared. Nothing is merged when details differ.

Confirmation: a group inside the confirming Dean's own college is confirmed at once; a group that includes another college's program is saved and waits for the
Registrar's Confirm (only confirmed groups are used). A Dean can only choose for programs of their own college.

Generation: generating the host program makes ONE class (one qualified teacher, one room sized for all members, one conflict-free time that is also free for every
member section) and gives each participating section the same teacher/room/time (`merge_key`), so no duplicate classes. The result lists the participating programs
and any section that could not join (and why). The existing teacher/room/student checks, workload limits and the clash scan still apply. Curriculum records, sections and
students are untouched; regenerating replaces the drafts instead of stacking copies. A member section that already has its own class of that subject is not changed
(clear it first). The batch "Generate all minor subjects" honours the same choices.

API: `GET /api/engine/shared-classes/options/`, `POST .../validate/ | save/ | exclusive/ | clear/ | confirm/`. Code: `engine/shared_classes.py`.

## Generate: suggestions instead of automatic moving (updated)

* **Nothing is re-arranged by itself.** Generate places what fits in the room and Start/End time chosen in the preview (greedy, most-constrained
  first, as before). A class that does not fit is NOT placed somewhere else and NO other class is moved for it (the automatic
  `placement.resolve_groups` call after generation was removed). It is listed with its reason.
* **The pop-up shows the owner's choice**: "Your room / Your time / Why", and immediately looks up free days and times with
  `POST /api/engine/slot-options/` in that order: (1) same room, inside the chosen time; (2) same room, other times; (3) other rooms only when
  the subject permits (never for CS/IT majors). Clicking a suggestion opens it; nothing is saved until **Apply / Confirm** (`slot-options/apply/`,
  which re-checks every rule and rolls back on any clash). Each unplaced class appears once (per section), not once per block.
* Generate response: each `conflicts[]` row also has `classification`, `department`, `chosen_room_id`, `chosen_room`, `chosen_start`, `chosen_end`.
  `auto_resolved` is kept in the response for compatibility and is always empty.
* The Generate result no longer has "Resolve all conflicts" (which changed teacher / room / time on its own); conflicts are reviewed in the pop-up.
  The Registrar's Minor Schedules "Resolve" buttons are unchanged.

## Faculty for major subjects (updated)
Only a teacher with the subject's field as a recorded specialization, or a same-discipline degree inside the subject's college, may teach a
major. Being in the same college, or one word of the title matching a degree, is no longer enough. A major with no field tagged and no
same-discipline teacher is reported ("tag its field in the Curriculum tab"). Gen Ed rules are unchanged.

## Shared Gen Ed classes: Registrar only (updated)
Minor subjects belong to the Registrar, so only the Registrar saves, clears, makes exclusive or confirms shared classes (`engine/shared_classes.py`
`_may_edit`). Deans see a read-only list under their preview. Groups saved by a Dean earlier are kept; unconfirmed ones still wait for the
Registrar's Confirm.

Tests on this computer (SQLite in memory, never Supabase): `python manage.py test --settings=config.settings_test`.

## Conflict Checker: suggest-then-confirm (updated)
Conflicts tab (Dean and Registrar), `ConflictChecker.js`. It still scans the whole semester for teacher / room / student double-bookings
(`GET /api/engine/conflicts/`). "Fix this conflict" and "Review and fix conflicts" now open the same pop-up as Generate
(`ScheduleProblemsModal`): for each side the owner chooses which class to move and sees only free days / times for it (same room first,
other rooms only if the subject permits). Nothing is saved until Apply / Confirm; the server re-checks and rolls back on any clash, and the
schedule is scanned again afterwards. Approved / published / shared sides and other owners' sides are labelled and cannot be moved from here.
Scan rows now include `status` and `shared`. The old automatic endpoint `POST /api/engine/conflicts/resolve/` is kept on the server but no
screen calls it.

## Schedules tab: Select, Approve, Remove, Edit, History (Registrar and Dean)
Code: `frontend/src/components/ScheduleActions.js` (bar + dialogs, shared by `RegistrarDashboard.js` and the Dean's `FacultyDashboard.js`),
`backend/engine/schedule_actions.py` (the rules), endpoints on `/api/engine/schedules/`.

* **Select**: a checkbox on every class the user owns (Registrar = Gen Ed, Dean = own college's majors) and a "select all shown by this filter"
  box. A sticky bar shows "N selected: Approve, Publish, Back to draft, (Dean: Change day / time), Remove, Clear". Actions use the ticked rows
  only. The old "Approve All N Shown" buttons were replaced by select-all + Approve, so nothing is approved without being ticked.
* **Approve / Publish** (`POST approve_bulk/ {ids, to_status}`): on the server the selection is first run through the conflict scan
  (`conflict_report.scan`, the Conflicts tab's check) against the whole schedule. A class with any conflict is blocked as a whole and stays where it
  is; the answer lists "ready" and "blocked" classes with each reason. `approved_by` / `approved_at` record who and when (existing fields, no
  migration). The old scope form (program / year / semester) still works and runs the same check.
* **Back to draft** (`to_status: "draft"`): Approved classes only. Published classes stay published (their teachers were told they are final),
  and a class with a faculty-absence coverage stays approved (something depends on it).
* **Remove**: `POST remove_preview/ {ids}` lists exactly the classes and periods, the approved / published ones that will NOT be removed, and
  warnings (shared class used by other sections, coverage suggestions that Undo cannot bring back). `POST remove_bulk/ {ids, confirm_shared}`
  removes drafts only (a shared class needs the confirmation) and returns an undo token. `POST undo_remove/ {token}` restores the exact rows (same
  ids and fields) for 5 minutes, only for the same person, and only if nothing was booked into those times meanwhile. The snapshot is stored in
  the existing `Log` table. The single `DELETE /schedules/{id}/` now refuses approved / published classes too.
* **Edit**: drafts only (the server refuses editing or moving approved / published classes). Teacher and room are saved with Save (the teacher
  must be qualified: same rule as the generator). The day and time are no longer typed in: "Choose a new day and time" opens the Smart Resolve
  pop-up (`ScheduleProblemsModal` with `startWith`) that lists only free times, and the confirmation shows what changed ("Mon 8:00 AM–9:00 AM →
  Tue 9:30 AM–10:30 AM, room stays 307D, teacher stays …", `changes` in the apply answer).
* **Locked edits**: a class changed by hand (`is_manual_override`) is kept by Generate exactly where it is and counts as booked for everything
  else; the Generate result lists them ("kept_edited"). Untick "Keep the classes I edited by hand" (`keep_edited: false`) to place them again.
* **History**: `GET history/?ids=` lists created / changed / approved / removed events with who and when. A Smart Resolve move re-creates the
  periods, so the history of a moved class starts at that move (the move itself is recorded with the old and new time).

## Insight cards (read-only analytics) -- Stage 1: IT admin
New, additive, read-only (GET only; nothing writes to the database or calls the scheduler; the existing `/api/analytics/` output is unchanged).
Code: `backend/analytics/insights.py` (calculations, reusing `placement.incomplete_groups` and `conflict_report.scan`),
`backend/analytics/insight_views.py` (roles), `frontend/src/components/InsightCards.js`. IT admin only (403 for everyone else).

| Card (where) | Endpoint | Shows |
|---|---|---|
| System health (Admin > Overview) | `GET /api/analytics/admin/health/?semester=` | Unplaced classes (fewer hours than their units need, only in year levels that were generated; classes of never-generated year levels are counted separately), open conflicts by kind, open "could not place" log entries, rooms with no department (shared rooms; normal for lecture rooms), faculty with no specialization (and whether a degree is recorded), sections with no curriculum. |
| Account hygiene (Admin > Overview) | `GET /api/analytics/admin/accounts/` | Active accounts never signed in, disabled accounts, e-mails used by more than one account (case-insensitive), accounts still on the first password, accounts with no e-mail. |
| Audit trail (Admin > Activity) | `GET /api/analytics/admin/audit/?category=&limit=` | Log entries grouped as approved / published / back to draft / blocked approval / removed / restored (undo) / moved / edited / workload, plus "generated" rebuilt from the classes still in the schedule. |

Not recorded by the system (shown on the card): who ran Generate (a run writes no log entry; a class keeps only its creation time), Admin
"clear generated", and approvals made before the Schedules-tab update (only the latest approver and time on the class).

## Insight cards -- Stage 2: Deans (Dean > Analytics, under the existing charts)
Scope (server-side, `analytics/insight_views.college_scope`): a Dean sees only their own college(s) (asking for another with `?department=`
gives 403); the Registrar and the IT admin may read every college (or one with `?department=`); everyone else gets 403. All GET, read-only.

| Card | Endpoint | Shows |
|---|---|---|
| Readiness | `GET /api/analytics/dean/readiness/?semester=&program_id=&kind=major\|minor\|all` | Per program + year level + semester: classes (section x subject), Published / Approved / Draft (fully placed; a class counts at its least advanced period) and Unplaced (fewer hours than its units need, also year levels not generated), with a progress bar and % placed / % published. |
| Faculty fit | `GET /api/analytics/dean/faculty-fit/?semester=` | Major subjects no active teacher qualifies for (engine/qualification.py, the generator's rule), classes whose teacher does not meet that rule, and classes matched only by degree (the subject's field is not a recorded specialization). |
| Lab capacity | `GET /api/analytics/dean/lab-capacity/?semester=` | For the designated rooms (`rooms.rules.designated_rooms`: Comp Lab C / D for Computer Studies): hours booked vs free per day; free = the time-slot table's day span minus booked hours (overlaps and shared classes counted once). |
| Faculty load bands | `GET /api/analytics/dean/load-bands/?semester=&under_pct=50` | Overloaded (above the teacher's Settings limit) / normal / underloaded (below `under_pct`% of the limit: a review band only, the system has no minimum-load rule). "Resolve overload" opens the existing overload resolver. |

The load-bands card reads the Settings limits without creating the settings row (`workload.limits()` uses get_or_create), so it never writes.

## Insight cards -- Stage 3: Registrar (Registrar > Analytics, under the existing charts)
All GET, read-only. Gen Ed coverage and dependencies: Registrar and IT admin only (403 for Deans, principals, teachers). Room heatmap and
capacity use the college scope of Stage 2 (Registrar / IT admin: every college; a Dean: own college only).

| Card | Endpoint | Shows |
|---|---|---|
| Gen Ed coverage | `GET /api/analytics/registrar/gened-coverage/?semester=&department=` | Per Gen Ed subject (grouped like shared classes: same code, units, title): programs, sections, placed / not placed, sections in a shared class, classes held, classes saved (= sections placed - classes held) and weekly teaching hours saved. |
| Room utilization | `GET /api/analytics/room-heatmap/?semester=&room_type=` | Day x hour grid of the % of rooms booked (off-site rooms excluded), and the busiest hour. New `HourHeatmap` component (the existing `PatternHeatmap` only has Morning / Afternoon / Evening). |
| Cross-college dependencies | `GET /api/analytics/registrar/dependencies/?semester=` | Major classes (in generated year levels, not fully placed) whose section has no free window as long as the subject's longest block WITH its Gen Ed classes but would WITHOUT them; shared Gen Ed groups not yet confirmed. Only the Gen Ed effect is isolated: teachers, rooms and availability can still matter. |
| Capacity vs enrollment | `GET /api/analytics/capacity/?semester=` | Each class (a shared class once, all its sections' students added) against its room's seats: over capacity, under 50% full, rooms with no recorded capacity. |

## Insight cards -- Stage 4: SHS / JHS principals (Principal > Analytics, under the existing workload analytics)
Access uses `basic_ed.permissions` (the rule of every Basic Ed screen): a principal sees only their own level (asking for the other gives
403); the IT admin must say `?level=SHS|JHS` (400 otherwise); everyone else 403. All GET, read-only.

| Card | Endpoint | Shows |
|---|---|---|
| Teaching hours vs limit (4a) | already existed: `GET /api/basic-ed/analytics/workload/` | Each teacher's hours against their own cap (`Faculty.max_weekly_hours`), "Overloaded" tile and "Over by X h" badge. Not duplicated. |
| Daily timetable feasibility | `GET /api/analytics/basic-ed/feasibility/?level=&year=&period=` | Per grade: school day, breaks (JHS recess + lunch, SHS one break), periods per day from the generator's own `build_grid`, unused minutes, weekly periods available (Mon-Fri) vs the most any section needs, missing breaks. |
| Completeness per grade and strand | `GET /api/analytics/basic-ed/completeness/?level=&year=&period=` | Subjects required (same selection as the curriculum validator), subjects no active teacher is eligible for (the engine's `eligible()`), and from the latest timetables: subjects with fewer periods than their sessions per week, periods with no teacher. |
| Absence impact | `GET /api/analytics/basic-ed/absences/?level=` | Not recorded: SHS / JHS teacher absences are not stored anywhere (the Absence model is for college faculty), so the card says so instead of showing 0. Recording them would need a new table (migration). |

## Insight cards -- Stage 5: filters, CSV export, run trend
* **Filters** (Dean and Registrar Insights): school year, semester, college (when more than one is visible) and program, from
  `GET /api/analytics/filters/` (scoped: a Dean gets only their own college's programs and years; principals 403). Cards send
  `school_year`, `semester`, `department`, `program_id`. Supported per card: readiness, faculty fit, lab capacity, Gen Ed coverage, room
  heatmap and capacity take all four; load bands take semester and program (hours always count every class of the teacher, so a
  school-year filter would hide real load); dependencies take semester, college and program. The admin cards stay institution-wide.
  A filter never widens scope: a Dean asking for another college's program gets nothing of it.
  SHS / JHS Insights: school year (`?year=`, the Basic Ed academic years) and grading period (`?period=`).
* **CSV export**: every table on the new cards has "Export CSV (n)". It is built in the browser from the rows already loaded (all rows,
  not only the first 200 shown), named after the card and the date, UTF-8 with BOM so Excel opens it correctly. Nothing is sent to the server.
* **Trend per generation run** (SHS / JHS only): `GET /api/analytics/basic-ed/run-trend/?level=&year=` reads the stored `ScheduleRun`
  rows (every version is kept, replaced ones included): periods placed, not placed, efficiency = placed / (placed + not placed), conflicts =
  validation errors. Runs created before these counts were stored show "not stored", never 0.
* **College trend: not built.** College generation keeps no run history: a Generate writes no run record (only "could not place" lines
  go to the conflict log, with no placed count), so efficiency per run cannot be computed. It would need a new table storing, per Generate
  run: who, when, program / year level / semester, classes placed, classes not placed, clashes found, duration. That is a migration and
  was not added.

