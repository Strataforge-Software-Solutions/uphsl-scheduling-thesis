import HowToUse from "./HowToUse";
import { reportLoadError } from "../services/loadError";
import { RegistrarHome } from "./HomeWrappers";
import React, { useState, useEffect } from "react";
import { onJump } from "../services/jump";
import { useLandingTab } from "../services/preferences";
import API, { getCurrentUser, logout } from "../services/api";
import { formatSchedule } from "../utils/formatSchedule";
import { LecLabTag, buildLecLabIndex } from "../utils/lecLab";
import { mergeSchedulesByDay, sortByDayTime } from "../utils/mergeSchedules";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import { StatTile, HBarChart, RecentActivity } from "./Charts";
import { kindLabel } from "../utils/labels";
import ScheduleEditModal from "./ScheduleEditModal";
import ScheduleProblemsModal from "./ScheduleProblemsModal";
import PrintPreviewButton, { printYears } from "./PrintPreviewButton";
import { GenEdRequestsPanel } from "./GenEdRequests";
import { useScheduleActions, SelectionBar, RowActions, btnStyle } from "./ScheduleActions";
import { GenEdCoverageCard, RoomHeatmapCard, DependenciesCard, CapacityCard, InsightFilters } from "./InsightCards";
import ClashDialog from "./ClashDialog";
import ExamSchedulePanel from "./ExamSchedulePanel";
import GenerateSchedulePanel from "./GenerateSchedulePanel";
import ErrorBoundary from "./ErrorBoundary";
import ConflictChecker from "./ConflictChecker";
import MinorSchedulesPanel from "./MinorSchedulesPanel";
import WorkloadPanel from "./WorkloadPanel";
import "./DashboardTheme.css";
import { OverrideBadge } from "./AssignAnywayDialog";

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
  const landing = useLandingTab(NAV_ITEMS, "home");
  const [activeTab, setActiveTab] = useState(landing);
  useEffect(() => onJump((t) => { if (t === "gened-requests") setActiveTab("schedules"); }), []);
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
        userName={user?.username || "Registrar"}
        userRole="Registrar staff"
        onSignOut={handleLogout}
      />

      <div className="app-main">
        <TopBar crumb={header.title} userName={user?.username} />
        <PageHeader eyebrow={header.eyebrow} title={header.title} subtitle={header.subtitle} />

        <div className="app-page-body">
          {activeTab !== "home" && <HowToUse role="registrar" tab={activeTab} />}
          {activeTab === "home" && <RegistrarHome nav={NAV_ITEMS} onNavigate={setActiveTab} name={user?.username} />}
          {["curriculum", "exams"].includes(activeTab) && (
            <div className="app-toolbar">
              <select value={college} onChange={(e) => setCollege(e.target.value)}>
                {colleges.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={programId} onChange={(e) => setProgramId(e.target.value)}>
                {programsInCollege.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}

          {/* Schedules has its own self-contained filter bar (search, college,
              status, year level, semester, reset) instead of the shared
              college/program toolbar above -- it needs to let the Registrar
              browse across every college at once, not just one program. */}
          {activeTab === "schedules" && <SchedulesTab />}
          {activeTab === "curriculum" && <CurriculumTab programId={programId} defaultProgram={programId} />}
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

  const load = () => {
    setLoading(true);
    Promise.allSettled([
      API.get("/engine/schedules/"),
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
        setSchedules(schedRes.value.data);
        // Rooms/faculty only feed the Edit dialog's dropdowns -- if one of
        // them fails the table should still show.
        if (roomRes.status === "fulfilled") setRooms(roomRes.value.data);
        if (facRes.status === "fulfilled") setFaculty(facRes.value.data);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

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
  const lecLabIndex = buildLecLabIndex(grouped);

  const resetFilters = () => {
    setSearch(""); setCollegeFilter(""); setProgramFilter(""); setStatusFilter(""); setYearLevel(""); setSemester(""); setTypeFilter("");
  };

  // The Registrar owns MINOR subjects only; the Dean's major subjects are shown for reference (view only).
  const isMine = (row) => row.subject_classification === "minor";
  const draftCount = filtered.filter((s) => isMine(s) && s.status === "draft").length;
  const approvedCount = filtered.filter((s) => isMine(s) && s.status === "approved").length;

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
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
        <div>
          <h3 style={{ marginBottom: "2px" }}>Class schedule</h3>
          <p style={{ fontSize: "13px", color: "#6b7280", margin: 0 }}>
            {filtered.length} entries shown
            {collegeFilter && ` · ${collegeFilter}`}{programFilter && ` · ${(programOptions.find(([id]) => String(id) === String(programFilter)) || [])[1] || ""}`}{yearLevel && ` · ${yearLevel}`}{semester && ` · ${semester}`}
            {draftCount > 0 && ` · ${draftCount} Draft`}{approvedCount > 0 && ` · ${approvedCount} Approved`}
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
          {/* the PDF follows the filters below (college, program, year level, semester, status, Gen Ed / program subjects) */}
          <PrintPreviewButton disabled={grouped.length === 0} onFixed={load} yearChoices={printYears(schedules)} defaultYear={yearLevel}
            params={{ department: collegeFilter, program_id: programFilter, semester, status: statusFilter, classification: typeFilter }} />
          <p style={{ fontSize: "13px", color: "#4b5563", margin: 0, maxWidth: 360, textAlign: "right" }}>
            Tick the Gen Ed classes to approve, publish or remove (the top box selects every one shown by this filter).
          </p>
        </div>
      </div>
      <GenEdRequestsPanel role="registrar" onChanged={load} />

      <div style={{
        display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center",
        background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 14px", marginBottom: "16px",
      }}>
        <input
          placeholder="Search subjects, teachers, sections"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...filterInputStyle, flex: "1 1 220px", minWidth: "200px" }}
        />
        <select value={collegeFilter} onChange={(e) => { setCollegeFilter(e.target.value); setProgramFilter(""); }} style={filterInputStyle}>
          <option value="">All colleges</option>
          {collegeOptions.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={programFilter} onChange={(e) => setProgramFilter(e.target.value)} style={filterInputStyle}>
          <option value="">All programs</option>
          {programOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={filterInputStyle}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="approved">Approved</option>
          <option value="published">Published</option>
        </select>
        <select value={yearLevel} onChange={(e) => setYearLevel(e.target.value)} style={filterInputStyle}>
          <option value="">All year levels</option>
          {yearLevelOptions.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <select value={semester} onChange={(e) => setSemester(e.target.value)} style={filterInputStyle}>
          <option value="">All semesters</option>
          {semesterOptions.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={filterInputStyle}>
          <option value="">Gen Ed &amp; program subjects</option>
          <option value="minor">Gen Ed only</option>
          <option value="major">Program subjects only</option>
        </select>
        <button onClick={resetFilters} style={{ ...filterInputStyle, color: "#111827" }}>Reset</button>
      </div>

      <table className="sched-compact">
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
          {grouped.map((g) => (
            <tr key={g.key} style={selected.includes(g.key) ? { background: "#eef6ff" } : undefined}>
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
        </tbody>
      </table>

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
function CurriculumTab({ programId, defaultProgram }) {
  const [subjects, setSubjects] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [academicFields, setAcademicFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newFieldName, setNewFieldName] = useState("");

  const [form, setForm] = useState({
    code: "", title: "", lec_units: 0, lab_units: 0,
    program: "", year_level: "", semester: "", classification: "major", field: "",
  });

  const load = () => {
    setLoading(true);
    Promise.all([
      API.get("/curriculum/subjects/"),
      API.get("/curriculum/programs/"),
      API.get("/curriculum/academic-fields/"),
    ])
      .then(([subjRes, progRes, fieldRes]) => {
        setSubjects(subjRes.data);
        setPrograms(progRes.data);
        setAcademicFields(fieldRes.data);
      })
      .catch(reportLoadError("the curriculum"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (defaultProgram) setForm((f) => ({ ...f, program: defaultProgram }));
  }, [defaultProgram]);

  const filtered = programId ? subjects.filter((s) => String(s.program) === String(programId)) : subjects;

  const addSubject = async () => {
    if (!form.code || !form.title || !form.program) return;
    const payload = { ...form, field: form.field || null };
    await API.post("/curriculum/subjects/", payload);
    setForm({ code: "", title: "", lec_units: 0, lab_units: 0, program: programId, year_level: "", semester: "", classification: "major", field: "" });
    load();
  };

  const remove = async (id) => {
    if (!window.confirm("Remove this subject?")) return;
    await API.delete(`/curriculum/subjects/${id}/`);
    load();
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
    setForm((f) => ({ ...f, field: res.data.id }));
    setNewFieldName("");
  };

  const updateSubjectField = async (subjectId, fieldId) => {
    await API.patch(`/curriculum/subjects/${subjectId}/`, { field: fieldId || null });
    load();
  };

  if (loading) return <p>Loading curriculum…</p>;

  return (
    <div>
      <h3>Curriculum Management — {programs.find((p) => String(p.id) === String(programId))?.name || ""}</h3>

      <div style={{ marginBottom: "10px" }}>
        <input placeholder="New academic field (e.g. Computer Science)" value={newFieldName}
               onChange={(e) => setNewFieldName(e.target.value)} style={{ width: "260px" }} />
        <button onClick={addAcademicField}>Add Field</button>
      </div>

      <div style={{ marginBottom: "20px" }}>
        <input placeholder="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        <input placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <input type="number" placeholder="Lec Units" value={form.lec_units}
               onChange={(e) => setForm({ ...form, lec_units: Number(e.target.value) })} />
        <input type="number" placeholder="Lab Units" value={form.lab_units}
               onChange={(e) => setForm({ ...form, lab_units: Number(e.target.value) })} />
        <select value={form.program} onChange={(e) => setForm({ ...form, program: e.target.value })}>
          <option value="">-- Program --</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.department})</option>)}
        </select>
        <input placeholder="Year Level (e.g. 1st Year)" value={form.year_level}
               onChange={(e) => setForm({ ...form, year_level: e.target.value })} />
        <input placeholder="Semester (e.g. 1st Sem)" value={form.semester}
               onChange={(e) => setForm({ ...form, semester: e.target.value })} />
        <select value={form.classification} onChange={(e) => setForm({ ...form, classification: e.target.value })}>
          <option value="major">{kindLabel("major", (programs.find((p) => String(p.id) === String(form.program)) || {}).name)}</option>
          <option value="minor">{kindLabel("minor")}</option>
        </select>
        <select value={form.field} onChange={(e) => setForm({ ...form, field: e.target.value })}>
          <option value="">-- Academic Field (optional) --</option>
          {academicFields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <button onClick={addSubject}>Add Subject</button>
      </div>

      <table>
        <thead>
          <tr><th>Code</th><th>Title</th><th>Lec</th><th>Lab</th><th>Type</th><th>Department</th><th>Field</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {filtered.map((s) => (
            <tr key={s.id}>
              <td>{s.code}</td><td>{s.title}</td><td>{s.lec_units}</td><td>{s.lab_units}</td>
              <td>{kindLabel(s.classification, s.program_name)}</td>
              <td>{s.department}</td>
              <td>
                <select value={s.field || ""} onChange={(e) => updateSubjectField(s.id, e.target.value)}>
                  <option value="">-- none --</option>
                  {academicFields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </td>
              <td><button onClick={() => remove(s.id)}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------- Exam Schedule: Registrar owns minors, Dean owns majors (own dept) ---------------- */
/* ---------------- Analytics: institution-wide ---------------- */
/* New read-only insight cards for the Registrar (Gen Ed; every college). Mounted under the existing analytics. */
function RegistrarInsights() {
  const [filters, setFilters] = useState({});
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <h3 style={{ margin: 0, color: "#003366" }}>Insights — Gen Ed and every college</h3>
        <InsightFilters value={filters} onChange={setFilters} />
      </div>
      <GenEdCoverageCard filters={filters} />
      <RoomHeatmapCard filters={filters} />
      <DependenciesCard filters={filters} />
      <CapacityCard filters={filters} />
    </div>
  );
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
  if (!data) return <p>Loading analytics…</p>;

  return (
    <div>
      <WorkloadPanel canConfigure canSuggest />
      <h3 style={{ color: "#003366" }}>Analytics — Institution-Wide</h3>
      {data.semesters && data.semesters.length > 1 && (
        <p style={{ fontSize: "13px", color: "#374151" }}>
          Semester:{" "}
          <select value={data.semester || ""} onChange={(e) => setSem(e.target.value)}>
            {data.semesters.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>{" "}
          (1st and 2nd Sem use the same rooms and teachers, so each is shown on its own.)
        </p>
      )}
      <p style={{ fontSize: "13px", color: "#6b7280", marginTop: 0 }}>
        A workforce/HR-style view of how teaching load and room capacity are actually being used.
      </p>

      <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginBottom: "24px" }}>
        <StatTile label="Schedule Efficiency" value={`${data.schedule_efficiency}%`} />
        <StatTile label="Workload Std. Deviation" value={`${data.workload_std_dev} hrs`} accent="#b8860b" />
        <StatTile label="Teachers With Load" value={Object.keys(data.teacher_workload).length} />
        <StatTile label="Rooms In Use" value={Object.keys(data.room_utilization).length} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px", marginBottom: "8px" }}>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Teacher Workload</h4>
          <HBarChart
            data={Object.entries(data.teacher_workload).map(([t, c]) => ({ label: t, value: c })).sort((a, b) => b.value - a.value)}
            unit=" hrs"
            emptyText="No schedule entries yet."
          />
        </div>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Room Utilization</h4>
          <HBarChart
            data={Object.entries(data.room_utilization).map(([r, c]) => ({ label: r, value: c })).sort((a, b) => b.value - a.value)}
            color="#b8860b"
            unit=" hrs"
            emptyText="No schedule entries yet."
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px", marginTop: "20px" }}>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Class Hours by Day</h4>
          <HBarChart
            data={Object.entries(data.class_hours_by_day || {}).map(([d, n]) => ({ label: d, value: n }))}
            unit=" hrs" emptyText="No schedule entries yet."
          />
        </div>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Schedule Status</h4>
          <HBarChart
            data={Object.entries(data.schedule_status || {}).map(([k, n]) => ({ label: k.charAt(0).toUpperCase() + k.slice(1), value: n }))}
            color="#b8860b" unit=" hrs" emptyText="No schedule entries yet."
          />
        </div>
      </div>

      <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px", marginTop: "20px" }}>
        <h4 style={{ marginTop: 0, color: "#003366" }}>Recent Activity</h4>
        <RecentActivity items={data.recent_activity} />
      </div>
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
  const [error, setError] = useState("");
  const [config, setConfig] = useState(null);

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

  return (
    <div>
      <div style={{ marginBottom: "24px", padding: "14px", background: "#f9fafb", borderRadius: 6 }}>
        <h4 style={{ marginTop: 0 }}>Scheduling policy</h4>
        <p style={{ fontSize: "13px", color: "#6b7280" }}>
          Class schedules never let a section's students be in two classes at once (the scheduler's rule; no allowance).
          This grace window applies to <strong>exam</strong> scheduling only: a small overlap between a student's exam and
          another class or exam is tolerated. Teacher and room conflicts are always hard.
        </p>
        {config && (
          <label style={{ fontSize: "13px" }}>
            Exam grace window:{" "}
            <input
              type="number" min="0" max="120" style={{ width: "60px" }}
              defaultValue={config.student_overlap_tolerance_minutes}
              onBlur={(e) => updateTolerance(Number(e.target.value))}
            /> minutes
          </label>
        )}
      </div>

      <h3>Report a faculty absence</h3>
      <div style={{ marginBottom: "16px" }}>
        <select value={form.faculty} onChange={(e) => setForm({ ...form, faculty: e.target.value })}>
          <option value="">-- Faculty --</option>
          {facultyList.map((f) => <option key={f.id} value={f.id}>{f.full_name && f.full_name !== f.username ? `${f.full_name} (${f.username})` : f.username}</option>)}
        </select>
        <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        <input placeholder="Reason (optional)" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        <button onClick={reportAbsence} disabled={busy}>Report & Get Coverage Suggestions</button>
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}

      {busy && <p>Finding coverage…</p>}

      {suggestions && (
        <div style={{ marginBottom: "24px" }}>
          <h4>Coverage suggestions</h4>
          {suggestions.length === 0 && <p>No classes found for that faculty on that weekday.</p>}
          <table>
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
          </table>
        </div>
      )}

      <h3>Recent absences</h3>
      <table>
        <thead><tr><th>Faculty</th><th>Date</th><th>Reason</th><th>Coverage</th><th></th></tr></thead>
        <tbody>
          {absences.map((a) => (
            <tr key={a.id}>
              <td>{a.faculty_name}</td>
              <td>{a.date}</td>
              <td>{a.reason || "—"}</td>
              <td>
                {a.coverage_status === "applied" && <Badge tone="success">Covered</Badge>}
                {a.coverage_status === "suggested" && <Badge tone="warning">Suggested</Badge>}
                {(!a.coverage_status || a.coverage_status === "none") && <Badge tone="neutral">None yet</Badge>}
              </td>
              <td><button onClick={() => getSuggestions(a.id)}>View / Re-run suggestions</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default RegistrarDashboard;
