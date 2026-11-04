import React, { useState, useEffect } from "react";
import { reportLoadError } from "../services/loadError";
import API from "../services/api";
import { WorkloadWarningList } from "./WorkloadPanel";
import { ConflictList } from "./ConflictChecker";
import ScheduleProblemsModal from "./ScheduleProblemsModal";
import NotGeneratedList from "./NotGeneratedList";
import FacultyTimePopover from "./FacultyTimePopover";
import { rankProfessors } from "../utils/suggestProfessors";
import ErrorBoundary from "./ErrorBoundary";
import TeacherPicker from "./TeacherPicker";
import SharedClassModal, { sharedLabel } from "./SharedClassModal";
import RoomSelect from "./RoomSelect";
import { ResolverWindow, notifyWorkloadChanged } from "./OverloadResolver";
import { toMin, timeWindowProblem, startOptions, endOptions, pickStart, pickEnd, needHint, needMinutes, professorFits, freeText as profFreeText,
  DAY_START, DAY_END } from "../utils/timeWindow";

/* Generate Schedule -- shared by the Registrar (minor / Gen Ed subjects) and the Dean (major subjects). */
const STANDARD_YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"];
const STANDARD_SEMESTERS = ["1st Sem", "2nd Sem"];

const uniqueClasses = (list) => Object.values(Object.fromEntries((list || []).map((c) => [`${c.section_id}-${c.subject_id}`, c])));
const popBtn = { background: "#003366", color: "white", border: "1px solid #003366", borderRadius: 6, padding: "5px 12px", cursor: "pointer", fontSize: 12.5, whiteSpace: "nowrap" };
// Start / End times: every 30 minutes from 7:00 AM to 8:00 PM (the college time-slot grid), limited per row so the range always
// holds the subject's longest class period (utils/timeWindow.js startOptions / endOptions; the server checks the same rule)
const timeLabel = (t) => { const [h, m] = String(t).split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m || 0).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
// the longest unbroken class period a subject needs comes from the server (Subject.need_minutes): see utils/timeWindow.js

function GenerateSchedulePanel({ role, departments, initialProgramId = "", onGenerated, hideTitle = false, onProgramName }) {
  const isRegistrar = role === "registrar";
  const kindWord = isRegistrar ? "minor" : "major";
  const progName = () => (programs.find((p) => String(p.id) === String(programId)) || {}).name || "Program";
  const [programs, setPrograms] = useState([]);
  const [programId, setProgramId] = useState(initialProgramId ? String(initialProgramId) : "");
  // a parent that draws its own title (hideTitle) is told which program is chosen in the dropdown, so the title always matches it
  useEffect(() => {
    if (onProgramName) onProgramName((programs.find((p) => String(p.id) === String(programId)) || {}).name || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programId, programs]);
  const [combos, setCombos] = useState([]);       // real [year_level, semester] pairs that exist for the program
  const [yearLevel, setYearLevel] = useState("");
  const [semester, setSemester] = useState("");
  const [result, setResult] = useState(null);
  /* Fixed clashes leave the list (the pop-up reports each one it fixed). Nothing is changed automatically. */
  const dropClash = (idxs) => setResult((r) => {
    const keep = r.clashes.conflicts.filter((_c, i) => !idxs.includes(i));
    return { ...r, clashes: { ...r.clashes, conflicts: keep, total: Math.max(0, (r.clashes.total || 0) - idxs.length) } };
  });

  const [popup, setPopup] = useState(null);     // visible pop-up after Generate: {title, tone, items:[{text, action, label}]}
  const [sharedInfo, setSharedInfo] = useState(null);   // shared-class choices of the minor subjects of the chosen program / year / semester
  const [sharedItem, setSharedItem] = useState(null);
  const loadShared = React.useCallback(async () => {
    if (!programId || !yearLevel || !semester) { setSharedInfo(null); return; }
    try { setSharedInfo((await API.get("/engine/shared-classes/options/", { params: { program_id: programId, year_level: yearLevel, semester } })).data); }
    catch (_e) { setSharedInfo(null); }
  }, [programId, yearLevel, semester]);
  useEffect(() => { loadShared(); }, [loadShared]);
  const sharedFor = (id) => (sharedInfo?.subjects || []).find((x) => x.subject_id === id);
  const [problems, setProblems] = useState(false);   // the Schedule problems window: opened ONLY by "Review conflicts" (real clashes)
  const [skipped, setSkipped] = useState(null);       // after Generate: the classes that could not be placed, with the reason (OK only)
  const [listKey, setListKey] = useState(0);
  const [timeFor, setTimeFor] = useState(null);       // the "Faculty time" pop-over: { code, teachers, initialId }          // refreshes the "not generated yet" list after a run
  const [resolver, setResolver] = useState(null); // faculty id (or 0 = all) for the View Suggestions window
  const [running, setRunning] = useState(false);
  const [loadingCombos, setLoadingCombos] = useState(false);
  const [mergeMinors, setMergeMinors] = useState(true);
  const [keepEdited, setKeepEdited] = useState(true);    // classes changed by hand are locked: Generate leaves them where they are
  const [allSubjects, setAllSubjects] = useState(null);   // curriculum, loaded once, filtered below
  /* Curriculum preview choices: Room / Start Time / End Time per subject. Only what the user changed is sent; a blank value
     means "let the engine decide" (the Dean's saved room preference still applies). */
  const [roomList, setRoomList] = useState([]);
  const [savedRooms, setSavedRooms] = useState({});
  const [picks, setPicks] = useState({});                 // subjectId -> { room, start, end }
  const setPick = (sid, key, value) => setPicks((p) => ({ ...p, [sid]: { ...(p[sid] || {}), [key]: value } }));
  const [timeNotice, setTimeNotice] = useState({});      // subjectId -> short note after End was reset / set automatically
  useEffect(() => { setPicks({}); setTimeNotice({}); }, [programId, yearLevel, semester]);
  /* Start and End follow each other: never an invalid range in the row (see utils/timeWindow.js pickStart / pickEnd). */
  const setTimes = (s, which, value) => {
    const cur = picks[s.id] || {};
    const r = which === "start" ? pickStart(s, value, cur.end) : pickEnd(s, cur.start, value);
    setPicks((pk) => ({ ...pk, [s.id]: { ...(pk[s.id] || {}), start: r.start, end: r.end } }));
    setTimeNotice((n) => ({ ...n, [s.id]: r.notice }));
  };
  /* Dean only: the qualified professors of the college per subject, with their current weekly load (read-only list from the server). */
  const [profOpts, setProfOpts] = useState(null);
  useEffect(() => {
    setProfOpts(null);
    if (isRegistrar || !programId || !yearLevel || !semester) return;
    API.get("/engine/generate/professor-options/", { params: { program_id: programId, year_level: yearLevel, semester } })
      .then((res) => setProfOpts(res.data)).catch(() => setProfOpts({ subjects: [], teachers: {}, error: true }));
  }, [isRegistrar, programId, yearLevel, semester]);
  const profRow = (sid) => (profOpts?.subjects || []).find((x) => x.subject_id === sid);
  /* A Lecture and its Lab have one teacher: choosing for one sets the other too. */
  const setProfessor = (sid, value) => {
    const partner = profRow(sid)?.partner_id;
    setPicks((p) => {
      const next = { ...p, [sid]: { ...(p[sid] || {}), teacher: value } };
      if (partner) next[partner] = { ...(p[partner] || {}), teacher: value };
      return next;
    });
  };
  /* Hours a professor would have with every row chosen for them (each row covers all of its sections). */
  const chosenHours = (tid) => (profOpts?.subjects || []).reduce((n, x) => n + (String(picks[x.subject_id]?.teacher || "") === String(tid) ? x.total_hours : 0), 0);
  const hrs = (n) => `${Math.round(n * 100) / 100}`;
  /* Rooms (read-only): with a semester they carry their free hours, and with a year level the rooms Generate accepts per subject. */
  const [roomAllowed, setRoomAllowed] = useState(null);
  useEffect(() => {
    API.get("/rooms/preview-choices/", { params: { program_id: programId || undefined, year_level: yearLevel || undefined, semester: semester || undefined } })
      .then((res) => { setRoomList(res.data.rooms || []); setSavedRooms(res.data.saved || {}); setRoomAllowed(res.data.allowed || null); })
      .catch(() => { setRoomList([]); setSavedRooms({}); setRoomAllowed(null); });
  }, [programId, yearLevel, semester]);
  const freeText = (r) => (r.free_hours != null ? ` – ${hrs(r.free_hours)} of ${hrs(r.total_hours)} hrs free` : "");
  const [programSections, setProgramSections] = useState([]);

  useEffect(() => {
    API.get("/curriculum/subjects/").then((res) => setAllSubjects(res.data)).catch(() => setAllSubjects([]));
  }, []);

  useEffect(() => {
    API.get("/curriculum/programs/").then((res) => setPrograms(
      isRegistrar ? res.data : res.data.filter((p) => (departments || []).includes(p.department)))).catch(reportLoadError("the programs"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // "1st Year" < "2nd Year" < ... < "5th Year" (some programs run 5 years),
  // sorted by the leading number, not alphabetically.
  const rank = (label) => parseInt(String(label).match(/\d+/)?.[0] || "99", 10);
  // Always offer 1st-5th Year and both semesters (a program may run 5 years);
  // anything else found in the data is added too.
  const yearOptions = [...new Set([...STANDARD_YEARS, ...combos.map((c) => c[0]).filter((y) => /^\d+(st|nd|rd|th) Year$/i.test(String(y || "").trim()))])].sort((a, b) => rank(a) - rank(b));
  const semesterOptions = [...new Set([...STANDARD_SEMESTERS, ...combos.map((c) => c[1]).filter((x) => /sem/i.test(x || ""))])]
    .sort((a, b) => rank(a) - rank(b));

  // Whenever the program changes, pull real Section rows for it and derive the
  // year levels / semesters that actually exist (so a 5-year program shows a
  // 5th Year option and a 4-year program doesn't).
  useEffect(() => {
    setResult(null);
    if (!programId) { setCombos([]); setYearLevel(""); setSemester(""); return; }
    setLoadingCombos(true);
    API.get("/engine/sections/")
      .then((res) => {
        const forProgram = res.data.filter((s) => String(s.program) === String(programId));
        setProgramSections(forProgram);
        const seen = new Set();
        const pairs = [];
        forProgram.forEach((s) => {
          const k = `${s.year_level}|${s.semester}`;
          if (!seen.has(k)) { seen.add(k); pairs.push([s.year_level, s.semester]); }
        });
        setCombos(pairs);
        const years = [...new Set(pairs.map((c) => c[0]))].sort((a, b) => rank(a) - rank(b));
        setYearLevel(years[0] || STANDARD_YEARS[0]);
      })
      .catch(reportLoadError("the sections"))
      .finally(() => setLoadingCombos(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [programId]);

  // Keep the semester valid for whichever year level is selected.
  useEffect(() => {
    if (!semesterOptions.includes(semester)) setSemester(semesterOptions[0] || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yearLevel, combos]);

  const scopeSubjects = (allSubjects || []).filter((s) => String(s.program) === String(programId) && s.year_level === yearLevel
    && s.semester === semester && s.classification === kindWord);
  const badRows = scopeSubjects.filter((s) => timeWindowProblem(s, picks[s.id]?.start, picks[s.id]?.end)).map((s) => s.code).sort();

  const run = async (onlyMissing = false) => {
    if (!programId || !yearLevel || !semester || badRows.length) return;
    setRunning(true);
    setResult(null);
    try {
      const room_choices = {}, time_windows = {}, teacher_choices = {};
      Object.entries(picks).forEach(([sid, p]) => {
        if (p.room) room_choices[sid] = Number(p.room);
        if (p.start || p.end) time_windows[sid] = { start: p.start || "", end: p.end || "" };
        if (p.teacher) teacher_choices[sid] = Number(p.teacher);
      });
      const res = await API.post("/engine/generate-schedule/", {
        program_id: programId, year_level: yearLevel, semester, merge_minors: mergeMinors, room_choices, time_windows, keep_edited: keepEdited, only_missing: onlyMissing === true, ...(isRegistrar ? {} : { teacher_choices }),
      }, { timeout: 180000 });   // generation can take a while over a remote database
      setResult(res.data);
      const d = res.data, items = [];
      // Classes that could not be placed were SKIPPED (nothing was forced): one plain pop-up with the reasons, OK only.
      // Nothing opens by itself to fix them; real clashes are shown in red under the result.
      const skippedList = uniqueClasses(d.conflicts);
      if (skippedList.length) setSkipped(skippedList);
      else if ((d.workload_warnings || []).length) {
        items.push({ text: `${d.workload_warnings.length} teacher(s) are overloaded by this schedule.`, action: "overload", label: "View Suggestions" });
        setPopup({ title: "Schedule generated — action needed", tone: "warn", items });
      }
      setListKey((k) => k + 1);
      onGenerated?.(res.data);
    } catch (err) {
      let message = err.response?.data?.detail || "Schedule generation failed.";
      if (err.code === "ECONNABORTED") {
        message = "Request timed out after 3 minutes -- the backend or database connection may be "
          + "down (e.g. laptop went to sleep, or the Supabase project paused). Check that "
          + "'python manage.py runserver' is still running and Supabase isn't paused, then try again.";
      } else if (!err.response) {
        message = "Could not reach the backend at all -- confirm 'python manage.py runserver' "
          + "is running and reachable at http://127.0.0.1:8000.";
      }
      setResult({ error: message });
      setPopup({ title: "Schedule generation failed", tone: "bad", items: [{ text: message }] });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      {!hideTitle && <h3>{isRegistrar ? "Generate Schedule — Gen Ed Subjects" : `Generate Schedule — ${progName()} Subjects`}</h3>}
      <p style={{ fontSize: "13px", color: "#475569", maxWidth: "760px", marginTop: 0 }}>
        {isRegistrar
          ? "You generate the Gen Ed subjects. The Dean of each college then generates the program subjects and they are placed around yours in the same weekly schedule. You can edit and approve Gen Ed subjects only."
          : `You generate the ${progName()} subjects. They are placed around the Registrar's Gen Ed subjects in the same weekly schedule. You can edit, remove and approve ${progName()} subjects only; the Gen Ed subjects are view-only.`}
      </p>
      <select value={programId} onChange={(e) => setProgramId(e.target.value)}>
        <option value="">-- Program --</option>
        {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      {loadingCombos && <span> Loading year/semester options…</span>}

      {!loadingCombos && programId && combos.length === 0 && (
        <p style={{ color: "red", marginTop: "10px" }}>
          No sections exist yet for this program. Add a Section (Curriculum/Sections setup)
          before generating a schedule — the engine has nothing to schedule without one.
        </p>
      )}

      {combos.length > 0 && (
        <>
          <select value={yearLevel} onChange={(e) => setYearLevel(e.target.value)} aria-label="Year level">
            {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={semester} onChange={(e) => setSemester(e.target.value)} aria-label="Semester">
            {semesterOptions.map((sem) => <option key={sem} value={sem}>{sem}</option>)}
          </select>
        </>
      )}

      <button onClick={() => run(false)} disabled={running || !programId || !yearLevel || !semester || badRows.length > 0}
        style={{ color: "white" }} title={badRows.length ? `Fix the Start / End Time of ${badRows.join(", ")} first.` : undefined}>{running ? "Generating…" : "Generate"}</button>
      {programId && yearLevel && semester && (
        <NotGeneratedList programId={programId} yearLevel={yearLevel} semester={semester} refreshKey={listKey}
          onRetry={() => run(true)} retrying={running} />
      )}
      {badRows.length > 0 && (
        <div role="alert" style={{ marginTop: 8, fontSize: 12.5, color: "#a4231a" }}>
          Fix the Start / End Time of {badRows.join(", ")} before generating (see the red note in {badRows.length === 1 ? "that row" : "those rows"}).
        </div>
      )}

      {programId && yearLevel && semester && (() => {
        // The subjects this run will schedule: same program + year level + semester, only the kind this role generates.
        const scope = (allSubjects || []).filter((s) => String(s.program) === String(programId)
          && s.year_level === yearLevel && s.semester === semester);
        const shown = scope.filter((s) => s.classification === kindWord).sort((a, b) => String(a.code).localeCompare(String(b.code)));
        const otherCount = scope.length - shown.length;
        return (
          <div style={{ marginTop: "16px", border: "1px solid #e0e6ed", borderRadius: "10px", overflow: "hidden" }}>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "6px", padding: "10px 14px", background: "#f7f9fc", fontSize: "13px" }}>
              <strong style={{ color: "#003366" }}>Subjects to be scheduled — {yearLevel}, {semester}</strong>
              <span style={{ color: "#64748b" }}>
                {allSubjects === null ? "Loading…" : `${shown.length} ${kindWord} subject${shown.length === 1 ? "" : "s"}`}
              </span>
            </div>
            {allSubjects !== null && shown.length === 0 ? (
              <p style={{ margin: 0, padding: "12px 14px", fontSize: "13px", color: "#a4231a" }}>
                No {kindWord} subjects are set up for this year and semester. Check the Curriculum tab before generating.
              </p>
            ) : (
              <div style={{ maxHeight: "min(460px, 60vh)", overflow: "auto" }}>
                <table style={{ margin: 0, boxShadow: "none", border: "none", borderRadius: 0, width: "100%", minWidth: isRegistrar ? 1170 : 1180, tableLayout: "fixed" }}>
                  <thead><tr><th style={{ width: 86 }}>Code</th><th style={{ width: isRegistrar ? 200 : 180 }}>Subject</th><th style={{ width: 118 }}>Needs</th>{!isRegistrar && <th style={{ width: 230 }}>Professor</th>}<th style={{ width: 310 }}>Room</th><th style={{ width: 128 }}>Start Time</th><th style={{ width: 128 }}>End Time</th>{isRegistrar && <th style={{ width: 190 }}>Shared Class / Programs</th>}</tr></thead>
                  <tbody>
                    {shown.map((s) => {
                      const p = picks[s.id] || {};
                      const dept = (programs.find((p) => String(p.id) === String(programId)) || {}).department;
                      const rooms = roomList.filter((r) => (s.lab_units > 0 ? r.room_type === "lab" : (r.room_type !== "lab" || !!r.department)) && (!r.department || String(r.department).toLowerCase().replace(/[^a-z0-9]/g, "") === String(dept || "").toLowerCase().replace(/[^a-z0-9]/g, "")));
                      // Computer Studies major subjects: only the department's own laboratories (Comp Lab C / D), never an ordinary lecture room
                      // the server's list of rooms Generate accepts for this subject (same check as Generate); the older filter below only if it is missing
                      const allowedIds = roomAllowed && roomAllowed[s.id] ? new Set(roomAllowed[s.id].map(String)) : null;
                      const roomsShown = allowedIds ? roomList.filter((r) => allowedIds.has(String(r.id)))
                        : ((!isRegistrar && /comput/i.test(dept || "")) ? rooms.filter((r) => r.room_type === "lab" && !!r.department) : rooms);
                      const nSec = programSections.filter((x) => x.year_level === yearLevel && x.semester === semester).length;
                      const perWeek = (Number(s.lec_units) || 0) + (Number(s.lab_units) || 0) * 3;
                      const kindText = s.lab_units > 0 && s.lec_units > 0 ? "Lecture + Lab" : (s.lab_units > 0 ? "Lab" : "Lecture");
                      const room = p.room !== undefined ? p.room : (savedRooms[s.id] || "");
                      const sel = { fontSize: 12, padding: "3px 4px", width: "100%", maxWidth: "100%", boxSizing: "border-box" };
                      const timeProblem = timeWindowProblem(s, p.start, p.end);
                      // the chosen professor's free time (availability minus their classes): times outside it are marked, still selectable
                      const prof = !isRegistrar && p.teacher ? profOpts?.teachers?.[p.teacher] : null;
                      const need = needMinutes(s);
                      const outside = (a, b) => (prof && prof.submitted ? !professorFits(prof.free, need, a, b) : false);
                      const mark = (bad) => (bad ? " (outside professor's time)" : "");
                      const starts = startOptions(s, p.end), ends = endOptions(s, p.start);
                      const showHint = !timeProblem && (p.start || p.end || prof);
                      return (
                        <ErrorBoundary key={s.id} row colSpan={7} what={`the row for ${s.code}`}>
                        <React.Fragment>
                        <tr style={timeProblem ? { background: "#fff5f5" } : undefined}>
                          <td style={{ whiteSpace: "nowrap", verticalAlign: "middle" }}>{s.code}</td><td style={{ verticalAlign: "middle" }}>{s.title}</td>
                          <td style={{ verticalAlign: "middle", fontSize: 12, lineHeight: 1.35, color: "#334155" }}>
                            <div><strong>{hrs(perWeek)} hrs/wk</strong></div><div>{kindText}</div><div>{nSec} section{nSec === 1 ? "" : "s"}</div>
                          </td>
                          {!isRegistrar && (() => {
                            const pr = profRow(s.id);
                            const opts = pr ? pr.qualified.map((id) => profOpts.teachers[id]).filter(Boolean) : [];
                            const chosen = p.teacher ? profOpts?.teachers?.[p.teacher] : null;
                            const total = chosen ? chosen.current_hours + chosenHours(chosen.id) : 0;
                            const over = chosen && chosen.max_hours > 0 && total > chosen.max_hours + 1e-9;
                            const partner = pr?.partner_id ? (profOpts.subjects.find((x) => x.subject_id === pr.partner_id) || {}).code : "";
                            return (
                              <td style={{ verticalAlign: "top" }}>
                                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                                  <div style={{ flex: 1, minWidth: 0 }}>
                                    <TeacherPicker compact ariaLabel={`Professor for ${s.code}`} value={p.teacher || ""} onChange={(v) => setProfessor(s.id, v)}
                                      disabled={!pr || opts.length === 0 || (keepEdited && pr.sections === 0)}
                                      title={partner ? `${s.code} and ${partner} are a Lecture and Lab: they keep one professor.` : undefined}
                                      emptyLabel={profOpts === null ? "Loading…" : (profOpts.error ? "Automatic (professor list not loaded)" : "Automatic")}
                                      options={(() => {
                                        // The Professor list for this program / year / semester is loaded AFTER the table first renders
                                        // (and again whenever the scope changes): until this row's entry is there, there is nothing to rank.
                                        if (!pr || opts.length === 0) return [];
                                        // advice only: qualified teachers who fit this row (limit + free time inside the chosen range) first
                                        const range = (p.start || p.end) ? [p.start ? toMin(p.start) : 0, p.end ? toMin(p.end) : 24 * 60] : null;
                                        const other = (tid) => chosenHours(tid) - (String(p.teacher || "") === String(tid) ? pr.total_hours : 0);
                                        const { suggested, others, missing } = rankProfessors(opts, pr, range, other);
                                        if (missing) return [];
                                        const find = (t) => `${t.full_name || ""} ${t.school_id || ""} ${t.username || ""}`;
                                        return [
                                          ...suggested.map(({ teacher: t, why }) => ({ id: t.id, label: `${t.label} — ${why}`, group: "Suggested", search: find(t) })),
                                          ...others.map(({ teacher: t, badge, loadText }) => ({ id: t.id, label: `${t.label} (${loadText}) — ${badge}`,
                                            group: suggested.length ? "Other qualified" : "Qualified", search: find(t) })),
                                        ];
                                      })()} />
                                  </div>
                                  <button type="button" disabled={opts.length === 0} onClick={() => setTimeFor({ code: s.code, teachers: opts, initialId: p.teacher || "" })}
                                    aria-label={`Faculty time for ${s.code}`} title="See the teacher's availability, load and classes"
                                    style={{ background: "white", color: "#003366", border: "1px solid #94a3b8", borderRadius: "50%", width: 24, height: 24, padding: 0, fontSize: 13, lineHeight: "22px", cursor: opts.length ? "pointer" : "not-allowed", flex: "0 0 auto", boxShadow: "none" }}>ⓘ</button>
                                </div>
                                {profOpts && !profOpts.error && !pr && (
                                  <div style={{ fontSize: 11, color: "#64748b", marginTop: 3 }}>No suggestions for {s.code} (not in the professor list).</div>
                                )}
                                {profOpts?.error && (
                                  <div style={{ fontSize: 11, color: "#a4231a", marginTop: 3 }}>The professor list could not be loaded; Generate will choose automatically.</div>
                                )}
                                {pr && opts.length === 0 && pr.no_qualified_reason && (
                                  <div style={{ fontSize: 11, color: "#a4231a", marginTop: 3, lineHeight: 1.3 }}>{pr.no_qualified_reason}</div>
                                )}
                                {pr && keepEdited && pr.sections === 0 && opts.length > 0 && (
                                  <div style={{ fontSize: 11, color: "#475569", marginTop: 3, lineHeight: 1.3 }}>🔒 Every section of {s.code} was edited by hand and is kept as it is. Untick "Keep the classes I edited by hand" to choose a professor.</div>
                                )}
                                {chosen && partner && <div style={{ fontSize: 11, color: "#475569", marginTop: 3 }}>Also teaches {partner} (Lec and Lab keep one professor).</div>}
                                {over && (
                                  <div role="alert" style={{ fontSize: 11, color: "#a4231a", marginTop: 3, lineHeight: 1.3 }}>
                                    {chosen.label} would have {hrs(total)} of {chosen.max_hours} hrs with your choices ({hrs(pr.total_hours)} hrs here for {pr.sections} section{pr.sections === 1 ? "" : "s"}). {profOpts.policy === "strict" ? "The limit is strict: classes over it will not be placed." : "Generate will warn about the overload."}
                                  </div>
                                )}
                              </td>
                            );
                          })()}
                          <td>
                            <RoomSelect rooms={roomsShown} suffix={freeText} groupBy={(r) => (r.room_type === "lab" ? "Computer laboratories" : "Lecture rooms")} value={room} onChange={(v) => setPick(s.id, "room", v)} ariaLabel={`Room for ${s.code}`} width="100%" style={{ fontSize: 12, padding: "3px 6px" }} />
                          </td>
                          <td>
                            <select style={sel} value={p.start || ""} onChange={(e) => setTimes(s, "start", e.target.value)} aria-label={`Start time for ${s.code}`}>
                              <option value="">Any time</option>
                              {(p.start && !starts.includes(p.start) ? [p.start, ...starts] : starts).map((t) => (
                                <option key={t} value={t}>{timeLabel(t)}{mark(outside(toMin(t), p.end ? toMin(p.end) : DAY_END))}</option>))}
                            </select>
                          </td>
                          <td>
                            <select style={sel} value={p.end || ""} onChange={(e) => setTimes(s, "end", e.target.value)} aria-label={`End time for ${s.code}`}>
                              <option value="">Any time</option>
                              {(p.end && !ends.includes(p.end) ? [...ends, p.end] : ends).map((t) => (
                                <option key={t} value={t}>{timeLabel(t)}{mark(outside(p.start ? toMin(p.start) : DAY_START, toMin(t)))}</option>))}
                            </select>
                          </td>
                          {isRegistrar && (
                            <td style={{ verticalAlign: "middle" }}>
                              {sharedFor(s.id) ? (
                                <button onClick={() => setSharedItem(sharedFor(s.id))} style={{ background: "#fff", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "3px 8px", fontSize: 12, cursor: "pointer", maxWidth: "100%", whiteSpace: "normal", textAlign: "left" }}>{sharedLabel(sharedFor(s.id))}</button>
                              ) : <span style={{ fontSize: 12, color: "#94a3b8" }}>…</span>}
                            </td>
                          )}
                        </tr>
                        {showHint && (
                          <tr>
                            <td colSpan={7} style={{ paddingTop: 0, fontSize: 11.5, color: "#475569", lineHeight: 1.4 }} aria-label={`Time hint for ${s.code}`}>
                              {s.code}: {needHint(s, p.start)}.
                              {timeNotice[s.id] ? <span style={{ color: "#92400e" }}> {timeNotice[s.id]}</span> : null}
                              {prof && (prof.submitted
                                ? <> {prof.label} free {profFreeText(prof.free) || "at no time this week"}{(p.start || p.end) && outside(p.start ? toMin(p.start) : DAY_START, p.end ? toMin(p.end) : DAY_END) ? " (none of it fits this range: Generate will skip it with the reason)" : ""}.</>
                                : <> {prof.label} has not submitted availability (free whenever not teaching).</>)}
                            </td>
                          </tr>
                        )}
                        {timeProblem && (
                          <tr style={{ background: "#fff5f5" }}>
                            <td colSpan={7} role="alert" style={{ paddingTop: 0, fontSize: 12, color: "#a4231a" }}>
                              {s.code}: {timeProblem} Choose a longer range, or set Start / End to "Any time".
                            </td>
                          </tr>
                        )}
                        </React.Fragment>
                        </ErrorBoundary>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {otherCount > 0 && (
              <p style={{ margin: 0, padding: "8px 14px", fontSize: "12px", color: "#64748b", borderTop: "1px solid #eef2f6" }}>
                {otherCount} {isRegistrar ? "program" : "Gen Ed"} subject{otherCount === 1 ? "" : "s"} for this term {isRegistrar ? "are generated by each Dean" : "are generated by the Registrar"}.
              </p>
            )}
          </div>
        );
      })()}

      {!isRegistrar && programId && yearLevel && semester && sharedInfo && sharedInfo.subjects.length > 0 && (
        <div style={{ marginTop: "14px", border: "1px solid #e0e6ed", borderRadius: "10px", overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", background: "#f7f9fc", fontSize: "13px" }}>
            <strong style={{ color: "#003366" }}>Gen Ed (minor) subjects of this program — for your information</strong>
            <div style={{ color: "#64748b", marginTop: 2 }}>The Registrar schedules these and decides which programs share a class. Shown here so you know which times your students already use.</div>
          </div>
          <table style={{ margin: 0, boxShadow: "none", border: "none", borderRadius: 0, width: "100%" }}>
            <thead><tr><th>Code</th><th>Subject</th><th>Shared class (set by the Registrar)</th></tr></thead>
            <tbody>
              {sharedInfo.subjects.map((x) => (
                <tr key={x.subject_id}><td>{x.code}</td><td>{x.title}</td>
                  <td style={{ fontSize: 12.5, color: "#334155" }}>{sharedLabel(x)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <label style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "12px", fontSize: "13px", color: "#334155" }}
        title="A class you edited or moved by hand stays exactly where you put it. Untick to let Generate place those classes again too.">
        <input type="checkbox" checked={keepEdited} onChange={(e) => setKeepEdited(e.target.checked)} />
        Keep the classes I edited by hand (they are locked; untick to place them again)
      </label>
      {isRegistrar && (
        <label style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "12px", fontSize: "13px", color: "#334155" }}>
          <input type="checkbox" checked={mergeMinors} onChange={(e) => setMergeMinors(e.target.checked)} />
          Share Gen Ed classes with other departments when the students fit in the room
        </label>
      )}

      {result && !result.error && (
        <div style={{ marginTop: "20px" }}>
          {(() => {
            const need = uniqueClasses(result.conflicts).length, clashN = result.clashes?.total || 0;
            const ok = need === 0 && clashN === 0;
            return (
              <div style={{ background: ok ? "#ecfdf5" : "#fffbeb", border: `1px solid ${ok ? "#a7f3d0" : "#fde68a"}`, borderRadius: 8, padding: "10px 14px", fontSize: 13.5, maxWidth: 760, color: "#1e293b" }}>
                <div><strong>{result.created_schedule_ids.length}</strong> class period{result.created_schedule_ids.length === 1 ? "" : "s"} saved as <strong>Draft</strong> (nothing is final until you approve it in the Schedules tab).</div>
                {need > 0 && (
                  <div><strong>{need}</strong> class{need === 1 ? " was" : "es were"} skipped: {need === 1 ? "it" : "they"} could not be placed without breaking a rule.{" "}
                    <button type="button" onClick={() => setSkipped(uniqueClasses(result.conflicts))}
                      style={{ background: "none", border: "none", boxShadow: "none", color: "#003366", textDecoration: "underline", padding: 0, fontSize: 13.5, cursor: "pointer" }}>See why</button>
                  </div>
                )}
                {(result.missing_untouched || []).map((t, i) => <div key={i} style={{ color: "#7a4b00" }}>{t}</div>)}
                {ok && <div>Everything fits: no conflicts and nothing left to place.</div>}
              </div>
            );
          })()}
          {(result.kept_edited || []).length > 0 && (
            <div style={{ background: "#f0f6ff", border: "1px solid #cfe0f7", borderRadius: 8, padding: "8px 12px", fontSize: 13, color: "#1e3a5f", maxWidth: 760, marginTop: 8 }}>
              🔒 {result.kept_edited.length} class{result.kept_edited.length === 1 ? "" : "es"} you edited by hand were kept where you put them: {result.kept_edited.join(", ")}.
            </div>
          )}
          {result.clashes && result.clashes.total > 0 && (
            <div id="gen-clashes" role="alert" style={{ margin: "10px 0", maxWidth: "860px", border: "2px solid #b91c1c", background: "#fef2f2", borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontWeight: 700, fontSize: "14px", color: "#b91c1c", marginBottom: "4px" }}>
                ⚠ {result.clashes.total} real conflict{result.clashes.total === 1 ? "" : "s"} found after generating (same teacher, room or students at the same time)
              </div>
              <div style={{ fontSize: 12.5, color: "#7f1d1d", marginBottom: 8 }}>This should not happen: please review {result.clashes.total === 1 ? "it" : "them"} before approving anything.</div>
              <ConflictList report={result.clashes} emptyText="No conflicts." />
              <button onClick={() => setProblems(true)} style={{ background: "#b91c1c", color: "white", border: "none", borderRadius: 6, padding: "7px 16px", fontSize: 13, cursor: "pointer", marginTop: 8 }}>Review conflicts</button>
            </div>
          )}
          {result.warning && (
            <div style={{ background: "#fff8e6", border: "1px solid #f0d58a", borderRadius: "8px", padding: "10px 14px", fontSize: "13px", color: "#5b4500", maxWidth: "760px", margin: "10px 0" }}>
              {result.warning}
            </div>
          )}
          {result.merged_classes && result.merged_classes.length > 0 && (
            <div style={{ background: "#eef7ee", border: "1px solid #b7dcb7", borderRadius: "8px", padding: "10px 14px", fontSize: "13px", color: "#1d5a1d", maxWidth: "760px", margin: "10px 0" }}>
              <strong>{result.merged_classes.length} shared class{result.merged_classes.length === 1 ? "" : "es"}:</strong> these subjects joined another department's class, so they use no extra teacher, room or time.
              <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                {result.merged_classes.map((m, i) => (
                  <li key={i}>{m.subject} — with {m.joined.join(", ")} · {m.students} students in {m.room} (seats {m.capacity})</li>
                ))}
              </ul>
            </div>
          )}
          {result.shared_classes && result.shared_classes.length > 0 && (
            <div style={{ background: "#eef7ee", border: "1px solid #b7dcb7", borderRadius: "8px", padding: "10px 14px", fontSize: "13px", color: "#1d5a1d", maxWidth: "760px", margin: "10px 0" }}>
              <strong>{result.shared_classes.length} shared class{result.shared_classes.length === 1 ? "" : "es"} generated</strong> (one teacher, room and time for all participating programs):
              <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                {result.shared_classes.map((m, i) => (
                  <li key={i}>{m.subject}: {[m.host, ...m.joined].join(" + ")} · {m.students} students in {m.room} (seats {m.capacity})
                    {m.skipped.length > 0 && <div style={{ color: "#7a4b00" }}>Not joined: {m.skipped.join("; ")}</div>}</li>
                ))}
              </ul>
            </div>
          )}
          {result.created_schedule_ids.length === 0 && result.conflicts.length === 0 && (
            <p style={{ color: "#a00" }}>
              0 entries and 0 conflicts usually means this exact Program/Year/Semester has no {kindWord}
              subjects, or no Faculty/Rooms/TimeSlots exist yet for the engine to assign. Check the
              curriculum for this program/year/semester, and confirm rooms and faculty are set up.
            </p>
          )}
          {result.room_notes && result.room_notes.length > 0 && (
            <div style={{ margin: "10px 0", padding: "10px 14px", background: "#f0f6ff", border: "1px solid #cfe0f7", borderRadius: "8px", fontSize: "12.5px", color: "#1e3a5f" }}>
              <b>Room assignments</b>
              {result.room_notes.map((n, i) => <div key={i} style={{ marginTop: "3px" }}>{n}</div>)}
            </div>
          )}
          <WorkloadWarningList warnings={result.workload_warnings} canResolve />
          {(result.lunch_gap_warnings || []).length > 0 && (
            <div role="status" style={{ marginTop: 10, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "10px 12px", fontSize: 12.5, color: "#92400e" }}>
              <strong>Lunch gap (optional setting): {result.lunch_gap_warnings.length} day{result.lunch_gap_warnings.length === 1 ? "" : "s"} without a free hour between 10:30 AM and 2:30 PM.</strong>{" "}
              Every class was still placed; these are warnings only.
              <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>{result.lunch_gap_warnings.slice(0, 12).map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      {result?.error && <p style={{ color: "red" }}>{result.error}</p>}
      {timeFor && (
        <FacultyTimePopover teachers={timeFor.teachers} initialId={timeFor.initialId} subjectCode={timeFor.code} semester={semester}
          programId={programId} yearLevel={yearLevel} onClose={() => setTimeFor(null)} />
      )}
      {skipped && (
        <div role="alertdialog" aria-label="Some classes were not placed" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "white", borderRadius: 12, maxWidth: 720, width: "100%", maxHeight: "86vh", display: "flex", flexDirection: "column", boxShadow: "0 12px 40px rgba(0,0,0,.3)", borderTop: "5px solid #d97706" }}>
            <div style={{ padding: "16px 20px 6px" }}>
              <h3 style={{ margin: 0, color: "#92400e" }}>⚠ Some classes were not placed</h3>
              <p style={{ margin: "6px 0 0", fontSize: 13, color: "#475569" }}>
                {skipped.length} class{skipped.length === 1 ? " was" : "es were"} skipped because {skipped.length === 1 ? "it" : "they"} could not be placed without breaking a rule.
                Everything else was saved as Draft. Nothing was changed to make room.
              </p>
            </div>
            <div style={{ overflow: "auto", padding: "4px 20px" }}>
              {skipped.map((c) => (
                <div key={`${c.section_id}-${c.subject_id}`} style={{ padding: "9px 0", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
                  <div style={{ fontWeight: 600, color: "#1e293b" }}>{c.code || String(c.subject).split(" - ")[0]} — {c.title || String(c.subject).split(" - ").slice(1).join(" - ")}</div>
                  <div style={{ color: "#64748b", fontSize: 12 }}>Section {String(c.section)} · {c.year_level}</div>
                  <div style={{ color: "#a4231a", marginTop: 3 }}>{c.reason || "No reason was recorded."}</div>
                </div>
              ))}
            </div>
            <div style={{ padding: "12px 20px", textAlign: "right", borderTop: "1px solid #eef2f6" }}>
              <button onClick={() => setSkipped(null)} autoFocus style={{ background: "#003366", color: "white", border: "none", borderRadius: 6, padding: "7px 22px", fontSize: 13.5, cursor: "pointer" }}>OK</button>
            </div>
          </div>
        </div>
      )}
      {popup && (
        <div role="alertdialog" aria-label={popup.title} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "white", borderRadius: 12, maxWidth: 520, width: "100%", padding: "18px 20px", boxShadow: "0 12px 40px rgba(0,0,0,.3)", borderTop: `5px solid ${popup.tone === "bad" ? "#b91c1c" : "#d97706"}` }}>
            <h3 style={{ margin: "0 0 10px", color: popup.tone === "bad" ? "#b91c1c" : "#92400e" }}>⚠ {popup.title}</h3>
            {popup.items.map((it, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", padding: "8px 0", borderBottom: "1px solid #f1f5f9", fontSize: 13.5 }}>
                <span>{it.text}</span>
                {it.action === "clashes" && <button onClick={() => { setPopup(null); setProblems(true); }} style={popBtn}>{it.label}</button>}
                {it.action === "unplaced" && <button onClick={() => { setPopup(null); setProblems(true); }} style={popBtn}>{it.label}</button>}
                {it.action === "overload" && <button onClick={() => { setPopup(null); setResolver(0); }} style={popBtn}>{it.label}</button>}
              </div>
            ))}
            <div style={{ textAlign: "right", marginTop: 12 }}><button onClick={() => setPopup(null)} style={{ ...popBtn, background: "white", color: "#003366" }}>Close</button></div>
          </div>
        </div>
      )}
      {sharedItem && sharedInfo && <SharedClassModal item={sharedInfo.subjects.find((x) => x.subject_id === sharedItem.subject_id) || sharedItem} program={sharedInfo.program} onClose={() => setSharedItem(null)} onChanged={loadShared} key={sharedItem.subject_id} />}
      {problems && result && (
        <ScheduleProblemsModal clashes={result.clashes?.conflicts || []} unplaced={[]} yearLevel={yearLevel} picks={picks}
          onClose={() => setProblems(false)}
          onFixed={(d) => {
            if (d.clash != null) dropClash([d.clash]);
          }} />
      )}
      {resolver !== null && <ResolverWindow focusId={resolver || null} onClose={() => { setResolver(null); notifyWorkloadChanged(); }} />}
    </div>
  );
}

export default GenerateSchedulePanel;
