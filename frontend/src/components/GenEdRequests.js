import React, { useCallback, useEffect, useRef, useState } from "react";
import ModalPortal from "./ModalPortal";
import API from "../services/api";
import { onJump, takeJump } from "../services/jump";

/* Gen Ed move requests (engine/gened_requests.py).
   Dean: "Request move" on a Gen Ed class of their program -> pick one of the times the Registrar could move it to + a reason.
   Registrar: approve (moves ONLY that Gen Ed class, re-checked at that moment; never another Dean's or Gen Ed class) or reject.
   Both see the list with its status. */

const btn = { background: "white", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "4px 12px", fontSize: 13, cursor: "pointer" };
const btnPrimary = { ...btn, background: "#003366", color: "white", fontWeight: 600 };
const DAY_ORDER = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
const DAY_NAME = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };
const dayOf = (o) => String(o.day || o.label || "").slice(0, 3);
const displayTime = (value) => {
  const [hours, minutes] = String(value || "").split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return value || "";
  const date = new Date(2000, 0, 1, hours, minutes);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
};
// Monday first ... Saturday last, then by start time; same time keeps the server's order (best first)
const byDay = (opts) => opts.map((o, i) => [o, i]).sort(([a, i], [b, j]) =>
  (DAY_ORDER[dayOf(a)] ?? 9) - (DAY_ORDER[dayOf(b)] ?? 9) || String(a.start || "").localeCompare(String(b.start || "")) || i - j).map(([o]) => o);

const TONE = {
  pending: ["#fef3c7", "#92400e"], approved: ["#dcfce7", "#166534"], rejected: ["#fee2e2", "#991b1b"],
  cancelled: ["#f3f4f6", "#4b5563"], failed: ["#fee2e2", "#991b1b"],
};

export function RequestMoveModal({ group, onClose, onDone }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [key, setKey] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  useEffect(() => {
    API.post("/engine/gened-requests/options/", { ids: group.ids })
      .then((r) => setData(r.data)).catch((e) => setError(e.response?.data?.detail || "Could not load the possible times."));
  }, [group.ids]);
  const send = async () => {
    setBusy(true); setError("");
    try {
      const r = await API.post("/engine/gened-requests/", { ids: group.ids, key, reason });
      setDone(r.data);
      onDone && onDone();
    } catch (e) { setError(e.response?.data?.detail || "Could not send the request."); }
    setBusy(false);
  };
  return (
    <div className="gened-move-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="gened-move-modal" role="dialog" aria-modal="true" aria-labelledby="gened-move-title">
        <header className="gened-move-header">
          <div>
            <div className="gened-move-eyebrow">SCHEDULE CHANGE REQUEST</div>
            <h2 id="gened-move-title">Request a Gen Ed schedule change</h2>
            <p>Choose an available time. The schedule changes only after the Registrar approves.</p>
    <ModalPortal><div role="dialog" aria-label="Request a Gen Ed schedule change" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1500, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: "white", borderRadius: 6, width: "min(640px, 100%)", maxHeight: "90vh", overflow: "auto", padding: "16px 18px", boxShadow: "var(--shadow-pop)" }}>
        <h3 style={{ margin: "0 0 4px", color: "#003366" }}>Request a Gen Ed schedule change</h3>
        <p style={{ margin: "0 0 10px", fontSize: 13, color: "#4b5563" }}>
          {group.subject_code} — {group.subject_title} · {group.section_name}. Gen Ed classes belong to the Registrar: pick the time you would like
          it moved to (for example to free its current time for a major subject). Nothing changes until the Registrar approves.
        </p>
        {error && <p role="alert" style={{ color: "#b91c1c", fontSize: 13 }}>{error}</p>}
        {done ? (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "10px 12px", fontSize: 13, color: "#166534" }}>
            <b>Request sent.</b> {done.subject}: {done.current} → {done.target}. The Registrar was notified; you will be notified of the decision.
            <div style={{ textAlign: "right", marginTop: 8 }}><button style={btnPrimary} onClick={onClose}>OK</button></div>
          </div>
          <button className="gened-move-close" onClick={onClose} aria-label="Close request">×</button>
        </header>
        <div className="gened-move-content">
          <div className="gened-move-subject">
            <span>{group.subject_code}</span>
            <strong>{group.subject_title}</strong>
            <small>{group.section_name}</small>
          </div>
          {error && <div className="gened-move-alert" role="alert">{error}</div>}
          {done ? (
            <div className="gened-move-success">
              <strong>Request sent</strong>
              <p>{done.subject}: {done.current} → {done.target}</p>
              <span>The Registrar was notified. You’ll receive a notification when a decision is made.</span>
              <div className="gened-move-actions"><button className="gened-move-primary" onClick={onClose}>Done</button></div>
            </div>
          ) : !data ? (!error && <div className="gened-move-loading">Loading available times…</div>) : (
            <>
              {data.note && <div className="gened-move-notice">{data.note}</div>}
              <div className="gened-current-time">
                <span>Current schedule</span>
                <strong>{data.class.when}</strong>
                <small>{data.class.room} <i>·</i> {data.class.teacher}</small>
              </div>
              <div className="gened-time-section-heading">
                <div><h3>Choose a new time</h3><p>Only conflict free options are shown.</p></div>
                <span>{data.options.length} options</span>
              </div>
              {data.options.length === 0 ? (
                <div className="gened-move-alert">{data.reason || "There is no other free time for this class right now."}</div>
              ) : (
                <div className="gened-time-list" role="radiogroup" aria-label="New time">
                  {byDay(data.options).map((o, i, all) => (
                    <React.Fragment key={o.key}>
                      {(i === 0 || dayOf(all[i - 1]) !== dayOf(o)) && <div className="gened-time-day">{DAY_NAME[dayOf(o)] || dayOf(o)}</div>}
                      <label className={`gened-time-option${key === o.key ? " is-selected" : ""}`}>
                        <input type="radio" name="gened-time" checked={key === o.key} onChange={() => setKey(o.key)} />
                        <span className="gened-time-option-main">
                          <strong>{displayTime(o.start)} – {displayTime(o.end)}</strong>
                          <small>{[o.room, o.teacher].filter(Boolean).join(" · ")}</small>
                        </span>
                        <span className="gened-time-check" aria-hidden="true">✓</span>
                      </label>
                    </React.Fragment>
                  ))}
                </div>
              )}
              <label className="gened-move-reason">Reason <span>Optional</span>
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} maxLength={500}
                  placeholder="For example, request this time to make room for a major subject" />
              </label>
              <p className="gened-move-footnote">If approved, only this Gen Ed class moves. If the selected time becomes unavailable, nothing else is changed.</p>
              <footer className="gened-move-actions">
                <button className="gened-move-secondary" onClick={onClose}>Cancel</button>
                <button className="gened-move-primary" onClick={send} disabled={!key || busy}>{busy ? "Sending…" : "Send request"}</button>
              </footer>
            </>
          )}
        </div>
      </section>
    </div>
          </>
        )}
      </div>
    </div></ModalPortal>
  );
}

export function GenEdRequestsPanel({ role, onChanged, refreshKey = 0 }) {
  const isRegistrar = role === "registrar";
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [notes, setNotes] = useState({});
  const load = useCallback(() => {
    API.get("/engine/gened-requests/").then((r) => setData(r.data)).catch(() => setData(null));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  // opened from a notification: reload (the request may be new), then scroll here
  const boxRef = useRef(null);
  const [flash, setFlash] = useState(false);
  useEffect(() => onJump((t) => { if (t === "gened-requests") load(); }), [load]);
  useEffect(() => {
    if (!data || data.items.length === 0 || !takeJump("gened-requests")) return undefined;
    setOpen(true);
    if (boxRef.current) boxRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 2500);
    return () => clearTimeout(t);
  }, [data]);
  if (!data || data.items.length === 0) return null;
  const act = async (item, action) => {
    setBusy(`${item.id}-${action}`); setMsg(null);
    try {
      const r = await API.post(`/engine/gened-requests/${item.id}/${action}/`, { note: notes[item.id] || "" });
      const st = r.data.status;
      setMsg({ ok: st === "approved" || st === "rejected" || st === "cancelled",
        text: st === "approved" ? `Approved and moved. ${r.data.summary || ""}` : st === "failed" ? r.data.decision_note : `Request ${r.data.status_label.toLowerCase()}.` });
      load();
      if (st === "approved" && onChanged) onChanged();
    } catch (e) { setMsg({ ok: false, text: e.response?.data?.detail || "Could not update the request." }); }
    setBusy(null);
  };
  const shown = open ? data.items : data.items.filter((x) => x.status === "pending");
  return (
    <div ref={boxRef} id="gened-requests" tabIndex={-1} style={{ border: "1px solid #fde68a", background: "#fffbeb", borderRadius: 6, padding: "10px 14px", margin: "0 0 14px",
      scrollMarginTop: 72, outline: flash ? "2px solid #003366" : "none", outlineOffset: 2 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ color: "#92400e", fontSize: 14 }}>
          Gen Ed move requests {isRegistrar ? "from the Deans" : "(your college)"}: {data.pending} pending
        </strong>
        <button style={{ ...btn, fontSize: 12 }} onClick={() => setOpen((o) => !o)}>{open ? "Show pending only" : `Show all (${data.items.length})`}</button>
      </div>
      {msg && <div role="status" style={{ marginTop: 6, fontSize: 13, color: msg.ok ? "#166534" : "#991b1b" }}>{msg.text}</div>}
      {shown.length === 0 && <div style={{ fontSize: 13, color: "#6b7280", marginTop: 6 }}>No pending requests.</div>}
      {shown.map((x) => (
        <div key={x.id} style={{ background: "white", border: "1px solid #f1e3b5", borderRadius: 6, padding: "8px 10px", marginTop: 8, fontSize: 13 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "baseline" }}>
            <span style={{ background: TONE[x.status][0], color: TONE[x.status][1], borderRadius: 4, padding: "1px 8px", fontWeight: 600, fontSize: 12 }}>{x.status_label}</span>
            <b>{x.subject}</b><span style={{ color: "#4b5563" }}>{x.section}</span>
          </div>
          <div style={{ marginTop: 3 }}>{x.current} → <b>{x.target}</b> · asked by {x.requested_by}{x.reason ? ` — “${x.reason}”` : ""}</div>
          {x.decision_note && <div style={{ marginTop: 3, color: "#4b5563" }}>{x.decided_by ? `${x.decided_by}: ` : ""}{x.decision_note}</div>}
          {x.status === "pending" && isRegistrar && (
            <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
              <input aria-label={`Note for request ${x.id}`} placeholder="Note (optional)" value={notes[x.id] || ""} maxLength={300}
                onChange={(e) => setNotes((n) => ({ ...n, [x.id]: e.target.value }))}
                style={{ flex: "1 1 180px", fontSize: 13, padding: "4px 6px", borderRadius: 6, border: "1px solid #d1d5db" }} />
              <button style={btn} disabled={!!busy} onClick={() => act(x, "reject")}>{busy === `${x.id}-reject` ? "…" : "Reject"}</button>
              <button style={{ ...btnPrimary, background: "#16a34a", border: "1px solid #16a34a" }} disabled={!!busy} onClick={() => act(x, "approve")}
                title="Moves only this Gen Ed class, after re-checking every schedule now">{busy === `${x.id}-approve` ? "Checking…" : "Approve & move"}</button>
            </div>
          )}
          {x.status === "pending" && !isRegistrar && (
            <div style={{ marginTop: 6 }}><button style={btn} disabled={!!busy} onClick={() => act(x, "cancel")}>Cancel request</button></div>
          )}
        </div>
      ))}
    </div>
  );
}
