import React, { useState, useEffect, useCallback } from "react";
import ModalPortal from "./ModalPortal";
import API from "../services/api";
import Badge from "./Badge";
import TeacherPicker from "./TeacherPicker";

/* Dean's overload resolver: a warning banner (View Suggestions) and a window that lists each overloaded teacher, the class to move,
   and the qualified / available / free faculty who can take it, with their degree, qualifications and workload. "Assign" changes the
   real schedule on the server, which re-checks qualification, availability, clashes and the weekly limit, and the page then refreshes
   its warnings and analytics (the "workload-changed" event). */

const TYPE_LABEL = { full_time: "Full-time", part_time: "Part-time", dean: "Dean" };
const fmt = (h) => (Number.isInteger(h) ? String(h) : String(Math.round(h * 100) / 100));
const EVENT = "workload-changed";
export const notifyWorkloadChanged = () => window.dispatchEvent(new Event(EVENT));
export const onWorkloadChanged = (fn) => { window.addEventListener(EVENT, fn); return () => window.removeEventListener(EVENT, fn); };

const btn = { background: "white", color: "#003366", border: "1px solid #d1d5db", borderRadius: "6px", padding: "6px 12px", fontSize: "13px", cursor: "pointer" };
const btnPrimary = { ...btn, background: "#003366", color: "white", border: "1px solid #003366", fontWeight: 600 };

function Bar({ value, max, after }) {
  const pct = (v) => (max > 0 ? Math.min(100, (v / max) * 100) : 0);
  return (
    <div style={{ background: "#e8eef7", borderRadius: 4, height: 8, overflow: "hidden", position: "relative", minWidth: 120 }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pct(after)}%`, background: "#9db8dc" }} />
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pct(value)}%`, background: "#2e7d52" }} />
    </div>
  );
}

function Candidate({ s, picked, onPick, hours }) {
  const spec = (s.specializations || []).join(", ");
  return (
    <label style={{ display: "flex", gap: 10, alignItems: "flex-start", border: `1px solid ${picked ? "#003366" : "#e5e7eb"}`, background: picked ? "#f2f7fd" : "white", borderRadius: 6, padding: "10px 12px", marginBottom: 8, cursor: "pointer" }}>
      <input type="radio" checked={picked} onChange={onPick} style={{ marginTop: 3 }} />
      <div style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <b>{s.full_name}</b>
          <Badge tone="neutral">{TYPE_LABEL[s.faculty_type] || s.faculty_type}</Badge>
          <Badge tone={s.fit === "Specialization match" ? "success" : "warning"}>{s.fit}</Badge>
          {s.same_department && <span style={{ fontSize: 12, color: "#6b7280" }}>same college</span>}
        </div>
        <div style={{ color: "#4b5563", marginTop: 4, overflowWrap: "anywhere" }}>
          {s.degree ? <>Degree: <b>{s.degree}</b></> : <span style={{ color: "#6b7280" }}>No degree on file</span>}
          {spec && <> · Specialization: <b>{spec}</b></>}
        </div>
        {s.qualifications && <div style={{ color: "#4b5563", overflowWrap: "anywhere" }}>Qualifications: {s.qualifications}</div>}
        <div style={{ color: "#4b5563", overflowWrap: "anywhere" }}>Availability: {s.availability || "No availability limits submitted (open)"}{" "}<span style={{ color: "#166534" }}>· free at the class time</span></div>
        <div style={{ marginTop: 6, display: "grid", gridTemplateColumns: "minmax(120px, 200px) 1fr", gap: 10, alignItems: "center" }}>
          <Bar value={s.current_hours} max={s.max_hours} after={s.current_hours + hours} />
          <span style={{ fontSize: 12, color: "#374151" }}>{fmt(s.current_hours)} → <b>{fmt(s.current_hours + hours)}</b> / {fmt(s.max_hours)} h · {fmt(Math.max(0, s.remaining_after))} h to spare after</span>
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 3 }}>{(s.reasons || []).join(" · ")}</div>
      </div>
    </label>
  );
}

function ClassBlock({ teacher, cls, onDone }) {
  const [sugg, setSugg] = useState(cls.suggestions);
  const [reason, setReason] = useState(cls.reason_none);
  const [loading, setLoading] = useState(false);
  const [pick, setPick] = useState(cls.suggestions && cls.suggestions[0] ? cls.suggestions[0].faculty_id : null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [confirming, setConfirming] = useState(false);

  const find = async () => {
    setLoading(true);
    try {
      const r = await API.get("/engine/workload/replacements/", { params: { faculty_id: teacher.faculty_id, subject_id: cls.subject_id, section_id: cls.section_id } });
      const list = (r.data.suggestions || []).map((s) => ({ ...s, remaining_after: s.remaining_after }));
      setSugg(list); setPick(list[0] ? list[0].faculty_id : null);
      // the server's own reason (for a major: "No available faculty in your department ..." with the reason for each teacher)
      setReason(list.length ? "" : (r.data.reason_none || "No qualified faculty member is available, free and under their weekly limit for this class."));
    } catch (e) { setMsg({ ok: false, text: e.response?.data?.detail || "Could not look up replacements." }); }
    setLoading(false);
  };

  const assign = async () => {
    setBusy(true); setMsg(null); setConfirming(false);
    try {
      const r = await API.post("/engine/workload/overload-assign/", { schedule_ids: cls.schedule_ids, teacher: pick });
      setMsg({ ok: true, data: r.data });
      notifyWorkloadChanged();
      onDone && onDone(r.data);
    } catch (e) {
      const d = e.response?.data || {};
      setMsg({ ok: false, text: d.detail || "Could not assign.", conflicts: d.conflicts });
    }
    setBusy(false);
  };

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 14px", marginBottom: 12, background: "#fff" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <b style={{ overflowWrap: "anywhere" }}>{cls.code} — {cls.subject}</b>
        <span style={{ color: "#4b5563", fontSize: 13 }}>{cls.section}</span>
        {cls.recommended && <Badge tone="warning">Move this to fix the overload</Badge>}
      </div>
      <div style={{ fontSize: 13, color: "#6b7280", margin: "3px 0 8px" }}>{cls.when} · {fmt(cls.hours)} h / week{cls.required_field ? ` · needs ${cls.required_field}` : ""}</div>
      {msg && msg.ok && (
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "10px 12px", fontSize: 13, color: "#166534" }}>
          <b>Assigned.</b> {msg.data.subject} ({msg.data.section}) now belongs to {msg.data.to.name}. The schedule was updated.
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            {msg.data.checks.map((c, i) => <li key={i} style={{ color: c.ok ? "#166534" : "#92400e" }}>{c.ok ? "Passed:" : "Check:"} {c.label}{c.detail ? ` — ${c.detail}` : ""}</li>)}
          </ul>
        </div>
      )}
      {!(msg && msg.ok) && (
        <>
          {sugg === null && <button style={btn} onClick={find} disabled={loading}>{loading ? "Looking…" : "Find qualified faculty"}</button>}
          {sugg && sugg.length > 0 && (
            <>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
                Qualified, available and free ({sugg.length})
              </div>
              {/* one searchable list (TeacherPicker, the same as the Edit and Generate dialogs); the server sends only teachers the rules
                  allow (for a major: qualified faculty of the same department, free then, within their limit), lower load first */}
              <div style={{ marginBottom: 8 }}>
                <TeacherPicker ariaLabel={`Replacement for ${cls.code}`} value={pick ? String(pick) : ""}
                  onChange={(v) => { setPick(v ? Number(v) : null); setConfirming(false); }}
                  options={sugg.map((s) => ({ id: s.faculty_id, label: `${s.full_name} - ${fmt(s.current_hours)} of ${fmt(s.max_hours)} hrs`,
                    detail: `${TYPE_LABEL[s.faculty_type] || s.faculty_type} · ${s.fit} · ${fmt(Math.max(0, s.remaining_after))} h to spare after`,
                    group: "Suggested", search: `${s.school_id || ""} ${s.email || ""}` }))} />
              </div>
              {sugg.filter((s) => s.faculty_id === pick).map((s) => <Candidate key={s.faculty_id} s={s} hours={cls.hours} picked onPick={() => {}} />)}
              {!confirming && <button style={btnPrimary} onClick={() => setConfirming(true)} disabled={busy || !pick}>{busy ? "Assigning…" : "Assign"}</button>}
              {confirming && (() => {
                const c = sugg.find((x) => x.faculty_id === pick);
                if (!c) return null;
                return (
                  <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 6, padding: "10px 12px", fontSize: 13, color: "#1e3a8a" }}>
                    <b>Confirm reassignment</b>
                    <div style={{ marginTop: 4 }}>Move <b>{cls.code} {cls.subject}</b> ({cls.section}) from <b>{teacher.full_name}</b> ({fmt(teacher.hours)} → <b>{fmt(Math.max(0, teacher.hours - cls.hours))}</b> / {fmt(teacher.max_hours)} h)
                      to <b>{c.full_name}</b> ({fmt(c.current_hours)} → <b>{fmt(c.current_hours + cls.hours)}</b> / {fmt(c.max_hours)} h)? This changes the actual schedule.</div>
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button style={btnPrimary} onClick={assign} disabled={busy}>{busy ? "Assigning…" : "Okay, confirm"}</button>
                      <button style={btn} onClick={() => setConfirming(false)} disabled={busy}>Cancel</button>
                    </div>
                  </div>);
              })()}
            </>
          )}
          {sugg && sugg.length === 0 && (
            <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 6, padding: "10px 12px", fontSize: 13, color: "#92400e" }}>
              <b>This cannot be resolved automatically.</b> {reason}
            </div>
          )}
          {msg && !msg.ok && (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "10px 12px", fontSize: 13, color: "#991b1b", marginTop: 8 }}>
              Nothing was changed. {msg.text}
              {msg.conflicts && msg.conflicts.length > 0 && <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>{msg.conflicts.slice(0, 3).map((c, i) => <li key={i}>{c.message || c.kind}</li>)}</ul>}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function ResolverWindow({ onClose, focusId = null }) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState({});
  const [done, setDone] = useState([]);          // reassignments made in this window (their cards disappear once the overload is cured)
  const load = useCallback(() => {
    API.get("/engine/workload/overload-plan/").then((r) => { setPlan(r.data); setError(""); })
      .catch((e) => setError(e.response?.data?.detail || "Could not load the suggestions."));
  }, []);
  useEffect(() => { load(); }, [load]);
  const applied = (d) => { setDone((x) => [...x, d]); load(); };

  return (
    <ModalPortal><div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 80, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div className="overload-resolver-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Overload suggestions"
        style={{ background: "#f9fafb", borderRadius: 6, width: "100%", maxWidth: 860, maxHeight: "92vh", overflowY: "auto", padding: "20px 22px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <h3 style={{ margin: 0, color: "#003366" }}>Faculty overload — suggestions</h3>
          <button style={btn} onClick={onClose}>Close</button>
        </div>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: "#6b7280" }}>
          Only faculty with a matching specialization, degree or qualification are listed, and only if they are available, free at that time and stay within their weekly limit.
          Assign changes the real schedule; it is checked again before it is saved.
        </p>
        {done.map((d, i) => (
          <div key={i} style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "12px 14px", marginBottom: 12, fontSize: 13, color: "#166534" }}>
            <b>Resolved:</b> {d.subject} ({d.section}) moved from {d.from.name} ({fmt(d.from.hours)}/{fmt(d.from.max_hours)} h) to {d.to.name} ({fmt(d.to.hours)}/{fmt(d.to.max_hours)} h). The schedule was updated.
            <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>{d.checks.map((c, j) => <li key={j} style={{ color: c.ok ? "#166534" : "#92400e" }}>{c.ok ? "Passed:" : "Check:"} {c.label}{c.detail ? ` — ${c.detail}` : ""}</li>)}</ul>
          </div>))}
        {error && <p style={{ color: "#b91c1c" }}>{error} <button style={btn} onClick={load}>Retry</button></p>}
        {!plan && !error && <p>Loading suggestions…</p>}
        {plan && plan.items.length === 0 && (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "14px 16px", color: "#166534" }}>
            <b>No faculty member is overloaded now.</b> Every teacher is within their weekly limit.
          </div>
        )}
        {plan && focusId && plan.items.length > 0 && !plan.items.some((i) => i.faculty_id === focusId) && (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "12px 14px", color: "#166534", marginBottom: 12 }}>
            This teacher is no longer overloaded.
          </div>)}
        {plan && plan.items.filter((i) => !focusId || i.faculty_id === focusId).map((it) => {
          const extra = it.classes.filter((c) => !c.recommended);
          const lockedSubjects = (it.subjects || []).filter((subject) => !subject.editable);
          return (
            <div className="overload-teacher-card" key={`${it.faculty_id}-${it.term}`}>
              <div className="overload-teacher-heading">
                <b>{it.full_name}</b>
                <Badge tone="neutral">{TYPE_LABEL[it.faculty_type] || it.faculty_type}</Badge>
                <span className="overload-hours-summary">{fmt(it.hours)} / {fmt(it.max_hours)} h · {it.term}</span>
                <Badge tone="warning">Over by {fmt(it.overload_hours)} h</Badge>
              </div>
              <details className="overload-subject-details">
                <summary>Assigned classes <span>{(it.subjects || []).length}</span></summary>
                <div className="overload-subject-list">
                  {(it.subjects || []).map((x, i) => <div className="overload-subject-row" key={`${x.code}-${x.section}-${i}`}>
                    <div><b>{x.code}</b><span>{x.subject}</span><small>{x.section} · {x.when}</small></div>
                    <div className="overload-subject-meta"><b>{fmt(x.hours)} h</b><span className={x.editable ? "is-editable" : "is-locked"}>{x.editable ? "Can be moved" : x.locked_reason || "Locked"}</span></div>
                  </div>)}
                </div>
              </details>
              {lockedSubjects.length > 0 && <div className="overload-lock-note">
                <b>{it.classes.length === 0 ? "No classes can be moved from this page." : `${lockedSubjects.length} assigned ${lockedSubjects.length === 1 ? "class is" : "classes are"} locked.`}</b>
                <span>{it.classes.length === 0
                  ? "These classes are shared, approved, published, or owned by another workspace. Ask the class owner to make an editable draft before changing its teacher."
                  : "Locked classes are excluded from the suggested changes."}</span>
              </div>}
              {lockedSubjects.length === 0 && it.notes.length > 0 && <div className="overload-lock-note">
                <b>Some overload may remain.</b><span>{it.notes[0]}</span>
              </div>}
              {it.classes.filter((c) => c.recommended).map((c) => <ClassBlock key={c.schedule_ids.join("-")} teacher={it} cls={c} onDone={applied} />)}
              {extra.length > 0 && (
                <>
                  <button style={btn} onClick={() => setShowAll({ ...showAll, [it.faculty_id]: !showAll[it.faculty_id] })}>
                    {showAll[it.faculty_id] ? "Hide" : "Show"} other changeable classes ({extra.length})
                  </button>
                  {showAll[it.faculty_id] && <div style={{ marginTop: 10 }}>{extra.map((c) => <ClassBlock key={c.schedule_ids.join("-")} teacher={it} cls={{ ...c, suggestions: null }} onDone={applied} />)}</div>}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div></ModalPortal>
  );
}

/* The warning: one row per overloaded teacher (subjects + excess) with its own View Suggestions button. Refreshes itself and stays
   until the overload is really gone. */
export default function OverloadBanner() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(null);          // null = closed, 0 = all teachers, id = one teacher
  const load = useCallback(() => {
    API.get("/engine/workload/overload-summary/").then((r) => setItems(r.data.items)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const tick = () => { if (!document.hidden) load(); };
    const id = setInterval(tick, 30000);
    window.addEventListener("focus", tick);
    const off = onWorkloadChanged(load);
    return () => { clearInterval(id); window.removeEventListener("focus", tick); off(); };
  }, [load]);
  return (
    <>
      {items.length > 0 && (
        <div style={{ background: "#fdecea", border: "1px solid #f3b3ac", borderRadius: 6, padding: "12px 16px", margin: "0 0 16px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
            <strong style={{ color: "#b91c1c" }}>Faculty workload warning — {items.length} faculty member{items.length === 1 ? " is" : "s are"} overloaded</strong>
            {items.length > 1 && <button style={btnPrimary} onClick={() => setOpen(0)}>View Suggestions (all)</button>}
          </div>
          {items.map((f) => (
            <div key={`${f.faculty_id}-${f.term}`} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", justifyContent: "space-between", marginTop: 10, paddingTop: 10, borderTop: "1px solid #f3c9c4" }}>
              <div style={{ flex: "1 1 340px", minWidth: 0, fontSize: 13, color: "#7a1b14" }}>
                <b>{f.full_name}</b> ({TYPE_LABEL[f.faculty_type] || f.faculty_type}) is assigned {fmt(f.hours)} h a week; the limit is {fmt(f.max_hours)} h — <b>over by {fmt(f.overload_hours)} h</b> ({f.term}).
                <div style={{ color: "#8a4b44", overflowWrap: "anywhere" }}>
                  Subjects: {f.subjects.slice(0, 4).map((x) => `${x.code} (${fmt(x.hours)} h)`).join(", ")}{f.subjects.length > 4 ? ` +${f.subjects.length - 4} more` : ""}
                </div>
              </div>
              <button style={btnPrimary} onClick={() => setOpen(f.faculty_id)}>View Suggestions</button>
            </div>))}
        </div>
      )}
      {open !== null && <ResolverWindow focusId={open || null} onClose={() => { setOpen(null); load(); }} />}
    </>
  );
}
