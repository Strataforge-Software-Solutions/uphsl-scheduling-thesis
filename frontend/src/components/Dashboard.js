import RegistrarDashboard from "./RegistrarDashboard";
import FacultyDashboard from "./FacultyDashboard";
import StudentDashboard from "./StudentDashboard";
import AdminDashboard from "./AdminDashboard";
import BasicEdDashboard from "./BasicEdDashboard";
import BasicEdTeacher from "./BasicEdTeacher";
import React, { useState } from "react";
import { refreshCurrentUser } from "../services/api";

/* IT admin: a clear school-level selector (College / SHS / JHS). Each level keeps its own data and dashboard. */
function AdminWithLevelSelector() {
  const [level, setLevel] = useState(() => { try { return sessionStorage.getItem("admin_level") || "COLLEGE"; } catch (e) { return "COLLEGE"; } });
  const pick = (l) => { setLevel(l); try { sessionStorage.setItem("admin_level", l); } catch (e) { /* ignore */ } };
  const opts = [["COLLEGE", "College"], ["SHS", "Senior High"], ["JHS", "Junior High"]];
  return (
    <>
      <div style={{ position: "fixed", right: "16px", bottom: "16px", zIndex: 50, background: "white", border: "1px solid #cdd6e0", borderRadius: "999px", padding: "4px", boxShadow: "0 4px 14px rgba(0,0,0,0.15)", display: "flex", gap: "2px", alignItems: "center" }}>
        <span style={{ fontSize: "11px", color: "#64748b", padding: "0 8px", fontWeight: 700, textTransform: "uppercase" }}>School level</span>
        {opts.map(([k, l]) => (
          <button key={k} onClick={() => pick(k)} style={{ border: "none", borderRadius: "999px", padding: "7px 14px", cursor: "pointer", fontSize: "13px", background: level === k ? "#003366" : "transparent", color: level === k ? "white" : "#334155" }}>{l}</button>))}
      </div>
      {level === "COLLEGE" ? <AdminDashboard /> : <BasicEdDashboard key={level} level={level} />}
    </>
  );
}

function Dashboard({ user: signedInUser }) {
  // Use the server's current profile (department names etc.), not only what was saved at sign-in.
  const [user, setUser] = useState(signedInUser);
  React.useEffect(() => {
    refreshCurrentUser().then((fresh) => setUser((old) => (JSON.stringify(old) === JSON.stringify(fresh) ? old : fresh))).catch(() => {});
  }, []);
  const { role, faculty_type: facultyType, username } = user;
  // A dean can head several departments (user.departments); everyone else has one.
  const departments = (user.departments && user.departments.length ? user.departments : [user.department]).filter(Boolean);
  const department = departments.join(" & ");

  switch (role) {
    case "registrar":
      return <RegistrarDashboard />;
    case "faculty":
      return <FacultyDashboard name={username} department={department} departments={departments} facultyType={facultyType} />;
    case "principal":
      return <BasicEdDashboard level={user.school_level} />;
    case "teacher":
      return <BasicEdTeacher />;
    case "admin":
      return <AdminWithLevelSelector />;
    case "student":
      return <StudentDashboard studentId={username} />;
    default:
      return <p style={{ textAlign: "center" }}>No dashboard available for this role.</p>;
  }
}

export default Dashboard;
