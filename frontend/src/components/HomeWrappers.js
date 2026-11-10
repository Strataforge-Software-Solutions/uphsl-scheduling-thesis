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
    { label: "Class periods", value: d ? d.class_periods : null },
    { label: "Draft", value: d ? d.draft : null },
    { label: "Approved", value: d ? d.approved : null },
    { label: "Published", value: d ? d.published : null, accent: "#15803d" },
    { label: "Conflicts", value: d ? d.conflicts : null, accent: d && d.conflicts ? "#b91c1c" : "#15803d" },
    { label: "Overloaded teachers", value: d ? d.overloaded : null, accent: d && d.overloaded ? "#b91c1c" : "#15803d" },
  ];
  const tasks = [];
  if (d) {
    if (d.class_periods === 0) tasks.push({ text: "No schedule generated yet.", tab: labelMap.generate, tone: "warn" });
    if (d.draft) tasks.push({ text: `${d.draft} draft class period(s) wait for your review and approval.`, tab: "schedules", tone: "warn" });
    if (d.conflicts) tasks.push({ text: `${d.conflicts} scheduling conflict(s) to resolve.`, tab: "conflicts", tone: "bad" });
    if (d.overloaded) tasks.push({ text: `${d.overloaded} teacher(s) are overloaded: press View Suggestions.`, tab: "analytics", tone: "bad" });
  }
  const status = d ? [
    d.class_periods ? `${d.class_periods} periods · ${d.draft} draft · ${d.approved} approved · ${d.published} published` : "No class periods exist",
    d.conflicts ? `${d.conflicts} scheduling ${d.conflicts === 1 ? "conflict" : "conflicts"} found` : "No scheduling conflicts",
    d.overloaded ? `${d.overloaded} ${d.overloaded === 1 ? "teacher exceeds" : "teachers exceed"} the weekly limit` : "No teachers over the weekly limit",
  ] : failed ? ["The numbers could not be loaded. They retry automatically."] : [];
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
    { label: "Sections", value: c.sections }, { label: "Teachers", value: c.faculty }, { label: "Rooms", value: c.rooms },
    { label: "Timetables", value: overview.runs.length },
    { label: "Periods placed", value: overview.runs.reduce((n, r) => n + (r.entry_count || 0), 0) },
    { label: "Awaiting approval", value: c.pending_review, accent: c.pending_review ? "#b45309" : "#15803d" },
    { label: "Open conflicts", value: c.open_conflicts, accent: c.open_conflicts ? "#b91c1c" : "#15803d" },
  ];
  const tasks = [];
  if (!overview.runs.length) tasks.push({ text: "No timetable generated yet.", tab: "schedules", tone: "warn" });
  if (c.pending_review) tasks.push({ text: `${c.pending_review} timetable(s) wait for your approval.`, tab: "schedules", tone: "warn" });
  if (c.open_conflicts) tasks.push({ text: `${c.open_conflicts} open conflict(s) in the timetables.`, tab: "schedules", tone: "bad" });
  if (c.unverified_subjects) tasks.push({ text: `${c.unverified_subjects} curriculum line(s) are unverified.`, tab: "curriculum", tone: "warn" });
  const by = {};
  overview.runs.forEach((r) => { by[r.status] = (by[r.status] || 0) + 1; });
  const status = [
    overview.runs.length ? `${overview.runs.length} timetable(s): ` + Object.entries(by).map(([k, v]) => `${v} ${k}`).join(", ") + "." : "No timetable generated yet.",
    `Academic year ${overview.academic_year || "–"}.`,
  ];
  return <HomePage role="principal" name={name} scope={levelName} nav={nav} onNavigate={onNavigate} stats={stats} tasks={tasks} status={status} extra={extra} skip={["overview"]} />;
}
