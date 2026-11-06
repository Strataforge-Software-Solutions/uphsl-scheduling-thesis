import React, { useEffect, useState } from "react";
import API from "../services/api";
import { formatDateTime, formatTime } from "../utils/formatDateTime";

/* New read-only insight cards (additive). They only call the GET endpoints under /api/analytics/... and never change data.
   Buttons carry explicit colours (the theme has a global button { color: white } rule). Empty data shows "No data yet". */
const C = { navy: "#003366", line: "#e5e7eb", muted: "#6b7280", bad: "#b91c1c", warn: "#96690a", ok: "#1e7a45" };
const card = { background: "#ffffff", borderRadius: 6, padding: "18px 22px", marginBottom: 22, border: "1px solid #e5e7eb", boxShadow: "none" };
const linkBtn = { background: "#ffffff", color: C.navy, border: `1px solid ${C.navy}`, borderRadius: 6, padding: "3px 10px", fontSize: 12, cursor: "pointer" };

export function useInsight(url, params) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const key = JSON.stringify(params || {});
  useEffect(() => {
    let alive = true;
    setError(""); setData(null);
    API.get(url, { params: params || {} })
      .then((r) => { if (alive) setData(r.data); })
      .catch((e) => { if (alive) setError(e.response?.data?.detail || "Could not load this card."); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, key, tick]);
  return [data, error, () => setTick((n) => n + 1)];
}

const CardTitle = React.createContext("u-fast");

export function InsightCard({ title, subtitle, error, loading, onRetry, children, right }) {
  return (
    <CardTitle.Provider value={title}>
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, color: C.navy }}>{title}</h3>
        {right}
      </div>
      {subtitle && <p style={{ fontSize: 13, color: C.muted, margin: "4px 0 12px" }}>{subtitle}</p>}
      {error ? <p style={{ color: C.bad, fontSize: 13 }}>{error} {onRetry && <button onClick={onRetry} style={linkBtn}>Try again</button>}</p>
        : loading ? <p style={{ color: C.muted, fontSize: 13 }}>Loading…</p> : children}
    </div>
    </CardTitle.Provider>
  );
}

/* CSV of exactly the rows of a table (all of them, not only the first 200 shown). A column exports its `csv(row)` value, else the
   row's own field; a column with neither (e.g. a button) is left out. Done in the browser: nothing is sent to the server. */
const cell = (v) => {
  if (v === null || v === undefined) return "";
  const t = Array.isArray(v) ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : x)).join("; ") : typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\n\r]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
};
export function downloadCsv(name, columns, rows) {
  const cols = columns.filter((c) => c.csv || rows.some((r) => r[c.key] !== undefined));
  const lines = [cols.map((c) => cell(c.label || c.key)).join(","),
    ...rows.map((r) => cols.map((c) => cell(c.csv ? c.csv(r) : r[c.key])).join(","))];
  const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "u-fast"}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function Metric({ label, value, tone, onClick, active }) {
  const color = tone === "bad" ? C.bad : tone === "warn" ? C.warn : tone === "ok" ? C.ok : C.navy;
  return (
    <button type="button" onClick={onClick} disabled={!onClick}
      style={{ textAlign: "left", background: active ? "#eef6ff" : "#f9fafb", color: "#111827", border: `1px solid ${active ? C.navy : C.line}`,
        borderRadius: 6, padding: "10px 14px", minWidth: 140, flex: "1 1 140px", cursor: onClick ? "pointer" : "default", boxShadow: "none" }}>
      <div style={{ fontSize: 18, fontWeight: 600, color, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: 12, color: C.muted }}>{label}</div>
    </button>
  );
}

export function SimpleTable({ columns, rows, empty = "No data yet.", max = 200, csvName }) {
  const title = React.useContext(CardTitle);
  if (!rows || !rows.length) return <p style={{ color: C.muted, fontSize: 13, margin: "6px 0" }}>{empty}</p>;
  return (
    <>
    <div style={{ textAlign: "right", marginTop: 6 }}>
      <button type="button" onClick={() => downloadCsv(csvName || title, columns, rows)} style={linkBtn} title="Download every row of this table as a CSV file">
        ⬇ Export CSV ({rows.length})</button>
    </div>
    <div className="scroll-box" style={{ maxHeight: 320, overflowY: "auto" }}>
      <table className="sched-compact" style={{ marginTop: 6 }}>
        <thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, max).map((r, i) => (
            <tr key={i}>{columns.map((c) => <td key={c.key} style={{ wordBreak: "break-word" }}>{c.render ? c.render(r) : String(r[c.key] ?? "")}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && <p style={{ fontSize: 12, color: C.muted }}>Showing the first {max} of {rows.length} (the CSV has all of them).</p>}
    </div>
    </>
  );
}

const when = (iso) => (iso ? formatDateTime(iso) : "—");
// the filter object without empty values, as query parameters
export const fq = (f) => Object.fromEntries(Object.entries(f || {}).filter(([_k, v]) => v !== "" && v !== null && v !== undefined));

/* ---------------------------------------------------------------- Stage 1: IT admin */
export function AdminHealthCard() {
  const [d, error, retry] = useInsight("/analytics/admin/health/");
  const [open, setOpen] = useState("");
  const toggle = (k) => setOpen((o) => (o === k ? "" : k));
  const lists = d && {
    unplaced: { cols: [{ key: "subject", label: "Subject" }, { key: "section", label: "Section" }, { key: "kind", label: "Kind" },
      { key: "semester", label: "Semester" }, { key: "h", label: "Hours placed", render: (r) => `${r.placed_hours} of ${r.needed_hours}`, csv: (r) => `${r.placed_hours} of ${r.needed_hours}` }], rows: d.unplaced,
      empty: "Every generated class is fully placed." },
    rooms: { cols: [{ key: "name", label: "Room" }, { key: "type", label: "Type" }, { key: "capacity", label: "Seats" }], rows: d.rooms_no_department_list,
      empty: "Every room has a department." },
    faculty: { cols: [{ key: "name", label: "Teacher" }, { key: "department", label: "Department" },
      { key: "has_degree", label: "Degree / qualifications recorded", render: (r) => (r.has_degree ? "Yes" : "No") },
      { key: "active", label: "Active", render: (r) => (r.active ? "Yes" : "No") }], rows: d.faculty_no_specialization_list,
      empty: "Every teacher has at least one specialization." },
    sections: { cols: [{ key: "section", label: "Section" }, { key: "department", label: "Department" }, { key: "year_level", label: "Year" },
      { key: "semester", label: "Semester" }], rows: d.sections_no_curriculum_list, empty: "Every section has a curriculum." },
  };
  return (
    <InsightCard title="System health" subtitle="Read-only check of the whole schedule and setup. Click a number to see the list."
      error={error} loading={!d && !error} onRetry={retry} right={<button onClick={retry} style={linkBtn}>Refresh</button>}>
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label="Unplaced classes (generated year levels)" value={d.unplaced_classes} tone={d.unplaced_classes ? "bad" : "ok"} onClick={() => toggle("unplaced")} active={open === "unplaced"} />
            <Metric label="Open conflicts (teacher / room / students)" value={d.open_conflicts} tone={d.open_conflicts ? "bad" : "ok"} />
            <Metric label="Rooms with no department" value={d.rooms_no_department} tone={d.rooms_no_department ? "warn" : "ok"} onClick={() => toggle("rooms")} active={open === "rooms"} />
            <Metric label="Faculty with no specialization" value={d.faculty_no_specialization} tone={d.faculty_no_specialization ? "warn" : "ok"} onClick={() => toggle("faculty")} active={open === "faculty"} />
            <Metric label="Sections with no curriculum" value={d.sections_no_curriculum} tone={d.sections_no_curriculum ? "warn" : "ok"} onClick={() => toggle("sections")} active={open === "sections"} />
          </div>
          <p style={{ fontSize: 13, color: C.muted, margin: "10px 0 0" }}>
            {d.not_generated_classes} class{d.not_generated_classes === 1 ? "" : "es"} belong to year levels nobody has generated yet.
            {d.open_conflicts > 0 && ` Conflicts by kind: ${Object.entries(d.conflict_counts).map(([k, n]) => `${k} ${n}`).join(", ")} (fix them in a Dean's or the Registrar's Conflicts tab).`}
            {d.unresolved_unplaced_log_entries > 0 && ` ${d.unresolved_unplaced_log_entries} 'could not place' entries are still open in the conflict log.`}
          </p>
          {open && <div style={{ marginTop: 10 }}><SimpleTable columns={lists[open].cols} rows={lists[open].rows} empty={lists[open].empty} /></div>}
          <ul style={{ fontSize: 12, color: C.muted, margin: "10px 0 0 18px", padding: 0 }}>{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </>
      )}
    </InsightCard>
  );
}

export function AccountHygieneCard() {
  const [d, error, retry] = useInsight("/analytics/admin/accounts/");
  const [open, setOpen] = useState("");
  const toggle = (k) => setOpen((o) => (o === k ? "" : k));
  const cols = [{ key: "username", label: "Login" }, { key: "name", label: "Name" }, { key: "role", label: "Role" },
    { key: "department", label: "Department / level", render: (r) => r.department || r.school_level }, { key: "last_login", label: "Last sign-in", render: (r) => when(r.last_login) }];
  const dupRows = d ? d.duplicate_email_list.flatMap((g) => g.accounts.map((a) => ({ ...a, email: g.email }))) : [];
  return (
    <InsightCard title="Account hygiene" subtitle="Accounts nobody has used, disabled accounts and e-mail addresses used by more than one account."
      error={error} loading={!d && !error} onRetry={retry}>
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label={`Never signed in (of ${d.total_accounts})`} value={d.never_signed_in} tone={d.never_signed_in ? "warn" : "ok"} onClick={() => toggle("never")} active={open === "never"} />
            <Metric label="Inactive (disabled)" value={d.inactive} onClick={() => toggle("inactive")} active={open === "inactive"} />
            <Metric label="Duplicate e-mails" value={d.duplicate_emails} tone={d.duplicate_emails ? "bad" : "ok"} onClick={() => toggle("dupes")} active={open === "dupes"} />
            <Metric label="Still on the first password" value={d.still_on_first_password} tone={d.still_on_first_password ? "warn" : "ok"} />
            <Metric label="Accounts with no e-mail" value={d.accounts_without_email} />
          </div>
          {open === "never" && <SimpleTable columns={cols} rows={d.never_signed_in_list} empty="Everyone has signed in at least once." />}
          {open === "inactive" && <SimpleTable columns={cols} rows={d.inactive_list} empty="No disabled accounts." />}
          {open === "dupes" && <SimpleTable columns={[{ key: "email", label: "E-mail" }, ...cols]} rows={dupRows} empty="No e-mail is used twice." />}
          <p style={{ fontSize: 12, color: C.muted, margin: "10px 0 0" }}>Enable, disable or reset these accounts in the Accounts tab.</p>
        </>
      )}
    </InsightCard>
  );
}

const CAT_TONE = { approved: "#166534", published: "#1d4ed8", removed: "#b91c1c", "back to draft": "#7a4b00", "blocked approval": "#b91c1c", generated: "#374151" };
export function AuditTrailCard() {
  const [cat, setCat] = useState("");
  const [d, error, retry] = useInsight("/analytics/admin/audit/", cat ? { category: cat } : {});
  const cats = ["", "generated", "approved", "published", "back to draft", "blocked approval", "removed", "restored (undo)", "moved / resolved", "edited", "workload"];
  return (
    <InsightCard title="Audit trail" subtitle="Who approved, published, removed or generated what, and when. Read-only."
      error={error} loading={!d && !error} onRetry={retry}
      right={<select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Filter by kind" style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13 }}>
        {cats.map((c) => <option key={c} value={c}>{c ? c[0].toUpperCase() + c.slice(1) : "Every kind"}</option>)}</select>}>
      {d && (
        <>
          <SimpleTable rows={d.events} empty="Nothing recorded yet." columns={[
            { key: "when", label: "When", render: (r) => <span style={{ whiteSpace: "nowrap" }}>{when(r.when)}</span> },
            { key: "who", label: "Who", render: (r) => (r.who === "not recorded" ? <em style={{ color: C.muted }}>not recorded</em> : r.who) },
            { key: "category", label: "What", render: (r) => <strong style={{ color: CAT_TONE[r.category] || "#374151" }}>{r.category}</strong> },
            { key: "details", label: "Details" }]} />
          <div style={{ background: "#fffbeb", border: "1px solid #fde68a", color: "#7a4b00", borderRadius: 6, padding: "8px 12px", fontSize: 13, marginTop: 10 }}>
            <strong>Not recorded by the system:</strong>
            <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>{d.not_recorded.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </div>
        </>
      )}
    </InsightCard>
  );
}


/* ---------------------------------------------------------------- Stage 2: Deans (own college; Registrar / IT admin read-only) */
function Progress({ parts, total }) {
  if (!total) return <span style={{ fontSize: 12, color: C.muted }}>No classes</span>;
  return (
    <div title={parts.map((p) => `${p.label}: ${p.value}`).join(" · ")} style={{ display: "flex", height: 12, borderRadius: 6, overflow: "hidden", background: "#eef2f7", minWidth: 120 }}>
      {parts.filter((p) => p.value > 0).map((p) => <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />)}
    </div>
  );
}
const STAGE_COLORS = { published: "#003366", approved: "#5b7fa6", draft: "#c3cfdc", unplaced: "#b91c1c" };      // navy shades + red only for a problem
function StageLegend() {
  return (
    <div aria-hidden="true" style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12, color: "#4b5563", margin: "2px 0 8px" }}>
      {[["Published", STAGE_COLORS.published], ["Approved", STAGE_COLORS.approved], ["Draft", STAGE_COLORS.draft], ["Unplaced", STAGE_COLORS.unplaced]].map(([l, c]) => (
        <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 10, height: 10, background: c, display: "inline-block" }} />{l}</span>
      ))}
    </div>
  );
}

export function SemesterSelect({ value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Semester"
      style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13, background: "#ffffff", color: "#111827" }}>
      <option value="">All semesters</option>
      <option value="1st Sem">1st Sem</option>
      <option value="2nd Sem">2nd Sem</option>
    </select>
  );
}

export function ReadinessCard({ filters = {}, kind = "major", title = "Readiness by program and year level" }) {
  const [d, error, retry] = useInsight("/analytics/dean/readiness/", { ...fq(filters), kind });
  return (
    <InsightCard title={title} error={error} loading={!d && !error} onRetry={retry}
      subtitle="One class = one section and one subject. Unplaced = fewer hours than its units need (including year levels not generated yet). A class counts at the stage of its least advanced period.">
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
            <Metric label="Classes" value={d.totals.classes} />
            <Metric label="Published" value={d.totals.published} tone="ok" />
            <Metric label="Approved" value={d.totals.approved} />
            <Metric label="Draft" value={d.totals.draft} tone={d.totals.draft ? "warn" : undefined} />
            <Metric label="Unplaced" value={d.totals.unplaced} tone={d.totals.unplaced ? "bad" : "ok"} />
          </div>
          <StageLegend />
          <div style={{ display: "flex", gap: 12, fontSize: 12, color: C.muted, margin: "4px 0" }}>
            {Object.entries(STAGE_COLORS).map(([k, c]) => <span key={k}><span style={{ display: "inline-block", width: 10, height: 10, background: c, borderRadius: 2, marginRight: 4 }} />{k}</span>)}
          </div>
          <SimpleTable rows={d.rows} empty="No sections in scope yet." columns={[
            { key: "program", label: "Program" }, { key: "year_level", label: "Year" }, { key: "semester", label: "Semester" },
            { key: "classes", label: "Classes" }, { key: "published", label: "Published" }, { key: "approved", label: "Approved" },
            { key: "draft", label: "Draft" }, { key: "unplaced", label: "Unplaced", render: (r) => <strong style={{ color: r.unplaced ? C.bad : C.ok }}>{r.unplaced}</strong> },
            { key: "bar", label: "Progress", csv: (r) => `${r.placed_pct}% placed; ${r.published_pct}% published`, render: (r) => (
              <div><Progress total={r.classes} parts={["published", "approved", "draft", "unplaced"].map((k) => ({ label: k, value: r[k], color: STAGE_COLORS[k] }))} />
                <div style={{ fontSize: 12, color: C.muted }}>{r.placed_pct}% placed · {r.published_pct}% published</div></div>) }]} />
        </>
      )}
    </InsightCard>
  );
}

export function FacultyFitCard({ filters = {} }) {
  const [d, error, retry] = useInsight("/analytics/dean/faculty-fit/", fq(filters));
  const [open, setOpen] = useState("outside");
  const cls = [{ key: "teacher", label: "Teacher" }, { key: "teacher_department", label: "Teacher's department" }, { key: "code", label: "Subject", render: (r) => `${r.code} ${r.title}`, csv: (r) => `${r.code} ${r.title}` },
    { key: "field", label: "Subject field" }, { key: "section", label: "Section" }, { key: "status", label: "Status" }];
  return (
    <InsightCard title="Faculty fit" error={error} loading={!d && !error} onRetry={retry}
      subtitle="Uses the system's qualification rule (the same one the generator uses). Nothing is changed here: fix a class with Edit in the Schedules tab, or record a specialization in the Faculty tab.">
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label="Subjects with no qualified teacher" value={d.subjects_without_qualified_faculty.length} tone={d.subjects_without_qualified_faculty.length ? "bad" : "ok"} onClick={() => setOpen("nobody")} active={open === "nobody"} />
            <Metric label="Classes taught outside the teacher's qualification" value={d.teaching_outside_specialization.length} tone={d.teaching_outside_specialization.length ? "bad" : "ok"} onClick={() => setOpen("outside")} active={open === "outside"} />
            <Metric label="Qualified by degree only (specialization not recorded)" value={d.qualified_by_degree_only.length} tone={d.qualified_by_degree_only.length ? "warn" : "ok"} onClick={() => setOpen("degree")} active={open === "degree"} />
          </div>
          {open === "nobody" && <SimpleTable rows={d.subjects_without_qualified_faculty} empty="Every subject has at least one qualified teacher." columns={[
            { key: "code", label: "Subject", render: (r) => `${r.code} ${r.title}`, csv: (r) => `${r.code} ${r.title}` }, { key: "program", label: "Program" }, { key: "year_level", label: "Year" },
            { key: "semester", label: "Semester" }, { key: "field", label: "Field" }, { key: "why", label: "Why" }]} />}
          {open === "outside" && <SimpleTable rows={d.teaching_outside_specialization} columns={cls} empty="Every class has a qualified teacher." />}
          {open === "degree" && <SimpleTable rows={d.qualified_by_degree_only} columns={cls} empty="Every match is a recorded specialization." />}
          <ul style={{ fontSize: 12, color: C.muted, margin: "10px 0 0 18px", padding: 0 }}>{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </>
      )}
    </InsightCard>
  );
}

export function LabCapacityCard({ filters = {} }) {
  const [d, error, retry] = useInsight("/analytics/dean/lab-capacity/", fq(filters));
  return (
    <InsightCard title="Lab capacity (designated laboratories)" error={error} loading={!d && !error} onRetry={retry}
      subtitle={`Hours booked vs free per day in the rooms your majors must use${d && d.semester ? ` · ${d.semester}` : ""}. Free = the day's time-slot span minus booked hours.`}>
      {d && (d.labs.length === 0 ? <p style={{ color: C.muted, fontSize: 13 }}>{d.note || "No data yet."}</p> : d.labs.map((l) => (
        <div key={l.room} style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 600, color: "#111827", fontSize: 14 }}>{l.room}{l.label && l.label !== l.room ? ` (${l.label})` : ""} · {l.capacity} seats ·{" "}
            <span style={{ color: l.used_pct >= 90 ? C.bad : l.used_pct >= 70 ? C.warn : C.ok }}>{l.used_hours} h booked, {l.free_hours} h free ({l.used_pct}% used)</span></div>
          {l.days.map((x) => (
            <div key={x.day} style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4, fontSize: 13 }}>
              <span style={{ width: 34, color: C.muted }}>{x.day}</span>
              <div style={{ flex: 1, background: "#eef2f7", borderRadius: 6, height: 12, overflow: "hidden" }}>
                <div style={{ width: `${x.used_pct}%`, height: "100%", background: x.used_pct >= 90 ? "#b91c1c" : x.used_pct >= 70 ? "#b45309" : "#003366" }} />
              </div>
              <span style={{ width: 150, color: "#374151" }}>{x.used_hours} h used · {x.free_hours} h free</span>
            </div>
          ))}
        </div>
      )))}
    </InsightCard>
  );
}

export function LoadBandsCard({ filters = {}, onOpenResolver }) {
  const [pct, setPct] = useState(50);
  const [d, error, retry] = useInsight("/analytics/dean/load-bands/", { ...fq(filters), under_pct: pct });
  const [open, setOpen] = useState("overloaded");
  return (
    <InsightCard title="Faculty load bands" error={error} loading={!d && !error} onRetry={retry}
      subtitle="Weekly hours against each teacher's own limit (the limits in Settings). Shared classes count once."
      right={<label style={{ fontSize: 13, color: "#374151" }}>Underloaded below{" "}
        <select value={pct} onChange={(e) => setPct(Number(e.target.value))} style={{ padding: "3px 6px", borderRadius: 6, border: "1px solid #d1d5db", background: "#ffffff", color: "#111827" }}>
          {[25, 50, 75].map((p) => <option key={p} value={p}>{p}%</option>)}</select> of the limit</label>}>
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label="Overloaded" value={d.counts.overloaded} tone={d.counts.overloaded ? "bad" : "ok"} onClick={() => setOpen("overloaded")} active={open === "overloaded"} />
            <Metric label="Normal" value={d.counts.normal} tone="ok" onClick={() => setOpen("normal")} active={open === "normal"} />
            <Metric label="Underloaded" value={d.counts.underloaded} tone={d.counts.underloaded ? "warn" : undefined} onClick={() => setOpen("underloaded")} active={open === "underloaded"} />
          </div>
          <SimpleTable rows={d.bands[open]} empty="Nobody in this band." columns={[
            { key: "full_name", label: "Teacher" }, { key: "faculty_type", label: "Type" }, { key: "department", label: "Department" },
            { key: "current_hours", label: "Hours" }, { key: "max_hours", label: "Limit" }, { key: "term", label: "Semester" },
            { key: "classes", label: "Classes" },
            { key: "act", label: "", render: (r) => (r.overload_hours > 0 && onOpenResolver
              ? <button onClick={() => onOpenResolver(r.faculty_id)} style={{ background: "#b91c1c", color: "#ffffff", border: "none", borderRadius: 5, padding: "3px 9px", fontSize: 12, cursor: "pointer" }}>Resolve overload</button>
              : null) }]} />
          <p style={{ fontSize: 12, color: C.muted, margin: "8px 0 0" }}>{d.note}</p>
        </>
      )}
    </InsightCard>
  );
}


/* ---------------------------------------------------------------- Stage 3: Registrar (Gen Ed; every college, read-only) */
export function GenEdCoverageCard({ filters = {} }) {
  const [d, error, retry] = useInsight("/analytics/registrar/gened-coverage/", fq(filters));
  return (
    <InsightCard title="Gen Ed coverage and sharing" error={error} loading={!d && !error} onRetry={retry}
      subtitle="Per Gen Ed subject (the same code, units and title count as one requirement across programs).">
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label="Sections that take Gen Ed subjects" value={d.totals.sections} />
            <Metric label="Sections not fully placed" value={d.totals.unplaced_sections} tone={d.totals.unplaced_sections ? "bad" : "ok"} />
            <Metric label="Sections in a shared class" value={d.totals.shared_sections} />
            <Metric label="Classes saved by sharing" value={d.totals.classes_saved} tone="ok" />
            <Metric label="Teaching hours / week saved" value={d.totals.teaching_hours_saved} tone="ok" />
          </div>
          <SimpleTable rows={d.subjects} empty="No Gen Ed subjects in scope yet." columns={[
            { key: "code", label: "Subject", render: (r) => `${r.code} ${r.title}`, csv: (r) => `${r.code} ${r.title}` }, { key: "semester", label: "Semester" },
            { key: "programs", label: "Programs", render: (r) => r.programs.length, csv: (r) => r.programs.join("; ") },
            { key: "sections", label: "Sections" }, { key: "placed_sections", label: "Placed" },
            { key: "unplaced_sections", label: "Not placed", render: (r) => <span style={{ color: r.unplaced_sections ? C.bad : "#374151" }}>{r.unplaced_sections}</span> },
            { key: "shared_sections", label: "Shared" }, { key: "classes_held", label: "Classes held" },
            { key: "classes_saved", label: "Classes saved" }, { key: "teaching_hours_saved", label: "Hours saved / week" }]} />
          <p style={{ fontSize: 12, color: C.muted, margin: "8px 0 0" }}>{d.note}</p>
        </>
      )}
    </InsightCard>
  );
}

/* Day x hour grid (the existing PatternHeatmap only has Morning / Afternoon / Evening, so this is a separate small component). */
export function HourHeatmap({ days, hours, cells, total }) {
  if (!days.length || !hours.length) return <p style={{ color: C.muted, fontSize: 13 }}>No time slots yet.</p>;
  const at = {};
  cells.forEach((c) => { at[`${c.day}|${c.hour}`] = c; });
  const hh = (h) => `${((h + 11) % 12) + 1}${h < 12 ? "a" : "p"}`;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", boxShadow: "none", border: "none", width: "auto", marginTop: 6, background: "transparent" }}>
        <thead style={{ background: "transparent" }}>
          <tr><th style={{ padding: "4px 6px", background: "transparent" }} />{hours.map((h) => <th key={h} style={{ padding: "4px 6px", fontSize: 12, color: C.muted, background: "transparent", fontWeight: 600 }}>{hh(h)}</th>)}</tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d} style={{ background: "transparent" }}>
              <td style={{ padding: "3px 8px 3px 0", fontSize: 12, color: "#374151", border: "none", fontWeight: 600 }}>{d}</td>
              {hours.map((h) => {
                const c = at[`${d}|${h}`] || { rooms_busy: 0, pct: 0 };
                return (
                  <td key={h} title={`${d} ${hh(h)}: ${c.rooms_busy} of ${total} rooms booked (${c.pct}%)`}
                    style={{ width: 34, height: 26, padding: 0, border: "2px solid #ffffff", textAlign: "center", fontSize: 12,
                      background: c.pct ? `rgba(3, 51, 102, ${0.12 + 0.88 * (c.pct / 100)})` : "#f3f4f6", color: c.pct > 55 ? "#ffffff" : "#374151" }}>
                    {c.pct ? `${c.pct}` : ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RoomHeatmapCard({ filters = {} }) {
  const [type, setType] = useState("");
  const [d, error, retry] = useInsight("/analytics/room-heatmap/", { ...fq(filters), ...(type ? { room_type: type } : {}) });
  return (
    <InsightCard title="Room utilization by day and hour" error={error} loading={!d && !error} onRetry={retry}
      subtitle={`% of rooms booked in each hour${d && d.semester ? ` · ${d.semester}` : ""}${d ? ` · ${d.rooms} room${d.rooms === 1 ? "" : "s"}` : ""}. Darker = busier.`}
      right={<select value={type} onChange={(e) => setType(e.target.value)} aria-label="Room type" style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13, background: "#ffffff", color: "#111827" }}>
        <option value="">Every room type</option><option value="lecture">Lecture rooms</option><option value="lab">Laboratories</option><option value="gym">Gym</option></select>}>
      {d && (
        <>
          <HourHeatmap days={d.days} hours={d.hours} cells={d.cells} total={d.rooms} />
          <p style={{ fontSize: 13, color: C.muted, margin: "8px 0 0" }}>
            {d.peak ? `Busiest: ${d.peak.day} ${formatTime(d.peak.hour * 60)} with ${d.peak.rooms_busy} of ${d.rooms} rooms (${d.peak.pct}%).` : "No classes booked yet."}
          </p>
        </>
      )}
    </InsightCard>
  );
}

export function DependenciesCard({ filters = {} }) {
  const [d, error, retry] = useInsight("/analytics/registrar/dependencies/", fq(filters));
  return (
    <InsightCard title="Cross-college dependencies" error={error} loading={!d && !error} onRetry={retry}
      subtitle="Major classes that Gen Ed classes leave no room for, and shared Gen Ed classes waiting for your confirmation.">
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label="Major classes blocked by Gen Ed" value={d.blocked_by_gen_ed.length} tone={d.blocked_by_gen_ed.length ? "bad" : "ok"} />
            <Metric label="Shared classes waiting for confirmation" value={d.shared_groups_waiting.length} tone={d.shared_groups_waiting.length ? "warn" : "ok"} />
          </div>
          <h4 style={{ margin: "12px 0 2px", fontSize: 14, color: "#111827" }}>Major classes blocked by Gen Ed</h4>
          <SimpleTable rows={d.blocked_by_gen_ed} empty="No major class is blocked by Gen Ed classes." columns={[
            { key: "section", label: "Section" }, { key: "department", label: "College" }, { key: "subject", label: "Major subject" },
            { key: "needs_block_hours", label: "Needs (h, unbroken)" }, { key: "gen_ed_hours_in_section", label: "Gen Ed h in section" },
            { key: "gen_ed_classes", label: "Gen Ed classes", render: (r) => r.gen_ed_classes.join(", ") }]} />
          <h4 style={{ margin: "12px 0 2px", fontSize: 14, color: "#111827" }}>Shared classes waiting for the Registrar</h4>
          <SimpleTable rows={d.shared_groups_waiting} empty="Nothing waiting." columns={[
            { key: "code", label: "Subject", render: (r) => `${r.code} ${r.title}`, csv: (r) => `${r.code} ${r.title}` }, { key: "year_level", label: "Year" }, { key: "semester", label: "Semester" },
            { key: "programs", label: "Programs", render: (r) => r.programs.join(" + ") }, { key: "requested_by", label: "Requested by" }]} />
          <p style={{ fontSize: 12, color: C.muted, margin: "8px 0 0" }}>{d.note}</p>
        </>
      )}
    </InsightCard>
  );
}

export function CapacityCard({ filters = {} }) {
  const [d, error, retry] = useInsight("/analytics/capacity/", fq(filters));
  const [open, setOpen] = useState("over");
  const cols = [{ key: "subject", label: "Class" }, { key: "kind", label: "Kind" }, { key: "room", label: "Room" },
    { key: "students", label: "Students" }, { key: "seats", label: "Seats" }, { key: "fill_pct", label: "% full" },
    { key: "sections", label: "Sections", render: (r) => `${r.sections.join(", ")}${r.shared ? " (shared)" : ""}` }];
  return (
    <InsightCard title="Capacity vs enrollment" error={error} loading={!d && !error} onRetry={retry}
      subtitle={`Each class against its room's seats${d && d.semester ? ` · ${d.semester}` : ""}. A shared class adds up all its sections.`}>
      {d && (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Metric label={`Over capacity (of ${d.classes} classes)`} value={d.over_capacity.length} tone={d.over_capacity.length ? "bad" : "ok"} onClick={() => setOpen("over")} active={open === "over"} />
            <Metric label="Under 50% full" value={d.under_half.length} tone={d.under_half.length ? "warn" : "ok"} onClick={() => setOpen("under")} active={open === "under"} />
            <Metric label="Rooms with no recorded capacity" value={d.rooms_without_capacity} />
          </div>
          {open === "over" && <SimpleTable rows={d.over_capacity} columns={cols} empty="No class has more students than seats." />}
          {open === "under" && <SimpleTable rows={d.under_half} columns={cols} empty="No class is under half full." />}
          <p style={{ fontSize: 12, color: C.muted, margin: "8px 0 0" }}>{d.note}</p>
        </>
      )}
    </InsightCard>
  );
}


/* ---------------------------------------------------------------- Stage 4: SHS / JHS principals (own level only) */
const t12 = (hhmm) => formatTime(hhmm);

export function FeasibilityCard({ level, params = {} }) {
  const [d, error, retry] = useInsight("/analytics/basic-ed/feasibility/", { level, ...params });
  return (
    <InsightCard title="Daily timetable feasibility" error={error} loading={!d && !error} onRetry={retry}
      subtitle="How many class periods fit in each grade's school day after the break(s), using the same rule as the timetable generator.">
      {d && (!d.configured ? <p style={{ color: C.muted, fontSize: 13 }}>{d.note}</p> : (
        <>
          <SimpleTable rows={d.grades} empty="No grade levels have a daily time window yet." columns={[
            { key: "grade", label: "Grade" },
            { key: "day", label: "School day", render: (r) => `${t12(r.start)} – ${t12(r.end)}`, csv: (r) => `${r.start}-${r.end}` },
            { key: "breaks", label: "Breaks", render: (r) => (r.breaks.length ? r.breaks.map((b) => `${b.name} ${t12(b.start)}–${t12(b.end)}`).join("; ") : "—"),
              csv: (r) => r.breaks.map((b) => `${b.name} ${b.start}-${b.end}`).join("; ") },
            { key: "periods_per_day", label: "Periods / day", render: (r) => `${r.periods_per_day} × ${r.period_minutes} min` },
            { key: "unused_minutes", label: "Unused min / day" },
            { key: "need", label: "Needed / available per week", csv: (r) => `${r.max_needed_per_week} / ${r.periods_per_week}`, render: (r) => `${r.max_needed_per_week} / ${r.periods_per_week}${r.max_needed_section ? ` (${r.max_needed_section})` : ""}` },
            { key: "fits", label: "Fits?", render: (r) => (
              <span>
                <strong style={{ color: r.fits ? C.ok : C.bad }}>{r.fits ? "Yes" : `No: ${r.max_needed_per_week - r.periods_per_week} short`}</strong>
                {r.missing_breaks.length > 0 && <div style={{ color: C.warn, fontSize: 12 }}>Missing: {r.missing_breaks.join(", ")}</div>}
              </span>) }]} />
          <p style={{ fontSize: 12, color: C.muted, margin: "8px 0 0" }}>{d.note}{d.period ? ` Needed periods use grading period ${d.period}.` : ""}</p>
        </>
      ))}
    </InsightCard>
  );
}

export function CompletenessCard({ level, params = {} }) {
  const [d, error, retry] = useInsight("/analytics/basic-ed/completeness/", { level, ...params });
  return (
    <InsightCard title="Completeness per grade and strand" error={error} loading={!d && !error} onRetry={retry}
      subtitle="Subjects with no qualified teacher, subjects not fully in the latest timetable, and periods with no teacher.">
      {d && (
        <>
          <SimpleTable rows={d.groups} empty="No sections yet." columns={[
            { key: "grade", label: "Grade", render: (r) => `${r.grade}${r.strand ? ` · ${r.strand}` : ""}` }, { key: "strand", label: "Strand", csv: (r) => r.strand },
            { key: "sections", label: "Sections", render: (r) => r.sections.length, csv: (r) => r.sections.join("; ") },
            { key: "subjects", label: "Subjects" },
            { key: "no_teacher_subjects", label: "No qualified teacher", render: (r) => (r.no_teacher_subjects.length
              ? <span style={{ color: C.bad }}>{r.no_teacher_subjects.join("; ")}</span> : "—") },
            { key: "not_scheduled", label: "Not fully scheduled", csv: (r) => r.not_scheduled.map((x) => `${x.section}: ${x.subject} ${x.scheduled}/${x.needed}`).join("; "), render: (r) => (!r.timetabled ? <em style={{ color: C.muted }}>no timetable yet</em>
              : r.not_scheduled.length ? <span style={{ color: C.bad }}>{r.not_scheduled.map((x) => `${x.section}: ${x.subject} ${x.scheduled}/${x.needed}`).join("; ")}</span> : "—") },
            { key: "periods_without_teacher", label: "Periods w/o teacher", render: (r) => <span style={{ color: r.periods_without_teacher ? C.bad : "#374151" }}>{r.periods_without_teacher}</span> },
            { key: "complete", label: "Status", render: (r) => <strong style={{ color: r.complete ? C.ok : C.warn }}>{r.complete ? "Complete" : "Needs work"}</strong> }]} />
          <p style={{ fontSize: 12, color: C.muted, margin: "8px 0 0" }}>{d.note}{d.period ? ` Grading period ${d.period}.` : ""}</p>
        </>
      )}
    </InsightCard>
  );
}

export function AbsenceImpactCard({ level }) {
  const [d, error, retry] = useInsight("/analytics/basic-ed/absences/", { level });
  return (
    <InsightCard title="Absence impact" error={error} loading={!d && !error} onRetry={retry}>
      {d && (d.recorded ? <p>{d.uncovered_classes} classes uncovered.</p> : (
        <div style={{ background: "#fffbeb", border: "1px solid #fde68a", color: "#7a4b00", borderRadius: 6, padding: "8px 12px", fontSize: 13 }}>
          <strong>Not recorded.</strong> {d.note}
        </div>
      ))}
    </InsightCard>
  );
}


/* ---------------------------------------------------------------- Stage 5: filters and trend */
const selStyle = { padding: "5px 8px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13, background: "#ffffff", color: "#111827" };

/* School year / semester / college / program for the college insight cards. The choices come from the server and are limited to what
   this user may see (a Dean: own college only). */
export function InsightFilters({ value, onChange, showCollege = true }) {
  const [opts] = useInsight("/analytics/filters/");
  const set = (k, v) => onChange({ ...value, [k]: v, ...(k === "department" ? { program_id: "" } : {}) });
  const programs = (opts?.programs || []).filter((p) => !value.department || p.department === value.department);
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <select value={value.school_year || ""} onChange={(e) => set("school_year", e.target.value)} aria-label="School year" style={selStyle}>
        <option value="">All school years</option>
        {(opts?.school_years || []).map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
      <select value={value.semester || ""} onChange={(e) => set("semester", e.target.value)} aria-label="Semester" style={selStyle}>
        <option value="">All semesters</option>
        {(opts?.semesters?.length ? opts.semesters : ["1st Sem", "2nd Sem"]).map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      {showCollege && (opts?.departments || []).length > 1 && (
        <select value={value.department || ""} onChange={(e) => set("department", e.target.value)} aria-label="College" style={selStyle}>
          <option value="">All colleges</option>
          {opts.departments.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
      )}
      <select value={value.program_id || ""} onChange={(e) => set("program_id", e.target.value)} aria-label="Program" style={selStyle}>
        <option value="">All programs</option>
        {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      {Object.values(value).some((v) => v) && (
        <button type="button" onClick={() => onChange({})} style={linkBtn}>Clear filters</button>
      )}
    </div>
  );
}

/* SHS / JHS: efficiency and conflicts of every stored generation run (replaced versions included), oldest first. */
export function RunTrendCard({ level, year }) {
  const [d, error, retry] = useInsight("/analytics/basic-ed/run-trend/", { level, ...(year ? { year } : {}) });
  const runs = d ? d.runs.filter((r) => r.efficiency_pct !== null) : [];
  const W = 640, H = 150, pad = 28;
  const x = (i) => pad + (runs.length > 1 ? (i * (W - 2 * pad)) / (runs.length - 1) : (W - 2 * pad) / 2);
  const maxC = Math.max(1, ...runs.map((r) => r.conflicts || 0));
  return (
    <InsightCard title="Trend per generation run" error={error} loading={!d && !error} onRetry={retry}
      subtitle={`Every timetable generated${d && d.academic_year ? ` in ${d.academic_year}` : ""}, oldest first. Efficiency = periods placed / (placed + not placed). Conflicts = validation errors of that run.`}>
      {d && (
        <>
          {runs.length > 0 ? (
            <div style={{ overflowX: "auto" }}>
              <svg width={W} height={H} role="img" aria-label="Efficiency and conflicts per run" style={{ maxWidth: "100%" }}>
                <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="#d1d5db" />
                <text x={4} y={pad - 8} fontSize="10" fill="#6b7280">100%</text>
                <text x={10} y={H - pad} fontSize="10" fill="#6b7280">0%</text>
                {runs.map((r, i) => {
                  const h = ((r.conflicts || 0) / maxC) * (H - 2 * pad) * 0.5;
                  return <rect key={`c${r.id}`} x={x(i) - 6} y={H - pad - h} width={12} height={h} fill="#fca5a5"><title>{`Run ${r.id}: ${r.conflicts} conflicts`}</title></rect>;
                })}
                <polyline fill="none" stroke="#003366" strokeWidth="2"
                  points={runs.map((r, i) => `${x(i)},${H - pad - (r.efficiency_pct / 100) * (H - 2 * pad)}`).join(" ")} />
                {runs.map((r, i) => (
                  <circle key={r.id} cx={x(i)} cy={H - pad - (r.efficiency_pct / 100) * (H - 2 * pad)} r="3.5" fill="#003366">
                    <title>{`Grade ${r.grade ?? "all"}, period ${r.period}, v${r.version}: ${r.efficiency_pct}% placed, ${r.conflicts ?? "?"} conflicts`}</title>
                  </circle>
                ))}
              </svg>
              <div style={{ fontSize: 12, color: C.muted }}>
                <span style={{ color: "#003366", fontWeight: 600 }}>— efficiency</span> · <span style={{ color: "#dc2626", fontWeight: 600 }}>▮ conflicts</span>
              </div>
            </div>
          ) : <p style={{ color: C.muted, fontSize: 13 }}>No generation runs with stored counts yet.</p>}
          <SimpleTable rows={d.runs} empty="No timetables generated yet." columns={[
            { key: "when", label: "When", render: (r) => <span style={{ whiteSpace: "nowrap" }}>{when(r.when)}</span>, csv: (r) => r.when },
            { key: "grade", label: "Grade" }, { key: "period", label: "Period" }, { key: "version", label: "Version" }, { key: "status", label: "Status" },
            { key: "by", label: "By" }, { key: "placed", label: "Placed", render: (r) => r.placed ?? "not stored" },
            { key: "unresolved", label: "Not placed", render: (r) => r.unresolved ?? "not stored" },
            { key: "efficiency_pct", label: "Efficiency %", render: (r) => (r.efficiency_pct === null ? "—" : `${r.efficiency_pct}%`) },
            { key: "conflicts", label: "Conflicts", render: (r) => r.conflicts ?? "—" }]} />
        </>
      )}
    </InsightCard>
  );
}

export function BasicEdInsights({ level }) {
  const [year, setYear] = useState("");
  const [period, setPeriod] = useState("");
  const [meta] = useInsight("/analytics/basic-ed/run-trend/", { level });
  const params = { ...(year ? { year } : {}), ...(period ? { period } : {}) };
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <h3 style={{ margin: 0, color: "#003366" }}>Insights — {level}</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <select value={year} onChange={(e) => setYear(e.target.value)} aria-label="School year" style={selStyle}>
            <option value="">Active school year</option>
            {(meta?.years || []).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Grading period" style={selStyle}>
            <option value="">Latest timetable's period</option>
            {[1, 2, 3].map((n) => <option key={n} value={n}>{level === "JHS" ? `Term ${n}` : `Term / semester ${n}`}</option>)}
          </select>
        </div>
      </div>
      <FeasibilityCard level={level} params={params} />
      <CompletenessCard level={level} params={params} />
      <AbsenceImpactCard level={level} />
      <RunTrendCard level={level} year={year} />
    </div>
  );
}
