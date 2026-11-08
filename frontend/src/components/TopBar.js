import React, { useState, useEffect, useRef } from "react";
import { reportLoadError } from "../services/loadError";
import API, { logout } from "../services/api";
import { notificationTarget, jumpTo } from "../services/jump";
import { useNavigate } from "react-router-dom";
import { usePreferences, initialsOf } from "../services/preferences";
import { formatDate } from "../utils/formatDateTime";

// what each notification is about, as a short word (no icons)
const TYPE_LABEL = {
  schedule_update: "Schedule",
  conflict_alert: "Conflict",
  exam_assignment: "Exam",
  substitute_assignment: "Substitute",
};

/* Line-drawn bell (24 x 24, 1.75 stroke), drawn inline: no icon library. */
function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

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
  return formatDate(iso);
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
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-expanded={open}
        style={{
          position: "relative", background: open ? "#f3f4f6" : "transparent", color: "#374151", border: "1px solid transparent",
          cursor: "pointer", width: 34, height: 34, padding: 0, borderRadius: 6, display: "inline-flex",
          alignItems: "center", justifyContent: "center",
        }}
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span aria-hidden="true" style={{
            position: "absolute", top: 2, right: 1, background: "#b91c1c", color: "white", border: "2px solid white",
            borderRadius: 999, fontSize: 10, fontWeight: 600, padding: "0 4px", lineHeight: "14px",
            minWidth: 18, textAlign: "center", boxSizing: "border-box",
          }}>
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div role="dialog" aria-label="Notifications" style={{
          position: "absolute", right: 0, top: "calc(100% + 6px)", width: "min(360px, 92vw)", maxHeight: "420px",
          overflowY: "auto", background: "white", borderRadius: 6, border: "1px solid #e5e7eb",
          boxShadow: "var(--shadow-pop)", zIndex: 1000,
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "10px 12px", borderBottom: "1px solid #e5e7eb", position: "sticky", top: 0, background: "white",
          }}>
            <strong style={{ fontSize: 14, color: "#111827", fontWeight: 600 }}>Notifications</strong>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                style={{ background: "transparent", border: "none", color: "#003366", fontSize: 12, cursor: "pointer", fontWeight: 600, padding: "2px 4px" }}
              >
                Mark all as read
              </button>
            )}
          </div>

          {loading ? (
            <p style={{ padding: 16, fontSize: 13, color: "#6b7280", margin: 0 }}>Loading…</p>
          ) : items.length === 0 ? (
            <p style={{ padding: 16, fontSize: 13, color: "#6b7280", margin: 0 }}>No notifications.</p>
          ) : (
            items.map((n) => (
              <div
                key={n.id}
                onClick={() => {
                  if (!n.is_read) markRead(n.id);
                  const target = notificationTarget(n);
                  if (target) { setOpen(false); jumpTo(target); }
                }}
                title={notificationTarget(n) ? "Open the Gen Ed move requests" : n.is_read ? undefined : "Mark as read"}
                style={{
                  display: "flex", gap: 10, padding: "10px 12px", borderBottom: "1px solid #f3f4f6",
                  background: n.is_read ? "white" : "#f5f8fc", cursor: n.is_read && !notificationTarget(n) ? "default" : "pointer",
                  borderLeft: `3px solid ${n.is_read ? "transparent" : "#003366"}`,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontSize: 13, color: "#111827", lineHeight: 1.45, fontWeight: n.is_read ? 400 : 600 }}>{n.message}</p>
                  <p style={{ margin: "4px 0 0", fontSize: 12, color: "#6b7280" }}>
                    {TYPE_LABEL[n.notif_type] || "Notice"} · {timeAgo(n.created_at)}{n.is_read ? "" : " · Unread"}
                    {notificationTarget(n) && <span style={{ color: "#003366", fontWeight: 600, textDecoration: "underline" }}> · Open</span>}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/* Avatar: the profile picture (or initials in a plain circle) and a small menu with "My settings". */
function AvatarMenu({ userName }) {
  const { pictureUrl, profile } = usePreferences();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const initials = profile ? initialsOf(profile.first_name, profile.last_name, userName) : initialsOf("", "", userName);
  const name = profile ? (`${profile.first_name} ${profile.last_name}`.trim() || profile.username) : userName;
  return (
    <div className="app-avatar-wrap" ref={wrap}>
      <button type="button" className="app-avatar-btn" aria-haspopup="menu" aria-expanded={open} aria-label="Account menu"
        onClick={() => setOpen((o) => !o)}>
        {pictureUrl
          ? <img className="app-avatar-img" src={pictureUrl} alt="" width="30" height="30" />
          : <span className="app-avatar-circle small" aria-hidden="true">{initials}</span>}
      </button>
      {open && (
        <div className="app-avatar-menu" role="menu">
          <div className="app-avatar-menu-head">
            <div className="app-avatar-menu-name">{name}</div>
            {profile && <div className="app-avatar-menu-role">{profile.role}</div>}
          </div>
          <button type="button" role="menuitem" className="app-avatar-menu-item" onClick={() => { setOpen(false); navigate("/settings"); }}>My settings</button>
          <button type="button" role="menuitem" className="app-avatar-menu-item app-avatar-menu-signout" onClick={() => { setOpen(false); logout(); window.location.href = "/login"; }}>Sign out</button>
        </div>
      )}
    </div>
  );
}

function TopBar({ crumb, userName }) {
  return (
    <div className="app-topbar">
      <div className="app-breadcrumb">
        <span>U-FAST</span>
        <span className="app-breadcrumb-sep">›</span>
        <span className="app-breadcrumb-current">{crumb}</span>
      </div>
      <div className="app-topbar-right">
        <NotificationBell />
        <AvatarMenu userName={userName} />
      </div>
    </div>
  );
}

export default TopBar;
