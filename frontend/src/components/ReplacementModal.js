import React, { useEffect, useState } from "react";
import API from "../services/api";

/* Dean / Registrar: a teacher is leaving or unavailable. For each of their classes, show qualified
   replacements ranked by degree / specialization / qualifications, with availability and workload,
   and let the Dean choose one. */
const chip = { fontSize: "11.5px", background: "#eef4fb", color: "#003366", borderRadius: "999px", padding: "2px 8px" };

export default function ReplacementModal({ faculty, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [overload, setOverload] = useState(null);

  const load = () => API.get("/engine/replacements/teacher/", { params: { faculty_id: faculty.faculty_id || faculty.id } })
    .then((r) => setData(r.data)).catch((e) => setError(e.response?.data?.detail || "Could not load replacements."));
  // load once when the window opens (load is re-created every render)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const assign = async (cls, cand, override = false) => {
    const key = `${cls.schedule_ids[0]}-${cand.faculty_id}`;
    setBusyKey(key); setError(""); setOverload(null);
    try {
      await API.post("/engine/replacements/assign/", { schedule_ids: cls.schedule_ids, teacher: cand.faculty_id, override_workload: override });
      await load(); onChanged?.();
    } catch (e) {
      const d = e.response?.data;
      if (e.response?.status === 409 && d?.workload_overload) setOverload({ cls, cand, d });
      else setError(d?.detail || "Could not reassign the class.");
    } finally { setBusyKey(""); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "12px" }}>
      <div style={{ background: "white", borderRadius: "12px", padding: "22px 24px", width: "820px", maxWidth: "100%", maxHeight: "92vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h3 style={{ margin: 0, color: "#003366" }}>Find replacement{data ? ` for ${data.faculty.full_name}` : ""}</h3>
            <p style={{ margin: "4px 0 0", fontSize: "12.5px", color: "#64748b" }}>
              Ranked by degree, specialization and qualifications, then availability and remaining workload.
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" style={{ border: "none", background: "none", fontSize: "18px", cursor: "pointer", color: "#64748b" }}>Close</button>
        </div>
        {error && <p style={{ color: "#a4231a", fontSize: "13px" }}>{error}</p>}
        {!data && !error && <p style={{ color: "#64748b" }}>Loading…</p>}
        {data && data.classes.length === 0 && <p style={{ color: "#64748b", marginTop: "16px" }}>This teacher has no classes you can reassign.</p>}
        {data && data.classes.map((cls) => (
          <div key={cls.schedule_ids.join("-")} style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "12px 14px", marginTop: "14px" }}>
            <div style={{ fontWeight: 700 }}>{cls.code ? `${cls.code} — ` : ""}{cls.subject} <span style={{ fontWeight: 400, color: "#64748b" }}>· {cls.section}</span></div>
            <div style={{ fontSize: "12.5px", color: "#64748b", marginTop: "2px" }}>
              {cls.when} · {cls.hours} h/week{cls.required_field ? ` · Field: ${cls.required_field}` : ""}
            </div>
            {cls.suggestions.length === 0 ? (
              <p style={{ fontSize: "13px", color: "#a4231a", margin: "10px 0 0" }}>{cls.reason_none || "No qualified faculty is free for this class. Check availability submissions or the workload limits."}</p>
            ) : cls.suggestions.map((c, i) => (
              <div key={c.faculty_id} style={{ display: "flex", gap: "12px", justifyContent: "space-between", alignItems: "flex-start", padding: "10px 0", borderTop: i ? "1px solid #f1f5f9" : "none", marginTop: i ? 0 : "10px" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>
                    {i === 0 && <span style={{ ...chip, background: "#e6f6ec", color: "#1e5f3a", marginRight: "6px" }}>Best match</span>}
                    {c.full_name} <span style={{ fontWeight: 400, color: "#64748b", fontSize: "12.5px" }}>{c.school_id} · {c.faculty_type === "part_time" ? "Part-time" : "Full-time"} · {c.department}</span>
                  </div>
                  <div style={{ fontSize: "12.5px", color: "#334155", marginTop: "3px" }}>
                    {c.degree ? <>Degree: {c.degree}</> : <span style={{ color: "#94a3b8" }}>No degree on file</span>}
                    {c.specializations.length > 0 && <> · Specialization: {c.specializations.join(", ")}</>}
                  </div>
                  {c.qualifications && <div style={{ fontSize: "12px", color: "#64748b", marginTop: "2px" }}>Qualifications: {c.qualifications}</div>}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginTop: "6px" }}>
                    {c.reasons.map((r) => <span key={r} style={chip}>{r}</span>)}
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b", marginTop: "5px" }}>
                    Load now {c.current_hours} / {c.max_hours} h per week{c.email ? ` · ${c.email}` : ""}
                  </div>
                </div>
                <button onClick={() => assign(cls, c)} disabled={!!busyKey}
                        style={{ background: "#003366", color: "white", border: "none", padding: "8px 14px", borderRadius: "6px", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
                  {busyKey === `${cls.schedule_ids[0]}-${c.faculty_id}` ? "Assigning…" : "Assign"}
                </button>
              </div>
            ))}
          </div>
        ))}
      </div>
      {overload && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: "12px" }}>
          <div role="alertdialog" style={{ background: "white", borderRadius: "12px", padding: "22px", width: "460px", maxWidth: "100%", borderTop: "5px solid #d97706" }}>
            <h3 style={{ margin: 0, color: "#92400e" }}>Workload warning</h3>
            <p style={{ fontSize: "13.5px" }}>{overload.d.detail}</p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button onClick={() => setOverload(null)} style={{ background: "white", color: "#1f2937", border: "1px solid #cdd6e0", padding: "8px 16px", borderRadius: "6px", cursor: "pointer" }}>Choose someone else</button>
              {overload.d.can_override && (
                <button onClick={() => assign(overload.cls, overload.cand, true)} style={{ background: "#b45309", color: "white", border: "none", padding: "8px 16px", borderRadius: "6px", fontWeight: 600, cursor: "pointer" }}>Assign anyway</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
