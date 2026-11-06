import React from "react";
import API from "../services/api";
import { formatDate } from "../utils/formatDateTime";

/* Small, dependency-free chart primitives (plain divs/SVG, no chart library
   to install) for an HR-style analytics look: stat tiles up top, horizontal
   bar charts for workload/utilization breakdowns. Shared between
   RegistrarDashboard (institution-wide) and FacultyDashboard (Dean's own
   department) so both Analytics tabs look consistent. */

// a figure is colored only when the color means something (red = problem, amber = needs attention); otherwise plain text
const STATUS_ACCENT = new Set(["#b91c1c", "#b91c1c", "#c0392b", "#dc2626", "#991b1b", "#b45309", "#92400e", "#96690a"]);

export function StatTile({ label, value, accent = "#003366" }) {
  return (
    <div style={{
      background: "white", border: "1px solid #e5e7eb", borderRadius: 6,
      padding: "8px 12px", minWidth: "140px", flex: "1 1 140px",
    }}>
      <div style={{ fontSize: "12px", color: "#6b7280", marginBottom: "2px" }}>{label}</div>
      <div style={{ fontSize: "18px", fontWeight: 600, color: STATUS_ACCENT.has(String(accent).toLowerCase()) ? accent : "#111827",
        fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

/* Horizontal bar chart -- labels can be long (usernames, room names), so
   bars run left-to-right instead of a vertical column chart. */
export function HBarChart({ data, color = "#003366", unit = "", emptyText = "No data yet." }) {
  if (!data || data.length === 0) {
    return <p style={{ color: "#6b7280", fontSize: "13px" }}>{emptyText}</p>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="chart-scroll" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {data.map((d) => (
        <div key={d.label} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            title={d.label}
            style={{
              width: "130px", flexShrink: 0, fontSize: "13px", color: "#111827",
              textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}
          >
            {d.label}
          </div>
          <div style={{ flex: 1, background: "#f3f4f6", borderRadius: 2, height: "14px" }}>
            <div
              style={{
                width: `${Math.max(2, (d.value / max) * 100)}%`, background: color,
                height: "100%", borderRadius: 2,
              }}
            />
          </div>
          <div style={{ minWidth: "56px", flexShrink: 0, fontSize: "13px", color: "#111827", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
            {d.value}{unit}
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
        .catch(() => { if (!cancelled) setResults(null); })
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
        !results || results.length === 0 ? (
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
