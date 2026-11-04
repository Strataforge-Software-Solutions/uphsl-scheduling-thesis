# SHS curriculum verification

`python manage.py verify_shs_curriculum` compares every Senior High School curriculum line with the DepEd Strengthened SHS Curriculum
(DO 017 s.2026, DM 48 s.2025, DM 12 s.2026; reference data in `basic_ed/shs_reference.py`).

    python manage.py verify_shs_curriculum            # report only, changes nothing
    python manage.py verify_shs_curriculum --apply    # fixes what is safe; NEVER deletes

Reports: MISSING, DUPLICATE, INCORRECT, OUTDATED, MISASSIGNED, UNVERIFIED.

`--apply` adds a missing Grade 11 core / Homeroom line, corrects hours, periods per week, category, strand and period of the five core
subjects (160 h, 4 periods/week, whole year) and Homeroom Guidance (40 h, 1/week), and retires (is_active=False, reason stored in the line)
test/import leftovers, duplicates and 2016 K-12 subjects found in Grade 11. Retired lines are hidden from new scheduling only; schedules
already made keep their own copy of the subject, and other dashboards read the same tables unchanged.

Cannot be verified from DepEd documents (reported, not rewritten): which elective is taken in which term; the Grade 12 (SY 2026-2027, still
2016 curriculum) semester subject list. Placeholder electives get the official cluster titles written into their note.
Tests: `python manage.py test basic_ed`.
