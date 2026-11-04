import PasswordInput from "../components/PasswordInput";
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
      setError("Please fill in both password fields.");
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
    <div style={{ minHeight: "100vh", background: "#eef2f6", fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif" }}>
      <div style={{
        background: "#003366", padding: "14px 28px", display: "flex", alignItems: "center", gap: "14px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
      }}>
        <span style={{ color: "white", fontWeight: 700, fontSize: "18px", letterSpacing: "0.2px" }}>
          U-FAST — University-Faculty Academic Scheduling Tool
        </span>
      </div>

      <div style={{ display: "flex", justifyContent: "center", paddingTop: "60px" }}>
        <form
          onSubmit={handleSubmit}
          style={{
            background: "linear-gradient(180deg, #003b7a 0%, #002347 100%)",
            borderRadius: "18px",
            padding: "32px 36px",
            width: "360px",
            boxShadow: "0 15px 40px rgba(0,0,0,0.25)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", marginBottom: "18px" }}>
            <span style={{ color: "white", fontWeight: 700, fontSize: "14px", marginRight: "10px", whiteSpace: "nowrap" }}>
              Login ID:
            </span>
            <div style={{
              flex: 1, background: "#dbe4ee", borderRadius: "6px", padding: "9px 12px",
              fontSize: "13.5px", color: "#1f2937", fontWeight: 600,
            }}>
              {displayName}
            </div>
          </div>

          <p style={{ color: "rgba(255,255,255,0.85)", fontSize: "13px", margin: "0 0 14px 0" }}>
            Create New Password
          </p>

          <div style={{ marginBottom: "10px" }}>
            <label style={{ color: "rgba(255,255,255,0.75)", fontSize: "12px", display: "block", marginBottom: "4px" }}>
              Password
            </label>
            <PasswordInput
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              style={{
                width: "100%", padding: "10px 12px", borderRadius: "7px", border: "none",
                fontSize: "13.5px", boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ marginBottom: "8px" }}>
            <label style={{ color: "rgba(255,255,255,0.75)", fontSize: "12px", display: "block", marginBottom: "4px" }}>
              Confirm Password
            </label>
            <PasswordInput
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              style={{
                width: "100%", padding: "10px 12px", borderRadius: "7px", border: "none",
                fontSize: "13.5px", boxSizing: "border-box",
              }}
            />
          </div>

          {error && (
            <p style={{ color: "#ffb4b4", fontSize: "12.5px", marginBottom: "10px", textAlign: "center" }}>
              {error}
            </p>
          )}

          <div style={{ display: "flex", justifyContent: "center", marginTop: "8px" }}>
            <button
              type="submit"
              disabled={submitting}
              style={{
                background: "white", color: "#003366", border: "none",
                padding: "11px 40px", borderRadius: "999px", fontWeight: 700, fontSize: "13.5px",
                cursor: submitting ? "default" : "pointer", opacity: submitting ? 0.7 : 1,
                boxShadow: "0 4px 10px rgba(0,0,0,0.2)",
              }}
            >
              {submitting ? "Saving…" : "SUBMIT"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ChangePassword;
