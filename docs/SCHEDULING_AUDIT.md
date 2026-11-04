# U-FAST scheduling audit (rooms, faculty, conflicts)

Method: the thesis' constraint-based scheduler with a greedy, most-constrained-first assignment (engine/scheduler.py: variables = one per class block, domains = valid
(teacher, room, time) triples, forward checking, then a repair pass for leftovers). Nothing here replaces it; the rules below only shape the domains and the reports.

## Pipeline (thesis steps -> code)
| # | Step | Where |
|---|------|-------|
| 1 | Curriculum, sections, faculty, rooms, preferences | `generate_schedule_view` |
| 2 | Mandatory constraints (teacher / room / section overlap, one block per day) | `scheduler.is_consistent`, DB unique constraints, `conflicts.find_conflicts` |
| 3 | Faculty qualification + availability | `engine/qualification.py`, `_build_availability_rules` |
| 4 | Room type, ownership, capacity, availability | `scheduler.build_domain`, `rooms/rules.py` |
| 5 | Dean's / Registrar's room and time first | preview room = fixed for the run; Start/End = hard window (30-min steps) |
| 6 | Greedy ordering, Gen Ed first then majors | `generate_schedule_two_phase`, `select_unassigned_variable` |
| 7 | Detect clashes against major, Gen Ed, shared classes | `conflict_report.scan` after every run |
| 8 | Alternative days / times | `reschedule.suggest` (suggestions in the pop-up; applied only after the owner confirms). Generate no longer calls `placement.resolve_groups` |
| 9 | Unresolved items with an actionable reason | `explain_unresolved`, `placement._why_not`, the problems pop-up |
| 10 | Validate before saving | scan + rollback in Resolve/Apply and the minor batch |

Hard constraints (never relaxed): teacher / room / student overlap, qualified faculty, room type and ownership, designated rooms, capacity of a fixed room, approved /
published classes untouched, weekly limit when the policy is strict. Preferences (ordered, never block a schedule): home rooms and buildings from the GTI class program,
spreading a section over days, less-loaded teachers.

## Rules added in this pass
* **Computer Studies majors (BSCS, BSIT)** use Comp Lab C and Comp Lab D only (lecture and lab), for all year levels. Not an ordinary lecture room: not by the
  generator, not by re-arranging, not by Resolve, not by the Dean's room choice or Room assignments (refused with the reason). The GTI class program also shows
  CCS lectures in these labs. Rooms are taken from the existing records (Comp Lab C = 307D, Comp Lab D = 309D in the GTI file and in the database); no room was invented.
  Other departments keep their GTI home rooms as a preference, because no hard rule was given for them.
* **Who assigns rooms**: IT Admin = room records; Dean = rooms of own college's major subjects; Registrar = Gen Ed / shared classes. Anyone else, or the wrong owner, gets
  a pop-up with the reason and who can do it.
* **Resolve order**: (1) same room, days/times inside the chosen Start-End; (2) same room, other times (flagged "outside your window"); (3) only when the subject may change
  room (Gen Ed, or a major of a college with no designated rooms and no fixed room): other free rooms, flagged, applied only after Confirm. Computer Studies majors are never
  offered an ordinary room. Every option is checked against teacher availability / load, room, and the section's other classes, and re-checked on Apply.
* **Pop-up correctness**: each row is built from the schedule record (subject id, section id, row ids). Resolve is shown only for classes the user owns; the other side of a clash
  says who owns it. A class that is already placed is removed from the list instead of offering a second period.
* **Faculty**: one qualification rule for every code path; when nobody qualifies the report says so and lists related faculty who could be given the specialization.

## Seeded-data run (sandbox copy of the seeded database, all programs, both semesters, Gen Ed batch first)
1180 major class periods placed, 0 clashes in the final scan, 8 classes left with a specific reason:
* 5 IT classes (3rd/4th year, 1st sem): Comp Lab C and D are booked at every free 3-hour period (about 80% of their weekly hours are used). They stay unplaced rather than
  moving to a lecture room. Freeing a period in a lab or making another designated room available (IT Admin) resolves them.
* 3 RadTech classes: free windows are held by Registrar-owned Gen Ed classes, which only the Registrar can move.
BS Hospitality / Tourism have no Dean account in this sandbox database, so they were not generated here.

## One teacher for a subject's Lec and Lab (hard rule)
A subject's lecture and laboratory parts (curriculum codes `X` and `XL`, e.g. CS1103 / CS1103L) are taught by the SAME teacher in a section.
It was only a preference before, so a busy lecture teacher could leave the lab to someone else. Now it is part of the constraint check
(`scheduler.is_consistent`, the forward check and the indexed pre-filter), so the greedy search never assigns a different teacher. Also enforced in
Resolve suggestions (`reschedule.suggest` offers only the partner's teacher), the old automatic resolver (no teacher swap for a paired class) and
manual edits (refused with the reason). When the lecture's teacher has no free time for the lab, the lab is reported with that reason.
Schedules generated before this rule keep their teachers until they are generated again.

## Students are never in two classes at once (one rule everywhere)
Root cause of overlaps that only showed up in the printed table: the CSP solver (`is_consistent`, forward checking) never lets a section
overlap, but the other class paths (Resolve, manual edit / move tools, the old automatic resolver, the conflict scan) used the 30-minute
student "grace window" from SchedulingConfig. A class moved through them could overlap its section by up to 30 minutes and the scan hid it.
Now every class-schedule path uses `conflicts.class_tolerance_minutes()` = 0, the same rule as the solver. The stored setting is kept and is used
for EXAMS only (Registrar Settings label says so). Existing overlaps now appear in the Conflicts tab and can be fixed there.
Print / Preview (`export-pdf`) checks the classes in the table first: with a conflict it returns 409 and the Dean sees the list with
"Fix them now" (same pop-up) or "Print anyway", which prints a red NOT FINAL line.

## Lecture before Lab in every path (and shown as a pair)
The solver already places a subject's Lab (code X + "L") only after its Lecture (X) has ended in the week, for the same section. The other paths did
not check it, so a moved Lecture could land after its Lab (e.g. CS2107L Thu 10:00, CS2107 Lec Fri 7:30). `engine/lecorder.py` holds the one rule
(same as `scheduler.is_consistent`) and is now used by Resolve suggestions (`reschedule.suggest`), Change day / time and the old resolver
(`tools._evaluate`, its free-time suggestions too; partners moved in the same request count at their new time), the Edit window and a manually
added class (refused with a plain reason). Pairs already saved in the wrong order are fixed by generating that year level again (no new problem
type was added). Tables (Dean, Faculty, Registrar, Student) tag each pair "Lec · 1 of 2 · then Lab …" / "Lab · 2 of 2 · after Lec …"
(`frontend/src/utils/lecLab.js`), and the PDF adds a small second line under the subject. No data is changed by the tags.
