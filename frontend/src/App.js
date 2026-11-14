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

  React.useEffect(() => {
    const lock = () => { if (getCurrentUser()) setIsLocked(true); };
    window.addEventListener("app-screen-lock", lock);
    return () => window.removeEventListener("app-screen-lock", lock);
  }, []);

  const handleLoginSuccess = (loggedInUser) => setUser(loggedInUser);

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
      {isLocked && user && <LockScreen user={user} onUnlock={(authenticatedUser) => { setUser(authenticatedUser); setIsLocked(false); }} onSignOut={() => { setUser(null); setIsLocked(false); }} />}
    </Router>
    </ConfirmDialogProvider>
    </PreferencesProvider>
  );
}

export default App;
