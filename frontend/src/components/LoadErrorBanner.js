import React, { useEffect, useState } from "react";
import { LOAD_FAILED_EVENT } from "../services/loadError";

/* Shows the data loads that failed (reportLoadError), e.g. "Could not load the faculty list (server error 500)", with Reload. */
export default function LoadErrorBanner() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    const on = (e) => setItems((cur) => {
      const key = `${e.detail.what}|${e.detail.why}`;
      return cur.some((x) => x.key === key) ? cur : [...cur, { key, ...e.detail }].slice(-4);
    });
    window.addEventListener(LOAD_FAILED_EVENT, on);
    return () => window.removeEventListener(LOAD_FAILED_EVENT, on);
  }, []);
  if (!items.length) return null;
  return (
    <div role="alert" style={{ position: "fixed", left: 12, right: 12, bottom: 12, zIndex: 3000, maxWidth: 640, margin: "0 auto",
      background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 10, padding: "10px 14px", boxShadow: "0 8px 24px rgba(0,0,0,.18)", fontSize: 13, color: "#7f1d1d" }}>
      <strong>Some data could not be loaded.</strong>
      <ul style={{ margin: "6px 0 8px 18px", padding: 0 }}>
        {items.map((x) => <li key={x.key}>Could not load {x.what} ({x.why}).</li>)}
      </ul>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button type="button" onClick={() => setItems([])} style={{ background: "white", color: "#7f1d1d", border: "1px solid #fca5a5", borderRadius: 6, padding: "4px 12px", fontSize: 12.5, cursor: "pointer" }}>Dismiss</button>
        <button type="button" onClick={() => window.location.reload()} style={{ background: "#b91c1c", color: "white", border: "none", borderRadius: 6, padding: "4px 12px", fontSize: 12.5, cursor: "pointer" }}>Reload</button>
      </div>
    </div>
  );
}
