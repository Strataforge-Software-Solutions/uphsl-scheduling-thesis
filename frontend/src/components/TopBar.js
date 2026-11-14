import React, { useState, useEffect, useRef } from "react";
import API, { logout } from "../services/api";
import { notifyToast } from "../services/toast";
import { notificationTarget, jumpTo } from "../services/jump";
import { useNavigate } from "react-router-dom";
import { usePreferences, initialsOf } from "../services/preferences";
import { formatDate } from "../utils/formatDateTime";
import usePopupPresence from "./usePopupPresence";

// what each notification is about, as a short word (no icons)
const TYPE_LABEL = {
  schedule_update: "Schedule",
  conflict_alert: "Conflict",
  exam_assignment: "Exam",
  substitute_assignment: "Substitute",
};
const NOTIFICATION_CACHE_KEY = "app_notifications_cache_v1";

function readNotificationCache() {
  try {
    const cached = JSON.parse(sessionStorage.getItem(NOTIFICATION_CACHE_KEY) || "null");
    return Array.isArray(cached?.items) ? cached.items : [];
  } catch {
    return [];
  }
}

function writeNotificationCache(items) {
  try { sessionStorage.setItem(NOTIFICATION_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), items })); }
  catch { /* cache is an optional speed-up */ }
}

function parseMoveRequest(message = "") {
  const match = message.match(/^(.+?) asks to move (.+?) from (.+?) to (.+?)\. See Schedules > Gen Ed move requests\.?$/i);
  if (!match) return null;
  return { requester: match[1], subject: match[2], currentTime: match[3], requestedTime: match[4] };
}

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
  const { present: menuPresent, closing: menuClosing } = usePopupPresence(open);
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState(readNotificationCache);
  const wrapRef = useRef(null);

  const refreshCount = () => {
    if (document.visibilityState !== "visible") return;
    API.get("/notifications/unread_count/")
      .then((res) => setUnreadCount(res.data.unread_count))
      .catch(() => {});
  };

  const refreshNotifications = () => {
    API.get("/notifications/", { params: { limit: 50 } })
      .then((res) => {
        setItems(res.data);
        writeNotificationCache(res.data);
      })
      .catch(() => {});
  };

  useEffect(() => {
    refreshCount();
    refreshNotifications();
    const vis = () => { if (document.visibilityState === "visible") refreshCount(); };
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("focus", refreshCount);
    const t = setInterval(refreshCount, 120000);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", vis); window.removeEventListener("focus", refreshCount); };
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
      refreshCount();
      refreshNotifications();
    }
  };

  const markRead = async (id) => {
    setItems((prev) => {
      const updated = prev.map((n) => (n.id === id ? { ...n, is_read: true } : n));
      writeNotificationCache(updated);
      return updated;
    });
    setUnreadCount((c) => Math.max(0, c - 1));
    try {
      await API.patch(`/notifications/${id}/`, { is_read: true });
    } catch {
      notifyToast("Could not update the notification. Try again.", "error");
      refreshCount();
    }
  };

  const markAllRead = async () => {
    setItems((prev) => {
      const updated = prev.map((n) => ({ ...n, is_read: true }));
      writeNotificationCache(updated);
      return updated;
    });
    setUnreadCount(0);
    try {
      await API.post("/notifications/mark_all_read/");
      notifyToast("All notifications marked as read.");
    } catch {
      notifyToast("Could not mark notifications as read. Try again.", "error");
      refreshCount();
    }
  };

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button
        onClick={toggleOpen}
        className={`app-notification-button${open ? " is-open" : ""}${unreadCount > 0 ? " has-unread" : ""}`}
        title="Notifications"
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-expanded={open}
        style={{ position: "relative" }}
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

      {menuPresent && (
        <div role="dialog" aria-label="Notifications" aria-hidden={menuClosing} inert={menuClosing ? "" : undefined} className={`popup-slide${menuClosing ? " is-closing" : ""}`} style={{
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

          {items.length === 0 ? (
            <p style={{ padding: 16, fontSize: 13, color: "#6b7280", margin: 0 }}>No notifications.</p>
          ) : (
            items.map((n) => {
              const target = notificationTarget(n);
              const moveRequest = parseMoveRequest(n.message);
              return <button
                key={n.id}
                type="button"
                className={`notification-card${n.is_read ? " is-read" : " is-unread"}${moveRequest ? " is-move-request" : ""}`}
                disabled={n.is_read && !target}
                onClick={() => {
                  if (!n.is_read) markRead(n.id);
                  if (target) { setOpen(false); jumpTo(target); }
                }}
                title={target ? "Review this request in Schedules" : n.is_read ? undefined : "Mark as read"}
              >
                <span className="notification-card-topline">
                  <span className={`notification-kind${moveRequest ? " is-request" : ""}`}>{moveRequest ? "Move request" : TYPE_LABEL[n.notif_type] || "Notice"}</span>
                  {!n.is_read && <span className="notification-new">New</span>}
                </span>
                {moveRequest ? (
                  <>
                    <strong className="notification-subject">{moveRequest.subject}</strong>
                    <span className="notification-requester">Requested by {moveRequest.requester}</span>
                    <span className="notification-time-change">
                      <span><small>Current time</small><strong>{moveRequest.currentTime}</strong></span>
                      <span className="notification-time-arrow" aria-hidden="true">→</span>
                      <span><small>Requested time</small><strong>{moveRequest.requestedTime}</strong></span>
                    </span>
                  </>
                ) : <span className="notification-message">{n.message}</span>}
                <span className="notification-card-footer">
                  <time dateTime={n.created_at}>{timeAgo(n.created_at)}</time>
                  <span>{target ? "Review request →" : n.is_read ? "" : "Mark read"}</span>
                </span>
              </button>;
            })
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
  const { present: menuPresent, closing: menuClosing } = usePopupPresence(open);
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
      {menuPresent && (
        <div className={`app-avatar-menu popup-slide${menuClosing ? " is-closing" : ""}`} role="menu" aria-hidden={menuClosing} inert={menuClosing ? "" : undefined}>
          <div className="app-avatar-menu-head">
            <div className="app-avatar-menu-name">{name}</div>
            {profile && <div className="app-avatar-menu-role">{profile.role}</div>}
          </div>
          <button type="button" role="menuitem" className="app-avatar-menu-item" onClick={() => {
            setOpen(false);
            const lockedAt = Date.now();
            if (!sessionStorage.getItem("app_session_started_at")) sessionStorage.setItem("app_session_started_at", String(lockedAt));
            sessionStorage.setItem("app_lock_started_at", String(lockedAt));
            sessionStorage.setItem("app_screen_locked", "true");
            window.dispatchEvent(new Event("app-screen-lock"));
          }}>Lock screen</button>
          <button type="button" role="menuitem" className="app-avatar-menu-item" onClick={() => { setOpen(false); navigate("/settings"); }}>My settings</button>
          <button type="button" role="menuitem" className="app-avatar-menu-item app-avatar-menu-signout" onClick={() => { setOpen(false); logout(); window.location.href = "/login?signedOut=1"; }}>Sign out</button>
        </div>
      )}
    </div>
  );
}

const QUICK_PAGE_KEYS = ["home", "overview", "generate", "schedules", "schedule", "timetable", "analytics", "exams", "coverage"];

function QuickPageSearch({ items = [], onNavigate }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const inputRef = useRef(null);
  const resultListRef = useRef(null);
  const { present, closing } = usePopupPresence(open);
  const pages = items.filter((item) => item.key && item.label);
  const matches = pages.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()));
  const quickPages = QUICK_PAGE_KEYS.map((key) => pages.find((item) => item.key === key)).filter(Boolean)
    .filter((item, index, list) => list.findIndex((candidate) => candidate.key === item.key) === index).slice(0, 4);
  const presets = quickPages.length ? quickPages : pages.slice(0, 4);

  useEffect(() => {
    if (!open) return undefined;
    const closeIfOutside = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener("pointerdown", closeIfOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeIfOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const navigateTo = (item) => {
    onNavigate?.(item.key);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const handleKeyDown = (event) => {
    if (event.key === "ArrowDown" && matches.length) {
      event.preventDefault();
      resultListRef.current?.querySelector("button")?.focus();
    } else if (event.key === "Enter" && matches.length) {
      event.preventDefault();
      navigateTo(matches[0]);
    }
  };

  if (!pages.length || !onNavigate) return null;

  return (
    <div className="app-quick-search" ref={wrapRef}>
      <svg className="app-quick-search-icon" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" /><path d="m13 13 4 4" /></svg>
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        value={query}
        placeholder="Search pages…"
        aria-label="Search pages and quick links"
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-expanded={present}
        aria-controls="app-quick-search-results"
        onFocus={() => setOpen(true)}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
        onKeyDown={handleKeyDown}
      />
      {present && (
        <div className={`app-quick-search-panel${closing ? " is-closing" : ""}`} role="dialog" aria-label="Quick page navigation" aria-hidden={closing} inert={closing ? "" : undefined}>
          {!query.trim() && presets.length > 0 && (
            <div className="app-quick-search-presets">
              <div className="app-quick-search-heading">Quick presets</div>
              <div className="app-quick-search-chips">
                {presets.map((item) => (
                  <button key={item.key} type="button" onClick={() => navigateTo(item)}>{item.label}</button>
                ))}
              </div>
            </div>
          )}
          <div className="app-quick-search-heading">{query.trim() ? "Search results" : "All pages"}</div>
          <div id="app-quick-search-results" className="app-quick-search-results" role="listbox" ref={resultListRef}>
            {matches.length ? matches.map((item) => (
              <button key={item.key} type="button" role="option" aria-selected="false" onClick={() => navigateTo(item)}>
                <span>{item.label}</span><span aria-hidden="true">›</span>
              </button>
            )) : <p className="app-quick-search-empty">No pages match “{query}”.</p>}
          </div>
          <div className="app-quick-search-hint">Type to filter · Enter to open · Esc to close</div>
        </div>
      )}
    </div>
  );
}

function TopBar({ crumb, userName, navItems, onNavigate }) {
  return (
    <div className="app-topbar">
      <div className="app-breadcrumb">
        <span>U-FAST</span>
        <span className="app-breadcrumb-sep">›</span>
        <span className="app-breadcrumb-current">{crumb}</span>
      </div>
      <QuickPageSearch items={navItems} onNavigate={onNavigate} />
      <div className="app-topbar-right">
        <NotificationBell />
        <AvatarMenu userName={userName} />
      </div>
    </div>
  );
}

export default TopBar;
