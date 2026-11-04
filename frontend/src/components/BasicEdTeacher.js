import React, { useState, useEffect } from "react";
import API, { getCurrentUser, logout } from "../services/api";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import { StatTile } from "./Charts";
import { errText, cardStyle, btn, Notice, DAYS, hhmm, ampm } from "./basicEdUi";
import { AvailabilityModal } from "./BasicEdData";
import "./DashboardTheme.css";

/* SHS / JHS teacher: sees only their own published timetable and profile. */
function BasicEdTeacher() {
  const user = getCurrentUser();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [avail, setAvail] = useState(false);
  const [tab, setTab] = useState("schedule");
  const load = () => API.get("/basic-ed/my/schedule/").then((r) => setData(r.data)).catch((e) => setError(errText(e)));
  useEffect(() => { load(); }, []);
  const p = data?.profile;
  const entries = data?.entries || [];
  const times = [...new Set(entries.map((e) => hhmm(e.start_time)))].sort();
  const byKey = {};
  entries.forEach((e) => { byKey[`${e.day}|${hhmm(e.start_time)}`] = e; });
  const handleLogout = () => { logout(); window.location.href = "/login"; };
  const nav = [{ key: "schedule", label: "My Schedule", icon: "🗓" }, { key: "profile", label: "My Profile", icon: "👤" }];
  return (
    <div className="app-shell">
      <Sidebar brandLabel="U-FAST" workspaceLabel={`${user.school_level} Faculty`} items={nav} activeKey={tab} onSelect={setTab} userName={user.username} userRole={`${user.school_level} Teacher`} onSignOut={handleLogout} />
      <div className="app-main">
        <TopBar crumb={tab === "schedule" ? "My Schedule" : "My Profile"} userName={user.username} />
        <PageHeader eyebrow={`${user.school_level} Faculty`} title={tab === "schedule" ? "My Schedule" : "My Profile"} subtitle={tab === "schedule" ? "Your classes, rooms and sections once the principal publishes the schedule." : "Your teaching profile."} />
        <div className="app-page-body">
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
                      <tr key={t}><td style={{ border: "1px solid #e2e8f0", padding: "6px", fontSize: "12px", textAlign: "center", background: "#f1f5f9" }}>{ampm(t)}</td>
                        {DAYS.map(([d]) => { const e = byKey[`${d}|${t}`]; return (
                          <td key={d} style={{ border: "1px solid #e2e8f0", padding: "6px", fontSize: "12px", background: e ? "#f0f7ff" : "#fafafa" }}>
                            {e && <><b>{e.subject_code}</b><div>{e.subject_name}</div><div style={{ color: "#64748b" }}>{e.section_name} · {e.room_name}</div></>}</td>); })}
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
              <p style={{ fontSize: "13px", color: "#64748b" }}>{p.availability.length ? "Your availability rules:" : "You are marked available at any time."}</p>
              <ul style={{ fontSize: "13px" }}>{p.availability.map((a) => <li key={a.id}>{a.available ? "Available only" : "Not available"}: {a.day} {ampm(hhmm(a.start_time))}–{ampm(hhmm(a.end_time))}</li>)}</ul>
              <button style={btn} onClick={() => setAvail(true)}>Update my availability</button>
              <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "14px" }}>You can't edit approved schedules. Ask the principal for a change.</p>
            </div>)}
        </div>
      </div>
      {avail && <AvailabilityModal selfService faculty={p} onClose={() => { setAvail(false); load(); }} />}
    </div>
  );
}

export default BasicEdTeacher;
