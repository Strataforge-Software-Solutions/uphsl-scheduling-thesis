import React, { useState } from "react";
import ModalPortal from "./ModalPortal";

/* Confirmation for a manual "Assign anyway": the chosen person is NOT connected to the subject (no matching specialization or degree).
   A short reason is required. Nothing is saved here; the server checks everything again when the change is saved. */
export function OverrideBadge({ text = "Assigned by Dean (not connected)", reason }) {
  return (
    <span title={reason ? `Reason: ${reason}` : undefined}
      style={{ display: "inline-block", border: "1px solid #92400e", color: "#92400e", background: "#fffbeb", borderRadius: 4,
        padding: "0 6px", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>
      {text}
    </span>
  );
}

export default function AssignAnywayDialog({ person, subjectCode, subjectTitle, onCancel, onConfirm, busy = false, roleWord = "Dean" }) {
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  if (!person) return null;
  const ok = reason.trim().length >= 3;
  const name = person.full_name || person.label;
  return (
    <ModalPortal><div role="dialog" aria-modal="true" aria-labelledby="assign-anyway-title"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}
      onKeyDown={(e) => { if (e.key === "Escape" && !busy) { e.preventDefault(); e.stopPropagation(); onCancel(); } }}
      style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 6000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: "white", borderRadius: 6, width: "min(520px, 100%)", padding: "18px 20px", boxShadow: "var(--shadow-pop)" }}>
        <h3 id="assign-anyway-title" style={{ margin: "0 0 8px", fontSize: 16, color: "#111827" }}>Assign anyway?</h3>
        <p style={{ margin: "0 0 10px", fontSize: 14, color: "#374151", lineHeight: 1.5 }}>
          <strong>{name}</strong> is not connected to <strong>{subjectCode}{subjectTitle ? ` ${subjectTitle}` : ""}</strong>{" "}
          (specialization: {person.specializations || "none recorded"}). Assign anyway?
        </p>
        <p style={{ margin: "0 0 10px", fontSize: 12, color: "#6b7280" }}>
          Their availability, other classes and weekly limit still apply. The class is marked "Assigned by {roleWord} (not connected)".
        </p>
        <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151" }}>
          Reason (required)
          <input autoFocus value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} onBlur={() => setTouched(true)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setTouched(true); if (ok && !busy) onConfirm(reason.trim()); } }}
            placeholder="e.g. no qualified faculty free" aria-invalid={touched && !ok ? "true" : "false"}
            style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 4, fontSize: 14, padding: "7px 9px", borderRadius: 4, border: "1px solid #d1d5db", fontWeight: 400 }} />
        </label>
        {touched && !ok && <div role="alert" style={{ fontSize: 12, color: "#b91c1c", marginTop: 4 }}>Write a short reason.</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
          <button type="button" onClick={onCancel} disabled={busy}
            style={{ background: "white", color: "#374151", border: "1px solid #d1d5db", borderRadius: 4, padding: "6px 14px", fontSize: 13 }}>Cancel</button>
          <button type="button" disabled={!ok || busy} onClick={() => onConfirm(reason.trim())}
            style={{ background: "#003366", color: "white", border: "1px solid #003366", borderRadius: 4, padding: "6px 14px", fontSize: 13, fontWeight: 600 }}>
            {busy ? "Assigning…" : "Assign"}
          </button>
        </div>
      </div>
    </div></ModalPortal>
  );
}
