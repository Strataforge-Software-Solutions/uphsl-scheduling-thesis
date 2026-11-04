import React, { useState } from "react";
import { HOWTO } from "./howto";

/* "How to Use This Tab": a short, collapsed step-by-step panel placed under the page header of every dashboard tab. */
export default function HowToUse({ role, tab }) {
  const info = HOWTO[role]?.[tab];
  const [open, setOpen] = useState(false);
  if (!info) return null;
  return (
    <div className="howto" style={{ margin: "0 0 14px", border: "1px solid #dbe5f1", borderRadius: 10, background: "#f6f9fd" }}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", background: "none", border: "none", padding: "9px 14px", cursor: "pointer", fontSize: 13.5, color: "#003366", fontWeight: 600 }}>
        <span aria-hidden="true" title="Help" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, borderRadius: "50%", background: "#003366", color: "white", fontSize: 12 }}>i</span>
        How to Use This Tab
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>{open ? "Hide ▲" : "Show ▼"}</span>
      </button>
      {open && (
        <div style={{ padding: "0 16px 12px", fontSize: 13, color: "#334155" }}>
          <p style={{ margin: "0 0 6px" }}>{info.summary}</p>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.65 }}>
            {info.steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}
    </div>
  );
}
