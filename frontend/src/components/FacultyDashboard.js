import CustomSelect from "./CustomSelect";
import CustomDatePicker from "./CustomDatePicker";
import CustomTimePicker from "./CustomTimePicker";
import React, { useState, useEffect } from "react";
import { onJump } from "../services/jump";
import { useLandingTab } from "../services/preferences";
import { reportLoadError } from "../services/loadError";
import API, { getCurrentUser, logout, displayName } from "../services/api";
import { formatSchedule } from "../utils/formatSchedule";
import { LecLabTag, buildLecLabIndex } from "../utils/lecLab";
import { mergeSchedulesByDay, sortByDayTime } from "../utils/mergeSchedules";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import PageHeader from "./PageHeader";
import Badge from "./Badge";
import { StatTile, HBarChart, RecentActivity } from "./Charts";
import ScheduleEditModal from "./ScheduleEditModal";
import { RequestMoveModal, GenEdRequestsPanel } from "./GenEdRequests";
import PrintPreviewButton, { printYears } from "./PrintPreviewButton";
import { kindLabel, kindFilterOptions } from "../utils/labels";
import DeanRooms from "./DeanRooms";
import HowToUse from "./HowToUse";
import { DeanHome } from "./HomeWrappers";
import MoveClassesModal from "./MoveClassesModal";
import ConflictChecker from "./ConflictChecker";
import ScheduleProblemsModal from "./ScheduleProblemsModal";
import NotGeneratedList from "./NotGeneratedList";
import ErrorBoundary from "./ErrorBoundary";
import { ReadinessCard, FacultyFitCard, LabCapacityCard, LoadBandsCard, InsightFilters } from "./InsightCards";
import { useScheduleActions, SelectionBar, RowActions, btnStyle } from "./ScheduleActions";
import { useConfirmDialog } from "./ConfirmDialog";
import ClashDialog from "./ClashDialog";
import ReplacementModal from "./ReplacementModal";
import ExamSchedulePanel from "./ExamSchedulePanel";
import GenerateSchedulePanel from "./GenerateSchedulePanel";
import WorkloadPanel from "./WorkloadPanel";
import OverloadBanner, { onWorkloadChanged, ResolverWindow, notifyWorkloadChanged } from "./OverloadResolver";
import AddFacultyModal from "./AddFacultyModal";
import "./DashboardTheme.css";
import { OverrideBadge } from "./AssignAnywayDialog";
import { formatDate } from "../utils/formatDateTime";

function StatusPill({ status }) {
  if (status === "published") return <Badge tone="success">Published</Badge>;
  if (status === "approved") return <Badge tone="success">Approved</Badge>;
  return <Badge tone="warning">Draft</Badge>;
}

// Same sections in the Dean, Registrar and Admin workspaces: Plan / Academics / People / Insights.
const DEAN_NAV = [
  { key: "home", label: "Home", icon: "" },
  { group: "Plan" },
  { key: "schedules", label: "Schedules", icon: "" },
  { key: "exams", label: "Exam Schedule", icon: "" },
  { key: "conflicts", label: "Conflicts", icon: "" },
  { group: "Academics" },
  { key: "curriculum", label: "Curriculum", icon: "" },
  { key: "classlists", label: "Class Lists", icon: "" },
  { group: "People" },
  { key: "availability", label: "Faculty", icon: "" },
  { key: "coverage", label: "Faculty Coverage", icon: "" },
  { group: "Insights" },
  { key: "analytics", label: "Analytics", icon: "" },
];
const FULL_TIME_NAV = [
  { group: "Plan" },
  { key: "schedule", label: "My Schedule", icon: "" },
  { group: "People" },
  { key: "availability", label: "Availability", icon: "" },
];
const PART_TIME_NAV = [
  { group: "Plan" },
  { key: "schedule", label: "My Schedule", icon: "" },
  { group: "People" },
  { key: "availability", label: "Availability", icon: "" },
];

const DEAN_HEADERS = {
  home: { title: "Home", subtitle: "Your dashboard at a glance." },
  schedules: { title: "Schedules", subtitle: "" },
  curriculum: { title: "Curriculum", subtitle: "Manage subjects for your own department." },
  classlists: { title: "Class Lists", subtitle: "Who's in each of your college's block sections." },
  conflicts: { title: "Conflicts", subtitle: "Teacher, room and student double-bookings in the class schedule." },
  exams: { title: "Exam Schedule", subtitle: "Program and Gen Ed exams — checked against every other schedule automatically." },
  coverage: { title: "Faculty Coverage", subtitle: "Report a faculty absence and get a coverage recommendation from your own college's faculty." },
  analytics: { title: "Analytics", subtitle: "Workload and room utilization for your college." },
  availability: { title: "Faculty", subtitle: "Review faculty load and availability for your college." },
};

/**
 * One dashboard for the whole "Faculty" role. What renders inside depends on
 * `facultyType`, which comes from the backend (accounts.User.faculty_type):
 *   - "dean"       -> full scheduling + curriculum authority, scoped to own department
 *   - "full_time"  -> read-only personal teaching schedule
 *   - "part_time"  -> read-only schedule + availability submission form
 */
function FacultyDashboard({ name, department, departments = [department], facultyType }) {
  const navItems = facultyType === "dean" ? DEAN_NAV : facultyType === "part_time" ? PART_TIME_NAV : FULL_TIME_NAV;
  const landing = useLandingTab(navItems, navItems.find((i) => i.key).key);
  const [activeTab, setActiveTab] = useState(landing);
  useEffect(() => onJump((t) => { if (t === "gened-requests" && facultyType === "dean") setActiveTab("schedules"); }), [facultyType]);
  const user = getCurrentUser();

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  const eyebrow = facultyType === "dean" ? `${department} · Dean View` : facultyType === "part_time" ? `Part-time Faculty · ${department}` : `Full-time Faculty · ${department}`;
  const crumb = facultyType === "dean" ? DEAN_HEADERS[activeTab]?.title : activeTab === "availability" ? "Availability" : "Schedule";
  const title = facultyType === "dean" ? DEAN_HEADERS[activeTab]?.title
    : activeTab === "availability" ? "Availability"
    : "My Schedule";
  const subtitle = facultyType === "dean" ? DEAN_HEADERS[activeTab]?.subtitle
    : activeTab === "availability" ? ""
    : "Your assigned classes for this term.";

  return (
    <div className="app-shell">
      <Sidebar
        brandLabel="U-FAST"
        workspaceLabel="Manila Campus Workspace"
        items={navItems}
        activeKey={activeTab}
        onSelect={setActiveTab}
        userName={facultyType === "dean" ? displayName(user) : name}
        userRole={facultyType === "dean" ? "College dean" : facultyType === "part_time" ? "Part-time faculty" : "Full-time faculty"}
        onSignOut={handleLogout}
      />

      <div className="app-main">
        <TopBar crumb={crumb} userName={facultyType === "dean" ? displayName(user) : user?.username} />
        <PageHeader eyebrow={eyebrow.toUpperCase()} title={title} subtitle={subtitle} />

        <div className="app-page-body">
          {facultyType === "dean" && activeTab !== "home" && <HowToUse role="dean" tab={activeTab} />}
          {facultyType === "dean" && <DeanView onNavigate={setActiveTab} name={displayName(user)} department={department} departments={departments} activeTab={activeTab} />}
          {facultyType === "full_time" && activeTab === "schedule" && (
            <>
              <WorkloadSummary username={name} />
              <ScheduleView />
            </>
          )}
          {facultyType === "full_time" && activeTab === "availability" && <AvailabilityPanel />}
          {facultyType === "part_time" && activeTab === "schedule" && (
            <>
              <WorkloadSummary username={name} />
              <ScheduleView />
            </>
          )}
          {facultyType === "part_time" && activeTab === "availability" && <AvailabilityPanel />}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Workload summary card: total hours this week vs target load ---------------- */
function WorkloadSummary({ username }) {
  const [profile, setProfile] = useState(null);
  const [totalHours, setTotalHours] = useState(0);
  const [classCount, setClassCount] = useState(0);

  React.useEffect(() => {
    API.get("/faculty/profiles/").then((res) => {
      const mine = res.data.find((p) => p.username === username);
      setProfile(mine || null);
    }).catch(reportLoadError("your faculty profile"));
    API.get("/engine/schedules/").then((res) => {
      setClassCount(res.data.length);
      const hours = res.data.reduce((sum, s) => {
        if (!s.timeslot_start || !s.timeslot_end) return sum;
        const [sh, sm] = s.timeslot_start.split(":").map(Number);
        const [eh, em] = s.timeslot_end.split(":").map(Number);
        return sum + ((eh * 60 + em) - (sh * 60 + sm)) / 60;
      }, 0);
      setTotalHours(Math.round(hours * 10) / 10);
    }).catch(reportLoadError("your classes"));
  }, [username]);

  const target = profile?.target_load_hours ?? 18;
  const percent = Math.min(100, Math.round((totalHours / target) * 100));
  const isOverload = totalHours > target;

  const cardStyle = {
    background: "white", borderRadius: 6, padding: "18px 22px",
    boxShadow: "none", border: "1px solid #e5e7eb",
    marginBottom: "20px", display: "flex", gap: "32px", alignItems: "center", flexWrap: "wrap",
  };
  const statStyle = { textAlign: "left" };
  const numStyle = { fontSize: "18px", fontWeight: 600, color: "#111827", fontVariantNumeric: "tabular-nums" };
  const labelStyle = { fontSize: "12px", color: "#6b7280" };

  return (
    <div style={cardStyle}>
      <div style={statStyle}>
        <div style={numStyle}>{totalHours}h</div>
        <div style={labelStyle}>Hours / week</div>
      </div>
      <div style={statStyle}>
        <div style={numStyle}>{classCount}</div>
        <div style={labelStyle}>Class periods</div>
      </div>
      <div style={statStyle}>
        <div style={{ ...numStyle, color: isOverload ? "#b91c1c" : "#003366" }}>{target}h</div>
        <div style={labelStyle}>Target load</div>
      </div>
      <div style={{ flex: 1, minWidth: "180px" }}>
        <div style={{ height: "10px", borderRadius: "6px", background: "#eef1f5", overflow: "hidden" }}>
          <div style={{
            width: `${percent}%`, height: "100%",
            background: isOverload ? "#b91c1c" : "#003366",
          }} />
        </div>
        <div style={{ fontSize: "12px", color: isOverload ? "#b91c1c" : "#6b7280", marginTop: "4px" }}>
          {isOverload ? `${(totalHours - target).toFixed(1)}h over target load` : `${percent}% of target load`}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Full-time & part-time: history of submitted availability ---------------- */
const PREFERENCE_BADGE = {
  preferred: { tone: "success", label: "Preferred" },
  available: { tone: "neutral", label: "Available" },
  unavailable: { tone: "warning", label: "Unavailable" },
};

/* A single row's own edit state -- day/preference/start/end -- while it's
   being corrected. Kept outside AvailabilityHistory's own state so editing
   one row never re-renders or clears the others. */
function AvailabilityRow({ row, onChanged, onDeleted }) {
  const confirmDialog = useConfirmDialog();
  const [editing, setEditing] = useState(false);
  const [day, setDay] = useState(row.day);
  const [preference, setPreference] = useState(row.preference);
  const [start, setStart] = useState(row.start_time?.slice(0, 5) || "");
  const [end, setEnd] = useState(row.end_time?.slice(0, 5) || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const inputStyle = { padding: "6px 8px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "13px", background: "white" };

  const startEdit = () => {
    setDay(row.day);
    setPreference(row.preference);
    setStart(row.start_time?.slice(0, 5) || "");
    setEnd(row.end_time?.slice(0, 5) || "");
    setError("");
    setEditing(true);
  };

  const save = async () => {
    if (!day || !start || !end) return;
    if (end <= start) { setError("End must be after start."); return; }
    setSaving(true);
    setError("");
    try {
      const res = await API.patch(`/faculty/availability/${row.id}/`, {
        day, preference, start_time: start, end_time: end,
      });
      setEditing(false);
      onChanged?.(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save this change.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!(await confirmDialog({ title: "Remove availability?", message: "Remove this availability block? The Dean and Registrar will no longer see it.", confirmLabel: "Remove availability" }))) return;
    try {
      await API.delete(`/faculty/availability/${row.id}/`);
      onDeleted?.(row.id);
    } catch (err) {
      alert(err.response?.data?.detail || "Could not remove this block.");
    }
  };

  if (editing) {
    return (
      <tr>
        <td>
          <CustomSelect style={inputStyle} value={day} onChange={(e) => setDay(e.target.value)}>
            {DAY_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
          </CustomSelect>
        </td>
        <td style={{ whiteSpace: "nowrap" }}>
          <CustomTimePicker style={{ ...inputStyle, width: "90px" }} value={start} onChange={(e) => setStart(e.target.value)} aria-label="Availability start time" />
          {" – "}
          <CustomTimePicker style={{ ...inputStyle, width: "90px" }} value={end} onChange={(e) => setEnd(e.target.value)} aria-label="Availability end time" />
          {error && <div style={{ color: "#b91c1c", fontSize: "12px", marginTop: "4px" }}>{error}</div>}
        </td>
        <td>
          <CustomSelect style={inputStyle} value={preference} onChange={(e) => setPreference(e.target.value)}>
            {PREFERENCE_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </CustomSelect>
        </td>
        <td>{row.submitted_at ? formatDate(row.submitted_at) : "—"}</td>
        <td style={{ whiteSpace: "nowrap" }}>
          <button onClick={save} disabled={saving} style={{ marginRight: "6px", background: "#003366", color: "white", border: "none", borderRadius: "6px", padding: "5px 10px", fontSize: "12px", cursor: "pointer" }}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button onClick={() => setEditing(false)} disabled={saving} style={{ background: "none", color: "#111827", border: "1px solid #d1d5db", borderRadius: "6px", padding: "5px 10px", fontSize: "12px", cursor: "pointer" }}>
            Cancel
          </button>
        </td>
      </tr>
    );
  }

  const badge = PREFERENCE_BADGE[row.preference] || PREFERENCE_BADGE.preferred;
  return (
    <tr>
      <td>{row.day}</td>
      <td>{row.start_time?.slice(0, 5)}–{row.end_time?.slice(0, 5)}</td>
      <td><Badge tone={badge.tone}>{badge.label}</Badge></td>
      <td>{row.submitted_at ? formatDate(row.submitted_at) : "—"}</td>
      <td style={{ whiteSpace: "nowrap" }}>
        <button onClick={startEdit} title="Fix a mistake in this block" style={{ marginRight: "6px", background: "none", color: "#111827", border: "1px solid #d1d5db", borderRadius: "6px", padding: "5px 10px", fontSize: "12px", cursor: "pointer" }}>
          Edit
        </button>
        <button onClick={remove} title="Remove this block" style={{ background: "none", border: "1px solid #f3c2c2", color: "#b91c1c", borderRadius: "6px", padding: "5px 10px", fontSize: "12px", cursor: "pointer" }}>
          Delete
        </button>
      </td>
    </tr>
  );
}

function AvailabilityHistory({ refreshKey }) {
  const [rows, setRows] = useState([]);

  React.useEffect(() => {
    API.get("/faculty/availability/").then((res) => setRows(res.data)).catch(reportLoadError("faculty availability"));
  }, [refreshKey]);

  const handleChanged = (updated) => {
    setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  };
  const handleDeleted = (id) => {
    setRows((prev) => prev.filter((r) => r.id !== id));
  };

  return (
    <div style={{ marginTop: "20px", maxWidth: "720px" }}>
      <h3 style={{ color: "#003366" }}>My Submitted Availability</h3>
      {rows.length === 0 ? (
        <p style={{ color: "#6b7280", fontSize: "14px" }}>You haven't submitted any availability yet.</p>
      ) : (
        <>
          <p style={{ color: "#6b7280", fontSize: "13px", marginTop: 0 }}>
            Made a mistake -- like two Monday blocks with different preferences? Edit or delete the wrong one below;
            the Dean/Registrar only ever see what's currently listed here.
          </p>
          <table>
            <thead><tr><th>Day</th><th>Time</th><th>Preference</th><th>Submitted</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <AvailabilityRow key={r.id} row={r} onChanged={handleChanged} onDeleted={handleDeleted} />
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

/* Wrapper so a freshly-saved availability block shows up in the history
   list immediately, without the two components needing to share state
   any other way. */
function AvailabilityPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div>
      <AvailabilityForm onSaved={() => setRefreshKey((k) => k + 1)} />
      <AvailabilityHistory refreshKey={refreshKey} />
    </div>
  );
}

/* ---------------- Dean view: schedules + curriculum + analytics, own dept only ---------------- */
function DeanView({ department, departments = [department], activeTab, onNavigate, name }) {
  const [programs, setPrograms] = useState([]);
  const [programId, setProgramId] = useState("");
  const [programsLoaded, setProgramsLoaded] = useState(false);

  React.useEffect(() => {
    API.get("/curriculum/programs/").then((res) => {
      setProgramsLoaded(true);
      const ownDeptPrograms = res.data.filter((p) => departments.includes(p.department));
      setPrograms(ownDeptPrograms);
      if (ownDeptPrograms.length && !programId) setProgramId(String(ownDeptPrograms[0].id));
    }).catch(reportLoadError("the programs"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department]);

  return (
    <div>
      {activeTab === "home" && <DeanHome nav={DEAN_NAV} onNavigate={onNavigate} name={name} scope={departments.join(" / ")} />}
      {["schedules", "analytics", "conflicts", "availability"].includes(activeTab) && <OverloadBanner />}
      {activeTab !== "coverage" && activeTab !== "home" && (
        <div className="app-toolbar">
          <CustomSelect value={programId} onChange={(e) => setProgramId(e.target.value)}>
            {programs.length === 0 && <option value="">No programs found</option>}
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </CustomSelect>
          {programsLoaded && programs.length === 0 && (
            <span style={{ marginLeft: "12px", fontSize: "13px", color: "#b91c1c" }}>
              No program has the department name "{departments.join('" or "')}". Ask the IT Admin to run
              {" "}<code>python manage.py prefix_departments</code> so program and account department names match.
            </span>
          )}
        </div>
      )}

      {activeTab === "schedules" && (
        <>
          <ScheduleManager programId={programId} programName={(programs.find((p) => String(p.id) === String(programId)) || {}).name || ""} departments={departments} />
          <details style={{ marginTop: 18, border: "1px solid #dbe5f1", borderRadius: 6, padding: "10px 14px", background: "white" }}>
            <summary style={{ cursor: "pointer", fontWeight: 600, color: "#003366" }}>Room assignments — preferred, alternative and fixed rooms per subject</summary>
            <p style={{ fontSize: 13, color: "#6b7280" }}>Rooms come from the room records kept by the IT Admin. A preferred or fixed room is used first when you press Generate; you can also pick a room per subject in the Generate preview.</p>
            <DeanRooms programs={programs} />
          </details>
        </>
      )}
      {activeTab === "curriculum" && <CurriculumManager programId={programId} />}
      {activeTab === "classlists" && <DeanClassListsTab department={department} departments={departments} />}
      {activeTab === "conflicts" && <ConflictChecker />}
      {activeTab === "exams" && <ExamSchedulePanel role="dean" programId={programId} />}
      {activeTab === "coverage" && <DeanCoverageTab department={department} departments={departments} />}
      {activeTab === "analytics" && <><AnalyticsPanel /><DeanInsights /></>}
      {activeTab === "availability" && <CollegeFacultyRoster department={department} departments={departments} />}
    </div>
  );
}

function ScheduleManager({ programId, programName = "", departments = [] }) {
  const [schedules, setSchedules] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [roomAssign, setRoomAssign] = useState({});     // subject id -> the Dean's preferred / alternative / fixed rooms
  const [faculty, setFaculty] = useState([]);
  const [editingGroup, setEditingGroup] = useState(null);
  const [editForm, setEditForm] = useState({ room: "", teacher: "", day: "", start_time: "", end_time: "" });
  const [saveError, setSaveError] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [pickTime, setPickTime] = useState(null);      // Edit > "Choose a new day and time" (real free times)
  const [editNote, setEditNote] = useState("");
  const [showGenerate, setShowGenerate] = useState(false);
  const [genProgramName, setGenProgramName] = useState("");      // the program chosen inside the Generate dialog (its title follows it)
  const [workloadIssue, setWorkloadIssue] = useState(null);
  const [selected, setSelected] = useState([]);       // ticked rows (group keys): the bar's actions apply to these ONLY
  const [showMove, setShowMove] = useState(false);
  const [moveNote, setMoveNote] = useState("");
  const [moveReq, setMoveReq] = useState(null);       // a Gen Ed class the Dean asks the Registrar to move (GenEdRequests.js)
  const [reqKey, setReqKey] = useState(0);
  // Year Level / Semester filter -- the Dean's own college has several
  // year levels and semesters worth of schedule rows in the same program,
  // and without this there's no way to tell which one you're looking at.
  const [yearLevel, setYearLevel] = useState("");
  const [semester, setSemester] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  // Search + status filter, matching the Registrar's schedule view.
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const load = () => {
    API.get("/engine/schedules/").then((res) => setSchedules(res.data));
    API.get("/rooms/").then((res) => setRooms(res.data));
    API.get("/rooms/dean/overview/", { params: { program_id: programId || undefined } }).then((res) => {
      const m = {};
      (res.data.subjects || []).forEach((s) => { if (s.preferred_room || (s.alternative_rooms || []).length) m[s.id] = { preferred: s.preferred_room, alts: s.alternative_rooms || [], fixed: s.is_fixed }; });
      setRoomAssign(m);
    }).catch(() => setRoomAssign({}));
    API.get("/faculty/profiles/").then((res) => setFaculty(res.data)).catch(reportLoadError("the faculty list"));
  };

  // load only when the program changes (load is re-created every render; listing it would reload in a loop)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => { load(); }, [programId]);
  // an overload resolved from the suggestions window changes teachers in the real schedule: reload the table
  React.useEffect(() => onWorkloadChanged(() => load()), [programId]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Reset the Year Level / Semester filter whenever the program changes --
  // otherwise switching programs could silently show an empty table because
  // the previous program's year/semester selection doesn't exist here.
  React.useEffect(() => { setYearLevel(""); setSemester(""); }, [programId]);

  const byProgram = programId ? schedules.filter((s) => String(s.program) === String(programId)) : schedules;
  // Year Level / Semester options are drawn from whatever's actually in this
  // program's schedule rows -- so the dropdowns never offer a combination
  // that has nothing in it.
  const yearLevelOptions = [...new Set(["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year", ...byProgram.map((s) => s.year_level)])].filter(Boolean).sort();
  const semesterOptions = [...new Set(byProgram.map((s) => s.semester))].filter((x) => /sem/i.test(x || "")).sort();

  const searchLower = search.trim().toLowerCase();
  const filtered = byProgram
    .filter((s) => !yearLevel || s.year_level === yearLevel)
    .filter((s) => !semester || s.semester === semester)
    .filter((s) => !statusFilter || s.status === statusFilter)
    .filter((s) => !typeFilter || s.subject_classification === typeFilter)
    .filter((s) => {
      if (!searchLower) return true;
      const haystack = `${s.subject_code} ${s.subject_title} ${s.teacher_name} ${s.section_name} ${s.room_name}`.toLowerCase();
      return haystack.includes(searchLower);
    });
  const grouped = sortByDayTime(mergeSchedulesByDay(filtered));
  const lecLabIndex = buildLecLabIndex(grouped);
  // A Dean edits / removes / approves MAJOR subjects only; the Registrar's minor subjects are view-only here.
  const isMine = (row) => row.subject_classification === "major";
  const editableKeys = grouped.filter(isMine).map((g) => g.key);

  const resetFilters = () => {
    setSearch(""); setStatusFilter(""); setYearLevel(""); setSemester(""); setTypeFilter("");
  };

  // Select / Approve / Publish / Back to draft / Remove act on the TICKED rows only (ScheduleActions.js; the server checks every rule:
  // the conflict check before approving, drafts-only removal with Undo, ownership).
  const actions = useScheduleActions(() => { setSelected([]); load(); });
  const selectedGroups = grouped.filter((g) => isMine(g) && selected.includes(g.key));
  const idsOf = (groups) => groups.flatMap((g) => g.ids);

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
      } else {
        const extra = override ? { override_workload: true } : {};
        // Assign anyway (not connected): the reason goes with it; the server re-checks every rule before saving
        const ov = form.override_reason ? { override_qualification: true, override_reason: form.override_reason } : {};
        await Promise.all(group.ids.map((id) => API.patch(`/engine/schedules/${id}/`, { room: form.room, teacher: form.teacher, ...extra, ...ov })));
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

  const filterSelectStyle = { padding: "9px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "13px", background: "white" };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", marginBottom: "14px", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Class schedule</h3>
        <div style={{ display: "flex", gap: "8px" }}>
          <PrintPreviewButton disabled={grouped.length === 0} onFixed={load} yearChoices={printYears(byProgram)} defaultYear={yearLevel}
            params={{ program_id: programId, semester, status: statusFilter, classification: typeFilter }} />
          <button onClick={() => setShowGenerate(true)} title={`Generate the ${programName || "program"} subject schedule`}
                  style={{ background: "#003366", color: "white" }}>
            Generate Schedule
          </button>
        </div>
      </div>

      <div style={{
        display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center",
        background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 14px", marginBottom: "16px",
      }}>
        <input
          placeholder="Search subjects, teachers, sections"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...filterSelectStyle, flex: "1 1 220px", minWidth: "200px" }}
        />
        <CustomSelect style={filterSelectStyle} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="approved">Approved</option>
          <option value="published">Published</option>
        </CustomSelect>
        <CustomSelect
          style={filterSelectStyle}
          value={yearLevel}
          onChange={(e) => setYearLevel(e.target.value)}
          title="Filter by Year Level"
        >
          <option value="">All year levels</option>
          {yearLevelOptions.map((y) => <option key={y} value={y}>{y}</option>)}
        </CustomSelect>
        <CustomSelect
          style={filterSelectStyle}
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
          title="Filter by Semester"
        >
          <option value="">All semesters</option>
          {semesterOptions.map((s) => <option key={s} value={s}>{s}</option>)}
        </CustomSelect>
        <CustomSelect style={filterSelectStyle} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          {kindFilterOptions(programName).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </CustomSelect>
        <button onClick={resetFilters} style={{ ...filterSelectStyle, color: "#111827" }}>Reset</button>
      </div>

      {/* plain information: this program's subjects that are still not generated (no fixes from here) */}
      <NotGeneratedList programId={programId} yearLevel={yearLevel} semester={semester} refreshKey={schedules.length} />
      <GenEdRequestsPanel role="dean" refreshKey={reqKey} onChanged={load} />
      {moveReq && <RequestMoveModal group={moveReq} onClose={() => setMoveReq(null)} onDone={() => setReqKey((k) => k + 1)} />}

      <table className="sched-compact schedule-list-table">
        <thead>
          <tr>
            <th style={{ width: "28px" }}>
              <input type="checkbox" aria-label="Select every program class shown by this filter"
                     checked={editableKeys.length > 0 && editableKeys.every((k) => selected.includes(k))}
                     onChange={(e) => setSelected(e.target.checked ? editableKeys : [])} />
            </th>
            <th>Subject</th><th>Type</th><th>Section</th><th>Room</th><th>Teacher</th><th>Time</th><th>Status</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {grouped.map((g) => (
            <tr key={g.key} style={selected.includes(g.key) ? { background: "#eef6ff" } : undefined}>
              <td>
                {isMine(g) && (
                  <input type="checkbox" aria-label={`Select ${g.subject_title}`} checked={selected.includes(g.key)}
                         onChange={(e) => setSelected((cur) => e.target.checked ? [...cur, g.key] : cur.filter((k) => k !== g.key))} />
                )}
              </td>
              <td>{g.subject_code} — {g.subject_title}<LecLabTag row={g} index={lecLabIndex} /></td>
              <td><Badge tone={g.subject_classification === "major" ? "success" : "neutral"}>{kindLabel(g.subject_classification, g.program_name)}</Badge></td>
              <td>
                {g.section_name}
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
              <td>{g.qualification_override && <><OverrideBadge reason={g.qualification_override.reason} />{" "}</>}{g.is_manual_override && <span title="Edited by hand: Generate keeps it where it is (locked)"><Badge tone="warning">Edited</Badge>{" "}</span>}<StatusPill status={g.status} /></td>
              <td>
                {!isMine(g) ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 3 }}>
                    <span style={{ fontSize: "12px", color: "#6b7280" }} title="Gen Ed subjects are edited by the Registrar">View only</span>
                    {g.subject_classification === "minor" && (
                      <button type="button" onClick={() => setMoveReq(g)} title="Ask the Registrar to move this Gen Ed class (e.g. to free its time for a major)"
                        style={{ background: "white", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "2px 8px", fontSize: 12, cursor: "pointer", whiteSpace: "nowrap" }}>
                        Request move
                      </button>
                    )}
                  </div>
                ) : (
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
        onClear={() => setSelected([])}
        extra={(() => { const d = selectedGroups.filter((g) => g.status === "draft").length; return (
          <button disabled={actions.busy || !d} onClick={() => setShowMove(true)} style={{ ...btnStyle("#ffffff", "#0f2747", "1px solid #ffffff"), opacity: d ? 1 : 0.45 }}
            title="Change the day and start time of the selected drafts (clashes and the Lec / Lab order are checked)">Change day / time{d ? ` (${d})` : ""}</button>); })()} />
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
      {moveNote && <div style={{ background: "#eafaf0", border: "1px solid #b7e4c7", color: "#1e5f3a", padding: "8px 12px", borderRadius: 6, fontSize: "13px", marginBottom: "10px" }}>{moveNote}</div>}
      {showMove && (
        <MoveClassesModal
          groups={selectedGroups.filter((g) => g.status === "draft")}
          describe={(g) => formatSchedule(g.timeslot_day, g.start, g.end)}
          onClose={() => setShowMove(false)}
          onDone={(r) => { setShowMove(false); setSelected([]); setMoveNote(`Moved ${r.classes} class${r.classes > 1 ? "es" : ""}.`); load(); }}
        />
      )}

      <ClashDialog
        clash={editClash} picked={editPicked} busy={savingEdit} applyLabel="Apply this time"
        onPick={(c, sug) => setEditPicked({ [[...c.ids].sort((x, y) => x - y).join("-")]: sug })}
        onBack={() => { setEditClash(null); setEditPicked({}); }}
        onApply={applySuggestion}
      />

      <ScheduleEditModal
        onOverrideRemoved={() => { setEditingGroup(null); load(); }}
        roomAssignment={editingGroup ? roomAssign[editingGroup.subject] : undefined}
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

      {showGenerate && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "12px" }}>
          <div style={{ background: "white", borderRadius: 6, padding: "22px 26px", width: "min(1240px, 96vw)", maxWidth: "100%", maxHeight: "92vh", overflowY: "auto", overflowX: "hidden", boxSizing: "border-box" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <h3 style={{ margin: 0, color: "#003366" }}>Generate Schedule — {genProgramName || programName || "Program"} Subjects</h3>
              <button onClick={() => { setShowGenerate(false); load(); }} aria-label="Close"
                      style={{ border: "1px solid #d1d5db", background: "white", color: "#374151", fontSize: "13px", fontWeight: 600, padding: "6px 12px", borderRadius: 4, cursor: "pointer" }}>Close</button>
            </div>
            <ErrorBoundary what="the Generate Schedule dialog">
              <GenerateSchedulePanel role="dean" departments={departments} initialProgramId={programId} hideTitle onGenerated={load} onProgramName={setGenProgramName} />
            </ErrorBoundary>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Dean's Faculty Coverage: Dean Villanueva's interview --------
 * Same feature as RegistrarDashboard's CoverageTab, scoped to this Dean's own
 * department -- "dapat able ang system to recommend" a stand-in from current
 * faculty when someone becomes unavailable. Doesn't rewrite the recurring
 * weekly Schedule; just records who is covering a specific absence date. --- */
function DeanCoverageTab({ department, departments = [department] }) {
  const [facultyList, setFacultyList] = useState([]);
  const [absences, setAbsences] = useState([]);
  const [form, setForm] = useState({ faculty: "", date: "", reason: "" });
  const [suggestions, setSuggestions] = useState(null);
  const [activeAbsenceId, setActiveAbsenceId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Was `!f.department || f.department === department` -- treating a blank/null
  // department as belonging to EVERY department, so any faculty account with
  // no department set leaked into every Dean's Faculty Coverage tab (visible
  // and selectable, with their absences shown too). Only an exact match now.
  const ownDeptFaculty = facultyList.filter((f) => departments.includes(f.department));

  const load = () => {
    API.get("/faculty/profiles/").then((res) => setFacultyList(res.data)).catch(reportLoadError("the faculty list"));
    API.get("/faculty/absences/").then((res) => setAbsences(res.data)).catch(reportLoadError("faculty absences"));
  };
  React.useEffect(() => { load(); }, []);

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

  const ownDeptAbsences = absences.filter((a) => ownDeptFaculty.some((f) => f.id === a.faculty));

  return (
    <div>
      <h3>Report a faculty absence — {department}</h3>
      <div className="coverage-absence-form">
        <CustomSelect className="faculty-picker-select" value={form.faculty} onChange={(e) => setForm({ ...form, faculty: e.target.value })}>
          <option value="">-- Faculty --</option>
          {ownDeptFaculty.map((f) => <option key={f.id} value={f.id}>{f.full_name && f.full_name !== f.username ? `${f.full_name} (${f.username})` : f.username}</option>)}
        </CustomSelect>
        <CustomDatePicker value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} aria-label="Absence date" />
        <input className="coverage-reason" placeholder="Reason (optional)" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
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
                  <td>{s.suggested_faculty_id && <button onClick={() => apply(s.coverage_suggestion_id)}>Apply</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Recent absences — {department}</h3>
      <table>
        <thead><tr><th>Faculty</th><th>Date</th><th>Reason</th><th>Coverage</th><th></th></tr></thead>
        <tbody>
          {ownDeptAbsences.map((a) => (
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

/* ---------------- Dean's Class Lists: who's in each of the college's block
 * sections. Same idea as Registrar's ClassListsTab, scoped to this Dean's own
 * department -- not a student portal, just roster data so Full-time/Part-time
 * faculty can see "who's in my class" on their own schedule view. ----------- */
function DeanClassListsTab({ department, departments = [department] }) {
  const confirmDialog = useConfirmDialog();
  const [students, setStudents] = useState([]);
  const [sections, setSections] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sectionFilter, setSectionFilter] = useState("");
  // upload card
  const [upProgram, setUpProgram] = useState("");
  const [upSemester, setUpSemester] = useState("");
  const [upFile, setUpFile] = useState(null);
  const [upBusy, setUpBusy] = useState(false);
  const [upError, setUpError] = useState("");
  const [upResult, setUpResult] = useState(null);      // preview / import summary from the server
  const [upDone, setUpDone] = useState("");
  const [loadError, setLoadError] = useState("");

  const load = () => {
    setLoading(true);
    Promise.all([API.get("/engine/students/"), API.get("/engine/sections/"), API.get("/curriculum/programs/")])
      .then(([stuRes, secRes, progRes]) => {
        const own = progRes.data.filter((p) => departments.includes(p.department));
        const ownIds = new Set(own.map((p) => p.id));
        setStudents(stuRes.data);
        setSections(secRes.data.filter((s) => ownIds.has(s.program)));
        setPrograms(own);
        setUpProgram((cur) => cur || (own[0] ? String(own[0].id) : ""));
        setLoadError("");
      })
      .catch((err) => setLoadError(err.response?.data?.detail || "Could not load the class lists. Please try again."))
      .finally(() => setLoading(false));
  };

  // load only when the department changes (load is re-created every render; listing it would reload in a loop)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => { load(); }, [department]);

  const sectionLabel = (s) => `${s.program_name || ""} ${s.year_level} - ${s.name}`.trim();
  const ownSectionIds = new Set(sections.map((s) => s.id));
  const semesters = [...new Set(sections.filter((s) => String(s.program) === String(upProgram)).map((s) => s.semester))].sort();

  const send = async (commit) => {
    if (!upFile) { setUpError("Choose a file first."); return; }
    setUpBusy(true); setUpError(""); setUpDone("");
    try {
      const fd = new FormData();
      fd.append("file", upFile); fd.append("program_id", upProgram); fd.append("commit", commit ? "true" : "false");
      if (upSemester) fd.append("semester", upSemester);
      const res = await API.post("/engine/students/import/", fd, { headers: { "Content-Type": "multipart/form-data" } });
      if (commit) {
        setUpResult(null); setUpFile(null);
        setUpDone(`Added ${res.data.added} student${res.data.added === 1 ? "" : "s"} to ${res.data.program} (${res.data.semester}).` +
                  (res.data.duplicates ? ` ${res.data.duplicates} already on the list were skipped.` : ""));
        load();
      } else {
        setUpResult(res.data);
      }
    } catch (err) {
      setUpResult(null);
      setUpError(err.response?.data?.detail || "Could not read the file.");
    } finally { setUpBusy(false); }
  };

  const template = () => {
    const sec = sections.find((s) => String(s.program) === String(upProgram) && (!upSemester || s.semester === upSemester)) || sections[0];
    const csv = `Full Name,Section,Year Level\nJuan Dela Cruz,${sec ? sec.name : "A1"},${sec ? sec.year_level : "1st Year"}\n`;
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = "class_list_template.csv"; a.click(); URL.revokeObjectURL(url);
  };

  const remove = async (id) => {
    if (!(await confirmDialog({ title: "Remove student?", message: "Remove this student from the class list?", confirmLabel: "Remove student" }))) return;
    try {
      await API.delete(`/engine/students/${id}/`);
    } catch (err) {
      setLoadError(err.response?.data?.detail || "Could not remove the student.");
      return;
    }
    load();
  };

  const searchLower = search.trim().toLowerCase();
  const filtered = students
    .filter((s) => ownSectionIds.has(s.section))
    .filter((s) => (!sectionFilter || String(s.section) === String(sectionFilter)))
    .filter((s) => (!searchLower || (s.full_name || "").toLowerCase().includes(searchLower)));

  const inputStyle = { padding: "9px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "14px", background: "white" };

  if (loading) return <p>Loading class lists…</p>;

  return (
    <div>
      {loadError && <p style={{ color: "#b91c1c", fontSize: "13px" }}>{loadError} <button onClick={load}>Retry</button></p>}
      <div style={{
        background: "white", borderRadius: 6, padding: "18px 20px", marginBottom: "20px",
        border: "1px solid #e5e7eb", boxShadow: "none",
      }}>
        <h4 style={{ marginTop: 0, marginBottom: "4px", color: "#003366" }}>Upload a class list</h4>
        <p style={{ fontSize: "13px", color: "#6b7280", marginTop: 0, marginBottom: "14px" }}>
          Upload a CSV or Excel file with three columns: <b>Full Name</b>, <b>Section</b>, <b>Year Level</b>. Every student in a block section
          takes that section's whole subject load, so teachers of that section see them on their class list.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center" }}>
          <CustomSelect value={upProgram} onChange={(e) => { setUpProgram(e.target.value); setUpSemester(""); setUpResult(null); }} style={inputStyle} aria-label="Program">
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </CustomSelect>
          <CustomSelect value={upSemester} onChange={(e) => { setUpSemester(e.target.value); setUpResult(null); }} style={inputStyle} aria-label="Semester">
            <option value="">Current semester</option>
            {semesters.map((x) => <option key={x} value={x}>{x}</option>)}
          </CustomSelect>
          <label style={{ ...inputStyle, cursor: "pointer", color: upFile ? "#111827" : "#6b7280" }}>
            {upFile ? upFile.name : "Choose file (.csv, .xlsx)"}
            <input type="file" accept=".csv,.xlsx,.xlsm,text/csv" style={{ display: "none" }}
                   onChange={(e) => { setUpFile(e.target.files[0] || null); setUpResult(null); setUpDone(""); setUpError(""); e.target.value = ""; }} />
          </label>
          <button onClick={() => send(false)} disabled={upBusy || !upFile || !upProgram}>{upBusy && !upResult ? "Checking…" : "Check file"}</button>
          <button onClick={template} style={{ background: "white", color: "#003366", border: "1px solid #d1d5db" }}>Download template</button>
        </div>
        {upError && <p style={{ color: "#b91c1c", fontSize: "13px", marginTop: "10px", marginBottom: 0 }}>{upError}</p>}
        {upDone && <p style={{ color: "#166534", fontSize: "13px", marginTop: "10px", marginBottom: 0 }}>{upDone}</p>}
        {upResult && (
          <div style={{ marginTop: "12px", border: "1px solid #e5e7eb", borderRadius: 6, padding: "10px 12px", background: "#f9fafb" }}>
            <div style={{ fontSize: "13px" }}>
              <b>{upResult.to_add}</b> student{upResult.to_add === 1 ? "" : "s"} ready to add to {upResult.program} ({upResult.semester})
              {upResult.duplicates ? <> · {upResult.duplicates} already listed (skipped)</> : null}
              {upResult.error_count ? <span style={{ color: "#b91c1c" }}> · {upResult.error_count} row{upResult.error_count === 1 ? " needs" : "s need"} fixing</span> : null}
            </div>
            {upResult.by_section.length > 0 && (
              <div style={{ fontSize: "13px", color: "#4b5563", marginTop: "4px" }}>
                {upResult.by_section.map((b) => `${b.section}: ${b.count}`).join("  ·  ")}
              </div>
            )}
            {upResult.errors.length > 0 && (
              <ul style={{ margin: "8px 0 0", paddingLeft: "18px", fontSize: "13px", color: "#b91c1c", maxHeight: "130px", overflowY: "auto" }}>
                {upResult.errors.map((er, i) => <li key={i}>Row {er.row}{er.name ? ` (${er.name})` : ""}: {er.message}</li>)}
              </ul>
            )}
            <div style={{ marginTop: "10px", display: "flex", gap: "8px", alignItems: "center" }}>
              <button onClick={() => send(true)} disabled={upBusy || upResult.to_add === 0}>
                {upBusy ? "Importing…" : `Import ${upResult.to_add} student${upResult.to_add === 1 ? "" : "s"}`}
              </button>
              {upResult.error_count > 0 && upResult.to_add > 0 && <span style={{ fontSize: "12px", color: "#6b7280" }}>Rows with problems are left out.</span>}
            </div>
          </div>
        )}
      </div>

      <div style={{
        display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center",
        background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px 14px", marginBottom: "16px",
      }}>
        <input
          placeholder="Search name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...inputStyle, flex: "1 1 220px", minWidth: "200px" }}
        />
        <CustomSelect value={sectionFilter} onChange={(e) => setSectionFilter(e.target.value)} style={inputStyle}>
          <option value="">All sections</option>
          {sections.map((s) => <option key={s.id} value={s.id}>{sectionLabel(s)} · {s.semester}</option>)}
        </CustomSelect>
        <span style={{ fontSize: "13px", color: "#6b7280" }}>{filtered.length} students</span>
      </div>

      <table>
        <thead>
          <tr><th>Full name</th><th>Section</th><th>Year level</th><th>Program</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {filtered.map((s) => (
            <tr key={s.id}>
              <td>{s.full_name}</td>
              <td>{s.section_name}</td>
              <td>{s.year_level}</td>
              <td>{s.program_name}</td>
              <td><button onClick={() => remove(s.id)}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CurriculumManager({ programId }) {
  const [subjects, setSubjects] = useState([]);

  React.useEffect(() => {
    API.get("/curriculum/subjects/").then((res) => setSubjects(res.data)).catch(reportLoadError("the curriculum subjects"));
  }, []);

  const filtered = programId ? subjects.filter((s) => String(s.program) === String(programId)) : subjects;

  return (
    <table>
      <thead>
        <tr><th>Code</th><th>Title</th><th>Lec</th><th>Lab</th><th>Type</th><th>Actions</th></tr>
      </thead>
      <tbody>
        {filtered.map((s) => (
          <tr key={s.id}>
            <td>{s.code}</td><td>{s.title}</td><td>{s.lec_units}</td><td>{s.lab_units}</td>
            <td>{kindLabel(s.classification, s.program_name)}</td>
            <td><button onClick={() => API.delete(`/curriculum/subjects/${s.id}/`)}>Remove</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* New read-only insight cards for the Dean (own college only; the server enforces it). Mounted under the existing analytics. */
function DeanInsights() {
  const [filters, setFilters] = useState({});
  const [resolver, setResolver] = useState(null);
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <h3 style={{ margin: 0, color: "#003366" }}>Insights — your college</h3>
        <InsightFilters value={filters} onChange={setFilters} />
      </div>
      <ReadinessCard filters={filters} />
      <FacultyFitCard filters={filters} />
      <LabCapacityCard filters={filters} />
      <LoadBandsCard filters={filters} onOpenResolver={(id) => setResolver(id)} />
      {resolver !== null && <ResolverWindow focusId={resolver || null} onClose={() => { setResolver(null); notifyWorkloadChanged(); }} />}
    </div>
  );
}

function AnalyticsPanel() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [sem, setSem] = useState("");

  React.useEffect(() => onWorkloadChanged(() => setAttempt((n) => n + 1)), []);
  React.useEffect(() => {
    setLoadError("");
    API.get("/analytics/", { params: sem ? { semester: sem } : {} })
      .then((res) => setData(res.data))
      .catch((err) => setLoadError(err.code === "ECONNABORTED"
        ? "Analytics took too long to load (slow connection or database)."
        : (err.response?.data?.detail || "Could not load analytics.")));
  }, [attempt, sem]);

  if (loadError) return <p style={{ color: "red" }}>{loadError} <button onClick={() => setAttempt((n) => n + 1)}>Try again</button></p>;
  if (!data) return <p>Loading analytics…</p>;

  const workload = Object.entries(data.teacher_workload).map(([t, c]) => ({ label: t, value: c })).sort((a, b) => b.value - a.value);
  const rooms = Object.entries(data.room_utilization).map(([r, c]) => ({ label: r, value: c })).sort((a, b) => b.value - a.value);

  return (
    <div>
      <h3 style={{ color: "#003366" }}>Analytics — Your College</h3>
      {data.semesters && data.semesters.length > 1 && (
        <p style={{ fontSize: "13px", color: "#374151" }}>
          Semester:{" "}
          <CustomSelect value={data.semester || ""} onChange={(e) => setSem(e.target.value)}>
            {data.semesters.map((s) => <option key={s} value={s}>{s}</option>)}
          </CustomSelect>{" "}
          (1st and 2nd Sem use the same rooms and teachers, so each is shown on its own.)
        </p>
      )}
      <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginBottom: "24px" }}>
        <StatTile label="Schedule Efficiency" value={`${data.schedule_efficiency}%`} />
        <StatTile label="Workload Std. Deviation" value={`${data.workload_std_dev} hrs`} accent="#b8860b" />
        <StatTile label="Teachers With Load" value={workload.length} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Teacher Workload</h4>
          <HBarChart data={workload} unit=" hrs" emptyText="No schedule entries yet." />
        </div>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Room Utilization</h4>
          <HBarChart data={rooms} color="#b8860b" unit=" hrs" emptyText="No schedule entries yet." />
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px", marginTop: "20px" }}>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Class Hours by Day</h4>
          <HBarChart data={Object.entries(data.class_hours_by_day || {}).map(([d, n]) => ({ label: d, value: n }))} unit=" hrs" emptyText="No schedule entries yet." />
        </div>
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px" }}>
          <h4 style={{ marginTop: 0, color: "#003366" }}>Schedule Status</h4>
          <HBarChart data={Object.entries(data.schedule_status || {}).map(([k, n]) => ({ label: k.charAt(0).toUpperCase() + k.slice(1), value: n }))} color="#b8860b" unit=" hrs" emptyText="No schedule entries yet." />
        </div>
      </div>
      <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 6, padding: "18px 20px", marginTop: "20px" }}>
        <h4 style={{ marginTop: 0, color: "#003366" }}>Recent Activity</h4>
        <RecentActivity items={data.recent_activity} />
      </div>
    </div>
  );
}

const FACULTY_TYPE_LABEL = { dean: "Dean", full_time: "Full-time", part_time: "Part-time" };

/* ---------------- Dean's "Faculty" tab: one row per faculty member, not per
   availability slot. Was previously rendering the raw FacultyProfile id
   number in place of a name, and raw "HH:MM:SS" timestamps with no
   day/time grouping -- /faculty/profiles/roster/ now does that grouping
   server-side (see faculty/views.py FacultyProfileViewSet.roster). ---------------- */
function CollegeFacultyRoster({ department, departments = [department] }) {
  const [rows, setRows] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [replaceFor, setReplaceFor] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  // Which teacher's row is expanded to show full availability + specialization
  // -- so the Dean can decide what major/minor subject to assign them,
  // instead of just seeing a comma list of days with no times or expertise.
  const [expandedId, setExpandedId] = useState(null);

  React.useEffect(() => {
    setLoading(true);
    setLoadError("");
    API.get("/faculty/profiles/roster/").then((res) => setRows(res.data))
      .catch((e) => setLoadError(e.response?.data?.detail || "Could not load the faculty list. If you just updated the system, run 'python manage.py migrate' and restart the backend."))
      .finally(() => setLoading(false));
  }, [department, reloadKey]);
  React.useEffect(() => onWorkloadChanged(() => setReloadKey((k) => k + 1)), []);

  const exportCsv = () => {
    const header = "School ID,Faculty Member,Type,Load (units),Weekly hours,Availability\n";
    const body = rows.map((r) =>
      [r.school_id, r.full_name, FACULTY_TYPE_LABEL[r.faculty_type] || r.faculty_type || "", r.load_units, r.workload ? `${r.workload.current_hours}/${r.workload.max_hours}` : "", r.availability_days.join("; ")]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")
    ).join("\n");
    const blob = new Blob([header + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `faculty-list-${department || "college"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Only block the view on the very first load; a reload after adding a faculty member must not
  // unmount the "Add Faculty" dialog (it is still showing the new School ID).
  if (loading && rows.length === 0) return <p>Loading faculty…</p>;
  if (loadError) return <p style={{ color: "#b91c1c" }}>{loadError}</p>;

  return (
    <div>
    <WorkloadPanel canSuggest refreshKey={reloadKey} />
    <div style={{
      background: "white", borderRadius: 6, padding: "20px 24px",
      border: "1px solid #e5e7eb", boxShadow: "none",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
        <div>
          <h3 style={{ margin: 0, color: "#003366" }}>College Faculty</h3>
          <p style={{ margin: "2px 0 0", fontSize: "13px", color: "#6b7280" }}>
            {rows.length} faculty member{rows.length === 1 ? "" : "s"}
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        <button
          onClick={() => setShowAdd(true)}
          style={{
            background: "#003366", color: "white", border: "none", padding: "8px 16px",
            borderRadius: "6px", fontSize: "13px", fontWeight: 600, cursor: "pointer",
          }}
        >
          Add Faculty
        </button>
        <button
          onClick={exportCsv}
          disabled={rows.length === 0}
          style={{
            background: "#003366", color: "white", border: "none", padding: "8px 16px",
            borderRadius: "6px", fontSize: "13px", fontWeight: 600, cursor: rows.length ? "pointer" : "default",
          }}
        >
          Export faculty list
        </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <p style={{ color: "#6b7280", fontSize: "14px" }}>No faculty found for this department yet.</p>
      ) : (
        <table>
          <thead>
            <tr><th>School ID</th><th>Faculty Member</th><th>Type</th><th>Load</th><th>Weekly hours</th><th>Availability</th><th></th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const expanded = expandedId === r.id;
              return (
                <React.Fragment key={r.id}>
                  <tr
                    onClick={() => setExpandedId(expanded ? null : r.id)}
                    style={{ cursor: "pointer" }}
                    title="Click to see this teacher's full availability and specialization"
                  >
                    <td>{r.school_id}</td>
                    <td>{r.full_name}</td>
                    <td>{FACULTY_TYPE_LABEL[r.faculty_type] || r.faculty_type || "—"}</td>
                    <td>{r.load_units} unit{r.load_units === 1 ? "" : "s"}</td>
                    <td style={r.workload?.overload_hours > 0 ? { color: "#b91c1c", fontWeight: 600 } : undefined}
                        title={r.workload?.warning || ""}>
                      {r.workload ? `${r.workload.current_hours} / ${r.workload.max_hours} h` : "—"}
                      {r.workload?.overload_hours > 0 ? " (overloaded)" : ""}
                    </td>
                    <td>{r.availability_days.length ? r.availability_days.join(", ") : "Not submitted yet"}</td>
                    <td>
                      <button onClick={(e) => { e.stopPropagation(); setReplaceFor(r); }}
                              title="Find qualified replacements for this teacher's classes"
                              style={{ fontSize: "12px", padding: "5px 10px" }}>
                        Find replacement
                      </button>
                    </td>
                    <td style={{ color: "#003366", fontSize: "12px", fontWeight: 600 }}>
                      {expanded ? "Hide ▲" : "Details ▼"}
                    </td>
                  </tr>
                  {expanded && (
                    <tr>
                      <td colSpan={8} style={{ background: "#f7f9fc", padding: 0 }}>
                        <FacultyDetailPanel row={r} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
    {replaceFor && (
      <ReplacementModal faculty={{ id: replaceFor.id }} onClose={() => setReplaceFor(null)} onChanged={() => setReloadKey((k) => k + 1)} />
    )}
    {showAdd && (
      <AddFacultyModal departments={departments} onClose={() => setShowAdd(false)} onCreated={() => setReloadKey((k) => k + 1)} />
    )}
    </div>
  );
}

/* Expanded detail under a clicked roster row -- every availability block
   (day/time/preference, not just a list of days) plus specialization, so
   a Dean deciding which major/minor subject to hand a teacher doesn't have
   to go ask them or dig through the Availability review tab separately. */
function FacultyDetailPanel({ row }) {
  const slots = row.availability_slots || [];
  const specializations = row.specializations || [];

  return (
    <div style={{ padding: "16px 20px 20px" }}>
      <div style={{ marginBottom: "14px" }}>
        <p style={{ margin: "0 0 6px", fontSize: "13px", fontWeight: 600, color: "#111827" }}>
          Specialization
        </p>
        {specializations.length === 0 ? (
          <p style={{ margin: 0, fontSize: "13px", color: "#6b7280" }}>No specialization on file.</p>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {specializations.map((s) => (
              <span key={s} style={{
                background: "#e8eef7", color: "#003366", fontSize: "12px", fontWeight: 600,
                padding: "4px 10px", borderRadius: 4,
              }}>
                {s}
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <p style={{ margin: "0 0 6px", fontSize: "13px", fontWeight: 600, color: "#111827" }}>
          Submitted Availability
        </p>
        {slots.length === 0 ? (
          <p style={{ margin: 0, fontSize: "13px", color: "#6b7280" }}>Not submitted yet.</p>
        ) : (
          <table style={{ background: "white", maxWidth: "480px" }}>
            <thead><tr><th>Day</th><th>Time</th><th>Preference</th></tr></thead>
            <tbody>
              {slots.map((s) => {
                const badge = PREFERENCE_BADGE[s.preference] || PREFERENCE_BADGE.preferred;
                return (
                  <tr key={s.id}>
                    <td>{s.day}</td>
                    <td>{s.start_time}–{s.end_time}</td>
                    <td><Badge tone={badge.tone}>{badge.label}</Badge></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ---------------- Full-time / Part-time shared: read-only schedule ---------------- */
function ScheduleView() {
  const [classes, setClasses] = useState([]);
  // Students in the sections this teacher actually has a class in --
  // the backend already scopes /engine/students/ to that for a
  // full_time/part_time faculty account, so no extra filtering needed here.
  const [students, setStudents] = useState([]);
  const [rosterSection, setRosterSection] = useState(null);

  React.useEffect(() => {
    API.get("/engine/schedules/").then((res) => setClasses(res.data)).catch(reportLoadError("the classes"));
    API.get("/engine/students/").then((res) => setStudents(res.data)).catch(reportLoadError("the students"));
  }, []);

  const grouped = sortByDayTime(mergeSchedulesByDay(classes));
  const lecLabIndex = buildLecLabIndex(grouped);
  const rosterFor = (sectionId) => students.filter((s) => s.section === sectionId);

  return (
    <div>
      <table>
        <thead><tr><th>Subject</th><th>Section</th><th>Room</th><th>Time</th><th>Students</th></tr></thead>
        <tbody>
          {grouped.map((g) => {
            const roster = rosterFor(g.section);
            return (
              <tr key={g.key}>
                <td>{g.subject_code} — {g.subject_title}<LecLabTag row={g} index={lecLabIndex} /></td>
                <td>{g.section_name}</td>
                <td>{g.room_name}</td>
                <td>{formatSchedule(g.timeslot_day, g.start, g.end)}</td>
                <td>
                  <button
                    onClick={() => setRosterSection(rosterSection === g.section ? null : g.section)}
                    title="See the students in this section"
                  >
                    {roster.length} student{roster.length !== 1 ? "s" : ""}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {rosterSection !== null && (
        <div style={{
          marginTop: "16px", background: "white", borderRadius: 6, padding: "16px 20px",
          border: "1px solid #e5e7eb", boxShadow: "none", maxWidth: "480px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
            <h4 style={{ margin: 0, color: "#003366" }}>
              {grouped.find((g) => g.section === rosterSection)?.section_name || "Class list"}
            </h4>
            <button onClick={() => setRosterSection(null)} style={{ background: "none", color: "#111827", border: "none", cursor: "pointer", fontSize: "16px" }}>×</button>
          </div>
          {rosterFor(rosterSection).length === 0 ? (
            <p style={{ color: "#6b7280", fontSize: "13px" }}>No students recorded for this section yet -- ask the Registrar/Dean to add the class list.</p>
          ) : (
            <table>
              <thead><tr><th>Name</th></tr></thead>
              <tbody>
                {rosterFor(rosterSection).map((s) => (
                  <tr key={s.id}><td>{s.full_name}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- Full-time & part-time: submit availability for Dean/Registrar review ---------------- */
const DAY_OPTIONS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const PREFERENCE_OPTIONS = [
  { value: "preferred", label: "Preferred" },
  { value: "available", label: "Available" },
  { value: "unavailable", label: "Unavailable" },
];

function AvailabilityForm({ onSaved }) {
  const [day, setDay] = useState("Monday");
  const [preference, setPreference] = useState("preferred");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setError("");
    if (!day || !start || !end) return;
    if (end <= start) { setError("\"Available until\" must be after \"Available from\"."); return; }
    setSaving(true);
    try {
      await API.post("/faculty/availability/", { day, preference, start_time: start, end_time: end });
      setStart(""); setEnd("");
      onSaved?.();
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save this availability block.");
    } finally {
      setSaving(false);
    }
  };

  const fieldLabelStyle = { display: "block", fontSize: "12px", fontWeight: 600, color: "#003366", marginBottom: "6px" };
  const inputStyle = { width: "100%", padding: "10px 12px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: "14px", boxSizing: "border-box", background: "white" };

  return (
    <div style={{ marginTop: "8px", marginBottom: "24px" }}>
      <div style={{
        background: "white", borderRadius: 6, padding: "22px 24px", maxWidth: "640px",
        border: "1px solid #e5e7eb", boxShadow: "none",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <h3 style={{ margin: 0, color: "#111827", fontSize: "16px" }}>Add an availability block</h3>
            <p style={{ margin: "2px 0 0", fontSize: "13px", color: "#6b7280" }}>
              Submitted to the Registrar/Dean for review -- not final until scheduled.
            </p>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "16px" }}>
          <div>
            <label style={fieldLabelStyle}>Day</label>
            <CustomSelect style={inputStyle} value={day} onChange={(e) => setDay(e.target.value)}>
              {DAY_OPTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
            </CustomSelect>
          </div>
          <div>
            <label style={fieldLabelStyle}>Preference</label>
            <CustomSelect style={inputStyle} value={preference} onChange={(e) => setPreference(e.target.value)}>
              {PREFERENCE_OPTIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </CustomSelect>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "18px" }}>
          <div>
            <label style={fieldLabelStyle}>Available from</label>
            <CustomTimePicker style={inputStyle} value={start} onChange={(e) => setStart(e.target.value)} aria-label="Available from" />
          </div>
          <div>
            <label style={fieldLabelStyle}>Available until</label>
            <CustomTimePicker style={inputStyle} value={end} onChange={(e) => setEnd(e.target.value)} aria-label="Available until" />
          </div>
        </div>

        {error && <p style={{ color: "#b91c1c", fontSize: "13px", marginTop: 0, marginBottom: "14px" }}>{error}</p>}

        <button
          onClick={submit}
          disabled={saving || !day || !start || !end}
          style={{
            background: "#003366", color: "white", border: "none", padding: "12px 20px",
            borderRadius: 6, fontSize: "14px", fontWeight: 600, cursor: saving ? "default" : "pointer",
            width: "100%",
          }}
        >
          {saving ? "Saving…" : "Add availability"}
        </button>
      </div>
    </div>
  );
}

export default FacultyDashboard;
