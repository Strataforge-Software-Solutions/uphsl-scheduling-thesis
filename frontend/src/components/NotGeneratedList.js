import React, { useEffect, useState } from "react";
import API from "../services/api";

/* Plain information: the classes of a program (and year level / semester) that still do not have all their hours, with the
   reason recorded the last time they could not be placed. Read-only (GET /engine/unplaced/). Nothing here changes the schedule;
   the optional onRetry button is the Dean's / Registrar's own "Generate only the missing ones". */
const SEMS = ["1st Sem", "2nd Sem"];

export default function NotGeneratedList({ programId, yearLevel = "", semester = "", refreshKey = 0, onRetry = null, retrying = false }) {
  const [items, setItems] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!programId) { setItems(null); return undefined; }
    let gone = false;
    const sems = semester ? [semester] : SEMS;
    Promise.all(sems.map((sem) => API.get("/engine/unplaced/", { params: { semester: sem, program_id: programId, year_level: yearLevel || undefined } })
      .then((r) => (r.data.items || []).map((x) => ({ ...x, semester: sem }))).catch(() => [])))
      .then((lists) => { if (!gone) setItems(lists.flat()); });
    return () => { gone = true; };
  }, [programId, yearLevel, semester, refreshKey]);

  if (!items || items.length === 0) return null;
  const notYet = items.filter((x) => x.placed_minutes === 0 && x.reason === "Not generated yet.").length;
  const withReason = items.length - notYet;
  return (
    <div style={{ margin: "12px 0", border: "1px solid #f0d58a", background: "#fffbeb", borderRadius: 8, fontSize: 13, color: "#1e293b" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between", padding: "8px 12px" }}>
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
          style={{ background: "none", border: "none", color: "#7a4b00", padding: 0, fontWeight: 600, fontSize: 13, cursor: "pointer", textAlign: "left", boxShadow: "none" }}>
          {open ? "▾" : "▸"} {items.length} class{items.length === 1 ? "" : "es"} not generated yet
          {withReason > 0 && ` (${withReason} could not be placed)`}
        </button>
        {onRetry && (
          <button type="button" onClick={onRetry} disabled={retrying}
            style={{ background: "#003366", color: "white", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12.5, cursor: retrying ? "not-allowed" : "pointer" }}>
            {retrying ? "Generating…" : "Generate only the missing ones"}
          </button>
        )}
      </div>
      {open && (
        <div style={{ maxHeight: 260, overflow: "auto", borderTop: "1px solid #f3e3ad" }}>
          <table style={{ margin: 0, boxShadow: "none", border: "none", borderRadius: 0, width: "100%", minWidth: 640, fontSize: 12.5 }}>
            <thead><tr><th style={{ width: 90 }}>Code</th><th>Subject</th><th style={{ width: 90 }}>Section</th><th style={{ width: 120 }}>Year / Sem</th><th>Why</th></tr></thead>
            <tbody>
              {items.map((x) => (
                <tr key={`${x.semester}-${x.section_id}-${x.subject_id}`}>
                  <td>{x.code}</td><td>{x.title}</td><td>{x.section_name}</td><td>{x.year_level}, {x.semester}</td>
                  <td style={{ color: x.reason === "Not generated yet." ? "#64748b" : "#a4231a" }}>{x.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
