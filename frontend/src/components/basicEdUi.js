import React from "react";
import API from "../services/api";
import { formatTime } from "../utils/formatDateTime";

/* Small shared bits for the SHS / JHS dashboards. */
export const DAYS = [["Mon", "Monday"], ["Tue", "Tuesday"], ["Wed", "Wednesday"], ["Thu", "Thursday"], ["Fri", "Friday"]];
export const inputStyle = { padding: "9px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "13px", background: "white", boxSizing: "border-box" };
export const cardStyle = { background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px", boxShadow: "none", marginBottom: "18px" };
export const labelStyle = { display: "block", fontSize: "13px", fontWeight: 600, color: "#374151", marginBottom: "5px" };
export const btn = { padding: "8px 14px", borderRadius: 6, border: "1px solid #d1d5db", background: "white", color: "#111827", cursor: "pointer", fontSize: "13px" };
export const btnPrimary = { ...btn, background: "#003366", color: "white", border: "1px solid #003366" };

/** Every call carries the school level (a principal's own level is enforced by the server anyway). */
export const be = {
  get: (level, path, params = {}) => API.get(`/basic-ed/${path}`, { params: { level, ...params } }),
  post: (level, path, data = {}, params = {}) => API.post(`/basic-ed/${path}`, { level, ...data }, { params: { level, ...params } }),
  patch: (level, path, data = {}) => API.patch(`/basic-ed/${path}`, data, { params: { level } }),
  del: (level, path) => API.delete(`/basic-ed/${path}`, { params: { level } }),
};

export function errText(err, fallback = "Something went wrong.") {
  const d = err?.response?.data;
  if (!d) return err?.message === "Network Error" ? "Can't reach the server." : fallback;
  if (typeof d === "string") return d.slice(0, 200);
  if (d.detail) return Array.isArray(d.detail) ? d.detail.join(" ") : String(d.detail);
  const first = Object.entries(d)[0];
  if (first) return `${first[0]}: ${Array.isArray(first[1]) ? first[1].join(" ") : first[1]}`;
  return fallback;
}

export function hhmm(t) { return (t || "").slice(0, 5); }
export function ampm(t) {
  return formatTime(t);          // follows My settings (12- or 24-hour)
}

export function Field({ label, children, style }) {
  return <div style={style}><label style={labelStyle}>{label}</label>{children}</div>;
}

export function Modal({ title, onClose, children, width = 560 }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "white", borderRadius: 6, padding: "22px 24px", width: "100%", maxWidth: width, maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h3 style={{ margin: 0, color: "#003366" }}>{title}</h3>
          <button onClick={onClose} style={{ ...btn, padding: "4px 10px" }}>Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Notice({ tone = "info", children }) {
  const c = { info: ["#eff6ff", "#1e3a8a"], warn: ["#fffbeb", "#92400e"], error: ["#fef2f2", "#991b1b"], ok: ["#f0fdf4", "#166534"] }[tone];
  return <div style={{ background: c[0], color: c[1], borderRadius: 6, padding: "10px 14px", fontSize: "13px", marginBottom: "12px" }}>{children}</div>;
}

export const STATUS_LABEL = { draft: "Draft", submitted: "Awaiting principal", revision_requested: "Revision requested", approved: "Approved", published: "Published", superseded: "Superseded" };
export const STATUS_TONE = { draft: "warning", submitted: "warning", revision_requested: "warning", approved: "success", published: "success", superseded: "neutral" };
