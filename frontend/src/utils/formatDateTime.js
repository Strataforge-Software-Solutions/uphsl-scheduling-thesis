/* One place that turns times and dates into text on screen, following "My settings" > Language and format.
   Display only: stored values and what is sent to the API stay exactly as they are ("13:30:00", "2026-11-06").
   The print/PDF output is built on the server and does not use this. */

export const TIME_ZONE = "Asia/Manila";

let current = { time_format: "12h", date_format: "mdy_short" };

export function setFormatPrefs(p) {
  if (!p) return;
  current = {
    time_format: p.time_format === "24h" ? "24h" : "12h",
    date_format: ["mdy_short", "dmy", "iso"].includes(p.date_format) ? p.date_format : "mdy_short",
  };
}
export const getFormatPrefs = () => ({ ...current });

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WD_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WD_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const pad = (n) => String(n).padStart(2, "0");

// a moment in time (Date, or an ISO string with a time part) -> its parts in Manila time
function manilaParts(d) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: TIME_ZONE, year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", hourCycle: "h23", weekday: "short",
    }).formatToParts(d);
    const get = (t) => (parts.find((p) => p.type === t) || {}).value;
    return { y: Number(get("year")), mo: Number(get("month")), d: Number(get("day")), h: Number(get("hour")) % 24, mi: Number(get("minute")),
      wd: WD_SHORT.indexOf(get("weekday")) };
  } catch (e) {
    return { y: d.getFullYear(), mo: d.getMonth() + 1, d: d.getDate(), h: d.getHours(), mi: d.getMinutes(), wd: d.getDay() };
  }
}

// "13:30", "13:30:00", minutes since midnight (810) or a Date -> { h, m }
function hourMinute(v) {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number" && Number.isFinite(v)) return { h: Math.floor(v / 60), m: Math.round(v % 60) };
  if (v instanceof Date) { if (Number.isNaN(v.getTime())) return null; const p = manilaParts(v); return { h: p.h, m: p.mi }; }
  const s = String(v);
  const hit = /^(\d{1,2}):(\d{2})/.exec(s);
  if (hit) return { h: Number(hit[1]), m: Number(hit[2]) };
  const d = new Date(s);
  if (!Number.isNaN(d.getTime())) { const p = manilaParts(d); return { h: p.h, m: p.mi }; }
  return null;
}

/* formatTime("13:30") -> "1:30 PM" (12-hour) or "13:30" (24-hour).
   compact: no space before AM/PM ("1:30PM"), the UPHSL schedule style used in the schedule tables. */
export function formatTime(v, { compact = false } = {}) {
  const t = hourMinute(v);
  if (!t) return "";
  if (current.time_format === "24h") return `${pad(t.h)}:${pad(t.m)}`;
  return `${((t.h + 11) % 12) + 1}:${pad(t.m)}${compact ? "" : " "}${t.h % 24 < 12 ? "AM" : "PM"}`;
}

export function formatTimeRange(a, b, sep = " – ", opts) {
  return `${formatTime(a, opts)}${sep}${formatTime(b, opts)}`;
}

// a date-only value "2026-11-06" is a calendar day (no time zone shift); anything with a time is read in Manila time
function dateParts(v) {
  if (v === null || v === undefined || v === "") return null;
  const s = typeof v === "string" ? v : "";
  const only = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (only) {
    const y = Number(only[1]), mo = Number(only[2]), d = Number(only[3]);
    return { y, mo, d, wd: new Date(y, mo - 1, d).getDay() };
  }
  const d = v instanceof Date ? v : new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  return manilaParts(d);
}

/* formatDate("2026-11-06") -> "Nov 6, 2026" | "06/11/2026" | "2026-11-06".
   weekday: "short" ("Fri, Nov 6, 2026") or "long" ("Friday, Nov 6, 2026"). */
export function formatDate(v, { weekday } = {}) {
  const p = dateParts(v);
  if (!p) return "";
  let out;
  if (current.date_format === "dmy") out = `${pad(p.d)}/${pad(p.mo)}/${p.y}`;
  else if (current.date_format === "iso") out = `${p.y}-${pad(p.mo)}-${pad(p.d)}`;
  else out = `${MONTHS[p.mo - 1]} ${p.d}, ${p.y}`;
  if (weekday === "short") return `${WD_SHORT[p.wd]}, ${out}`;
  if (weekday === "long") return `${WD_LONG[p.wd]}, ${out}`;
  return out;
}

// "2026-11-06T05:30:00Z" -> "Nov 6, 2026 1:30 PM"
export function formatDateTime(v) {
  const p = dateParts(v);
  if (!p || p.h === undefined) return formatDate(v);
  return `${formatDate(v)} ${formatTime(p.h * 60 + p.mi)}`;
}
