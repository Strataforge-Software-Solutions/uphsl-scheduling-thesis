import React, { useEffect, useState } from "react";
import ModalPortal from "./ModalPortal";
import API from "../services/api";

/* Choose how one minor (Gen Ed) subject is held before generating: Automatic, exclusive to this program, or shared by 2 or 3 programs.
   The choice is checked on the server (same code, title and units; same year level and semester; enough seats; a qualified teacher)
   and is only used by the generator after it is confirmed. Sections, students and the curriculum are never changed. */
const NAVY = "#003366";
const btn = (bg, fg = "#fff") => ({ background: bg, color: fg, border: bg === "#fff" ? `1px solid ${NAVY}` : "none", borderRadius: 6, padding: "7px 16px", fontSize: 13, cursor: "pointer" });

export function sharedLabel(item) {
  if (!item) return "";
  if (item.mode === "exclusive") return "Exclusive";
  if (item.mode === "shared") return `${item.group.confirmed ? "Shared" : "Shared (awaiting Registrar)"}: ${item.group.programs.map((p) => p.name).join(" + ")}`;
  return item.shareable ? "Automatic" : "Own class (lab)";
}

export default function SharedClassModal({ item, program, onClose, onChanged }) {
  const [mode, setMode] = useState(item.mode === "auto" ? "auto" : item.mode);
  const initial = item.group ? item.group.programs.filter((p) => p.id !== program.id).map((p) => p.id) : [];
  const [chosen, setChosen] = useState(initial);
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    setCheck(null);
    if (mode !== "shared" || chosen.length < 1) return undefined;
    let live = true;
    API.post("/engine/shared-classes/validate/", { subject_id: item.subject_id, program_ids: chosen })
      .then((r) => { if (live) setCheck(r.data); })
      .catch((e) => { if (live) setCheck({ ok: false, errors: [e.response?.data?.detail || "Could not check this choice."], warnings: [], programs: [] }); });
    return () => { live = false; };
  }, [mode, chosen, item.subject_id]);

  const toggle = (id) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 2 ? c : [...c, id]));
  const act = async (path, body, msg) => {
    setBusy(true); setError(""); setNote("");
    try {
      const r = await API.post(`/engine/shared-classes/${path}/`, body);
      setNote(r.data.message || msg);
      if (onChanged) await onChanged();
      return r.data;
    } catch (e) { setError(e.response?.data?.detail || "Could not save."); return null; } finally { setBusy(false); }
  };
  const save = async () => {
    if (mode === "auto") return act("clear", { subject_id: item.subject_id }, "Back to automatic.");
    if (mode === "exclusive") return act("exclusive", { subject_id: item.subject_id }, "Kept exclusive to this program.");
    return act("save", { subject_id: item.subject_id, program_ids: chosen }, "Shared class confirmed.");
  };

  return (
    <ModalPortal><div role="dialog" aria-modal="true" aria-label="Shared class" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: 14 }}>
      <div style={{ background: "#fff", borderRadius: 6, width: "100%", maxWidth: 680, maxHeight: "90vh", display: "flex", flexDirection: "column", boxShadow: "var(--shadow-pop)" }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
          <div>
            <h3 style={{ margin: 0, color: NAVY }}>Shared class — {item.code}</h3>
            <div style={{ fontSize: 13, color: "#4b5563" }}>{item.title} · {item.lec_units} lec / {item.lab_units} lab units · {program.name}, {program.year_level}, {program.semester}</div>
          </div>
          <button onClick={onClose} style={btn("#fff", NAVY)}>Close</button>
        </div>
        <div style={{ padding: "14px 18px", overflowY: "auto", fontSize: 14 }}>
          {!item.shareable ? <p>{item.why_not}</p> : (
            <>
              {[["auto", "Automatic", "The generator may join an equal class of another program when it fits (the original behaviour)."],
                ["exclusive", `Exclusive to ${program.name}`, "This program always keeps its own class for this subject."],
                ["shared", "Shared with other programs", "Choose 1 or 2 other programs (2 or 3 programs in total) that attend ONE class."]].map(([v, t, d]) => (
                <label key={v} style={{ display: "block", border: `1px solid ${mode === v ? NAVY : "#e5e7eb"}`, background: mode === v ? "#e6f0fa" : "#fff", borderRadius: 6, padding: "8px 12px", marginBottom: 8, cursor: "pointer" }}>
                  <input type="radio" name="mode" checked={mode === v} onChange={() => setMode(v)} style={{ marginRight: 8 }} />
                  <strong>{t}</strong><div style={{ color: "#6b7280", fontSize: 13, marginLeft: 24 }}>{d}</div>
                </label>
              ))}
              {mode === "shared" && (
                <div style={{ margin: "6px 0 10px" }}>
                  {!item.candidates.length && <p style={{ color: "#b91c1c" }}>No other program has this same subject (same code, title and units) in {program.year_level}, {program.semester}, so it cannot be shared.</p>}
                  {item.candidates.map((c) => (
                    <label key={c.id} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "6px 8px", borderBottom: "1px solid #f3f4f6", cursor: "pointer" }}>
                      <input type="checkbox" checked={chosen.includes(c.id)} disabled={!chosen.includes(c.id) && chosen.length >= 2} onChange={() => toggle(c.id)} />
                      <span><strong>{c.name}</strong> — {c.department}<br /><span style={{ color: "#6b7280", fontSize: 13 }}>{c.year_level} · {c.semester} · {c.sections} section(s) · {c.students} students</span></span>
                    </label>
                  ))}
                  {check && (
                    <div style={{ marginTop: 10, border: `1px solid ${check.ok ? "#a7f3d0" : "#fecaca"}`, background: check.ok ? "#ecfdf5" : "#fef2f2", borderRadius: 6, padding: "10px 12px" }}>
                      <strong style={{ color: check.ok ? "#166534" : "#991b1b" }}>{check.ok ? "These programs can share this class" : "They cannot share this class"}</strong>
                      {check.programs?.length > 0 && (
                        <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                          {check.programs.map((p) => <li key={p.id}>{p.name} ({p.department}) — {p.year_level}, {p.semester}: {p.students} students in {p.sections} section(s)</li>)}
                        </ul>
                      )}
                      {check.ok && <div style={{ marginTop: 4 }}>Combined enrolment {check.total_students} · largest room they may use seats {check.capacity} · {check.shared_classes} shared class(es) will form.</div>}
                      {(check.errors || []).map((m, i) => <div key={i} style={{ color: "#991b1b", marginTop: 4 }}>{m}</div>)}
                      {(check.warnings || []).map((m, i) => <div key={i} style={{ color: "#7a4b00", marginTop: 4 }}>{m}</div>)}
                    </div>
                  )}
                  {item.group && !item.group.confirmed && <p style={{ color: "#7a4b00" }}>This shared class includes another college's program. It is saved, but the Registrar has to confirm it before the generator uses it.</p>}
                </div>
              )}
            </>
          )}
          {note && <p style={{ color: "#166534" }}>{note}</p>}
          {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
        </div>
        {item.shareable && (
          <div style={{ padding: "12px 18px", borderTop: "1px solid #e5e7eb", display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
            {item.group && !item.group.confirmed && (
              <button disabled={busy} onClick={() => act("confirm", { group_id: item.group.id }, "Confirmed.")} style={btn("#0b6b3a")}>Confirm (Registrar)</button>
            )}
            <button onClick={save} disabled={busy || (mode === "shared" && !(check && check.ok))} style={{ ...btn(NAVY), opacity: busy || (mode === "shared" && !(check && check.ok)) ? 0.5 : 1 }}>
              {mode === "shared" ? "Review and confirm shared class" : "Save choice"}
            </button>
          </div>
        )}
      </div>
    </div></ModalPortal>
  );
}
