import CustomSelect from "./CustomSelect";
import CustomDatePicker from "./CustomDatePicker";
import HowToUse, { SimplifiedGuide } from "./HowToUse";
import { reportLoadError } from "../services/loadError";
import { RegistrarHome } from "./HomeWrappers";
import React, { useState, useEffect, useRef } from "react";
import { onJump } from "../services/jump";
import { useDashboardTab } from "../services/preferences";
import { useMainScrollReset } from "../services/useMainScrollReset";
import { getCachedCurriculumData, loadCurriculumData, updateCurriculumCache } from "../services/curriculumCache";
import { prefetchDashboardPage } from "../services/pagePrefetch";
import API, { getCurrentUser, getSchedules, logout } from "../services/api";
import { formatSchedule } from "../utils/formatSchedule";
import { LecLabTag, buildLecLabIndex } from "../utils/lecLab";
import { changedScheduleIds, mergeSchedulesByDay, sortByDayTime } from "../utils/mergeSchedules";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import { CollapsibleChartPanel, StatTile, HBarChart, RecentActivity } from "./Charts";
import { kindLabel } from "../utils/labels";
import ScheduleEditModal from "./ScheduleEditModal";
import ScheduleProblemsModal from "./ScheduleProblemsModal";
import PrintPreviewButton, { printYears, printTerms } from "./PrintPreviewButton";
import { GenEdRequestsPanel } from "./GenEdRequests";
import { useScheduleActions, SelectionBar, RowActions, btnStyle } from "./ScheduleActions";
import { GenEdCoverageCard, RoomHeatmapCard, DependenciesCard, CapacityCard, InsightFilters } from "./InsightCards";
import ClashDialog from "./ClashDialog";
import ExamSchedulePanel from "./ExamSchedulePanel";
import GenerateSchedulePanel from "./GenerateSchedulePanel";
import TeacherPicker from "./TeacherPicker";
import ErrorBoundary from "./ErrorBoundary";
import ConflictChecker from "./ConflictChecker";
import { useConfirmDialog } from "./ConfirmDialog";
import MinorSchedulesPanel from "./MinorSchedulesPanel";
import WorkloadPanel from "./WorkloadPanel";
import "./DashboardTheme.css";
import { OverrideBadge } from "./AssignAnywayDialog";
import { HOME_INTRO } from "./howto";
import coveragePolicyIllustration from "../assets/coverage-policy-illustration.png";
import coverageReportIllustration from "../assets/coverage-report-illustration.png";

// Same sections in the Dean, Registrar and Admin workspaces: Plan / Academics / People / Insights.
const NAV_ITEMS = [
  { key: "home", label: "Home", icon: "" },
  { group: "Plan" },
  { key: "generate", label: "Generate Schedule", icon: "" },
  { key: "minors", label: "Minor Schedules", icon: "" },
  { key: "schedules", label: "Schedules", icon: "" },
  { key: "exams", label: "Exam Schedule", icon: "" },
  { key: "conflicts", label: "Conflicts", icon: "" },
  { group: "Academics" },
  { key: "curriculum", label: "Curriculum", icon: "" },
  { group: "People" },
  { key: "coverage", label: "Faculty Coverage", icon: "" },
  { group: "Insights" },
  { key: "analytics", label: "Analytics", icon: "" },
];

const TAB_HEADERS = {
  home: { eyebrow: "Registrar Workspace", title: "Home", subtitle: "Your dashboard at a glance." },
  schedules: { eyebrow: "Registrar Workspace", title: "Schedules", subtitle: "" },
  curriculum: { eyebrow: "Registrar Workspace", title: "Curriculum", subtitle: "Manage subjects and curriculum across every college." },
  minors: { eyebrow: "Registrar Workspace", title: "Minor Schedules", subtitle: "Generate Gen Ed schedules for all colleges together and verify they do not conflict." },
  conflicts: { eyebrow: "Registrar Workspace", title: "Conflicts", subtitle: "Teacher, room and student double-bookings in the class schedule." },
  exams: { eyebrow: "Registrar Workspace", title: "Exam Schedule", subtitle: "Gen Ed exams — checked against every other schedule automatically." },
  coverage: { eyebrow: "Registrar Workspace", title: "Faculty Coverage", subtitle: "Report a faculty absence and get a coverage recommendation from current faculty." },
  analytics: { eyebrow: "Registrar Workspace", title: "Analytics", subtitle: "Institution-wide workload and room utilization." },
  generate: { eyebrow: "Registrar Workspace", title: "Generate Schedule", subtitle: "Run the constraint-based scheduling engine for a program and term." },
};

const STANDARD_YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"];

function RegistrarDashboard() {
  const [activeTab, setActiveTab] = useDashboardTab(NAV_ITEMS, "home", "registrar");
  useMainScrollReset(activeTab);
  useEffect(() => onJump((t) => { if (t === "gened-requests") setActiveTab("schedules"); }), [setActiveTab]);
  const [colleges, setColleges] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [college, setCollege] = useState("");
  const [programId, setProgramId] = useState("");

  const user = getCurrentUser();

  useEffect(() => {
    API.get("/curriculum/programs/").then((res) => {
      const depts = [...new Set(res.data.map((p) => p.department))];
      setColleges(depts);
      setPrograms(res.data);
      if (depts.length && !college) setCollege(depts[0]);
    }).catch(reportLoadError("the programs"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const programsInCollege = programs.filter((p) => p.department === college);

  React.useEffect(() => {
    if (programsInCollege.length) setProgramId(String(programsInCollege[0].id));
    else setProgramId("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [college, programs]);

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  const header = TAB_HEADERS[activeTab];

  return (
    <div className="app-shell">
      <Sidebar
        brandLabel="U-FAST"
        workspaceLabel="Manila Campus Workspace"
        items={NAV_ITEMS}
        activeKey={activeTab}
        onSelect={setActiveTab}
        onPrefetch={(page) => prefetchDashboardPage(page, "registrar", { programId })}
        userName={user?.username || "Registrar"}
        userRole="Registrar staff"
        onSignOut={handleLogout}
      />

      <div className="app-main">
        <TopBar crumb={header.title} userName={user?.username} />
        <PageHeader
          eyebrow={header.eyebrow}
          title={header.title}
          subtitle={header.subtitle}
          supportingText={activeTab === "home" ? <><strong>{user?.username || "Registrar"}</strong> · Registrar · {HOME_INTRO.registrar}</> : null}
        />

        <div className="app-page-body motion-page-content" key={activeTab}>
          {activeTab !== "home" && <HowToUse role="registrar" tab={activeTab} />}
          {activeTab === "home" && <RegistrarHome nav={NAV_ITEMS} onNavigate={setActiveTab} name={user?.username} hideIntro />}
          {["curriculum", "exams"].includes(activeTab) && (
            <div className="app-toolbar">
              <CustomSelect value={college} onChange={(e) => setCollege(e.target.value)}>
                {colleges.map((c) => <option key={c} value={c}>{c}</option>)}
              </CustomSelect>
              <CustomSelect value={programId} onChange={(e) => setProgramId(e.target.value)}>
                {programsInCollege.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </CustomSelect>
            </div>
          )}

          {/* Schedules has its own self-contained filter bar (search, college,
              status, year level, semester, reset) instead of the shared
              college/program toolbar above -- it needs to let the Registrar
              browse across every college at once, not just one program. */}
          {activeTab === "schedules" && <SchedulesTab />}
          {activeTab === "curriculum" && <CurriculumTab programs={programs} programId={programId} defaultProgram={programId} />}
          {activeTab === "conflicts" && <ConflictChecker />}
          {activeTab === "minors" && <MinorSchedulesPanel />}
          {activeTab === "exams" && <ExamSchedulePanel role="registrar" programId={programId} />}
          {activeTab === "coverage" && <CoverageTab />}
          {activeTab === "analytics" && <><AnalyticsTab /><RegistrarInsights /></>}
          {activeTab === "generate" && <ErrorBoundary what="Generate Schedule"><GenerateSchedulePanel role="registrar" /></ErrorBoundary>}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Schedules: all departments, full CRUD ---------------- */
// Draft -> Approved -> Published, Dean Villanueva's described approval chain
// (she drafts the class program, the Director approves, then it's encoded/live).
function StatusPill({ status }) {
  if (status === "published") return <Badge tone="success">Published</Badge>;
  if (status === "approved") return <Badge tone="success">Approved</Badge>;
  return <Badge tone="warning">Draft</Badge>;
}

function SchedulesTab() {
  const [schedules, setSchedules] = useState([]);
  const [changedIds, setChangedIds] = useState(() => new Set());
  const previousSchedules = useRef(null);
  const changedTimer = useRef(null);
  const [rooms, setRooms] = useState([]);
  const [faculty, setFaculty] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingGroup, setEditingGroup] = useState(null);
  const [editForm, setEditForm] = useState({ room: "", teacher: "", day: "", start_time: "", end_time: "" });
  const [saveError, setSaveError] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [selected, setSelected] = useState([]);        // ticked rows (group keys): the bar acts on these ONLY
  const [pickTime, setPickTime] = useState(null);      // Edit > "Choose a new day and time" (real free times)
  const [editNote, setEditNote] = useState("");
  const [workloadIssue, setWorkloadIssue] = useState(null);

  // Self-contained filter bar -- search text, college, status, year level,
  // semester, all applied client-side over the full schedules list (already
  // scoped server-side to what this Registrar/Dean may see). Lets the
  // Registrar browse the whole institution at once instead of drilling into
  // one program first.
  const [search, setSearch] = useState("");
  const [collegeFilter, setCollegeFilter] = useState("");
  const [programFilter, setProgramFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [yearLevel, setYearLevel] = useState("");
  const [semester, setSemester] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [schedulePage, setSchedulePage] = useState(1);
  const [schedulePageSize, setSchedulePageSize] = useState(25);

  const load = () => {
    setLoading(true);
    Promise.allSettled([
      getSchedules(),
      API.get("/rooms/"),
      API.get("/faculty/profiles/"),
    ])
      .then(([schedRes, roomRes, facRes]) => {
        if (schedRes.status !== "fulfilled") {
          const why = schedRes.reason?.response?.status
            ? `server returned ${schedRes.reason.response.status}`
            : "could not reach the server -- is the backend running?";
          setError(`Could not load schedules (${why}).`);
          return;
        }
        setError("");
        const nextSchedules = schedRes.value.data;
        if (previousSchedules.current) {
          const changed = changedScheduleIds(previousSchedules.current, nextSchedules);
          setChangedIds(changed);
          if (changedTimer.current) window.clearTimeout(changedTimer.current);
          if (changed.size) changedTimer.current = window.setTimeout(() => setChangedIds(new Set()), 2800);
        }
        previousSchedules.current = nextSchedules;
        setSchedules(nextSchedules);
        // Rooms/faculty only feed the Edit dialog's dropdowns -- if one of
        // them fails the table should still show.
        if (roomRes.status === "fulfilled") setRooms(roomRes.value.data);
        if (facRes.status === "fulfilled") setFaculty(facRes.value.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); return () => { if (changedTimer.current) window.clearTimeout(changedTimer.current); }; }, []);

  const collegeOptions = [...new Set(schedules.map((s) => s.department).filter(Boolean))].sort();
  // A college/department (e.g. "Computer Studies") can hold several programs
  // (BS Computer Science AND BS Information Technology), so the table also
  // needs a Program filter -- otherwise both programs' "A1" sections mix.
  const programOptions = [
    ...new Map(
      schedules
        .filter((s) => s.program && (!collegeFilter || s.department === collegeFilter))
        .map((s) => [s.program, s.program_name])
    ).entries(),
  ].sort((a, b) => String(a[1]).localeCompare(String(b[1])));
  const yearLevelOptions = [...new Set([...STANDARD_YEARS, ...schedules.map((s) => s.year_level).filter(Boolean)])].sort();
  const semesterOptions = [...new Set(schedules.map((s) => s.semester).filter((x) => /sem/i.test(x || "")))].sort();

  const searchLower = search.trim().toLowerCase();
  const filtered = schedules.filter((s) => {
    if (collegeFilter && s.department !== collegeFilter) return false;
    if (programFilter && String(s.program) !== String(programFilter)) return false;
    if (yearLevel && s.year_level !== yearLevel) return false;
    if (semester && s.semester !== semester) return false;
    if (statusFilter && s.status !== statusFilter) return false;
    if (typeFilter && s.subject_classification !== typeFilter) return false;
    if (searchLower) {
      const haystack = `${s.subject_code} ${s.subject_title} ${s.teacher_name} ${s.section_name} ${s.room_name}`.toLowerCase();
      if (!haystack.includes(searchLower)) return false;
    }
    return true;
  });
  const grouped = sortByDayTime(mergeSchedulesByDay(filtered));
  const schedulePageCount = Math.max(1, Math.ceil(grouped.length / schedulePageSize));
  const pageGroups = grouped.slice((schedulePage - 1) * schedulePageSize, schedulePage * schedulePageSize);
  const lecLabIndex = buildLecLabIndex(grouped);

  useEffect(() => { setSchedulePage(1); }, [search, collegeFilter, programFilter, statusFilter, yearLevel, semester, typeFilter, schedulePageSize]);
  useEffect(() => { if (schedulePage > schedulePageCount) setSchedulePage(schedulePageCount); }, [schedulePage, schedulePageCount]);

  const resetFilters = () => {
    setSearch(""); setCollegeFilter(""); setProgramFilter(""); setStatusFilter(""); setYearLevel(""); setSemester(""); setTypeFilter("");
  };

  // The Registrar owns MINOR subjects only; the Dean's major subjects are shown for reference (view only).
  const isMine = (row) => row.subject_classification === "minor";
  const draftCount = filtered.filter((s) => isMine(s) && s.status === "draft").length;
  const approvedCount = filtered.filter((s) => isMine(s) && s.status === "approved").length;
  const activeExtraFilterCount = [programFilter, yearLevel, semester, typeFilter].filter(Boolean).length;
  const hasAnyFilter = Boolean(search || collegeFilter || statusFilter || activeExtraFilterCount);

  // Select / Approve / Publish / Back to draft / Remove act on the TICKED rows only (ScheduleActions.js; the server checks every rule).
  const actions = useScheduleActions(() => { setSelected([]); load(); });
  const mineShown = grouped.filter(isMine);
  const selectedGroups = mineShown.filter((g) => selected.includes(g.key));
  const idsOf = (groups) => groups.flatMap((g) => g.ids);
  const toggle = (key) => setSelected((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));
  const allShownSelected = mineShown.length > 0 && mineShown.every((g) => selected.includes(g.key));

  const startEdit = (group) => {
    setEditingGroup(group);
    setSaveError("");
    setWorkloadIssue(null);
    setEditForm({
      room: group.room, teacher: group.teacher,
      day: group.timeslot_day, start_time: (group.start || "").slice(0, 5), end_time: (group.end || "").slice(0, 5),
    });
  };

  // Saving the Edit dialog. A change of day / start / end goes through ONE all-or-nothing request that checks the
  // class's final position against every other class (a multi-period block is never compared with its own old
  // periods). Clashes open a warning with free times on that day; picking one re-submits. Room / teacher-only
  // changes are saved period by period as before.
  const [editClash, setEditClash] = useState(null);
  const [editPicked, setEditPicked] = useState({});
  const saveEdit = async (group, override = false, formOverride = null) => {
    const form = formOverride || editForm;
    setSaveError("");
    setSavingEdit(true);
    try {
      // Workload check first, for the whole class at once: a different teacher must not be pushed past
      // their weekly limit silently. Over the limit -> show the warning + replacements (and an override
      // button unless the policy is strict) instead of saving.
      if (!override && String(form.teacher) !== String(group.teacher)) {
        const chk = await API.post("/engine/workload/check/", { teacher: form.teacher, schedule_ids: group.ids });
        if (chk.data.overloaded) {
          setWorkloadIssue(chk.data);
          setSavingEdit(false);
          return;
        }
      }
      setWorkloadIssue(null);
      const cut = (t) => (t || "").slice(0, 5);
      const timeChanged = form.day !== group.timeslot_day || cut(form.start_time) !== cut(group.start) || cut(form.end_time) !== cut(group.end);
      if (timeChanged) {
        await API.post("/engine/reschedule/", {
          day: form.day, override_workload: override,
          items: [{ ids: group.ids, start_time: cut(form.start_time), end_time: cut(form.end_time), room: form.room, teacher: form.teacher }],
        });
      } else if ((group.merged_with || []).length > 0) {
        // a SHARED class: one change for every attending section together (the server checks all of them, then saves all or nothing)
        await API.post("/engine/shared-classes/edit/", { ids: group.ids, teacher: form.teacher, room: form.room, override_workload: override });
      } else {
        const extra = override ? { override_workload: true } : {};
        await Promise.all(group.ids.map((id) => API.patch(`/engine/schedules/${id}/`, { room: form.room, teacher: form.teacher, ...extra })));
      }
      setEditClash(null); setEditPicked({});
      setEditingGroup(null);
      load();
    } catch (err) {
      const data = err.response?.data;
      if (err.response?.status === 409 && data?.conflicts) {
        setEditClash(data);                       // warning pop-up with suggested free times
        setSavingEdit(false);
        return;
      }
      if (err.response?.status === 409 && data?.workload_overload) {
        setWorkloadIssue(data);
        setSavingEdit(false);
        load();
        return;
      }
      const msg = data?.detail || (data?.non_field_errors ? "That teacher, room, or time is already booked -- pick a different one." : "");
      setSaveError(msg || `${JSON.stringify(data || "Could not save.")}`);
      load();
    } finally {
      setSavingEdit(false);
    }
  };

  const applySuggestion = () => {
    const c = editClash?.conflicts?.[0];
    const sug = c && editPicked[[...c.ids].sort((x, y) => x - y).join("-")];
    if (!sug) return;
    const next = { ...editForm, start_time: sug.start_time, end_time: sug.end_time };
    setEditForm(next);
    saveEdit(editingGroup, false, next);
  };


  if (loading) return <p>Loading schedules…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  const filterInputStyle = {
    padding: "9px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "13px", background: "white",
  };

  return (
    <div className="workflow-page schedules-page">
      <div className="schedule-intro-grid">
      <section className="coverage-panel schedule-overview-panel">
      <div className="schedule-overview-heading">
        <div className="schedule-overview-title">
          <span className="coverage-panel-icon" aria-hidden="true"><svg className="coverage-icon" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18M8 14h3m-3 3h7"/></svg></span>
          <div><h3>Class schedule</h3><p>Review and manage class entries across colleges and programs.</p></div>
        </div>
        {/* the PDF follows the filters below (college, program, year level, semester, status, Gen Ed / program subjects) */}
        <PrintPreviewButton disabled={grouped.length === 0} onFixed={load} yearChoices={printYears(schedules)} defaultYear={yearLevel}
          termChoices={printTerms(schedules)} params={{ department: collegeFilter, program_id: programFilter, semester, status: statusFilter, classification: typeFilter }} />
      </div>
      <div className="schedule-overview-stats" aria-label="Schedule summary">
        <div><strong>{filtered.length}</strong><span>Entries shown</span></div>
        <div><strong>{draftCount}</strong><span>Gen Ed drafts</span></div>
        <div><strong>{approvedCount}</strong><span>Gen Ed approved</span></div>
      </div>
      <div className="schedule-overview-note"><span aria-hidden="true">i</span><p>Select Gen Ed rows below to approve, publish, return to draft, or remove. The table checkbox selects every Gen Ed row currently shown by your filters.</p></div>
      </section>
      <SimplifiedGuide steps={["Search or filter by college, program, year, semester, or status.", "Select Gen Ed rows to approve, publish, return to draft, or remove.", "Use Edit for schedule changes and Preview / Print for the current filters."]} />
      </div>
      <GenEdRequestsPanel role="registrar" onChanged={load} />

      <div className="coverage-panel schedule-filter-panel schedule-filter-layout" style={{
        display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center",
        background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 14px", marginBottom: "16px",
      }}>
        <input
          aria-label="Search schedules"
          placeholder="Search by subject, teacher, or section"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...filterInputStyle, flex: "1 1 280px", minWidth: "200px" }}
        />
        <CustomSelect className="schedule-college-filter" aria-label="Filter by college" value={collegeFilter} onChange={(e) => { setCollegeFilter(e.target.value); setProgramFilter(""); }} style={filterInputStyle}>
          <option value="">All colleges</option>
          {collegeOptions.map((c) => <option key={c} value={c}>{c}</option>)}
        </CustomSelect>
        <CustomSelect aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={filterInputStyle}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="approved">Approved</option>
          <option value="published">Published</option>
        </CustomSelect>
        {hasAnyFilter && <button className="schedule-reset-filters" onClick={resetFilters}>Reset filters</button>}
        <details className="schedule-advanced-filters">
          <summary>More filters{activeExtraFilterCount ? ` · ${activeExtraFilterCount} active` : ""}</summary>
          <div className="schedule-advanced-filter-fields">
            <CustomSelect className="schedule-program-filter" aria-label="Filter by program" value={programFilter} onChange={(e) => setProgramFilter(e.target.value)} style={filterInputStyle}>
              <option value="">All programs</option>
              {programOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </CustomSelect>
            <CustomSelect aria-label="Filter by year level" value={yearLevel} onChange={(e) => setYearLevel(e.target.value)} style={filterInputStyle}>
              <option value="">All year levels</option>
              {yearLevelOptions.map((y) => <option key={y} value={y}>{y}</option>)}
            </CustomSelect>
            <CustomSelect aria-label="Filter by semester" value={semester} onChange={(e) => setSemester(e.target.value)} style={filterInputStyle}>
              <option value="">All semesters</option>
              {semesterOptions.map((s) => <option key={s} value={s}>{s}</option>)}
            </CustomSelect>
            <CustomSelect aria-label="Filter by subject type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={filterInputStyle}>
              <option value="">Gen Ed &amp; program subjects</option>
              <option value="minor">Gen Ed only</option>
              <option value="major">Program subjects only</option>
            </CustomSelect>
          </div>
        </details>
      </div>

      <section className="coverage-panel schedule-table-panel"><div className="coverage-table-wrap">
      <table className="sched-compact schedule-list-table">
        <thead>
          <tr>
            <th style={{ width: 34 }}>
              <input type="checkbox" aria-label="Select every Gen Ed class shown by this filter" checked={allShownSelected} disabled={!mineShown.length}
                onChange={(e) => setSelected(e.target.checked ? mineShown.map((g) => g.key) : [])} />
            </th>
            <th>Subject</th><th>Type</th><th>Section</th><th>Room</th><th>Teacher</th><th>Time</th><th>Status</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {pageGroups.map((g) => (
            <tr key={g.key} className={g.ids.some((id) => changedIds.has(String(id))) ? "schedule-row-changed" : undefined} style={selected.includes(g.key) ? { background: "#eef6ff" } : undefined}>
              <td>{isMine(g) && <input type="checkbox" aria-label={`Select ${g.subject_code} ${g.section_name}`} checked={selected.includes(g.key)} onChange={() => toggle(g.key)} />}</td>
              <td>{g.subject_code} — {g.subject_title}<LecLabTag row={g} index={lecLabIndex} /></td>
              <td><Badge tone={g.subject_classification === "major" ? "success" : "neutral"}>{kindLabel(g.subject_classification, g.program_name)}</Badge></td>
              <td>
                {g.section_name}
                <div style={{ fontSize: "12px", color: "#6b7280" }}>{g.program_name}</div>
                {g.merged_with && g.merged_with.length > 0 && (
                  <div style={{ fontSize: "12px", color: "#7a4b00", marginTop: "3px" }}
                       title="Shared class: these sections attend the same class (same teacher, room and time).">
                    Shared with {g.merged_with.join(", ")} · {g.merged_students} students
                  </div>
                )}
              </td>
              <td>{g.room_name}</td>
              <td>{g.teacher_name}</td>
              <td>{formatSchedule(g.timeslot_day, g.start, g.end)}</td>
              <td>
                {g.qualification_override && <><OverrideBadge reason={g.qualification_override.reason} />{" "}</>}
                {g.is_manual_override ? <span title="Edited by hand: Generate keeps it where it is (locked)"><Badge tone="warning">Edited</Badge></span> : <Badge tone="success">Generated</Badge>}{" "}
                <StatusPill status={g.status} />
              </td>
              <td>
                {!isMine(g) ? <span style={{ fontSize: "12px", color: "#6b7280" }} title="Program subjects are edited by the Dean">View only</span> : (
                <RowActions group={g} actions={actions} onEdit={startEdit} selecting={selectedGroups.length > 0} />
                )}
              </td>
            </tr>
          ))}
          {pageGroups.length === 0 && <tr><td colSpan={9} className="coverage-empty">No schedule entries match these filters.</td></tr>}
        </tbody>
      </table>
      </div>
      <div className="schedule-pagination" aria-label="Schedule table pagination">
        <span>{grouped.length ? `${(schedulePage - 1) * schedulePageSize + 1}–${Math.min(schedulePage * schedulePageSize, grouped.length)} of ${grouped.length} rows` : "0 rows"}</span>
        <label>Rows per page
          <CustomSelect aria-label="Rows per page" value={schedulePageSize} onChange={(e) => setSchedulePageSize(Number(e.target.value))}>
            <option value={10}>10</option><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
          </CustomSelect>
        </label>
        <div>
          <button type="button" onClick={() => setSchedulePage(1)} disabled={schedulePage === 1} aria-label="First page">«</button>
          <button type="button" onClick={() => setSchedulePage((page) => Math.max(1, page - 1))} disabled={schedulePage === 1}>Previous</button>
          <span>Page {schedulePage} of {schedulePageCount}</span>
          <button type="button" onClick={() => setSchedulePage((page) => Math.min(schedulePageCount, page + 1))} disabled={schedulePage >= schedulePageCount}>Next</button>
          <button type="button" onClick={() => setSchedulePage(schedulePageCount)} disabled={schedulePage >= schedulePageCount} aria-label="Last page">»</button>
        </div>
      </div>
      </section>

      <SelectionBar groups={selectedGroups} busy={actions.busy}
        onApprove={() => actions.changeStatus(idsOf(selectedGroups.filter((g) => g.status === "draft")), "approved")}
        onPublish={() => actions.changeStatus(idsOf(selectedGroups.filter((g) => g.status === "approved")), "published")}
        onDraft={() => actions.changeStatus(idsOf(selectedGroups.filter((g) => g.status === "approved")), "draft")}
        onRemove={() => actions.askRemove(idsOf(selectedGroups))}
        onClear={() => setSelected([])} />
      {actions.dialogs}
      {editNote && (
        <div role="status" style={{ position: "fixed", bottom: 18, left: 18, zIndex: 1200, background: "#ecfdf5", color: "#166534", border: "1px solid #a7f3d0", borderRadius: 6, padding: "10px 14px", fontSize: 13, maxWidth: 480 }}>
          Saved: {editNote} <button onClick={() => setEditNote("")} style={btnStyle("#ffffff", "#166534", "1px solid #a7f3d0")}>OK</button>
        </div>
      )}
      {pickTime && (
        <ScheduleProblemsModal clashes={[]} unplaced={[]} startWith={{ request: { ids: pickTime.ids }, reason: "Choose a new day and time (only free times are listed)." }}
          onClose={() => setPickTime(null)}
          onFixed={(d) => { if (d && d.changes) { setEditNote(`${pickTime.subject_code}: ${d.changes}`); setPickTime(null); setEditingGroup(null); load(); } }} />
      )}

      <ClashDialog
        clash={editClash} picked={editPicked} busy={savingEdit} applyLabel="Apply this time"
        onPick={(c, sug) => setEditPicked({ [[...c.ids].sort((x, y) => x - y).join("-")]: sug })}
        onBack={() => { setEditClash(null); setEditPicked({}); }}
        onApply={applySuggestion}
      />

      <ScheduleEditModal
        group={editingGroup}
        rooms={rooms}
        faculty={faculty}
        editForm={editForm}
        setEditForm={setEditForm}
        onSave={saveEdit}
        onCancel={() => setEditingGroup(null)}
        saveError={saveError}
        saving={savingEdit}
        workloadIssue={workloadIssue}
        onOverride={(g) => saveEdit(g, true)}
        onPickReplacement={(id) => { setEditForm({ ...editForm, teacher: String(id) }); setWorkloadIssue(null); }}
        onPickTime={(g) => setPickTime(g)}
      />
    </div>
  );
}

/* ---------------- Class Lists: who's in each block section -----------------
 * NOT a student portal -- students already use the GTI website for that.
 * This exists only so the Registrar/Dean can record roster data, which then
 * lets a Full-time/Part-time faculty member see "who's in my class" on their
 * own schedule view. One Student row = one section membership (PH-style
 * block sections: everyone in a section takes that section's whole load). */
/* ---------------- Curriculum: all departments, full CRUD ---------------- */
function CurriculumTab({ programs, programId, defaultProgram }) {
  const confirmDialog = useConfirmDialog();
  const initialData = getCachedCurriculumData();
  const [subjects, setSubjects] = useState(() => initialData?.subjects || []);
  const [academicFields, setAcademicFields] = useState(() => initialData?.academicFields || []);
  const [loading, setLoading] = useState(!initialData);
  const [newFieldName, setNewFieldName] = useState("");
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState("");

  const [form, setForm] = useState({
    code: "", title: "", lec_units: 0, lab_units: 0,
    program: "", year_level: "", semester: "", classification: "major", field: "",
  });

  useEffect(() => {
    loadCurriculumData()
      .then((data) => { setSubjects(data.subjects); setAcademicFields(data.academicFields); })
      .catch(reportLoadError("the curriculum"))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (defaultProgram) setForm((f) => ({ ...f, program: defaultProgram }));
  }, [defaultProgram]);

  const filtered = programId ? subjects.filter((s) => String(s.program) === String(programId)) : subjects;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginatedSubjects = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const visibleIds = paginatedSubjects.map((subject) => subject.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));

  useEffect(() => { setSelectedIds([]); setCurrentPage(1); }, [programId]);
  useEffect(() => { if (currentPage > pageCount) setCurrentPage(pageCount); }, [currentPage, pageCount]);

  const addSubject = async () => {
    if (!form.code || !form.title || !form.program) return;
    const payload = { ...form, field: form.field || null };
    const response = await API.post("/curriculum/subjects/", payload);
    setSubjects((current) => [...current, response.data]);
    updateCurriculumCache((data) => ({ ...data, subjects: [...data.subjects, response.data] }));
    setForm({ code: "", title: "", lec_units: 0, lab_units: 0, program: programId, year_level: "", semester: "", classification: "major", field: "" });
  };

  const startEdit = (subject) => {
    setEditingId(subject.id);
    setEditForm({
      code: subject.code, title: subject.title, lec_units: subject.lec_units, lab_units: subject.lab_units,
      program: String(subject.program), year_level: subject.year_level || "", semester: subject.semester || "",
      classification: subject.classification, field: subject.field ? String(subject.field) : "",
    });
    setEditError("");
  };

  const cancelEdit = () => { setEditingId(null); setEditForm(null); setEditError(""); };

  const saveEdit = async (subjectId) => {
    if (!editForm || !editForm.code.trim() || !editForm.title.trim() || !editForm.program
      || !editForm.year_level.trim() || !editForm.semester.trim()) {
      setEditError("Subject code, title, program, year level, and semester are required.");
      return;
    }
    if (![editForm.lec_units, editForm.lab_units].every((value) => Number.isInteger(Number(value)) && Number(value) >= 0)) {
      setEditError("Lecture and laboratory units must be whole numbers of zero or more.");
      return;
    }
    setSavingEdit(true);
    setEditError("");
    const payload = {
      code: editForm.code.trim(), title: editForm.title.trim(),
      lec_units: Number(editForm.lec_units), lab_units: Number(editForm.lab_units),
      program: Number(editForm.program), year_level: editForm.year_level.trim(), semester: editForm.semester.trim(),
      classification: editForm.classification, field: editForm.field || null,
    };
    try {
      const response = await API.patch(`/curriculum/subjects/${subjectId}/`, payload);
      setSubjects((current) => current.map((subject) => subject.id === subjectId ? response.data : subject));
      updateCurriculumCache((data) => ({ ...data, subjects: data.subjects.map((subject) => subject.id === subjectId ? response.data : subject) }));
      cancelEdit();
    } catch (err) {
      const data = err.response?.data;
      const fieldMessage = data && typeof data === "object" ? Object.values(data).flat().find((value) => typeof value === "string") : null;
      setEditError(data?.detail || fieldMessage || "Could not save changes. Check the subject details and try again.");
    } finally {
      setSavingEdit(false);
    }
  };

  const remove = async (id) => {
    if (!(await confirmDialog({ title: "Remove subject?", message: "Removing this subject also deletes any schedule and exam records linked to it. This cannot be undone.", confirmLabel: "Remove subject" }))) return;
    const removed = subjects.find((subject) => subject.id === id);
    const previousIndex = subjects.findIndex((subject) => subject.id === id);
    setSubjects((current) => current.filter((subject) => subject.id !== id));
    setSelectedIds((current) => current.filter((selectedId) => selectedId !== id));
    updateCurriculumCache((data) => ({ ...data, subjects: data.subjects.filter((subject) => subject.id !== id) }));
    try {
      await API.delete(`/curriculum/subjects/${id}/`);
    } catch (err) {
      if (removed) {
        setSubjects((current) => {
          if (current.some((subject) => subject.id === id)) return current;
          const restored = [...current];
          restored.splice(Math.min(previousIndex, restored.length), 0, removed);
          return restored;
        });
        updateCurriculumCache((data) => ({ ...data, subjects: [...data.subjects, removed] }));
      }
      reportLoadError("removing the subject")(err);
    }
  };

  const removeSelected = async () => {
    const ids = filtered.map((subject) => subject.id).filter((id) => selectedIds.includes(id));
    if (!ids.length || bulkDeleting) return;
    if (!(await confirmDialog({
      title: `Remove ${ids.length} selected subject${ids.length === 1 ? "" : "s"}?`,
      message: "Removing these subjects also deletes any schedule and exam records linked to them. This cannot be undone.",
      confirmLabel: `Remove ${ids.length} subject${ids.length === 1 ? "" : "s"}`,
    }))) return;

    const idSet = new Set(ids);
    const originalSubjects = subjects;
    const removed = subjects.filter((subject) => idSet.has(subject.id));
    setBulkDeleting(true);
    setSubjects((current) => current.filter((subject) => !idSet.has(subject.id)));
    setSelectedIds([]);
    updateCurriculumCache((data) => ({ ...data, subjects: data.subjects.filter((subject) => !idSet.has(subject.id)) }));
    try {
      await API.post("/curriculum/subjects/bulk-delete/", { ids });
    } catch (err) {
      setSubjects((current) => {
        const byId = new Map(current.map((subject) => [subject.id, subject]));
        removed.forEach((subject) => byId.set(subject.id, subject));
        const restored = originalSubjects.map((subject) => byId.get(subject.id)).filter(Boolean);
        const originalIds = new Set(originalSubjects.map((subject) => subject.id));
        return [...restored, ...current.filter((subject) => !originalIds.has(subject.id))];
      });
      setSelectedIds(ids);
      updateCurriculumCache((data) => {
        const byId = new Map(data.subjects.map((subject) => [subject.id, subject]));
        removed.forEach((subject) => byId.set(subject.id, subject));
        return { ...data, subjects: [...byId.values()] };
      });
      reportLoadError("removing the selected subjects")(err);
    } finally {
      setBulkDeleting(false);
    }
  };

  // Lets Registrar/Dean add a new academic field (e.g. "Computer Science")
  // on the fly instead of needing the Django admin for it -- this is what a
  // faculty's "Specialization" picker (FacultyProfile admin) now draws from,
  // instead of raw subject codes.
  const addAcademicField = async () => {
    const name = newFieldName.trim();
    if (!name) return;
    const res = await API.post("/curriculum/academic-fields/", { name });
    setAcademicFields((prev) => [...prev, res.data]);
    updateCurriculumCache((data) => ({ ...data, academicFields: [...data.academicFields, res.data] }));
    setForm((f) => ({ ...f, field: res.data.id }));
    setNewFieldName("");
  };

  const updateSubjectField = async (subjectId, fieldId) => {
    try {
      const response = await API.patch(`/curriculum/subjects/${subjectId}/`, { field: fieldId || null });
      setSubjects((current) => current.map((subject) => subject.id === subjectId ? response.data : subject));
      updateCurriculumCache((data) => ({ ...data, subjects: data.subjects.map((subject) => subject.id === subjectId ? response.data : subject) }));
    } catch (err) {
      reportLoadError("updating the subject field")(err);
    }
  };

  if (loading) return <p>Loading curriculum…</p>;

  return (
    <div className="curriculum-dashboard">
      <div className="curriculum-intro-grid">
        <section className="coverage-panel curriculum-overview-panel">
          <div className="coverage-panel-heading">
            <span className="coverage-panel-icon" aria-hidden="true"><svg className="coverage-icon" viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></svg></span>
            <div>
              <h3>Curriculum Management</h3>
              <p>{programs.find((p) => String(p.id) === String(programId))?.name || "All programs"} · Keep subject details and academic fields up to date.</p>
            </div>
          </div>
          <div className="curriculum-overview-stats">
            <div><strong>{filtered.length}</strong><span>Subjects in this program</span></div>
            <div><strong>{academicFields.length}</strong><span>Academic fields</span></div>
            <div><strong>{programs.length}</strong><span>Programs available</span></div>
          </div>
          <div className="curriculum-field-create">
            <div><strong>Academic fields</strong><span>Add a reusable field for subject classification.</span></div>
            <input aria-label="New academic field" placeholder="e.g., Computer Science" value={newFieldName}
              onChange={(e) => setNewFieldName(e.target.value)} />
            <button onClick={addAcademicField} disabled={!newFieldName.trim()}>Add Field</button>
          </div>
        </section>
        <section className="coverage-panel coverage-howto-panel curriculum-guide-panel">
          <div className="coverage-panel-heading">
            <span className="coverage-panel-icon"><svg className="coverage-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg></span>
            <div><h3>How to use this tab (Simplified)</h3></div>
          </div>
          <div className="coverage-steps">
            <div><b>1</b><span>Choose a college and program above.</span></div><i>›</i>
            <div><b>2</b><span>Review subjects and use pagination to browse the list.</span></div><i>›</i>
            <div><b>3</b><span>Add or update subjects and fields, then regenerate affected schedules.</span></div>
          </div>
        </section>
      </div>

      <section className="coverage-panel curriculum-subject-panel">
        <div className="coverage-panel-heading curriculum-section-heading">
          <div><h3>Add a subject</h3><p>Enter the subject details below. Required fields are code, title, and program.</p></div>
        </div>
        <div className="curriculum-add-form">
        <label className="curriculum-add-field curriculum-add-code"><span>Subject code</span>
          <input aria-label="Subject code" placeholder="e.g., CS1101" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        </label>
        <label className="curriculum-add-field curriculum-add-title"><span>Subject title</span>
          <input aria-label="Subject title" placeholder="e.g., Introduction to Computing" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </label>
        <label className="curriculum-add-field curriculum-add-lec"><span>Lecture units</span>
          <input aria-label="Lecture units" type="number" min="0" placeholder="0" value={form.lec_units}
                 onChange={(e) => setForm({ ...form, lec_units: Number(e.target.value) })} />
        </label>
        <label className="curriculum-add-field curriculum-add-lab"><span>Laboratory units</span>
          <input aria-label="Laboratory units" type="number" min="0" placeholder="0" value={form.lab_units}
                 onChange={(e) => setForm({ ...form, lab_units: Number(e.target.value) })} />
        </label>
        <div className="curriculum-add-field curriculum-add-program"><span>Program</span>
          <CustomSelect aria-label="Program" value={form.program} onChange={(e) => setForm({ ...form, program: e.target.value })}>
            <option value="">Select program</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.department})</option>)}
          </CustomSelect>
        </div>
        <label className="curriculum-add-field curriculum-add-year"><span>Year level</span>
          <input aria-label="Year level" placeholder="e.g., 1st Year" value={form.year_level}
                 onChange={(e) => setForm({ ...form, year_level: e.target.value })} />
        </label>
        <label className="curriculum-add-field curriculum-add-semester"><span>Semester</span>
          <input aria-label="Semester" placeholder="e.g., 1st Sem" value={form.semester}
                 onChange={(e) => setForm({ ...form, semester: e.target.value })} />
        </label>
        <div className="curriculum-add-field curriculum-add-classification"><span>Subject type</span>
          <CustomSelect aria-label="Subject type" value={form.classification} onChange={(e) => setForm({ ...form, classification: e.target.value })}>
            <option value="major">{kindLabel("major", (programs.find((p) => String(p.id) === String(form.program)) || {}).name)}</option>
            <option value="minor">{kindLabel("minor")}</option>
          </CustomSelect>
        </div>
        <div className="curriculum-add-field curriculum-add-academic-field"><span>Academic field (optional)</span>
          <CustomSelect aria-label="Academic field (optional)" value={form.field} onChange={(e) => setForm({ ...form, field: e.target.value })}>
            <option value="">Select academic field</option>
            {academicFields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </CustomSelect>
        </div>
        <button onClick={addSubject}>Add Subject</button>
        </div>
      </section>

      <section className="coverage-panel curriculum-list-panel">
        <div className="coverage-panel-heading curriculum-list-heading">
          <div><h3>Subjects</h3><p>{filtered.length} {filtered.length === 1 ? "subject" : "subjects"} in the selected program</p></div>
          <label className="curriculum-page-size">Rows per page
            <CustomSelect aria-label="Rows per page" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}>
              <option value={10}>10</option><option value={25}>25</option><option value={50}>50</option>
            </CustomSelect>
          </label>
        </div>
        <div className="coverage-table-wrap curriculum-table-wrap">
      <table className="coverage-table curriculum-table">
        <thead>
          <tr>
            <th><label style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <input type="checkbox" aria-label="Select all subjects on this page" checked={allVisibleSelected} disabled={bulkDeleting}
                onChange={(event) => setSelectedIds((current) => event.target.checked
                  ? [...new Set([...current, ...visibleIds])]
                  : current.filter((id) => !visibleIds.includes(id)))} />Select all
            </label></th>
            <th>Code</th><th>Title</th><th>Lec</th><th>Lab</th><th>Type</th><th>Department</th><th>Year level</th><th>Semester</th><th>Field</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {selectedIds.length > 0 && <tr>
            <td colSpan={11}>
              <span>{selectedIds.length} selected</span>{" "}
              <button className="curriculum-remove-button" disabled={bulkDeleting} onClick={removeSelected}>
                {bulkDeleting ? "Removing…" : `Remove selected (${selectedIds.length})`}
              </button>
            </td>
          </tr>}
          {filtered.map((s) => (
            <React.Fragment key={s.id}>
              <tr>
                <td><input type="checkbox" aria-label={`Select ${s.code}`} checked={selectedIds.includes(s.id)} disabled={bulkDeleting || savingEdit}
                  onChange={(event) => setSelectedIds((current) => event.target.checked
                    ? [...current, s.id] : current.filter((id) => id !== s.id))} /></td>
                <td>{s.code}</td><td>{s.title}</td><td>{s.lec_units}</td><td>{s.lab_units}</td>
                <td>{kindLabel(s.classification, s.program_name)}</td>
                <td>{s.department}</td>
                <td>{s.year_level || "—"}</td>
                <td>{s.semester || "—"}</td>
                <td>
                  <CustomSelect className="curriculum-field-select" value={s.field || ""} disabled={bulkDeleting || savingEdit || editingId !== null} onChange={(e) => updateSubjectField(s.id, e.target.value)}>
                    <option value="">-- none --</option>
                    {academicFields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </CustomSelect>
                </td>
                <td>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button type="button" disabled={bulkDeleting || savingEdit || (editingId !== null && editingId !== s.id)} onClick={() => startEdit(s)}>
                      {editingId === s.id ? "Editing" : "Edit"}
                    </button>
                    <button className="curriculum-remove-button" disabled={bulkDeleting || savingEdit} onClick={() => remove(s.id)}>Remove</button>
                  </div>
                </td>
              </tr>
              {editingId === s.id && editForm && (
                <tr>
                  <td colSpan={11}>
                    <div style={{ padding: "12px 8px" }}>
                      <div className="curriculum-add-form" aria-label={`Edit ${s.code}`}>
                        <label className="curriculum-add-field curriculum-add-code"><span>Subject code</span>
                          <input aria-label="Edit subject code" value={editForm.code} onChange={(e) => setEditForm({ ...editForm, code: e.target.value })} />
                        </label>
                        <label className="curriculum-add-field curriculum-add-title"><span>Subject title</span>
                          <input aria-label="Edit subject title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
                        </label>
                        <label className="curriculum-add-field curriculum-add-lec"><span>Lecture units</span>
                          <input aria-label="Edit lecture units" type="number" min="0" step="1" value={editForm.lec_units}
                            onChange={(e) => setEditForm({ ...editForm, lec_units: e.target.value })} />
                        </label>
                        <label className="curriculum-add-field curriculum-add-lab"><span>Laboratory units</span>
                          <input aria-label="Edit laboratory units" type="number" min="0" step="1" value={editForm.lab_units}
                            onChange={(e) => setEditForm({ ...editForm, lab_units: e.target.value })} />
                        </label>
                        <label className="curriculum-add-field curriculum-add-program"><span>Program / department</span>
                          <CustomSelect aria-label="Edit program" value={editForm.program} onChange={(e) => setEditForm({ ...editForm, program: e.target.value })}>
                            <option value="">Select program</option>
                            {programs.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.department})</option>)}
                          </CustomSelect>
                        </label>
                        <label className="curriculum-add-field curriculum-add-year"><span>Year level</span>
                          <input aria-label="Edit year level" value={editForm.year_level} onChange={(e) => setEditForm({ ...editForm, year_level: e.target.value })} />
                        </label>
                        <label className="curriculum-add-field curriculum-add-semester"><span>Semester</span>
                          <input aria-label="Edit semester" value={editForm.semester} onChange={(e) => setEditForm({ ...editForm, semester: e.target.value })} />
                        </label>
                        <label className="curriculum-add-field curriculum-add-classification"><span>Subject type</span>
                          <CustomSelect aria-label="Edit subject type" value={editForm.classification} onChange={(e) => setEditForm({ ...editForm, classification: e.target.value })}>
                            <option value="major">{kindLabel("major", (programs.find((p) => String(p.id) === String(editForm.program)) || {}).name)}</option>
                            <option value="minor">{kindLabel("minor")}</option>
                          </CustomSelect>
                        </label>
                        <label className="curriculum-add-field curriculum-add-academic-field"><span>Academic field (optional)</span>
                          <CustomSelect aria-label="Edit academic field" value={editForm.field} onChange={(e) => setEditForm({ ...editForm, field: e.target.value })}>
                            <option value="">-- none --</option>
                            {academicFields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                          </CustomSelect>
                        </label>
                        <button type="button" disabled={savingEdit} onClick={() => saveEdit(s.id)}>
                          {savingEdit ? "Saving…" : "Save changes"}
                        </button>
                        <button type="button" disabled={savingEdit} onClick={cancelEdit}>Cancel</button>
                      </div>
                      {editError && <p role="alert" style={{ color: "#b42318", margin: "8px 0 0", fontSize: 13 }}>{editError}</p>}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
          {paginatedSubjects.length === 0 && <tr><td colSpan={9} className="coverage-empty">No subjects found for this program yet. Add one using the form above.</td></tr>}
        </tbody>
      </table>
        </div>
        <div className="curriculum-pagination" aria-label="Subject table pagination">
          <span>{filtered.length ? `${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, filtered.length)} of ${filtered.length}` : "0 subjects"}</span>
          <div>
            <button type="button" onClick={() => setCurrentPage(1)} disabled={currentPage === 1} aria-label="First page">«</button>
            <button type="button" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={currentPage === 1}>Previous</button>
            <span>Page {currentPage} of {pageCount}</span>
            <button type="button" onClick={() => setCurrentPage((page) => Math.min(pageCount, page + 1))} disabled={currentPage >= pageCount}>Next</button>
            <button type="button" onClick={() => setCurrentPage(pageCount)} disabled={currentPage >= pageCount} aria-label="Last page">»</button>
          </div>
        </div>
      </section>
    </div>
  );
}

/* ---------------- Exam Schedule: Registrar owns minors, Dean owns majors (own dept) ---------------- */
/* ---------------- Analytics: institution-wide ---------------- */
/* New read-only insight cards for the Registrar (Gen Ed; every college). Mounted under the existing analytics. */
function RegistrarInsights() {
  const [filters, setFilters] = useState({});
  return (
    <div className="registrar-analytics-insights" style={{ marginTop: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <h3 className="analytics-section-title"><AnalyticsIcon type="analytics" />Insights — Gen Ed and every college</h3>
        <InsightFilters value={filters} onChange={setFilters} />
      </div>
      <GenEdCoverageCard filters={filters} />
      <RoomHeatmapCard filters={filters} />
      <DependenciesCard filters={filters} />
      <CapacityCard filters={filters} />
    </div>
  );
}

function AnalyticsIcon({ type }) {
  const paths = {
    analytics: <><path d="M3 17V3m0 14h14" /><path d="m5.5 13 3-3.5 2.7 1.8 4.3-5.1" /><circle cx="5.5" cy="13" r=".8" /><circle cx="8.5" cy="9.5" r=".8" /><circle cx="11.2" cy="11.3" r=".8" /><circle cx="15.5" cy="6.2" r=".8" /></>,
    people: <><circle cx="8" cy="7" r="3" /><path d="M2.5 17c.5-2.7 2.3-4 5.5-4s5 1.3 5.5 4M14 5a2.5 2.5 0 0 1 0 4.8M14.5 13c1.7.4 2.7 1.7 3 4" /></>,
    room: <><path d="M4 18V3h12v15M2 18h16M8 18v-4h4v4" /><circle cx="13.5" cy="9" r=".5" /></>,
    calendar: <><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6.5 2.5v3M13.5 2.5v3M3.5 8h13M7 11h2m2 0h2m-6 3h2" /></>,
    layers: <><path d="m10 2.5 7.5 4.2L10 11 2.5 6.7z" /><path d="m2.5 10.5 7.5 4.2 7.5-4.2M2.5 14.3l7.5 4.2 7.5-4.2" /></>,
    clock: <><circle cx="10" cy="10" r="7" /><path d="M10 6v4l2.8 1.8" /></>,
    check: <><circle cx="10" cy="10" r="7" /><path d="m6.5 10 2.3 2.3 4.8-5" /></>,
    dependency: <><circle cx="4" cy="5" r="2" /><circle cx="16" cy="5" r="2" /><circle cx="10" cy="16" r="2" /><path d="m5.7 6.2 2.8 7.1m5.8-7.1-2.8 7.1M6 5h8" /></>,
    capacity: <><circle cx="8" cy="7" r="3" /><path d="M2.5 17c.5-2.7 2.3-4 5.5-4s5 1.3 5.5 4M14 7h4m-2-2v4" /></>,
  };
  return <svg className="analytics-heading-icon" viewBox="0 0 20 20" aria-hidden="true">{paths[type] || paths.analytics}</svg>;
}

function AnalyticsTab() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [sem, setSem] = useState("");

  useEffect(() => {
    setLoadError("");
    API.get("/analytics/", { params: sem ? { semester: sem } : {} })
      .then((res) => setData(res.data))
      .catch((err) => setLoadError(err.code === "ECONNABORTED"
        ? "Analytics took too long to load (slow connection or database)."
        : (err.response?.data?.detail || "Could not load analytics.")));
  }, [attempt, sem]);

  if (loadError) return <p style={{ color: "red" }}>{loadError} <button onClick={() => setAttempt((n) => n + 1)}>Try again</button></p>;
  if (!data) return <div className="analytics-chart-grid" aria-label="Loading analytics">{[0, 1].map((i) => <div className="analytics-chart-card" key={i}><HBarChart loading /></div>)}</div>;

  return (
    <div className="registrar-analytics-view">
      <WorkloadPanel canConfigure canSuggest analyticsStyle />
      <h3 className="analytics-section-title"><AnalyticsIcon type="analytics" />Analytics — Institution-Wide</h3>
      {data.semesters && data.semesters.length > 1 && (
        <p className="analytics-filter-note" style={{ fontSize: "13px", color: "#374151" }}>
          Semester:{" "}
          <CustomSelect className="registrar-analytics-semester" value={data.semester || ""} onChange={(e) => setSem(e.target.value)}>
            {data.semesters.map((s) => <option key={s} value={s}>{s}</option>)}
          </CustomSelect>{" "}
          (1st and 2nd Sem use the same rooms and teachers, so each is shown on its own.)
        </p>
      )}
      <p className="analytics-description" style={{ fontSize: "13px", color: "#6b7280", marginTop: 0 }}>
        A workforce/HR-style view of how teaching load and room capacity are actually being used.
      </p>

      <div className="registrar-analytics-summary" style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginBottom: "24px" }}>
        <StatTile label="Schedule Efficiency" value={`${data.schedule_efficiency}%`} icon={<AnalyticsIcon type="analytics" />} />
        <StatTile label="Workload Std. Deviation" value={`${data.workload_std_dev} hrs`} accent="#b8860b" icon={<AnalyticsIcon type="layers" />} />
        <StatTile label="Teachers With Load" value={Object.keys(data.teacher_workload).length} icon={<AnalyticsIcon type="people" />} />
        <StatTile label="Rooms In Use" value={Object.keys(data.room_utilization).length} icon={<AnalyticsIcon type="room" />} />
      </div>

      <div className="analytics-chart-grid">
        <CollapsibleChartPanel title={<><AnalyticsIcon type="people" />Teacher Workload</>} ariaTitle="Teacher Workload">
          <HBarChart
            data={Object.entries(data.teacher_workload).map(([t, c]) => ({ label: t, name: data.teacher_names?.[t], value: c })).sort((a, b) => b.value - a.value)}
            unit=" hrs"
            emptyText="No schedule entries yet."
          />
        </CollapsibleChartPanel>
        <CollapsibleChartPanel title={<><AnalyticsIcon type="room" />Room Utilization</>} ariaTitle="Room Utilization">
          <HBarChart
            data={Object.entries(data.room_utilization).map(([r, c]) => ({ label: r, value: c })).sort((a, b) => b.value - a.value)}
            color="#b8860b"
            unit=" hrs"
            emptyText="No schedule entries yet."
          />
        </CollapsibleChartPanel>
      </div>

      <div className="analytics-chart-grid analytics-chart-grid-secondary">
        <CollapsibleChartPanel title={<><AnalyticsIcon type="calendar" />Class Hours by Day</>} ariaTitle="Class Hours by Day">
          <HBarChart
            data={Object.entries(data.class_hours_by_day || {}).map(([d, n]) => ({ label: d, value: n }))}
            unit=" hrs" emptyText="No schedule entries yet."
          />
        </CollapsibleChartPanel>
        <CollapsibleChartPanel title={<><AnalyticsIcon type="layers" />Schedule Status</>} ariaTitle="Schedule Status">
          <HBarChart
            data={Object.entries(data.schedule_status || {}).map(([k, n]) => ({ label: k.charAt(0).toUpperCase() + k.slice(1), value: n }))}
            color="#b8860b" unit=" hrs" emptyText="No schedule entries yet."
          />
        </CollapsibleChartPanel>
      </div>

      <CollapsibleChartPanel className="analytics-chart-card analytics-activity-card" title={<><AnalyticsIcon type="clock" />Recent Activity</>} ariaTitle="Recent Activity">
        <RecentActivity items={data.recent_activity} />
      </CollapsibleChartPanel>
    </div>
  );
}

/* ---------------- Generate schedule: triggers the CSP engine ---------------- */
/* ---------------- Faculty Coverage: Dean Villanueva's interview --------------
 * "Dapat able ang system to recommend" a stand-in when a faculty becomes
 * unavailable. This is a same-department coverage suggestion drawn from
 * CURRENT faculty (same-subject + free first, else any free, lowest load),
 * not a dedicated substitute-teacher pool -- there isn't one. Nothing here
 * rewrites the recurring weekly Schedule; it only records who is covering a
 * specific absence date, for visibility/reporting. ------------------------ */
function CoverageTab() {
  const [facultyList, setFacultyList] = useState([]);
  const [absences, setAbsences] = useState([]);
  const [form, setForm] = useState({ faculty: "", date: "", reason: "" });
  const [suggestions, setSuggestions] = useState(null);
  const [activeAbsenceId, setActiveAbsenceId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadingSuggestionsId, setLoadingSuggestionsId] = useState(null);
  const [error, setError] = useState("");
  const [config, setConfig] = useState(null);
  const facultyPickerOptions = React.useMemo(() => facultyList.map((f) => ({
    id: f.id,
    label: f.full_name && f.full_name !== f.username ? `${f.full_name} (${f.username})` : f.username,
    search: `${f.full_name || ""} ${f.username || ""}`,
  })), [facultyList]);

  const load = () => {
    API.get("/faculty/profiles/").then((res) => setFacultyList(res.data)).catch(reportLoadError("the faculty list"));
    API.get("/faculty/absences/").then((res) => setAbsences(res.data)).catch(reportLoadError("faculty absences"));
    API.get("/engine/scheduling-config/").then((res) => setConfig(res.data)).catch(reportLoadError("the scheduling settings"));
  };
  useEffect(() => { load(); }, []);

  const reportAbsence = async () => {
    setError("");
    if (!form.faculty || !form.date || busy) return;
    setBusy(true);
    try {
      const res = await API.post("/faculty/absences/", {
        faculty: form.faculty, date: form.date, reason: form.reason, status: "approved",
      });
      setForm({ faculty: "", date: "", reason: "" });
      load();
      await getSuggestions(res.data.id);
    } catch (err) {
      setError("Could not record absence -- " + (err.response?.data?.detail || "check the fields above."));
      setBusy(false);
    }
  };

  const getSuggestions = async (absenceId) => {
    if (loadingSuggestionsId !== null) return;
    setLoadingSuggestionsId(absenceId);
    setBusy(true);
    setError("");
    setActiveAbsenceId(absenceId);
    try {
      const res = await API.post("/engine/suggest-substitute/", { absence_id: absenceId });
      setSuggestions(res.data.suggestions);
    } catch (err) {
      setError("Could not generate coverage suggestions.");
      setSuggestions(null);
    } finally {
      setLoadingSuggestionsId(null);
      setBusy(false);
    }
  };

  const apply = async (coverageSuggestionId) => {
    if (busy) return;
    setBusy(true);
    try {
      await API.post("/engine/apply-coverage/", { coverage_suggestion_id: coverageSuggestionId });
    } catch (err) {
      setError(err.response?.data?.detail || "Could not apply this coverage.");
    }
    await getSuggestions(activeAbsenceId);
    load();
  };

  const updateTolerance = async (minutes) => {
    await API.patch("/engine/scheduling-config/", { student_overlap_tolerance_minutes: minutes });
    load();
  };

  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const activeAbsences = absences.filter((a) => a.status !== "denied");
  const coverageStats = [
    { label: "Open absence reports", value: activeAbsences.filter((a) => a.coverage_status !== "applied").length, icon: "calendar" },
    { label: "Coverage pending", value: activeAbsences.filter((a) => a.coverage_status === "suggested").length, icon: "layers" },
    { label: "Today's absences", value: activeAbsences.filter((a) => a.date === todayKey).length, icon: "today" },
    { label: "Resolved (last 7 days)", value: activeAbsences.filter((a) => a.coverage_status === "applied" && a.submitted_at && new Date(a.submitted_at) >= weekAgo).length, icon: "check" },
  ];

  const CoverageIcon = ({ type }) => {
    const paths = {
      calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 14h3M8 17h6" /></>,
      layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
      today: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18" /><path d="m9 15 2 2 4-4" /></>,
      check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>,
      people: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="10" cy="7" r="4" /><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
      info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
      gear: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1-2.8-2.8.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3v-4h.2a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 2.8-2.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V3h4v.2a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 2.8 2.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    };
    return <svg className="coverage-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[type] || paths.info}</svg>;
  };

  return (
    <div className="coverage-dashboard">
      <section className="coverage-stat-row" aria-label="Faculty coverage summary">
        {coverageStats.map((stat) => <div className="coverage-stat" key={stat.label}>
          <span className="coverage-stat-icon"><CoverageIcon type={stat.icon} /></span>
          <span className="coverage-stat-copy"><strong>{stat.label}</strong><b>{stat.value}</b></span>
        </div>)}
      </section>

      <div className="coverage-top-grid">
        <section className="coverage-panel coverage-report-panel">
          <div className="coverage-panel-heading">
            <span className="coverage-panel-icon"><CoverageIcon type="people" /></span>
            <div><h3>Report a faculty absence</h3><p>Log an absence and get coverage options based on availability and workload.</p></div>
            <img className="coverage-card-illustration coverage-report-illustration" src={coverageReportIllustration} alt="" aria-hidden="true" />
          </div>
          <div className="coverage-form-grid">
            <label>Faculty <span aria-hidden="true">*</span>
              <TeacherPicker className="coverage-faculty-picker" options={facultyPickerOptions} value={form.faculty}
                onChange={(faculty) => setForm((current) => ({ ...current, faculty }))} emptyLabel="Select faculty member"
                placeholder="Select faculty member" ariaLabel="Faculty member" emptyText="No faculty found" footer="Search by name or employee ID." />
            </label>
            <label>Absence date <span aria-hidden="true">*</span>
              <CustomDatePicker value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} aria-label="Absence date" />
            </label>
            <label className="coverage-reason-field">Reason <span aria-hidden="true">*</span>
              <input className="coverage-reason" maxLength={200} placeholder="e.g., Medical leave, Official business, Personal emergency" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
              <small>{form.reason.length} / 200</small>
            </label>
          </div>
          <button className="coverage-submit" onClick={reportAbsence} disabled={busy || !form.faculty || !form.date || !form.reason.trim()}>
            {busy ? "Finding coverage…" : "✦  Report & Get Coverage Suggestions"}
          </button>
        </section>

        <div className="coverage-side-stack">
          <section className="coverage-panel coverage-policy-panel">
            <div className="coverage-panel-heading">
              <span className="coverage-panel-icon"><CoverageIcon type="gear" /></span>
              <div><h3>Scheduling policy</h3><p>Rules used when generating coverage schedules.</p></div>
              <img className="coverage-card-illustration coverage-policy-illustration" src={coveragePolicyIllustration} alt="" aria-hidden="true" />
            </div>
            <ul>
              <li>Use qualified faculty with available time slots.</li>
              <li>Prefer the same department or course expertise.</li>
              <li>Avoid schedule conflicts and workload overload.</li>
              <li>Apply the exam grace window for exam-related absences.</li>
            </ul>
            {config && <label className="coverage-grace-field">Exam grace window
              <input className="grace-window-input" type="number" min="0" max="120" defaultValue={config.student_overlap_tolerance_minutes} onBlur={(e) => updateTolerance(Number(e.target.value))} /> minutes
            </label>}
          </section>
          <section className="coverage-panel coverage-howto-panel">
            <div className="coverage-panel-heading">
              <span className="coverage-panel-icon"><CoverageIcon type="info" /></span>
              <div><h3>How to use this tab (Simplified)</h3></div>
            </div>
            <div className="coverage-steps">
              <div><b>1</b><span>Report an absence with the date and reason.</span></div><i>›</i>
              <div><b>2</b><span>Review recommended coverage options.</span></div><i>›</i>
              <div><b>3</b><span>Apply coverage to update affected schedules.</span></div>
            </div>
          </section>
        </div>
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}

      {suggestions && (
        <section className="coverage-panel coverage-suggestions-panel">
          <h3>Coverage suggestions</h3>
          {suggestions.length === 0 ? (
            <div className="coverage-empty-suggestions" role="status">
              <strong>No coverage suggestions</strong>
              <p>No scheduled classes were found for this faculty on the selected absence date.</p>
            </div>
          ) : <table>
            <thead><tr><th>Class</th><th>Needs</th><th>Time</th><th>Suggested faculty</th><th>Their specialization</th><th>Reason</th><th></th></tr></thead>
            <tbody>
              {suggestions.map((s) => (
                <tr key={s.coverage_suggestion_id}>
                  <td>{s.subject} — {s.section}</td>
                  <td>{s.subject_field ? <Badge tone="neutral">{s.subject_field}</Badge> : <span style={{ color: "#6b7280" }}>—</span>}</td>
                  <td>{s.timeslot}</td>
                  <td>{s.suggested_faculty_name || <em>No one available</em>}</td>
                  <td>
                    {(s.suggested_faculty_specializations || []).length > 0
                      ? s.suggested_faculty_specializations.map((spec) => (
                          <Badge key={spec} tone={spec === s.subject_field ? "success" : "neutral"}>{spec}</Badge>
                        ))
                      : s.suggested_faculty_id ? <span style={{ color: "#6b7280", fontSize: "12px" }}>No specialization on file</span> : null}
                  </td>
                  <td style={{ fontSize: "12px", color: "#6b7280" }}>{s.reason}</td>
                  <td>
                    {s.suggested_faculty_id && (
                      <button onClick={() => apply(s.coverage_suggestion_id)}>Apply</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>}
        </section>
      )}

      <section className="coverage-panel coverage-recent-panel">
        <div className="coverage-recent-heading"><div className="coverage-panel-heading">
          <span className="coverage-panel-icon"><CoverageIcon type="calendar" /></span>
          <div><h3>Recent absences</h3><p>Recently reported absences and their coverage status.</p></div>
        </div><span className="coverage-count">{activeAbsences.length} reports</span></div>
        <div className="coverage-table-wrap"><table className="coverage-table">
        <thead><tr><th>#</th><th>Faculty</th><th>Date</th><th>Reason</th><th>Coverage status</th><th>Actions</th></tr></thead>
        <tbody>
          {activeAbsences.map((a, index) => (
            <tr key={a.id}>
              <td>{index + 1}</td>
              <td><span className="coverage-faculty-name"><CoverageIcon type="people" />{a.faculty_name}</span></td>
              <td>{a.date}</td>
              <td>{a.reason || "—"}</td>
              <td>
                {a.coverage_status === "applied" && <Badge tone="success">Covered</Badge>}
                {a.coverage_status === "suggested" && <Badge tone="warning">Coverage pending</Badge>}
                {(!a.coverage_status || a.coverage_status === "none") && <Badge tone="neutral">Open</Badge>}
              </td>
              <td><button className="coverage-view-button" onClick={() => getSuggestions(a.id)} disabled={loadingSuggestionsId !== null} aria-busy={loadingSuggestionsId === a.id}>
                {loadingSuggestionsId === a.id ? <><span className="coverage-button-spinner" aria-hidden="true" />Finding suggestions…</> : <>↻ &nbsp;View / Re-run suggestions</>}
              </button></td>
            </tr>
          ))}
          {activeAbsences.length === 0 && <tr><td className="coverage-empty" colSpan="6">No absence reports yet. Reports will appear here.</td></tr>}
        </tbody>
        </table></div>
      </section>
    </div>
  );
}

export default RegistrarDashboard;
