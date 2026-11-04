# Historical Data Request — IT Department (2021–2026)

This spec matches the exact fields the system's database now has. Ask IT for exports shaped
like these tables (CSV is fine) — anything outside these fields can't be imported without
extra mapping work, so it's worth confirming what IT actually has before they export anything.

## 1. Historical Class Schedules
| Field | Notes |
|---|---|
| school_year | e.g. "2022-2023" |
| semester | e.g. "1st Sem" |
| subject_code | must match/be mappable to our Subject.code |
| section | e.g. "BSCS 2A" |
| faculty_name_or_id | teacher assigned |
| room | room name |
| day | Mon/Tue/Wed/Thu/Fri/Sat |
| start_time / end_time | 24hr, e.g. 08:00 / 09:00 |

## 2. Exam Timetables
| Field | Notes |
|---|---|
| school_year, semester | |
| subject_code | |
| section | |
| **exam_date** | **actual calendar date** (e.g. 2023-03-15) — our exam table now stores this |
| exam_period | Prelim / Midterm / Final |
| room | |
| proctor_name_or_id | invigilator |

## 3. Faculty Availability / Absences / Overload
Three separate things — ask IT to keep them separate if possible:
- **Availability** (recurring weekly preference): faculty, day, start_time, end_time, school_year, semester
- **Absences** (specific dates): faculty, date, reason (if recorded), status (approved/denied/pending), school_year, semester
- **Workload/Overload**: faculty, school_year, semester, total_hours_taught, whether flagged as overload

## 4. Manual Overrides
| Field | Notes |
|---|---|
| school_year, semester | |
| subject_code, section | which schedule entry was changed |
| what_changed | e.g. "room changed", "teacher reassigned" |
| changed_by | registrar/dean name if recorded |
| date_changed | |

If IT's system doesn't explicitly log *that* something was manually overridden (many systems
don't), this one may not be available — that's fine, it's the least critical of the six.

## 5. Conflict Logs
| Field | Notes |
|---|---|
| school_year, semester | |
| conflict_type | double-booked teacher / room / section, overload, etc. |
| description | free text is fine |
| date_occurred | |
| resolved | yes/no, if tracked |

Also likely unavailable from a manual/spreadsheet-based old system — ask, but don't expect it.

## 6. Room / Resource Metadata
| Field | Notes |
|---|---|
| room_name | |
| capacity | |
| room_type | lecture / lab |
| equipment | free text, e.g. "Projector, 30 PCs, Aircon" |
| is_accessible | wheelchair/PWD accessible (yes/no) |

---

## Practical notes for the conversation with IT
- **Categories 1, 3 (availability), and 6 are most likely to actually exist** in a usable form (registrar spreadsheets, HR records, room inventories).
- **Categories 2 (exam dates specifically), 4, and 5 are the least likely to exist** in most institutions' old systems — don't be surprised if IT says "we don't track that separately." That's normal, not a failure on your part.
- Ask for **CSV or Excel exports**, not PDFs/printouts — PDFs would need manual re-entry, which defeats the purpose.
- If IT can only provide 1–2 years instead of 2021–2026, that's still useful — more history helps eventually, but isn't required to demonstrate the system works.
