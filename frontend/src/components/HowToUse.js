import React, { useState } from "react";
import { HOWTO } from "./howto";
import usePopupPresence from "./usePopupPresence";

export function SimplifiedGuide({ steps, title = "How to use this tab (Simplified)" }) {
  return (
    <section className="coverage-panel coverage-howto-panel page-simplified-guide">
      <div className="coverage-panel-heading">
        <span className="coverage-panel-icon"><svg className="coverage-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg></span>
        <div><h3>{title}</h3></div>
      </div>
      <div className="coverage-steps">
        {steps.map((step, index) => <React.Fragment key={step}>
          <div><b>{index + 1}</b><span>{step}</span></div>
          {index < steps.length - 1 && <i aria-hidden="true">›</i>}
        </React.Fragment>)}
      </div>
    </section>
  );
}

/* "How to Use This Tab": a short, collapsed step-by-step panel placed under the page header of every dashboard tab. */
export default function HowToUse({ role, tab }) {
  const info = HOWTO[role]?.[tab];
  const [open, setOpen] = useState(false);
  const { present: contentPresent, closing } = usePopupPresence(open, 320);
  if (!info) return null;
  return (
    <div className={`howto${tab === "curriculum" ? " howto-curriculum" : ""}`} style={{ margin: "0 0 16px", border: "1px solid #e5e7eb", borderRadius: 6, background: "white" }}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", background: "none", border: "none", padding: "8px 12px", cursor: "pointer", fontSize: 13, color: "#374151", fontWeight: 600 }}>
        How to use this tab
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#003366", fontWeight: 600 }}>{open ? "Hide" : "Show"}</span>
      </button>
      {contentPresent && (
        <div className={`howto-content${closing ? " is-closing" : ""}`} aria-hidden={closing} inert={closing ? "" : undefined}>
          <div className="howto-content-inner" style={{ padding: "10px 16px 12px", fontSize: 13, color: "#374151", borderTop: "1px solid #f3f4f6" }}>
            <p style={{ margin: "0 0 6px" }}>{info.summary}</p>
            <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.65 }}>
              {info.steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
