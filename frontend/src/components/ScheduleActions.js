import React, { useEffect, useState } from "react";
import API from "../services/api";
import { formatDateTime } from "../utils/formatDateTime";

/* Select / Approve / Publish / Back to draft / Remove (with Undo) / History for the Schedules tab.
   Shared by the Registrar's and the Dean's schedule tables. Every rule is checked again on the server
   (engine/schedule_actions.py): ownership, the Draft -> Approved -> Published chain, the conflict check before approving,
   and "only drafts can be removed". Buttons here carry explicit colours (the theme has a global button { color: white } rule). */
const C = { navy: "#003366", line: "#e5e7eb", ok: "#166534", warn: "#7a4b00", bad: "#b91c1c", muted: "#6b7280" };
export const btnStyle = (bg, fg = "#ffffff", border) => ({
  background: bg, color: fg, border: border || (bg === "#ffffff" ? `1px solid ${C.navy}` : "none"), borderRadius: 6,
  padding: "6px 12px", fontSize: 13, cursor: "pointer", whiteSpace: "nowrap",
});
const overlay = { position: "fixed", inset: 0, background: "rgba(15,23,42,.48)", backdropFilter: "blur(2px)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 };
const panel = { background: "#ffffff", color: "#142b4e", border: "1px solid #e4eaf2", borderRadius: 12, width: "100%", maxWidth: 620, maxHeight: "88vh", overflowY: "auto", padding: "22px 24px 18px", boxShadow: "0 22px 60px rgba(15, 35, 63, .28)" };

function ClassList({ items, tone }) {
  return (
    <ul style={{ margin: "4px 0 10px 18px", padding: 0, fontSize: 13 }}>
      {items.map((c) => (
        <li key={c.key} style={{ marginBottom: 4 }}>
          <strong>{c.code}</strong> {c.title} — {c.section}
          <div style={{ color: C.muted, fontSize: 12 }}>{c.periods.join("; ")} · room {c.room}</div>
          {(c.reasons || []).map((r, i) => <div key={i} style={{ color: tone === "bad" ? C.bad : C.warn, fontSize: 13 }}>{r}</div>)}
        </li>
      ))}
    </ul>
  );
}

/* The sticky bar shown while rows are ticked. */
export function SelectionBar({ groups, busy, onApprove, onPublish, onDraft, onRemove, onClear, extra }) {
  if (!groups.length) return null;
  const n = (st) => groups.filter((g) => g.status === st).length;
  const drafts = n("draft"), approved = n("approved");
  return (
    <div role="region" aria-label="Selected classes" style={{ position: "sticky", bottom: 0, zIndex: 50, marginTop: 10, background: "#0f2747", color: "#ffffff",
      borderRadius: 6, padding: "10px 14px", display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", boxShadow: "0 -4px 18px rgba(0,0,0,.18)" }}>
      <strong style={{ marginRight: 6 }}>{groups.length} selected</strong>
      <button disabled={busy || !drafts} onClick={onApprove} style={{ ...btnStyle("#16a34a"), opacity: drafts ? 1 : 0.45 }} title="Approve the selected drafts (each is checked for conflicts first)">
        Approve{drafts ? ` (${drafts})` : ""}</button>
      <button disabled={busy || !approved} onClick={onPublish} style={{ ...btnStyle("#2563eb"), opacity: approved ? 1 : 0.45 }} title="Publish the selected approved classes (teachers are told they are final)">
        Publish{approved ? ` (${approved})` : ""}</button>
      <button disabled={busy || !approved} onClick={onDraft} style={{ ...btnStyle("#ffffff", "#0f2747", "1px solid #ffffff"), opacity: approved ? 1 : 0.45 }} title="Move the selected approved classes back to Draft">
        Back to draft{approved ? ` (${approved})` : ""}</button>
      {extra}
      <button disabled={busy || !drafts} onClick={onRemove} style={{ ...btnStyle("#b91c1c"), opacity: drafts ? 1 : 0.45 }} title="Remove the selected drafts (you see the list first; Undo is possible for a few minutes)">
        Remove{drafts ? ` (${drafts})` : ""}</button>
      <span style={{ flex: 1 }} />
      <button onClick={onClear} disabled={busy} style={btnStyle("transparent", "#ffffff", "1px solid #6b7280")}>Clear</button>
    </div>
  );
}

/* Keep every row action visible, but group them into a clear, consistent grid. */
export function RowActions({ group, actions, onEdit, selecting }) {
  const g = group;
  const lockTitle = selecting ? "Rows are selected: use the bar at the bottom (or clear the selection)" : undefined;
  const off = actions.busy || selecting;
  return (
    <div className="schedule-row-actions" role="group" aria-label={`Actions for ${g.subject_code} ${g.section_name}`}>
      {g.status === "draft" && (
        <button onClick={() => actions.changeStatus(g.ids, "approved")} disabled={off} title={lockTitle || "Approve this class (checked for conflicts first)"}
          className="schedule-row-action is-approve">Approve</button>
      )}
      {g.status === "approved" && (
        <button onClick={() => actions.changeStatus(g.ids, "published")} disabled={off} title={lockTitle || "Publish this class (checked for conflicts first)"}
          className="schedule-row-action is-publish">Publish</button>
      )}
      {g.status === "draft" && <button onClick={() => onEdit(g)} className="schedule-row-action is-edit" title="Edit teacher, room, or choose a new free day and time">Edit</button>}
      {g.status === "approved" && <button onClick={() => actions.changeStatus(g.ids, "draft")} disabled={off} className="schedule-row-action is-draft" title={lockTitle || "Move this class back to draft"}>Draft</button>}
      {g.status === "draft" && <button onClick={() => actions.askRemove(g.ids)} disabled={off} className="schedule-row-action is-remove" title={lockTitle || "Remove this draft class"}>Remove</button>}
      <button onClick={() => actions.showHistory(g.ids, `${g.subject_code} ${g.section_name}`)} className="schedule-row-action is-history" title="View change history">History</button>
    </div>
  );
}

export function useScheduleActions(reload) {
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);      // approve / publish / draft result {to, ready, blocked, skipped, updated}
  const [removal, setRemoval] = useState(null);    // {plan, confirmShared}
  const [undo, setUndo] = useState(null);          // {token, until, text}
  const [hist, setHist] = useState(null);          // {label, events} | {error}
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => { if (!undo) return undefined; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, [undo]);
  useEffect(() => { if (undo && now > undo.until) setUndo(null); }, [now, undo]);

  const changeStatus = async (ids, to) => {
    if (!ids.length) return;
    setBusy("status"); setError("");
    try {
      const r = await API.post("/engine/schedules/approve_bulk/", { ids, to_status: to });
      setResult({ ...r.data, to });
    } catch (e) {
      setResult({ to, error: e.response?.data?.detail || "Could not change the status." });
    } finally { setBusy(""); reload(); }
  };
  const askRemove = async (ids) => {
    setBusy("preview"); setError("");
    try {
      const r = await API.post("/engine/schedules/remove_preview/", { ids });
      setRemoval({ plan: r.data, confirmShared: false });
    } catch (e) { setError(e.response?.data?.detail || "Could not prepare the removal."); }
    finally { setBusy(""); }
  };
  const doRemove = async () => {
    const ids = removal.plan.remove.flatMap((c) => c.ids);
    setBusy("remove");
    try {
      const r = await API.post("/engine/schedules/remove_bulk/", { ids, confirm_shared: removal.confirmShared });
      setRemoval(null);
      setUndo({ token: r.data.undo_token, until: Date.now() + r.data.undo_minutes * 60000,
        text: `Removed ${r.data.removed} period${r.data.removed === 1 ? "" : "s"} (${r.data.classes.map((c) => c.code).join(", ")}).` });
    } catch (e) {
      setRemoval((x) => ({ ...x, error: e.response?.data?.detail || "Could not remove." }));
    } finally { setBusy(""); reload(); }
  };
  const doUndo = async () => {
    setBusy("undo");
    try {
      const r = await API.post("/engine/schedules/undo_remove/", { token: undo.token });
      setUndo({ ...undo, done: `Restored ${r.data.restored} period${r.data.restored === 1 ? "" : "s"}.`, until: Date.now() + 4000, token: null });
    } catch (e) {
      setUndo({ ...undo, done: e.response?.data?.detail || "Could not undo.", until: Date.now() + 8000, token: null });
    } finally { setBusy(""); reload(); }
  };
  const showHistory = async (ids, label) => {
    setHist({ label, loading: true });
    try { setHist({ label, events: (await API.get("/engine/schedules/history/", { params: { ids: ids.join(",") } })).data.events }); }
    catch (e) { setHist({ label, error: e.response?.data?.detail || "Could not load the history." }); }
  };

  const verb = { approved: "approved", published: "published", draft: "moved back to draft" };
  const dialogs = (
    <>
      {error && <div role="alert" style={{ position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)", zIndex: 1200, background: "#fef2f2", color: C.bad, border: "1px solid #fecaca", borderRadius: 6, padding: "8px 14px", fontSize: 13 }}>
        {error} <button onClick={() => setError("")} style={btnStyle("#ffffff", C.bad, "1px solid #fecaca")}>OK</button></div>}

      {result && (
        <div role="dialog" aria-modal="true" aria-label="Result" style={overlay}>
          <div style={panel}>
            {result.error ? <><h3 style={{ marginTop: 0, color: C.bad }}>Nothing was changed</h3><p style={{ fontSize: 14 }}>{result.error}</p></> : (
              <>
                <h3 style={{ marginTop: 0, color: C.navy }}>
                  {result.ready.length} ready, {result.blocked.length} blocked
                </h3>
                <p style={{ fontSize: 13, color: C.muted, marginTop: 0 }}>
                  {result.to === "draft" ? "Approved classes were moved back to Draft." : "Each class was checked against the whole schedule first. Classes in a conflict stay as they are."}
                </p>
                {result.ready.length > 0 && <><div style={{ fontWeight: 600, color: C.ok }}>{verb[result.to]} ({result.updated} period{result.updated === 1 ? "" : "s"})</div><ClassList items={result.ready} /></>}
                {result.blocked.length > 0 && <><div style={{ fontWeight: 600, color: C.bad }}>Blocked — not {verb[result.to]}</div><ClassList items={result.blocked} tone="bad" />
                  {result.to !== "draft" && <p style={{ fontSize: 13, color: C.muted }}>Fix these in the Conflicts tab (Fix this conflict), then approve them again.</p>}</>}
                {(result.skipped || []).length > 0 && <><div style={{ fontWeight: 600, color: C.muted }}>Skipped (not at the right stage)</div><ClassList items={result.skipped} /></>}
              </>
            )}
            <div style={{ textAlign: "right" }}><button onClick={() => setResult(null)} style={btnStyle(C.navy)}>Close</button></div>
          </div>
        </div>
      )}

      {removal && (
        <div role="dialog" aria-modal="true" aria-label="Remove classes" style={overlay}>
          <div style={{ ...panel, borderTop: "5px solid #b91c1c" }}>
            <h3 style={{ marginTop: 0, color: C.bad }}>Remove {removal.plan.periods} period{removal.plan.periods === 1 ? "" : "s"}?</h3>
            {removal.plan.remove.length > 0 ? <ClassList items={removal.plan.remove} /> : <p style={{ fontSize: 13 }}>None of the selected classes can be removed.</p>}
            {removal.plan.locked.length > 0 && <><div style={{ fontWeight: 600, color: C.warn }}>Not removed (approved or published)</div><ClassList items={removal.plan.locked} /></>}
            {removal.plan.warnings.map((w, i) => <div key={i} style={{ background: "#fffbeb", border: "1px solid #fde68a", color: C.warn, borderRadius: 6, padding: "8px 10px", fontSize: 13, marginBottom: 8 }}>{w}</div>)}
            {removal.plan.shared && (
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, marginBottom: 8 }}>
                <input type="checkbox" checked={removal.confirmShared} onChange={(e) => setRemoval({ ...removal, confirmShared: e.target.checked })} />
                I understand this removes this section from a shared class.
              </label>
            )}
            <p style={{ fontSize: 13, color: C.muted }}>You can undo this for {removal.plan.undo_minutes} minutes.</p>
            {removal.error && <p style={{ color: C.bad, fontSize: 13 }}>{removal.error}</p>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setRemoval(null)} style={btnStyle("#ffffff", C.navy)}>Cancel</button>
              <button disabled={busy === "remove" || !removal.plan.remove.length || (removal.plan.shared && !removal.confirmShared)} onClick={doRemove}
                style={{ ...btnStyle("#b91c1c"), opacity: (!removal.plan.remove.length || (removal.plan.shared && !removal.confirmShared)) ? 0.5 : 1 }}>
                {busy === "remove" ? "Removing…" : `Remove ${removal.plan.periods} period${removal.plan.periods === 1 ? "" : "s"}`}</button>
            </div>
          </div>
        </div>
      )}

      {undo && (
        <div role="status" style={{ position: "fixed", bottom: 18, right: 18, zIndex: 1200, background: "#111827", color: "#ffffff", borderRadius: 6, padding: "10px 14px", fontSize: 13, display: "flex", gap: 10, alignItems: "center", boxShadow: "var(--shadow-pop)", maxWidth: 440 }}>
          <span>{undo.done || undo.text}</span>
          {undo.token && <button onClick={doUndo} disabled={busy === "undo"} style={btnStyle("#fbbf24", "#111827")}>
            Undo ({Math.max(0, Math.ceil((undo.until - now) / 1000 / 60))} min)</button>}
          <button onClick={() => setUndo(null)} aria-label="Dismiss" style={btnStyle("transparent", "#ffffff", "1px solid #6b7280")}>×</button>
        </div>
      )}

      {hist && (
        <div role="dialog" aria-modal="true" aria-label="Class history" style={overlay}>
          <div style={panel}>
            <h3 style={{ marginTop: 0, color: C.navy }}>History — {hist.label}</h3>
            {hist.loading && <p>Loading…</p>}
            {hist.error && <p style={{ color: C.bad }}>{hist.error}</p>}
            {hist.events && (
              <table style={{ width: "100%", fontSize: 13 }}>
                <thead><tr><th>When</th><th>What</th><th>Who</th><th>Details</th></tr></thead>
                <tbody>{hist.events.map((e, i) => (
                  <tr key={i}><td style={{ whiteSpace: "nowrap" }}>{formatDateTime(e.when)}</td><td>{e.action}</td><td>{e.user || "—"}</td><td>{e.details}</td></tr>
                ))}</tbody>
              </table>
            )}
            <div style={{ textAlign: "right", marginTop: 10 }}><button onClick={() => setHist(null)} style={btnStyle(C.navy)}>Close</button></div>
          </div>
        </div>
      )}
    </>
  );
  return { busy: !!busy, changeStatus, askRemove, showHistory, dialogs };
}
