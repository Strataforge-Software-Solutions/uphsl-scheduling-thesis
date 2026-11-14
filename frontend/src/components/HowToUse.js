import React, { useState } from "react";
import { HOWTO } from "./howto";

export function SimplifiedGuide({
  steps,
  title = "How to use this tab (Simplified)",
}) {
  return (
    <section className="coverage-panel coverage-howto-panel page-simplified-guide">
      <div className="coverage-panel-heading">
        <span className="coverage-panel-icon">
          <svg className="coverage-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 11v5M12 8h.01" />
          </svg>
        </span>
        <div>
          <h3>{title}</h3>
        </div>
      </div>
      <div className="coverage-steps">
        {steps.map((step, index) => (
          <React.Fragment key={step}>
            <div>
              <b>{index + 1}</b>
              <span>{step}</span>
            </div>
            {index < steps.length - 1 && <i aria-hidden="true">›</i>}
          </React.Fragment>
        ))}
      </div>
    </section>
  );
}

/* A compact, consistent guide shared by every dashboard role and tab. */
export default function HowToUse({ role, tab }) {
  const info = HOWTO[role]?.[tab];
  const [open, setOpen] = useState(false);
  if (!info) return null;

  const steps = info.steps || [];
  const visibleSteps = steps.slice(0, 3);
  const moreSteps = steps.slice(3);
  const contentId = `howto-${role}-${tab}`;

  return (
    <section
      className={`howto${tab === "curriculum" ? " howto-curriculum" : ""}`}
      aria-label="How to use this tab"
    >
      <button
        type="button"
        className="howto-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={contentId}
      >
        <span className="howto-info-icon" aria-hidden="true">
          i
        </span>
        <span className="howto-title">How to use this tab (Simplified)</span>
        <span className="howto-toggle-action">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="howto-content" id={contentId}>
          <div className="howto-steps">
            {visibleSteps.map((step, index) => (
              <React.Fragment key={index}>
                <div className="howto-step">
                  <b>{index + 1}</b>
                  <span>{step}</span>
                </div>
                {index < visibleSteps.length - 1 && <i aria-hidden="true">›</i>}
              </React.Fragment>
            ))}
          </div>
          {moreSteps.length > 0 && (
            <details className="howto-more">
              <summary>More steps ({moreSteps.length})</summary>
              <ol>
                {moreSteps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
