import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { reportLoadError } from "../services/loadError";
import API, { getCurrentUser, login, logout } from "../services/api";
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
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      <path d="M12 14v3" />
    </svg>
  );
}

function elapsedLabel(milliseconds) {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function ScreenLock({ children }) {
  const [now, setNow] = useState(Date.now());
  const [lockedAt, setLockedAt] = useState(() => {
    const stored = Number(sessionStorage.getItem("screen_locked_at"));
    return Number.isFinite(stored) && stored > 0 ? stored : null;
  });
  const [sessionStartedAt] = useState(() => {
    const stored = Number(sessionStorage.getItem("session_started_at"));
    const started = Number.isFinite(stored) && stored > 0 ? stored : Date.now();
    if (!sessionStorage.getItem("session_started_at"))
      sessionStorage.setItem("session_started_at", String(started));
    return started;
  });
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [unlocking, setUnlocking] = useState(false);
  const passwordRef = useRef(null);
  const unlockRef = useRef(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!lockedAt) return undefined;
    const previousBodyOverflow = document.body.style.overflow;
    const previousRootOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    passwordRef.current?.focus();
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousRootOverflow;
    };
  }, [lockedAt]);

  const lockScreen = () => {
    const timestamp = Date.now();
    sessionStorage.setItem("screen_locked_at", String(timestamp));
    setPassword("");
    setError("");
    setLockedAt(timestamp);
  };

  const unlockScreen = async (event) => {
    event.preventDefault();
    if (!password || unlocking) return;
    const currentUser = getCurrentUser();
    if (!currentUser?.username) {
      setError("Your sign-in session is missing. Sign in again to continue.");
      return;
    }
    setUnlocking(true);
    setError("");
    try {
      const refreshedUser = await login(currentUser.username, password);
      if (refreshedUser?.must_change_password) {
        setError(
          "Your password needs to be updated before you can unlock this screen.",
        );
        return;
      }
      sessionStorage.removeItem("screen_locked_at");
      setLockedAt(null);
      setPassword("");
    } catch (unlockError) {
      setError(
        unlockError.response?.data?.detail ||
          "That password could not be verified.",
      );
    } finally {
      setUnlocking(false);
    }
  };

  const trapKeys = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      const target =
        document.activeElement === passwordRef.current
          ? unlockRef.current
          : passwordRef.current;
      target?.focus();
    }
  };

  return (
    <>
      {children(lockScreen)}
      {lockedAt &&
        createPortal(
          <div className="screen-lock-backdrop">
            <section
              className="screen-lock-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby="screen-lock-title"
              onKeyDown={trapKeys}
            >
              <div className="screen-lock-brand">
                <span className="screen-lock-icon">
                  <LockIcon />
                </span>
                <span>U-FAST · MANILA CAMPUS WORKSPACE</span>
              </div>
              <p className="screen-lock-eyebrow">SCREEN LOCKED</p>
              <h1 id="screen-lock-title">Take a break.</h1>
              <p className="screen-lock-copy">
                Your workspace is hidden. Enter your password when you’re ready
                to return.
              </p>
              <div className="screen-lock-clock" aria-live="off">
                <strong>
                  {new Intl.DateTimeFormat(undefined, {
                    hour: "numeric",
                    minute: "2-digit",
                    second: "2-digit",
                  }).format(now)}
                </strong>
                <span>
                  {new Intl.DateTimeFormat(undefined, {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  }).format(now)}
                </span>
              </div>
              <div className="screen-lock-timers" aria-live="off">
                <div>
                  <span>Break time</span>
                  <strong>{elapsedLabel(now - lockedAt)}</strong>
                </div>
                <div>
                  <span>Session time</span>
                  <strong>{elapsedLabel(now - sessionStartedAt)}</strong>
                </div>
              </div>
              <form className="screen-lock-form" onSubmit={unlockScreen}>
                <label htmlFor="screen-lock-password">Password</label>
                <input
                  ref={passwordRef}
                  id="screen-lock-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                />
                {error && (
                  <p className="screen-lock-error" role="alert">
                    {error}
                  </p>
                )}
                <button
                  ref={unlockRef}
                  type="submit"
                  disabled={!password || unlocking}
                >
                  {unlocking ? "Verifying…" : "Unlock screen"}
                </button>
              </form>
              <p className="screen-lock-footer">
                Your break timer continues while this screen is locked.
              </p>
            </section>
          </div>,
          document.body,
        )}
    </>
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
  const [expandedNotificationId, setExpandedNotificationId] = useState(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);

  const refreshCount = () => {
    if (document.visibilityState !== "visible") return;
    API.get("/notifications/unread_count/")
      .then((res) => setUnreadCount(res.data.unread_count))
      .catch(() => {});
  };

  useEffect(() => {
    refreshCount();
    const vis = () => {
      if (document.visibilityState === "visible") refreshCount();
    };
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("focus", refreshCount);
    const t = setInterval(refreshCount, 120000);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", vis);
      window.removeEventListener("focus", refreshCount);
    };
  }, []);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target))
        setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      setLoading(true);
      API.get("/notifications/", { params: { limit: 50 } })
        .then((res) => setItems(res.data))
        .catch(reportLoadError("the notifications"))
        .finally(() => setLoading(false));
    }
  };

  const markRead = async (id) => {
    setItems((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
    );
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
        aria-label={
          unreadCount > 0
            ? `Notifications, ${unreadCount} unread`
            : "Notifications"
        }
        aria-expanded={open}
        style={{
          position: "relative",
          background: open ? "#f3f4f6" : "transparent",
          color: "#374151",
          border: "1px solid transparent",
          cursor: "pointer",
          width: 34,
          height: 34,
          padding: 0,
          borderRadius: 6,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              top: 2,
              right: 1,
              background: "#b91c1c",
              color: "white",
              border: "2px solid white",
              borderRadius: 999,
              fontSize: 10,
              fontWeight: 600,
              padding: "0 4px",
              lineHeight: "14px",
              minWidth: 18,
              textAlign: "center",
              boxSizing: "border-box",
            }}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            width: "min(360px, 92vw)",
            maxHeight: "420px",
            overflowY: "auto",
            background: "white",
            borderRadius: 6,
            border: "1px solid #e5e7eb",
            boxShadow: "var(--shadow-pop)",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "10px 12px",
              borderBottom: "1px solid #e5e7eb",
              position: "sticky",
              top: 0,
              background: "white",
            }}
          >
            <strong style={{ fontSize: 14, color: "#111827", fontWeight: 600 }}>
              Notifications
            </strong>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#003366",
                  fontSize: 12,
                  cursor: "pointer",
                  fontWeight: 600,
                  padding: "2px 4px",
                }}
              >
                Mark all as read
              </button>
            )}
          </div>

          {loading ? (
            <p
              style={{ padding: 16, fontSize: 13, color: "#6b7280", margin: 0 }}
            >
              Loading…
            </p>
          ) : items.length === 0 ? (
            <p
              style={{ padding: 16, fontSize: 13, color: "#6b7280", margin: 0 }}
            >
              No notifications.
            </p>
          ) : (
            items.map((n) => {
              const target = notificationTarget(n);
              const expanded = expandedNotificationId === n.id;
              return (
                <div
                  className={`notification-dropdown-item${n.is_read ? " is-read" : " is-unread"}`}
                  key={n.id}
                >
                  <button
                    type="button"
                    className="notification-dropdown-trigger"
                    aria-expanded={expanded}
                    aria-controls={`notification-detail-${n.id}`}
                    onClick={() => {
                      if (!n.is_read) markRead(n.id);
                      setExpandedNotificationId((current) =>
                        current === n.id ? null : n.id,
                      );
                    }}
                  >
                    <span className="notification-dropdown-copy">
                      <span className="notification-dropdown-message">
                        {n.message}
                      </span>
                      <span className="notification-dropdown-meta">
                        {TYPE_LABEL[n.notif_type] || "Notice"} ·{" "}
                        {timeAgo(n.created_at)}
                        {n.is_read ? "" : " · Unread"}
                      </span>
                    </span>
                    <span
                      className={`notification-dropdown-chevron${expanded ? " is-open" : ""}`}
                      aria-hidden="true"
                    >
                      ⌄
                    </span>
                  </button>
                  <div
                    id={`notification-detail-${n.id}`}
                    className={`notification-dropdown-detail${expanded ? " is-open" : ""}`}
                    aria-hidden={!expanded}
                  >
                    <div className="notification-dropdown-detail-inner">
                      <p>{n.message}</p>
                      {target && (
                        <button
                          type="button"
                          className="notification-dropdown-open"
                          onClick={() => {
                            setOpen(false);
                            jumpTo(target);
                          }}
                        >
                          Open requests
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

/* Avatar: the profile picture (or initials in a plain circle) and a small menu with "My settings". */
function AvatarMenu({ userName, onLockScreen }) {
  const { pictureUrl, profile } = usePreferences();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => {
      if (wrap.current && !wrap.current.contains(e.target)) setOpen(false);
    };
    const esc = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const initials = profile
    ? initialsOf(profile.first_name, profile.last_name, userName)
    : initialsOf("", "", userName);
  const name = profile
    ? `${profile.first_name} ${profile.last_name}`.trim() || profile.username
    : userName;
  return (
    <div className="app-avatar-wrap" ref={wrap}>
      <button
        type="button"
        className="app-avatar-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((o) => !o)}
      >
        {pictureUrl ? (
          <img
            className="app-avatar-img"
            src={pictureUrl}
            alt=""
            width="30"
            height="30"
          />
        ) : (
          <span className="app-avatar-circle small" aria-hidden="true">
            {initials}
          </span>
        )}
      </button>
      {open && (
        <div className="app-avatar-menu" role="menu">
          <div className="app-avatar-menu-head">
            <div className="app-avatar-menu-name">{name}</div>
            {profile && (
              <div className="app-avatar-menu-role">{profile.role}</div>
            )}
          </div>
          <button
            type="button"
            role="menuitem"
            className="app-avatar-menu-item"
            onClick={() => {
              setOpen(false);
              navigate("/settings");
            }}
          >
            My settings
          </button>
          <button
            type="button"
            role="menuitem"
            className="app-avatar-menu-item app-avatar-lock-item"
            onClick={() => {
              setOpen(false);
              onLockScreen();
            }}
          >
            <LockIcon />
            <span>Lock screen</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="app-avatar-menu-item app-avatar-menu-signout"
            onClick={() => {
              setOpen(false);
              logout();
              window.location.href = "/login";
            }}
          >
            Sign out
          </button>
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
        <ScreenLock>
          {(lockScreen) => (
            <>
              <NotificationBell />
              <AvatarMenu userName={userName} onLockScreen={lockScreen} />
            </>
          )}
        </ScreenLock>
      </div>
    </div>
  );
}

export default TopBar;
