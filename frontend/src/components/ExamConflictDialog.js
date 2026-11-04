import React, { useEffect, useState } from "react";
import API from "../services/api";

/* Pop-up for exams that could not be placed: shows what is in the way and the new date / hour for the program (major) exams that have to
   move, then places the blocked exams in the hour its other sections use (same subject, same time, different room). */
export default function ExamConflictDialog({ pending, form, onClose, onApplied, isDean = false }) {
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const body = (apply) => ({
    semester: form.semester, exam_period: form.exam_period, exam_start_date: form.exam_start_date, exam_end_date: form.exam_end_date,
    items: (pending || []).map((p) => ({ subject_id: p.subject_id, section_id: p.section_id })), apply,
  });

  useEffect(() => {
    let alive = true;
    setBusy(true);
    API.post("/exams/resolve/", body(false), { timeout: 120000 })
      .then((r) => alive && setPlan(r.data))
      .catch((e) => alive && setError(e.response?.data?.detail || "Could not check the conflicts."))
      .finally(() => alive && setBusy(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apply = async () => {
    setBusy(true); setError("");
    try {
      const r = await API.post("/exams/resolve/", body(true), { timeout: 120000 });
      setPlan(r.data);
      if (r.data.applied) onApplied && onApplied(r.data);
      else if (r.data.detail) setError(r.data.detail);
    } catch (e) {
      setError(e.response?.data?.detail || "Could not apply the change.");
    } finally { setBusy(false); }
  };

  const fmt = (p) => `${new Date(p.date + "T00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} ${p.start}–${p.end}`;
  const items = plan?.items || [];
  const fixable = items.filter((i) => ["can_place", "needs_dean", "dean_moves"].includes(i.status));
  const done = plan?.applied;
  const asks = items.filter((i) => i.status === "needs_dean").length;
  const actionLabel = isDean
    ? `Change date / time of ${fixable.reduce((n, i) => n + i.moves.length, 0)} of my exam(s)`
    : asks ? "Place what I can and ask the Dean(s) to move their exams" : `Place ${fixable.length} exam${fixable.length === 1 ? "" : "s"}`;
  return (
    <div role="dialog" aria-modal="true" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.55)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}>
      <div style={{ background: "#fff", borderRadius: "12px", maxWidth: "760px", width: "100%", maxHeight: "86vh", overflowY: "auto", padding: "22px 24px", boxShadow: "0 20px 50px rgba(0,0,0,.3)" }}>
        <h3 style={{ marginTop: 0, color: "#003366" }}>{done ? (isDean ? "✓ Exams moved" : "✓ Done") : (isDean ? "Registrar requests" : "⚠ Exam conflict")}</h3>
        {!done && !isDean && <p style={{ fontSize: "13px", color: "#475569", marginTop: 0 }}>
          {pending.length} Gen Ed exam{pending.length === 1 ? "" : "s"} could not be placed because the section already has a program (major) exam in that hour.
          The Registrar places the Gen Ed exams in the hour the other sections use (same subject, same time, different room); the Dean of each college
          changes the date or hour of their own major exams. Classes are never moved.</p>}
        {!done && isDean && <p style={{ fontSize: "13px", color: "#475569", marginTop: 0 }}>
          These exams of your college are in the hour a Gen Ed exam needs. Moving them to the new date / hour below lets the Registrar place the Gen Ed exams.
          {items.length === 0 && !busy ? " There are no requests for your college right now." : ""}</p>}
        {done && !isDean && plan?.requested > 0 && <p style={{ fontSize: "13px", color: "#1d5a1d" }}>The Dean(s) were notified and will change the date / time of their exams.</p>}
        {busy && !plan && <p>Checking the exam week…</p>}
        {error && <p style={{ color: "#a4231a", fontSize: "13px" }}>{error}</p>}
        {items.map((it, i) => (
          <div key={i} style={{ border: "1px solid #e2e8f0", borderRadius: "8px", padding: "10px 12px", marginBottom: "10px", background: it.status === "blocked" ? "#fff8e6" : "#f8fafc" }}>
            <div style={{ fontWeight: 600, fontSize: "13.5px" }}>{it.subject} — {it.section}</div>
            {it.status === "blocked" && <div style={{ fontSize: "12.5px", color: "#7a4b00" }}>{it.reason}</div>}
            {it.place && <div style={{ fontSize: "12.5px", color: "#1d5a1d" }}>{isDean ? "Gen Ed exam will use" : (it.status === "placed" ? "Placed" : "Will be placed")}: {fmt(it.place)} · room {it.place.room}{it.status === "requested" ? " (after the Dean moves the exam below)" : ""}</div>}
            {it.moves?.length > 0 && (
              <div style={{ fontSize: "12.5px", marginTop: "4px" }}>
                {done ? "Major exams moved:" : (isDean ? "Your exams that will change date / time:" : "Major exams the Dean must move:")}
                <ul style={{ margin: "3px 0 0 18px", padding: 0 }}>
                  {it.moves.map((m) => <li key={m.exam_id}>{m.subject} ({m.section}): {fmt(m)} → <b>{fmt(m.to)}</b>, room {m.to.room}</li>)}
                </ul>
              </div>
            )}
          </div>
        ))}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "8px" }}>
          <button onClick={onClose} disabled={busy} style={{ padding: "8px 16px", borderRadius: "8px", border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer" }}>{done ? "Close" : "Not now"}</button>
          {!done && fixable.length > 0 && (
            <button onClick={apply} disabled={busy} style={{ padding: "8px 16px", borderRadius: "8px", border: "none", background: "#0b6b3a", color: "#fff", fontWeight: 600, cursor: busy ? "wait" : "pointer" }}>
              {busy ? "Applying…" : actionLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
