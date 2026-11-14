import React, { useEffect, useState } from "react";
import API, { onSchedulesChanged } from "../services/api";
import { onWorkloadChanged } from "./OverloadResolver";
import HomePage from "./HomePage";

/* Role-specific data for the Homepage, using endpoints that already exist. Every call is optional: a failure just leaves that number out. */

/* Live numbers from /engine/dashboard-stats/. Refresh on schedule changes and while the dashboard is visible. */
function useClassData() {
  const [d, setD] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true, seq = 0, lastRequestAt = 0;
    const load = (force = false) => {
      if (document.visibilityState !== "visible" || (!force && Date.now() - lastRequestAt < 3000)) return;
      lastRequestAt = Date.now();
      const mine = ++seq;
      API.get("/engine/dashboard-stats/")
        .then((r) => { if (live && mine === seq) { setD(r.data); setFailed(false); } })
        .catch(() => { if (live && mine === seq) setFailed(true); });
    };
    load();
    const off = onSchedulesChanged(() => load(true)), off2 = onWorkloadChanged(() => load(true));
    const vis = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("focus", vis);
    const t = setInterval(load, 120000);
    return () => { live = false; off(); off2(); document.removeEventListener("visibilitychange", vis); window.removeEventListener("focus", vis); clearInterval(t); };
  }, []);
  return [d, failed];
}

function classHome(role, [d, failed], nav, onNavigate, name, scope, labelMap, hideIntro = false) {
  const stats = [
    { label: "Class periods", value: d ? d.class_periods : null, tab: "schedules" },
    { label: "Draft", value: d ? d.draft : null, tab: "schedules" },
    { label: "Approved", value: d ? d.approved : null, tab: "schedules" },
    { label: "Published", value: d ? d.published : null, accent: "#15803d", tab: "schedules" },
    { label: "Conflicts", value: d ? d.conflicts : null, accent: d && d.conflicts ? "#b91c1c" : "#15803d", tab: "conflicts" },
    { label: "Overloaded teachers", value: d ? d.overloaded : null, accent: d && d.overloaded ? "#b91c1c" : "#15803d", tab: "analytics" },
  ];
  const tasks = [];
  if (d) {
    if (d.class_periods === 0) tasks.push({ text: "No schedule generated yet.", tab: labelMap.generate, tone: "warn" });
    if (d.draft) tasks.push({ text: `${d.draft} draft ${d.draft === 1 ? "class period is" : "class periods are"} waiting for your review and approval.`, tab: "schedules", tone: "warn" });
    if (d.conflicts) tasks.push({ text: `${d.conflicts} scheduling ${d.conflicts === 1 ? "conflict needs" : "conflicts need"} resolution.`, tab: "conflicts", tone: "bad" });
    if (d.overloaded) tasks.push({ text: `${d.overloaded} ${d.overloaded === 1 ? "teacher is" : "teachers are"} over the weekly load limit.`, tab: "analytics", tone: "bad" });
  }
  const status = d ? {
    summary: `${d.class_periods} class ${d.class_periods === 1 ? "period" : "periods"} scheduled`,
    metrics: [
      { label: "Draft review", value: d.draft, tone: d.draft ? "warn" : "ok" },
      { label: "Approved", value: d.approved, tone: "info" },
      { label: "Published", value: d.published, tone: d.published ? "ok" : "neutral" },
    ],
    checks: [
      { label: d.conflicts ? `${d.conflicts} scheduling ${d.conflicts === 1 ? "conflict" : "conflicts"} need attention` : "No scheduling conflicts", tone: d.conflicts ? "bad" : "ok" },
      { label: d.overloaded ? `${d.overloaded} ${d.overloaded === 1 ? "teacher is" : "teachers are"} over the weekly limit` : "Faculty workload is within limits", tone: d.overloaded ? "warn" : "ok" },
    ],
  } : failed ? { error: "Schedule information could not be loaded. It will retry automatically." } : null;
  return <HomePage role={role} name={name} scope={scope} nav={nav} onNavigate={onNavigate} stats={stats} tasks={tasks} status={status} hideIntro={hideIntro} />;
}

export function DeanHome({ nav, onNavigate, name, scope }) {
  return classHome("dean", useClassData(), nav, onNavigate, name, scope, { generate: "schedules" });
}

export function RegistrarHome({ nav, onNavigate, name }) {
  return classHome("registrar", useClassData(), nav, onNavigate, name, "Registrar", { generate: "generate" }, true);
}

export function PrincipalHome({ level, levelName, overview, nav, onNavigate, name, extra }) {
  const c = overview.counts;
  const stats = [
    { label: "Sections", value: c.sections, tab: "sections" }, { label: "Teachers", value: c.faculty, tab: "faculty" }, { label: "Rooms", value: c.rooms },
    { label: "Timetables", value: overview.runs.length, tab: "schedules" },
    { label: "Periods placed", value: overview.runs.reduce((n, r) => n + (r.entry_count || 0), 0), tab: "schedules" },
    { label: "Awaiting approval", value: c.pending_review, accent: c.pending_review ? "#b45309" : "#15803d", tab: "schedules" },
    { label: "Open conflicts", value: c.open_conflicts, accent: c.open_conflicts ? "#b91c1c" : "#15803d", tab: "schedules" },
  ];
  const tasks = [];
  if (!overview.runs.length) tasks.push({ text: "No timetable generated yet.", tab: "schedules", tone: "warn" });
  if (c.pending_review) tasks.push({ text: `${c.pending_review} timetable(s) wait for your approval.`, tab: "schedules", tone: "warn" });
  if (c.open_conflicts) tasks.push({ text: `${c.open_conflicts} open conflict(s) in the timetables.`, tab: "schedules", tone: "bad" });
  if (c.unverified_subjects) tasks.push({ text: `${c.unverified_subjects} curriculum line(s) are unverified.`, tab: "curriculum", tone: "warn" });
  const status = {
    summary: `Academic year ${overview.academic_year || "–"}`,
    metrics: [
      { label: "Timetables", value: overview.runs.length, tone: overview.runs.length ? "info" : "warn" },
      { label: "Periods placed", value: overview.runs.reduce((n, r) => n + (r.entry_count || 0), 0), tone: "info" },
      { label: "Awaiting approval", value: c.pending_review, tone: c.pending_review ? "warn" : "ok" },
    ],
    checks: [
      { label: c.open_conflicts ? `${c.open_conflicts} open conflicts need attention` : "No open timetable conflicts", tone: c.open_conflicts ? "bad" : "ok" },
      { label: c.unverified_subjects ? `${c.unverified_subjects} curriculum lines need verification` : "Curriculum is verified", tone: c.unverified_subjects ? "warn" : "ok" },
    ],
  };
  return <HomePage role="principal" name={name} scope={levelName} nav={nav} onNavigate={onNavigate} stats={stats} tasks={tasks} status={status} extra={extra} skip={["overview"]} />;
}
