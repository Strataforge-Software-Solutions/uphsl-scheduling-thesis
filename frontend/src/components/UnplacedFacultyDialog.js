import React, { useEffect, useState } from "react";
import API from "../services/api";
import { notifyToast } from "../services/toast";
import TeacherPicker from "./TeacherPicker";
import AssignAnywayDialog, { OverrideBadge } from "./AssignAnywayDialog";
import { groupOptions, pickerExtras } from "../utils/facultyGroups";

/* "See other available faculty" for a class that was not placed. Nothing is assigned automatically:
   1. the three Professor groups for this class come from the server (POST /engine/unplaced/faculty-groups/);
   2. the Dean picks a person (someone not connected needs a confirmation with a reason);
   3. that person's free times are listed (POST /engine/slot-options/ with teacher_id), the Dean picks one and presses Place class.
   The server re-checks every rule when the class is placed. */
export default function UnplacedFacultyDialog({ cls, onClose, onPlaced }) {
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState("");
  const [teacher, setTeacher] = useState("");
  const [override, setOverride] = useState(null);       // {reason} when the chosen person is not connected
  const [ask, setAsk] = useState(null);                 // the not-connected option waiting for confirmation
  const [times, setTimes] = useState(null);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState("");
  const [done, setDone] = useState("");
  const base = { section_id: cls.section_id, subject_id: cls.subject_id };

  useEffect(() => {
    let live = true;
    API.post("/engine/unplaced/faculty-groups/", base)
      .then((r) => { if (live) setGroups(r.data); })
      .catch((e) => { if (live) setError(e.response?.data?.detail || "Could not load the faculty list."); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cls.section_id, cls.subject_id]);

  const request = (tid, ov) => ({ ...base, teacher_id: Number(tid), ...(ov ? { override_qualification: true, override_reason: ov.reason } : {}) });
  const loadTimes = async (tid, ov) => {
    setBusy("times"); setError(""); setTimes(null); setChoice("");
    try {
      const r = await API.post("/engine/slot-options/", { ...request(tid, ov), limit: 30 });
      setTimes([...(r.data.options || []), ...(r.data.outside_options || []), ...(r.data.room_options || [])]);
      if (!(r.data.options || []).length && !(r.data.outside_options || []).length && !(r.data.room_options || []).length) setError(r.data.reason || "No free time was found.");
    } catch (e) { setError(e.response?.data?.detail || "Could not look up free times."); }
    setBusy("");
  };
  const choose = (v, opt) => {
    if (opt && opt.notConnected) { setAsk(opt); return; }
    setTeacher(v); setOverride(null);
    if (v) loadTimes(v, null);
  };
  const place = async () => {
    setBusy("apply"); setError("");
    try {
      const r = await API.post("/engine/slot-options/apply/", { ...request(teacher, override), key: choice });
      setDone(r.data.summary || "The class was placed."); notifyToast(r.data.summary || "The class was placed.");
      if (onPlaced) onPlaced(r.data);
    } catch (e) {
      const message = e.response?.data?.detail || "Could not place the class.";
      setError(message); notifyToast(message, "error");
      if (e.response?.data?.refresh) loadTimes(teacher, override);
    }
    setBusy("");
  };
  const code = cls.code || String(cls.subject || "").split(" - ")[0];
  const title = cls.title || String(cls.subject || "").split(" - ").slice(1).join(" - ");

  return (
    <div role="dialog" aria-modal="true" aria-label={`Other available faculty for ${code}`}
      style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1200, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: "white", borderRadius: 6, width: "min(620px, 100%)", maxHeight: "88vh", overflow: "auto", padding: "16px 20px", boxShadow: "var(--shadow-pop)" }}>
        <h3 style={{ margin: "0 0 4px", fontSize: 16, color: "#111827" }}>Faculty for {code} {title}</h3>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "#4b5563" }}>Section {String(cls.section)}. Choose a person, then one of their free times. Nothing is placed until you press Place class.</p>
        {groups?.fixed_teacher && (
          <p style={{ fontSize: 13, color: "#92400e" }}>Its Lecture / Lab partner is taught by {groups.fixed_teacher}; both parts keep one teacher.</p>
        )}
        {groups && (
          <TeacherPicker ariaLabel={`Professor for ${code}`} value={teacher} onChange={choose} placeholder="-- Professor --"
            options={groupOptions(groups)} {...pickerExtras(groups)} disabled={!!busy || !!done} />
        )}
        {!groups && !error && <p style={{ fontSize: 13, color: "#6b7280" }}>Loading the faculty list…</p>}
        {override && <div style={{ marginTop: 6 }}><OverrideBadge reason={override.reason} /> <span style={{ fontSize: 12, color: "#4b5563" }}>Reason: {override.reason}</span></div>}
        {busy === "times" && <p style={{ fontSize: 13, color: "#6b7280" }}>Looking up free times…</p>}
        {times && times.length > 0 && !done && (
          <div role="radiogroup" aria-label="Free times" style={{ marginTop: 12, maxHeight: 240, overflowY: "auto", border: "1px solid #e5e7eb", borderRadius: 6, padding: 6 }}>
            {times.map((o) => (
              <label key={o.key} style={{ display: "flex", gap: 8, alignItems: "center", padding: "5px 6px", fontSize: 13, cursor: "pointer",
                background: choice === o.key ? "#eef4fb" : "white", borderRadius: 4 }}>
                <input type="radio" name="unplaced-time" checked={choice === o.key} onChange={() => setChoice(o.key)} />
                <span>{o.label} <span style={{ color: "#6b7280", fontSize: 12 }}>· {o.room}</span></span>
              </label>
            ))}
          </div>
        )}
        {error && <p role="alert" style={{ fontSize: 13, color: "#b91c1c", marginTop: 8 }}>{error}</p>}
        {done && <p role="status" style={{ fontSize: 13, color: "#166534", marginTop: 8 }}>{done}</p>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
          <button type="button" onClick={onClose} style={{ background: "white", color: "#374151", border: "1px solid #d1d5db", borderRadius: 4, padding: "6px 14px", fontSize: 13 }}>
            {done ? "Close" : "Cancel"}
          </button>
          {!done && (
            <button type="button" onClick={place} disabled={!choice || !!busy}
              style={{ background: "#003366", color: "white", border: "1px solid #003366", borderRadius: 4, padding: "6px 14px", fontSize: 13, fontWeight: 600 }}>
              {busy === "apply" ? "Placing…" : "Place class"}
            </button>
          )}
        </div>
      </div>
      {ask && (
        <AssignAnywayDialog person={ask.person} subjectCode={code} subjectTitle={title} onCancel={() => setAsk(null)}
          onConfirm={(reason) => { const ov = { reason }; setTeacher(String(ask.id)); setOverride(ov); setAsk(null); loadTimes(ask.id, ov); }} />
      )}
    </div>
  );
}
