import React, { useEffect, useState } from "react";
import API from "../services/api";

/* Dean / Registrar: a teacher is leaving or unavailable. For each of their classes, show qualified
   replacements ranked by degree / specialization / qualifications, with availability and workload,
   and let the Dean choose one. */
const chip = { fontSize: "12px", background: "var(--replacement-chip-bg, #eef4fb)", color: "var(--replacement-chip-fg, #174a80)", borderRadius: 999, padding: "4px 9px" };
const replacementPreloads = new Map();

const replacementFacultyId = (faculty) => faculty?.faculty_id || faculty?.id;

export function prefetchReplacementData(facultyId, force = false) {
  const id = String(facultyId || "");
  if (!id) return Promise.resolve(null);
  const cached = replacementPreloads.get(id);
  if (!force && cached && (cached.expiresAt > Date.now() || cached.promise)) return cached.promise || Promise.resolve(cached.data);

  const promise = API.get("/engine/replacements/teacher/", { params: { faculty_id: id } })
    .then((response) => {
      const data = response.data;
      replacementPreloads.set(id, { data, expiresAt: Date.now() + 30_000 });
      return data;
    })
    .catch(() => {
      replacementPreloads.delete(id);
      return null;
    });
  replacementPreloads.set(id, { promise, expiresAt: 0 });
  return promise;
}

const cachedReplacementData = (facultyId) => {
  const entry = replacementPreloads.get(String(facultyId || ""));
  return entry?.expiresAt > Date.now() ? entry.data : null;
};

export default function ReplacementModal({ faculty, onClose, onChanged }) {
  const facultyId = replacementFacultyId(faculty);
  const [data, setData] = useState(() => cachedReplacementData(facultyId));
  const [error, setError] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const [overload, setOverload] = useState(null);

  const load = async (force = false) => {
    setError("");
    const result = await prefetchReplacementData(facultyId, force);
    if (result) setData(result);
    else setError("Could not load replacements. Please try again.");
  };
  // `load` is intentionally recreated, while this request should only initialize for the selected faculty.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!cachedReplacementData(facultyId)) load(); }, [facultyId]);

  const assign = async (cls, cand, override = false) => {
    const key = `${cls.schedule_ids[0]}-${cand.faculty_id}`;
    setBusyKey(key); setError(""); setOverload(null);
    try {
      await API.post("/engine/replacements/assign/", { schedule_ids: cls.schedule_ids, teacher: cand.faculty_id, override_workload: override });
      await load(true); onChanged?.();
    } catch (e) {
      const d = e.response?.data;
      if (e.response?.status === 409 && d?.workload_overload) setOverload({ cls, cand, d });
      else setError(d?.detail || "Could not reassign the class.");
    } finally { setBusyKey(""); }
  };

  return (
    <div className="replacement-modal-backdrop">
      <section className="replacement-modal" role="dialog" aria-modal="true" aria-labelledby="replacement-modal-title">
        <header className="replacement-modal-header">
          <div>
            <div className="replacement-modal-eyebrow">FACULTY COVERAGE</div>
            <h2 id="replacement-modal-title">Find a replacement</h2>
            <p>{data ? `Classes assigned to ${data.faculty.full_name}` : "Review available faculty for this teacher’s classes."}</p>
          </div>
          <button className="replacement-close" onClick={onClose} aria-label="Close replacement dialog">×</button>
        </header>
        <div className="replacement-modal-body">
          {error && <div className="replacement-message is-error" role="alert">{error}</div>}
          {!data && !error && <div className="replacement-message">Loading qualified replacement options…</div>}
          {data && data.classes.length === 0 && <div className="replacement-message">This teacher has no classes you can reassign.</div>}
          {data?.classes.map((cls) => (
            <article className="replacement-class-card" key={cls.schedule_ids.join("-")}>
              <div className="replacement-class-heading">
                <div className="replacement-class-title">
                  <span className="replacement-subject-code">{cls.code || "Class"}</span>
                  <h3>{cls.subject}</h3>
                </div>
                <span className="replacement-section">{cls.section}</span>
              </div>
              <div className="replacement-class-meta">
                <span>{cls.when}</span><span>{cls.hours} h/week</span>
                {cls.required_field && <span>{cls.required_field}</span>}
              </div>
              {cls.suggestions.length === 0 ? (
                <div className="replacement-message is-empty">{cls.reason_none || "No qualified faculty is currently free for this class."}</div>
              ) : (
                <div className="replacement-candidate-list">
                  {cls.suggestions.map((c, i) => {
                    const loadPct = Math.min(100, Math.max(0, (Number(c.current_hours || 0) / Math.max(Number(c.max_hours || 0), 1)) * 100));
                    return (
                      <div className="replacement-candidate" key={c.faculty_id}>
                        <div className="replacement-candidate-main">
                          <div className="replacement-candidate-name-row">
                            <h4>{c.full_name}</h4>
                            {i === 0 && <span className="replacement-best-match">Best match</span>}
                          </div>
                          <div className="replacement-candidate-identity">
                            {[c.school_id, c.faculty_type === "part_time" ? "Part-time" : "Full-time", c.department].filter(Boolean).join(" · ")}
                          </div>
                          <div className="replacement-candidate-credentials">
                            {c.degree || "No degree on file"}
                            {c.specializations?.length > 0 && <> <span aria-hidden="true">·</span> {c.specializations.join(", ")}</>}
                            {c.qualifications && <> <span aria-hidden="true">·</span> {c.qualifications}</>}
                          </div>
                          <div className="replacement-reason-list">
                            {c.reasons.map((reason) => <span key={reason} style={chip}>{reason}</span>)}
                          </div>
                          <div className="replacement-workload">
                            <div className="replacement-workload-label"><span>Weekly workload</span><strong>{c.current_hours} / {c.max_hours} h</strong></div>
                            <div className="replacement-workload-track"><span className="motion-meter-fill" style={{ width: `${loadPct}%` }} /></div>
                          </div>
                        </div>
                        <button className="replacement-assign" onClick={() => assign(cls, c)} disabled={!!busyKey}>
                          {busyKey === `${cls.schedule_ids[0]}-${c.faculty_id}` ? "Assigning…" : "Assign"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
      {overload && (
        <div className="replacement-warning-backdrop">
          <div className="replacement-warning" role="alertdialog" aria-labelledby="replacement-warning-title">
            <h3 id="replacement-warning-title">Workload limit warning</h3>
            <p>{overload.d.detail}</p>
            <div className="replacement-warning-actions">
              <button className="replacement-close-action" onClick={() => setOverload(null)}>Choose someone else</button>
              {overload.d.can_override && <button className="replacement-override" onClick={() => assign(overload.cls, overload.cand, true)}>Assign anyway</button>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
