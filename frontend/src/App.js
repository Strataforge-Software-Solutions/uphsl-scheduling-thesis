import React, { useState } from "react";
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import ChangePassword from "./pages/ChangePassword";
import Dashboard from "./components/Dashboard";
import { getCurrentUser } from "./services/api";
import LoadErrorBanner from "./components/LoadErrorBanner";
import Settings from "./pages/Settings";
import { PreferencesProvider } from "./services/preferences";

function App() {
  const [user, setUser] = useState(getCurrentUser());

  const handleLoginSuccess = (loggedInUser) => setUser(loggedInUser);

  return (
    <PreferencesProvider userId={user?.id}>
    <Router>
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
    </Router>
    </PreferencesProvider>
  );
}

export default App;
