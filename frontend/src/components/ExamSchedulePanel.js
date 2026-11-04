import React, { useState, useEffect } from "react";
import API from "../services/api";
import Badge from "./Badge";
import { HistoricalHint } from "./Charts";
import RoomSelect from "./RoomSelect";
import { kindLabel } from "../utils/labels";
import ExamConflictDialog from "./ExamConflictDialog";

/* Exam Schedule -- shared by the Registrar and the Dean.
     Registrar : sees and prints MINOR subjects only, can edit their date and time.
     Dean      : sees minor + major subjects (a Gen Ed / program column says which), edits and prints program subjects only.
   The table follows the school's printed exam sheet: one banner per exam date, then
   Time | Room | Subject Code | Subject / Description | Faculty (no Section column). */

const SEMESTERS = ["1st Sem", "2nd Sem"];
const PERIODS = [["prelim", "Prelim"], ["midterm", "Midterm"], ["final", "Final"]];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"];

const fieldLabel = { display: "block", fontSize: "11.5px", fontWeight: 600, color: "#64748b", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.3px" };
const input = { padding: "9px 10px", borderRadius: "7px", border: "1px solid #cdd6e0", fontSize: "13.5px", minWidth: "140px", background: "white" };
const card = { background: "white", borderRadius: "10px", padding: "20px 24px", marginBottom: "24px", border: "1px solid #e0e6ed", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" };
const smallBtn = { background: "white", color: "#003366", border: "1px solid #cdd6e0", padding: "4px 10px", borderRadius: "6px", fontSize: "12px", fontWeight: 600, cursor: "pointer", marginRight: "6px" };
const th = { textAlign: "left", padding: "10px 12px", background: "#003366", color: "white", fontSize: "12px", letterSpacing: "0.4px", textTransform: "uppercase", fontWeight: 600 };
const td = { padding: "9px 12px", fontSize: "13.5px", color: "#1f2937", borderBottom: "1px solid #eef2f6", verticalAlign: "middle" };

function clock(t) {            // "13:00:00" -> "1:00"
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")}`;
}
function ampm(t) { return t && Number(t.split(":")[0]) >= 12 ? "PM" : "AM"; }
function timeRange(e) {
  if (!e.timeslot_start) return "Time not set";
  const a = ampm(e.timeslot_start), b = ampm(e.timeslot_end);
  return `${clock(e.timeslot_start)}${a !== b ? " " + a : ""} – ${clock(e.timeslot_end)} ${b}`;
}
function niceDate(iso) {
  if (!iso) return "Date not set";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", weekday: "long" });
}
const weekdayOf = (iso) => WEEKDAYS[new Date(iso + "T00:00:00").getDay()];

function ExamSchedulePanel({ role, programId }) {
  const isRegistrar = role === "registrar";
  const ownKind = isRegistrar ? "minor" : "major";

  const [exams, setExams] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [sections, setSections] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [facultyList, setFacultyList] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");

  // filters
  const [search, setSearch] = useState("");
  const [period, setPeriod] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [yearLevel, setYearLevel] = useState("");

  const [form, setForm] = useState({
    subject: "", section: "", proctor: "", room: "", exam_date: "",
    start_time: "09:00", end_time: "10:00", exam_period: "prelim",
  });
  const [genForm, setGenForm] = useState({ semester: "", exam_period: "prelim", exam_start_date: "", exam_end_date: "" });
  const [genResult, setGenResult] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [conflictDialog, setConflictDialog] = useState(false);
  const [deanDialog, setDeanDialog] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [editing, setEditing] = useState(null);       // { id, exam_date, start_time, end_time }
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [showManual, setShowManual] = useState(false);

  const load = () => {
    setLoadError("");
    Promise.all([
      API.get("/exams/"), API.get("/curriculum/subjects/"), API.get("/engine/sections/"),
      API.get("/rooms/"), API.get("/faculty/profiles/"),
    ]).then(([e, s, sec, r, f]) => {
      setExams(e.data); setSubjects(s.data); setSections(sec.data); setRooms(r.data); setFacultyList(f.data);
    }).catch((err) => setLoadError(err.code === "ECONNABORTED"
      ? "The exam schedule took too long to load (slow connection or database)."
      : (err.response?.data?.detail || "Could not load the exam schedule.")));
  };
  useEffect(() => { load(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const canEdit = (e) => e.subject_classification === ownKind;

  /* ---------- filtering ---------- */
  const q = search.trim().toLowerCase();
  const filtered = exams.filter((e) => {
    if (period && e.exam_period !== period) return false;
    if (!isRegistrar) {
      if (sectionId && String(e.section) !== sectionId) return false;
      if (yearLevel && e.year_level !== yearLevel) return false;
    }
    if (q) {
      const hay = `${e.subject_code} ${e.subject_title} ${e.proctor_full_name} ${e.room_name} ${e.exam_date || ""} ${e.exam_period} ${e.section_name} ${e.subject_classification}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const sortKey = (e) => `${e.exam_date || "9999-99-99"} ${e.timeslot_start || "99:99"} ${e.room_name}`;
  const sorted = [...filtered].sort((a, b) => sortKey(a).localeCompare(sortKey(b)));
  const byDate = [];
  sorted.forEach((e) => {
    const last = byDate[byDate.length - 1];
    if (last && last.date === (e.exam_date || "")) last.items.push(e);
    else byDate.push({ date: e.exam_date || "", items: [e] });
  });

  const sectionMap = {};
  exams.forEach((e) => { sectionMap[e.section] = `${e.section_name} · ${e.program_name} · ${e.semester}`; });
  const sectionChoices = Object.entries(sectionMap)
    .map(([id, label]) => ({ id, label }))
    .sort((a, b) => a.label.localeCompare(b.label));
  const yearChoices = YEARS.filter((y) => exams.some((e) => e.year_level === y));

  /* ---------- actions ---------- */
  const printPdf = async () => {
    setDownloading(true);
    try {
      const semesters = [...new Set(filtered.map((e) => e.semester))];
      const res = await API.get("/exams/export-pdf/", {
        params: { exam_period: period || undefined, semester: semesters.length === 1 ? semesters[0] : undefined },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (err) {
      alert(isRegistrar
        ? "Could not make the PDF -- there may be no Gen Ed exams for this exam period yet."
        : "Could not make the PDF -- there may be no program-subject exams for this exam period yet.");
    } finally {
      setDownloading(false);
    }
  };

  const runGenerate = async () => {
    if (!genForm.semester || !genForm.exam_start_date || !genForm.exam_end_date) return;
    setGenerating(true);
    setGenResult(null);
    try {
      const res = await API.post("/exams/generate/", {
        semester: genForm.semester, exam_period: genForm.exam_period,
        exam_start_date: genForm.exam_start_date, exam_end_date: genForm.exam_end_date,
      }, { timeout: 180000 });
      setGenResult(res.data);
      setConflictDialog(isRegistrar && (res.data.pending || []).length > 0);
      load();
    } catch (err) {
      setGenResult({ error: err.response?.data?.detail || "Generation failed — please try again." });
    } finally {
      setGenerating(false);
    }
  };

  const startEdit = (e) => setEditing({
    id: e.id, exam_date: e.exam_date || "", start_time: (e.timeslot_start || "09:00").slice(0, 5),
    end_time: (e.timeslot_end || "10:00").slice(0, 5),
  });
  const saveEdit = async () => {
    if (!editing.exam_date || !editing.start_time || !editing.end_time) { setEditError("Pick a date and both times."); return; }
    if (editing.start_time >= editing.end_time) { setEditError("The end time must be later than the start time."); return; }
    setSaving(true); setEditError("");
    try {
      const slot = await API.post("/engine/timeslots/get_or_create/", {
        day: weekdayOf(editing.exam_date), start_time: editing.start_time, end_time: editing.end_time });
      await API.patch(`/exams/${editing.id}/`, { exam_date: editing.exam_date, timeslot: slot.data.id });
      setEditing(null);
      load();
    } catch (err) {
      const d = err.response?.data;
      setEditError(d?.timeslot ? [].concat(d.timeslot).join(" ") : (d?.detail || (d ? JSON.stringify(d) : "Could not save.")));
    } finally {
      setSaving(false);
    }
  };
  const removeExam = async (e) => {
    if (!window.confirm(`Remove the ${e.subject_code} exam on ${e.exam_date || "this date"}?`)) return;
    try { await API.delete(`/exams/${e.id}/`); load(); }
    catch (err) { alert(err.response?.data?.detail || "Could not remove that exam."); }
  };

  const addExam = async () => {
    setError("");
    if (!form.subject || !form.section || !form.proctor || !form.room || !form.exam_date || !form.start_time || !form.end_time) {
      setError("Fill in every field first."); return;
    }
    try {
      const slotRes = await API.post("/engine/timeslots/get_or_create/", {
        day: weekdayOf(form.exam_date), start_time: form.start_time, end_time: form.end_time });
      await API.post("/exams/", {
        subject: form.subject, section: form.section, proctor: form.proctor, room: form.room,
        timeslot: slotRes.data.id, exam_period: form.exam_period, exam_date: form.exam_date,
      });
      setForm({ ...form, subject: "", section: "", proctor: "", room: "", exam_date: "" });
      load();
    } catch (err) {
      const d = err.response?.data;
      setError(d?.timeslot ? [].concat(d.timeslot).join(" ") : (d?.detail || JSON.stringify(d)));
    }
  };

  const ownedSubjects = subjects.filter((s) =>
    s.classification === ownKind && (!programId || String(s.program) === String(programId)));
  const cols = isRegistrar ? 6 : 7;          // visible columns incl. the Edit/Remove column

  return (
    <div>
      <h3 style={{ color: "#003366", marginTop: 0 }}>
        {isRegistrar ? "Exam Schedule — Gen Ed Subjects" : "Exam Schedule — Program & Gen Ed Subjects"}
      </h3>
      <p style={{ fontSize: "13px", color: "#475569", marginTop: 0 }}>
        {isRegistrar
          ? "You generate, edit and print the Gen Ed exams. Everything is checked against class schedules and the other exams automatically."
          : "You can see the Registrar's Gen Ed exams, but you generate, edit and print only the program-subject exams of your college(s)."}
      </p>

      <div style={card}>
        <h4 style={{ marginTop: 0, marginBottom: "4px", color: "#003366" }}>⚡ Generate Exam Schedule</h4>
        <p style={{ fontSize: "12.5px", color: "#64748b", marginTop: 0, marginBottom: "18px", maxWidth: "680px" }}>
          Auto-assigns room, proctor and time for every {ownKind} subject in the chosen semester, all year levels at once,
          {isRegistrar ? " across every college." : " across every program of your college(s)."} Exams are spread over the
          exam-week dates below and checked against every class and exam already scheduled.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "14px", alignItems: "flex-end" }}>
          <div>
            <label style={fieldLabel}>Semester</label>
            <select style={input} value={genForm.semester} onChange={(e) => setGenForm({ ...genForm, semester: e.target.value })}>
              <option value="">-- Select --</option>
              {SEMESTERS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label style={fieldLabel}>Exam Period</label>
            <select style={input} value={genForm.exam_period} onChange={(e) => setGenForm({ ...genForm, exam_period: e.target.value })}>
              {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label style={fieldLabel}>Exam Week — From</label>
            <input style={input} type="date" value={genForm.exam_start_date} onChange={(e) => setGenForm({ ...genForm, exam_start_date: e.target.value })} />
          </div>
          <div>
            <label style={fieldLabel}>Exam Week — Until</label>
            <input style={input} type="date" value={genForm.exam_end_date} min={genForm.exam_start_date || undefined} onChange={(e) => setGenForm({ ...genForm, exam_end_date: e.target.value })} />
          </div>
          <button onClick={runGenerate} disabled={generating || !genForm.semester || !genForm.exam_start_date || !genForm.exam_end_date}
            style={{ background: generating ? "#6b8bb3" : "#003366", color: "white", border: "none", padding: "10px 24px", borderRadius: "8px", fontSize: "13.5px", fontWeight: 600, cursor: generating ? "default" : "pointer", height: "38px" }}>
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>
        {genResult && !genResult.error && (
          <div style={{ marginTop: "16px", background: "#eafaf0", border: "1px solid #b7e4c7", color: "#1e7a45", borderRadius: "8px", padding: "12px 16px", fontSize: "13px" }}>
            ✓ {genResult.detail || `Created ${genResult.created_count} exam slot(s) across ${genResult.programs_covered ?? 1} program(s).`}
            {genResult.validation?.counts && (
              <div style={{ marginTop: "8px", color: genResult.validation.counts.missing || genResult.validation.counts.room_conflicts || genResult.validation.counts.rule_violations ? "#96690a" : "#1e7a45" }}>
                Checked after generating: {genResult.validation.counts.exams} exams saved ·{" "}
                {genResult.validation.counts.missing} subject(s) without an exam · {genResult.validation.counts.room_conflicts} room double-booking(s) ·{" "}
                {genResult.validation.counts.rule_violations} room-rule exception(s).
                {["missing", "room_conflicts", "rule_violations"].map((k) => (genResult.validation[k] || []).length > 0 && (
                  <ul key={k} style={{ margin: "4px 0 0 18px", padding: 0 }}>
                    {genResult.validation[k].slice(0, 6).map((m, i) => <li key={i}>{typeof m === "string" ? m : JSON.stringify(m)}</li>)}
                    {genResult.validation[k].length > 6 && <li>…and {genResult.validation[k].length - 6} more</li>}
                  </ul>
                ))}
              </div>
            )}
            {genResult.capacity_warnings?.length > 0 && (
              <div style={{ marginTop: "8px", color: "#96690a" }}>
                ℹ {genResult.capacity_warnings.length} exam(s) are in a room with fewer seats than students (the same way the college seats them); check them if needed:
                <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                  {genResult.capacity_warnings.slice(0, 5).map((w, i) => <li key={i}>{w}</li>)}
                  {genResult.capacity_warnings.length > 5 && <li>…and {genResult.capacity_warnings.length - 5} more</li>}
                </ul>
              </div>
            )}
            {isRegistrar && genResult.pending?.length > 0 && (
              <button onClick={() => setConflictDialog(true)} style={{ marginTop: "8px", padding: "6px 14px", borderRadius: "8px", border: "none", background: "#003366", color: "#fff", cursor: "pointer" }}>
                Resolve {genResult.pending.length} conflict{genResult.pending.length === 1 ? "" : "s"}
              </button>
            )}
            {genResult.unresolved?.length > 0 && (
              <div style={{ marginTop: "8px", color: "#96690a" }}>
                ⚠ {genResult.unresolved.length} could not be placed:
                <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>{genResult.unresolved.map((u, i) => <li key={i}>{u}</li>)}</ul>
              </div>
            )}
          </div>
        )}
        {!isRegistrar && (
          <div style={{ marginTop: "12px" }}>
            <button onClick={() => setDeanDialog(true)} disabled={!genForm.semester || !genForm.exam_start_date || !genForm.exam_end_date}
              style={{ padding: "7px 16px", borderRadius: "8px", border: "1px solid #003366", background: "#fff", color: "#003366", cursor: "pointer" }}>
              Registrar requests — move my exams that block Gen Ed exams
            </button>
            <span style={{ fontSize: "12px", color: "#64748b", marginLeft: "8px" }}>(uses the semester, period and exam week above)</span>
          </div>
        )}
        {deanDialog && (
          <ExamConflictDialog isDean pending={[]} form={genForm} onClose={() => setDeanDialog(false)} onApplied={() => load()} />
        )}
        {conflictDialog && isRegistrar && genResult?.pending?.length > 0 && (
          <ExamConflictDialog isDean={!isRegistrar} pending={genResult.pending} form={genForm} onClose={() => setConflictDialog(false)}
            onApplied={() => { load(); setGenResult((g) => g && ({ ...g, pending: [], unresolved: [] })); }} />
        )}
        {genResult?.error && (
          <div style={{ marginTop: "16px", background: "#fdecea", border: "1px solid #f3b3ac", color: "#a4231a", borderRadius: "8px", padding: "12px 16px", fontSize: "13px" }}>
            ⚠ {genResult.error}
          </div>
        )}
      </div>

      {/* ---------- filters + print ---------- */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center", marginBottom: "14px" }}>
        <input type="text" placeholder="Search subject, faculty, room or date" value={search}
          onChange={(e) => setSearch(e.target.value)} style={{ ...input, minWidth: "260px" }} />
        {isRegistrar ? (
          <select style={input} value={period} onChange={(e) => setPeriod(e.target.value)}>
            <option value="">All exam periods</option>
            {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ) : (
          <>
            <select style={input} value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
              <option value="">All sections</option>
              {sectionChoices.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <select style={input} value={yearLevel} onChange={(e) => setYearLevel(e.target.value)}>
              <option value="">All year levels</option>
              {yearChoices.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <select style={input} value={period} onChange={(e) => setPeriod(e.target.value)} title="Also decides which period is printed">
              <option value="">All exam periods</option>
              {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </>
        )}
        {(search || period || sectionId || yearLevel) && (
          <button style={smallBtn} onClick={() => { setSearch(""); setPeriod(""); setSectionId(""); setYearLevel(""); }}>Reset</button>
        )}
        <span style={{ flex: 1 }} />
        <button onClick={printPdf} disabled={downloading}
          title={isRegistrar ? "Prints the Gen Ed exam schedule" : "Prints the program-subject exam schedule (Gen Ed is not printed)"}
          style={{ background: "#003366", color: "white", border: "none", padding: "9px 18px", borderRadius: "8px", fontSize: "13.5px", fontWeight: 600, cursor: "pointer" }}>
          {downloading ? "Preparing PDF…" : "🖨 Preview / Print PDF"}
        </button>
      </div>
      {!isRegistrar && (
        <p style={{ fontSize: "12px", color: "#64748b", marginTop: "-6px" }}>
          The printed PDF contains the <b>program</b> subjects only{period ? ` for the ${period} period` : " (choose an exam period above to print one period)"}.
        </p>
      )}

      {loadError && <p style={{ color: "red" }}>{loadError} <button style={smallBtn} onClick={load}>Try again</button></p>}

      {/* ---------- table ---------- */}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Time</th><th style={th}>Room</th><th style={th}>Subject Code</th>
                <th style={th}>Subject / Description</th><th style={th}>Faculty</th>
                {!isRegistrar && <th style={th}>Type</th>}
                <th style={{ ...th, width: "150px" }}> </th>
              </tr>
            </thead>
            <tbody>
              {byDate.length === 0 && (
                <tr><td style={{ ...td, textAlign: "center", color: "#64748b", padding: "26px" }} colSpan={cols}>
                  {exams.length === 0 ? "No exam schedule yet. Use Generate above." : "No exams match these filters."}
                </td></tr>
              )}
              {byDate.map((g) => (
                <React.Fragment key={g.date || "none"}>
                  <tr>
                    <td colSpan={cols} style={{ background: "#e8eef6", color: "#003366", fontWeight: 700, fontSize: "13px", padding: "8px 12px", borderBottom: "1px solid #d5dfec" }}>
                      {niceDate(g.date)}
                    </td>
                  </tr>
                  {g.items.map((e, i) => (
                    <React.Fragment key={e.id}>
                      <tr style={{ background: i % 2 ? "#f8fafc" : "white" }}>
                        <td style={{ ...td, whiteSpace: "nowrap", fontWeight: 600 }}>{timeRange(e)}</td>
                        <td style={td}>{e.room_name}</td>
                        <td style={{ ...td, fontWeight: 600 }}>{e.subject_code}
                          {e.combined_with && e.combined_with.length > 0 && (
                            <div style={{ fontWeight: 400, fontSize: "11px", color: "#5b6b7c" }}
                                 title="Low-enrollment sections sitting this exam together in one room">
                              Combined with {e.combined_with.join(", ")}
                            </div>
                          )}
                        </td>
                        <td style={td}>{e.subject_title}</td>
                        <td style={td}>{e.proctor_full_name}</td>
                        {!isRegistrar && (
                          <td style={td}><Badge tone={e.subject_classification === "major" ? "success" : "neutral"}>
                            {kindLabel(e.subject_classification, e.program_name)}</Badge></td>
                        )}
                        <td style={{ ...td, whiteSpace: "nowrap" }}>
                          {canEdit(e) ? (
                            <>
                              <button style={smallBtn} onClick={() => { setEditError(""); startEdit(e); }}>Edit</button>
                              <button style={{ ...smallBtn, color: "#a4231a" }} onClick={() => removeExam(e)}>Remove</button>
                            </>
                          ) : <span style={{ fontSize: "12px", color: "#94a3b8" }}>View only</span>}
                        </td>
                      </tr>
                      {editing && editing.id === e.id && (
                        <tr style={{ background: "#fff8e6" }}>
                          <td colSpan={cols} style={{ ...td, padding: "12px" }}>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "flex-end" }}>
                              <div><label style={fieldLabel}>Date</label>
                                <input style={input} type="date" value={editing.exam_date} onChange={(ev) => setEditing({ ...editing, exam_date: ev.target.value })} /></div>
                              <div><label style={fieldLabel}>Start</label>
                                <input style={input} type="time" value={editing.start_time} onChange={(ev) => setEditing({ ...editing, start_time: ev.target.value })} /></div>
                              <div><label style={fieldLabel}>End</label>
                                <input style={input} type="time" value={editing.end_time} onChange={(ev) => setEditing({ ...editing, end_time: ev.target.value })} /></div>
                              <button disabled={saving} onClick={saveEdit}
                                style={{ background: "#003366", color: "white", border: "none", padding: "9px 18px", borderRadius: "7px", fontWeight: 600, cursor: "pointer" }}>
                                {saving ? "Saving…" : "Save"}
                              </button>
                              <button style={smallBtn} onClick={() => setEditing(null)}>Cancel</button>
                            </div>
                            {editError && <p style={{ color: "#a4231a", fontSize: "13px", margin: "8px 0 0" }}>{editError}</p>}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p style={{ fontSize: "12px", color: "#64748b" }}>{filtered.length} exam row(s) shown{filtered.length !== exams.length ? ` of ${exams.length}` : ""}.</p>

      {/* ---------- manual add ---------- */}
      <div style={card}>
        <button style={{ ...smallBtn, marginBottom: showManual ? "12px" : 0 }} onClick={() => setShowManual(!showManual)}>
          {showManual ? "▾ Hide manual entry" : "▸ Add one exam by hand"}
        </button>
        {showManual && (
          <div>
            <select value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}>
              <option value="">-- Subject --</option>
              {ownedSubjects.map((s) => <option key={s.id} value={s.id}>{s.code} - {s.title}</option>)}
            </select>
            <select value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })}>
              <option value="">-- Section --</option>
              {sections.filter((s) => !programId || String(s.program) === String(programId))
                .map((s) => <option key={s.id} value={s.id}>{s.name} · {s.year_level} · {s.semester}</option>)}
            </select>
            <select value={form.proctor} onChange={(e) => setForm({ ...form, proctor: e.target.value })}>
              <option value="">-- Proctor --</option>
              {facultyList.map((f) => <option key={f.id} value={f.id}>{f.full_name && f.full_name !== f.username ? `${f.full_name} (${f.username})` : f.username}</option>)}
            </select>
            <RoomSelect rooms={rooms} value={form.room} onChange={(v) => setForm({ ...form, room: v })} autoLabel="-- Room --" width={170} />
            <input type="date" value={form.exam_date} onChange={(e) => setForm({ ...form, exam_date: e.target.value })} />
            <input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
            <input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
            <select value={form.exam_period} onChange={(e) => setForm({ ...form, exam_period: e.target.value })}>
              {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <button onClick={addExam}>Add Exam Slot</button>
            {form.exam_date && (
              <HistoricalHint day={weekdayOf(form.exam_date)} startTime={form.start_time} endTime={form.end_time}
                roomName={rooms.find((r) => String(r.id) === String(form.room))?.name} />
            )}
            {error && <p style={{ color: "red" }}>{error}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

export default ExamSchedulePanel;
