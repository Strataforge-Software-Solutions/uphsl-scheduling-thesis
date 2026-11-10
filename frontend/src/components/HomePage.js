import React, { useEffect, useState } from "react";
import API, { onSchedulesChanged } from "../services/api";
import { HOWTO, HOME_INTRO } from "./howto";
import pendingTasksImage from "../assets/pending-tasks-illustration.png";
import schedulingStatusImage from "../assets/scheduling-status-illustration.png";
import recentNotificationsImage from "../assets/recent-notifications-illustration.png";

/* Homepage shown first on the Dean, Registrar and SHS / JHS Principal dashboards.
   Props: role ("dean" | "registrar" | "principal"), name, scope (e.g. college or school level), nav (sidebar items),
   onNavigate(tabKey), stats [{label, value, accent}], tasks [{text, tab, tone}], status [text], extra (optional node). */
const ROLE = { dean: "Dean", registrar: "Registrar", principal: "Principal" };

function StatIcon({ label }) {
  const name = label.toLowerCase();
  let icon;
  if (name.includes("conflict")) {
    icon = <><path d="M10 3.2 18 17H2z" /><path d="M10 8v4m0 2.5h.01" /></>;
  } else if (name.includes("overload") || name.includes("teacher") || name.includes("faculty")) {
    icon = <><circle cx="8" cy="7" r="3" /><path d="M2.5 17c.5-2.7 2.3-4 5.5-4s5 1.3 5.5 4M14 5a2.5 2.5 0 0 1 0 4.8M14.5 13c1.7.4 2.7 1.7 3 4" /></>;
  } else if (name.includes("approved") || name.includes("verified")) {
    icon = <><circle cx="10" cy="10" r="7" /><path d="m6.5 10 2.3 2.3 4.8-5" /></>;
  } else if (name.includes("published")) {
    icon = <><path d="m10 3 7 4-7 4-7-4z" /><path d="m3 10 7 4 7-4m-14 4 7 4 7-4" /></>;
  } else if (name.includes("draft")) {
    icon = <><path d="M5 2.8h7l4 4V17a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3.8a1 1 0 0 1 1-1z" /><path d="M12 3v4h4M7 11h6m-6 3h6" /></>;
  } else if (name.includes("room")) {
    icon = <><path d="M4 18V3h12v15M2 18h16M8 18v-4h4v4" /><circle cx="13.5" cy="9" r=".5" /></>;
  } else {
    icon = <><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6.5 2.5v3M13.5 2.5v3M3.5 8h13M7 11h2m2 0h2m-6 3h2" /></>;
  }
  return <svg className="home-stat-svg" viewBox="0 0 20 20" aria-hidden="true">{icon}</svg>;
}

function InsightHeadingIcon({ type }) {
  const paths = type === "status"
    ? <path d="M3 17V11m5 6V7m5 10V3m4 14v-8" />
    : type === "pending"
      ? <><path d="M7 3H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2" /><path d="M7 2h6v4H7zM6 12l2.2 2.2L13.5 9" /></>
      : <><path d="M5 14V8a5 5 0 0 1 10 0v6l2 2H3z" /><path d="M8 18a2 2 0 0 0 4 0" /></>;
  return <svg className="home-insight-heading-icon" viewBox="0 0 20 20" aria-hidden="true">{paths}</svg>;
}

function TabIcon({ label }) {
  const name = label.toLowerCase();
  let paths;
  if (name.includes("generate")) {
    paths = <><rect x="2.5" y="5" width="12.5" height="12" rx="2" /><path d="M6.5 3v3M11.5 3v3M3 8.5h11.5M6.5 11.5h2m-2 3h2" /><path d="m16.2 2.2.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9z" /></>;
  } else if (name.includes("exam")) {
    paths = <><path d="M6 3H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2" /><path d="M6 2h8v4H6zM6 12l2.2 2.2L13.5 9" /></>;
  } else if (name.includes("conflict")) {
    paths = <><path d="M10 2.5 18.2 17H1.8z" /><path d="M10 7.5v4.2m0 2.7h.01" /></>;
  } else if (name.includes("curriculum") || name.includes("class list") || name.includes("section")) {
    paths = <><path d="M2.5 4.5c2.8-.7 5.2-.2 7.5 1.4v11c-2.3-1.6-4.7-2.1-7.5-1.4z" /><path d="M17.5 4.5c-2.8-.7-5.2-.2-7.5 1.4v11c2.3-1.6 4.7-2.1 7.5-1.4z" /></>;
  } else if (name.includes("faculty") || name.includes("teacher") || name.includes("people")) {
    paths = <><circle cx="8" cy="7" r="3" /><path d="M2.5 17c.5-2.7 2.3-4 5.5-4s5 1.3 5.5 4M14 5a2.5 2.5 0 0 1 0 4.8M14.5 13c1.7.4 2.7 1.7 3 4" /></>;
  } else if (name.includes("analytics") || name.includes("overview") || name.includes("activity")) {
    paths = <><path d="M3 17V3m0 14h14" /><path d="m5.5 13 3-3.5 2.7 1.8 4.3-5.1" /><circle cx="5.5" cy="13" r=".8" /><circle cx="8.5" cy="9.5" r=".8" /><circle cx="11.2" cy="11.3" r=".8" /><circle cx="15.5" cy="6.2" r=".8" /></>;
  } else if (name.includes("minor")) {
    paths = <><path d="m10 2.5 7.5 4.2L10 11 2.5 6.7z" /><path d="m2.5 10.5 7.5 4.2 7.5-4.2M2.5 14.3l7.5 4.2 7.5-4.2" /></>;
  } else {
    paths = <><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6.5 2.5v3M13.5 2.5v3M3.5 8h13" /></>;
  }
  return <svg className="home-tab-svg" viewBox="0 0 20 20" aria-hidden="true">{paths}</svg>;
}

function useNotifications() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    let live = true;
    const load = () => {
      if (document.visibilityState !== "visible") return;
      API.get("/notifications/", { params: { limit: 5 } })
        .then((r) => live && setItems(r.data || []))
        .catch(() => live && setItems([]));
    };
    load();
    const off = onSchedulesChanged(load), vis = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("focus", load);
    const t = setInterval(load, 120000);
    return () => { live = false; off(); document.removeEventListener("visibilitychange", vis); window.removeEventListener("focus", load); clearInterval(t); };
  }, []);
  return items;
}

export default function HomePage({ role, name, scope, nav = [], onNavigate, stats = [], tasks = [], status = [], extra = null, skip = [], hideIntro = false }) {
  const notes = useNotifications();
  const tabs = nav.filter((i) => i.key && !skip.includes(i.key) && HOWTO[role]?.[i.key]);
  const visibleScope = scope && scope.toLowerCase() !== ROLE[role]?.toLowerCase() ? scope : null;
  return (
    <div className="home-dashboard">
      {!hideIntro && <p className="home-intro">
        {name && <strong className="home-intro-name">{name}</strong>}
        {ROLE[role] && <span>{name ? " · " : ""}{ROLE[role]}</span>}
        {visibleScope && <span> · {visibleScope}</span>}
        {(name || ROLE[role] || visibleScope) && " · "}{HOME_INTRO[role]}
      </p>}

      {stats.length > 0 && (
        // one compact summary line (label above value), separated by thin rules -- not a row of big tiles
        <div className="home-summary-card" aria-label="Summary">
          {stats.map((s, i) => (
            <div className="home-stat-item" key={s.label}>
              <div className="home-stat-icon"><StatIcon label={s.label} /></div>
              <div className="home-stat-copy">
                <div className="home-stat-label">{s.label}</div>
                <div className="home-stat-value" style={s.accent && s.accent !== "#15803d" ? { color: s.accent } : undefined}>{s.value ?? "…"}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 16 }}>
        <div className="home-insight-card home-pending-card">
          <h3 className="home-insight-title"><InsightHeadingIcon type="pending" />Pending tasks</h3>
          {tasks.length === 0 ? <p className="home-insight-body">No pending tasks.</p> : (
            <ul className="home-task-list" style={{ paddingLeft: 0, listStyle: "none", fontSize: 13 }}>
              {tasks.map((t, i) => (
                <li key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid #f3f4f6" }}>
                  <span className={t.tone === "bad" ? "is-bad" : ""}>{t.text}</span>
                  {t.tab && <button className="home-task-open" type="button" onClick={() => onNavigate(t.tab)}>Open</button>}
                </li>
              ))}
            </ul>
          )}
          <img className="home-insight-illustration" src={pendingTasksImage} alt="" aria-hidden="true" />
        </div>
        <div className="home-insight-card home-status-card">
          <h3 className="home-insight-title"><InsightHeadingIcon type="status" />Scheduling status</h3>
          {status.length === 0 ? <p className="home-insight-body">Loading…</p> : (
            <ul className="home-insight-list">{status.map((s, i) => <li key={i}>{s}</li>)}</ul>
          )}
          <img className="home-insight-illustration" src={schedulingStatusImage} alt="" aria-hidden="true" />
        </div>
        <div className="home-insight-card home-notifications-card">
          <h3 className="home-insight-title"><InsightHeadingIcon type="notifications" />Recent notifications</h3>
          {notes === null ? <p className="home-insight-body">Loading…</p>
            : notes.length === 0 ? <p className="home-insight-body">No notifications.</p> : (
              <ul className="home-insight-list home-notification-list">
                {notes.slice(0, 3).map((n) => <li className={n.is_read ? "is-read" : "is-unread"} key={n.id} title={n.message || n.title}>{n.message || n.title}</li>)}
              </ul>)}
          <img className="home-insight-illustration" src={recentNotificationsImage} alt="" aria-hidden="true" />
        </div>
      </div>

      {extra}

      <h3 className="home-tab-grid-heading">What you can do in each tab</h3>
      <div className="home-tab-grid">
        {tabs.map((t) => {
          const info = HOWTO[role][t.key];
          return (
            <div className="home-tab-card" key={t.key}>
              <div className="home-tab-icon"><TabIcon label={t.label} /></div>
              <div className="home-tab-copy">
                <button type="button" className="home-tab-title" onClick={() => onNavigate(t.key)}>{t.label}</button>
                <p className="home-tab-summary">{info.summary}</p>
                <details className="home-tab-details">
                  <summary>Step by step</summary>
                  <ol>{info.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
                </details>
              </div>
              <button type="button" className="home-tab-open" aria-label={`Open ${t.label}`} onClick={() => onNavigate(t.key)}>
                <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h13m-5-5 5 5-5 5" /></svg>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
