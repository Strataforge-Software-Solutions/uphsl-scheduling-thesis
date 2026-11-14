import React, { useState } from "react";
import API from "../services/api";
import { notifyToast } from "../services/toast";

/* Classes the generator could not place, with a Resolve button per class and "Resolve all".
   Resolve re-arranges the few classes that are in the way (another room, teacher or time) with every scheduling rule kept,
   and only reports "placed" after the saved schedule was checked again for clashes. Nothing here asks anyone to add rooms or staff. */
export default function UnplacedResolve({ items, semester, schoolYear, onDone, title }) {
  const [busy, setBusy] = useState("");
  const [done, setDone] = useState({});      // "sectionId-subjectId" -> result
  const [error, setError] = useState("");
  const keyOf = (c) => `${c.section_id}-${c.subject_id}`;
  const seen = new Set();
  const list = (items || []).filter((c) => {
    if (c.section_id == null || seen.has(keyOf(c))) return false;
    seen.add(keyOf(c));
    return true;
  });
  const open = list.filter((c) => done[keyOf(c)]?.status !== "placed");

  const run = async (scope, label) => {
    setBusy(label); setError("");
    try {
      const res = await API.post("/engine/unplaced/resolve/",
        { semester, school_year: schoolYear || "", ...scope }, { timeout: 900000 });
      const next = { ...done };
      (res.data.results || []).forEach((r) => { next[`${r.section_id}-${r.subject_id}`] = r; });
      setDone(next);
      notifyToast("Schedule placement suggestions applied.");
      if (onDone) onDone(res.data);
    } catch (e) {
      const message = e.response?.data?.detail || "Could not place the class. Please try again.";
      setError(message); notifyToast(message, "error");
    } finally { setBusy(""); }
  };

  if (!list.length) return null;
  return (
    <div style={{ marginTop: "10px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h4 style={{ margin: 0 }}>{title || "Classes not placed"} ({open.length} left)</h4>
        {open.length > 1 && (
          <button disabled={!!busy} onClick={() => run({}, "all")}
            style={{ background: "#003366", color: "#fff", border: "none", borderRadius: "6px", padding: "6px 12px", cursor: busy ? "wait" : "pointer" }}>
            {busy === "all" ? "Resolving… this can take a minute" : "Resolve all"}
          </button>
        )}
      </div>
      {error && <p style={{ color: "#b91c1c", fontSize: "13px" }}>{error}</p>}
      <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
        {list.map((c) => {
          const r = done[keyOf(c)];
          const placed = r?.status === "placed";
          return (
            <li key={keyOf(c)} style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "10px 12px", marginBottom: "8px", background: placed ? "#eef7ee" : "#fff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", alignItems: "flex-start" }}>
                <div style={{ fontSize: "14px" }}>
                  <strong>{c.subject}</strong> — {c.section}
                  {placed
                    ? <div style={{ color: "#1d5a1d", fontSize: "13px", marginTop: "3px" }}>Placed and checked: no clash. ({r.method})</div>
                    : <div style={{ color: "#7a4b00", fontSize: "13px", marginTop: "3px" }}>{r?.reason || c.reason}</div>}
                  {placed && r.moved?.length > 0 && (
                    <details style={{ marginTop: "4px", fontSize: "13px", color: "#374151" }}>
                      <summary>{r.moved.length} other class{r.moved.length === 1 ? "" : "es"} moved to make room</summary>
                      <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                        {r.moved.map((m, i) => <li key={i}>{m.subject} ({m.section}): {m.from} → {m.to}</li>)}
                      </ul>
                    </details>
                  )}
                </div>
                {!placed && (
                  <button disabled={!!busy} onClick={() => run({ section_id: c.section_id, subject_id: c.subject_id }, keyOf(c))}
                    style={{ background: "#0b6b3a", color: "#fff", border: "none", borderRadius: "6px", padding: "6px 14px", whiteSpace: "nowrap", cursor: busy ? "wait" : "pointer" }}>
                    {busy === keyOf(c) ? "Resolving…" : "Resolve"}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
