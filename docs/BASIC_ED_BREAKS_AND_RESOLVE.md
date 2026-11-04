# JHS / SHS recess and lunch, and the Resolve actions

## Recess and lunch (Basic Education)
Every grade level's daily window now has a **recess** and a **lunch** (Settings > Daily time windows). No class is ever placed in
them: the period grid skips them, the timetable shows them as shaded "RECESS" / "LUNCH" rows, the PDF prints them, and the
validation reports a class that overlaps one (`during_break`) or a grade level without recess or lunch (`no_break`, blocks generation).

| Level | Periods | Recess | Lunch | Day |
|---|---|---|---|---|
| JHS 7-10 | 8 x 45 min | 10:15-10:30 | 12:00-12:45 | 8:00 AM - 3:00 PM (was 2:00 PM) |
| SHS Grade 11 | 6 x 50 min | 8:40-8:55 | 10:35-11:05 | 7:00 AM - 12:45 PM (was 12:30) |
| SHS Grade 12 | 6 x 50 min | 2:25-2:40 PM | 4:20-4:50 PM | 12:45 PM - 6:30 PM (was 12:30 start) |

Why the day grew: JHS needs 37 of 40 weekly periods and Grade 11 STEM/TVL needs 26+, so the number of periods per day must stay; the 60 / 45
minutes of breaks are added to the day. SHS Grade 11 and 12 share rooms, so the 15 minutes were taken from both (Grade 11 ends 12:45,
Grade 12 starts 12:45). **These times are defaults to confirm with the principal; change them in Settings.**

Apply to an existing database:

    python manage.py migrate
    python manage.py set_basic_ed_breaks --dry-run
    python manage.py set_basic_ed_breaks            # --reset puts the defaults back
    python manage.py clear_basic_ed_schedules --level JHS --apply     # old timetables were built without breaks
    python manage.py clear_basic_ed_schedules --level SHS --apply
    (then Generate again for every grade: all grades must use the same new periods)

## Resolve actions
* **College classes (Generate panel and Conflict Checker):** a *Resolve* button on every conflict and *Resolve all conflicts*. One of the two
  classes is changed (another qualified teacher, another room, or another day/time) only when that creates no new clash. A Dean changes only
  own-college program subjects, the Registrar only Gen Ed; approved, published and shared classes are never moved. When neither class may be
  changed by you, the message names the owners and they get a notification. A conflict an earlier fix already removed is not "fixed" again.
* **JHS / SHS timetables:** *Resolve* after Generate, and *Resolve all* / *Resolve* per problem in the Conflicts tab. Tries another teacher, room or
  period (or a new period for a missing one); every change is re-validated with ALL hard rules and kept only if it leaves fewer problems and none
  new. What cannot be fixed is listed with the reason and what to do (add a teacher, add a room, regenerate the neighbouring grade).
* **Exams:** unchanged (Registrar places Gen Ed exams, Dean moves own majors).

## IT admin workspace for SHS / JHS
When the IT admin switches the school level to Senior High / Junior High, the sidebar is the admin's (not the principal's):
Insights (Overview: setup health + analytics, Activity) · People (Accounts of that level, Faculty) · Management (Sections, Curriculum, Rooms,
Calendar, Settings) · Data (Data Tools: preview and clear generated timetables of that level, approved ones kept unless ticked).
There is no Schedules tab: generating, reviewing, resolving and approving timetables is the Principal's work.

## Principal Analytics tab (SHS / JHS)
`GET /api/basic-ed/analytics/workload/?level=SHS|JHS[&period=n]` (principal of that level, or IT admin) reads the latest non-superseded
timetables of one school level and reports each teacher's hours, subjects, sections and load status, workload conflicts (overload,
daily limit, double booking, availability, specialization, no teacher) and balancing recommendations (a subject-in-a-section moved to a
qualified, free teacher within weekly/daily limits). Read-only; "Apply" uses the normal `entries/<id>/` edit, so all rules still validate.
The tab refreshes every 30 s and when the window regains focus. See `backend/basic_ed/analytics.py`.
