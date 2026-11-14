import React, { useEffect, useState } from "react";
import API from "../services/api";
import { notifyToast } from "../services/toast";
import ScheduleProblemsModal from "./ScheduleProblemsModal";
import CustomSelect from "./CustomSelect";
import usePopupPresence from "./usePopupPresence";

/* "Print Report" exports a schedule table in PDF, XLSX, or CSV using the table's filters. A table with
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

export function printTerms(rows) {
  return [...new Set((rows || []).map((r) => r.semester).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

export default function PrintPreviewButton({ params, disabled = false, onFixed, yearChoices = null, defaultYear = "", termChoices = [] }) {
  const [busy, setBusy] = useState(false);
  const [download, setDownload] = useState(null);
  const [clash, setClash] = useState(null);
  const [fixing, setFixing] = useState(false);
  const [asking, setAsking] = useState(false);
  const { present: dialogPresent, closing: dialogClosing } = usePopupPresence(asking);
  const [year, setYear] = useState(defaultYear || ALL);
  const [term, setTerm] = useState(params?.semester || ALL);
  const [format, setFormat] = useState("pdf");
  const [usedYear, setUsedYear] = useState(null);      // the choice of the last print (Print anyway reuses it)
  const [usedTerm, setUsedTerm] = useState(ALL);
  const [usedFormat, setUsedFormat] = useState("pdf");
  useEffect(() => () => { if (download) window.URL.revokeObjectURL(download.url); }, [download]);
  const clean = Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== "" && v != null));
  const years = (yearChoices || []).filter(Boolean);
  const allLabel = years.length > 1 ? `All year levels (${years[0].split(" ")[0]} - ${years[years.length - 1].split(" ")[0]})` : "All year levels";
  const terms = [...new Set(termChoices.filter(Boolean))];

  const print = async (allowConflicts = false, yearChoice = usedYear, formatChoice = usedFormat, termChoice = usedTerm) => {
    // Reserve a tab synchronously during the click. Opening it after the PDF request
    // resolves is commonly blocked because the user activation has expired.
    let previewWindow = null;
    try {
      if (formatChoice === "pdf") previewWindow = window.open("", "_blank");
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
    setUsedTerm(termChoice);
    setUsedFormat(formatChoice);
    setDownload(null);
    const yp = yearChoice === null ? {} : { year_level: yearChoice === ALL ? undefined : yearChoice };
    try {
      const rp = { ...clean, ...yp, semester: termChoice === ALL ? undefined : termChoice,
        format: formatChoice, allow_conflicts: allowConflicts ? 1 : undefined };
      const res = await API.get("/engine/export-report/", { params: rp, responseType: "blob" });
      setClash(null);
      const mime = formatChoice === "pdf" ? "application/pdf" : formatChoice === "xlsx"
        ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" : "text/csv;charset=utf-8";
      const ext = formatChoice === "xlsx" ? "xlsx" : formatChoice;
      const url = window.URL.createObjectURL(new Blob([res.data], { type: mime }));
      let opened = false;
      try {
        if (previewWindow && !previewWindow.closed) {
          previewWindow.location.href = url;
          opened = true;
        }
      } catch (_e) { /* Fall back to a download link if navigating the reserved tab fails. */ }
      if (!opened) setDownload({ url, filename: `class_schedule.${ext}`, format: ext });
      else setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (err) {
      try { if (previewWindow && !previewWindow.closed) previewWindow.close(); } catch (_e) { /* Ignore a tab already closed by the user. */ }
      const st = err.response?.status;
      if (st === 409) {
        try { setClash(JSON.parse(await err.response.data.text())); }
        catch (_e) { setClash({ total: 1, conflicts: [], detail: "This table has conflicts. Fix them in the Conflicts tab before printing." }); }
      } else if (st === 404) {
        notifyToast("No classes match these report filters.", "warning");
      } else {
        let msg = "";
        try { msg = JSON.parse(await err.response.data.text()).detail || ""; } catch (_e) { /* not JSON */ }
        notifyToast(msg || "Could not create the report. Check that the backend is running, then try again.", "error");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <span style={{ position: "relative", display: "inline-block" }}>
        <button onClick={() => { setYear(defaultYear || ALL); setTerm(params?.semester || ALL); setFormat("pdf"); setAsking((a) => !a); }} disabled={busy || disabled}
          style={{ background: "#003366", color: "white" }} title="Choose a term and download the schedule report as PDF, XLSX, or CSV">
          {busy ? "Preparing report…" : "Print Report"}
        </button>
        {dialogPresent && (
          <div role="dialog" aria-label="Choose report options" aria-hidden={dialogClosing} inert={dialogClosing ? "" : undefined} className={`popup-slide${dialogClosing ? " is-closing" : ""}`} style={{ position: "absolute", right: 0, top: "100%", marginTop: 6, zIndex: 1100, width: "min(320px, 90vw)",
            background: "white", border: "1px solid #d1d5db", borderRadius: 6, boxShadow: "var(--shadow-pop)", padding: "10px 12px", textAlign: "left" }}>
            <div style={{ fontWeight: 600, color: "#003366", fontSize: 13, marginBottom: 8 }}>Print report</div>
            <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#374151", marginBottom: 8 }}>Semester / term
              <CustomSelect value={term} onChange={(e) => setTerm(e.target.value)} style={{ width: "100%", padding: "7px 8px", border: "1px solid #cbd5e1", borderRadius: 5, color: "#111827", background: "white" }}>
                <option value={ALL}>All semesters / terms</option>
                {terms.map((t) => <option key={t} value={t}>{t}</option>)}
              </CustomSelect>
            </label>
            <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#374151", marginBottom: 8 }}>File format
              <CustomSelect value={format} onChange={(e) => setFormat(e.target.value)} style={{ width: "100%", padding: "7px 8px", border: "1px solid #cbd5e1", borderRadius: 5, color: "#111827", background: "white" }}>
                <option value="pdf">PDF (preview / print)</option><option value="xlsx">Excel workbook (.xlsx)</option><option value="csv">CSV (.csv)</option>
              </CustomSelect>
            </label>
            {years.length > 0 && <div style={{ fontWeight: 600, color: "#003366", fontSize: 12, margin: "8px 0 4px" }}>Year level</div>}
            {years.map((y) => (
              <label key={y} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, padding: "3px 0", cursor: "pointer", color: "#111827" }}>
                <input type="radio" name="print-year" checked={year === y} onChange={() => setYear(y)} /> {y} <span style={{ color: "#6b7280", fontSize: 12 }}>(1 page)</span>
              </label>
            ))}
            {years.length > 0 && <>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, padding: "3px 0", cursor: "pointer", color: "#111827" }}>
                <input type="radio" name="print-year" checked={year === ALL} onChange={() => setYear(ALL)} /> {allLabel}
              </label>
              <div style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 8px" }}>
                All year levels: one table per year level, in order, and one signatory block at the end.
              </div>
            </>}
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <button type="button" onClick={() => setAsking(false)} style={{ background: "white", color: "#003366", border: "1px solid #003366", padding: "4px 10px", fontSize: 13 }}>Cancel</button>
              <button type="button" onClick={() => print(false, years.length ? year : null, format, term)} style={{ background: "#003366", color: "white", padding: "4px 10px", fontSize: 13 }}>Create report</button>
            </div>
          </div>
        )}
      </span>
      {download && (
        <div role="status" style={{ display: "inline-flex", alignItems: "center", gap: 8, marginLeft: 8, fontSize: 13, color: "#374151" }}>
          <span>{download.format === "pdf" ? "Your browser blocked the preview tab." : "Your report is ready."}</span>
          <a href={download.url} download={download.filename} onClick={() => setTimeout(() => setDownload((current) => current?.url === download.url ? null : current), 60000)}
            style={{ color: "#003366", fontWeight: 600 }}>Download {download.format.toUpperCase()}</a>
        </div>
      )}
      {clash && !fixing && (
        <div role="alertdialog" aria-label="Conflicts before printing" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "white", borderRadius: 6, maxWidth: 560, width: "100%", padding: "18px 20px", boxShadow: "var(--shadow-pop)", borderTop: "5px solid #b91c1c" }}>
            <h3 style={{ margin: "0 0 8px", color: "#b91c1c" }}>Report paused: {clash.total} conflict{clash.total === 1 ? "" : "s"} in this table</h3>
            <p style={{ fontSize: 14, margin: "0 0 8px" }}>{clash.detail}</p>
            <ul style={{ fontSize: 13, margin: "0 0 12px 18px", padding: 0, maxHeight: 180, overflowY: "auto" }}>
              {(clash.conflicts || []).slice(0, 8).map((c, i) => <li key={i}>{c.a?.code} and {c.b?.code}: {c.message}</li>)}
            </ul>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
              <button onClick={() => setClash(null)} style={{ background: "white", color: "#003366", border: "1px solid #003366" }}>Close</button>
              <button onClick={() => print(true)} title="The report is marked NOT FINAL and includes the unresolved conflicts" style={{ background: "white", color: "#b91c1c", border: "1px solid #b91c1c" }}>Export anyway (marked NOT FINAL)</button>
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
