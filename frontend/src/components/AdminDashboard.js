import CustomSelect from "./CustomSelect";
import React, { useState } from "react";
import { notifyToast } from "../services/toast";
import { useMainScrollReset } from "../services/useMainScrollReset";
import API, { logout, getCurrentUser } from "../services/api";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import AdminRooms from "./AdminRooms";
import { AddStaffModal, BulkCreateAccounts } from "./AccountTools";
import { AdminHealthCard, AccountHygieneCard, AuditTrailCard } from "./InsightCards";
import HowToUse from "./HowToUse";
import AuditLogs from "./AuditLogs";
import { useDashboardTab } from "../services/preferences";
import { formatDateTime } from "../utils/formatDateTime";
import { useConfirmDialog } from "./ConfirmDialog";
import { AnimatedMetricValue } from "./Charts";

/* IT-admin workspace: setup health + counts, account tools, and clear-generated tools.
   Shown for role "admin" (or a Django superuser with no regular U-FAST role). */

// Same section style as the Dean and Registrar workspaces.
const NAV = [
  { group: "Insights" },
  { key: "overview", label: "Overview", icon: "" },
  { key: "activity", label: "Activity", icon: "" },
  { key: "audit", label: "Audit logs", icon: "" },
  { group: "People" },
  { key: "accounts", label: "Accounts", icon: "" },
  { group: "Management" },
  { key: "rooms", label: "Rooms", icon: "" },
  { group: "Data" },
  { key: "data", label: "Data Tools", icon: "" },
];

const HEADERS = {
  overview: { title: "System Overview", subtitle: "What is set up, what is missing, and whether the database is healthy." },
  accounts: { title: "Accounts", subtitle: "Add, search and manage every account: reset passwords, disable accounts, give a dean more than one department." },
  rooms: { title: "Rooms", subtitle: "Add, edit, view and manage the room records used by every scheduling dropdown." },
  data: { title: "Data Tools", subtitle: "Clear generated class or exam schedules so they can be generated again." },
  activity: { title: "Recent Activity", subtitle: "Latest changes recorded in the schedule log." },
  audit: { title: "Audit Logs", subtitle: "Who changed what, when, the values before and after, and from which IP address. Read only." },
};

const card = { background: "white", borderRadius: 6, padding: "20px 24px", marginBottom: "24px", border: "1px solid #e5e7eb", boxShadow: "none" };
const LEVEL = { error: { icon: "Error:", color: "#b91c1c" }, warn: { icon: "Warning:", color: "#92400e" }, info: { icon: "Note:", color: "#4b5563" }, ok: { icon: "OK:", color: "#166534" } };

function useLoad(fn, deps) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  React.useEffect(() => {
    setError("");
    fn().then(setData).catch((e) => setError(e.response?.data?.detail || (e.code === "ECONNABORTED" ? "Timed out -- slow connection or database." : "Could not load.")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...(deps || [])]);
  return [data, error, () => setTick((n) => n + 1)];
}

function Stat({ label, value }) {
  return (
    <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "8px 12px", minWidth: "120px" }}>
      <div style={{ fontSize: "18px", fontWeight: 600, color: "#111827", fontVariantNumeric: "tabular-nums" }}><AnimatedMetricValue value={value} /></div>
      <div style={{ fontSize: "12px", color: "#6b7280" }}>{label}</div>
    </div>
  );
}

function Overview() {
  const [data, error, reload] = useLoad(() => API.get("/accounts/admin/overview/").then((r) => r.data));
  if (error) return <p style={{ color: "#b91c1c" }}>{error} <button onClick={reload}>Try again</button></p>;
  if (!data) return <p>Loading…</p>;
  const c = data.counts;
  return (
    <div>
      <div style={card}>
        <h3 style={{ marginTop: 0, color: "#003366" }}>Database</h3>
        <p style={{ margin: 0 }}>
          Engine: <b>{data.db.engine}</b> · response time <b>{data.db.latency_ms} ms</b>{" "}
          {data.db.latency_ms > 800 ? <Badge tone="warning">slow connection</Badge> : <Badge tone="success">OK</Badge>}
        </p>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0, color: "#003366" }}>Setup health</h3>
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {data.checks.map((k, i) => (
            <li key={i} style={{ padding: "6px 0", color: LEVEL[k.level].color, fontSize: "14px" }}><strong style={{ fontWeight: 600 }}>{LEVEL[k.level].icon}</strong> {k.text}</li>
          ))}
        </ul>
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0, color: "#003366" }}>What is in the system</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "14px" }}>
          <Stat label="Programs" value={c.programs} /><Stat label="Subjects" value={c.subjects} /><Stat label="Sections" value={c.sections} />
          <Stat label="Rooms" value={c.rooms} /><Stat label="Time slots" value={c.time_slots} /><Stat label="Faculty" value={c.faculty} />
          <Stat label="Class rows" value={c.class_rows} /><Stat label="Exam rows" value={c.exam_rows} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
          {Object.entries(data.users).map(([k, v]) => <Stat key={k} label={`${k.replace("_", "-")} accounts`} value={v} />)}
          <Stat label="Draft class rows" value={data.schedule_status.draft} />
          <Stat label="Approved" value={data.schedule_status.approved} />
          <Stat label="Published" value={data.schedule_status.published} />
          <Stat label="Conflict log entries" value={data.conflict_log_entries} />
        </div>
      </div>
      <p style={{ fontSize: "13px", color: "#6b7280" }}>
        The full data editor is the Django admin at <b>{(API.defaults.baseURL || "").replace(/\/api\/?$/, "") || window.location.origin}/admin/</b>.
      </p>
    </div>
  );
}

const ROLE_NAME = { registrar: "Registrar", admin: "IT Admin", student: "Student", principal: "Principal", teacher: "SHS/JHS Teacher" };
const TYPE_NAME = { dean: "Dean", full_time: "Full-time faculty", part_time: "Part-time faculty" };
const roleLabel = (r) => TYPE_NAME[r.faculty_type] || ROLE_NAME[r.role] || r.role || "IT Admin";

export function Accounts({ level } = {}) {
  const [rows, error, reload] = useLoad(() => API.get("/accounts/directory/").then((r) => r.data));
  const [programs] = useLoad(() => API.get("/curriculum/programs/").then((r) => r.data));
  const [toast, setToast] = useState(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const me = getCurrentUser();
  const departments = programs ? [...new Set(programs.map((p) => p.department))].sort() : [];

  const act = async (key, fn) => {
    setBusy(key); setToast(null);
    try { const res = await fn(); const message = res.data.detail || "Action completed."; setToast({ ok: true, text: message }); notifyToast(message); reload(); }
    catch (e) { const message = e.response?.data?.detail || "Request failed."; setToast({ ok: false, text: message }); notifyToast(message, "error"); }
    finally { setBusy(""); }
  };
  const editDepts = (r) => {
    const current = (r.extra_departments || "").split(";").filter(Boolean).join("; ");
    const answer = window.prompt(
      `Extra departments for ${r.full_name} (separate with ;). Leave empty for none.\nAvailable: ${departments.join(" | ")}`, current);
    if (answer === null) return;
    act(`dept${r.id}`, () => API.post("/accounts/admin/set-dean-departments/", {
      username: r.username, extra_departments: answer.split(";").map((x) => x.trim()).filter(Boolean) }));
  };

  if (error) return <p style={{ color: "#b91c1c" }}>{error} <button onClick={reload}>Try again</button></p>;
  if (!rows) return <p>Loading accounts…</p>;
  const q = search.trim().toLowerCase();
  // Every word typed must match somewhere in: School ID, name, username, email, role (raw + friendly),
  // faculty classification (Full-time / Part-time) or department.
  const haystack = (r) => [
    r.school_id, r.full_name, r.username, r.email, r.role, r.faculty_type, roleLabel(r),
    r.faculty_classification, r.department, r.extra_departments,
  ].filter(Boolean).join(" ").toLowerCase();
  const words = q.split(/\s+/).filter(Boolean);
  // SHS / JHS workspace: only that level's principal and teachers
  const inLevel = (r) => !level || ((r.role === "principal" || r.role === "teacher") && r.school_level === level);
  const shown = rows.filter((r) => inLevel(r) && (() => { const h = haystack(r); return words.every((w) => h.includes(w)); })());
  const btn = { background: "white", border: "1px solid #d1d5db", padding: "5px 10px", borderRadius: 4, fontSize: "13px", fontWeight: 600, cursor: "pointer", color: "#003366", marginRight: "6px" };

  return (
    <div style={card}>
      {level ? (
        <p style={{ fontSize: "13px", color: "#6b7280", marginTop: 0 }}>Teacher accounts of this level are added in the <b>Faculty</b> tab; this list is for resetting passwords and enabling or disabling accounts.</p>
      ) : (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end", marginBottom: "12px" }}>
          <button style={{ ...btn, background: "#003366", color: "white", marginRight: 0 }} onClick={() => setShowAdd(true)}>Add account</button>
          <button style={{ ...btn, marginRight: 0 }} onClick={() => setShowBulk((v) => !v)}>{showBulk ? "Hide CSV import" : "Import CSV"}</button>
        </div>)}
      {showAdd && <AddStaffModal onClose={() => setShowAdd(false)} onCreated={reload} />}
      {showBulk && <div style={{ marginBottom: "16px" }}><BulkCreateAccounts onCreated={reload} /></div>}

      <div className="directory-search">
        <input type="search" aria-label="Search accounts"
               placeholder="Search School ID, name, email, role (e.g. dean) or Full-time / Part-time"
               value={search} onChange={(e) => setSearch(e.target.value)} />
        {search && <button style={{ ...btn, marginRight: 0 }} onClick={() => setSearch("")}>Clear search</button>}
      </div>
      <div style={{ fontSize: "13px", color: "#6b7280", marginBottom: "8px" }}>
        {q ? `${shown.length} account${shown.length === 1 ? "" : "s"} match` : `${shown.length} account${shown.length === 1 ? "" : "s"}`}{level ? " — principal and teachers of this level" : ""}
      </div>
      {toast && <p style={{ color: toast.ok ? "#1e7a45" : "#b91c1c", fontSize: "13px" }}>{toast.text}</p>}
      <div className="scroll-box">
        <table>
          <thead><tr><th>School ID</th><th>Person</th><th>Email</th><th>Role</th><th>Department(s)</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={7} style={{ color: "#6b7280" }}>No account matches “{search}”. <button style={btn} onClick={() => setSearch("")}>Clear search</button></td></tr>}
            {shown.map((r) => (
              <tr key={r.id} style={r.is_active ? undefined : { opacity: 0.55 }}>
                <td>{r.school_id}</td>
                <td style={{ fontWeight: 600 }}>{r.full_name}<div style={{ fontSize: "12px", color: "#6b7280", fontWeight: 400 }}>{r.username}</div></td>
                <td style={{ wordBreak: "break-word" }}>{r.email || "—"}</td>
                <td><Badge tone="neutral">{roleLabel(r)}</Badge></td>
                <td>{r.department || "—"}</td>
                <td>{!r.is_active ? <Badge tone="warning">Disabled</Badge> : r.must_change_password ? <Badge tone="warning">First login</Badge> : <Badge tone="success">Active</Badge>}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button style={btn} disabled={busy === `r${r.id}`} onClick={() => act(`r${r.id}`, () => API.post("/accounts/reset-password/", { username: r.username }))}>Reset password</button>
                  {r.username !== me?.username && (
                    <button style={btn} disabled={busy === `a${r.id}`} onClick={() => act(`a${r.id}`, () => API.post("/accounts/admin/set-active/", { username: r.username, active: !r.is_active }))}>
                      {r.is_active ? "Disable" : "Enable"}
                    </button>
                  )}
                  {r.faculty_type === "dean" && <button style={btn} onClick={() => editDepts(r)}>Departments…</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DataTools() {
  const confirmDialog = useConfirmDialog();
  const [programs] = useLoad(() => API.get("/curriculum/programs/").then((r) => r.data));
  const [f, setF] = useState({ scope: "classes", program_id: "", year_level: "", semester: "", include_approved: false });
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => { setF({ ...f, [k]: v }); setPreview(null); setMsg(null); };

  const run = async (apply) => {
    setBusy(true); setMsg(null);
    try {
      const res = await API.post("/accounts/admin/clear-generated/", { ...f, apply });
      if (apply) { const message = `Deleted ${res.data.count} row(s).`; setMsg({ ok: true, text: message }); notifyToast(message); setPreview(null); }
      else setPreview(res.data);
    } catch (e) { const message = e.response?.data?.detail || "Request failed."; setMsg({ ok: false, text: message }); notifyToast(message, "error"); }
    finally { setBusy(false); }
  };
  return (
    <div style={card}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "14px" }}>
        <CustomSelect value={f.scope} onChange={(e) => set("scope", e.target.value)}>
          <option value="classes">Class schedules</option><option value="exams">Exam schedules</option>
        </CustomSelect>
        <CustomSelect value={f.program_id} onChange={(e) => set("program_id", e.target.value)}>
          <option value="">All programs</option>
          {(programs || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </CustomSelect>
        <CustomSelect value={f.year_level} onChange={(e) => set("year_level", e.target.value)}>
          <option value="">All year levels</option>
          {["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"].map((y) => <option key={y} value={y}>{y}</option>)}
        </CustomSelect>
        <CustomSelect value={f.semester} onChange={(e) => set("semester", e.target.value)}>
          <option value="">Both semesters</option><option value="1st Sem">1st Sem</option><option value="2nd Sem">2nd Sem</option>
        </CustomSelect>
        {f.scope === "classes" && (
          <label style={{ fontSize: "13px" }}>
            <input type="checkbox" checked={f.include_approved} onChange={(e) => set("include_approved", e.target.checked)} /> include approved / published
          </label>
        )}
      </div>
      <button onClick={() => run(false)} disabled={busy}>Preview what would be deleted</button>
      {preview && (
        <div style={{ marginTop: "14px", padding: "12px", background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 6 }}>
          <p style={{ margin: "0 0 8px" }}><b>{preview.count}</b> row(s) would be deleted
            {preview.kept_approved ? ` (${preview.kept_approved} approved/published row(s) will be kept)` : ""}.</p>
          {preview.count > 0 && (
            <button style={{ background: "#b91c1c", color: "white" }} disabled={busy}
              onClick={async () => { if (await confirmDialog({ title: "Delete schedules?", message: `Delete ${preview.count} row(s)? This cannot be undone.`, confirmLabel: "Delete schedules" })) run(true); }}>
              Yes, delete them
            </button>
          )}
        </div>
      )}
      {msg && <p style={{ color: msg.ok ? "#1e7a45" : "#b91c1c" }}>{msg.text}</p>}
      <p style={{ fontSize: "13px", color: "#6b7280", marginTop: "14px" }}>
        Without the "include approved" box only Draft rows are removed, so nothing already signed off is lost by accident.
      </p>
    </div>
  );
}

function Activity() {
  const [data, error, reload] = useLoad(() => API.get("/accounts/admin/overview/").then((r) => r.data));
  if (error) return <p style={{ color: "#b91c1c" }}>{error} <button onClick={reload}>Try again</button></p>;
  if (!data) return <p>Loading…</p>;
  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "6px", marginBottom: "10px" }}>
        <h3 style={{ margin: 0, color: "#003366" }}>Recent Activity</h3>
        <span style={{ fontSize: "13px", color: "#6b7280" }}>{data.recent_logs.length} most recent entries · newest first</span>
      </div>
      {data.recent_logs.length === 0 ? <p>No schedule changes have been logged yet.</p> : (
        <div className="scroll-box" role="region" aria-label="Recent activity" tabIndex={0}>
          <table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr></thead>
            <tbody>
              {data.recent_logs.map((l, i) => (
                <tr key={i}><td style={{ whiteSpace: "nowrap" }}>{formatDateTime(l.when)}</td><td>{l.who}</td><td>{l.action}</td><td style={{ wordBreak: "break-word" }}>{l.text}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AdminDashboard() {
  const [tab, setTab] = useDashboardTab(NAV, "overview", "admin-college");
  useMainScrollReset(tab);
  const user = getCurrentUser();
  const h = HEADERS[tab];
  const handleLogout = () => { logout(); window.location.href = "/login?signedOut=1"; };
  return (
    <div className="app-shell">
      <Sidebar brandLabel="U-FAST" workspaceLabel="IT Admin" items={NAV} activeKey={tab} onSelect={setTab}
        userName={user?.username || "Admin"} userRole="IT administrator" onSignOut={handleLogout} />
      <div className="app-main">
        <TopBar crumb={h.title} userName={user?.username} navItems={NAV} onNavigate={setTab} />
        <PageHeader eyebrow="IT ADMIN WORKSPACE" title={h.title} subtitle={h.subtitle} />
        <div className="app-page-body motion-page-content" key={tab}>
          {tab === "overview" && <><HowToUse role="admin" tab="overview" /><Overview /><AdminHealthCard /><AccountHygieneCard /></>}
          {tab === "accounts" && <Accounts />}
          {tab === "rooms" && <AdminRooms />}
          {tab === "data" && <DataTools />}
          {tab === "activity" && <><HowToUse role="admin" tab="activity" /><Activity /><AuditTrailCard /></>}
          {tab === "audit" && <><HowToUse role="admin" tab="audit" /><AuditLogs /></>}
        </div>
      </div>
    </div>
  );
}

export default AdminDashboard;
