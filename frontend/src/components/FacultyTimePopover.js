import CustomSelect from "./CustomSelect";
import React, { useEffect, useState } from "react";
import API from "../services/api";
import { formatTime } from "../utils/formatDateTime";

/* Read-only: one teacher's week for the Generate dialog, as a table (one row per day, Monday-Saturday) -- submitted availability (preferred / available / unavailable), the classes
   they already teach this semester, and weekly load vs limit (GET /engine/generate/faculty-time/). Nothing here changes anything. */
const DAYS = [["Mon", "Monday"], ["Tue", "Tuesday"], ["Wed", "Wednesday"], ["Thu", "Thursday"], ["Fri", "Friday"], ["Sat", "Saturday"]];
const DAY_START = 7 * 60, DAY_END = 20 * 60;                      // the college time grid: 7:00 AM - 8:00 PM
const toMin = (t) => { const [h, m] = String(t).split(":").map(Number); return h * 60 + (m || 0); };
const fmt = (m) => formatTime(m);
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

/* One row per day: submitted windows, classes already taught, the BEST free time (their preferred / available windows minus unavailable
   times and their classes; with nothing submitted, 7:00 AM-8:00 PM minus their classes) and the OTHER free time: preferred / available
   windows are priorities, not limits, so the rest of the day (7:00 AM-8:00 PM minus unavailable times and classes) is still possible. */
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
    const also = (data.submitted ? subtract(subtract([[DAY_START, DAY_END]], [...blocked, ...busy]), free) : []).map(([a, b]) => ({ a, b }));
    return { day, name, wins, teach, suggested, also, hours: free.reduce((n, [a, b]) => n + (b - a) / 60, 0) };
  });
}

const toHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

/* A free-time chip; clickable (Dean's assignment) when the time is long enough for the subject. */
function Chip({ day, x, kind, onPick, need, style, children }) {
  const fits = x.b - x.a >= need;
  const base = { display: "inline-block", margin: "0 4px 4px 0", padding: "2px 7px", borderRadius: 6, fontSize: 12, whiteSpace: "nowrap", ...style };
  if (!onPick) return <span style={base}>{children}</span>;
  return (
    <button type="button" disabled={!fits} onClick={() => onPick({ day, a: x.a, b: x.b, kind })}
      title={fits ? "Assign the subject to this teacher at this time" : "Too short for this subject"}
      style={{ ...base, cursor: fits ? "pointer" : "not-allowed", opacity: fits ? 1 : 0.5, boxShadow: "none", textDecoration: fits ? "underline dotted" : "none" }}>
      {children}
    </button>
  );
}

export default function FacultyTimePopover({ teachers = [], initialId = "", semester, programId = "", yearLevel = "", subjectCode = "", onClose,
  needMinutes = 0, onAssign }) {
  /* Dean only (onAssign given): click one of the teacher's free times to assign THIS subject to them on that day and time -- inside
     their preference ("Best time") or overriding it ("Also possible"). It fills the subject's row in the Generate list. */
  const [pick, setPick] = useState(null);              // { day, a, b, kind: "best" | "also", start }
  const [fid, setFid] = useState(String(initialId || (teachers[0] || {}).id || ""));
  const [data, setData] = useState(null);
  const canAssign = typeof onAssign === "function" && needMinutes > 0;
  const [error, setError] = useState("");

  useEffect(() => { setPick(null); }, [fid]);
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
      <div style={{ background: "white", borderRadius: 6, width: "min(760px, 100%)", maxHeight: "90vh", overflow: "auto", padding: "14px 16px", boxShadow: "var(--shadow-pop)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <h3 style={{ margin: 0, color: "#003366", fontSize: 16 }}>Faculty time{subjectCode ? ` — for ${subjectCode}` : ""}</h3>
          <button onClick={onClose} style={{ background: "white", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "4px 12px", fontSize: 13, cursor: "pointer" }}>Close</button>
        </div>
        {teachers.length > 1 && (
          <CustomSelect value={fid} onChange={(e) => setFid(e.target.value)} aria-label="Teacher" style={{ marginTop: 8, fontSize: 13, padding: "4px 6px", maxWidth: "100%" }}>
            {teachers.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </CustomSelect>
        )}
        {error && <p style={{ color: "#b91c1c", fontSize: 13 }}>{error}</p>}
        {!data && !error && <p style={{ fontSize: 13, color: "#6b7280" }}>Loading…</p>}
        {data && (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, margin: "8px 0", fontSize: 13, color: "#111827" }}>
              <strong>{data.name}</strong>
              <span>{data.faculty_type === "part_time" ? "Part-time" : data.faculty_type === "dean" ? "Dean" : "Full-time"}</span>
              <span style={{ color: data.current_hours > data.max_hours ? "#b91c1c" : "#111827" }}>
                Weekly load: <strong>{data.current_hours} of {data.max_hours} hrs</strong> ({data.semester})
              </span>
            </div>
            {!data.submitted && <div style={{ fontSize: 13, color: "#166534", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "5px 8px", marginBottom: 8 }}>No availability submitted (free at any time).</div>}
            <div style={{ overflowX: "auto" }}>
              <table aria-label="Weekly availability by day" style={{ margin: 0, boxShadow: "none", borderCollapse: "collapse", width: "100%", minWidth: 640, fontSize: 13 }}>
                <thead>
                  <tr>
                    {["Day", "Submitted availability", "Already teaching", "Best time (their preference)", "Also possible"].map((h) => (
                      <th key={h} style={{ textAlign: "left", background: "#f3f4f6", color: "#374151", padding: "6px 8px", borderBottom: "1px solid #e5e7eb", fontSize: 12 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dayRows(data).map((r) => (
                    <tr key={r.day} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600, color: "#003366", whiteSpace: "nowrap", verticalAlign: "top" }}>{r.name}</td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {!data.submitted ? <span style={{ color: "#6b7280" }}>Nothing submitted</span>
                          : r.wins.length === 0 ? <span style={{ color: "#6b7280" }}>—</span>
                          : r.wins.map((w, i) => {
                            const t = TONE[w.preference] || TONE.available;
                            return <span key={i} title={t.label} style={{ display: "inline-block", margin: "0 4px 4px 0", padding: "2px 7px", borderRadius: 4, background: t.bg, color: t.fg, border: `1px solid ${t.bd}`, fontSize: 12, whiteSpace: "nowrap" }}>{clock(w.start)}-{clock(w.end)} · {t.label}</span>;
                          })}
                      </td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {r.teach.length === 0 ? <span style={{ color: "#6b7280" }}>—</span>
                          : r.teach.map((t, i) => (
                            <div key={i} title={`${t.section} · ${t.room} (${t.status})`} style={{ fontSize: 12, color: "#111827", whiteSpace: "nowrap" }}>
                              {clock(t.start)}-{clock(t.end)} <strong>{t.code}</strong> <span style={{ color: "#6b7280" }}>({t.section})</span>
                            </div>))}
                      </td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {r.suggested.length === 0 ? <span style={{ color: "#6b7280" }}>—</span>
                          : r.suggested.map((x, i) => (
                            <Chip key={i} day={r.day} x={x} kind="best" onPick={canAssign ? setPick : null} need={needMinutes}
                              style={{ background: x.preferred ? "#dcfce7" : "#f9fafb", color: x.preferred ? "#14532d" : "#111827",
                                border: `1px solid ${x.preferred ? "#86efac" : "#d1d5db"}`, fontWeight: x.preferred ? 700 : 400 }}>
                              {range(x.a, x.b)}{x.preferred ? " (preferred)" : ""}
                            </Chip>))}
                      </td>
                      <td style={{ padding: "6px 8px", verticalAlign: "top" }}>
                        {r.also.length === 0 ? <span style={{ color: "#6b7280" }}>{data.submitted ? "—" : ""}</span>
                          : r.also.map((x, i) => (
                            <Chip key={i} day={r.day} x={x} kind="also" onPick={canAssign ? setPick : null} need={needMinutes}
                              style={{ background: "white", color: "#4b5563", border: "1px dashed #d1d5db" }}>{range(x.a, x.b)}</Chip>))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {canAssign && !pick && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#1e3a8a" }}>
                Click a time above to assign <strong>{subjectCode}</strong> to {data.name} on that day ({needMinutes / 60} hrs needed).
              </div>
            )}
            {canAssign && pick && (() => {
              const starts = [];
              for (let m = pick.a; m + needMinutes <= pick.b; m += 30) starts.push(m);
              const start = pick.start ?? starts[0];
              const DAYS_FULL = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday" };
              return (
                <div role="group" aria-label="Assign this time" style={{ marginTop: 10, padding: "10px 12px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 6, fontSize: 13, color: "#111827" }}>
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                    <span>Assign <strong>{subjectCode}</strong> to <strong>{data.name}</strong> on <strong>{DAYS_FULL[pick.day] || pick.day}</strong>, starting</span>
                    <CustomSelect aria-label="Start of the assigned time" value={start} onChange={(e) => setPick({ ...pick, start: Number(e.target.value) })}
                      style={{ fontSize: 13, padding: "3px 6px" }}>
                      {starts.map((m) => <option key={m} value={m}>{fmt(m)}</option>)}
                    </CustomSelect>
                    <span>to <strong>{fmt(start + needMinutes)}</strong></span>
                  </div>
                  {pick.kind === "also" && (
                    <div style={{ marginTop: 6, color: "#92400e" }}>This is outside {data.name}'s preferred / available time: you are overriding their preference.</div>
                  )}
                  <div style={{ marginTop: 6, color: "#4b5563", fontSize: 12 }}>
                    This sets the Professor, Day and Start / End of {subjectCode} in the Generate list. Nothing is saved until you press Generate,
                    which places it there if the room and the students are free too (otherwise it is skipped with the reason).
                  </div>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
                    <button type="button" onClick={() => setPick(null)} style={{ background: "white", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "4px 12px", fontSize: 13, cursor: "pointer" }}>Cancel</button>
                    <button type="button" onClick={() => onAssign(Number(fid), pick.day, toHHMM(start), toHHMM(start + needMinutes))}
                      style={{ background: "#003366", color: "white", border: "none", borderRadius: 6, padding: "4px 12px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                      Assign to this time
                    </button>
                  </div>
                </div>
              );
            })()}
            <div style={{ marginTop: 6, fontSize: 12, color: "#4b5563" }}>
              Best time = their preferred / available time minus the classes they already teach{data.submitted ? "" : " (nothing submitted: 7:00 AM-8:00 PM minus their classes)"}. Generate uses these first.
              Also possible = the rest of the day (not marked unavailable, no class): Generate may use it when needed, and a Dean may place a class there by hand.
            </div>
            <div style={{ marginTop: 6, fontSize: 12, color: "#6b7280" }}>Drafts that this Generate would replace are not counted. This is for information only; Generate checks everything again.</div>
          </>
        )}
      </div>
    </div>
  );
}
