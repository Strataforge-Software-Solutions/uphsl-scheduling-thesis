import CustomSelect from "./CustomSelect";
import CustomDatePicker from "./CustomDatePicker";
import CustomTimePicker from "./CustomTimePicker";
import HowToUse from "./HowToUse";
import { PrincipalHome } from "./HomeWrappers";
import React, { useState, useEffect, useCallback } from "react";
import { getCurrentUser, logout, displayName } from "../services/api";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import { StatTile } from "./Charts";
import { be, errText, inputStyle, cardStyle, btn, btnPrimary, Field, Notice, Modal, ampm, hhmm, STATUS_LABEL, STATUS_TONE } from "./basicEdUi";
import { SectionsTab, RoomsTab, FacultyTab, CurriculumTab } from "./BasicEdData";
import TeachingAssignmentsPanel from "./BasicEdAssignments";
import AuditLogs from "./AuditLogs";
import { FacultyAvailability } from "./BasicEdAvailability";
import { SchedulesPanel } from "./BasicEdSchedules";
import BasicEdAnalytics from "./BasicEdAnalytics";
import { BasicEdInsights } from "./InsightCards";
import { Accounts } from "./AdminDashboard";
import API, { onSchedulesChanged } from "../services/api";
import { periodHeading } from "../utils/terms";
import "./DashboardTheme.css";
import { useLandingTab } from "../services/preferences";
import { formatDateTime } from "../utils/formatDateTime";
import { useConfirmDialog } from "./ConfirmDialog";

const NAV = [
  { key: "overview", label: "Home", icon: "" },
  { group: "Plan" },
  { key: "schedules", label: "Schedules", icon: "" },
  { key: "calendar", label: "Calendar", icon: "" },
  { group: "Academics" },
  { key: "sections", label: "Sections", icon: "" },
  { key: "curriculum", label: "Curriculum", icon: "" },
  { group: "People" },
  { key: "faculty", label: "Faculty", icon: "" },
  { group: "Insights" },
  { key: "analytics", label: "Analytics", icon: "" },
  { group: "Management" },
  { key: "settings", label: "Settings", icon: "" },
];

/* IT admin workspace for one school level: accounts, data management and analytics. Scheduling itself (generate, review, approve) is the
   Principal's job, so there is no Schedules tab here. */
const NAV_ADMIN = [
  { group: "Insights" },
  { key: "overview", label: "Overview", icon: "" },
  { key: "activity", label: "Activity", icon: "" },
  { key: "audit", label: "Audit logs", icon: "" },
  { group: "People" },
  { key: "accounts", label: "Accounts", icon: "" },
  { key: "faculty", label: "Faculty", icon: "" },
  { group: "Management" },
  { key: "sections", label: "Sections", icon: "" },
  { key: "curriculum", label: "Curriculum", icon: "" },
  { key: "rooms", label: "Rooms", icon: "" },
  { key: "calendar", label: "Calendar", icon: "" },
  { key: "settings", label: "Settings", icon: "" },
  { group: "Data" },
  { key: "data", label: "Data Tools", icon: "" },
];

const LEVEL_NAME = { SHS: "Senior High School", JHS: "Junior High School" };

function BasicEdDashboard({ level }) {
  const user = getCurrentUser();
  const landing = useLandingTab(user?.role === "admin" ? NAV_ADMIN : NAV, "overview");
  const [tab, setTab] = useState(landing);
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    if (overview || error) return undefined;
    const t = setTimeout(() => setSlow(true), 8000);
    return () => clearTimeout(t);
  }, [overview, error, level]);
  const reload = useCallback(() => {
    be.get(level, "overview/").then((r) => { setOverview(r.data); setError(""); }).catch((e) => setError(errText(e, "Could not load the dashboard.")));
  }, [level]);
  useEffect(() => { setOverview(null); setTab("overview"); }, [level]);
  // Refresh overview data only while it is visible; reopening Home and schedule changes always trigger a fresh read.
  useEffect(() => {
    if (tab !== "overview") return undefined;
    const off = onSchedulesChanged(reload), vis = () => { if (document.visibilityState === "visible") reload(); };
    document.addEventListener("visibilitychange", vis); window.addEventListener("focus", reload);
    const t = setInterval(() => { if (document.visibilityState === "visible") reload(); }, 120000);
    return () => { off(); document.removeEventListener("visibilitychange", vis); window.removeEventListener("focus", reload); clearInterval(t); };
  }, [reload, tab]);
  useEffect(() => { if (tab === "overview") reload(); }, [tab, reload]);

  const periodLabel = periodHeading(overview?.structure);
  const titles = {
    overview: ["Home", `${LEVEL_NAME[level]} scheduling at a glance.`],
    schedules: ["Schedules", "Generate, review, approve and publish the timetable."],
    analytics: ["Analytics", `Teacher workload, balance and conflicts for ${LEVEL_NAME[level]}.`],
    sections: ["Sections", level === "SHS" ? "Grade 11 and 12 sections by strand." : "Grades 7–10 sections."],
    curriculum: ["Curriculum", "Subjects, learning hours and their official sources for A.Y. " + (overview?.academic_year || "")],
    faculty: ["Faculty", "Teachers, qualifications, availability and teaching loads."],
    rooms: ["Rooms", `${overview?.config.building || ""}${overview?.config.floor != null ? " — floor " + overview.config.floor : ""}`],
    calendar: ["Calendar", (level === "SHS" ? "Terms, Grade 12 semesters, holidays and examination periods." : "Terms, holidays and examination periods.")],
    settings: ["Settings", "Building, period length, teaching limits and daily time windows."],
  };
  const isAdmin = user?.role === "admin";
  if (isAdmin) {
    titles.overview = ["System Overview", `${LEVEL_NAME[level]}: what is set up, what is missing, and how the timetables are doing.`];
    titles.activity = ["Recent Activity", `Latest approvals, revisions and changes to ${level} timetables.`];
    titles.audit = ["Audit Logs", `Who changed what in ${LEVEL_NAME[level]}, when, the values before and after, and from which IP address. Read only.`];
    titles.accounts = ["Accounts", `Principal and teacher accounts of ${LEVEL_NAME[level]}: reset passwords, disable or enable accounts.`];
    titles.data = ["Data Tools", `Clear generated ${level} timetables so they can be generated again.`];
    titles.faculty = ["Faculty", `${LEVEL_NAME[level]} teachers, qualifications, availability and teaching loads.`];
  }
  const [title, subtitle] = titles[tab];
  const handleLogout = () => { logout(); window.location.href = "/login"; };

  return (
    <div className="app-shell">
      <Sidebar brandLabel="U-FAST" workspaceLabel={isAdmin ? `IT Admin · ${level}` : `${level} · ${overview?.config.building || LEVEL_NAME[level]}`}
        items={isAdmin ? NAV_ADMIN : NAV} activeKey={tab} onSelect={setTab}
        userName={(isAdmin ? user?.username : displayName(user)) || "User"} userRole={isAdmin ? "IT administrator" : `${level} Principal`} onSignOut={handleLogout} />
      <div className="app-main">
        <TopBar crumb={title} userName={isAdmin ? user?.username : displayName(user)} />
        <PageHeader eyebrow={isAdmin ? `IT ADMIN WORKSPACE · ${level}` : `${LEVEL_NAME[level]} Workspace`} title={title} subtitle={subtitle} />
        <div className="app-page-body">
          {error && <Notice tone="error">{error} <button style={btn} onClick={reload}>Retry</button></Notice>}
          {!overview && !error && <p style={{ color: "#6b7280" }}>Loading…{slow && <> Still waiting for the server: slow connection or database, or the latest <code>python manage.py migrate</code> has not been run. <button style={btn} onClick={reload}>Retry</button></>}</p>}
          {overview && isAdmin && tab === "overview" && <AdminOverview level={level} overview={overview} go={setTab} />}
          {overview && isAdmin && tab === "activity" && <AdminActivity overview={overview} />}
          {isAdmin && tab === "audit" && <AuditLogs key={level} level={level} />}
          {isAdmin && tab === "accounts" && <Accounts level={level} />}
          {overview && isAdmin && tab === "data" && <AdminData level={level} overview={overview} />}
          {overview && !isAdmin && tab === "overview" && (
            <PrincipalHome level={level} levelName={LEVEL_NAME[level]} overview={overview} nav={NAV} onNavigate={setTab} name={displayName(user)}
              extra={<Overview level={level} overview={overview} go={setTab} hideStats />} />)}
          {overview && !isAdmin && tab !== "overview" && <HowToUse role="principal" tab={tab} />}
          {overview && !isAdmin && tab === "schedules" && <SchedulesPanel level={level} overview={overview} periodLabel={periodLabel} user={user} />}
          {overview && !isAdmin && tab === "analytics" && (
            <>
              <BasicEdAnalytics level={level} overview={overview} />
              <BasicEdInsights level={level} />
            </>
          )}
          {overview && tab === "sections" && <><SectionsTab level={level} windows={overview.windows} /><TeachingAssignmentsPanel level={level} /></>}
          {overview && tab === "curriculum" && <CurriculumTab level={level} windows={overview.windows} structure={overview.structure} periodLabel={periodLabel} />}
          {overview && tab === "faculty" && <><FacultyTab level={level} /><FacultyAvailability level={level} /></>}
          {overview && tab === "rooms" && <RoomsTab level={level} config={overview.config} />}
          {overview && tab === "calendar" && <CalendarTab level={level} overview={overview} periodLabel={periodLabel} reload={reload} />}
          {overview && tab === "settings" && <SettingsTab level={level} overview={overview} reload={reload} />}
          {overview && !isAdmin && tab === "settings" && (
            <details style={{ ...cardStyle, marginTop: 18 }}>
              <summary style={{ cursor: "pointer", fontWeight: 600, color: "#003366" }}>Rooms — room records used when scheduling</summary>
              <p style={{ fontSize: 13, color: "#6b7280" }}>Add, edit or retire rooms here. Generated timetables and the room dropdown when editing a period use these records.</p>
              <RoomsTab level={level} config={overview.config} />
            </details>)}
        </div>
      </div>
    </div>
  );
}

const adminCard = { background: "white", borderRadius: 6, padding: "18px 22px", marginBottom: "20px", border: "1px solid #e5e7eb", boxShadow: "none" };

function AdminOverview({ level, overview, go }) {
  const c = overview.counts;
  const runs = overview.runs || [];
  const byStatus = runs.reduce((a, r) => { a[r.status] = (a[r.status] || 0) + 1; return a; }, {});
  const noBreaks = overview.windows.filter((w) => (level === "SHS" ? !(w.break_start && w.break_end) : !(w.recess_start && w.recess_end && w.lunch_start && w.lunch_end)));
  const checks = [
    c.sections ? ["ok", `${c.sections} section(s) set up.`] : ["error", "No sections yet (Sections tab)."],
    c.faculty ? ["ok", `${c.faculty} active teacher(s).`] : ["error", "No teachers yet (Faculty tab)."],
    c.rooms ? ["ok", `${c.rooms} room(s) in ${overview.config.building}.`] : ["error", "No rooms yet (Rooms tab)."],
    c.subjects ? ["ok", `${c.subjects} curriculum subject(s).`] : ["error", "No curriculum yet (Curriculum tab)."],
    c.unverified_subjects ? ["warn", `${c.unverified_subjects} subject(s) are not verified against an official DepEd document.`] : ["ok", "Every curriculum subject is verified."],
    noBreaks.length ? ["error", `${level === "SHS" ? "The 30-minute break" : "Recess/lunch"} is missing for Grade ${noBreaks.map((w) => w.grade_level).join(", ")} (Settings tab). Timetables cannot be generated without them.`]
      : ["ok", level === "SHS" ? "The 30-minute break is set for every grade level." : "Recess and lunch are set for every grade level."],
    runs.length ? ["ok", `${runs.length} timetable(s) generated; ${c.pending_review} waiting for the Principal's review.`] : ["warn", "No timetable generated yet. The Principal generates it in the Schedules tab of the principal workspace."],
    c.open_conflicts ? ["warn", `${c.open_conflicts} open conflict(s) in the current timetables. The Principal can press Resolve in the Conflicts tab.`] : ["ok", "No open conflicts."],
  ];
  const col = { ok: "#166534", warn: "#92400e", error: "#b91c1c" }, ico = { ok: "OK:", warn: "Warning:", error: "Error:" };
  return (
    <div>
      <div style={adminCard}>
        <h3 style={{ marginTop: 0, color: "#003366" }}>Setup health</h3>
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {checks.map(([k, t], i) => <li key={i} style={{ padding: "5px 0", color: col[k], fontSize: "14px" }}><strong style={{ fontWeight: 600 }}>{ico[k]}</strong> {t}</li>)}
        </ul>
      </div>
      <div style={adminCard}>
        <h3 style={{ marginTop: 0, color: "#003366" }}>Analytics</h3>
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "14px" }}>
          <StatTile label="Sections" value={c.sections} /><StatTile label="Teachers" value={c.faculty} /><StatTile label="Rooms" value={c.rooms} />
          <StatTile label="Subjects" value={c.subjects} /><StatTile label="Timetables" value={c.runs} />
          <StatTile label="Open conflicts" value={c.open_conflicts} accent={c.open_conflicts ? "#b45309" : "#003366"} />
        </div>
        {runs.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead><tr>{["Grade", "Period", "Version", "Status", "Periods placed", "Unplaced", "Open issues"].map((h) => <th key={h} style={{ textAlign: "left", fontSize: "12px", color: "#6b7280", padding: "8px 10px", borderBottom: "1px solid #e5e7eb" }}>{h}</th>)}</tr></thead>
              <tbody>{runs.map((r) => (
                <tr key={r.id}>
                  <td style={{ padding: "8px 10px" }}><b>Grade {r.grade_level}</b></td><td style={{ padding: "8px 10px" }}>{r.period_label}</td><td style={{ padding: "8px 10px" }}>v{r.version}</td>
                  <td style={{ padding: "8px 10px" }}><Badge tone={STATUS_TONE[r.status] || "neutral"}>{STATUS_LABEL[r.status] || r.status}</Badge></td>
                  <td style={{ padding: "8px 10px" }}>{r.stats?.placed ?? "—"}</td><td style={{ padding: "8px 10px" }}>{r.stats?.unresolved ?? "—"}</td>
                  <td style={{ padding: "8px 10px" }}>{r.validation?.errors ?? "—"}</td>
                </tr>))}</tbody>
            </table>
          </div>)}
        <p style={{ fontSize: "13px", color: "#6b7280", marginBottom: 0 }}>Status: {Object.keys(byStatus).length ? Object.entries(byStatus).map(([k, v]) => `${STATUS_LABEL[k] || k}: ${v}`).join(" · ") : "nothing generated yet"}.
          Generating, reviewing and approving timetables is done by the {level} Principal.</p>
      </div>
    </div>
  );
}

function AdminActivity({ overview }) {
  const rows = overview.recent || [];
  return (
    <div style={adminCard}>
      <h3 style={{ marginTop: 0, color: "#003366" }}>Recent Activity</h3>
      {rows.length === 0 ? <p>Nothing has been recorded yet.</p> : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead><tr>{["When", "Who", "Action", "Details"].map((h) => <th key={h} style={{ textAlign: "left", fontSize: "12px", color: "#6b7280", padding: "8px 10px", borderBottom: "1px solid #e5e7eb" }}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((e, i) => (
              <tr key={i}><td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>{formatDateTime(e.created_at)}</td>
                <td style={{ padding: "8px 10px" }}>{e.actor_name || e.actor || "—"}</td><td style={{ padding: "8px 10px" }}>{e.action}</td>
                <td style={{ padding: "8px 10px", wordBreak: "break-word" }}>{e.comment || ""}</td></tr>))}</tbody>
          </table>
        </div>)}
    </div>
  );
}

function AdminData({ level, overview }) {
  const confirmDialog = useConfirmDialog();
  const [f, setF] = useState({ grade_level: "", include_approved: false });
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => { setF({ ...f, [k]: v }); setPreview(null); setMsg(null); };
  const run = async (apply) => {
    setBusy(true); setMsg(null);
    try {
      const r = await API.post("/basic-ed/clear-generated/", { level, ...f, apply }, { params: { level } });
      if (apply) { setMsg({ tone: "ok", text: `Removed ${r.data.runs} timetable(s) (${r.data.entries} periods). Generate them again in the Principal workspace.` }); setPreview(null); }
      else setPreview(r.data);
    } catch (e) { setMsg({ tone: "error", text: errText(e) }); } finally { setBusy(false); }
  };
  return (
    <div style={adminCard}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "14px", alignItems: "center" }}>
        <CustomSelect style={inputStyle} value={f.grade_level} onChange={(e) => set("grade_level", e.target.value)}>
          <option value="">All grade levels</option>
          {overview.windows.map((w) => <option key={w.grade_level} value={w.grade_level}>Grade {w.grade_level}</option>)}
        </CustomSelect>
        <label style={{ fontSize: "13px" }}><input type="checkbox" checked={f.include_approved} onChange={(e) => set("include_approved", e.target.checked)} /> include approved / published</label>
        <button style={btn} disabled={busy} onClick={() => run(false)}>Preview what would be deleted</button>
      </div>
      {preview && (
        <div style={{ padding: "12px", background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 6 }}>
          <p style={{ margin: "0 0 8px" }}><b>{preview.runs}</b> timetable(s) with <b>{preview.entries}</b> period(s) would be deleted{preview.kept_approved ? ` (${preview.kept_approved} approved/published timetable(s) are kept)` : ""}.</p>
          {preview.runs > 0 && <button style={{ ...btn, background: "#b91c1c", color: "white" }} disabled={busy} onClick={async () => { if (await confirmDialog({ title: "Delete timetables?", message: `Delete ${preview.runs} timetable(s)? This cannot be undone.`, confirmLabel: "Delete timetables" })) run(true); }}>Yes, delete them</button>}
        </div>)}
      {msg && <div style={{ marginTop: "10px" }}><Notice tone={msg.tone}>{msg.text}</Notice></div>}
      <p style={{ fontSize: "13px", color: "#6b7280", marginTop: "14px" }}>Curriculum, sections, rooms and teachers are never touched. Use this after changing recess/lunch or the period length, so every grade is generated again on the same periods.</p>
    </div>
  );
}

function Overview({ level, overview, go, hideStats = false }) {
  const c = overview.counts;
  const pending = overview.runs.filter((r) => r.status === "submitted");
  return (
    <div>
      {!hideStats && <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "18px" }}>
        <StatTile label="Sections" value={c.sections} /><StatTile label="Teachers" value={c.faculty} /><StatTile label="Rooms" value={c.rooms} />
        <StatTile label="Curriculum lines" value={c.subjects} /><StatTile label="Awaiting approval" value={c.pending_review} accent={c.pending_review ? "#b45309" : "#15803d"} />
        <StatTile label="Open conflicts" value={c.open_conflicts} accent={c.open_conflicts ? "#b91c1c" : "#15803d"} />
      </div>}
      {c.unverified_subjects > 0 && <Notice tone="warn"><b>{c.unverified_subjects} curriculum line(s) are unverified.</b> DepEd doesn't publish some of them in checkable form (elective names, Grade 12, some Grade 7–10 details). Review them in <button style={btn} onClick={() => go("curriculum")}>Curriculum</button>.</Notice>}
      {level === "SHS" && overview.periods.some((p) => p.kind === "semester" && p.is_placeholder) && <Notice tone="warn"><b>The Grade 12 term ↔ semester mapping is a placeholder.</b> DepEd's calendar order doesn't say how the 3 terms relate to the 2 semesters. Confirm it in <button style={btn} onClick={() => go("calendar")}>Calendar</button>.</Notice>}
      <div style={cardStyle}>
        <b>Principal review</b>
        {pending.length === 0 ? <p style={{ color: "#6b7280", fontSize: "13px" }}>Nothing is waiting for approval.</p> : pending.map((r) => (
          <div key={r.id} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f3f4f6" }}>
            <span>Grade {r.grade_level} · {r.period_label} · v{r.version} — {r.entry_count} periods</span>
            <button style={btnPrimary} onClick={() => go("schedules")}>Review</button>
          </div>))}
      </div>
      <div style={cardStyle}>
        <b>Current schedules</b>
        {overview.runs.length === 0 ? <p style={{ color: "#6b7280", fontSize: "13px" }}>No schedule generated yet. Open <button style={btn} onClick={() => go("schedules")}>Schedules</button> to generate one.</p> : (
          <table style={{ width: "100%", fontSize: "13px", borderCollapse: "collapse", marginTop: "8px" }}><tbody>
            {overview.runs.map((r) => (<tr key={r.id}><td style={{ padding: "7px 0" }}><b>Grade {r.grade_level}</b> · {r.period_label} · v{r.version}</td>
              <td><Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge></td><td>{r.entry_count} periods</td><td>{r.validation?.errors ? `${r.validation.errors} conflict(s)` : "No conflicts"}</td></tr>))}
          </tbody></table>)}
      </div>
      <div style={cardStyle}>
        <b>Recent activity</b>
        <ul style={{ maxHeight: "220px", overflowY: "auto", margin: "8px 0 0", paddingLeft: "18px", fontSize: "13px", lineHeight: 1.7 }}>
          {overview.recent.length === 0 && <li style={{ color: "#6b7280" }}>No activity yet.</li>}
          {overview.recent.map((e) => <li key={e.id}><b>{e.action.replace(/_/g, " ")}</b> — {e.actor_name || "system"} · {formatDateTime(e.created_at)}</li>)}
        </ul>
      </div>
    </div>
  );
}

function CalendarTab({ level, overview, periodLabel, reload }) {
  const confirmDialog = useConfirmDialog();
  const [events, setEvents] = useState([]);
  const [edit, setEdit] = useState(null);
  const [mapEdit, setMapEdit] = useState(null);
  const [err, setErr] = useState("");
  const loadEvents = useCallback(() => be.get(level, "calendar/events/").then((r) => setEvents(r.data)), [level]);
  useEffect(() => { loadEvents(); }, [loadEvents]);
  const terms = overview.periods.filter((p) => p.kind === "term");
  const grading = overview.periods.filter((p) => p.kind === "semester");      // SHS Grade 12 only
  const saveEvent = async () => {
    setErr("");
    try { await be.post(level, "calendar/events/", { ...edit, academic_year: undefined }); setEdit(null); loadEvents(); }
    catch (e) { setErr(errText(e)); }
  };
  const saveMap = async () => {
    try { await be.post(level, `calendar/periods/${mapEdit.id}/terms/`, { terms: mapEdit.terms }); setMapEdit(null); reload(); }
    catch (e) { setErr(errText(e)); }
  };
  const saveTerm = async (t, patch) => { try { await be.patch(level, `calendar/periods/${t.id}/`, patch); reload(); } catch (e) { alert(errText(e)); } };
  return (
    <div>
      <div style={cardStyle}>
        <b>Terms (A.Y. {overview.academic_year})</b>
        <p style={{ color: "#6b7280", fontSize: "13px", margin: "4px 0 10px" }}>Source: {terms[0]?.source}</p>
        {terms.map((t) => (
          <div key={t.id} style={{ display: "flex", gap: "10px", alignItems: "center", padding: "6px 0", flexWrap: "wrap" }}>
            <b style={{ width: "70px" }}>{t.name}</b>
            <CustomDatePicker style={inputStyle} defaultValue={t.start_date || ""} onBlur={(e) => e.target.value !== (t.start_date || "") && saveTerm(t, { start_date: e.target.value })} aria-label={`${t.name} start date`} />
            <span>→</span>
            <CustomDatePicker style={inputStyle} defaultValue={t.end_date || ""} onBlur={(e) => e.target.value !== (t.end_date || "") && saveTerm(t, { end_date: e.target.value })} aria-label={`${t.name} end date`} />
          </div>))}
      </div>
      {grading.length > 0 && <div style={cardStyle}>
        <b>Grade 12 semesters and the terms they cover</b>
        <p style={{ color: "#6b7280", fontSize: "13px", margin: "4px 0 10px" }}>Grade 11 and Junior High use the 3 terms directly. Grade 12 keeps 2 semesters; set which terms fall inside each one.</p>
        {grading.map((g) => (
          <div key={g.id} style={{ display: "flex", gap: "10px", alignItems: "center", padding: "6px 0", flexWrap: "wrap" }}>
            <b style={{ width: "100px" }}>{g.name}</b>
            <span>{g.linked_terms.length ? terms.filter((t) => g.linked_terms.includes(t.id)).map((t) => t.name).join(" + ") : "— no terms linked —"}</span>
            {g.is_placeholder ? <Badge tone="warning">Placeholder — confirm</Badge> : <Badge tone="success">Confirmed</Badge>}
            <button style={btn} onClick={() => setMapEdit({ id: g.id, name: g.name, terms: [...g.linked_terms] })}>Edit</button>
          </div>))}
      </div>}
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between" }}><b>Holidays, examination periods and suspensions</b>
          <button style={btnPrimary} onClick={() => { setErr(""); setEdit({ kind: "suspension", name: "", start_date: "", end_date: "", blocks_classes: true }); }}>Add</button></div>
        <p style={{ color: "#6b7280", fontSize: "13px", margin: "4px 0" }}>No regular classes are counted on these dates.</p>
        <div style={{ maxHeight: "340px", overflowY: "auto" }}>
          <table style={{ width: "100%", fontSize: "13px", borderCollapse: "collapse" }}><tbody>
            {events.map((e) => (<tr key={e.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
              <td style={{ padding: "7px 8px 7px 0" }}>{e.start_date}{e.end_date !== e.start_date ? ` → ${e.end_date}` : ""}</td><td>{e.name}</td><td><Badge>{e.kind}</Badge></td>
              <td><button style={btn} onClick={async () => { if (await confirmDialog({ title: "Delete calendar entry?", message: `Delete ${e.name}?`, confirmLabel: "Delete entry" })) { await be.del(level, `calendar/events/${e.id}/`); loadEvents(); } }}>Remove</button></td></tr>))}
          </tbody></table>
        </div>
      </div>
      {edit && (
        <Modal title="Add calendar entry" onClose={() => setEdit(null)}>
          {err && <Notice tone="error">{err}</Notice>}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <Field label="Type"><CustomSelect style={{ ...inputStyle, width: "100%" }} value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>
              {[["holiday", "Holiday"], ["exam", "Examination period"], ["suspension", "Class suspension"], ["break", "Break"], ["other", "Other (no classes)"]].map((o) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}</CustomSelect></Field>
            <Field label="Name"><input style={{ ...inputStyle, width: "100%" }} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="From"><CustomDatePicker style={{ ...inputStyle, width: "100%" }} value={edit.start_date} onChange={(e) => setEdit({ ...edit, start_date: e.target.value, end_date: edit.end_date || e.target.value })} aria-label="Event start date" /></Field>
            <Field label="To"><CustomDatePicker style={{ ...inputStyle, width: "100%" }} value={edit.end_date} onChange={(e) => setEdit({ ...edit, end_date: e.target.value })} aria-label="Event end date" /></Field>
          </div>
          <div style={{ textAlign: "right", marginTop: "16px" }}><button style={btnPrimary} onClick={saveEvent}>Save</button></div>
        </Modal>)}
      {mapEdit && (
        <Modal title={`${mapEdit.name}: which terms does it cover?`} onClose={() => setMapEdit(null)} width={420}>
          {err && <Notice tone="error">{err}</Notice>}
          {terms.map((t) => (<label key={t.id} style={{ display: "block", padding: "6px 0", fontSize: "14px" }}>
            <input type="checkbox" checked={mapEdit.terms.includes(t.id)} onChange={(e) => setMapEdit({ ...mapEdit, terms: e.target.checked ? [...mapEdit.terms, t.id] : mapEdit.terms.filter((x) => x !== t.id) })} /> {t.name} ({t.start_date} → {t.end_date})</label>))}
          <div style={{ textAlign: "right", marginTop: "16px" }}><button style={btnPrimary} onClick={saveMap}>Save mapping</button></div>
        </Modal>)}
    </div>
  );
}

function SettingsTab({ level, overview, reload }) {
  const [cfg, setCfg] = useState(overview.config);
  const [wins, setWins] = useState(overview.windows);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await be.patch(level, "config/", { period_minutes: Number(cfg.period_minutes), break_minutes: Number(cfg.break_minutes), break_every: Number(cfg.break_every),
        max_teacher_hours: Number(cfg.max_teacher_hours), max_periods_per_teacher_day: Number(cfg.max_periods_per_teacher_day), building: cfg.building, floor: cfg.floor === "" || cfg.floor == null ? null : Number(cfg.floor) });
      for (const w of wins) await be.patch(level, `windows/${w.id}/`, { start_time: w.start_time, end_time: w.end_time, recess_start: w.recess_start || null, recess_end: w.recess_end || null, lunch_start: w.lunch_start || null, lunch_end: w.lunch_end || null, break_start: w.break_start || null, break_end: w.break_end || null, curriculum_framework: w.curriculum_framework, framework_verified: w.framework_verified, framework_note: w.framework_note });
      setMsg({ tone: "ok", text: "Saved. New schedules use these settings; existing versions are unchanged." }); reload();
    } catch (e) { setMsg({ tone: "error", text: errText(e) }); } finally { setBusy(false); }
  };
  const n = (k, label) => <Field label={label}><input style={{ ...inputStyle, width: "100%" }} type="number" value={cfg[k] ?? ""} onChange={(e) => setCfg({ ...cfg, [k]: e.target.value })} /></Field>;
  return (
    <div>
      <div style={cardStyle}>
        <b>{LEVEL_NAME[level]} configuration</b>
        {cfg.notes && <p style={{ color: "#6b7280", fontSize: "13px" }}>{cfg.notes}</p>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: "12px", marginTop: "10px" }}>
          <Field label="Building"><input style={{ ...inputStyle, width: "100%" }} value={cfg.building} onChange={(e) => setCfg({ ...cfg, building: e.target.value })} /></Field>
          {n("floor", "Floor (blank = whole building)")}{n("period_minutes", "Minutes per class period")}{n("break_minutes", "Break minutes (0 = none)")}{n("break_every", "Break after every N periods")}
          {n("max_teacher_hours", "Default teacher load (h / week)")}{n("max_periods_per_teacher_day", "Max periods per teacher per day")}
        </div>
      </div>
      <div style={cardStyle}>
        <b>Daily time windows and curriculum framework per grade level</b>
        {wins.map((w, i) => (
          <div key={w.id} style={{ display: "grid", gridTemplateColumns: "90px 130px 130px 1fr auto", gap: "10px", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #f3f4f6" }}>
            <b>Grade {w.grade_level}</b>
            <CustomTimePicker style={inputStyle} value={hhmm(w.start_time)} onChange={(e) => setWins(wins.map((x, j) => j === i ? { ...x, start_time: e.target.value } : x))} aria-label={`Grade ${w.grade_level} starts at`} />
            <CustomTimePicker style={inputStyle} value={hhmm(w.end_time)} onChange={(e) => setWins(wins.map((x, j) => j === i ? { ...x, end_time: e.target.value } : x))} aria-label={`Grade ${w.grade_level} ends at`} />
            <input style={inputStyle} placeholder="Curriculum framework" value={w.curriculum_framework} onChange={(e) => setWins(wins.map((x, j) => j === i ? { ...x, curriculum_framework: e.target.value } : x))} />
            <label style={{ fontSize: "13px" }}><input type="checkbox" checked={w.framework_verified} onChange={(e) => setWins(wins.map((x, j) => j === i ? { ...x, framework_verified: e.target.checked } : x))} /> verified</label>
            <div style={{ gridColumn: "1 / -1", display: "flex", gap: "14px", flexWrap: "wrap", alignItems: "center", fontSize: "13px", color: "#374151" }}>
              {(level === "SHS" ? [["Break (30 min)", "break_start", "break_end"]] : [["Recess", "recess_start", "recess_end"], ["Lunch", "lunch_start", "lunch_end"]]).map(([label, a, b]) => (
                <span key={label}><b>{label}</b>{" "}
                  <CustomTimePicker style={inputStyle} value={hhmm(w[a] || "")} onChange={(e) => setWins(wins.map((x, j) => j === i ? { ...x, [a]: e.target.value || null } : x))} aria-label={`${label} start`} />{" – "}
                  <CustomTimePicker style={inputStyle} value={hhmm(w[b] || "")} onChange={(e) => setWins(wins.map((x, j) => j === i ? { ...x, [b]: e.target.value || null } : x))} aria-label={`${label} end`} /></span>))}
            </div>
          </div>))}
        <p style={{ color: "#6b7280", fontSize: "13px" }}>{level === "SHS" ? "SHS has one 30-minute break (no separate recess or lunch)." : "Recess and lunch are both kept for JHS."} Breaks are never used for classes and show in the timetable and the printout. Classes are never placed outside a grade level's window. Current: {wins.map((w) => `Grade ${w.grade_level} ${ampm(hhmm(w.start_time))}–${ampm(hhmm(w.end_time))}`).join(" · ")}</p>
      </div>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      <button style={btnPrimary} disabled={busy} onClick={save}>{busy ? "Saving…" : "Save settings"}</button>
    </div>
  );
}

export default BasicEdDashboard;
