import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, logout } from "../services/api";
import "./LockScreen.css";

export default function LockScreen({ user, onUnlock, onSignOut }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [now, setNow] = useState(Date.now());
  const navigate = useNavigate();
  const sessionStartedAt = Number(sessionStorage.getItem("app_session_started_at")) || now;
  const lockStartedAt = Number(sessionStorage.getItem("app_lock_started_at")) || now;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const mountedAt = String(Date.now());
    if (!sessionStorage.getItem("app_session_started_at")) sessionStorage.setItem("app_session_started_at", mountedAt);
    if (!sessionStorage.getItem("app_lock_started_at")) sessionStorage.setItem("app_lock_started_at", mountedAt);
    const previousHtmlOverflow = document.documentElement.style.overflow;
    const previousBodyOverflow = document.body.style.overflow;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = previousHtmlOverflow;
      document.body.style.overflow = previousBodyOverflow;
    };
  }, []);

  const unlock = async (event) => {
    event.preventDefault();
    if (!password || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const authenticatedUser = await login(user.username, password);
      sessionStorage.removeItem("app_screen_locked");
      sessionStorage.removeItem("app_lock_started_at");
      setPassword("");
      onUnlock(authenticatedUser);
    } catch (requestError) {
      setError(requestError.response?.status === 401 || requestError.response?.status === 400
        ? "That password did not match. Try again."
        : "Could not unlock right now. Check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const signOut = () => {
    sessionStorage.removeItem("app_screen_locked");
    sessionStorage.removeItem("app_lock_started_at");
    logout();
    onSignOut();
    navigate("/login", { replace: true });
  };

  return (
    <main className="app-lock-screen" role="dialog" aria-modal="true" aria-labelledby="app-lock-title">
      <form className="app-lock-card" onSubmit={unlock}>
        <div className="app-lock-brand">
          <span className="app-lock-icon" aria-hidden="true">
            <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" />
            </svg>
          </span>
          <span>U-FAST · MANILA CAMPUS WORKSPACE</span>
        </div>
        <div className="app-lock-eyebrow">SCREEN LOCKED</div>
        <h1 id="app-lock-title">Take a break.</h1>
        <p className="app-lock-description">Your workspace is hidden. Enter your password when you're ready to return.</p>
        <div className="app-lock-clock" aria-live="off">
          <div className="app-lock-time">{new Date(now).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}</div>
          <div className="app-lock-date">{new Date(now).toLocaleDateString([], { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</div>
        </div>
        <div className="app-lock-timers" aria-label="Session timers">
          <div className="app-lock-timer"><span>Break time</span><strong>{formatElapsed(now - lockStartedAt)}</strong></div>
          <div className="app-lock-timer"><span>Session time</span><strong>{formatElapsed(now - sessionStartedAt)}</strong></div>
        </div>
        <label className="app-lock-password-label" htmlFor="lock-password">Password</label>
        <input id="lock-password" className="app-lock-password" type="password" autoComplete="current-password" autoFocus required value={password}
          onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" />
        {error && <p className="app-lock-error" role="alert">{error}</p>}
        <button className="app-lock-submit" type="submit" disabled={!password || submitting}>
          {submitting ? "Unlocking…" : "Unlock screen"}
        </button>
        <p className="app-lock-footnote">Your break timer continues while this screen is locked.</p>
        <button className="app-lock-signout" type="button" onClick={signOut}>Sign out instead</button>
      </form>
    </main>
  );
}

function formatElapsed(milliseconds) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}
