import React, { useState, useEffect, useRef } from "react";
import { reportLoadError } from "../services/loadError";
import API from "../services/api";

const TYPE_ICON = {
  schedule_update: "🗓",
  conflict_alert: "⚠️",
  exam_assignment: "📝",
  substitute_assignment: "🙋",
};

function timeAgo(iso) {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

/* Real notification bell -- was previously just a decorative emoji with no
   click handler, unread count, or dropdown, even though the backend
   Notification model/API already existed. Polls the lightweight
   unread_count endpoint every 30s so the badge stays current without
   pulling every notification, and only fetches the full list when the
   dropdown is actually opened. */
function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);

  const refreshCount = () => {
    API.get("/notifications/unread_count/")
      .then((res) => setUnreadCount(res.data.unread_count))
      .catch(() => {});
  };

  useEffect(() => {
    refreshCount();
    const t = setInterval(refreshCount, 30000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      API.get("/notifications/")
        .then((res) => setItems(res.data))
        .catch(reportLoadError("the notifications"))
        .finally(() => setLoading(false));
    }
  };

  const markRead = async (id) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    setUnreadCount((c) => Math.max(0, c - 1));
    try {
      await API.patch(`/notifications/${id}/`, { is_read: true });
    } catch {
      refreshCount();
    }
  };

  const markAllRead = async () => {
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    try {
      await API.post("/notifications/mark_all_read/");
    } catch {
      refreshCount();
    }
  };

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button
        onClick={toggleOpen}
        title="Notifications"
        aria-label="Notifications"
        style={{
          position: "relative", background: "none", border: "none", cursor: "pointer",
          fontSize: "18px", lineHeight: 1, padding: "4px",
        }}
      >
        🔔
        {unreadCount > 0 && (
          <span style={{
            position: "absolute", top: "-2px", right: "-4px", background: "#a4231a", color: "white",
            borderRadius: "999px", fontSize: "10px", fontWeight: 700, padding: "1px 5px", lineHeight: 1.3,
            minWidth: "16px", textAlign: "center",
          }}>
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: "absolute", right: 0, top: "calc(100% + 8px)", width: "340px", maxHeight: "420px",
          overflowY: "auto", background: "white", borderRadius: "12px", border: "1px solid #e0e6ed",
          boxShadow: "0 12px 32px rgba(0,0,0,0.18)", zIndex: 1000,
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "12px 14px", borderBottom: "1px solid #eef1f5",
          }}>
            <strong style={{ fontSize: "13.5px", color: "#0f172a" }}>Notifications</strong>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                style={{ background: "none", border: "none", color: "#003366", fontSize: "12px", cursor: "pointer", fontWeight: 600 }}
              >
                Mark all read
              </button>
            )}
          </div>

          {loading ? (
            <p style={{ padding: "16px", fontSize: "13px", color: "#64748b", margin: 0 }}>Loading…</p>
          ) : items.length === 0 ? (
            <p style={{ padding: "16px", fontSize: "13px", color: "#64748b", margin: 0 }}>No notifications yet.</p>
          ) : (
            items.map((n) => (
              <div
                key={n.id}
                onClick={() => !n.is_read && markRead(n.id)}
                style={{
                  display: "flex", gap: "10px", padding: "12px 14px", borderBottom: "1px solid #f3f5f8",
                  background: n.is_read ? "white" : "#f3f8ff", cursor: n.is_read ? "default" : "pointer",
                }}
              >
                <span style={{ fontSize: "16px" }}>{TYPE_ICON[n.notif_type] || "🔔"}</span>
                <div style={{ flex: 1 }}>
                  <p style={{ margin: 0, fontSize: "12.5px", color: "#1f2937", lineHeight: 1.4 }}>{n.message}</p>
                  <p style={{ margin: "4px 0 0", fontSize: "11px", color: "#94a3b8" }}>{timeAgo(n.created_at)}</p>
                </div>
                {!n.is_read && (
                  <span style={{ width: "8px", height: "8px", borderRadius: "999px", background: "#003366", marginTop: "4px", flexShrink: 0 }} />
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function TopBar({ crumb, userName }) {
  const initials = (userName || "?")
    .replace(/^(dr|mr|ms|mrs|engr|prof)\.?\s+/i, "")
    .split(/[\s-]+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="app-topbar">
      <div className="app-breadcrumb">
        <span>U-FAST</span>
        <span className="app-breadcrumb-sep">›</span>
        <span className="app-breadcrumb-current">{crumb}</span>
      </div>
      <div className="app-topbar-right">
        <NotificationBell />
        <div className="app-avatar-circle small">{initials}</div>
      </div>
    </div>
  );
}

export default TopBar;
