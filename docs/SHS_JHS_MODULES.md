# SHS & JHS scheduling modules (A.Y. 2026-2027)

Separate from the college system: own tables (`basic_ed` app), own dashboards, own rooms/sections/curriculum/teachers.
Shared: login (same `accounts.User`, roles `principal` and `teacher` + `school_level`).

## Set-up (backend folder, one at a time)
    python manage.py migrate
    python manage.py seed_basic_ed          # config, calendar, strands, sample rooms/sections, curriculum
    python manage.py setup_basic_ed_staff   # principals + sample teachers (fictional names)

Logins: PrincipalSHS / SHSPRIN, PrincipalJHS / JHSPRIN (must change password on first login);
teachers: UPHM-SHS-T001 ... / UPHM-JHS-T001 ... with the employee ID as first password. The IT admin sees a
"School level: College / Senior High / Junior High" selector at the bottom-right of the screen.

## Rules enforced by the engine (and re-checked by the validator after every edit)
* SHS Grade 11 07:00-12:30, Grade 12 12:30-18:30 (Alfredo Building); JHS 08:00-14:00, Alta Building 4th floor only.
* No teacher / room / section double-booking (also across grade levels of the same level).
* Teacher availability, qualification (specialization match), daily and weekly load limits.
* Room type (lab / workshop), capacity, active, correct building/floor.
* Every curriculum subject gets its required periods; anything that cannot be placed is listed with the reason.
* Flow: Draft -> Submitted -> Approved (principal) -> Published (teachers see it). Every regeneration/revision keeps the old version.

## Data that is NOT fabricated / what still needs the school
Verified from DepEd sources: the 3-term calendar, the Strengthened SHS Grade 11 core subjects (160 h) and elective/TechPro structure, Homeroom Guidance 1 h/week, MATATAG Grade 7 start.
Marked **unverified** in the dashboard (review/replace through Curriculum > Import file or the edit form):
elective subject names (DepEd lists clusters only), Grade 12 for SY 2026-2027 (not yet issued), Grade 8-10 MATATAG phase-in and the JHS learning-area list,
the term <-> semester/quarter mapping (placeholder), rooms/sections/student counts (sample).
Specialization matching is exact (case-insensitive) between a subject's "specialization" (alternatives separated by |) and a teacher's specializations.
