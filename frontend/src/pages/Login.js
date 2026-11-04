import React, { useState } from "react";
import { login } from "../services/api";
import logo from "../assets/uphsl_logo.png";
import PasswordInput from "../components/PasswordInput";
import "./Login.css";

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
          "Could not reach the server at all. If you're on a different device than the one "
          + "running the backend, or opened this via a network IP instead of localhost, that's "
          + "likely why -- check the browser console (F12) for the exact error."
        );
      } else if (err.response.status === 401 || err.response.status === 400) {
        setError("Invalid ID or password.");
      } else {
        setError(`Login failed (server responded ${err.response.status}). Check backend logs.`);
      }
    }
  };

  return (
    <div className="login-container">
      <div className="login-header">
        <img src={logo} alt="UPHSL U-FAST logo" className="login-logo" />
        <h2>U-FAST</h2>
      </div>

      <form className="login-form" onSubmit={handleLogin}>
        <p style={{ fontSize: "11px", color: "#0055aa", fontWeight: 600, marginTop: "-6px", marginBottom: "14px", lineHeight: "1.4" }}>
          University - Faculty Academic Scheduling Tool
        </p>
        <input
          type="text"
          placeholder="Login ID or School ID (e.g., UPHM-12345)"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <PasswordInput
          placeholder="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit">Login</button>
        <p style={{ fontSize: "12px", marginTop: "12px", color: "#555" }}>
          Forgot your password? Ask the IT Admin to reset it back to your school ID.
        </p>
      </form>

      <footer className="login-footer">
        © 2026 U-FAST — University - Faculty Academic Scheduling Tool
      </footer>
    </div>
  );
}

export default Login;
