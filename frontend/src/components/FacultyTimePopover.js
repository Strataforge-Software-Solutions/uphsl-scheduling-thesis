import React, { useEffect, useState } from "react";
import API from "../services/api";

/* Read-only: one teacher's week for the Generate dialog, as a table (one row per day, Monday-Saturday) -- submitted availability (preferred / available / unavailable), the classes
   they already teach this semester, and weekly load vs limit (GET /engine/generate/faculty-time/). Nothing here changes anything. */
const DAYS = [["Mon", "Monday"], ["Tue", "Tuesday"], ["Wed", "Wednesday"], ["Thu", "Thursday"], ["Fri", "Friday"], ["Sat", "Saturday"]];
const DAY_START = 7 * 60, DAY_END = 20 * 60;                      // the college time grid: 7:00 AM - 8:00 PM
const toMin = (t) => { const [h, m] = String(t).split(":").map(Number); return h * 60 + (m || 0); };
const fmt = (m) => { const h = Math.floor(m / 60); return `${((h + 11) % 12) + 1}:${String(m % 60).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
const clock = (t) => fmt(toMin(t));
const range = (a, b) => `${fmt(a)}-${fmt(b)}`;
const TONE = {
  preferred: { bg: "#dcfce7", fg: "#14532d", bd: "#86efac", label: "Preferred" },
  available: { bg: "#dbeafe", fg: "#1e3a8a", bd: "#93c5fd", label: "Available" },
  unavailable: { bg: "#fee2e2", fg: "#7f1d1d", bd: "#fca5a5", label: "Unavailable" },
};

/* [[a, b], ...] minus [[c, d], ...] (minutes), keeping pieces of at least 30 minutes */
function subtract(spans, cuts) {
  let out = spans.map(([a, b]) => [a, b]);
  cuts.forEach(([c, d]) => {
    out = out.flatMap(([a, b]) => (d <= a || c >= b ? [[a, b]] : [[a, Math.min(b, c)], [Math.max(a, d), b]]).filter(([x, y]) => y - x >= 30));
  });
  return out.sort((x, y) => x[0] - y[0]);
}

/* One row per day: submitted windows, classes already taught, and the SUGGESTED free time (their available / preferred windows minus
   unavailable times and their classes; with nothing submitted, 7:00 AM-8:00 PM minus their classes). Advice only. */
export function dayRows(data) {
  return DAYS.map(([day, name]) => {
    const wins = (data.availability || []).filter((w) => w.day === day).sort((x, y) => toMin(x.start) - toMin(y.start));
    const teach = (data.teaching || []).filter((t) => t.day === day).sort((x, y) => toMin(x.start) - toMin(y.start));
    const busy = teach.map((t) => [toMin(t.start), toMin(t.end)]);
    const blocked = wins.filter((w) => w.preference === "unavailable").map((w) => [toMin(w.start), toMin(w.end)]);
    const pos = (pref) => wins.filter((w) => (pref ? w.preference === "preferred" : w.preference !== "unavailable"))
      .map((w) => [Math.max(DAY_START, toMin(w.start)), Math.min(DAY_END, toMin(w.end))]);
    const base = data.submitted ? (pos(false).length ? pos(false) : (blocked.length ? [[DAY_START, DAY_END]] : [])) : [[DAY_START, DAY_END]];
    const free = subtract(base, [...blocked, ...busy]);
    const prefFree = subtract(pos(true), [...blocked, ...busy]);
    const suggested = free.map(([a, b]) => ({ a, b, preferred: prefFree.some(([c, d]) => c < b && d > a) }));
    return { day, name, wins, teach, suggested, hours: free.reduce((n, [a, b]) => n + (b - a) / 60, 0) };
  });
}

export default function FacultyTimePopover({ teachers = [], initialId = "", semester, programId = "", yearLevel = "", subjectCode = "", onClose }) {
  const [fid, setFid] = useState(String(initialId || (teachers[0] || {}).id || ""));
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!fid || !semester) return undefined;
    let gone = false;
    setData(null); setError("");
    API.get("/engine/generate/faculty-time/", { params: { faculty_id: fid, semester, program_id: programId || undefined, year_level: yearLevel || undefined } })
      .then((r) => { if (!gone) setData(r.data); })
      .catch((e) => { if (!gone) setError(e.response?.data?.detail || "Could not load this teacher's time."); });
    return () => { gone = true; };
  }, [fid, semester, programId, yearLevel]);

  return (
    <div role="dialog" aria-label="Faculty time" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.35)", zIndex: 2000, display: "flex", alignItems: "center", justifyContent: "center", padding: 12 }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: "white", borderRadius: 12, width: "min(760px, 100%)", maxHeight: "90vh", overflow: "auto", padding: "14px 16px", boxShadow: "0 12px 40px rgba(0,0,0,.3)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <h3 style={{ margin: 0, color: "#003366", fontSize: 16 }}>Faculty time{subjectCode ? ` — for ${subjectCode}` : ""}</h3>
          <button onClick={onClose} style={{ background: "white", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "4px 12px", fontSize: 12.5, cursor: "pointer" }}>Close</button>
        </div>
        {teachers.length > 1 && (
          <select value={fid} onChange={(e) => setFid(e.target.value)} aria-label="Teacher" style={{ marginTop: 8, fontSize: 13, padding: "4px 6px", maxWidth: "100%" }}>
            {teachers.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        )}
        {error && <p style={{ color: "#a4231a", fontSize: 13 }}>{error}</p>}
        {!data && !error && <p style={{ fontSize: 13, color: "#64748b" }}>Loading…</p>}
        {data && (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, margin: "8px 0", fontSize: 13, color: "#1e293b" }}>
              <strong>{data.name}</strong>
              <span>{data.faculty_type === "part_time" ? "Part-time" : data.faculty_type === "dean" ? "Dean" : "Full-time"}</span>
              <span style={{ color: data.current_hours > data.max_hours ? "#a4231a" : "#1e293b" }}>
                Weekly load: <strong>{data.current_hours} of {data.max_hours} hrs</strong> ({data.semester})
              </span>
            </div>
            {!data.submitted && <div style={{ fontSize: 12.5, color: "#166534", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "5px 8px", marginBottom: 8 }}>No availability submitted (free at any time).</div>}
            <div style={{ overflowX: "auto" }}>
              <table aria-label="Weekly availability by day" style={{ margin: 0, boxShadow: "none", borderCollapse: "collapse", width: "100%", minWidth: 520, fontSize: 12.5 }}>
                <thead>
                  <tr>
                    {["Day", "Submitted availability", "Already teaching", "Suggested free time"].map((h) => (
                      <th key={h} style={{ textAlign: "left", background: "#f1f5f9", color: "#334155", padding: "6px 8px", borderBottom: "1px solid #e2e8f0", fontSize: 12 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dayRows(data).map((r) => (
                    <tr key={r.day} style={{ borderBottom: "1px solid #eef2f6" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 700, color: "#003366", whiteSpace: "nowrap", verticalAlign: "top" }}>{r.name}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {!data.submitted ? <span style={{ color: "#64748b" }}>Nothing submitted</span>
                          : r.wins.length === 0 ? <span style={{ color: "#94a3b8" }}>—</span>
                          : r.wins.map((w, i) => {
                            const t = TONE[w.preference] || TONE.available;
                            return <span key={i} title={t.label} style={{ display: "inline-block", margin: "0 4px 4px 0", padding: "2px 7px", borderRadius: 999, background: t.bg, color: t.fg, border: `1px solid ${t.bd}`, fontSize: 11.5, whiteSpace: "nowrap" }}>{clock(w.start)}-{clock(w.end)} · {t.label}</span>;
                          })}
                      </td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {r.teach.length === 0 ? <span style={{ color: "#94a3b8" }}>—</span>
                          : r.teach.map((t, i) => (
                            <div key={i} title={`${t.section} · ${t.room} (${t.status})`} style={{ fontSize: 11.5, color: "#1e293b", whiteSpace: "nowrap" }}>
                              {clock(t.start)}-{clock(t.end)} <strong>{t.code}</strong> <span style={{ color: "#64748b" }}>({t.section})</span>
                            </div>))}
                      </td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {r.suggested.length === 0 ? <span style={{ color: "#94a3b8" }}>Not free</span>
                          : r.suggested.map((x, i) => (
                            <span key={i} style={{ display: "inline-block", margin: "0 4px 4px 0", padding: "2px 7px", borderRadius: 6, fontSize: 11.5, whiteSpace: "nowrap",
                              background: x.preferred ? "#dcfce7" : "#f8fafc", color: x.preferred ? "#14532d" : "#1e293b", border: `1px solid ${x.preferred ? "#86efac" : "#cbd5e1"}`, fontWeight: x.preferred ? 700 : 400 }}>
                              {range(x.a, x.b)}{x.preferred ? " ★" : ""}
                            </span>))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 6, fontSize: 11.5, color: "#475569" }}>
              Suggested free time = their submitted available / preferred time minus unavailable times and the classes they already teach{data.submitted ? "" : " (nothing submitted: 7:00 AM-8:00 PM minus their classes)"}. ★ = inside their preferred time.
            </div>
            <div style={{ marginTop: 6, fontSize: 11.5, color: "#64748b" }}>Drafts that this Generate would replace are not counted. This is for information only; Generate checks everything again.</div>
          </>
        )}
      </div>
    </div>
  );
}
