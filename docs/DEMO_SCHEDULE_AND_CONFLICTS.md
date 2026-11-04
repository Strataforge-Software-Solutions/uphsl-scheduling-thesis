# Demo: generate a schedule and detect conflicts

## What already existed (reused, not rewritten)
* `engine/scheduler.py` - the constraint solver (backtracking + MRV + forward checking). It treats every class already in
  the database as occupied, so a new schedule is placed AROUND existing ones.
* `engine/conflicts.py` - the shared conflict rules (teacher / room: any overlap; students: overlap beyond 30 min).
* `POST /api/engine/generate-schedule/` - generation (Registrar: Gen Ed subjects; Dean: program subjects), saved as Draft.

## What was added
* `engine/conflict_report.py` + `GET /api/engine/conflicts/` - scans the WHOLE class schedule in one query and lists every
  teacher / room / student double-booking with the two classes involved (subject, section, teacher, room, day and time).
* After every generation the response includes `clashes`: the new classes checked against everything already scheduled.
  The Generate window shows it ("No conflicts..." in green, or each clash in red).
* **Conflicts** tab (Dean and Registrar sidebar, under Plan): runs the scan automatically and has two demo buttons:
  "Add sample conflicts (demo)" creates three deliberate double-bookings (teacher, room, students; tagged `DEMO-CONFLICT`),
  "Remove sample conflicts" deletes exactly those rows.
* Manual edits keep their own check: Change day / time and Edit refuse a clash and suggest free times.
* `start-demo.ps1` starts backend and frontend together.

## Run
1. `python manage.py migrate` (nothing new to migrate for this feature).
2. Backend: `python manage.py runserver`   (http://127.0.0.1:8000)
3. Frontend: `npm start`   (http://localhost:3000). `npm start` only starts the frontend; the backend must be running too
   (or use `.\start-demo.ps1` from the project folder to start both).

## Test script for the evaluators
1. Sign in as a Dean. Schedules > Generate Schedule > choose program, year level, semester > Generate.
   Result: classes created as Draft + "Conflict check against the existing schedule: No conflicts".
2. Sign in as the Registrar and generate the Gen Ed subjects for the same term (they are placed around the Dean's classes):
   still no conflicts, because the solver avoids every occupied teacher, room and student group.
3. Open **Conflicts**: "No conflicts" with the number of classes checked.
4. Press **Add sample conflicts (demo)**: the report now lists a Teacher, a Room and a Students conflict, each showing both
   classes side by side with the clashing teacher / room / section highlighted and the overlap in minutes.
5. Press **Remove sample conflicts**: back to no conflicts.
6. Real clash through a manual change: Schedules > tick a class > Change day / time to a time that is already used by the
   same teacher / room / students: a warning names the other class and offers free times.
7. Generate the same scope again: the earlier Draft of that scope is replaced (not stacked); approved/published classes are
   never replaced (the system refuses and says why).

## Resolving conflicts (Resolve / Resolve all)
In the Conflicts tab every conflict has a **Resolve** button, and the toolbar has **Resolve all conflicts**.
One of the two clashing classes is changed (a sample class first, otherwise the one nobody edited by hand):
- Teacher conflict -> another qualified teacher who is free at that time (then another day/time if none)
- Room conflict -> another allowed room that fits the section and is free (then another day/time)
- Student conflict -> another day/time where the teacher, room and students are all free
Each fix is checked first so it creates no new conflict, and is written to the log. If nothing clean exists the class
is left alone and the reason is shown. A Dean can only change major classes of their own college, the Registrar only
minor classes, so run the demo as the Dean for the sample (IT) conflicts.
Demo flow: Add sample conflicts -> see 3 conflicts -> Resolve (one) or Resolve all -> 0 conflicts.
Endpoint: POST /api/engine/conflicts/resolve/ ({kind,a_ids,b_ids} or {all:true}).
