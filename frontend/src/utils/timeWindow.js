import { formatTime } from "./formatDateTime";
/* Start / End time chosen for a subject in the Generate preview. The server is the source of truth (engine/views.py
   _preview_choices with engine.scheduler.window_need_minutes); this only shows the same rule in the row before Generate. */

export const toMin = (t) => { const [h, m] = String(t).split(":").map(Number); return h * 60 + (m || 0); };

// Fallback when an older server does not send need_minutes: a lab period is 3 h, a lecture is its units up to 3 h.
const fallbackNeed = (s) => (s.lab_units > 0 ? 180 : Math.max(60, Math.min(Math.round((s.lec_units || 1) * 60), 180)));

// Shortest unbroken window (minutes) the subject needs: the server's own number when it is there.
export const needMinutes = (s) => (Number.isFinite(s?.need_minutes) && s.need_minutes > 0 ? s.need_minutes : fallbackNeed(s || {}));

const hrsText = (min) => { const h = Math.round((min / 60) * 100) / 100; return `${h} hr${h === 1 ? "" : "s"}`; };

/* "" when the row is fine, otherwise the red hint. Only a range with BOTH times is checked (one time alone is accepted by the server). */
export function timeWindowProblem(subject, start, end) {
  if (!start || !end) return "";
  const a = toMin(start), b = toMin(end);
  if (b <= a) return "The End Time must be later than the Start Time.";
  const need = needMinutes(subject);
  if (b - a < need) return `Needs ${hrsText(need)} in one block; this range is ${hrsText(b - a)}.`;
  return "";
}

/* ---- Start / End dropdowns that follow each other (same rule as the server: End - Start >= needMinutes). ---- */
export const DAY_START = 7 * 60;
export const DAY_END = 20 * 60;
export const toHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
export const clock = (m) => formatTime(m);
const GRID = Array.from({ length: (DAY_END - DAY_START) / 30 + 1 }, (_x, i) => DAY_START + i * 30);

// Start times that leave room for the class: at least needMinutes before the chosen End (or before the end of the day).
export function startOptions(subject, end) {
  const need = needMinutes(subject);
  const last = (end ? toMin(end) : DAY_END) - need;
  return GRID.filter((m) => m <= last).map(toHHMM);
}

// End times that make the class fit: from Start + needMinutes (or the first possible end of the day), every 30 minutes.
export function endOptions(subject, start) {
  const need = needMinutes(subject);
  const first = (start ? toMin(start) : DAY_START) + need;
  return GRID.filter((m) => m >= first).map(toHHMM);
}

export const earliestEnd = (subject, start) => (start ? toHHMM(toMin(start) + needMinutes(subject)) : "");

/* The row after the Dean picks a Start: an End that is "Any time" or too short becomes the earliest valid End (the Dean may change it).
   Returns { start, end, notice }. "Any time" for Start leaves End as it is. */
export function pickStart(subject, start, end) {
  if (!start) return { start: "", end: end || "", notice: "" };
  const need = needMinutes(subject);
  const first = toMin(start) + need;
  if (first > DAY_END) return { start: "", end: end || "", notice: `${clock(toMin(start))} is too late: the class needs ${hrsText(need)}.` };
  if (!end) return { start, end: toHHMM(first), notice: `End set to ${clock(first)}, the earliest end (${hrsText(need)} needed). Change it if you like.` };
  if (toMin(end) < first) return { start, end: toHHMM(first), notice: `End moved to ${clock(first)}: ${clock(toMin(end))} left less than ${hrsText(need)}.` };
  return { start, end, notice: "" };
}

/* The row after the Dean picks an End: a Start that would leave too little time is cleared to "Any time" (never an invalid range). */
export function pickEnd(subject, start, end) {
  if (!end || !start) return { start: start || "", end: end || "", notice: "" };
  const need = needMinutes(subject);
  if (toMin(end) - toMin(start) < need) return { start: "", end, notice: `Start cleared: ${clock(toMin(start))}-${clock(toMin(end))} is shorter than ${hrsText(need)}.` };
  return { start, end, notice: "" };
}

export const needHint = (subject, start) => (start
  ? `Needs ${hrsText(needMinutes(subject))} - earliest end ${clock(toMin(start) + needMinutes(subject))}`
  : `Needs ${hrsText(needMinutes(subject))} in one block`);

/* Advice only: is there free time of the professor (free = { Mon: [[a, b]], ... } in minutes) that holds the class inside [a, b]? */
export function professorFits(free, need, a, b) {
  return Object.values(free || {}).some((ws) => (ws || []).some(([x, y]) => Math.min(b, y) - Math.max(a, x) >= need));
}

// "Mon 10:00 AM-1:00 PM, Sat 7:00 AM-4:30 PM": the professor's free windows (availability minus the classes they already teach)
export function freeText(free) {
  const order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return order.flatMap((d) => ((free || {})[d] || []).map(([x, y]) => `${d} ${clock(x)}-${clock(y)}`)).join(", ");
}
