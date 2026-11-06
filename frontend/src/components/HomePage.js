import React, { useEffect, useState } from "react";
import API, { onSchedulesChanged } from "../services/api";
import { HOWTO, HOME_INTRO } from "./howto";

/* Homepage shown first on the Dean, Registrar and SHS / JHS Principal dashboards.
   Props: role ("dean" | "registrar" | "principal"), name, scope (e.g. college or school level), nav (sidebar items),
   onNavigate(tabKey), stats [{label, value, accent}], tasks [{text, tab, tone}], status [text], extra (optional node). */
const card = { background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 16px", marginBottom: 16 };
const h = { margin: "0 0 8px", fontSize: 14, fontWeight: 600, color: "#111827" };
const ROLE = { dean: "Dean", registrar: "Registrar", principal: "Principal" };

function useNotifications() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    let live = true;
    const load = () => API.get("/notifications/").then((r) => live && setItems((r.data || []).slice(0, 5))).catch(() => live && setItems([]));
    load();
    const off = onSchedulesChanged(load), t = setInterval(load, 30000);
    return () => { live = false; off(); clearInterval(t); };
  }, []);
  return items;
}

export default function HomePage({ role, name, scope, nav = [], onNavigate, stats = [], tasks = [], status = [], extra = null, skip = [] }) {
  const notes = useNotifications();
  const tabs = nav.filter((i) => i.key && !skip.includes(i.key) && HOWTO[role]?.[i.key]);
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 14, color: "#374151" }}>
          {name ? <strong style={{ fontWeight: 600, color: "#111827" }}>{name}</strong> : null}
          {[ROLE[role], scope].filter(Boolean).map((x) => <span key={x}> · {x}</span>)}
        </div>
        <p style={{ margin: "4px 0 0", fontSize: 13, lineHeight: 1.55, color: "#6b7280", maxWidth: 860 }}>{HOME_INTRO[role]}</p>
      </div>

      {stats.length > 0 && (
        // one compact summary line (label above value), separated by thin rules -- not a row of big tiles
        <div aria-label="Summary" style={{ ...card, display: "flex", flexWrap: "wrap", padding: 0 }}>
          {stats.map((s, i) => (
            <div key={s.label} style={{ flex: "1 1 120px", padding: "10px 16px", borderLeft: i ? "1px solid #e5e7eb" : "none" }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>{s.label}</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: s.accent && s.accent !== "#15803d" ? s.accent : "#111827",
                fontVariantNumeric: "tabular-nums", marginTop: 2 }}>{s.value ?? "…"}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16 }}>
        <div style={card}>
          <h3 style={h}>Pending tasks</h3>
          {tasks.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>No pending tasks.</p> : (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
              {tasks.map((t, i) => (
                <li key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid #f3f4f6" }}>
                  <span style={{ color: t.tone === "bad" ? "#b91c1c" : "#92400e" }}>{t.text}</span>
                  {t.tab && <button type="button" onClick={() => onNavigate(t.tab)} style={{ border: "1px solid #d1d5db", background: "white", color: "#374151", borderRadius: 4, padding: "3px 10px", cursor: "pointer", fontSize: 12 }}>Open</button>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div style={card}>
          <h3 style={h}>Scheduling status</h3>
          {status.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>Loading…</p> : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>{status.map((s, i) => <li key={i}>{s}</li>)}</ul>
          )}
        </div>
        <div style={card}>
          <h3 style={h}>Recent notifications</h3>
          {notes === null ? <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>Loading…</p>
            : notes.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>No notifications.</p> : (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
                {notes.map((n) => <li key={n.id} style={{ fontWeight: n.is_read ? 400 : 600 }}>{n.message || n.title}</li>)}
              </ul>)}
        </div>
      </div>

      {extra}

      <h3 style={{ ...h, fontSize: 16, marginTop: 8 }}>What you can do in each tab</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(250px,1fr))", gap: 12, marginBottom: 24 }}>
        {tabs.map((t) => {
          const info = HOWTO[role][t.key];
          return (
            <div key={t.key} style={{ ...card, marginBottom: 0 }}>
              <button type="button" onClick={() => onNavigate(t.key)} style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 14, fontWeight: 600, color: "#003366", textAlign: "left", textDecoration: "underline", textUnderlineOffset: 3 }}>
                {t.label}
              </button>
              <p style={{ margin: "6px 0", fontSize: 12.5, color: "#4b5563" }}>{info.summary}</p>
              <details style={{ fontSize: 12.5, color: "#374151" }}>
                <summary style={{ cursor: "pointer", color: "#374151" }}>Step by step</summary>
                <ol style={{ margin: "6px 0 0", paddingLeft: 18, lineHeight: 1.55 }}>{info.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              </details>
            </div>
          );
        })}
      </div>
    </div>
  );
}
