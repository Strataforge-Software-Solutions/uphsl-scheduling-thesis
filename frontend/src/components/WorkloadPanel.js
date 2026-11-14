import CustomSelect from "./CustomSelect";
import React, { useState, useEffect, useCallback } from "react";
import API from "../services/api";
import Badge from "./Badge";
import { ResolverWindow, onWorkloadChanged } from "./OverloadResolver";

/* Faculty workload monitoring: current vs. permitted weekly teaching hours for Full-time and
   Part-time faculty, overload warnings, replacement ideas, and (for authorized users) the limits. */

const TYPE_LABEL = { full_time: "Full-time", part_time: "Part-time", dean: "Dean" };
const POLICY_LABEL = {
  override: "Warn, and allow an authorized override (written to the audit log)",
  strict: "Strict: never allow an overloaded assignment",
};
const ANALYTICS_POLICY_LABEL = {
  override: "Warn; allow authorized override",
  strict: "Block overloaded assignments",
};

const fmt = (h) => (Number.isInteger(h) ? String(h) : String(Math.round(h * 100) / 100));

const resolveBtn = { background: "#003366", color: "white", border: "none", borderRadius: "6px", padding: "6px 12px", fontSize: "13px", fontWeight: 600, cursor: "pointer" };

/** Warning cards, used after a generate run and after a blocked manual assignment. */
export function WorkloadWarningList({ warnings, title = "Faculty workload warnings", canResolve = false }) {
  const [open, setOpen] = useState(null);
  if (!warnings || warnings.length === 0) return null;
  return (
    <div style={{ background: "#fdecea", border: "1px solid #f3b3ac", borderRadius: 6, padding: "12px 14px", margin: "12px 0", maxWidth: "820px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center", justifyContent: "space-between" }}>
        <strong style={{ color: "#b91c1c" }}>{title} ({warnings.length})</strong>
        {canResolve && warnings.length > 1 && <button onClick={() => setOpen(0)} style={resolveBtn}>View Suggestions (all)</button>}
      </div>
      {open !== null && <ResolverWindow focusId={open || null} onClose={() => setOpen(null)} />}
      {warnings.map((w, i) => (
        <div key={i} style={{ marginTop: "10px", fontSize: "13px", color: "#7a1b14" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontWeight: 600, flex: "1 1 360px" }}>{w.message}</div>
            {canResolve && w.faculty_id && <button onClick={() => setOpen(w.faculty_id)} style={resolveBtn}>View Suggestions</button>}
          </div>
          {w.conflicting_assignment && (
            <div style={{ fontSize: "13px", color: "#8a4b44" }}>Assignment that pushes them over: {w.conflicting_assignment}</div>
          )}
          <ReplacementList suggestions={w.replacement_suggestions} />
        </div>
      ))}
    </div>
  );
}

export function ReplacementList({ suggestions }) {
  if (!suggestions) return null;
  if (suggestions.length === 0) {
    return <div className="workload-replacements-empty">No replacement faculty is available for this class within their weekly limit.</div>;
  }
  return (
    <section className="workload-replacements" aria-label="Suggested replacement faculty">
      <div className="workload-replacements-heading">
        <strong>Suggested replacements</strong>
        <span>Qualified, available at this time, and within weekly limit</span>
      </div>
      <ul className="workload-replacements-list">
        {suggestions.map((s) => (
          <li className="workload-replacement-card" key={s.faculty_id}>
            <div className="workload-replacement-person">
              <strong>{s.full_name}</strong>
              <span>{TYPE_LABEL[s.faculty_type] || s.faculty_type}</span>
              {s.same_department && <span className="workload-replacement-department">Same college</span>}
            </div>
            <div className="workload-replacement-metrics">
              <span><strong>{fmt(s.current_hours)} / {fmt(s.max_hours)} h</strong><small>Current load</small></span>
              <span className="workload-replacement-spare"><strong>{fmt(s.remaining_after)} h</strong><small>Spare after class</small></span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Bar({ value, max, over }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div style={{ background: "#e8eef7", borderRadius: 4, height: "8px", minWidth: "90px", overflow: "hidden" }}>
      <div className="motion-meter-fill" style={{ width: `${pct}%`, height: "100%", background: over ? "#c0392b" : pct >= 90 ? "#e0a72e" : "#2e7d52" }} />
    </div>
  );
}

function LimitsEditor({ limits, onSaved, analyticsStyle = false }) {
  const [form, setForm] = useState(limits);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  useEffect(() => setForm(limits), [limits]);
  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      await API.patch("/engine/scheduling-config/", {
        max_weekly_hours_full_time: Number(form.full_time),
        max_weekly_hours_part_time: Number(form.part_time),
        workload_policy: form.policy,
        reserve_lunch_gap: !!form.reserve_lunch_gap,
      });
      setMsg({ ok: true, text: "Workload limits saved." });
      onSaved();
    } catch (e) {
      const d = e.response?.data;
      setMsg({ ok: false, text: d?.detail || (d && Object.values(d).flat().join(" ")) || "Could not save." });
    } finally { setSaving(false); }
  };
  const inp = { padding: "7px", borderRadius: "6px", border: "1px solid #d1d5db", width: "90px" };
  return (
    <div className={analyticsStyle ? "analytics-limits-editor" : undefined} style={analyticsStyle ? undefined : { background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 14px", marginBottom: "14px" }}>
      <div className={analyticsStyle ? "analytics-limits-title" : undefined} style={analyticsStyle ? undefined : { fontWeight: 600, color: "#003366", marginBottom: "8px", fontSize: "14px" }}>Workload limits (hours per week)</div>
      <div className={`workload-limits-row${analyticsStyle ? " analytics-workload-limits-row" : ""}`}>
        <label className="workload-limit-field" style={{ fontSize: "13px" }}>Full-time
          <input type="number" min="1" max="80" style={inp} value={form.full_time} onChange={(e) => setForm({ ...form, full_time: e.target.value })} /></label>
        <label className="workload-limit-field" style={{ fontSize: "13px" }}>Part-time
          <input type="number" min="1" max="80" style={inp} value={form.part_time} onChange={(e) => setForm({ ...form, part_time: e.target.value })} /></label>
        <label className="workload-policy-field" style={{ fontSize: "13px" }}>When a limit is exceeded
          <CustomSelect className={analyticsStyle ? "analytics-workload-policy-select" : ""} value={form.policy} onChange={(e) => setForm({ ...form, policy: e.target.value })} style={{ padding: "7px", width: "280px", maxWidth: "100%" }}>
            {Object.entries(analyticsStyle ? ANALYTICS_POLICY_LABEL : POLICY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </CustomSelect></label>
        <button onClick={save} disabled={saving} style={{ background: "#003366", color: "white", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: 600, cursor: "pointer" }}>
          {saving ? "Saving…" : "Save limits"}
        </button>
      </div>
      <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 12, fontSize: 13, color: "#111827", cursor: "pointer" }}>
        <input type="checkbox" checked={!!form.reserve_lunch_gap} onChange={(e) => setForm({ ...form, reserve_lunch_gap: e.target.checked })} style={{ marginTop: 2 }} />
        <span><strong>Reserve lunch gap (optional)</strong> — when generating, prefer leaving each section and professor at least 1 free hour
          between 10:30 AM and 2:30 PM per day. Never skips a class: where no gap is possible the class is still placed and a warning is shown.
          Lunch is otherwise not a fixed period; 12:00-1:00 PM is a normal class time. Saved with "Save limits".</span>
      </label>
      {msg && <div style={{ marginTop: "8px", fontSize: "13px", color: msg.ok ? "#1e7a45" : "#b91c1c" }}>{msg.text}</div>}
    </div>
  );
}

function ClassDetail({ facultyId, canSuggest }) {
  const [detail, setDetail] = useState(null);
  const [sugg, setSugg] = useState({});
  const [failed, setFailed] = useState("");
  useEffect(() => {
    API.get(`/engine/workload/${facultyId}/`).then((r) => setDetail(r.data))
      .catch((e) => setFailed(e.response?.data?.detail || "Could not load this teacher's classes."));
  }, [facultyId]);
  if (failed) return <div style={{ padding: "10px 16px", fontSize: "13px", color: "#b91c1c" }}>{failed}</div>;
  if (!detail) return <div style={{ padding: "10px 16px", fontSize: "13px" }}>Loading classes…</div>;
  const findReplacement = async (c) => {
    const key = `${c.subject_id}-${c.section_id}`;
    setSugg((s) => ({ ...s, [key]: { loading: true } }));
    try {
      const r = await API.get("/engine/workload/replacements/", { params: { faculty_id: facultyId, subject_id: c.subject_id, section_id: c.section_id } });
      setSugg((s) => ({ ...s, [key]: { list: r.data.suggestions } }));
    } catch (e) {
      setSugg((s) => ({ ...s, [key]: { error: e.response?.data?.detail || "Could not look up replacements." } }));
    }
  };
  return (
    <div style={{ padding: "12px 18px" }}>
      {detail.warning && <div style={{ color: "#b91c1c", fontWeight: 600, fontSize: "13px", marginBottom: "8px" }}>{detail.warning}</div>}
      {detail.class_list.length === 0 ? <div style={{ fontSize: "13px", color: "#6b7280" }}>No classes assigned in {detail.term || "any semester"}.</div> : (
        <table>
          <thead><tr><th>Class ({detail.term})</th><th>Section(s)</th><th>Hours / week</th>{canSuggest && <th></th>}</tr></thead>
          <tbody>
            {detail.class_list.map((c) => {
              const key = `${c.subject_id}-${c.section_id}`;
              const s = sugg[key];
              return (
                <React.Fragment key={key}>
                  <tr>
                    <td>{c.subject}</td><td>{c.sections.join(", ")}</td><td>{fmt(c.hours)}</td>
                    {canSuggest && (
                      <td><button onClick={() => findReplacement(c)} disabled={s?.loading}
                        style={{ background: "white", color: "#003366", border: "1px solid #d1d5db", borderRadius: "6px", padding: "4px 10px", fontSize: "12px", cursor: "pointer" }}>
                        {s?.loading ? "Looking…" : "Find replacement"}</button></td>
                    )}
                  </tr>
                  {s && !s.loading && (
                    <tr><td colSpan={4}>{s.error ? <span style={{ color: "#b91c1c", fontSize: "13px" }}>{s.error}</span> : <ReplacementList suggestions={s.list} />}</td></tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function WorkloadPanel({ canConfigure = false, canSuggest = false, refreshKey = 0, analyticsStyle = false }) {
  const [data, setData] = useState(null);
  const [resolveFor, setResolveFor] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const [onlyOver, setOnlyOver] = useState(false);

  const load = useCallback(() => {
    setError("");
    API.get("/engine/workload/").then((r) => setData(r.data)).catch((e) => setError(e.response?.data?.detail || "Could not load workloads."));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => onWorkloadChanged(load), [load]);

  if (error) return <p style={{ color: "#b91c1c" }}>{error}</p>;
  if (!data) return <p>Loading workloads…</p>;
  const rows = data.faculty.filter((r) => !onlyOver || r.overload_hours > 0);

  return (
    <div className={analyticsStyle ? "analytics-workload-card" : undefined} style={analyticsStyle ? undefined : { background: "white", borderRadius: 6, padding: "20px 24px", border: "1px solid #e5e7eb", boxShadow: "none", marginBottom: "24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
        <div>
          <h3 className={analyticsStyle ? "analytics-workload-title" : undefined} style={analyticsStyle ? undefined : { margin: 0, color: "#003366" }}>
            {analyticsStyle && <svg className="analytics-heading-icon" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8" cy="7" r="3" /><path d="M2.5 17c.5-2.7 2.3-4 5.5-4s5 1.3 5.5 4M14 5a2.5 2.5 0 0 1 0 4.8M14.5 13c1.7.4 2.7 1.7 3 4" /></svg>}
            Faculty Workload
          </h3>
          <p style={{ margin: "2px 0 0", fontSize: "13px", color: "#6b7280" }}>
            Teaching hours per week (shared classes counted once) against the limit for each classification:
            Full-time {data.limits.full_time} h · Part-time {data.limits.part_time} h.
            {data.overloaded > 0 ? ` ${data.overloaded} overloaded.` : " Nobody is overloaded."}
          </p>
        </div>
        <label className="overloaded-only-filter" style={{ fontSize: "13px" }}>
          <input type="checkbox" checked={onlyOver} onChange={(e) => setOnlyOver(e.target.checked)} /> Overloaded only
        </label>
      </div>

      {resolveFor && <ResolverWindow focusId={resolveFor} onClose={() => { setResolveFor(null); load(); }} />}
      {canConfigure && <LimitsEditor limits={data.limits} onSaved={load} analyticsStyle={analyticsStyle} />}

      <div style={{ overflowX: "auto", maxHeight: "460px", overflowY: "auto" }}>
        <table>
          <thead><tr><th>Faculty</th><th>Type</th><th>Semester</th><th>Hours / max</th><th style={{ minWidth: "110px" }}>Load</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} style={{ color: "#6b7280" }}>Nothing to show.</td></tr>}
            {rows.map((r) => (
              <React.Fragment key={r.faculty_id}>
                <tr onClick={() => setOpen(open === r.faculty_id ? null : r.faculty_id)} style={{ cursor: "pointer" }}>
                  <td style={{ fontWeight: 600 }}>{r.full_name}<div style={{ fontSize: "12px", color: "#6b7280", fontWeight: 400 }}>{r.school_id}</div></td>
                  <td>{TYPE_LABEL[r.faculty_type] || r.faculty_type}</td>
                  <td>{r.term || "—"}</td>
                  <td>{fmt(r.current_hours)} / {fmt(r.max_hours)}</td>
                  <td><Bar value={r.current_hours} max={r.max_hours} over={r.overload_hours > 0} /></td>
                  <td>{r.overload_hours > 0 ? <Badge tone="warning">Over by {fmt(r.overload_hours)} h</Badge>
                    : r.status === "at_limit" ? <Badge tone="neutral">At limit</Badge> : <Badge tone="success">OK</Badge>}</td>
                  <td style={{ color: "#003366", fontSize: "12px", fontWeight: 600 }}>{open === r.faculty_id ? "Hide ▲" : "Classes ▼"}</td>
                </tr>
                {r.overload_hours > 0 && (
                  <tr><td colSpan={7} style={{ color: "#b91c1c", fontSize: "13px", paddingTop: 0 }}>{r.warning}{canSuggest && <button onClick={() => setResolveFor(r.faculty_id)} style={{ ...resolveBtn, marginLeft: "10px" }}>View Suggestions</button>}</td></tr>
                )}
                {open === r.faculty_id && (
                  <tr><td colSpan={7} style={{ background: "#f7f9fc", padding: 0 }}><ClassDetail facultyId={r.faculty_id} canSuggest={canSuggest} /></td></tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default WorkloadPanel;
