import React, { useEffect, useState } from "react";
import API, { onSchedulesChanged } from "../services/api";
import { StatTile } from "./Charts";
import { HOWTO, HOME_INTRO } from "./howto";

/* Homepage shown first on the Dean, Registrar and SHS / JHS Principal dashboards.
   Props: role ("dean" | "registrar" | "principal"), name, scope (e.g. college or school level), nav (sidebar items),
   onNavigate(tabKey), stats [{label, value, accent}], tasks [{text, tab, tone}], status [text], extra (optional node). */
const card = { background: "white", border: "1px solid #e0e6ed", borderRadius: 10, padding: "14px 16px", marginBottom: 16 };
const h = { margin: "0 0 8px", fontSize: 14.5, color: "#003366" };

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
      <div style={{ ...card, background: "linear-gradient(135deg,#003366,#1d4f91)", color: "white", border: "none" }}>
        <h2 style={{ margin: "0 0 6px", fontSize: 22 }}>Welcome to U-FAST Scheduling System</h2>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, maxWidth: 820 }}>
          {name ? <b>{name}{scope ? ` · ${scope}` : ""}. </b> : null}{HOME_INTRO[role]}
        </p>
      </div>

      {stats.length > 0 && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          {stats.map((s) => <StatTile key={s.label} label={s.label} value={s.value ?? "…"} accent={s.accent} />)}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16 }}>
        <div style={card}>
          <h3 style={h}>Pending tasks</h3>
          {tasks.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#15803d" }}>Nothing needs your attention right now.</p> : (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
              {tasks.map((t, i) => (
                <li key={i} style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
                  <span style={{ color: t.tone === "bad" ? "#b91c1c" : "#92400e" }}>{t.text}</span>
                  {t.tab && <button type="button" onClick={() => onNavigate(t.tab)} style={{ border: "1px solid #003366", background: "white", color: "#003366", borderRadius: 6, padding: "2px 10px", cursor: "pointer", fontSize: 12 }}>Open</button>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div style={card}>
          <h3 style={h}>Scheduling status</h3>
          {status.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>Loading…</p> : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>{status.map((s, i) => <li key={i}>{s}</li>)}</ul>
          )}
        </div>
        <div style={card}>
          <h3 style={h}>Recent notifications</h3>
          {notes === null ? <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>Loading…</p>
            : notes.length === 0 ? <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>No notifications yet.</p> : (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
                {notes.map((n) => <li key={n.id} style={{ fontWeight: n.is_read ? 400 : 600 }}>{n.message || n.title}</li>)}
              </ul>)}
        </div>
      </div>

      {extra}

      <h3 style={{ ...h, marginTop: 8 }}>Quick links — what you can do in each tab</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(250px,1fr))", gap: 14, marginBottom: 20 }}>
        {tabs.map((t) => {
          const info = HOWTO[role][t.key];
          return (
            <div key={t.key} style={{ ...card, marginBottom: 0 }}>
              <button type="button" onClick={() => onNavigate(t.key)} style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#003366", textAlign: "left" }}>
                {t.icon} {t.label} →
              </button>
              <p style={{ margin: "6px 0", fontSize: 12.5, color: "#475569" }}>{info.summary}</p>
              <details style={{ fontSize: 12.5, color: "#334155" }}>
                <summary style={{ cursor: "pointer", color: "#1d4f91" }}>Step by step</summary>
                <ol style={{ margin: "6px 0 0", paddingLeft: 18, lineHeight: 1.55 }}>{info.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              </details>
            </div>
          );
        })}
      </div>
    </div>
  );
}
