# Faculty overload: View Suggestions and one-click Assign (Dean)

* Banner "N faculty members are overloaded" + **View Suggestions** on the Dean's Schedules, Analytics, Conflicts and Faculty tabs, and in the Generate panel's workload warnings.
* `GET /api/engine/workload/overload-plan/` -- per overloaded teacher and term: the changeable classes, the fewest classes that cure the overload (recommended), and ranked suggestions.
  A person is suggested only if their specialization, degree or qualification matches the subject, they are inside their submitted availability, free at every period, and stay within their full-time / part-time limit. Ranking: qualification fit, then the lowest resulting utilisation (spreads work). When nobody qualifies the response says why (no one qualified / unavailable / already teaching / no hours left).
* `POST /api/engine/workload/overload-assign/` `{schedule_ids, teacher}` -- re-checks qualification, availability, clashes and the weekly limit inside a lock, applies the change to the real schedule rows, then verifies no new clash (otherwise rolled back) and returns the checks and the new hours.
* Only draft, non-shared classes the user may edit are moved (Dean: own-college program subjects; Registrar: Gen Ed). Approved / published / shared classes are never moved; the plan states how many hours are locked.
* After Assign the banner, schedule table, analytics and workload lists refresh automatically.

## Update: scope, per-warning buttons, confirm step
* The warning scope is the Dean's college faculty **plus anyone teaching the Dean's own classes** (a generated class can land on a teacher whose home department is another college). `GET /api/engine/workload/overload-summary/` feeds the banner (teacher, subjects, excess).
* Every warning (banner, Generate panel, Faculty workload table) has its own **View Suggestions**; Assign asks "Okay, confirm" before the change is made, and the result with its validation checklist stays visible after the warning clears.
* Candidates show degree, qualifications, specialization, submitted availability and hours before/after. If every class of an overloaded teacher is locked (Gen Ed, shared, approved) or nobody qualifies, the window says why and the warning stays.
