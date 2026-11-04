# Exam schedule: room rules and validation

`backend/exams/room_rules.py` (used by `exams/services.py`) decides the rooms of every exam, following the GTI class program.
Lecture AND laboratory subjects all get an exam.

| Exam | Rooms |
|---|---|
| Computer Studies lab subject (major or minor) | Comp Lab C / Comp Lab D only |
| Computer Studies lecture | normal rooms; a lab only as a last resort (labs stay free for lab exams) |
| Minor (Gen Ed) lecture | first the rooms of the real 1st Sem Prelim Exam 2026-2027 schedule (Main 301/304/305/306/307/501, Alta 203/206/301/302/308/401, New Building 201/301/601), then Main Building floors 1-3, Alta (D) 3rd floor (never a lab), New Building floors 2-3 - taking turns to spread the load; any other room only if all of those are full |
| Nursing lab subject | major: Nursing Arts 4FA/4FB/7F, then Chem / Zoo lab; minor: Chem / Zoo, then Nursing Arts; then lecture rooms if every lab is taken |
| Other departments' lab subjects | their own laboratories, then lecture rooms |
| Major lecture | the department's rooms as in the class schedule |

Room ownership (rooms reserved to a department) and capacity always apply. The preferred rooms are tried across the whole exam week
before any other room is used.

After each generation the saved exams are checked again (`check_exams`): subjects without an exam, room double-bookings and room-rule
exceptions are listed in the Exam Schedule tab. A class that cannot be placed now says why (section busy / no room / no proctor) and
tells you to widen the exam week.

Tests: `python manage.py test exams`.

The room list for Gen Ed exams is `HISTORY_MINOR_ROOMS` in `exams/room_rules.py`; edit it to add or remove rooms. Main takes about half of the Gen Ed exams, like the history.

## Same subject, same hour, different rooms (exam-week practice)
Gen Ed (minor) exams are planned per SUBJECT across all programs: one date and hour, every section in its own room with its own
proctor, like the Prelim exam history (e.g. Reading in Philippine History, 10-11AM, sections A-F in 301M, 304M, 305M ...). If no
single hour suits every section the sections are split over as few hours as needed. Room capacity is a preference for exams: a room
that seats the section is used when free, otherwise the best room is used and shown as a capacity warning (no more "only the
auditorium").

## Exam conflict pop-up (Registrar = Gen Ed, Dean = majors)
The Registrar owns the Gen Ed (minor) exams and each Dean the program (major) exams of their college.
* **Registrar:** when a Gen Ed exam cannot be placed, a pop-up shows the plan: the exam goes to the hour its other sections use. If a
  major exam is in the way, the Registrar does NOT change it: "Place what I can and ask the Dean(s)" places the others and sends the
  Dean(s) of the colleges concerned a notification.
* **Dean:** Exam Schedule > "Registrar requests" lists the Dean's own exams that block Gen Ed exams, with a new free date / hour (and
  room / proctor) for each. "Change date / time" moves them (logged, marked as hand-edited); then the Registrar places the Gen Ed exams.
Every change is checked for double-bookings and undone as a whole if one is found. Classes are never moved.
API: `POST /api/exams/resolve/ {semester, exam_period, exam_start_date, exam_end_date, items?, apply}`.
Tests: `python manage.py test exams`.

## Exam proctors (`exams/proctors.py`)
* **Major exams:** faculty of the subject's own college, Dean included (Computer Studies exams -> Computer Studies faculty and Dean; same for
  every other college). A teacher whose specialization matches the subject's field is chosen first.
* **Gen Ed exams:** College of Arts and Science faculty whose specialization matches the subject (English, Filipino, Mathematics, Social
  Science, FCL, Communication, Science, PE/NSTP ...; read from the subject's academic field, or from its title when no field is set).
  Order: CAS + matching specialization -> anyone with a matching specialization -> other CAS -> anyone, so an exam is never left without a
  proctor; every proctor from a lower tier is listed in the check after generating.
* Because every section of a Gen Ed subject takes the exam in the same hour, each needs its own proctor: run
  `python manage.py add_department_staff` to bring CAS to 24 full-time + 16 part-time teachers (three specializations each).

## Combining low-enrollment Gen Ed sections (exam sittings)

Same rule as shared classes (`engine/merging.py`): the **same Gen Ed course** (same code, title, units, year level, semester) of several
programs sits **one exam together** -- one room, one hour, one proctor -- when all their students fit one Gen Ed exam room.

    5 BA + 15 CS + 15 IT = 35 students  -> one 40-seat room (as in the history: "N18-0204 / N22A-0202" on one row, 304 MAIN)
    25 RadTech + 15 CS + 15 IT = 55     -> not one room; first-fit packing makes the sittings (25+15, 15) or separate rooms

* Packing is first-fit-decreasing by student count; the limit is the biggest seat count among the preferred Gen Ed rooms.
* Every section keeps its **own `ExamSchedule` row**; rows of one sitting share `ExamSchedule.merge_key` (migration `exams/0002`).
  The unique room / proctor constraints apply to ordinary rows (`merge_key=""`); the section constraint still applies to every row.
* All members must be free at that hour (class/exam tolerance rule), so one busy section moves the whole sitting.
* Lab subjects and sections without a student count are never combined. Majors are never combined.
* The Exam Schedule table shows "Combined with <program section>"; `check_exams` treats the rows of one sitting as ONE room booking.
* Resolve places any exam it cannot fit on its own (an individual row) and never splits or moves an existing combined sitting.

Enrollment: `python manage.py set_enrollment --dry-run` then `python manage.py set_enrollment` sets the year-level totals
(CS 15/15/10/20, IT 15/16/10/9, RadTech 25/30/25/30, BA 5/5/6/9; a total is shared between the sections of a year level).
Then run `python manage.py migrate` and generate again.

### Update: Computer Studies first, Library last
* Shared Gen Ed classes (minor batch) and combined exam sittings pack **Computer Studies (CS + IT) first**; the other departments only take the seats that remain.
* The **Library** (listed as a lecture room in the class-program room list) is used for a lecture only when no other allowed room exists (`rooms.rules.is_library`). To never use it, mark the room inactive in Rooms.
