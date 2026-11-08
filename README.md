# UPHSL Academic Scheduling System — Rebuild Skeleton

Single source of truth: **Django + DRF** backend (Firestore dropped entirely).

## Backend structure (`backend/`)
```
config/         # settings, root urls, wsgi/asgi
accounts/       # User model (role, faculty_type, must_change_password), JWT login, bulk-import
curriculum/     # Program, Subject — department-scoped edit permission (Registrar: all, Dean: own dept)
faculty/        # FacultyProfile, Availability (part-time submissions)
rooms/          # Room
engine/         # Section, TimeSlot, Schedule, Constraint, Log
                #   scheduler.py = CSP engine: MRV heuristic + forward checking + backtracking
                #   + priority-based substitute-finder
exams/          # ExamSchedule -- separate model, Registrar owns minor-subject exams,
                #   Dean owns major-subject exams (own dept). Uses engine/conflicts.py
                #   to check across BOTH this table and the regular Schedule table,
                #   so Dean and Registrar can't silently double-book a section/room/timeslot.
analytics/      # room utilization, teacher workload, schedule efficiency, workload std-dev
notifications/  # Notification model (schedule updates, conflict alerts)
```

### Shared conflict-checking layer (`engine/conflicts.py`)
`find_conflicts()` / `is_slot_free()` check a candidate (teacher/proctor, room, section, timeslot)
against EVERY registered schedule-like model, not just the one being written to. Currently
registers `engine.Schedule` and `exams.ExamSchedule`. Add future schedule-like models (makeup
classes, seminars, etc.) to the `registry` list in that file to keep them conflict-free against
everything else automatically.

### ML groundwork (not yet a working model — just data collection)
Per our roadmap discussion, these fields exist now so a future ranking/prediction model has
training data to work with once a few semesters have passed:
- `engine.Schedule.is_manual_override` — auto-set `True` whenever a Dean/Registrar edits an
  entry after the CSP engine generated it (see `ScheduleViewSet.perform_update`). This is the
  negative-signal label a future "was this a good auto-assignment?" model would train on.
- `engine.Schedule.school_year` / `exams.ExamSchedule.school_year` — tag entries by year so
  multi-semester history can be distinguished.
- `faculty.Availability` now accumulates rows across semesters (`school_year`, `semester`,
  `submitted_at`, `is_active`) instead of being overwritten, so "this faculty always prefers
  Mon/Wed mornings" becomes visible once enough semesters exist.
- `curriculum.Subject.classification` (major/minor) — also doubles as the ownership split for
  exam scheduling.

### Roles
- **Registrar** — edits curriculum/schedules for all departments, sees institution-wide analytics.
- **Faculty** (`role=faculty`) — split by `faculty_type`:
  - `dean` — same scheduling/curriculum tools as Registrar, scoped to their own department; also reviews part-time availability submissions.
  - `full_time` — read-only personal teaching schedule.
  - `part_time` — read-only schedule + availability submission form.
- **Student** — read-only personal timetable.
- Secretary role removed; its curriculum-editing responsibilities now live under Dean.

### First-login password flow
`User.must_change_password` defaults to `True`. Bulk-import (`POST /api/accounts/bulk-create/`)
creates `UPHM-<school_id>` usernames with the school ID as the default password. Login response
includes `must_change_password`; frontend routes to `/change-password` before `/dashboard` until
`POST /api/accounts/change-password/` clears the flag.

## Frontend structure (`frontend/src/`)
```
services/api.js           # axios + JWT + login/session helpers
pages/Login.js            # real auth against Django
pages/ChangePassword.js   # forced first-login flow
components/Dashboard.js   # role router — registrar / faculty / student only
components/FacultyDashboard.js  # ONE component, three internal views by faculty_type
components/RegistrarDashboard.js, StudentDashboard.js  # carry over, need same API wiring
```

## Getting it running locally (Supabase / PostgreSQL)

1. **Create a Supabase project** at supabase.com — set a database password when prompted (save it).
2. **Get connection details** — Project Settings > Database > Connection Info: host, port (5432), database (`postgres`), user (`postgres`), and the password you set.
3. **Configure env vars** — `cp backend/.env.example backend/.env` and fill in those values.
4. **Install & migrate**:
   ```
   cd backend
   python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python manage.py makemigrations
   python manage.py migrate
   ```
5. **Seed sample data** (one program, subjects, rooms, timeslots, and one login per role):
   ```
   python manage.py seed_demo_data
   ```
   Prints sample logins, e.g. `UPHM-R1001 / R1001` for Registrar — all forced to change password on first login.

   **To load the real BS Computer Science curriculum** (transcribed from UPHSL's student
   residency evaluation — 1st through 4th Year, all subjects with correct codes/units/major-minor
   classification, plus one section per year/semester):
   ```
   python manage.py seed_bscs_curriculum
   ```
   Safe to re-run — uses `get_or_create`, won't duplicate existing subjects.

   **If you ran an older version of `seed_demo_data`** (before this fix) that already created
   demo subjects `CS101`/`CS102`/`CS103`/`GE101` and a demo section `"1A"` under the same
   Program as the real curriculum, those will collide with `seed_bscs_curriculum`'s real data
   and cause Generate Schedule to try scheduling both sets at once (visible as a huge, mostly
   duplicate-looking conflict report). Clean it up once with:
   ```
   python manage.py cleanup_demo_overlap
   ```
6. **Run the API**: `python manage.py runserver` → `http://127.0.0.1:8000`
7. **Frontend**: `cd frontend && npm install && npm start` → proxies to the API via `services/api.js`'s `baseURL`.

### Using local MySQL instead
`db_setup.sql` is still included for MySQL Workbench. In `settings.py`, comment out the active
Postgres `DATABASES` block and uncomment the MySQL one; in `requirements.txt`, swap
`psycopg2-binary` for `mysqlclient`; update `.env` to match MySQL's fields (host `127.0.0.1`, port `3306`).

## Deploying on Vercel

The root `vercel.json` configures two Vercel Services: the Django API in `backend/` and the
Create React App in `frontend/`. `/api/*` and `/admin/*` route to Django; Django admin and
REST framework assets under `/static/admin/*` and `/static/rest_framework/*` also route there.
Other `/static/*` assets route to React, and all remaining paths route to React. The frontend uses
the same-origin `/api` URL in production, while
local development continues to use `http://127.0.0.1:8000/api` by default.
No service binding is declared: this Create React App makes API requests from the user's browser,
and Vercel bindings are only available to server-side functions at runtime. The browser instead
uses the public `/api/*` rewrite on the shared domain.

Set these environment variables in the Vercel project before deploying:

- `DJANGO_SECRET_KEY`: a long, random secret.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`: the PostgreSQL/Supabase connection.
- `DJANGO_ALLOWED_HOSTS`: comma-separated allowed hostnames if using a custom domain (the default allows Vercel domains and localhost).
- `REACT_APP_API_BASE_URL` is optional; leave it unset to use the shared `/api` route.

`DEBUG` defaults off on Vercel. Apply Django migrations to the production database as a deployment
operation before using the app. Profile pictures currently use Vercel's ephemeral `/tmp` storage;
configure durable external storage if uploads must survive function restarts or deployments.


1. `python manage.py startapp`-style migrations — run `makemigrations && migrate` once you drop this into a real environment.
2. RegistrarDashboard.js / StudentDashboard.js still need to be pointed at the Django endpoints (currently only FacultyDashboard is wired).
3. Notifications are model-only — no push/poll mechanism wired yet.
4. `TimeSlot` <-> `Constraint.timeslot` matching in `engine/views.py generate_schedule_view` is a stub — needs a consistent slot-identifier format between the two models.
5. CSV bulk-import UI for Registrar/IT (backend endpoint exists at `/api/accounts/bulk-create/`, no frontend form yet).

## Latest additions
- `seed_college_deans` — one Dean login per college (DeanCS, DeanNursing, DeanBA, DeanCas, DeanCithm, DeanRadtech, DeanAllied), each scoped to their own department with zero overlap.
- PDF export of class schedules (`GET /api/engine/export-pdf/`), reportlab-based, matches UPHSL's printed format. Download buttons added to Registrar's and Dean's Schedules tabs.
- Full-time/part-time dashboards now show a workload summary card (hours/week vs target load) and, for part-time, a submitted-availability history table.
- Password reset: Registrar-only "Reset to Default" action (Manage Users tab) — sets password back to school ID, forces change on next login. No email flow, one clean state.
- Password-change screen redesigned to match the provided mockup (dark navy card, pill submit button).
- Global theme (`DashboardTheme.css`, `Login.css`) refreshed — applies automatically to all three dashboards since they share the same class names.
