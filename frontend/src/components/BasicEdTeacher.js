import React, { useState, useEffect } from "react";
import API, { getCurrentUser, logout } from "../services/api";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import { StatTile } from "./Charts";
import { errText, cardStyle, Notice, DAYS, hhmm, ampm } from "./basicEdUi";
import { MyAvailability } from "./BasicEdAvailability";
import "./DashboardTheme.css";
import { OverrideBadge } from "./AssignAnywayDialog";
import { useDashboardTab } from "../services/preferences";
import { useMainScrollReset } from "../services/useMainScrollReset";

/* SHS / JHS teacher: sees only their own published timetable and profile. */
function BasicEdTeacher() {
  const user = getCurrentUser();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useDashboardTab([{ key: "schedule" }, { key: "profile" }], "schedule", `teacher-${user.school_level}`);
  useMainScrollReset(tab);
  const load = () => API.get("/basic-ed/my/schedule/").then((r) => setData(r.data)).catch((e) => setError(errText(e)));
  useEffect(() => { load(); }, []);
  const p = data?.profile;
  const entries = data?.entries || [];
  const times = [...new Set(entries.map((e) => hhmm(e.start_time)))].sort();
  const byKey = {};
  entries.forEach((e) => { byKey[`${e.day}|${hhmm(e.start_time)}`] = e; });
  const handleLogout = () => { logout(); window.location.href = "/login"; };
  const nav = [{ group: "Plan" }, { key: "schedule", label: "My Schedule", icon: "" }, { group: "People" }, { key: "profile", label: "My Profile", icon: "" }];
  return (
    <div className="app-shell">
      <Sidebar brandLabel="U-FAST" workspaceLabel={`${user.school_level} Faculty`} items={nav} activeKey={tab} onSelect={setTab} userName={user.username} userRole={`${user.school_level} Teacher`} onSignOut={handleLogout} />
      <div className="app-main">
        <TopBar crumb={tab === "schedule" ? "My Schedule" : "My Profile"} userName={user.username} />
        <PageHeader eyebrow={`${user.school_level} Faculty`} title={tab === "schedule" ? "My Schedule" : "My Profile"} subtitle={tab === "schedule" ? "Your classes, rooms and sections once the principal publishes the schedule." : "Your teaching profile."} />
        <div className="app-page-body motion-page-content" key={tab}>
          {error && <Notice tone="error">{error}</Notice>}
          {p && tab === "schedule" && (
            <>
              <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "16px" }}>
                <StatTile label="Periods / week" value={entries.length} /><StatTile label="Hours / week" value={p.weekly_hours} /><StatTile label="Max load" value={`${p.max_weekly_hours} h`} />
              </div>
              {entries.length === 0 ? <Notice>No published schedule yet. The principal will publish it after approval.</Notice> : (
                <div style={{ ...cardStyle, overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "700px" }}>
                    <thead><tr><th style={{ background: "#003366", color: "white", padding: "8px" }}>Time</th>{DAYS.map((d) => <th key={d[0]} style={{ background: "#003366", color: "white", padding: "8px" }}>{d[1]}</th>)}</tr></thead>
                    <tbody>{times.map((t) => (
                      <tr key={t}><td style={{ border: "1px solid #e5e7eb", padding: "6px", fontSize: "12px", textAlign: "center", background: "#f3f4f6" }}>{ampm(t)}</td>
                        {DAYS.map(([d]) => { const e = byKey[`${d}|${t}`]; return (
                          <td key={d} style={{ border: "1px solid #e5e7eb", padding: "6px", fontSize: "12px", background: e ? "#f0f7ff" : "#fafafa" }}>
                            {e && <><b>{e.subject_code}</b><div>{e.subject_name}</div><div style={{ color: "#6b7280" }}>{e.section_name} · {e.room_name}</div>
                              {e.qualification_override && <div style={{ marginTop: 2 }}><OverrideBadge text="Assigned by Principal (not connected)" reason={e.qualification_override.reason} /></div>}</>}</td>); })}
                      </tr>))}</tbody>
                  </table>
                </div>)}
            </>
          )}
          {p && tab === "profile" && (
            <div style={cardStyle}>
              <h3 style={{ marginTop: 0 }}>{p.full_name}</h3>
              <p style={{ fontSize: "14px", lineHeight: 1.8 }}>Employee ID: <b>{p.employee_id}</b><br />Department: <b>{p.department || "—"}</b><br />Specializations: <b>{p.specializations || "—"}</b><br />
                Qualifications: <b>{p.qualifications || "—"}</b><br />Maximum teaching load: <b>{p.max_weekly_hours} hours / week</b><br />Advisory section(s): <b>{data.advised.join(", ") || "—"}</b><br />
                Status: {p.is_active ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>}</p>

              <p style={{ fontSize: "12px", color: "#6b7280", marginTop: "14px" }}>You can't edit approved schedules. Ask the principal for a change.</p>
            </div>)}
          {p && tab === "profile" && <MyAvailability />}
        </div>
      </div>
    </div>
  );
}

export default BasicEdTeacher;
