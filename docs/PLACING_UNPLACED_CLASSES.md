# Placing classes the generator could not place

## Why Gen Ed / major classes were left unplaced
* CS and IT *lectures* were placed in Comp Lab C / D (the GTI class program lists those rooms as the department's home rooms).
  They filled 73 of the 130 weekly hours of the two labs, so the 3-hour lab blocks of 4th year (and of Gen Ed classes that
  needed those rooms/teachers afterwards) had no room left. Capacity was never the problem (63 lab hours needed, 144 available).
* Fix in `engine/scheduler.py`: a lecture takes a department laboratory only as a last resort (`_lab_taken_by_lecture`),
  in the value ordering, the repair pass and the room shortlist. Rooms, teachers, specializations and all rules are unchanged.

## What happens now when a class still cannot be placed
1. Generation no longer calls `engine/placement.py` by itself: leftover classes are reported with suggested free times (same room first) and the owner confirms one.
2. **Resolve** (per class) and **Resolve all** are in the generate result (Dean and Registrar) and in Minor Schedules.
   API: `GET /api/engine/unplaced/?semester=` and `POST /api/engine/unplaced/resolve/ {semester, section_id?, subject_id?}`.
3. Order, like working the GTI class program by hand: free time -> lectures sitting in the lab go to lecture rooms (same teacher
   and time) -> re-solve the few classes blocking it (other room / teacher / time), with its lecture for a lab.
4. Every step uses the generator's own rules, is checked again with the clash scan and is undone if it fails.
   Approved/published and shared Gen Ed classes are never moved; a Dean moves only own-college majors, the Registrar only Gen Ed.
5. If it still fails, the message names the classes in the way and who owns them. It never tells anyone to add rooms or faculty.

Tests: `python manage.py test engine.tests.UnplacedResolveTests`.
