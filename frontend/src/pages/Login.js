import React, { useState } from "react";
import { login } from "../services/api";
import logo from "../assets/uphsl_logo.png";
import PasswordInput from "../components/PasswordInput";
import "./Login.css";

function LoginIcon({ name, className = "" }) {
  const paths = {
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18m-13 4h2m4 0h2m-8 3h2m4 0h2" /></>,
    users: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-1a6 6 0 0 1 12 0v1H3Zm13-9a3 3 0 1 0-1-5.8M17 14a5 5 0 0 1 4 5v1h-3" /></>,
    bolt: <><path d="M13 2 4 14h7l-1 8 10-13h-7l1-7Z" /></>,
    user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
    signin: <><path d="M10 17l5-5-5-5m5 5H3" /><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></>,
    key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9m-4 4 3 3m-6-1 3 3" /></>,
  };
  return <svg className={`login-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}

function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState("");   // e.g. UPHM-12345
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const user = await login(username, password);
      onLoginSuccess(user); // App.js routes to /change-password or /dashboard based on must_change_password
    } catch (err) {
      if (!err.response) {
        // No response at all = the browser couldn't even reach the backend --
        // wrong host/IP, backend not running, or blocked by CORS. This is very
        // different from a wrong password, so don't show the same message.
        setError(
          "Cannot reach the server. Check that the backend is running and that this page is opened from the "
          + "same address as the server (details in the browser console, F12)."
        );
      } else if (err.response.status === 401 || err.response.status === 400) {
        setError("Invalid ID or password.");
      } else {
        setError(`Sign-in failed (server error ${err.response.status}). Check the server log.`);
      }
    }
  };

  return (
    <div className="login-container">
      <main className="login-layout">
        <section className="login-brand-panel" aria-label="About U-FAST">
          <div className="login-brand">
            <img src={logo} alt="University of Perpetual Help System Laguna" className="login-logo" />
            <h1>U-FAST</h1>
            <p className="login-brand-subtitle">University – Faculty Academic<br />Scheduling Tool</p>
          </div>
          <div className="login-gold-rule" />
          <ul className="login-features">
            <li><span className="login-feature-icon"><LoginIcon name="calendar" /></span><span><strong>Generate and manage schedules</strong><small>Create, review, and publish class and exam schedules.</small></span></li>
            <li><span className="login-feature-icon"><LoginIcon name="users" /></span><span><strong>Coordinate with departments</strong><small>Handle Gen Ed move requests, substitutions, and approvals.</small></span></li>
            <li><span className="login-feature-icon"><LoginIcon name="bolt" /></span><span><strong>Detect and resolve conflicts</strong><small>Identify scheduling conflicts for teachers, rooms, and students.</small></span></li>
          </ul>
        </section>
        <section className="login-main-panel" aria-label="Sign in">
          <form className="login-form" onSubmit={handleLogin}>
            <h2>Welcome to <span>U-FAST</span></h2>
            <p className="login-form-subtitle">Sign in to your university scheduling account.</p>
            <div className="login-field">
              <label htmlFor="login-id">Login ID or School ID</label>
              <div className="login-input-wrap"><LoginIcon name="user" /><input
                id="login-id"
                type="text"
                placeholder="e.g. UPHM-R1001 or R1001"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              /></div>
            </div>
            <div className="login-field">
              <label htmlFor="login-password">Password</label>
              <div className="login-input-wrap"><LoginIcon name="lock" /><PasswordInput
                id="login-password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              /></div>
            </div>
            {error && <p className="login-error" role="alert">{error}</p>}
            <button className="login-submit" type="submit"><LoginIcon name="signin" />Sign in</button>
            <div className="login-forgot"><p><LoginIcon name="key" /><strong>Forgot your password?</strong></p><span>Ask the IT Admin to reset it to your school ID.</span></div>
          </form>
          <footer className="login-footer">© 2026 UPHSL Manila · U-FAST</footer>
        </section>
      </main>
    </div>
  );
}

export default Login;
