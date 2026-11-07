import React, { useCallback, useEffect, useMemo, useState } from "react";
import API from "../services/api";
import { be, errText, cardStyle, btn, btnPrimary, Notice } from "./basicEdUi";
import { formatDate, formatTime } from "../utils/formatDateTime";

/* SHS / JHS availability: the teacher SUBMITS it (My Profile), the Principal only VIEWS it (Faculty > Faculty availability).
   The grid shows every class period of the teacher's grades, Monday to Friday. A break for all of those grades cannot be marked; a break
   for one grade only stays selectable with a note. Each cell says its choice in words as well as in color. */
export const TIERS = ["available", "preferred", "unavailable"];
export const TIER_WORD = { preferred: "Preferred", available: "Available", unavailable: "Unavailable" };
const TIER_STYLE = {
  preferred: { background: "#dcfce7", color: "#166534", borderColor: "#86efac" },
  available: { background: "#ffffff", color: "#374151", borderColor: "#d1d5db" },
  unavailable: { background: "#fee2e2", color: "#991b1b", borderColor: "#fca5a5" },
};

export function statusText(x) {
  if (!x) return "";
  if (x.status === "returned") return "Returned for correction (last submission still in use)";
  if (x.status === "submitted") {
    return `Submitted${x.submitted_at ? ` on ${formatDate(x.submitted_at)}` : ""}${x.updated_since_generation ? " · Updated since last generation" : ""}`;
  }
  return "Not submitted (free at any time)";
}

export function AvailabilityGrid({ grid, cells, editable = false, onChange }) {
  if (!grid) return null;
  const set = (key, v) => onChange && onChange({ ...cells, [key]: v });
  const next = (v) => TIERS[(TIERS.indexOf(v) + 1) % TIERS.length];
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640, fontSize: 13 }}>
        <thead><tr><th style={{ background: "#003366", color: "white", padding: 6, width: 130 }}>Time</th>
          {grid.days.map((d) => <th key={d.key} style={{ background: "#003366", color: "white", padding: 6 }}>{d.label}</th>)}</tr></thead>
        <tbody>
          {grid.rows.map((r) => (
            r.kind === "break" ? (
              <tr key={`b-${r.start}`}>
                <td style={{ padding: 6, border: "1px solid #e5e7eb", background: "#f3f4f6", color: "#6b7280" }}>{formatTime(r.start)}–{formatTime(r.end)}</td>
                <td colSpan={grid.days.length} style={{ padding: 6, border: "1px solid #e5e7eb", background: "#f3f4f6", color: "#6b7280", textAlign: "center" }}>
                  {r.label || "Break"} (not a class time)</td>
              </tr>
            ) : (
              <tr key={`p-${r.start}`}>
                <td style={{ padding: 6, border: "1px solid #e5e7eb", background: "#f9fafb", verticalAlign: "top" }}>
                  {formatTime(r.start)}–{formatTime(r.end)}
                  {r.note && <div style={{ fontSize: 11, color: "#92400e" }}>{r.note}</div>}
                  {r.outside_preferred && <div style={{ fontSize: 11, color: "#6b7280" }}>Outside the preferred hours set by the school</div>}
                </td>
                {grid.days.map((d) => {
                  const key = `${d.key}|${r.start}`;
                  const v = cells[key] || "available";
                  const st = TIER_STYLE[v];
                  return (
                    <td key={key} style={{ padding: 3, border: "1px solid #e5e7eb" }}>
                      {editable ? (
                        <button type="button" onClick={() => set(key, next(v))}
                          aria-label={`${d.label} ${formatTime(r.start)} to ${formatTime(r.end)}: ${TIER_WORD[v]}. Press to change.`}
                          style={{ width: "100%", border: "1px solid", borderRadius: 4, padding: "6px 4px", fontSize: 12, fontWeight: 600, cursor: "pointer", ...st }}>
                          {TIER_WORD[v]}
                        </button>
                      ) : (
                        <div style={{ border: "1px solid", borderRadius: 4, padding: "6px 4px", fontSize: 12, fontWeight: 600, textAlign: "center", ...st }}>{TIER_WORD[v]}</div>
                      )}
                    </td>
                  );
                })}
              </tr>
            )
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 12, color: "#4b5563", margin: "6px 0 0" }}>
        Preferred: times you would like to teach (tried first). Available: you can teach. Unavailable: never scheduled.
        {editable ? " Press a time to change it." : ""}
      </p>
    </div>
  );
}

/* ---- the teacher: My Profile > Availability */
export function MyAvailability() {
  const [data, setData] = useState(null);
  const [cells, setCells] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const draftKey = data ? `ufast_avail_draft_${data.faculty_id}` : "";
  const load = useCallback(() => {
    API.get("/basic-ed/my/availability/").then((r) => {
      setData(r.data);
      let draft = null;
      try { draft = JSON.parse(window.localStorage.getItem(`ufast_avail_draft_${r.data.faculty_id}`) || "null"); } catch (e) { draft = null; }
      setCells(draft || r.data.cells);
    }).catch((e) => setError(errText(e, "Your availability could not be loaded.")));
  }, []);
  useEffect(() => { load(); }, [load]);
  const changed = useMemo(() => data && cells && JSON.stringify(cells) !== JSON.stringify(data.cells), [data, cells]);
  const edit = (c) => {
    setCells(c); setMsg(null);
    try { window.localStorage.setItem(draftKey, JSON.stringify(c)); } catch (e) { /* the draft is only kept on this computer when possible */ }
  };
  const discard = () => { try { window.localStorage.removeItem(draftKey); } catch (e) { /* ignore */ } setCells(data.cells); setMsg(null); };
  const submit = async () => {
    setBusy(true); setMsg(null);
    try {
      const out = Object.entries(cells).map(([k, v]) => { const [day, start] = k.split("|"); return { day, start, preference: v }; });
      const r = await API.post("/basic-ed/my/availability/", { cells: out });
      try { window.localStorage.removeItem(draftKey); } catch (e) { /* ignore */ }
      setData(r.data); setCells(r.data.cells); setMsg({ ok: true, text: r.data.detail });
    } catch (e) { setMsg({ ok: false, text: errText(e, "Could not submit your availability.") }); }
    setBusy(false);
  };
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data || !cells) return <p style={{ fontSize: 13, color: "#6b7280" }}>Loading your availability…</p>;
  return (
    <div style={{ ...cardStyle, marginTop: 14 }}>
      <h3 style={{ marginTop: 0 }}>My availability</h3>
      <p style={{ margin: "0 0 4px", fontSize: 14 }}><strong style={{ fontWeight: 600 }}>Status:</strong> {statusText(data)}</p>
      {data.status === "returned" && data.note && (
        <p role="alert" style={{ margin: "0 0 8px", fontSize: 13, color: "#92400e" }}>Principal's note: {data.note}</p>
      )}
      <p style={{ margin: "0 0 10px", fontSize: 12, color: "#4b5563" }}>
        Your submitted availability is used the next time the Principal generates the timetable. Approved or published timetables do not change.
        {data.grid.preferred_start ? ` The school set your teaching hours to ${formatTime(data.grid.preferred_start)}–${formatTime(data.grid.preferred_end)}.` : ""}
      </p>
      <AvailabilityGrid grid={data.grid} cells={cells} editable onChange={edit} />
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 10, flexWrap: "wrap" }}>
        {changed && <button type="button" style={btn} onClick={discard} disabled={busy}>Discard changes</button>}
        <button type="button" style={btnPrimary} onClick={submit} disabled={busy}>{busy ? "Submitting…" : "Submit to Principal"}</button>
      </div>
      {changed && <p style={{ fontSize: 12, color: "#92400e", textAlign: "right", margin: "6px 0 0" }}>You have changes that are not submitted yet.</p>}
      {msg && <p role="status" style={{ fontSize: 13, color: msg.ok ? "#166534" : "#b91c1c", marginTop: 8 }}>{msg.text}</p>}
    </div>
  );
}

/* ---- the Principal (read only; IT Admin too): Faculty > Faculty availability */
export function FacultyAvailability({ level }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState("");
  const load = useCallback(() => {
    be.get(level, "availability/").then((r) => setList(r.data)).catch((e) => setError(errText(e, "Faculty availability could not be loaded.")));
  }, [level]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    setDetail(null); setNote("");
    if (!open) return;
    be.get(level, `availability/${open}/`).then((r) => setDetail(r.data)).catch((e) => setMsg({ ok: false, text: errText(e) }));
  }, [open, level]);
  const waiting = (list?.teachers || []).filter((t) => t.status !== "submitted").length;
  const remind = async () => {
    setBusy("remind"); setMsg(null);
    try { const r = await be.post(level, "availability/remind/"); setMsg({ ok: true, text: r.data.detail }); }
    catch (e) { setMsg({ ok: false, text: errText(e) }); }
    setBusy("");
  };
  const giveBack = async () => {
    setBusy("return"); setMsg(null);
    try {
      const r = await be.post(level, `availability/${open}/return/`, { note });
      setMsg({ ok: true, text: r.data.detail }); setNote(""); load();
      setDetail((d) => (d ? { ...d, ...r.data } : d));
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
    setBusy("");
  };
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!list) return <p style={{ fontSize: 13, color: "#6b7280" }}>Loading faculty availability…</p>;
  const canEdit = list.can_edit_status;
  return (
    <div style={{ ...cardStyle, marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <b>Faculty availability</b>
        {canEdit && (
          <button type="button" style={btn} onClick={remind} disabled={busy === "remind" || waiting === 0}>
            {busy === "remind" ? "Sending…" : `Remind teachers who have not submitted (${waiting})`}
          </button>
        )}
      </div>
      <p style={{ fontSize: 13, color: "#4b5563", margin: "4px 0 10px" }}>
        Teachers submit their own availability. You can view it and return it for correction, but not change it.
      </p>
      {msg && <p role="status" style={{ fontSize: 13, color: msg.ok ? "#166534" : "#b91c1c" }}>{msg.text}</p>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead><tr>{["Teacher", "Status", "Load / limit", "Preferred hours (school)", ""].map((h) => (
          <th key={h} style={{ textAlign: "left", padding: "8px 10px", borderBottom: "1px solid #e5e7eb", color: "#374151", fontWeight: 600 }}>{h}</th>))}</tr></thead>
        <tbody>
          {list.teachers.map((t) => (
            <tr key={t.faculty_id} style={{ background: open === t.faculty_id ? "#eef4fb" : "white" }}>
              <td style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>{t.full_name}<div style={{ fontSize: 12, color: "#6b7280" }}>{t.department}</div></td>
              <td style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>{statusText(t)}</td>
              <td style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>{t.load_hours} / {t.max_weekly_hours} h</td>
              <td style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>{t.preferred_start ? `${formatTime(t.preferred_start)}–${formatTime(t.preferred_end)}` : "—"}</td>
              <td style={{ padding: "8px 10px", borderBottom: "1px solid #f3f4f6" }}>
                <button type="button" style={btn} onClick={() => setOpen(open === t.faculty_id ? null : t.faculty_id)} aria-expanded={open === t.faculty_id}>
                  {open === t.faculty_id ? "Close" : "View"}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && detail && (
        <div style={{ marginTop: 14, borderTop: "1px solid #e5e7eb", paddingTop: 12 }}>
          <h4 style={{ margin: "0 0 4px" }}>{detail.full_name}</h4>
          <p style={{ margin: "0 0 4px", fontSize: 13 }}><strong style={{ fontWeight: 600 }}>Status:</strong> {statusText(detail)} ·
            Load {detail.load_hours} of {detail.max_weekly_hours} h a week
            {detail.grid.preferred_start ? ` · Preferred hours (school): ${formatTime(detail.grid.preferred_start)}–${formatTime(detail.grid.preferred_end)}` : ""}</p>
          {detail.status === "returned" && detail.note && <p style={{ fontSize: 13, color: "#92400e", margin: "0 0 8px" }}>Your note: {detail.note}</p>}
          <AvailabilityGrid grid={detail.grid} cells={detail.cells} />
          {canEdit && detail.status !== "not_submitted" && (
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginTop: 10, flexWrap: "wrap" }}>
              <label style={{ fontSize: 13, color: "#374151", flex: "1 1 260px" }}>Note for the teacher
                <input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="What should be corrected?"
                  style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 4, fontSize: 13, padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4 }} />
              </label>
              <button type="button" style={btn} onClick={giveBack} disabled={busy === "return" || note.trim().length < 3}>
                {busy === "return" ? "Returning…" : "Return for correction"}</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
