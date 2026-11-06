import React, { useState } from "react";
import { HOWTO } from "./howto";

/* "How to Use This Tab": a short, collapsed step-by-step panel placed under the page header of every dashboard tab. */
export default function HowToUse({ role, tab }) {
  const info = HOWTO[role]?.[tab];
  const [open, setOpen] = useState(false);
  if (!info) return null;
  return (
    <div className="howto" style={{ margin: "0 0 16px", border: "1px solid #e5e7eb", borderRadius: 6, background: "white" }}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", background: "none", border: "none", padding: "8px 12px", cursor: "pointer", fontSize: 13, color: "#374151", fontWeight: 600 }}>
        How to use this tab
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#003366", fontWeight: 600 }}>{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div style={{ padding: "0 16px 12px", fontSize: 13, color: "#374151", borderTop: "1px solid #f3f4f6", paddingTop: 10 }}>
          <p style={{ margin: "0 0 6px" }}>{info.summary}</p>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.65 }}>
            {info.steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}
    </div>
  );
}
