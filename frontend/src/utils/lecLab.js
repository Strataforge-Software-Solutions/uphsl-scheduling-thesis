import React from "react";
import { formatSchedule } from "./formatSchedule";

/* Lec / Lab pairs: a subject's Lecture (code "X") and Laboratory (code "X" + "L") for one section.
   The scheduler always places the Lecture first and the Lab after it, with the same teacher. These helpers only LABEL the pair on the
   schedule tables so it is obvious they belong together and which one comes first; they change no data. */
const DAY = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
const mins = (t) => { const [h, m] = String(t || "0:0").split(":").map(Number); return h * 60 + (m || 0); };
const sectionKey = (r) => `${r.section ?? ""}|${r.program_name ?? ""}|${r.section_name ?? ""}`;
const startOf = (r) => r.start ?? r.timeslot_start;
const endOf = (r) => r.end ?? r.timeslot_end;

// rows: grouped schedule rows (mergeSchedulesByDay) -> {"section|code": first meeting of that subject in the week}
export function buildLecLabIndex(rows) {
  const first = {};
  (rows || []).forEach((r) => {
    if (!r.subject_code) return;
    const k = `${sectionKey(r)}|${r.subject_code}`;
    const pos = (DAY[String(r.timeslot_day).slice(0, 3)] ?? 9) * 1440 + mins(startOf(r));
    if (!first[k] || pos < first[k].pos) first[k] = { pos, row: r };
  });
  return first;
}

// {kind: "Lec" | "Lab", text, title} for a row whose partner is in the same table, otherwise null
export function lecLabInfo(row, index) {
  const code = String(row.subject_code || "");
  const isLab = code.length > 1 && code.endsWith("L");
  const partnerCode = isLab ? code.slice(0, -1) : `${code}L`;
  const p = index[`${sectionKey(row)}|${partnerCode}`];
  if (!p) return null;
  const when = formatSchedule(String(p.row.timeslot_day).slice(0, 3), startOf(p.row), endOf(p.row));
  return isLab
    ? { kind: "Lab", text: `Lab · 2 of 2 · after Lec ${when}`, title: `Laboratory part of ${partnerCode}. The lecture comes first (${when}).` }
    : { kind: "Lec", text: `Lec · 1 of 2 · then Lab ${when}`, title: `Lecture part. Its laboratory ${partnerCode} follows (${when}).` };
}

export function LecLabTag({ row, index }) {
  const info = lecLabInfo(row, index);
  if (!info) return null;
  const lec = info.kind === "Lec";
  return (
    <div title={info.title} style={{ marginTop: 3 }}>
      <span style={{ display: "inline-block", fontSize: 11.5, fontWeight: 600, borderRadius: 999, padding: "1px 8px",
        background: lec ? "#e0f2fe" : "#f3e8ff", color: lec ? "#075985" : "#6b21a8", border: `1px solid ${lec ? "#bae6fd" : "#e9d5ff"}` }}>
        {info.text}
      </span>
    </div>
  );
}
