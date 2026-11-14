import CustomSelect from "./CustomSelect";
import React, { useCallback, useEffect, useState } from "react";
import { notifyToast } from "../services/toast";
import TeacherPicker from "./TeacherPicker";
import AssignAnywayDialog, { OverrideBadge } from "./AssignAnywayDialog";
import { be, errText, cardStyle, Notice } from "./basicEdUi";
import { groupOptions, pickerExtras } from "../utils/facultyGroups";

/* SHS / JHS: pin a teacher to a subject of one section (TeachingAssignment). Anything not pinned is assigned by the engine.
   The teacher list comes from the server in three groups (basic_ed/teacher_groups.py). Choosing someone who is not connected to the
   subject (Principal only, and only when no qualified teacher is free) asks for a reason; the server checks everything again. */
export default function TeachingAssignmentsPanel({ level }) {
  const [sections, setSections] = useState([]);
  const [sectionId, setSectionId] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState("");
  const [ask, setAsk] = useState(null);               // {row, opt}: a not-connected pick waiting for the reason

  useEffect(() => {
    be.get(level, "sections/").then((r) => setSections((r.data || []).filter((s) => s.is_active !== false))).catch(() => setSections([]));
  }, [level]);
  const load = useCallback(() => {
    if (!sectionId) { setData(null); return; }
    setError("");
    be.get(level, "assignments/options/", { section: sectionId })
      .then((r) => setData(r.data)).catch((e) => { setData(null); setError(errText(e, "Could not load the subjects of this section.")); });
  }, [level, sectionId]);
  useEffect(() => { setMsg(null); load(); }, [load]);

  const save = async (row, facultyId, override) => {
    setBusy(String(row.subject_id)); setMsg(null);
    const extra = override ? { override_qualification: true, override_reason: override.reason } : {};
    try {
      if (row.pin) await be.patch(level, `assignments/${row.pin.id}/`, { faculty: Number(facultyId), ...extra });
      else await be.post(level, "assignments/", { faculty: Number(facultyId), section: Number(sectionId), subject: row.subject_id, ...extra });
      setMsg({ ok: true, text: `${row.code}: teacher pinned.` });
      notifyToast(`${row.code}: teacher pinned.`);
      load();
    } catch (e) { const message = errText(e, "Could not save the teacher."); setMsg({ ok: false, text: message }); notifyToast(message, "error"); }
    setBusy("");
  };
  const unpin = async (row) => {
    setBusy(String(row.subject_id)); setMsg(null);
    try { await be.del(level, `assignments/${row.pin.id}/`); const message = `${row.code}: pin removed. Generate will choose the teacher.`; setMsg({ ok: true, text: message }); notifyToast(message); load(); }
    catch (e) { const message = errText(e, "Could not remove the pin."); setMsg({ ok: false, text: message }); notifyToast(message, "error"); }
    setBusy("");
  };

  return (
    <div style={{ ...cardStyle, marginTop: 16 }}>
      <b>Teaching assignments</b>
      <p style={{ margin: "4px 0 10px", fontSize: 13, color: "#4b5563" }}>
        Pin a teacher to a subject of a section. Subjects without a pin get a qualified teacher when you generate the timetable.
      </p>
      <label style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>Section{" "}
        <CustomSelect value={sectionId} onChange={(e) => setSectionId(e.target.value)} style={{ fontSize: 14, padding: "5px 8px", marginLeft: 6 }}>
          <option value="">-- Choose a section --</option>
          {sections.map((s) => <option key={s.id} value={s.id}>{s.name} (Grade {s.grade_level})</option>)}
        </CustomSelect>
      </label>
      {error && <Notice tone="error">{error}</Notice>}
      {msg && <div role="status" style={{ marginTop: 8, fontSize: 13, color: msg.ok ? "#166534" : "#b91c1c" }}>{msg.text}</div>}
      {data && (
        <table style={{ marginTop: 12 }}>
          <thead><tr><th style={{ width: 110 }}>Code</th><th>Subject</th><th style={{ width: 90 }}>Periods / wk</th><th style={{ width: 300 }}>Teacher</th><th style={{ width: 90 }}></th></tr></thead>
          <tbody>
            {data.subjects.length === 0 && <tr><td colSpan={5} style={{ color: "#6b7280" }}>This section has no subjects in the curriculum.</td></tr>}
            {data.subjects.map((row) => (
              <tr key={row.subject_id}>
                <td>{row.code}</td>
                <td>{row.name}<div style={{ fontSize: 12, color: "#6b7280" }}>Needs: {row.needs || "any teacher"}</div></td>
                <td>{row.sessions_per_week}</td>
                <td>
                  <TeacherPicker compact ariaLabel={`Teacher for ${row.code}`} placeholder="-- Teacher (automatic) --"
                    value={row.pin ? String(row.pin.faculty) : ""} valueLabel={row.pin ? row.pin.faculty_name : ""}
                    disabled={busy === String(row.subject_id)}
                    options={groupOptions(row.groups, { currentId: row.pin?.faculty })} {...pickerExtras(row.groups)}
                    onChange={(v, opt) => { if (!v) return; if (opt && opt.notConnected) setAsk({ row, opt }); else save(row, v, null); }} />
                  {row.pin?.override && (
                    <div style={{ marginTop: 4, fontSize: 12, color: "#4b5563" }}><OverrideBadge text={row.pin.badge} reason={row.pin.override.reason} /> Reason: {row.pin.override.reason}</div>
                  )}
                </td>
                <td>{row.pin && <button type="button" onClick={() => unpin(row)} disabled={busy === String(row.subject_id)}
                  style={{ background: "white", color: "#374151", border: "1px solid #d1d5db", borderRadius: 4, padding: "3px 10px", fontSize: 12 }}>Remove pin</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ask && (
        <AssignAnywayDialog person={ask.opt.person} subjectCode={ask.row.code} subjectTitle={ask.row.name} roleWord="Principal"
          onCancel={() => setAsk(null)} onConfirm={(reason) => { const a = ask; setAsk(null); save(a.row, a.opt.id, { reason }); }} />
      )}
    </div>
  );
}
