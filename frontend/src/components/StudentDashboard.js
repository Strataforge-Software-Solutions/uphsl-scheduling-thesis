import React, { useEffect, useState } from "react";
import { reportLoadError } from "../services/loadError";
import API, { getCurrentUser, logout } from "../services/api";
import { formatSchedule } from "../utils/formatSchedule";
import { LecLabTag, buildLecLabIndex } from "../utils/lecLab";
import { mergeSchedulesByDay } from "../utils/mergeSchedules";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import "./DashboardTheme.css";

const NAV_ITEMS = [{ key: "timetable", label: "My Timetable", icon: "🗓" }];

function StudentDashboard({ studentId }) {
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const user = getCurrentUser();

  useEffect(() => {
    API.get("/engine/schedules/")
      .then((res) => setClasses(res.data))
      .catch(reportLoadError("your classes"))
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  return (
    <div className="app-shell">
      <Sidebar
        brandLabel="U-FAST"
        workspaceLabel="Manila Campus Workspace"
        items={NAV_ITEMS}
        activeKey="timetable"
        onSelect={() => {}}
        userName={studentId}
        userRole="Student"
        onSignOut={handleLogout}
      />

      <div className="app-main">
        <TopBar crumb="My Timetable" userName={user?.username} />
        <PageHeader
          eyebrow="Student Portal"
          title="My Timetable"
          subtitle="Your class schedule for this term."
        />

        <div className="app-page-body">
          {loading ? (
            <p>Loading…</p>
          ) : (
            <table>
              <thead>
                <tr><th>Subject</th><th>Room</th><th>Time</th></tr>
              </thead>
              <tbody>
                {mergeSchedulesByDay(classes).map((g, _i, all) => (
                  <tr key={g.key}>
                    <td>{g.subject_code} — {g.subject_title}<LecLabTag row={g} index={buildLecLabIndex(all)} /></td>
                    <td>{g.room_name}</td>
                    <td>{formatSchedule(g.timeslot_day, g.start, g.end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

export default StudentDashboard;
