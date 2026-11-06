import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Badge from "./Badge";
import { StatTile, HBarChart } from "./Charts";
import { be, errText, inputStyle, cardStyle, btn, btnPrimary, Notice } from "./basicEdUi";
import { periodOptionsAll } from "../utils/terms";
import { formatTime } from "../utils/formatDateTime";

/* Principal's Analytics tab (SHS or JHS, never both): teacher workload from the LATEST generated timetables of this school level.
   Same look as the Dean's Analytics (stat tiles, bar charts, cards). Read-only, except "Apply" on a recommendation, which changes the
   teacher of those periods through the same endpoint the Schedules tab uses, so every scheduling rule is still validated. The page
   re-reads the server every 30 s while it is visible and whenever the window regains focus, so a new or edited timetable shows up. */

const STATUS = {
  over: { label: "Overloaded", tone: "warning", color: "#b91c1c" },
  at_limit: { label: "At limit", tone: "neutral", color: "#b45309" },
  balanced: { label: "Balanced", tone: "success", color: "#003366" },
  under: { label: "Underloaded", tone: "neutral", color: "#5b7fa6" },
};
const DAY_NAME = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday" };
const KIND_LABEL = { overload: "Overload", daily_limit: "Daily limit", double_booked: "Double-booked", availability: "Availability",
  specialization: "Specialization", no_replacement: "No replacement", no_teacher: "No teacher" };
const REFRESH_MS = 30000;
const th = { textAlign: "left", padding: "9px 12px", background: "#f3f4f6", borderBottom: "1px solid #e5e7eb", fontSize: 13, color: "#374151", whiteSpace: "nowrap" };
const td = { padding: "10px 12px", borderBottom: "1px solid #eef2f7", fontSize: 13, verticalAlign: "top" };
const fmt = (h) => (Number.isInteger(h) ? String(h) : String(Math.round(h * 10) / 10));

function LoadBar({ value, max, status }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div style={{ minWidth: 110 }}>
      <div style={{ background: "#e8eef7", borderRadius: 4, height: 8, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: (STATUS[status] || STATUS.balanced).color }} />
      </div>
      <div style={{ fontSize: 12, color: "#6b7280", marginTop: 3 }}>{fmt(value)} / {max} h</div>
    </div>
  );
}

function TeacherDetail({ t }) {
  return (
    <div style={{ padding: "12px 16px", background: "#f7f9fc", fontSize: 13 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
        <div>
          <div style={{ fontWeight: 600, color: "#003366", marginBottom: 6 }}>Assigned subjects</div>
          {t.subjects.length === 0 ? <span style={{ color: "#6b7280" }}>No classes in this timetable.</span> : (
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <tbody>{t.subjects.map((s) => (
                <tr key={s.code}>
                  <td style={{ padding: "4px 8px 4px 0", overflowWrap: "anywhere" }}><b>{s.code}</b> {s.name}</td>
                  <td style={{ padding: "4px 0", color: "#4b5563", whiteSpace: "nowrap" }}>{s.sections.length} section{s.sections.length === 1 ? "" : "s"} · {s.periods} periods · {fmt(s.hours)} h</td>
                </tr>))}</tbody>
            </table>)}
        </div>
        <div>
          <div style={{ fontWeight: 600, color: "#003366", marginBottom: 6 }}>Class hours by day</div>
          {Object.keys(t.hours_by_day).length === 0 ? <span style={{ color: "#6b7280" }}>—</span>
            : Object.entries(t.hours_by_day).map(([d, h]) => <div key={d}>{DAY_NAME[d] || d}: <b>{fmt(h)} h</b></div>)}
        </div>
        <div>
          <div style={{ fontWeight: 600, color: "#003366", marginBottom: 6 }}>Specialization &amp; availability</div>
          <div>{t.specializations.length ? t.specializations.join(", ") : <span style={{ color: "#6b7280" }}>No specialization recorded</span>}</div>
          <div style={{ color: "#4b5563", marginTop: 4 }}>Available: {t.available_days.length ? t.available_days.map((d) => DAY_NAME[d] || d).join(", ") : "all days (no limits set)"}</div>
          {t.department && <div style={{ color: "#4b5563" }}>Department: {t.department}{t.strand ? ` · ${t.strand}` : ""}</div>}
        </div>
      </div>
    </div>
  );
}

export default function BasicEdAnalytics({ level, overview }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState("");
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);
  const [applying, setApplying] = useState(null);
  const [note, setNote] = useState(null);
  const [updated, setUpdated] = useState(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const load = useCallback((quiet) => {
    if (!quiet) setError("");
    be.get(level, "analytics/workload/", period ? { period } : {})
      .then((r) => { if (!alive.current) return; setData(r.data); setError(""); setUpdated(new Date()); })
      .catch((e) => { if (alive.current && !quiet) setError(errText(e, "Could not load the analytics.")); });
  }, [level, period]);

  useEffect(() => { setData(null); load(false); }, [load]);
  useEffect(() => {
    const tick = () => { if (!document.hidden) load(true); };
    const id = setInterval(tick, REFRESH_MS);
    window.addEventListener("focus", tick);
    return () => { clearInterval(id); window.removeEventListener("focus", tick); };
  }, [load]);

  const periodOptions = useMemo(() => periodOptionsAll(overview?.structure), [overview]);
  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.teachers.filter((t) => (status === "all" || t.status === status)
      && (!needle || `${t.full_name} ${t.employee_id} ${t.subjects.map((s) => s.code + " " + s.name).join(" ")}`.toLowerCase().includes(needle)))
      .sort((a, b) => b.hours - a.hours);
  }, [data, status, q]);

  const apply = async (rec, i) => {
    setApplying(i); setNote(null);
    try {
      for (const id of rec.entry_ids) await be.patch(level, `entries/${id}/`, { teacher: rec.to_id });
      setNote({ tone: "ok", text: `Moved ${rec.subject} (${rec.section}) from ${rec.from} to ${rec.to}.` });
    } catch (e) {
      setNote({ tone: "error", text: `Could not move it: ${errText(e)} Nothing else was changed; the list below is up to date.` });
    }
    setApplying(null);
    load(true);
  };

  if (error) return <Notice tone="error">{error} <button style={btn} onClick={() => load(false)}>Retry</button></Notice>;
  if (!data) return <p style={{ color: "#6b7280" }}>Loading analytics…</p>;
  const s = data.summary;
  const chart = rows.slice(0, 40).map((t) => ({ label: t.full_name, value: t.hours }));
  const lbl = (n) => (periodOptions.find(([k]) => k === n) || [n, `Period ${n}`])[1];

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 14 }}>
        <h3 style={{ margin: 0, color: "#003366" }}>Analytics — {level === "SHS" ? "Senior High School" : "Junior High School"} teachers</h3>
        <div style={{ flex: 1 }} />
        {data.periods.length > 1 && (
          <select style={inputStyle} value={data.period} onChange={(e) => setPeriod(e.target.value)} aria-label="Term">
            {data.periods.map((n) => <option key={n} value={n}>{lbl(n)}</option>)}
          </select>)}
        <button style={btn} onClick={() => load(false)}>Refresh</button>
        {updated && <span style={{ fontSize: 12, color: "#6b7280" }}>Updated {formatTime(updated)} · refreshes automatically</span>}
      </div>

      {!data.has_schedule ? (
        <Notice tone="info">No {level} timetable exists yet for {lbl(data.period)}. Generate one in the Schedules tab; the teacher analytics appear here right away.</Notice>
      ) : (
        <>
          <p style={{ fontSize: 13, color: "#374151", marginTop: 0 }}>
            Based on the latest {level} timetables for {lbl(data.period)} ({data.runs.map((r) => `Grade ${r.grade_level} v${r.version} ${r.status}`).join(" · ")}).
            Hours are class hours per week; each teacher is measured against their own weekly limit.
            Underloaded = below {data.thresholds.under_pct}% of the limit and clearly under the average; at limit = {data.thresholds.at_limit_pct}% or more.
          </p>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 20 }}>
            <StatTile label="Teachers" value={`${s.with_load}/${s.teachers}`} />
            <StatTile label="Average Load" value={`${fmt(s.average_hours)} h`} />
            <StatTile label="Overloaded" value={s.over} accent={s.over ? "#b91c1c" : undefined} />
            <StatTile label="Underloaded" value={s.under} />
            <StatTile label="Workload std. deviation" value={`${fmt(s.std_dev)} hrs`} />
            <StatTile label="Workload conflicts" value={s.conflicts} accent={s.conflicts ? "#b91c1c" : undefined} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20, marginBottom: 20 }}>
            <div style={{ ...cardStyle, marginBottom: 0 }}>
              <h4 style={{ marginTop: 0, color: "#003366" }}>Teacher Workload</h4>
              <div style={{ maxHeight: 360, overflowY: "auto" }}><HBarChart data={chart} unit=" hrs" emptyText="No teachers match." /></div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <div style={{ ...cardStyle, marginBottom: 0 }}>
                <h4 style={{ marginTop: 0, color: "#003366" }}>Class Hours by Day</h4>
                <HBarChart data={Object.entries(data.hours_by_day).map(([d, n]) => ({ label: DAY_NAME[d] || d, value: n }))} unit=" hrs" emptyText="No classes yet." />
              </div>
              <div style={{ ...cardStyle, marginBottom: 0 }}>
                <h4 style={{ marginTop: 0, color: "#003366" }}>Load Status</h4>
                <HBarChart color="#003366" unit=" teachers" data={Object.entries(STATUS).map(([k, v]) => ({ label: v.label, value: s[k] }))} />
              </div>
            </div>
          </div>

          <div style={cardStyle}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 10 }}>
              <h4 style={{ margin: 0, color: "#003366", flex: 1 }}>Teaching load per teacher</h4>
              <input style={{ ...inputStyle, minWidth: 190 }} placeholder="Search teacher or subject" value={q} onChange={(e) => setQ(e.target.value)} />
              <select style={inputStyle} value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">All loads</option>
                {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </div>
            <div style={{ overflowX: "auto", maxHeight: 520, overflowY: "auto", border: "1px solid #e5e7eb", borderRadius: 6 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 760 }}>
                <thead><tr>
                  <th style={th}>Teacher</th><th style={th}>Subjects</th><th style={{ ...th, textAlign: "right" }}>Sections</th>
                  <th style={{ ...th, textAlign: "right" }}>Class hours</th><th style={th}>Load</th><th style={th}>Status</th><th style={th}></th>
                </tr></thead>
                <tbody>
                  {rows.length === 0 && <tr><td style={{ ...td, color: "#6b7280" }} colSpan={7}>Nothing to show.</td></tr>}
                  {rows.map((t) => (
                    <React.Fragment key={t.faculty_id}>
                      <tr onClick={() => setOpen(open === t.faculty_id ? null : t.faculty_id)} style={{ cursor: "pointer" }}>
                        <td style={{ ...td, fontWeight: 600 }}>{t.full_name}<div style={{ fontSize: 12, color: "#6b7280", fontWeight: 400 }}>{t.employee_id}</div></td>
                        <td style={{ ...td, maxWidth: 300, overflowWrap: "anywhere" }}>
                          {t.subject_count === 0 ? <span style={{ color: "#6b7280" }}>None assigned</span>
                            : <>{t.subjects.slice(0, 3).map((x) => x.code).join(", ")}{t.subject_count > 3 ? ` +${t.subject_count - 3} more` : ""}
                              <div style={{ fontSize: 12, color: "#6b7280" }}>{t.subject_count} subject{t.subject_count === 1 ? "" : "s"} · {t.periods} periods</div></>}
                        </td>
                        <td style={{ ...td, textAlign: "right" }}>{t.sections}</td>
                        <td style={{ ...td, textAlign: "right", fontWeight: 600 }}>{fmt(t.hours)} h</td>
                        <td style={td}><LoadBar value={t.hours} max={t.max_hours} status={t.status} /></td>
                        <td style={td}><Badge tone={STATUS[t.status].tone}>{t.status === "over" ? `Over by ${fmt(t.over_hours)} h` : t.no_load ? "No classes" : STATUS[t.status].label}</Badge></td>
                        <td style={{ ...td, color: "#003366", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>{open === t.faculty_id ? "Hide ▲" : "Details ▼"}</td>
                      </tr>
                      {open === t.faculty_id && <tr><td colSpan={7} style={{ padding: 0, borderBottom: "1px solid #eef2f7" }}><TeacherDetail t={t} /></td></tr>}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={cardStyle}>
            <h4 style={{ marginTop: 0, color: "#003366" }}>Workload conflicts ({data.conflicts.length})</h4>
            {data.conflicts.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#166534" }}>No workload conflicts: every teacher is within their weekly and daily limits, free, available and qualified for their classes.</p>
              : data.conflicts.map((c, i) => (
                <div key={i} style={{ borderLeft: `4px solid ${c.severity === "error" ? "#dc2626" : "#e0a72e"}`, background: c.severity === "error" ? "#fef2f2" : "#fffbeb", borderRadius: 6, padding: "9px 12px", marginBottom: 8, fontSize: 13 }}>
                  <div><Badge tone="warning">{KIND_LABEL[c.kind] || c.kind}</Badge> <span style={{ marginLeft: 6 }}>{c.message}</span></div>
                  <div style={{ color: "#4b5563", marginTop: 4 }}>Suggested adjustment: {c.suggestion}</div>
                </div>))}
          </div>

          <div style={cardStyle}>
            <h4 style={{ marginTop: 0, color: "#003366" }}>Workload balancing recommendations ({data.recommendations.length})</h4>
            <p style={{ marginTop: 0, fontSize: 13, color: "#6b7280" }}>Each suggestion moves one subject in one section to a teacher with the right specialization who is free at all those times, inside their availability and within their weekly and daily limits.</p>
            {note && <Notice tone={note.tone}>{note.text}</Notice>}
            {data.recommendations.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#4b5563" }}>Nothing to rebalance right now.</p>
              : data.recommendations.map((r, i) => (
                <div key={i} style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "10px 12px", marginBottom: 8, fontSize: 13, display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                  <div style={{ flex: "1 1 320px", minWidth: 0 }}>
                    <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{r.subject} · {r.section}</div>
                    <div>{r.from} <span style={{ color: "#6b7280" }}>({fmt(r.from_hours_before)} → {fmt(r.from_hours_after)} h)</span> to <b>{r.to}</b> <span style={{ color: "#6b7280" }}>({fmt(r.to_hours_before)} → {fmt(r.to_hours_after)} h)</span></div>
                    <div style={{ color: "#6b7280", fontSize: 13, marginTop: 2 }}>{r.periods} period{r.periods === 1 ? "" : "s"} · {fmt(r.hours)} h a week. {r.reason}</div>
                  </div>
                  {r.editable
                    ? <button style={btnPrimary} disabled={applying !== null} onClick={() => apply(r, i)}>{applying === i ? "Applying…" : "Apply"}</button>
                    : <span style={{ fontSize: 12, color: "#6b7280" }}>Timetable is {r.run_status}; request a revision to change it.</span>}
                </div>))}
          </div>
        </>
      )}
    </div>
  );
}
