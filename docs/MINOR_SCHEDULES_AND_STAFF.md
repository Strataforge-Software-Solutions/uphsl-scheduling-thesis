# Generate All Minor Schedules (CCS, RadTech, Nursing, BAComm, Allied Health, IHM, BA) and department staff

## Use it (Registrar)
Registrar sidebar > **Minor Schedules**: choose Academic year, Semester, Year level (or All) > **Generate All Minor Schedules**.
You get: validation result, conflicts before / remaining after, per-department run table, the side-by-side comparison and the conflict report.

## How it works (backend/engine/minor_batch.py)
1. **Grouping** - equivalent minor lectures = same code + units + title (FCL 1 at 3 units for Nursing is NOT the same as FCL 1 at 2 units).
   Sections of different departments are packed (largest department first) into shared classes whose total students fit the biggest
   ordinary lecture room. The host section's room is chosen for the whole group; the others join it (same teacher/room/time) only if
   they are free then. Otherwise each department keeps its own section.
2. **Generation** - the existing generator runs per program (all existing rules still apply: teachers, rooms, availability, student overlap).
3. **Validation** - the semester is re-checked from the database. Any teacher/room/student clash involving a new class rolls back the
   WHOLE batch (nothing is saved) and the clashes are listed. "Validated" is shown only when remaining conflicts = 0 and nothing was left unplaced.
4. Re-running replaces earlier DRAFT minor classes of that semester/year level (no duplicates). Approved/published classes -> refused (409).
   Major subjects are never touched; minors are checked against majors too (conflict report shows Minor-Minor / Minor-Major / Major-Major).

If sections are bigger than the largest shared lecture room (40 seats in the current room list) they correctly stay SEPARATE.
To see sharing in a demo use realistic small section sizes (e.g. 10-14 students), or add bigger rooms.

Endpoints: POST /api/engine/minor/generate-all/ {school_year, semester, year_level}; GET /api/engine/minor/comparison/?semester=&year_level=

## Staff
    python manage.py add_department_staff --dry-run
    python manage.py add_department_staff
Adds full-time and part-time teachers (Filipino names, NO dean accounts) so each department has at least 6 full-time / 5 part-time;
Nursing gets 14 / 12. Login UPHM-F#### / UPHM-P####, first password = the ID. Safe to re-run.

## Departments covered
CCS (Computer Studies), RadTech, Nursing, BAComm (BA Communication), Allied Health (PT / OT / Med Tech), IHM (Hospitality / Tourism) and
BA (the two BSBA programs). Programs with no minor subjects in their curriculum (e.g. BS Medical Technology at the moment) are skipped with a note.
Room rules from the GTI class program (reserved rooms, labs, office rooms, capacity) are the existing ones and are applied to every class.

## Capacity warnings
If a section is larger than every room it may use (e.g. 50 Nursing students, largest shared lecture room 40 seats) the class is still placed
without a conflict and listed under "classes have more students than seats" - split the section or add a bigger room.

## Speed
The generator was made faster without changing its results (same schedules, checked row by row): generating all year levels of one semester
for all seven departments takes roughly 30 s on an empty schedule, and about as long with major subjects already scheduled.
