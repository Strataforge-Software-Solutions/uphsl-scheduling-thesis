import PasswordInput from "../components/PasswordInput";
import logo from "../assets/uphsl_logo.png";
import "./Login.css";
import React, { useEffect, useState } from "react";
import { changePassword, getCurrentUser, markPasswordChanged, refreshCurrentUser } from "../services/api";

function ChangePassword({ onDone }) {
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const user = getCurrentUser();
  // If the server already has this account's real password set (cached profile out of date), skip this screen.
  useEffect(() => {
    refreshCurrentUser().then((u) => { if (u && !u.must_change_password) { markPasswordChanged(); onDone(); } }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const displayName = user?.username || "";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!newPassword || !confirm) {
      setError("Fill in both password fields.");
      return;
    }
    if (newPassword !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(newPassword, undefined, confirm);
      markPasswordChanged();
      onDone();
    } catch (err) {
      // show the server's reason (too common, too similar to your ID, numbers only, ...), not a generic message
      const d = err.response?.data;
      const msgs = [...(d?.new_password || []), ...(d?.confirm_password || [])];
      setError(msgs.length ? msgs.join(" ") : d?.detail || (!err.response ? "Could not reach the server." : "Could not update password."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-header">
        <img src={logo} alt="UPHSL logo" className="login-logo" />
        <h2>U-FAST</h2>
        <p className="login-subtitle">University - Faculty Academic Scheduling Tool</p>
      </div>

      <form className="login-form" onSubmit={handleSubmit}>
        <h3>Set a new password</h3>
        <p className="login-help" style={{ margin: "-8px 0 16px" }}>
          Signed in as <strong style={{ color: "#111827" }}>{displayName}</strong>. Choose a password of at least 8 characters before you continue.
        </p>
        <div className="login-field">
          <label htmlFor="new-password">New password</label>
          <PasswordInput id="new-password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
        </div>
        <div className="login-field">
          <label htmlFor="confirm-password">Confirm new password</label>
          <PasswordInput id="confirm-password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </div>
        {error && <p className="login-error" role="alert">{error}</p>}
        <button type="submit" disabled={submitting}>{submitting ? "Saving…" : "Save password"}</button>
      </form>

      <footer className="login-footer">© 2026 UPHSL Manila · U-FAST</footer>
    </div>
  );
}

export default ChangePassword;
