import React, { useCallback, useEffect, useState } from "react";
import API from "../services/api";
import UnplacedResolve from "./UnplacedResolve";

/* Generate All Minor Schedules: Gen Ed (minor) subjects of CCS, RadTech, Nursing and BAComm in one validated action,
   the departments' minor schedules side by side (shared / separate section, conflicts), and a conflict report. */
const YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"];
const SEMS = ["1st Sem", "2nd Sem", "Summer"];
const DEPTS = ["CCS", "RadTech", "Nursing", "BAComm", "Allied Health", "IHM", "CBA"];
const DEPT_NAME = { CCS: "CCS", RadTech: "RadTech", Nursing: "Nursing", BAComm: "BAComm", "Allied Health": "Allied Health", IHM: "IHM", CBA: "BA (Business)" };
const MODE = {
  shared: { bg: "#dcfce7", fg: "#166534", label: "Shared section" },
  separate: { bg: "#e0e7ff", fg: "#3730a3", label: "Separate sections" },
  mixed: { bg: "#fef3c7", fg: "#92400e", label: "Shared + separate" },
  "not scheduled": { bg: "#f3f4f6", fg: "#6b7280", label: "Not scheduled" },
};

function defaultAcademicYear() {
  const d = new Date();
  const y = d.getMonth() >= 5 ? d.getFullYear() : d.getFullYear() - 1;
  return `${y}-${y + 1}`;
}

const card = { background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "14px 16px", marginBottom: 16 };
const th = { textAlign: "left", padding: "8px 10px", background: "#f3f4f6", borderBottom: "1px solid #e5e7eb", fontSize: 13, color: "#374151", verticalAlign: "bottom" };
const td = { padding: "10px 12px", borderBottom: "1px solid #eef2f7", fontSize: 13, verticalAlign: "top" };

function Tag({ bg, fg, children }) {
  return <span style={{ background: bg, color: fg, borderRadius: 4, padding: "1px 9px", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>{children}</span>;
}

/* One section of one subject in one department: who (program + section + students), how it is shared, and when / where. */
function Cell({ c }) {
  const bad = c.conflicts.length > 0;
  const m = MODE[c.mode] || MODE.separate;
  const others = c.shared_with || [];
  return (
    <div style={{ border: `1px solid ${bad ? "#fca5a5" : "#e5e7eb"}`, borderLeft: `4px solid ${bad ? "#dc2626" : c.mode === "shared" ? "#22c55e" : "#6b7280"}`,
      background: bad ? "#fef2f2" : "#fff", borderRadius: 6, padding: "9px 11px", marginBottom: 8, lineHeight: 1.45 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <span style={{ fontWeight: 600, color: "#111827", overflowWrap: "anywhere" }}>{c.program.replace(/^BS |^BA /, "")} {c.section}</span>
        <span style={{ color: "#6b7280", fontSize: 12, whiteSpace: "nowrap" }}>{c.students} student{c.students === 1 ? "" : "s"}</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, margin: "6px 0" }}>
        <Tag bg={m.bg} fg={m.fg}>{c.mode === "shared" ? "Shared section" : c.mode === "separate" ? "Separate section" : "Not scheduled"}</Tag>
        {c.scheduled && (bad ? <Tag bg="#fee2e2" fg="#991b1b">Conflict</Tag> : <Tag bg="#ecfdf5" fg="#166534">No conflict</Tag>)}
      </div>
      {c.mode === "shared" && others.length > 0 && (
        <div style={{ fontSize: 12, color: "#4b5563", marginBottom: 5, overflowWrap: "anywhere" }} title={others.join(", ")}>
          <span style={{ color: "#6b7280" }}>With: </span>{others.join(", ")}
        </div>)}
      {bad && <div style={{ fontSize: 12, color: "#991b1b", marginBottom: 5, overflowWrap: "anywhere" }}>{c.conflicts.join(", ")}</div>}
      {c.blocks.map((b, i) => (
        <div key={i} style={{ borderTop: i ? "1px dashed #e5e7eb" : "none", paddingTop: i ? 5 : 0, marginTop: i ? 5 : 0 }}>
          <div style={{ color: "#003366", fontWeight: 600 }}>{b.day} {b.time}</div>
          <div style={{ color: "#374151", overflowWrap: "anywhere" }}>Room {b.room}</div>
          <div style={{ color: "#6b7280", overflowWrap: "anywhere" }}>{b.teacher}</div>
        </div>
      ))}
    </div>
  );
}

export function Comparison({ data }) {
  if (!data) return null;
  if (!data.groups.length) return <p style={{ fontSize: 13, color: "#6b7280" }}>No minor subjects found for this semester and year level.</p>;
  const cols = data.departments.length ? data.departments : DEPTS;
  const SUBJ_W = 230, DEPT_W = 250;
  const head = { ...th, position: "sticky", top: 0, zIndex: 2, padding: "11px 12px", background: "#e8eef6", color: "#003366", borderBottom: "2px solid #d1d5db" };
  return (
    <div style={{ overflow: "auto", maxHeight: "75vh", border: "1px solid #e5e7eb", borderRadius: 6 }}>
      <table style={{ borderCollapse: "separate", borderSpacing: 0, width: "100%", minWidth: SUBJ_W + cols.length * DEPT_W, tableLayout: "fixed" }}>
        <colgroup><col style={{ width: SUBJ_W }} />{cols.map((d) => <col key={d} style={{ width: DEPT_W }} />)}</colgroup>
        <thead>
          <tr>
            <th style={{ ...head, left: 0, zIndex: 3 }}>Subject</th>
            {cols.map((d) => <th key={d} style={head}>{DEPT_NAME[d] || d}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.groups.map((g, i) => {
            const m = MODE[g.mode] || MODE.separate;
            const bg = i % 2 ? "#f9fafb" : "#ffffff";
            const cell = { ...td, padding: "12px", background: bg, borderBottom: "1px solid #e5e7eb", verticalAlign: "top" };
            return (
              <tr key={i}>
                <td style={{ ...cell, position: "sticky", left: 0, zIndex: 1, borderRight: "1px solid #e5e7eb" }}>
                  <div style={{ fontWeight: 600, color: "#111827", overflowWrap: "anywhere" }}>{g.code}</div>
                  <div style={{ color: "#111827", margin: "2px 0 4px", overflowWrap: "anywhere" }}>{g.title}</div>
                  <div style={{ color: "#6b7280", fontSize: 12, marginBottom: 6 }}>{g.year_level} · {g.units} unit{g.units === 1 ? "" : "s"}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                    <Tag bg={m.bg} fg={m.fg}>{m.label}</Tag>{g.conflict && <Tag bg="#fee2e2" fg="#991b1b">Has conflict</Tag>}
                  </div>
                </td>
                {cols.map((d) => {
                  const cells = g.cells.filter((c) => c.department === d);
                  return (
                    <td key={d} style={cell}>
                      {cells.length ? cells.map((c) => <Cell key={c.section_id} c={c} />)
                        : <div style={{ color: "#6b7280", fontSize: 12, textAlign: "center", padding: "10px 0" }}>Not in this curriculum</div>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const CAT = { "minor-minor": "Minor – Minor", "minor-major": "Minor – Major", "major-major": "Major – Major" };

export function ConflictTable({ conflicts }) {
  if (!conflicts || !conflicts.length) return null;
  const heads = ["Conflict", "Subject", "Department", "Year level", "Semester", "Section", "Day", "Time", "Room"];
  const w = [150, 260, 130, 90, 90, 90, 90, 130, 90];
  const cell = { ...td, padding: "10px 12px", overflowWrap: "anywhere", borderBottom: "1px solid #e5e7eb" };
  return (
    <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 6 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1000, tableLayout: "fixed" }}>
        <colgroup>{w.map((x, i) => <col key={i} style={{ width: x }} />)}</colgroup>
        <thead><tr>{heads.map((h) => <th key={h} style={{ ...th, padding: "10px 12px" }}>{h}</th>)}</tr></thead>
        <tbody>
          {conflicts.flatMap((c, i) => [c.a, c.b].map((x, j) => (
            <tr key={`${i}-${j}`} style={{ background: i % 2 ? "#f9fafb" : "white" }}>
              {j === 0 && <td style={{ ...cell, borderRight: "1px solid #e5e7eb" }} rowSpan={2}><Tag bg="#fee2e2" fg="#991b1b">{c.kind_label}</Tag><div style={{ color: "#6b7280", marginTop: 4 }}>{CAT[c.category] || ""}</div></td>}
              <td style={cell}><strong>{x.code}</strong> {x.title}</td>
              <td style={cell}>{x.department}</td>
              <td style={cell}>{x.year_level}</td>
              <td style={cell}>{x.semester}</td>
              <td style={cell}>{x.section}</td>
              <td style={cell}>{x.day}</td>
              <td style={cell}>{x.time.replace(/^\w+ /, "")}</td>
              <td style={cell}>{x.room}</td>
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  );
}

export default function MinorSchedulesPanel() {
  const [schoolYear, setSchoolYear] = useState(defaultAcademicYear());
  const [semester, setSemester] = useState("1st Sem");
  const [yearLevel, setYearLevel] = useState("1st Year");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);       // response of Generate All (201) or a blocked (422) payload
  const [cmp, setCmp] = useState(null);
  const [live, setLive] = useState(null);           // current conflicts of the chosen scope (when nothing was generated yet)

  const load = useCallback(async () => {
    try {
      const yl = yearLevel === "All" ? "" : yearLevel;
      const [c, r] = await Promise.all([
        API.get("/engine/minor/comparison/", { params: { semester, year_level: yl } }),
        API.get("/engine/conflicts/", { params: { semester } }),
      ]);
      setCmp(c.data);
      setLive(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Could not load the minor schedules.");
    }
  }, [semester, yearLevel]);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setBusy(true); setError(""); setResult(null);
    try {
      const res = await API.post("/engine/minor/generate-all/", { school_year: schoolYear, semester, year_level: yearLevel }, { timeout: 600000 });
      setResult(res.data);
    } catch (e) {
      const d = e.response?.data;
      if (e.response?.status === 422 && d) setResult({ blocked: true, ...d });
      else setError(d?.detail || "Could not generate the minor schedules.");
    }
    await load();
    setBusy(false);
  };

  const sel = { padding: "8px 10px", borderRadius: 6, border: "1px solid #d1d5db" };
  const stat = (label, value, color) => (
    <div style={{ minWidth: 130 }}><div style={{ fontSize: 18, fontWeight: 600, color: color || "#111827", fontVariantNumeric: "tabular-nums" }}>{value}</div><div style={{ fontSize: 12, color: "#6b7280" }}>{label}</div></div>
  );
  const scoped = (live?.conflicts || []).filter((c) => (yearLevel === "All" || [c.a.year_level, c.b.year_level].includes(yearLevel)));
  const ok = result && !result.blocked && result.validated;

  return (
    <div>
      <div style={card}>
        <p style={{ fontSize: 13, color: "#4b5563", marginTop: 0, maxWidth: 820 }}>
          Generates the Gen Ed (minor) subjects of <strong>CCS, RadTech, Nursing, BAComm, Allied Health, IHM and BA</strong> in one action. Equivalent subjects
          (same code, units and title) share one section when their combined students fit the room and everyone is free; otherwise each department
          gets its own section. The result is re-checked against every schedule (including major subjects) and is only kept when it has no teacher, room or student conflict.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ fontSize: 13, color: "#4b5563" }}>Academic year<br />
            <input value={schoolYear} onChange={(e) => setSchoolYear(e.target.value)} placeholder="2026-2027" style={{ ...sel, width: 120 }} aria-label="Academic year" />
          </label>
          <label style={{ fontSize: 13, color: "#4b5563" }}>Semester<br />
            <select value={semester} onChange={(e) => setSemester(e.target.value)} style={sel} aria-label="Semester">{SEMS.map((s) => <option key={s}>{s}</option>)}</select>
          </label>
          <label style={{ fontSize: 13, color: "#4b5563" }}>Year level<br />
            <select value={yearLevel} onChange={(e) => setYearLevel(e.target.value)} style={sel} aria-label="Year level">
              <option value="All">All year levels</option>{YEARS.map((y) => <option key={y}>{y}</option>)}
            </select>
          </label>
          <button onClick={generate} disabled={busy || !schoolYear.trim()} style={{ alignSelf: "flex-end" }}>{busy ? "Generating…" : "Generate All Minor Schedules"}</button>
        </div>
        <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 0 }}>Running it again replaces the earlier draft minor classes of this semester and year level (no duplicates). Approved or published classes are never changed.</p>
      </div>

      {error && <p style={{ color: "#b91c1c", fontSize: 13 }}>{error}</p>}

      {result && result.blocked && (
        <div style={{ ...card, borderColor: "#fecaca", background: "#fef2f2" }}>
          <strong style={{ color: "#991b1b" }}>Not saved: {result.detail}</strong>
          <p style={{ fontSize: 13, color: "#7f1d1d" }}>The existing schedule was left unchanged. Conflicts found in the new schedule:</p>
          <ConflictTable conflicts={result.conflicts} />
        </div>
      )}

      {result && !result.blocked && (
        <div style={{ ...card, borderColor: ok ? "#a7f3d0" : "#fde68a", background: ok ? "#f0fdf4" : "#fffbeb" }}>
          <div style={{ fontWeight: 600, color: ok ? "#166534" : "#92400e", marginBottom: 10 }}>{result.message}</div>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 12 }}>
            {stat("Conflicts detected before generating", result.conflicts_before)}
            {stat("Conflicts remaining after validation", result.conflicts_after, result.conflicts_after ? "#b91c1c" : "#166534")}
            {stat("Class periods created", result.created_rows)}
            {stat("Sections that joined a shared class", result.groups.actually_shared)}
            {stat("Classes that could not be placed", result.unplaced, result.unplaced ? "#b91c1c" : undefined)}
          </div>
          {result.capacity_warnings?.length > 0 && (
            <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", color: "#9a3412", borderRadius: 6, padding: "8px 12px", fontSize: 13, marginBottom: 12 }}>
              <strong>{result.capacity_warnings.length} class(es) have more students than seats</strong> (no allowed room is big enough). They were placed without a conflict; split the section or add a bigger room:
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {result.capacity_warnings.slice(0, 8).map((w, i) => <li key={i}>{w.subject} · {w.section}: {w.students} students in {w.room} ({w.capacity} seats)</li>)}
                {result.capacity_warnings.length > 8 && <li>…and {result.capacity_warnings.length - 8} more</li>}
              </ul>
            </div>
          )}
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 640 }}>
              <thead><tr>{["Department", "Program", "Year level", "Created", "Joined shared classes", "Status"].map((h) => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>{result.runs.map((r, i) => (
                <tr key={i}><td style={td}>{r.department}</td><td style={td}>{r.program}</td><td style={td}>{r.year_level}</td><td style={td}>{r.created}</td><td style={td}>{r.merged}</td>
                  <td style={td}>{r.status === "skipped" ? <span style={{ color: "#6b7280" }}>Skipped: {r.note}</span> : r.unplaced.length ? <span style={{ color: "#b91c1c" }}>{r.unplaced.length} not placed</span> : "Generated"}</td></tr>
              ))}</tbody>
            </table>
          </div>
          {result.unplaced > 0 && (
            <UnplacedResolve
              items={result.runs.flatMap((r) => r.unplaced_items || [])} semester={semester} schoolYear={schoolYear}
              title="Gen Ed classes not placed"
              onDone={(d) => { setResult((cur) => cur && ({ ...cur, unplaced: Math.max(0, cur.unplaced - (d.placed || 0)) })); load(); }} />
          )}
        </div>
      )}

      <div style={card}>
        <h3 style={{ margin: "0 0 4px", fontSize: 16 }}>Minor schedule comparison</h3>
        <p style={{ fontSize: 13, color: "#6b7280", marginTop: 0 }}>Each subject is shown for every department that takes it, with its day, time, room and teacher, and whether the students share one section or have separate ones.</p>
        <Comparison data={cmp} />
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 6px", fontSize: 16 }}>Conflict report</h3>
        {live && (
          <p style={{ fontSize: 13, color: scoped.length ? "#991b1b" : "#166534", marginTop: 0 }}>
            {result && !result.blocked
              ? `${result.conflicts_before} conflict(s) detected before generation · ${result.conflicts_after} remaining after the new schedule was validated.`
              : `${scoped.length} conflict(s) currently detected in ${semester}${yearLevel === "All" ? "" : ", " + yearLevel}.`}
            {" "}Checked against major and minor subjects.
          </p>
        )}
        {scoped.length ? <ConflictTable conflicts={scoped} /> : live && <p style={{ fontSize: 13, color: "#166534" }}>No teacher, room or student conflicts in this scope.</p>}
      </div>
    </div>
  );
}
