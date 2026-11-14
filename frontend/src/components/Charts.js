import React, { useEffect, useRef, useState } from "react";
import API from "../services/api";
import { formatDate } from "../utils/formatDateTime";

/* Small, dependency-free chart primitives (plain divs/SVG, no chart library
   to install) for an HR-style analytics look: stat tiles up top, horizontal
   bar charts for workload/utilization breakdowns. Shared between
   RegistrarDashboard (institution-wide) and FacultyDashboard (Dean's own
   department) so both Analytics tabs look consistent. */

// a figure is colored only when the color means something (red = problem, amber = needs attention); otherwise plain text
const STATUS_ACCENT = new Set(["#b91c1c", "#b91c1c", "#c0392b", "#dc2626", "#991b1b", "#b45309", "#92400e", "#96690a"]);

export function AnimatedMetricValue({ value }) {
  const text = value === null || value === undefined ? "" : String(value);
  const match = /^(-?\d+(?:\.\d+)?)(.*)$/.exec(text);
  const suffix = match?.[2] || "";
  const numeric = Boolean(match) && !suffix.trimStart().startsWith("/");
  const target = numeric ? Number(match[1]) : 0;
  const decimals = numeric ? (match[1].split(".")[1] || "").length : 0;
  const initialReduced = typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const initialSetting = typeof document === "undefined" ? "off" : document.documentElement.getAttribute("data-reduce-motion");
  const initialValue = initialSetting === "on" || (initialSetting !== "off" && initialReduced) ? target : 0;
  const [display, setDisplay] = useState(() => {
    if (!numeric || !Number.isFinite(target)) return target;
    return initialValue;
  });
  const displayRef = useRef(display);

  useEffect(() => {
    if (!numeric || !Number.isFinite(target)) { displayRef.current = target; setDisplay(target); return undefined; }
    const motionSetting = document.documentElement.getAttribute("data-reduce-motion");
    const systemReduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (motionSetting === "on" || (motionSetting !== "off" && systemReduced)) { displayRef.current = target; setDisplay(target); return undefined; }
    if (typeof window.requestAnimationFrame !== "function") { displayRef.current = target; setDisplay(target); return undefined; }
    const from = displayRef.current;
    const started = performance.now();
    let frame = 0;
    const step = (now) => {
      const progress = Math.min(1, (now - started) / 650);
      const next = from + (target - from) * (1 - Math.pow(1 - progress, 3));
      displayRef.current = next;
      setDisplay(next);
      if (progress < 1) frame = window.requestAnimationFrame(step);
    };
    frame = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(frame);
  }, [text, numeric, target]);

  const shown = numeric && Number.isFinite(target) ? `${display.toFixed(decimals)}${suffix}` : text;
  return <span aria-label={text}>{shown}</span>;
}

export function StatTile({ label, value, accent = "#003366", icon }) {
  return (
    <div className={icon ? "analytics-stat-tile analytics-stat-tile-with-icon" : "analytics-stat-tile"} style={{
      background: "white", border: "1px solid #e5e7eb", borderRadius: 6,
      padding: "8px 12px", minWidth: "140px", flex: "1 1 140px",
    }}>
      {icon && <div className="analytics-stat-icon">{icon}</div>}
      <div className="analytics-stat-copy">
        <div style={{ fontSize: "12px", color: "#6b7280", marginBottom: "2px" }}>{label}</div>
        <div className="analytics-stat-value" style={{ fontSize: "18px", fontWeight: 600, color: STATUS_ACCENT.has(String(accent).toLowerCase()) ? accent : "#111827",
          fontVariantNumeric: "tabular-nums" }}><AnimatedMetricValue value={value} /></div>
      </div>
    </div>
  );
}

export function CollapsibleChartPanel({ title, ariaTitle, children, className = "analytics-chart-card", style }) {
  const [collapsed, setCollapsed] = useState(false);
  const label = ariaTitle || (typeof title === "string" ? title : "analytics panel");
  return (
    <section className={`analytics-collapsible-panel ${className}`} style={style}>
      <div className="analytics-collapsible-heading">
        <h4 className="analytics-chart-title">{title}</h4>
        <button
          type="button"
          className="analytics-collapse-button"
          aria-expanded={!collapsed}
          aria-label={`${collapsed ? "Expand" : "Collapse"} ${label}`}
          onClick={() => setCollapsed((value) => !value)}
        >
          <span>{collapsed ? "Expand" : "Collapse"}</span>
          <svg viewBox="0 0 16 16" aria-hidden="true" className={collapsed ? "is-collapsed" : ""}>
            <path d="m3.5 6 4.5 4 4.5-4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
      <div className={`analytics-collapsible-content${collapsed ? " is-collapsed" : ""}`} aria-hidden={collapsed}>
        <div className="analytics-collapsible-inner" inert={collapsed ? "" : undefined}>{children}</div>
      </div>
    </section>
  );
}

/* Horizontal bar chart -- labels can be long (usernames, room names), so
   bars run left-to-right instead of a vertical column chart. */
export function HBarChart({ data, color = "#003366", unit = "", emptyText = "No data yet.", loading = false }) {
  if (loading) return <div className="chart-skeleton-list" role="status" aria-label="Loading chart data">{Array.from({ length: 5 }, (_, i) => <div className="chart-skeleton-row" key={i}><span /><i /><span /></div>)}</div>;
  if (!data || data.length === 0) {
    return <p style={{ color: "#6b7280", fontSize: "13px" }}>{emptyText}</p>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="chart-scroll chart-bar-list" role="list" aria-label="Chart data" tabIndex={0} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {data.map((d, index) => (
        <div key={d.label} className="chart-bar-row" role="listitem" aria-label={`${d.name ? `${d.name} (${d.label})` : d.label}: ${d.value}${unit}`} title={`${d.name ? `${d.name} (${d.label})` : d.label}: ${d.value}${unit}`} data-tooltip={d.name ? `${d.name} (${d.label}) · ${d.value}${unit}` : undefined} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            title={d.name ? `${d.name} (${d.label})` : d.label}
            style={{
              width: "130px", flexShrink: 0, fontSize: "13px", color: "#111827",
              textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}
          >
            {d.label}
          </div>
          <div style={{ flex: 1, background: "#f3f4f6", borderRadius: 2, height: "14px" }}>
            <div
              className="motion-chart-bar"
              style={{
                width: `${Math.max(2, (d.value / max) * 100)}%`, background: color,
                height: "100%", borderRadius: 2, animationDelay: `${Math.min(index * 28, 196)}ms`,
              }}
            />
          </div>
          <div style={{ minWidth: "56px", flexShrink: 0, fontSize: "13px", color: "#111827", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
            <AnimatedMetricValue value={`${d.value}${unit}`} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* Day (Mon-Sat) x time-of-day (Morning/Afternoon/Evening) heatmap grid --
   darker cell = more historical meetings in that slot, for a given faculty's
   compute_faculty_patterns() result. */
const HEATMAP_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HEATMAP_BUCKETS = ["Morning", "Afternoon", "Evening"];

export function PatternHeatmap({ patterns, color = "3, 51, 102" /* rgb for #003366 */ }) {
  if (!patterns || patterns.length === 0) {
    return <p style={{ color: "#6b7280", fontSize: "13px" }}>No historical pattern data.</p>;
  }
  const byKey = {};
  let max = 1;
  for (const p of patterns) {
    const dayAbbrev = (p.day || "").slice(0, 3);
    byKey[`${dayAbbrev}|${p.time_of_day}`] = p;
    if (p.count > max) max = p.count;
  }
  const daysPresent = HEATMAP_DAYS.filter((d) => patterns.some((p) => (p.day || "").slice(0, 3) === d));
  const days = daysPresent.length ? daysPresent : HEATMAP_DAYS.slice(0, 6);

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ padding: "6px 10px", fontSize: "12px", color: "#6b7280" }}></th>
            {days.map((d) => (
              <th key={d} style={{ padding: "6px 10px", fontSize: "12px", color: "#6b7280", textAlign: "center" }}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {HEATMAP_BUCKETS.map((bucket) => (
            <tr key={bucket}>
              <td style={{ padding: "6px 10px", fontSize: "12px", color: "#111827", fontWeight: 600 }}>{bucket}</td>
              {days.map((d) => {
                const cell = byKey[`${d}|${bucket}`];
                const alpha = cell ? Math.max(0.12, cell.count / max) : 0;
                return (
                  <td key={d} style={{ padding: "2px" }}>
                    <div
                      title={cell ? `${cell.count} occurrence(s) (${cell.share_pct}%)` : "No data"}
                      style={{
                        width: "52px", height: "36px", borderRadius: 3,
                        background: `rgba(${color}, ${alpha})`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "12px", fontWeight: 600,
                        color: alpha > 0.5 ? "white" : "#111827",
                      }}
                    >
                      {cell ? cell.count : ""}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* "What subject was historically scheduled at this day+time(+room)?" --
   a small reference box, fed by the imported 2021-2026 historical data, for
   use next to a manual schedule or exam slot form so staff aren't guessing
   what belongs in a given day/time. Pass whatever is already picked in the
   surrounding form; it debounces its own lookup and renders nothing until
   day+startTime are both set. */
export function HistoricalHint({ day, startTime, endTime, roomName }) {
  const [results, setResults] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!day || !startTime) { setResults(null); return; }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(() => {
      API.get("/analytics/historical-lookup/", {
        params: { day, start_time: startTime, end_time: endTime || undefined, room: roomName || undefined },
      })
        .then((res) => { if (!cancelled) setResults(res.data.results); })
        .catch((err) => { if (!cancelled) setResults(err.response?.status === 403 ? "forbidden" : null); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 300); // light debounce so it doesn't fire on every keystroke
    return () => { cancelled = true; clearTimeout(t); };
  }, [day, startTime, endTime, roomName]);

  if (!day || !startTime) return null;

  return (
    <div style={{
      marginTop: "8px", padding: "8px 12px", background: "#f9fafb", border: "1px solid #e5e7eb",
      borderRadius: 6, fontSize: "13px", color: "#374151",
    }}>
      <strong style={{ fontWeight: 600 }}>Historical reference:</strong>{" "}
      {loading ? "checking 2021–2026 records…" : (
        results === "forbidden" ? (
          <span>Historical reference is available to the Registrar and IT admin.</span>
        ) : !results || results.length === 0 ? (
          <span>No historical record for this day/time{roomName ? ` in ${roomName}` : ""}.</span>
        ) : (
          <span>
            Previously used for:{" "}
            {results.slice(0, 3).map((r, i) => (
              <span key={i}>
                {i > 0 && "; "}
                <strong>{r.subject_code}</strong>{r.description ? ` (${r.description})` : ""}
                {r.teacher_name ? ` — ${r.teacher_name}` : ""}
                {r.school_year ? ` [${r.school_year}${r.semester ? " " + r.semester : ""}]` : ""}
              </span>
            ))}
          </span>
        )
      )}
    </div>
  );
}


const ACTIVITY_LABEL = { generated: "Generated", approved: "Approved", exam: "Exam", conflict: "Conflict" };

function timeAgo(iso) {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} hr ago`;
  if (secs < 7 * 86400) return `${Math.floor(secs / 86400)} day${secs >= 2 * 86400 ? "s" : ""} ago`;
  return formatDate(iso);
}

/* Recent activity feed: newest first, from /analytics/ -> recent_activity. */
export function RecentActivity({ items }) {
  if (!items || items.length === 0) {
    return <p style={{ color: "#6b7280", fontSize: "13px" }}>No activity yet.</p>;
  }
  return (
    <ul className="chart-scroll" style={{ listStyle: "none", margin: 0, padding: "0 6px 0 0", maxHeight: "420px" }}>
      {items.map((it, i) => (
        <li key={i} style={{
          display: "flex", gap: "12px", alignItems: "flex-start", padding: "10px 0",
          borderTop: i === 0 ? "none" : "1px solid #f3f4f6",
        }}>
          <span style={{ fontSize: "12px", lineHeight: "20px", color: it.type === "conflict" ? "#b91c1c" : "#4b5563", fontWeight: 600, minWidth: 72 }}>{ACTIVITY_LABEL[it.type] || "Update"}</span>
          <span style={{ flex: 1, fontSize: "14px", color: "#111827" }}>{it.text}</span>
          <span style={{ fontSize: "12px", color: "#6b7280", whiteSpace: "nowrap" }}>{timeAgo(it.when)}</span>
        </li>
      ))}
    </ul>
  );
}
