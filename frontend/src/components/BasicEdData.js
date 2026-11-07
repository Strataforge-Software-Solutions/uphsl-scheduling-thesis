import React, { useState, useEffect, useCallback } from "react";
import { statusText } from "./BasicEdAvailability";
import API from "../services/api";
import { reportLoadError } from "../services/loadError";
import Badge from "./Badge";
import { periodOptionsAll, periodName } from "../utils/terms";
import { be, errText, inputStyle, cardStyle, btn, btnPrimary, Field, Modal, Notice, DAYS, hhmm } from "./basicEdUi";

/* ---------- generic form modal ---------- */
function FormModal({ title, fields, initial, onSave, onClose, saving, error }) {
  const [form, setForm] = useState(initial);
  return (
    <Modal title={title} onClose={onClose}>
      {error && <Notice tone="error">{error}</Notice>}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        {fields.map((f) => (
          <Field key={f.key} label={f.label} style={f.wide ? { gridColumn: "1 / -1" } : undefined}>
            {f.type === "select" ? (
              <select style={{ ...inputStyle, width: "100%" }} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                {f.options.map((o) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}
              </select>
            ) : f.type === "check" ? (
              <label style={{ fontSize: "13px" }}><input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} /> {f.hint || "Yes"}</label>
            ) : (
              <input style={{ ...inputStyle, width: "100%" }} type={f.type || "text"} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} placeholder={f.placeholder || ""} />
            )}
          </Field>
        ))}
      </div>
      <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "18px" }}>
        <button style={btn} onClick={onClose}>Cancel</button>
        <button style={btnPrimary} disabled={saving} onClick={() => onSave(form)}>{saving ? "Saving…" : "Save"}</button>
      </div>
    </Modal>
  );
}

function useList(level, path, params) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const key = JSON.stringify(params || {});
  const load = useCallback(() => {
    setLoading(true);
    be.get(level, path, params).then((r) => { setRows(r.data); setError(""); }).catch((e) => setError(errText(e))).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, path, key]);
  useEffect(() => { load(); }, [load]);
  return { rows, loading, error, load };
}

const TH = { textAlign: "left", fontSize: "12px", color: "#6b7280", padding: "8px 10px", borderBottom: "1px solid #e5e7eb" };
const TD = { padding: "9px 10px", borderBottom: "1px solid #f3f4f6", fontSize: "13px", verticalAlign: "top" };

function Table({ head, children, empty }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr>{head.map((h) => <th key={h} style={TH}>{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
      {empty && <p style={{ color: "#6b7280", fontSize: "13px", padding: "10px" }}>{empty}</p>}
    </div>
  );
}

/* ---------- Sections ---------- */
export function SectionsTab({ level, windows }) {
  const sections = useList(level, "sections/");
  const faculty = useList(level, "faculty/");
  const rooms = useList(level, "rooms/");
  const [strands, setStrands] = useState([]);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (level === "SHS") API.get("/basic-ed/strands/", { params: { level } }).then((r) => setStrands(r.data)).catch(reportLoadError("the strands")); }, [level]);

  const fields = [
    { key: "name", label: "Section name", placeholder: level === "SHS" ? "11-STEM-A" : "7-Rizal" },
    { key: "grade_level", label: "Grade level", type: "select", options: windows.map((w) => [w.grade_level, `Grade ${w.grade_level}`]) },
    ...(level === "SHS" ? [{ key: "strand", label: "Strand", type: "select", options: [["", "—"], ...strands.map((s) => [s.id, `${s.code} (${s.track === "ACADEMIC" ? "Academic" : "TechPro"})`])] }] : []),
    { key: "student_count", label: "Students", type: "number" },
    { key: "adviser", label: "Adviser", type: "select", options: [["", "—"], ...faculty.rows.map((f) => [f.id, f.full_name])] },
    { key: "home_room", label: "Home room", type: "select", options: [["", "—"], ...rooms.rows.filter((r) => r.room_type === "classroom").map((r) => [r.id, r.name])] },
    { key: "is_active", label: "Active", type: "check", hint: "Include in schedule generation" },
  ];
  const save = async (form) => {
    setSaving(true); setErr("");
    const body = { ...form, strand: form.strand || null, adviser: form.adviser || null, home_room: form.home_room || null, grade_level: Number(form.grade_level), student_count: Number(form.student_count) };
    try {
      if (form.id) await be.patch(level, `sections/${form.id}/`, body); else await be.post(level, "sections/", body);
      setEdit(null); sections.load();
    } catch (e) { setErr(errText(e)); } finally { setSaving(false); }
  };
  const remove = async (s) => {
    if (!window.confirm(`Remove section ${s.name}? Its schedule periods are removed too.`)) return;
    try { await be.del(level, `sections/${s.id}/`); sections.load(); } catch (e) { alert(errText(e)); }
  };
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "10px" }}>
        <b>{level === "SHS" ? "Grade 11 & 12 sections" : "Grade 7–10 sections"}</b>
        <button style={btnPrimary} onClick={() => { setErr(""); setEdit({ grade_level: windows[0]?.grade_level, student_count: level === "SHS" ? 35 : 40, is_active: true, strand: "", adviser: "", home_room: "" }); }}>Add section</button>
      </div>
      {sections.error && <Notice tone="error">{sections.error}</Notice>}
      <Table head={["Section", "Grade", ...(level === "SHS" ? ["Strand"] : []), "Students", "Adviser", "Home room", "Status", ""]} empty={!sections.loading && sections.rows.length === 0 ? "No sections yet." : ""}>
        {sections.rows.map((s) => (
          <tr key={s.id}>
            <td style={TD}><b>{s.name}</b></td><td style={TD}>{s.grade_level}</td>
            {level === "SHS" && <td style={TD}>{s.strand_code || "—"}</td>}
            <td style={TD}>{s.student_count}</td><td style={TD}>{s.adviser_name || "—"}</td><td style={TD}>{s.home_room_name || "—"}</td>
            <td style={TD}>{s.is_active ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>}</td>
            <td style={TD}><button style={btn} onClick={() => { setErr(""); setEdit({ ...s, strand: s.strand || "", adviser: s.adviser || "", home_room: s.home_room || "" }); }}>Edit</button>{" "}
              <button style={btn} onClick={() => remove(s)}>Remove</button></td>
          </tr>
        ))}
      </Table>
      {edit && <FormModal title={edit.id ? "Edit section" : "Add section"} fields={fields} initial={edit} onSave={save} onClose={() => setEdit(null)} saving={saving} error={err} />}
    </div>
  );
}

/* ---------- Rooms ---------- */
const ROOM_TYPES = [["classroom", "Classroom"], ["computer_lab", "Computer lab"], ["science_lab", "Science lab"], ["workshop", "TVL workshop"], ["gym", "Gym / court"]];
export function RoomsTab({ level, config }) {
  const rooms = useList(level, "rooms/");
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const fields = [
    { key: "room_number", label: "Room number / name" }, { key: "floor", label: "Floor", type: "number" },
    { key: "capacity", label: "Capacity", type: "number" }, { key: "room_type", label: "Type", type: "select", options: level === "JHS" ? ROOM_TYPES.slice(0, 1) : ROOM_TYPES },
    { key: "is_active", label: "Available", type: "check", hint: "Usable for scheduling" },
  ];
  const save = async (form) => {
    setSaving(true); setErr("");
    const body = { ...form, building: config.building, floor: Number(form.floor), capacity: Number(form.capacity) };
    try { if (form.id) await be.patch(level, `rooms/${form.id}/`, body); else await be.post(level, "rooms/", body); setEdit(null); rooms.load(); }
    catch (e) { setErr(errText(e)); } finally { setSaving(false); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete room ${r.name}?`)) return;
    try { await be.del(level, `rooms/${r.id}/`); rooms.load(); } catch (e) { alert(errText(e)); }
  };
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
        <b>{config.building}{config.floor != null ? ` — floor ${config.floor} (JHS classrooms only)` : ""}</b>
        <button style={btnPrimary} onClick={() => { setErr(""); setEdit({ floor: config.floor ?? 1, capacity: 40, room_type: "classroom", is_active: true }); }}>Add room</button>
      </div>
      <p style={{ color: "#6b7280", fontSize: "13px", marginTop: 0 }}>Rooms listed here belong to {level} only and are never used by the college schedule.</p>
      {rooms.error && <Notice tone="error">{rooms.error}</Notice>}
      <Table head={["Room", "Floor", "Type", "Capacity", "Status", ""]} empty={!rooms.loading && rooms.rows.length === 0 ? "No rooms yet." : ""}>
        {rooms.rows.map((r) => (
          <tr key={r.id}><td style={TD}><b>{r.name}</b></td><td style={TD}>{r.floor}</td><td style={TD}>{(r.room_type || "").replace("_", " ")}</td><td style={TD}>{r.capacity}</td>
            <td style={TD}>{r.is_active ? <Badge tone="success">Available</Badge> : <Badge>Closed</Badge>}</td>
            <td style={TD}><button style={btn} onClick={() => { setErr(""); setEdit({ ...r }); }}>Edit</button>{" "}<button style={btn} onClick={() => remove(r)}>Delete</button></td></tr>
        ))}
      </Table>
      {edit && <FormModal title={edit.id ? "Edit room" : "Add room"} fields={fields} initial={edit} onSave={save} onClose={() => setEdit(null)} saving={saving} error={err} />}
    </div>
  );
}

/* ---------- Faculty ---------- */
export function FacultyTab({ level }) {
  const faculty = useList(level, "faculty/");
  const [strands, setStrands] = useState([]);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => { if (level === "SHS") API.get("/basic-ed/strands/", { params: { level } }).then((r) => setStrands(r.data)).catch(reportLoadError("the strands")); }, [level]);
  const fields = [
    { key: "first_name", label: "First name" }, { key: "last_name", label: "Last name" },
    { key: "employee_id", label: "Employee ID" }, { key: "department", label: "Department / learning area" },
    ...(level === "SHS" ? [{ key: "strand", label: "Strand", type: "select", options: [["", "—"], ...strands.map((s) => [s.id, s.code])] }] : []),
    { key: "specializations", label: "Subject specializations (separate with ;)", wide: true, placeholder: "Mathematics; STEM" },
    { key: "qualifications", label: "Qualifications / eligibility", wide: true },
    { key: "max_weekly_hours", label: "Max teaching hours / week", type: "number" },
    { key: "preferred_start", label: "Preferred from (optional)", type: "time" }, { key: "preferred_end", label: "Preferred until (optional)", type: "time" },
    { key: "is_active", label: "Account status", type: "check", hint: "Active (can log in and be scheduled)" },
  ];
  const save = async (f) => {
    setSaving(true); setErr("");
    const body = { first_name: f.first_name, last_name: f.last_name, employee_id: f.employee_id, department: f.department || "", strand: f.strand || null,
      specializations: f.specializations || "", qualifications: f.qualifications || "", max_weekly_hours: Number(f.max_weekly_hours || 30),
      preferred_start: f.preferred_start || null, preferred_end: f.preferred_end || null, is_active: !!f.is_active, account_active: !!f.is_active };
    try { if (f.id) await be.patch(level, `faculty/${f.id}/`, body); else await be.post(level, "faculty/", body); setEdit(null); faculty.load(); }
    catch (e) { setErr(errText(e)); } finally { setSaving(false); }
  };
  const shown = faculty.rows.filter((f) => !q || `${f.full_name} ${f.employee_id} ${f.department} ${f.specializations}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", marginBottom: "10px", flexWrap: "wrap" }}>
        <b>{level} faculty directory</b>
        <div style={{ display: "flex", gap: "8px" }}>
          <input style={inputStyle} placeholder="Search name, ID, subject…" value={q} onChange={(e) => setQ(e.target.value)} />
          <button style={btnPrimary} onClick={() => { setErr(""); setEdit({ max_weekly_hours: 30, is_active: true, strand: "" }); }}>Add teacher</button>
        </div>
      </div>
      {faculty.error && <Notice tone="error">{faculty.error}</Notice>}
      <Table head={["Teacher", "ID", "Department", "Specializations", "Load", "Availability", "Status", ""]} empty={!faculty.loading && shown.length === 0 ? "No teachers found." : ""}>
        {shown.map((f) => (
          <tr key={f.id}>
            <td style={TD}><b>{f.full_name}</b><div style={{ fontSize: "12px", color: "#6b7280" }}>{f.qualifications}</div></td>
            <td style={TD}>{f.employee_id}</td><td style={TD}>{f.department || "—"}</td>
            <td style={TD}>{f.specializations || "—"}</td>
            <td style={TD}>{f.weekly_hours} / {f.max_weekly_hours} h</td>
            <td style={TD}>{statusText({ status: f.availability_status, submitted_at: f.availability_submitted_at })}</td>
            <td style={TD}>{f.is_active ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>}</td>
            <td style={TD}><button style={btn} onClick={() => { setErr(""); setEdit({ ...f, strand: f.strand || "" }); }}>Edit</button>{" "}
</td>
          </tr>
        ))}
      </Table>
      {edit && <FormModal title={edit.id ? "Edit teacher" : "Add teacher"} fields={fields} initial={edit} onSave={save} onClose={() => setEdit(null)} saving={saving} error={err} />}
    </div>
  );
}

/* (The old availability editor was removed: teachers submit availability themselves -- see BasicEdAvailability.js.) */

/* ---------- Curriculum ---------- */
const CATS = [["core", "Core"], ["applied", "Applied"], ["specialized", "Specialized"], ["elective", "Elective"], ["learning_area", "Learning area"], ["guidance", "Homeroom / guidance"]];
export function CurriculumTab({ level, windows, periodLabel, structure }) {
  const [grade, setGrade] = useState("");
  const [period, setPeriod] = useState("");
  const [strand, setStrand] = useState("");
  const curr = useList(level, "curriculum/", { grade: grade || undefined, period: period || undefined, strand: strand || undefined });
  const sources = useList(level, "curriculum-sources/");
  const [strands, setStrands] = useState([]);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [issues, setIssues] = useState(null);
  const [importMsg, setImportMsg] = useState(null);
  useEffect(() => { if (level === "SHS") API.get("/basic-ed/strands/", { params: { level } }).then((r) => setStrands(r.data)).catch(reportLoadError("the strands")); }, [level]);
  const periodOpts = periodOptionsAll(structure);       // Term 1-3 (JHS, Grade 11) / Semester 1-2 (Grade 12)
  const fields = [
    { key: "code", label: "Subject code" }, { key: "name", label: "Subject name / learning area" },
    { key: "grade_level", label: "Grade", type: "select", options: windows.map((w) => [w.grade_level, `Grade ${w.grade_level}`]) },
    { key: "grading_period", label: periodLabel, type: "select", options: [[0, "Whole school year"], ...periodOpts] },
    ...(level === "SHS" ? [{ key: "strand", label: "Strand (blank = all)", type: "select", options: [["", "All strands"], ...strands.map((s) => [s.id, s.code])] }] : []),
    { key: "category", label: "Classification", type: "select", options: CATS },
    { key: "learning_area", label: "Learning area" }, { key: "sessions_per_week", label: "Periods per week", type: "number" },
    { key: "total_hours", label: "Total hours (optional)", type: "number" },
    { key: "required_room_type", label: "Room needed", type: "select", options: [["classroom", "Classroom"], ["computer_lab", "Computer lab"], ["science_lab", "Science lab"], ["workshop", "Workshop"]] },
    { key: "specialization", label: "Teacher specialization (alternatives with |)", wide: true, placeholder: "English|Filipino" },
    { key: "prerequisite", label: "Prerequisite (if any)", wide: true },
    { key: "is_verified", label: "Verified", type: "check", hint: "Copied from an official DepEd document" },
    { key: "verification_note", label: "Source / note", wide: true },
  ];
  const save = async (f) => {
    setSaving(true); setErr("");
    const body = { ...f, strand: f.strand || null, grade_level: Number(f.grade_level), grading_period: Number(f.grading_period), sessions_per_week: Number(f.sessions_per_week),
      total_hours: f.total_hours === "" || f.total_hours == null ? null : Number(f.total_hours) };
    delete body.strand_code; delete body.source_title;
    try { if (f.id) await be.patch(level, `curriculum/${f.id}/`, body); else await be.post(level, "curriculum/", body); setEdit(null); curr.load(); }
    catch (e) { setErr(errText(e)); } finally { setSaving(false); }
  };
  const retire = async (s) => {
    if (!window.confirm(`Retire ${s.code}? Schedules already made keep it; new schedules won't use it.`)) return;
    try { await be.del(level, `curriculum/${s.id}/`); curr.load(); } catch (e) { alert(errText(e)); }
  };
  const validate = async () => {
    try { const r = await be.get(level, "curriculum-tools/validate/", { period: period || 1, grade: grade || undefined }); setIssues(r.data); }
    catch (e) { setIssues({ issues: [{ severity: "error", message: errText(e) }], errors: 1, warnings: 0 }); }
  };
  const doImport = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file); fd.append("level", level);
    try { const r = await API.post("/basic-ed/curriculum-tools/import/", fd, { params: { level } }); setImportMsg({ tone: "ok", text: `Imported ${r.data.imported} new, updated ${r.data.updated}. Imported lines start as unverified.` }); curr.load(); sources.load(); }
    catch (e) { const d = e.response?.data; setImportMsg({ tone: "error", text: d?.errors ? "Nothing was imported. " + d.errors.slice(0, 6).map((x) => `Row ${x.row}: ${x.message}`).join(" · ") : errText(e) }); }
  };
  const downloadTemplate = async () => {
    const r = await API.get("/basic-ed/curriculum-tools/template/", { params: { level }, responseType: "blob" });
    const url = window.URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = `${level}_curriculum_template.csv`; a.click();
    setTimeout(() => window.URL.revokeObjectURL(url), 5000);
  };
  const unverified = curr.rows.filter((r) => !r.is_verified).length;
  return (
    <div>
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", flexWrap: "wrap", marginBottom: "10px" }}>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <select style={inputStyle} value={grade} onChange={(e) => setGrade(e.target.value)}><option value="">All grades</option>{windows.map((w) => <option key={w.grade_level} value={w.grade_level}>Grade {w.grade_level}</option>)}</select>
            <select style={inputStyle} value={period} onChange={(e) => setPeriod(e.target.value)}><option value="">All terms / semesters</option>{periodOpts.map(([n, l]) => <option key={n} value={n}>{l}</option>)}</select>
            {level === "SHS" && <select style={inputStyle} value={strand} onChange={(e) => setStrand(e.target.value)}><option value="">All strands</option>{strands.map((s) => <option key={s.id} value={s.code}>{s.code}</option>)}</select>}
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button style={btn} onClick={validate}>Validate curriculum</button>
            <button style={btn} onClick={downloadTemplate}>Import template</button>
            <label style={{ ...btn, display: "inline-block" }}>Import file<input type="file" accept=".csv,.xlsx" style={{ display: "none" }} onChange={(e) => { doImport(e.target.files[0]); e.target.value = ""; }} /></label>
            <button style={btnPrimary} onClick={() => { setErr(""); setEdit({ grade_level: windows[0]?.grade_level, grading_period: 0, category: level === "SHS" ? "core" : "learning_area", sessions_per_week: 4, required_room_type: "classroom", strand: "", is_verified: false }); }}>Add subject</button>
          </div>
        </div>
        {importMsg && <Notice tone={importMsg.tone}>{importMsg.text}</Notice>}
        {issues && (
          <Notice tone={issues.errors ? "error" : issues.warnings ? "warn" : "ok"}>
            <b>{issues.errors} error(s), {issues.warnings} warning(s)</b>{!issues.issues.length && " — curriculum is complete and consistent."}
            <ul style={{ margin: "6px 0 0", paddingLeft: "18px", maxHeight: "180px", overflowY: "auto" }}>
              {issues.issues.slice(0, 60).map((i, k) => <li key={k}><strong style={{ fontWeight: 600 }}>{i.severity === "error" ? "Error:" : "Warning:"}</strong> {i.message}</li>)}
            </ul>
          </Notice>
        )}
        {unverified > 0 && <Notice tone="warn">{unverified} line(s) shown are marked <b>unverified</b> — DepEd does not publish them in a form that could be checked (elective names, Grade 12, some Grade 7–10 details). Review and edit them before relying on the schedule.</Notice>}
        {curr.error && <Notice tone="error">{curr.error}</Notice>}
        <Table head={["Code", "Subject", "Gr.", periodLabel, ...(level === "SHS" ? ["Strand"] : []), "Type", "Periods/wk", "Hours", "Specialization", "Source", ""]} empty={!curr.loading && curr.rows.length === 0 ? "No curriculum records. Import a file or add subjects." : ""}>
          {curr.rows.map((s) => (
            <tr key={s.id}>
              <td style={TD}>{s.code}</td><td style={TD}>{s.name}</td><td style={TD}>{s.grade_level}</td>
              <td style={TD}>{s.grading_period === 0 ? "Whole year" : periodName(structure, s.grade_level, s.grading_period)}</td>
              {level === "SHS" && <td style={TD}>{s.strand_code || "All"}</td>}
              <td style={TD}>{s.category}</td><td style={TD}>{s.sessions_per_week}</td><td style={TD}>{s.total_hours ?? "—"}</td>
              <td style={TD}>{s.specialization || s.learning_area || "—"}</td>
              <td style={TD}>{s.is_verified ? <Badge tone="success">Verified</Badge> : <span title={s.verification_note}><Badge tone="warning">Unverified</Badge></span>}</td>
              <td style={TD}><button style={btn} onClick={() => { setErr(""); setEdit({ ...s, strand: s.strand || "", total_hours: s.total_hours ?? "" }); }}>Edit</button>{" "}<button style={btn} onClick={() => retire(s)}>Retire</button></td>
            </tr>
          ))}
        </Table>
      </div>
      <div style={cardStyle}>
        <b>Curriculum sources</b>
        <Table head={["Source", "Reference", "Version", "Status", "Lines"]}>
          {sources.rows.map((s) => (
            <tr key={s.id}><td style={TD}>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : s.title}</td><td style={TD}>{s.reference}</td><td style={TD}>{s.version || "—"}</td>
              <td style={TD}>{s.is_verified ? <Badge tone="success">Official</Badge> : <Badge tone="warning">Needs review</Badge>}</td><td style={TD}>{s.subject_count}</td></tr>
          ))}
        </Table>
      </div>
      {edit && <FormModal title={edit.id ? "Edit curriculum line" : "Add curriculum line"} fields={fields} initial={edit} onSave={save} onClose={() => setEdit(null)} saving={saving} error={err} />}
    </div>
  );
}
