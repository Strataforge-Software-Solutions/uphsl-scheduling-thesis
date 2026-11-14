import React, { useState } from "react";
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import ChangePassword from "./pages/ChangePassword";
import Dashboard from "./components/Dashboard";
import { getCurrentUser } from "./services/api";
import LockScreen from "./components/LockScreen";
import LoadErrorBanner from "./components/LoadErrorBanner";
import Settings from "./pages/Settings";
import { PreferencesProvider } from "./services/preferences";
import { ConfirmDialogProvider } from "./components/ConfirmDialog";

function App() {
  const [user, setUser] = useState(getCurrentUser());
  const [isLocked, setIsLocked] = useState(() => Boolean(getCurrentUser() && sessionStorage.getItem("app_screen_locked") === "true"));
  const [toast, setToast] = useState(() => {
    const url = new URL(window.location.href);
    const signedOut = url.searchParams.get("signedOut") === "1"
      || sessionStorage.getItem("app_logout_toast") === "true";
    return signedOut ? { message: "You have been signed out.", type: "success" } : null;
  });

  React.useEffect(() => {
    sessionStorage.removeItem("app_logout_toast");
    const url = new URL(window.location.href);
    if (url.searchParams.has("signedOut")) {
      url.searchParams.delete("signedOut");
      window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }, []);

  React.useEffect(() => {
    if (!toast) return undefined;
    const timeout = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  React.useEffect(() => {
    const showToast = (event) => setToast({
      message: event.detail?.message || "Done.",
      type: event.detail?.type || "success",
    });
    window.addEventListener("app-toast", showToast);
    return () => window.removeEventListener("app-toast", showToast);
  }, []);

  React.useEffect(() => {
    const lock = () => { if (getCurrentUser()) setIsLocked(true); };
    window.addEventListener("app-screen-lock", lock);
    return () => window.removeEventListener("app-screen-lock", lock);
  }, []);

  const handleLoginSuccess = (loggedInUser) => {
    setUser(loggedInUser);
    setToast({ message: "Signed in successfully. Welcome to U-FAST.", type: "success" });
  };

  return (
    <PreferencesProvider userId={user?.id}>
    <ConfirmDialogProvider>
    <Router>
      <div inert={isLocked ? "" : undefined} aria-hidden={isLocked ? "true" : undefined} style={{ display: "contents" }}>
        <LoadErrorBanner />
        <Routes>
          <Route path="/" element={<Navigate to="/login" />} />
          <Route
            path="/login"
            element={user ? <Navigate to="/dashboard" /> : <Login onLoginSuccess={handleLoginSuccess} />}
          />
          <Route
            path="/change-password"
            element={
              user?.must_change_password
                ? <ChangePassword onDone={() => setUser({ ...user, must_change_password: false })} />
                : <Navigate to="/dashboard" />
            }
          />
          <Route
            path="/dashboard"
            element={
              !user ? <Navigate to="/login" />
              : user.must_change_password ? <Navigate to="/change-password" />
              : <Dashboard user={user} />
            }
          />
          <Route
            path="/settings"
            element={
              !user ? <Navigate to="/login" />
              : user.must_change_password ? <Navigate to="/change-password" />
              : <Settings user={user} />
            }
          />
        </Routes>
      </div>
      {isLocked && user && <LockScreen user={user} onUnlock={(authenticatedUser) => { setUser(authenticatedUser); setIsLocked(false); setToast({ message: "Screen unlocked. Welcome back.", type: "success" }); }} onSignOut={() => { sessionStorage.removeItem("app_logout_toast"); setUser(null); setIsLocked(false); setToast({ message: "You have been signed out.", type: "success" }); }} />}
      {toast && (
        <div className={`app-toast is-${toast.type}`} role={toast.type === "error" ? "alert" : "status"} aria-live={toast.type === "error" ? "assertive" : "polite"}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d={toast.type === "error" ? "M10 3v7m0 3v.2M3.8 16h12.4L10 4 3.8 16Z" : "m4 10 4 4 8-8"} /></svg>
          <span>{toast.message}</span>
        </div>
      )}
    </Router>
    </ConfirmDialogProvider>
    </PreferencesProvider>
  );
}

export default App;
