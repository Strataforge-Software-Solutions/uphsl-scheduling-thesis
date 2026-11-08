import CustomSelect from "./CustomSelect";
import CustomTimePicker from "./CustomTimePicker";
import React, { useEffect, useMemo, useRef, useState } from "react";
import API from "../services/api";
import { formatTime } from "../utils/formatDateTime";

/* Dean: change the day and time of one or more classes, ONE CLASS AT A TIME.
   Click a class on the left, choose its day and time on the right (free times are suggested), then click the
   next class. Every choice is checked live against the teacher, room and students of every other class,
   including the other classes you are moving in this same window. Nothing is saved until "Save"; classes you
   did not touch stay exactly as they were. */
const idKey = (ids) => [...ids].sort((a, b) => a - b).join("-");
const DAYS = [["Mon", "Monday"], ["Tue", "Tuesday"], ["Wed", "Wednesday"], ["Thu", "Thursday"], ["Fri", "Friday"], ["Sat", "Saturday"]];
const DAY_SHORT = Object.fromEntries(DAYS.map(([c]) => [c, c]));
const hhmm = (t) => String(t || "").slice(0, 5);
const to12 = (t) => formatTime(hhmm(t));
const box = { padding: "8px 10px", borderRadius: "6px", border: "1px solid #d1d5db", fontSize: "14px", boxSizing: "border-box" };
const overlay = { position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: "12px", zIndex: 1000 };
const chip = (on, bad) => ({ padding: "5px 10px", borderRadius: 4, fontSize: "13px", cursor: "pointer", border: on ? "1px solid #003366" : "1px solid #d1d5db",
  background: on ? "#003366" : "white", color: on ? "white" : bad ? "#b91c1c" : "#111827" });

export default function MoveClassesModal({ groups, describe, onClose, onDone }) {
  const [plan, setPlan] = useState({});              // group.key -> {day, start}   (only classes the dean has set)
  const [active, setActive] = useState(groups[0]?.key);
  const [result, setResult] = useState({});          // idKey -> {ok, messages, suggestions} from the live check
  const [checking, setChecking] = useState(false);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);

  const byKey = useMemo(() => Object.fromEntries(groups.map((g) => [g.key, g])), [groups]);
  const current = byKey[active];
  const planned = groups.filter((g) => plan[g.key]);
  const itemsOf = (keys) => keys.map((k) => ({ ids: byKey[k].ids, day: plan[k].day, start_time: plan[k].start }));

  // ONE live check at a time (a check temporarily moves the classes inside a transaction and rolls back):
  // everything that has been set, plus the class being edited so it can list its free times.
  const [draftDay, setDraftDay] = useState({});
  const [draftOpts, setDraftOpts] = useState({});
  const dayOf = (g) => plan[g.key]?.day || draftDay[g.key] || g.timeslot_day;
  useEffect(() => {
    const keys = Object.keys(plan).filter((k) => plan[k]?.start);
    const draft = current && !plan[current.key] ? current : null;
    if (!keys.length && !draft) { setResult({}); return; }
    const mine = ++seq.current;
    setChecking(true);
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const items = keys.map((k) => ({ ids: byKey[k].ids, day: plan[k].day, start_time: plan[k].start }));
        if (draft) items.push({ ids: draft.ids, day: dayOf(draft), start_time: hhmm(draft.start) });
        const res = await API.post("/engine/reschedule/", { preview: true, items }, { signal: ctl.signal });
        if (mine !== seq.current) return;
        const next = {};
        (res.data.items || []).forEach((i) => { next[idKey(i.ids)] = i; });
        setResult(next);
        if (draft) setDraftOpts((o) => ({ ...o, [draft.key]: { day: dayOf(draft), suggestions: next[idKey(draft.ids)]?.suggestions || [] } }));
        setError(""); setFailed(false);
      } catch (e) {
        if (mine !== seq.current || e.code === "ERR_CANCELED" || e.name === "CanceledError") return;
        setError(e.response?.data?.detail || "Could not check the schedule. Press Retry.");
        setFailed(true);
      } finally { if (mine === seq.current) setChecking(false); }
    }, 120);
    return () => { clearTimeout(t); ctl.abort(); };           // a newer choice cancels the older check
  }, [plan, active, draftDay, retry]);   // eslint-disable-line react-hooks/exhaustive-deps

  const res = current ? result[idKey(current.ids)] : null;
  const opts = current ? (plan[current.key] ? res?.suggestions : (draftOpts[current.key]?.day === dayOf(current) ? draftOpts[current.key].suggestions : null)) : null;
  const clashes = planned.filter((g) => result[idKey(g.ids)] && !result[idKey(g.ids)].ok);
  const unknown = planned.some((g) => !result[idKey(g.ids)]);
  const canSave = planned.length > 0 && clashes.length === 0 && !unknown && !checking && !busy;

  const setFor = (g, patch) => setPlan((p) => ({ ...p, [g.key]: { day: dayOf(g), start: hhmm(g.start), ...(p[g.key] || {}), ...patch } }));
  const clear = (g) => setPlan((p) => { const n = { ...p }; delete n[g.key]; return n; });
  const nextClass = () => {
    const i = groups.findIndex((g) => g.key === active);
    const order = [...groups.slice(i + 1), ...groups.slice(0, i)];
    const nxt = order.find((g) => !plan[g.key]) || order[0];
    if (nxt) setActive(nxt.key);
  };
  const save = async () => {
    setBusy(true); setError("");
    try {
      const r = await API.post("/engine/reschedule/", { items: itemsOf(planned.map((g) => g.key)) });
      onDone(r.data);
    } catch (e) {
      setError(e.response?.status === 409 ? "Something changed while you were editing; a time is no longer free. Check the marked classes." : (e.response?.data?.detail || "Could not save the schedule."));
    } finally { setBusy(false); }
  };

  const state = (g) => {
    const r = result[idKey(g.ids)];
    if (!plan[g.key]) return { text: "Unchanged", bg: "#f3f4f6", fg: "#6b7280" };
    if (r && !r.ok) return { text: "Conflict", bg: "#fee2e2", fg: "#b91c1c" };
    if (!r) return failed ? { text: "Not checked", bg: "#fee2e2", fg: "#b91c1c" } : { text: "Checking…", bg: "#fef9c3", fg: "#92400e" };
    return { text: "Ready", bg: "#dcfce7", fg: "#166534" };
  };

  return (
    <div style={overlay}>
      <div style={{ background: "white", borderRadius: 6, padding: "22px", width: "820px", maxWidth: "100%", maxHeight: "92vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "10px" }}>
          <div>
            <h3 style={{ margin: 0, color: "#003366" }}>Change day and time</h3>
            <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#6b7280" }}>
              Click a class, choose its day and time, then click the next class. Conflicts are checked as you go. Nothing is saved until you press Save.
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" style={{ border: "none", background: "none", fontSize: "16px", cursor: "pointer", color: "#6b7280" }}>Close</button>
        </div>

        <div style={{ display: "flex", gap: "16px", marginTop: "14px", flexWrap: "wrap" }}>
          {/* 1. the classes */}
          <div style={{ flex: "1 1 270px", minWidth: 0 }}>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "#4b5563", marginBottom: "6px" }}>1. Classes ({planned.length} of {groups.length} changed)</div>
            <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, maxHeight: "340px", overflowY: "auto" }}>
              {groups.map((g) => {
                const st = state(g); const sel = g.key === active; const pl = plan[g.key];
                return (
                  <button key={g.key} onClick={() => setActive(g.key)}
                          style={{ display: "block", width: "100%", textAlign: "left", padding: "9px 10px", border: "none", borderBottom: "1px solid #f3f4f6",
                                   background: sel ? "#eaf1fb" : "white", cursor: "pointer", borderLeft: sel ? "4px solid #003366" : "4px solid transparent" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "8px", alignItems: "center" }}>
                      <span style={{ fontSize: "13px", fontWeight: 600, color: "#111827" }}>{g.subject_title}</span>
                      <span style={{ fontSize: "12px", background: st.bg, color: st.fg, borderRadius: 4, padding: "2px 8px", whiteSpace: "nowrap" }}>{st.text}</span>
                    </div>
                    <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "2px" }}>
                      {g.section_name} · {describe(g)}{pl ? <span style={{ color: "#166534", fontWeight: 600 }}> → {DAY_SHORT[pl.day]} {to12(pl.start)}</span> : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 2. day and time for the active class */}
          <div style={{ flex: "1 1 340px", minWidth: 0 }}>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "#4b5563", marginBottom: "6px" }}>2. Day and time</div>
            {current && (
              <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "12px" }}>
                <div style={{ fontWeight: 600, fontSize: "14px" }}>{current.subject_title} · {current.section_name}</div>
                <div style={{ fontSize: "12px", color: "#6b7280", margin: "2px 0 10px" }}>
                  Now: {describe(current)} · {current.room_name} · {current.teacher_name}
                </div>
                <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                  <div style={{ flex: "1 1 140px" }}>
                    <label style={{ fontSize: "12px", fontWeight: 600 }}>Day</label>
                    <CustomSelect style={{ ...box, width: "100%", marginTop: "3px" }} value={dayOf(current)}
                            onChange={(e) => (plan[current.key] ? setFor(current, { day: e.target.value }) : setDraftDay((d) => ({ ...d, [current.key]: e.target.value })))}>
                      {DAYS.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                    </CustomSelect>
                  </div>
                  <div style={{ flex: "1 1 140px" }}>
                    <label style={{ fontSize: "12px", fontWeight: 600 }}>Start time</label>
                    <CustomTimePicker style={{ ...box, width: "100%", marginTop: "3px" }} value={plan[current.key]?.start || ""}
                           onChange={(e) => e.target.value && setFor(current, { start: e.target.value })} aria-label="Start time" />
                  </div>
                </div>

                <div style={{ marginTop: "12px", fontSize: "12px", color: "#4b5563" }}>Free times on {DAYS.find(([c]) => c === dayOf(current))?.[1]} (click one):</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "5px", minHeight: "30px" }}>
                  {opts === null || opts === undefined ? (failed
                      ? <span style={{ fontSize: "13px", color: "#b91c1c" }}>Could not load free times. <button onClick={() => setRetry((n) => n + 1)} style={{ border: "1px solid #d1d5db", background: "white", borderRadius: "6px", padding: "2px 8px", cursor: "pointer" }}>Retry</button></span>
                      : <span style={{ fontSize: "13px", color: "#6b7280" }}>Looking for free times…</span>)
                    : opts.length === 0 ? <span style={{ fontSize: "13px", color: "#b91c1c" }}>No free time on this day. Try another day.</span>
                    : opts.map((s) => (
                      <button key={s.start_time} style={chip(plan[current.key]?.start === s.start_time)}
                              onClick={() => setFor(current, { start: s.start_time })}>{s.label}</button>
                    ))}
                </div>

                {plan[current.key] && res && (
                  res.ok
                    ? <div style={{ marginTop: "10px", background: "#ecfdf5", border: "1px solid #a7f3d0", color: "#166534", borderRadius: 6, padding: "7px 10px", fontSize: "13px" }}>
                        No conflict: teacher, room and students are free at {DAY_SHORT[plan[current.key].day]} {to12(plan[current.key].start)}.
                      </div>
                    : <div style={{ marginTop: "10px", background: "#fffbeb", border: "1px solid #fde68a", color: "#92400e", borderRadius: 6, padding: "7px 10px", fontSize: "13px" }}>
                        <strong>Conflict.</strong> {res.messages.map((m, i) => <div key={i}>{m}</div>)}
                        <div style={{ marginTop: "4px" }}>Pick one of the free times above.</div>
                      </div>
                )}

                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "12px", gap: "8px" }}>
                  <button onClick={() => clear(current)} disabled={!plan[current.key]}
                          style={{ background: "white", color: "#4b5563", border: "1px solid #d1d5db", padding: "7px 12px", borderRadius: "6px", cursor: plan[current.key] ? "pointer" : "default", opacity: plan[current.key] ? 1 : 0.5 }}>
                    Keep original
                  </button>
                  {groups.length > 1 && (
                    <button onClick={nextClass} style={{ background: "#eaf1fb", color: "#003366", border: "1px solid #bcd0ea", padding: "7px 14px", borderRadius: "6px", fontWeight: 600, cursor: "pointer" }}>
                      Next class
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {error && <p style={{ color: "#b91c1c", fontSize: "13px", marginBottom: 0 }}>{error} {failed && <button onClick={() => setRetry((n) => n + 1)} style={{ border: "1px solid #d1d5db", background: "white", borderRadius: "6px", padding: "2px 8px", cursor: "pointer" }}>Retry</button>}</p>}
        {clashes.length > 0 && <p style={{ color: "#92400e", fontSize: "13px", marginBottom: 0 }}>Resolve the conflict{clashes.length > 1 ? "s" : ""} first: {clashes.map((g) => g.subject_title).join(", ")}.</p>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "16px" }}>
          <button onClick={onClose} style={{ background: "white", color: "#111827", border: "1px solid #d1d5db", padding: "9px 18px", borderRadius: "6px", cursor: "pointer" }}>Cancel</button>
          <button onClick={save} disabled={!canSave}
                  style={{ background: canSave ? "#003366" : "#6b7280", color: "white", border: "none", padding: "9px 20px", borderRadius: "6px", fontWeight: 600, cursor: canSave ? "pointer" : "default" }}>
            {busy ? "Saving…" : planned.length ? `Save ${planned.length} change${planned.length > 1 ? "s" : ""}` : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
