import { formatTime } from "./formatDateTime";
/* "Suggested" professors for one subject row of the Generate preview -- ADVICE ONLY (the server re-checks everything on Generate).
   Every teacher passed in is already qualified (the server's list). A teacher is suggested when
     - this row (all its sections), plus the other rows already chosen for them, stays within their weekly limit, and
     - their free time (inside their availability, minus the classes they already teach) holds every class block of the row for every
       section, inside the Dean's Start-End range.
   Rooms and the section's other classes are not considered here. Ranking: most overlap with their "preferred" time, then lower load. */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const clock = (m) => formatTime(m);

function clip(intervals, range) {
  if (!range) return intervals.map(([a, b]) => [a, b]);
  return intervals.map(([a, b]) => [Math.max(a, range[0]), Math.min(b, range[1])]).filter(([a, b]) => b > a);
}

/* Free time inside the range, per day: [{day, a, b}] in week order. */
function freeInRange(teacher, range) {
  const out = [];
  DAYS.forEach((d) => clip((teacher.free || {})[d] || [], range).forEach(([a, b]) => out.push({ day: d, a, b })));
  return out;
}

/* Can all blocks (each section needs every block) be laid in the free time without overlapping? Longest blocks first. */
export function fits(free, blocks, sections) {
  const need = [];
  for (let i = 0; i < Math.max(1, sections); i += 1) need.push(...blocks);
  need.sort((x, y) => y - x);
  const left = free.map((f) => ({ ...f }));
  for (const len of need) {
    const slot = left.find((f) => f.b - f.a >= len);
    if (!slot) return false;
    slot.a += len;
  }
  return true;
}

function preferredOverlap(teacher, free) {
  let n = 0;
  free.forEach(({ day, a, b }) => ((teacher.preferred || {})[day] || []).forEach(([c, d]) => { n += Math.max(0, Math.min(b, d) - Math.max(a, c)); }));
  return n;
}

const hrs = (n) => `${Math.round(n * 100) / 100}`;

/* teachers: [{id, label, current_hours, max_hours, free, preferred}]; row: {blocks, sections, total_hours};
   range: [startMin, endMin] or null; otherHours(teacherId): hours of OTHER rows already chosen for that teacher. */
export function rankProfessors(teachers, row, range, otherHours = () => 0) {
  const suggested = [], others = [];
  // Guard (the caller only ranks a row whose data has loaded): a missing row or teacher list must never break the dialog.
  if (!row || !Array.isArray(teachers)) {
    // eslint-disable-next-line no-console
    console.warn("rankProfessors: no professor data for this row; showing 'No suggestions'.", { row, teachers });
    return { suggested, others, missing: true };
  }
  const blocks = (row.blocks && row.blocks.length) ? row.blocks : [60];
  const longest = Math.max(...blocks);
  teachers.forEach((t) => {
    const load = (Number(t.current_hours) || 0) + (Number(otherHours(t.id)) || 0);
    const after = load + (row.total_hours || 0);
    const within = !(t.max_hours > 0) || after <= t.max_hours + 1e-9;
    const free = freeInRange(t, range);
    const ok = row.sections > 0 ? fits(free, blocks, row.sections) : free.some((f) => f.b - f.a >= longest);
    const loadText = `${hrs(load)} of ${t.max_hours} hrs`;
    if (within && ok) {
      const first = free.filter((f) => f.b - f.a >= longest).slice(0, 2).map((f) => `${f.day} ${clock(f.a)}-${clock(f.b)}`);
      suggested.push({ teacher: t, why: `Free ${first.join(", ")} · ${loadText}`, pref: preferredOverlap(t, free), load });
    } else {
      others.push({ teacher: t, badge: !within ? `Over weekly limit (${hrs(after)} of ${t.max_hours} hrs)` : "No matching free time", loadText });
    }
  });
  suggested.sort((x, y) => (y.pref - x.pref) || (x.load - y.load) || String(x.teacher.label).localeCompare(String(y.teacher.label)));
  others.sort((x, y) => String(x.teacher.label).localeCompare(String(y.teacher.label)));
  return { suggested, others, missing: false };
}
