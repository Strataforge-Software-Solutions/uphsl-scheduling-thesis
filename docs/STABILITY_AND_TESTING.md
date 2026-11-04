# Stability checks and how to re-run them

## Automated tests (backend)
    cd backend
    python manage.py test engine
19 tests, run on a throw-away database (your data is never touched). They cover:
- generation on an EMPTY schedule table, repeated generation (replaces the draft, never stacks copies),
  generation after "delete all", two programs sharing teachers, approved classes protected, bad input -> clear 400/403
- saving: teacher / room / student double-booking refused with a plain message (API), and by the database constraints
- updating a class into a clash is refused and the row is left unchanged; garbage input gives 400, never 500
- deleting a class / teacher then generating again; the conflict report and the Resolve tool; empty-table reads

## Load run (170 program/year/semester scopes, 12 programs, Registrar minor pass then each Dean's major pass)
Generated three times in a row (fresh, repeated, after clearing everything): identical 2210 class rows each time,
0 teacher/room/student conflicts afterwards, no server errors. Two scopes legitimately answer 400 (no minor subjects).
Most scopes take 0.3-3 s; Computer Science years with many sections sharing two labs can take 14-17 s because the
engine stops after its time budget (8 s per phase) and reports what it could not place instead of hanging.

## Frontend
    cd frontend
    npm install
    npm start        (dev server, http://localhost:3000)   |   npm run build  (production build: succeeds)
Only ESLint hook-dependency warnings remain (not errors).
