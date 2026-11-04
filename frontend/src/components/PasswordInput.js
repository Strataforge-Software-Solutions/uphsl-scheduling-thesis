import React, { useState } from "react";

/** Password field with an eye button that shows / hides what is typed. Drop-in for <input type="password">: same props. */
export default function PasswordInput({ style, color = "#64748b", ...props }) {
  const [shown, setShown] = useState(false);
  const label = shown ? "Hide password" : "Show password";
  return (
    <div style={{ position: "relative", width: "100%" }}>
      <input {...props} type={shown ? "text" : "password"} style={{ ...style, paddingRight: 42 }} />
      <button
        type="button" onClick={() => setShown((v) => !v)} aria-label={label} title={label} aria-pressed={shown}
        style={{ position: "absolute", top: "50%", right: 8, transform: "translateY(-50%)", width: 30, height: 30, minWidth: 0,
          margin: 0, padding: 0, border: "none", background: "transparent", borderRadius: 6, cursor: "pointer", color,
          display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "none" }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {shown ? (
            <>
              <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
              <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
              <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </>
          ) : (
            <>
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </>
          )}
        </svg>
      </button>
    </div>
  );
}
