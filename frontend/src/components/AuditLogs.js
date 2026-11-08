import CustomSelect from "./CustomSelect";
import CustomDatePicker from "./CustomDatePicker";
import React, { useCallback, useEffect, useState } from "react";
import API from "../services/api";
import { formatDateTime } from "../utils/formatDateTime";

/* IT Admin: audit logs -- who did what, when, to which record, the values before and after, and from which IP address.
   Read only: the server has no way to change or delete a log (GET /api/audit/logs/). */
const ACTION_WORD = { create: "Created", update: "Changed", delete: "Deleted", login: "Signed in", generate: "Generated" };
const btn = { background: "white", color: "#374151", border: "1px solid #d1d5db", borderRadius: 4, padding: "5px 12px", fontSize: 13, cursor: "pointer" };
const field = { fontSize: 13, padding: "5px 8px", border: "1px solid #d1d5db", borderRadius: 4, background: "white", color: "#111827" };
const EMPTY = { user: "", action: "", date_from: "", date_to: "", q: "" };

function show(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object" && !Array.isArray(v) && "name" in v) return v.name || `#${v.id}`;
  if (Array.isArray(v)) return v.length > 6 ? `${v.slice(0, 6).map(show).join("; ")} … (+${v.length - 6} more)` : v.map(show).join("; ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function Changes({ log }) {
  const oldV = log.old_values || {}, newV = log.new_values || {};
  const keys = [...new Set([...Object.keys(oldV), ...Object.keys(newV)])];
  if (!keys.length) return <span style={{ color: "#6b7280" }}>No values recorded.</span>;
  return (
    <table className="sched-compact" style={{ marginTop: 6 }}>
      <thead><tr><th style={{ width: 160 }}>Field</th><th>Before</th><th>After</th></tr></thead>
      <tbody>
        {keys.map((k) => (
          <tr key={k}><td>{k.replace(/_/g, " ")}</td><td style={{ overflowWrap: "anywhere" }}>{show(oldV[k])}</td>
            <td style={{ overflowWrap: "anywhere" }}>{show(newV[k])}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

/* level: "SHS" / "JHS" for that school level's admin view (its records and its own principal / teachers); none = everything. */
export default function AuditLogs({ level = "" }) {
  const [form, setForm] = useState(EMPTY);
  const [applied, setApplied] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    setError("");
    const params = Object.fromEntries(Object.entries({ ...applied, ...(level ? { level } : {}), page }).filter(([, v]) => v !== "" && v !== null));
    API.get("/audit/logs/", { params })
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "The audit logs could not be loaded."));
  }, [applied, page, level]);
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const apply = (e) => { e.preventDefault(); setPage(1); setOpen(null); setApplied(form); };
  const reset = () => { setForm(EMPTY); setApplied(EMPTY); setPage(1); setOpen(null); };

  return (
    <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "16px 20px" }}>
      <p style={{ margin: "0 0 12px", fontSize: 13, color: "#4b5563" }}>
        {level ? `Every change to ${level} records and everything done by ${level} accounts (principal and teachers)` :
          "Every change to the school's data, every sign-in and every Generate"}, with who did it, when, the values before and after, and the
        IP address. Logs cannot be changed or deleted by anyone.
      </p>
      <form onSubmit={apply} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end", marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: "#374151", display: "flex", flexDirection: "column", gap: 3 }}>User
          <CustomSelect value={form.user} onChange={(e) => set("user", e.target.value)} style={{ ...field, minWidth: 180 }}>
            <option value="">All users</option>
            <option value="system">System (no signed-in user)</option>
            {(data?.users || []).map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
          </CustomSelect>
        </label>
        <label style={{ fontSize: 12, color: "#374151", display: "flex", flexDirection: "column", gap: 3 }}>Action
          <CustomSelect value={form.action} onChange={(e) => set("action", e.target.value)} style={field}>
            <option value="">All actions</option>
            {(data?.actions || []).map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </CustomSelect>
        </label>
        <label style={{ fontSize: 12, color: "#374151", display: "flex", flexDirection: "column", gap: 3 }}>From
          <CustomDatePicker value={form.date_from} onChange={(e) => set("date_from", e.target.value)} style={field} aria-label="From date" />
        </label>
        <label style={{ fontSize: 12, color: "#374151", display: "flex", flexDirection: "column", gap: 3 }}>To
          <CustomDatePicker value={form.date_to} onChange={(e) => set("date_to", e.target.value)} style={field} aria-label="To date" />
        </label>
        <label style={{ fontSize: 12, color: "#374151", display: "flex", flexDirection: "column", gap: 3, flex: "1 1 160px" }}>Record contains
          <input value={form.q} onChange={(e) => set("q", e.target.value)} placeholder="e.g. CS101, CS1, a name" style={field} />
        </label>
        <button type="submit" style={{ ...btn, background: "#003366", color: "white", borderColor: "#003366" }}>Apply</button>
        <button type="button" onClick={reset} style={btn}>Reset</button>
      </form>
      {error && <p role="alert" style={{ color: "#b91c1c", fontSize: 13 }}>{error}</p>}
      {!data && !error && <p style={{ fontSize: 13, color: "#6b7280" }}>Loading…</p>}
      {data && (
        <>
          <div style={{ fontSize: 13, color: "#4b5563", marginBottom: 6 }}>{data.count} log entr{data.count === 1 ? "y" : "ies"}</div>
          <div style={{ overflowX: "auto" }}>
            <table className="sched-compact">
              <thead><tr><th style={{ width: 150 }}>When</th><th style={{ width: 150 }}>Who</th><th style={{ width: 90 }}>Action</th>
                <th>Record</th><th style={{ width: 120 }}>IP address</th><th style={{ width: 90 }}></th></tr></thead>
              <tbody>
                {data.results.length === 0 && <tr><td colSpan={6} style={{ color: "#6b7280" }}>No log entries match these filters.</td></tr>}
                {data.results.map((x) => (
                  <React.Fragment key={x.id}>
                    <tr>
                      <td style={{ whiteSpace: "nowrap" }}>{formatDateTime(x.timestamp)}</td>
                      <td>{x.user}</td>
                      <td>{ACTION_WORD[x.action] || x.action}</td>
                      <td style={{ overflowWrap: "anywhere" }}><strong style={{ fontWeight: 600 }}>{x.entity}{x.entity_id ? ` #${x.entity_id}` : ""}</strong>
                        {x.summary && <div style={{ color: "#4b5563" }}>{x.summary}</div>}</td>
                      <td>{x.ip_address || "—"}</td>
                      <td><button type="button" style={btn} aria-expanded={open === x.id} onClick={() => setOpen(open === x.id ? null : x.id)}>
                        {open === x.id ? "Hide" : "Details"}</button></td>
                    </tr>
                    {open === x.id && <tr><td colSpan={6} style={{ background: "#f9fafb" }}><Changes log={x} /></td></tr>}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", marginTop: 10, fontSize: 13 }}>
            <button type="button" style={btn} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
            <span>Page {data.page} of {data.pages}</span>
            <button type="button" style={btn} disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        </>
      )}
    </div>
  );
}
