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
      <div className="login-header">
        <img src={logo} alt="UPHSL logo" className="login-logo" />
        <h2>U-FAST</h2>
        <p className="login-subtitle">University - Faculty Academic Scheduling Tool</p>
      </div>

      <form className="login-form" onSubmit={handleLogin}>
        <h3>Sign in</h3>
        <div className="login-field">
          <label htmlFor="login-id">Login ID or School ID</label>
          <input
            id="login-id"
            type="text"
            placeholder="e.g. UPHM-12345"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="login-field">
          <label htmlFor="login-password">Password</label>
          <PasswordInput
            id="login-password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p className="login-error" role="alert">{error}</p>}
        <button type="submit">Sign in</button>
        <p className="login-help">Forgot your password? Ask the IT Admin to reset it to your school ID.</p>
      </form>

      <footer className="login-footer">
        © 2026 UPHSL Manila · U-FAST
      </footer>
    </div>
  );
}

export default Login;
