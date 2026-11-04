import React, { useCallback, useEffect, useState } from "react";
import API from "../services/api";
import ScheduleProblemsModal from "./ScheduleProblemsModal";

/* Conflict report: every teacher / room / student double-booking in the class schedule, with the two classes
   involved. Runs automatically when opened; also used (ConflictList) to show the clashes found right after a
   schedule is generated. Sample conflicts can be added / removed to demonstrate the detection.
   Fixing is suggest-then-confirm: "Fix" opens the pop-up with the free days and times for one of the two classes (same room first);
   nothing is changed until the Dean / Registrar confirms, and the server checks every rule again before saving. */
const KIND = {
  teacher: { label: "Teacher", bg: "#fee2e2", fg: "#a4231a" },
  room: { label: "Room", bg: "#ffedd5", fg: "#9a3412" },
  section: { label: "Students", bg: "#ede9fe", fg: "#5b21b6" },
};

function ClassBox({ c, shared, kind }) {
  const hi = (k) => (kind === k ? { background: "#fef9c3", borderRadius: "4px", padding: "0 3px", fontWeight: 600 } : null);
  return (
    <div style={{ flex: "1 1 240px", minWidth: 0, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "8px 10px", fontSize: "12.5px" }}>
      <div style={{ fontWeight: 600, color: "#1f2937" }}>{c.subject}{c.demo && <span style={{ marginLeft: 6, fontSize: 11, color: "#92400e" }}>(sample)</span>}</div>
      <div style={{ color: "#475569", marginTop: 2 }}>
        <span style={hi("section")}>{c.section}</span> · <span style={hi("teacher")}>{c.teacher}</span> · <span style={hi("room")}>{c.room}</span>
      </div>
      <div style={{ color: "#003366", marginTop: 2, fontWeight: 600 }}>{c.time}</div>
    </div>
  );
}

export function ConflictList({ report, emptyText = "No conflicts found.", onResolve, busy, fixed = {} }) {
  if (!report) return null;
  if (!report.total) {
    return (
      <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", color: "#166534", borderRadius: "8px", padding: "10px 14px", fontSize: "13px" }}>
        ✔ {emptyText}{report.checked ? ` (${report.checked} class${report.checked === 1 ? "" : "es"} checked)` : ""}
      </div>
    );
  }
  return (
    <div>
      <div style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", borderRadius: "8px", padding: "10px 14px", fontSize: "13px", marginBottom: "10px" }}>
        <strong>{report.total} conflict{report.total === 1 ? "" : "s"} found</strong>
        {Object.entries(report.counts || {}).map(([k, n]) => (
          <span key={k} style={{ marginLeft: 10, background: KIND[k]?.bg, color: KIND[k]?.fg, borderRadius: 999, padding: "2px 9px", fontSize: 12 }}>{KIND[k]?.label}: {n}</span>
        ))}
      </div>
      {report.conflicts.map((c, i) => (
        <div key={i} style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "10px 12px", marginBottom: "10px", background: "white" }}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap", marginBottom: "8px" }}>
            <span style={{ background: KIND[c.kind]?.bg, color: KIND[c.kind]?.fg, borderRadius: 999, padding: "2px 10px", fontSize: 12, fontWeight: 600 }}>{c.kind_label} conflict</span>
            <span style={{ fontSize: "12.5px", color: "#475569", flex: 1 }}>{c.message}</span>
            {onResolve && (
              <button onClick={() => onResolve(c, i)} disabled={busy} style={{ background: "#003366", color: "white", border: "none", padding: "6px 14px", borderRadius: 6, cursor: busy ? "default" : "pointer", fontSize: 12.5 }}>
                Fix this conflict
              </button>
            )}
          </div>
          {fixed[i] && <div style={{ background: fixed[i].ok ? "#ecfdf5" : "#fef2f2", color: fixed[i].ok ? "#166534" : "#991b1b", borderRadius: 6, padding: "6px 10px", fontSize: 12.5, marginBottom: 8 }}>{fixed[i].summary}</div>}
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <ClassBox c={c.a} kind={c.kind} />
            <ClassBox c={c.b} kind={c.kind} />
          </div>
        </div>
      ))}
      {report.total > report.conflicts.length && <p style={{ fontSize: 12.5, color: "#64748b" }}>Showing the first {report.conflicts.length} of {report.total}.</p>}
    </div>
  );
}

export default function ConflictChecker() {
  const [report, setReport] = useState(null);
  const [semester, setSemester] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [fixing, setFixing] = useState(null);     // conflicts shown in the pop-up (one, or all of them)

  const run = useCallback(async () => {
    setBusy(true); setError("");
    try {
      const res = await API.get("/engine/conflicts/", { params: semester ? { semester } : {} });
      setReport(res.data);
      return res.data;
    } catch (e) {
      setError(e.response?.data?.detail || "Could not run the conflict check.");
      return null;
    } finally { setBusy(false); }
  }, [semester]);

  useEffect(() => { run(); }, [run]);

  const demo = async (action) => {
    setBusy(true); setError(""); setNote("");
    try {
      const res = await API.post("/engine/conflicts/demo/", { action });
      setNote(action === "add" ? `Added ${res.data.created.length} sample conflicts (teacher, room, students).` : `Removed ${res.data.removed} sample class period(s).`);
    } catch (e) {
      setError(e.response?.data?.detail || "Could not do that.");
    }
    await run();
  };

  // after a confirmed change: check the whole schedule again, and keep showing only the conflicts that are still there
  const afterFix = async (d) => {
    if (d && d.summary) setNote(d.summary);
    if (!d || d.clash == null) return;
    const fresh = await run();
    if (!fresh) return;
    setFixing((cur) => {
      if (!cur) return cur;
      const same = (x, y) => x.kind === y.kind && x.a.ids.join() === y.a.ids.join() && x.b.ids.join() === y.b.ids.join();
      const left = fresh.conflicts.filter((c) => cur.some((o) => same(o, c)));
      return cur.length > 1 ? fresh.conflicts : left;
    });
  };

  const btn = { background: "white", color: "#003366", border: "1px solid #cdd6e0", padding: "8px 14px", borderRadius: "6px", cursor: "pointer" };
  return (
    <div>
      <p style={{ fontSize: "13px", color: "#475569", maxWidth: "780px", marginTop: 0 }}>
        Checks the whole class schedule for a teacher, a room or a group of students booked for two classes at the same time
        {report && report.allowance_minutes ? ` (students may overlap by up to ${report.allowance_minutes} minutes).` : " (no overlap is allowed for students either)."} Run it after generating or editing schedules.
        To fix one, press <strong>Fix this conflict</strong>: you choose which class moves and to which free day and time; nothing changes until you confirm.
      </p>
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" }}>
        <select value={semester} onChange={(e) => setSemester(e.target.value)} aria-label="Semester" style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid #cdd6e0" }}>
          <option value="">All semesters</option>
          <option value="1st Sem">1st Sem</option>
          <option value="2nd Sem">2nd Sem</option>
          <option value="Summer">Summer</option>
        </select>
        <button onClick={run} disabled={busy}>{busy ? "Checking…" : "Check for conflicts"}</button>
        <span style={{ flex: 1 }} />
        <button style={btn} onClick={() => demo("add")} disabled={busy} title="Adds three sample double-bookings next to an existing class, to show the detection">Add sample conflicts (demo)</button>
        {report?.total > 0 && <button onClick={() => setFixing(report.conflicts)} disabled={busy} title="Opens every conflict with the free days and times you can move one of the two classes to. Nothing changes until you confirm.">Review and fix conflicts</button>}
        {report?.demo_rows > 0 && <button style={btn} onClick={() => demo("remove")} disabled={busy}>Remove sample conflicts</button>}
      </div>
      {error && <p style={{ color: "#a4231a", fontSize: 13 }}>{error}</p>}
      {note && <p style={{ color: "#166534", fontSize: 13 }}>{note}</p>}
      {report ? <ConflictList report={report} emptyText="No conflicts: no teacher, room or student group is double-booked." onResolve={(c) => setFixing([c])} busy={busy} /> : <p>Checking…</p>}
      {fixing && (
        <ScheduleProblemsModal clashes={fixing} unplaced={[]} onFixed={afterFix} onClose={() => { setFixing(null); run(); }} />
      )}
    </div>
  );
}
