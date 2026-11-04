/* Academic-term structure of the basic-education levels (mirrors backend/basic_ed/structure.py):
   JHS = 3 terms; SHS Grade 11 = 3 terms; SHS Grade 12 = 2 semesters. The server sends `structure` with the overview:
   { "11": {kind, count, label}, "12": {...} }. */
const FALLBACK = { kind: "term", count: 3, label: "Term" };

export const periodInfo = (structure, grade) => (structure && structure[String(grade)]) || FALLBACK;

/* "Term 2" / "Semester 1" for one grade. */
export const periodName = (structure, grade, n) => `${periodInfo(structure, grade).label} ${n}`;

/* Options [[number, label]] for one grade (1..count). */
export const periodOptionsFor = (structure, grade) => {
  const { count, label } = periodInfo(structure, grade);
  return Array.from({ length: count }, (_, i) => [i + 1, `${label} ${i + 1}`]);
};

/* Options that cover every grade of a level (curriculum filters / add-subject form), with the grade named when the
   structure differs, e.g. 1 -> "Term 1 (Grade 11) / Semester 1 (Grade 12)". */
export const periodOptionsAll = (structure) => {
  const grades = Object.keys(structure || {});
  if (!grades.length) return periodOptionsFor(structure, 0);
  const max = Math.max(...grades.map((g) => structure[g].count));
  const mixed = new Set(grades.map((g) => `${structure[g].label}${structure[g].count}`)).size > 1;
  const out = [];
  for (let n = 1; n <= max; n++) {
    const parts = grades.filter((g) => structure[g].count >= n).map((g) => `${structure[g].label} ${n} (Grade ${g})`);
    out.push([n, mixed ? parts.join(" / ") : `${structure[grades[0]].label} ${n}`]);
  }
  return out;
};

/* Column / field heading for a level. */
export const periodHeading = (structure) => {
  const labels = [...new Set(Object.values(structure || {}).map((s) => s.label))];
  return labels.length ? labels.join(" / ") : "Term";
};
