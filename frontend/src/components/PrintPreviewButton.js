import React, { useEffect, useState } from "react";
import API from "../services/api";
import ScheduleProblemsModal from "./ScheduleProblemsModal";

/* "Print / Preview" for a schedule table: GET /engine/export-pdf/ with the table's filters, opened as a PDF preview tab. A table with
   conflicts is never printed silently: the server answers 409 and this shows them, with "Fix them now" and "Print anyway (marked NOT
   FINAL)" -- the same behaviour as the Dean's Schedules tab.
   params: { department, program_id, year_level, semester, status, classification } (blank = all).
   yearChoices (optional): the year levels to offer before printing -- one year level, or "All year levels" (one table per year
   level in the PDF, one signatory block at the end). defaultYear: the year level picked first ("" = all). */
const ALL = "__all__";
const ord = (y) => parseInt(String(y).match(/\d+/)?.[0] || "99", 10);

/* The year levels offered for printing: 1st to 4th Year, plus any further year level that really has classes (e.g. a 5-year program). */
export function printYears(rows) {
  const have = new Set((rows || []).map((r) => r.year_level).filter(Boolean));
  return [...new Set(["1st Year", "2nd Year", "3rd Year", "4th Year", ...have])].sort((a, b) => ord(a) - ord(b));
}

export default function PrintPreviewButton({ params, disabled = false, onFixed, yearChoices = null, defaultYear = "" }) {
  const [busy, setBusy] = useState(false);
  const [download, setDownload] = useState(null);
  const [clash, setClash] = useState(null);
  const [fixing, setFixing] = useState(false);
  const [asking, setAsking] = useState(false);
  const [year, setYear] = useState(defaultYear || ALL);
  const [usedYear, setUsedYear] = useState(null);      // the choice of the last print (Print anyway reuses it)
  useEffect(() => () => { if (download) window.URL.revokeObjectURL(download.url); }, [download]);
  const clean = Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== "" && v != null));
  const years = (yearChoices || []).filter(Boolean);
  const allLabel = years.length > 1 ? `All year levels (${years[0].split(" ")[0]} - ${years[years.length - 1].split(" ")[0]})` : "All year levels";

  const print = async (allowConflicts = false, yearChoice = usedYear) => {
    // Reserve a tab synchronously during the click. Opening it after the PDF request
    // resolves is commonly blocked because the user activation has expired.
    let previewWindow = null;
    try {
      previewWindow = window.open("", "_blank");
      if (previewWindow) {
        try {
          previewWindow.document.title = "Preparing schedule PDF";
          previewWindow.document.body.textContent = "Preparing your schedule PDF…";
        } catch (_e) { /* The tab may still accept the PDF URL even if its placeholder cannot be written. */ }
      }
    } catch (_e) { /* A blocked popup falls back to an explicit download link. */ }

    setBusy(true);
    setAsking(false);
    setUsedYear(yearChoice);
    setDownload(null);
    const yp = yearChoice === null ? {} : { year_level: yearChoice === ALL ? undefined : yearChoice };
    try {
      const res = await API.get("/engine/export-pdf/", { params: { ...clean, ...yp, allow_conflicts: allowConflicts ? 1 : undefined }, responseType: "blob" });
      setClash(null);
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      let opened = false;
      try {
        if (previewWindow && !previewWindow.closed) {
          previewWindow.location.href = url;
          opened = true;
        }
      } catch (_e) { /* Fall back to a download link if navigating the reserved tab fails. */ }
      if (!opened) setDownload({ url, filename: "class_schedule.pdf" });
      else setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (err) {
      try { if (previewWindow && !previewWindow.closed) previewWindow.close(); } catch (_e) { /* Ignore a tab already closed by the user. */ }
      const st = err.response?.status;
      if (st === 409) {
        try { setClash(JSON.parse(await err.response.data.text())); }
        catch (_e) { setClash({ total: 1, conflicts: [], detail: "This table has conflicts. Fix them in the Conflicts tab before printing." }); }
      } else if (st === 404) {
        alert("Nothing to print: no classes match these filters.");
      } else {
        let msg = "";
        try { msg = JSON.parse(await err.response.data.text()).detail || ""; } catch (_e) { /* not JSON */ }
        alert(msg || "Could not generate the PDF. Check that the backend is running, then try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <span style={{ position: "relative", display: "inline-block" }}>
        <button onClick={() => (years.length ? (setYear(defaultYear || ALL), setAsking((a) => !a)) : print(false, null))} disabled={busy || disabled}
          style={{ background: "#003366", color: "white" }} title="Opens the class schedule as a PDF (portrait) to preview or print">
          {busy ? "Checking and preparing PDF…" : "Print Report"}
        </button>
        {asking && (
          <div role="dialog" aria-label="Print which year levels" style={{ position: "absolute", right: 0, top: "100%", marginTop: 6, zIndex: 1100, width: "min(300px, 90vw)",
            background: "white", border: "1px solid #d1d5db", borderRadius: 6, boxShadow: "var(--shadow-pop)", padding: "10px 12px", textAlign: "left" }}>
            <div style={{ fontWeight: 600, color: "#003366", fontSize: 13, marginBottom: 6 }}>Year level to print</div>
            {years.map((y) => (
              <label key={y} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, padding: "3px 0", cursor: "pointer", color: "#111827" }}>
                <input type="radio" name="print-year" checked={year === y} onChange={() => setYear(y)} /> {y} <span style={{ color: "#6b7280", fontSize: 12 }}>(1 page)</span>
              </label>
            ))}
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, padding: "3px 0", cursor: "pointer", color: "#111827" }}>
              <input type="radio" name="print-year" checked={year === ALL} onChange={() => setYear(ALL)} /> {allLabel}
            </label>
            <div style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 8px" }}>
              All year levels: one table per year level, in order, and one signatory block at the end.
            </div>
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <button type="button" onClick={() => setAsking(false)} style={{ background: "white", color: "#003366", border: "1px solid #003366", padding: "4px 10px", fontSize: 13 }}>Cancel</button>
              <button type="button" onClick={() => print(false, year)} style={{ background: "#003366", color: "white", padding: "4px 10px", fontSize: 13 }}>Print Report</button>
            </div>
          </div>
        )}
      </span>
      {download && (
        <div role="status" style={{ display: "inline-flex", alignItems: "center", gap: 8, marginLeft: 8, fontSize: 13, color: "#374151" }}>
          <span>Your browser blocked the preview tab.</span>
          <a href={download.url} download={download.filename} onClick={() => setTimeout(() => setDownload((current) => current?.url === download.url ? null : current), 60000)}
            style={{ color: "#003366", fontWeight: 600 }}>Download PDF</a>
        </div>
      )}
      {clash && !fixing && (
        <div role="alertdialog" aria-label="Conflicts before printing" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "white", borderRadius: 6, maxWidth: 560, width: "100%", padding: "18px 20px", boxShadow: "var(--shadow-pop)", borderTop: "5px solid #b91c1c" }}>
            <h3 style={{ margin: "0 0 8px", color: "#b91c1c" }}>Not printed: {clash.total} conflict{clash.total === 1 ? "" : "s"} in this table</h3>
            <p style={{ fontSize: 14, margin: "0 0 8px" }}>{clash.detail}</p>
            <ul style={{ fontSize: 13, margin: "0 0 12px 18px", padding: 0, maxHeight: 180, overflowY: "auto" }}>
              {(clash.conflicts || []).slice(0, 8).map((c, i) => <li key={i}>{c.a?.code} and {c.b?.code}: {c.message}</li>)}
            </ul>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
              <button onClick={() => setClash(null)} style={{ background: "white", color: "#003366", border: "1px solid #003366" }}>Close</button>
              <button onClick={() => print(true)} title="The PDF is printed with a red NOT FINAL line naming the number of conflicts" style={{ background: "white", color: "#b91c1c", border: "1px solid #b91c1c" }}>Print anyway (marked NOT FINAL)</button>
              {(clash.conflicts || []).length > 0 && <button onClick={() => setFixing(true)} style={{ background: "#003366", color: "white" }}>Fix them now</button>}
            </div>
          </div>
        </div>
      )}
      {clash && fixing && (
        <ScheduleProblemsModal clashes={clash.conflicts || []} unplaced={[]}
          onFixed={(d) => { if (d && d.clash != null) setClash((p) => ({ ...p, total: Math.max(0, p.total - 1), conflicts: p.conflicts.filter((_c, i) => i !== d.clash) })); }}
          onClose={() => { setFixing(false); setClash(null); if (onFixed) onFixed(); }} />
      )}
    </>
  );
}
