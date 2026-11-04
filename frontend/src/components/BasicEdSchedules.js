import React, { useState, useEffect, useCallback } from "react";
import API from "../services/api";
import Badge from "./Badge";
import RoomSelect from "./RoomSelect";
import { StatTile, HBarChart } from "./Charts";
import { periodInfo } from "../utils/terms";
import { be, errText, inputStyle, cardStyle, btn, btnPrimary, Field, Modal, Notice, DAYS, hhmm, ampm, STATUS_LABEL, STATUS_TONE } from "./basicEdUi";

const toMin = (t) => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
const fromMin = (n) => `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;

/* Recess / lunch of a grade level's window: [["Recess", "10:15", "10:30"], ["Lunch", ...]] in time order (only complete ones). */
export function windowBreaks(win) {
  if (!win) return [];
  const pairs = win.level === "SHS"          // SHS: one 30-minute "Break"; JHS: Recess and Lunch
    ? [["Break", win.break_start, win.break_end]]
    : [["Recess", win.recess_start, win.recess_end], ["Lunch", win.lunch_start, win.lunch_end]];
  return pairs
    .filter(([, a, b]) => a && b && toMin(String(b).slice(0, 5)) > toMin(String(a).slice(0, 5)))
    .map(([l, a, b]) => [l, String(a).slice(0, 5), String(b).slice(0, 5)])
    .sort((x, y) => toMin(x[1]) - toMin(y[1]));
}

/* Same period grid the server builds: back-to-back periods that skip recess and lunch (or, with none set, a break after every `break_every`). */
export function buildGrid(config, win) {
  if (!config || !win) return [];
  const start = toMin(win.start_time), end = toMin(win.end_time), p = config.period_minutes;
  const breaks = windowBreaks(win).map(([l, a, b]) => [l, toMin(a), toMin(b)]);
  const out = []; let cur = start, n = 0;
  while (cur + p <= end) {
    const at = cur;
    const hit = breaks.find((b) => at < b[2] && at + p > b[1]);
    if (hit) { cur = cur >= hit[1] ? Math.max(cur, hit[2]) : hit[2]; continue; }
    out.push([fromMin(cur), fromMin(cur + p)]); cur += p; n += 1;
    if (!breaks.length && config.break_minutes && n % Math.max(config.break_every, 1) === 0) cur += config.break_minutes;
  }
  return out;
}

/* The whole school day for display: class periods plus the recess / lunch rows, in time order. */
export function buildRows(config, win) {
  const rows = buildGrid(config, win).map(([s, e]) => ({ kind: "period", s, e }));
  windowBreaks(win).forEach(([l, s, e]) => rows.push({ kind: l, s, e }));
  return rows.sort((x, y) => toMin(x.s) - toMin(y.s));
}

/* Resolve: fixes the timetable's errors by changing a teacher, room or period; each change is re-validated and kept only if it helps. */
export async function resolveRun(level, id, only = {}) {
  const r = await API.post(`/basic-ed/schedules/${id}/resolve/`, { level, ...only }, { params: { level }, timeout: 180000 });
  return r.data;
}
export function resolveText(d) {
  return `${d.resolved.length} problem${d.resolved.length === 1 ? "" : "s"} fixed${d.unresolved.length ? `, ${d.unresolved.length} could not be fixed automatically (reasons below).` : "."}`;
}

function StatusBadge({ status }) { return <Badge tone={STATUS_TONE[status] || "neutral"}>{STATUS_LABEL[status] || status}</Badge>; }

/* ---------- Generate ---------- */
export function GeneratePanel({ level, overview, periodLabel, onDone }) {
  // Senior High: each grade has its own structure (Grade 11 = 3 terms, Grade 12 = 2 semesters), so one grade at a time.
  const [grade, setGrade] = useState(level === "SHS" ? String(overview.windows[0]?.grade_level || "") : "all");
  const [period, setPeriod] = useState(1);
  const [fixing, setFixing] = useState(null);
  const [fixed, setFixed] = useState({});
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [blockers, setBlockers] = useState(null);
  const [err, setErr] = useState("");
  const info = periodInfo(overview.structure, grade === "all" ? overview.windows[0]?.grade_level : grade);
  const nPeriods = info.count;
  periodLabel = info.label;
  const run = async (force) => {
    setBusy(true); setErr(""); setRes(null); setBlockers(null);
    try {
      const r = await API.post("/basic-ed/schedules/generate/", { level, grading_period: Number(period), grade_level: grade, force: !!force }, { params: { level }, timeout: 180000 });
      setRes(r.data.results); onDone && onDone();
    } catch (e) {
      if (e.response?.data?.issues) setBlockers(e.response.data.issues); else setErr(errText(e));
    } finally { setBusy(false); }
  };
  return (
    <div style={cardStyle}>
      <b>Generate a schedule</b>
      <p style={{ color: "#64748b", fontSize: "13px", margin: "4px 0 12px" }}>
        Builds a weekly timetable for every section using only {level} teachers, rooms and curriculum. The grade-level time window, teacher availability, room type and teaching-load limits are enforced; anything that can't be placed is listed with the reason.
        Generating again keeps the earlier version in the history.
      </p>
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "flex-end" }}>
        <Field label="Grade level"><select style={inputStyle} value={grade} onChange={(e) => { setGrade(e.target.value); setPeriod(1); }}>
          {level !== "SHS" && <option value="all">All grade levels</option>}{overview.windows.map((w) => <option key={w.grade_level} value={w.grade_level}>Grade {w.grade_level} ({ampm(w.start_time)} – {ampm(w.end_time)})</option>)}</select></Field>
        <Field label={periodLabel}><select style={inputStyle} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {Array.from({ length: nPeriods }, (_, i) => <option key={i} value={i + 1}>{periodLabel} {i + 1}</option>)}</select></Field>
        <button style={btnPrimary} disabled={busy} onClick={() => run(false)}>{busy ? "Generating…" : "Generate schedule"}</button>
      </div>
      {busy && <p style={{ color: "#64748b", fontSize: "13px" }}>This can take up to a minute on a slow connection. Please don't click again.</p>}
      {err && <div style={{ marginTop: "12px" }}><Notice tone="error">{err}</Notice></div>}
      {blockers && (
        <div style={{ marginTop: "12px" }}>
          <Notice tone="error"><b>Fix the curriculum first</b> — generation was stopped:
            <ul style={{ margin: "6px 0 0", paddingLeft: "18px" }}>{blockers.slice(0, 15).map((b, i) => <li key={i}>{b.message}</li>)}</ul></Notice>
          <button style={btn} onClick={() => run(true)}>Generate anyway (unsatisfiable items will be reported)</button>
        </div>
      )}
      {res && res.map((r) => (
        <div key={r.run.id} style={{ marginTop: "14px" }}>
          <Notice tone={r.unresolved.length ? "warn" : "ok"}>
            <b>Grade {r.run.grade_level} — version {r.run.version}:</b> {r.run.stats.placed} periods placed, {r.unresolved.length} could not be placed.
            {r.run.validation.errors > r.unresolved.length && ` ${r.run.validation.errors - r.unresolved.length} validation issue(s).`}
          </Notice>
          {r.unresolved.length > 0 && <ul style={{ fontSize: "13px", color: "#7c2d12", margin: 0, paddingLeft: "20px" }}>{r.unresolved.map((u, i) => <li key={i}><b>{u.section} · {u.subject}</b>: {u.message}</li>)}</ul>}
          {r.run.validation.errors > 0 && (
            <div style={{ marginTop: "8px" }}>
              <button style={btnPrimary} disabled={fixing === r.run.id} onClick={async () => {
                setFixing(r.run.id);
                try { const d = await resolveRun(level, r.run.id); setFixed({ ...fixed, [r.run.id]: d }); onDone && onDone(); }
                catch (e) { setFixed({ ...fixed, [r.run.id]: { resolved: [], unresolved: [{ message: errText(e), reason: "" }] } }); }
                finally { setFixing(null); }
              }}>{fixing === r.run.id ? "Resolving…" : "Resolve"}</button>
              <span style={{ fontSize: "12.5px", color: "#64748b", marginLeft: "10px" }}>Tries another teacher, room or period for each problem; nothing is kept unless every rule still holds.</span>
            </div>)}
          {fixed[r.run.id] && (
            <div style={{ marginTop: "8px", fontSize: "12.5px" }}>
              <Notice tone={fixed[r.run.id].unresolved.length ? "warn" : "ok"}>{resolveText(fixed[r.run.id])}</Notice>
              {fixed[r.run.id].resolved.length > 0 && <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>{fixed[r.run.id].resolved.map((t, i) => <li key={i}>{t}</li>)}</ul>}
              {fixed[r.run.id].unresolved.length > 0 && <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>{fixed[r.run.id].unresolved.map((u, i) => <li key={i}>{u.message}<div style={{ color: "#7c2d12" }}>{u.reason}</div></li>)}</ul>}
            </div>)}
        </div>
      ))}
    </div>
  );
}

/* ---------- Runs list ---------- */
export function SchedulesPanel({ level, overview, periodLabel, user }) {
  const [runs, setRuns] = useState([]);
  const [history, setHistory] = useState(false);
  const [openId, setOpenId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setLoading(true);
    be.get(level, "schedules/", history ? { history: 1 } : {}).then((r) => { setRuns(r.data); setError(""); }).catch((e) => setError(errText(e))).finally(() => setLoading(false));
  }, [level, history]);
  useEffect(() => { load(); }, [load]);
  if (openId) return <RunDetail level={level} id={openId} overview={overview} periodLabel={periodLabel} user={user} onBack={() => { setOpenId(null); load(); }} />;
  return (
    <div>
      <GeneratePanel level={level} overview={overview} periodLabel={periodLabel} onDone={load} />
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "10px" }}>
          <b>{history ? "Schedule history (every version)" : "Current schedules"}</b>
          <label style={{ fontSize: "13px" }}><input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Show history</label>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead><tr>{["Grade", periodLabel, "Version", "Status", "Periods", "Open issues", "Created", ""].map((h) => <th key={h} style={{ textAlign: "left", fontSize: "11.5px", textTransform: "uppercase", color: "#64748b", padding: "8px 10px", borderBottom: "1px solid #e2e8f0" }}>{h}</th>)}</tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td style={{ padding: "9px 10px" }}><b>Grade {r.grade_level}</b></td><td style={{ padding: "9px 10px" }}>{r.period_label}</td>
                  <td style={{ padding: "9px 10px" }}>v{r.version}</td><td style={{ padding: "9px 10px" }}><StatusBadge status={r.status} /></td>
                  <td style={{ padding: "9px 10px" }}>{r.entry_count}</td>
                  <td style={{ padding: "9px 10px" }}>{r.validation?.errors ? <Badge tone="warning">{r.validation.errors}</Badge> : <Badge tone="success">0</Badge>}</td>
                  <td style={{ padding: "9px 10px" }}>{new Date(r.created_at).toLocaleString()}<div style={{ fontSize: "11px", color: "#64748b" }}>{r.created_by_name}</div></td>
                  <td style={{ padding: "9px 10px" }}><button style={btn} onClick={() => setOpenId(r.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && runs.length === 0 && <p style={{ color: "#64748b", fontSize: "13px", padding: "10px" }}>No schedules yet. Generate one above.</p>}
        </div>
      </div>
    </div>
  );
}

/* ---------- Run detail ---------- */
function RunDetail({ level, id, overview, periodLabel, onBack, user }) {
  const [data, setData] = useState(null);
  const [sectionId, setSectionId] = useState("");
  const [tab, setTab] = useState("timetable");
  const [report, setReport] = useState(null);
  const [faculty, setFaculty] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [editing, setEditing] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fix, setFix] = useState(null);                 // result of the last Resolve

  const load = useCallback(() => {
    be.get(level, `schedules/${id}/`).then((r) => {
      setData(r.data);
      setSectionId((cur) => cur || String(r.data.entries[0]?.section || ""));
    }).catch((e) => setMsg({ tone: "error", text: errText(e) }));
  }, [level, id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    be.get(level, "faculty/").then((r) => setFaculty(r.data)).catch(() => {});
    be.get(level, "rooms/").then((r) => setRooms(r.data)).catch(() => {});
  }, [level]);
  useEffect(() => { if (tab === "report" && !report) be.get(level, `schedules/${id}/report/`).then((r) => setReport(r.data)).catch(() => {}); }, [tab, report, level, id]);

  const doResolve = async (only) => {
    setBusy(true); setMsg(null);
    try { const d = await resolveRun(level, id, only); setFix(d); setMsg({ tone: d.unresolved.length ? "warn" : "ok", text: resolveText(d) }); load(); }
    catch (e) { setMsg({ tone: "error", text: errText(e) }); } finally { setBusy(false); }
  };

  if (!data) return <div style={cardStyle}>{msg ? <Notice tone="error">{msg.text}</Notice> : "Loading…"}<button style={btn} onClick={onBack}>Back</button></div>;
  const run = data.run;
  const win = overview.windows.find((w) => w.grade_level === run.grade_level);
  const grid = buildGrid(overview.config, win);
  const rows = buildRows(overview.config, win);
  const editable = ["draft", "revision_requested"].includes(run.status);
  const sections = [...new Map(data.entries.map((e) => [e.section, e.section_name])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const cell = (day, start) => data.entries.find((e) => String(e.section) === String(sectionId) && e.day === day && hhmm(e.start_time) === start);
  const errors = data.conflicts.filter((c) => c.severity === "error");
  const warnings = data.conflicts.filter((c) => c.severity === "warning");

  const act = async (action) => {
    let comment = "";
    if (action === "request-revision") { comment = window.prompt("What should be revised?") || ""; if (!comment.trim()) return; }
    setBusy(true); setMsg(null);
    try { await be.post(level, `schedules/${id}/${action}/`, { comment }); load(); setMsg({ tone: "ok", text: "Done." }); }
    catch (e) { setMsg({ tone: "error", text: errText(e) }); } finally { setBusy(false); }
  };
  const revalidate = async () => { setBusy(true); try { await be.post(level, `schedules/${id}/validate/`); load(); } finally { setBusy(false); } };
  const pdf = async () => {
    try {
      const r = await API.get(`/basic-ed/schedules/${id}/pdf/`, { params: { level }, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: "application/pdf" })); window.open(url, "_blank"); setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (e) { setMsg({ tone: "error", text: "Could not create the PDF." }); }
  };
  const canDecide = user.role === "principal" || user.role === "admin";
  return (
    <div>
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
          <div>
            <button style={btn} onClick={onBack}>All schedules</button>{" "}
            <b style={{ fontSize: "16px" }}>Grade {run.grade_level} · {run.period_label} · v{run.version}</b>{" "}<StatusBadge status={run.status} />
            <div style={{ fontSize: "12.5px", color: "#64748b", marginTop: "4px" }}>{win && `${ampm(win.start_time)} – ${ampm(win.end_time)} · ${overview.config.building}${overview.config.floor != null ? ", floor " + overview.config.floor : ""}`}</div>
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {editable && <button style={btn} disabled={busy} onClick={revalidate}>Re-validate</button>}
            {editable && <button style={btnPrimary} disabled={busy || errors.length > 0} title={errors.length ? "Resolve the conflicts first" : ""} onClick={() => act("submit")}>Submit for approval</button>}
            {run.status === "submitted" && canDecide && <button style={btnPrimary} disabled={busy} onClick={() => act("approve")}>Approve</button>}
            {["submitted", "approved"].includes(run.status) && canDecide && <button style={btn} disabled={busy} onClick={() => act("request-revision")}>Request revision</button>}
            {run.status === "approved" && <button style={btnPrimary} disabled={busy} onClick={() => act("publish")}>Publish to teachers</button>}
            <button style={btn} onClick={pdf}>🖨 Print / PDF</button>
          </div>
        </div>
        {msg && <div style={{ marginTop: "10px" }}><Notice tone={msg.tone}>{msg.text}</Notice></div>}
        {run.status === "superseded" && <div style={{ marginTop: "10px" }}><Notice tone="warn">This is an older version kept for the history. It can't be edited.</Notice></div>}
        {data.events.find((e) => e.action === "request_revision") && run.status === "revision_requested" && (
          <div style={{ marginTop: "10px" }}><Notice tone="warn"><b>Revision requested:</b> {[...data.events].reverse().find((e) => e.action === "request_revision")?.comment}</Notice></div>
        )}
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "12px" }}>
          <StatTile label="Periods" value={data.entries.length} /><StatTile label="Conflicts" value={errors.length} accent={errors.length ? "#b91c1c" : "#15803d"} /><StatTile label="Warnings" value={warnings.length} accent="#b45309" />
        </div>
      </div>

      <div style={{ display: "flex", gap: "6px", marginBottom: "12px" }}>
        {[["timetable", "Timetable"], ["conflicts", `Conflicts (${data.conflicts.length})`], ["report", "Report"], ["history", "Approval history"]].map(([k, l]) => (
          <button key={k} style={tab === k ? btnPrimary : btn} onClick={() => setTab(k)}>{l}</button>))}
      </div>

      {tab === "timetable" && (
        <div style={cardStyle}>
          <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "12px", flexWrap: "wrap" }}>
            <select style={inputStyle} value={sectionId} onChange={(e) => setSectionId(e.target.value)}>{sections.map(([sid, name]) => <option key={sid} value={sid}>{name}</option>)}</select>
            {editable ? <span style={{ fontSize: "12.5px", color: "#64748b" }}>Click a period to change its teacher, room or time. Every change is re-validated automatically.</span>
              : <span style={{ fontSize: "12.5px", color: "#64748b" }}>Read-only ({STATUS_LABEL[run.status].toLowerCase()}). Request a revision to edit.</span>}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "760px" }}>
              <thead><tr><th style={{ width: "92px", padding: "8px", background: "#003366", color: "white", fontSize: "12px" }}>Time</th>{DAYS.map((d) => <th key={d[0]} style={{ padding: "8px", background: "#003366", color: "white", fontSize: "12px" }}>{d[1]}</th>)}</tr></thead>
              <tbody>
                {rows.map((r) => r.kind !== "period" ? (
                  <tr key={`break-${r.s}`}>
                    <td style={{ padding: "6px", fontSize: "11.5px", background: "#fde68a", textAlign: "center", border: "1px solid #e2e8f0" }}>{ampm(r.s)}<br />{ampm(r.e)}</td>
                    <td colSpan={DAYS.length} style={{ padding: "6px", background: "#fef3c7", textAlign: "center", fontWeight: 700, letterSpacing: "4px", color: "#92400e", border: "1px solid #e2e8f0", fontSize: "12.5px" }}>
                      {r.kind.toUpperCase()}</td>
                  </tr>
                ) : (([s, e]) => (
                  <tr key={s}>
                    <td style={{ padding: "6px", fontSize: "11.5px", background: "#f1f5f9", textAlign: "center", border: "1px solid #e2e8f0" }}>{ampm(s)}<br />{ampm(e)}</td>
                    {DAYS.map(([d]) => {
                      const c = cell(d, s);
                      const bad = c && data.conflicts.some((x) => x.severity === "error" && String(x.section) === String(c.section) && x.subject_code === c.subject_code);
                      return (
                        <td key={d} onClick={() => editable && c && setEditing(c)} style={{ border: "1px solid #e2e8f0", padding: "5px 6px", fontSize: "11.5px", verticalAlign: "top", cursor: editable && c ? "pointer" : "default", background: bad ? "#fee2e2" : c ? (c.learning_area ? "#f0f7ff" : "white") : "#fafafa", minWidth: "120px" }}>
                          {c && (<><b>{c.subject_code}</b><div style={{ color: "#334155" }}>{c.subject_name.length > 34 ? c.subject_name.slice(0, 34) + "…" : c.subject_name}</div>
                            <div style={{ color: "#64748b" }}>{c.teacher_name || "— no teacher —"}</div><div style={{ color: "#64748b" }}>{c.room_name || "— no room —"}</div></>)}
                        </td>
                      );
                    })}
                  </tr>
                ))([r.s, r.e]))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "conflicts" && (
        <div style={cardStyle}>
          {data.conflicts.length === 0 ? <Notice tone="ok">No conflicts. Every hard rule is satisfied: time window, breaks, teacher/room/section overlaps, availability, qualification, room type, load and required periods.</Notice> : (
            <>
              {editable && (
                <div style={{ marginBottom: "10px" }}>
                  <button style={btnPrimary} disabled={busy} onClick={() => doResolve()}>{busy ? "Resolving…" : "Resolve all"}</button>
                  <span style={{ fontSize: "12.5px", color: "#64748b", marginLeft: "10px" }}>Changes a teacher, room or period; a change is kept only if every rule still holds and nothing new breaks.</span>
                </div>)}
              <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "13px", lineHeight: 1.9 }}>
                {data.conflicts.map((c) => <li key={c.id}>{c.severity === "error" ? "⛔" : "⚠️"} {c.section_name && <b>{c.section_name}: </b>}{c.message}
                  {editable && c.severity === "error" && <>{" "}<button style={{ ...btn, padding: "2px 10px", fontSize: "12px" }} disabled={busy}
                    onClick={() => doResolve({ kind: c.kind, section: c.section || undefined, subject_code: c.subject_code || undefined })}>Resolve</button></>}</li>)}
              </ul>
            </>
          )}
          {fix && (fix.resolved.length > 0 || fix.unresolved.length > 0) && (
            <div style={{ marginTop: "12px", fontSize: "12.5px" }}>
              {fix.resolved.length > 0 && <><b>Fixed</b><ul style={{ margin: "4px 0 8px", paddingLeft: "20px" }}>{fix.resolved.map((t, i) => <li key={i}>{t}</li>)}</ul></>}
              {fix.unresolved.length > 0 && <><b>Not fixed — what to do</b><ul style={{ margin: "4px 0", paddingLeft: "20px" }}>{fix.unresolved.map((u, i) => <li key={i}>{u.message}<div style={{ color: "#7c2d12" }}>{u.reason}</div></li>)}</ul></>}
            </div>)}
        </div>
      )}

      {tab === "report" && (
        <div style={cardStyle}>
          {!report ? "Loading report…" : (
            <>
              <h4 style={{ marginTop: 0 }}>Teacher workload (hours per week)</h4>
              <HBarChart data={report.teachers.map((t) => ({ label: `${t.name} (${t.load_pct}%)`, value: t.hours }))} unit=" h" />
              <h4>Room utilization</h4>
              <HBarChart data={report.rooms.map((r) => ({ label: `${r.name} (${r.utilization_pct}%)`, value: r.hours }))} unit=" h" color="#0f766e" />
              <h4>Calendar (class days after holidays, examination blocks and suspensions)</h4>
              {report.calendar.length === 0 ? <p style={{ color: "#64748b", fontSize: "13px" }}>Link this {periodLabel.toLowerCase()} to its terms in the Calendar tab.</p> : (
                <table style={{ fontSize: "13px", borderCollapse: "collapse" }}><tbody>
                  {report.calendar.map((c) => <tr key={c.term}><td style={{ padding: "4px 12px 4px 0" }}><b>{c.term}</b></td><td style={{ padding: "4px 12px" }}>{c.start} → {c.end}</td><td style={{ padding: "4px 12px" }}>{c.class_days} class days</td><td style={{ padding: "4px 12px", color: "#64748b" }}>{c.excluded_dates.length} date(s) with no regular classes</td></tr>)}
                </tbody></table>
              )}
            </>
          )}
        </div>
      )}

      {tab === "history" && (
        <div style={cardStyle}>
          <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "13px", lineHeight: 1.8 }}>
            {data.events.map((e) => <li key={e.id}><b>{e.action.replace(/_/g, " ")}</b> — {e.actor_name || "system"} · {new Date(e.created_at).toLocaleString()}{e.comment ? ` — ${e.comment}` : ""}</li>)}
          </ul>
        </div>
      )}

      {editing && <EntryEditModal level={level} entry={editing} grid={grid} faculty={faculty} rooms={rooms} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </div>
  );
}

function EntryEditModal({ level, entry, grid, faculty, rooms, onClose, onSaved }) {
  const [f, setF] = useState({ day: entry.day, start: hhmm(entry.start_time), teacher: entry.teacher || "", room: entry.room || "" });
  const [err, setErr] = useState("");
  const [issues, setIssues] = useState([]);
  const [saving, setSaving] = useState(false);
  const period = grid.find((g) => g[0] === f.start) || [f.start, hhmm(entry.end_time)];
  const save = async () => {
    setSaving(true); setErr("");
    try {
      const r = await be.patch(level, `entries/${entry.id}/`, { day: f.day, start_time: period[0], end_time: period[1], teacher: f.teacher || null, room: f.room || null });
      if (r.data.entry_issues?.length) { setIssues(r.data.entry_issues); } else onSaved();
    } catch (e) { setErr(errText(e)); } finally { setSaving(false); }
  };
  const remove = async () => {
    if (!window.confirm("Remove this period from the timetable?")) return;
    try { await be.del(level, `entries/${entry.id}/`); onSaved(); } catch (e) { setErr(errText(e)); }
  };
  const eligibleRooms = rooms.filter((r) => r.is_active);
  return (
    <Modal title={`${entry.subject_code} — ${entry.section_name}`} onClose={onClose}>
      <p style={{ marginTop: 0, fontSize: "13px", color: "#334155" }}>{entry.subject_name}</p>
      {err && <Notice tone="error">{err}</Notice>}
      {issues.length > 0 && <Notice tone="error"><b>Saved, but this change creates conflicts:</b><ul style={{ margin: "6px 0 0", paddingLeft: "18px" }}>{issues.map((i, k) => <li key={k}>{i.message}</li>)}</ul>
        <button style={{ ...btn, marginTop: "8px" }} onClick={onSaved}>Keep and review</button></Notice>}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        <Field label="Day"><select style={{ ...inputStyle, width: "100%" }} value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })}>{DAYS.map((d) => <option key={d[0]} value={d[0]}>{d[1]}</option>)}</select></Field>
        <Field label="Period"><select style={{ ...inputStyle, width: "100%" }} value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })}>{grid.map((g) => <option key={g[0]} value={g[0]}>{ampm(g[0])} – {ampm(g[1])}</option>)}</select></Field>
        <Field label="Teacher"><select style={{ ...inputStyle, width: "100%" }} value={f.teacher} onChange={(e) => setF({ ...f, teacher: e.target.value })}><option value="">—</option>{faculty.filter((t) => t.is_active).map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></Field>
        <Field label="Room"><RoomSelect rooms={eligibleRooms} value={f.room} onChange={(v) => setF({ ...f, room: v })} autoLabel="—" width="100%" style={{ padding: "8px 10px" }}
          groupBy={(r) => String(r.room_type || "").replace("_", " ")} /></Field>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: "18px" }}>
        <button style={btn} onClick={remove}>Remove period</button>
        <div style={{ display: "flex", gap: "8px" }}><button style={btn} onClick={onClose}>Cancel</button><button style={btnPrimary} disabled={saving} onClick={save}>{saving ? "Checking…" : "Save & validate"}</button></div>
      </div>
    </Modal>
  );
}
