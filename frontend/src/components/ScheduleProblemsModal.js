import React, { useEffect, useState } from "react";
import API, { getCurrentUser } from "../services/api";
import { formatTime } from "../utils/formatDateTime";

/* One pop-up for everything the generator could not settle: classes that were not placed and clashes with existing classes.
   Each row shows the subject code and name, year level, section, why it is a problem, and the room and time it has now.
   Nothing is fixed automatically. For a class that was not placed, the room and Start / End Time chosen before generating are shown, and
   the free days and times in THAT room are looked up right away (inside the chosen time first). The Dean / Registrar picks one and
   confirms; the server checks it again before saving. If nothing is free the problem stays and the reason is shown. */
const C = { navy: "#003366", line: "#e5e7eb", bad: "#b91c1c", warn: "#7a4b00", ok: "#166534" };
const btn = (bg, fg = "#fff") => ({ background: bg, color: fg, border: bg === "#fff" ? `1px solid ${C.navy}` : "none", borderRadius: 6, padding: "6px 14px", fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" });
const t12 = (hhmm) => formatTime(hhmm);
const split = (s) => { const t = String(s || ""); const i = t.indexOf(" "); return i < 0 ? [t, ""] : [t.slice(0, i), t.slice(i + 1)]; };

// "BS Computer Science 3rd Year - A3" already carries the year level: show it once, as "BS Computer Science · 3rd Year · A3"
const sectionText = (year, section) => {
  const t = String(section || "");
  const m = t.match(/^(.*?)\s+(\d(?:st|nd|rd|th) Year)\s*-\s*(.+)$/);
  if (m) return `${m[1]} · ${m[2]} · Section ${m[3]}`;
  return `${year ? `${year} · ` : ""}${t}`;
};
// may the signed-in user move this class? (the server decides again): the Registrar owns Gen Ed, a Dean owns the majors of their own college
const ownsClass = (x) => {
  const u = getCurrentUser() || {};
  if (u.role === "registrar") return x.classification === "minor";
  if (u.role === "faculty" && u.faculty_type === "dean") return x.classification !== "minor" && (u.departments || [u.department]).includes(x.department);
  return false;
};
const ownerName = (x) => (x.classification === "minor" ? "the Registrar (Gen Ed)" : `the Dean of ${x.department}`);

function Facts({ code, title, year, section, reason, room, when, tone, chosen }) {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.5, minWidth: 0 }}>
      <div><strong>{code}</strong> {title}</div>
      <div style={{ color: "#4b5563" }}>{sectionText(year, section)}</div>
      {chosen ? (
        <div style={{ color: C.navy }}>
          <span>Your room: <strong>{chosen.room || "Automatic"}</strong></span>
          {" · "}<span>Your time: <strong>{chosen.start || chosen.end ? `${t12(chosen.start) || "any"} – ${t12(chosen.end) || "any"}` : "Any time"}</strong></span>
        </div>
      ) : (
        <div style={{ color: C.navy, fontWeight: 600 }}>{room ? `Room ${room}` : "Room: automatic"} · {when || "No day and time yet"}</div>
      )}
      <div style={{ color: tone === "warn" ? C.warn : C.bad, margin: "2px 0" }}><strong>Why:</strong> {reason || "no free day and time was found"}</div>
    </div>
  );
}

export default function ScheduleProblemsModal({ clashes, unplaced, yearLevel, picks = {}, onClose, onFixed, startWith = null }) {
  // startWith: {request: {ids}, reason} -- open directly on ONE class (used by Edit > "Choose a new day and time")
  const [target, setTarget] = useState(null);     // {request:{ids|section_id,subject_id}, done(): update the lists}
  const [data, setData] = useState(null);
  const [choice, setChoice] = useState("");
  const [splitMode, setSplitMode] = useState(false);
  const [splitData, setSplitData] = useState(null);
  const [sessionChoices, setSessionChoices] = useState(["", ""]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const [why, setWhy] = useState("");              // the reason this class is a problem (from generation / the clash)
  const [extra, setExtra] = useState(null);        // server extras of a refusal (qualified replacements ...)
  // the request used to look up free times for one unplaced class: its chosen room and Start / End Time
  const reqFor = (u) => {
    const roomId = u.chosen_room_id || picks[u.subject_id]?.room;
    return { section_id: u.section_id, subject_id: u.subject_id, ...(roomId ? { room_id: Number(roomId) } : {}),
      start: u.chosen_start || picks[u.subject_id]?.start || "", end: u.chosen_end || picks[u.subject_id]?.end || "" };
  };
  const [preview, setPreview] = useState({});     // "section-subject" -> {options, outside, rooms, reason} | {error}
  const ukey = (u) => `${u.section_id}-${u.subject_id}`;
  useEffect(() => {
    let alive = true;
    (async () => {
      for (const u of unplaced) {           // one at a time: each look-up checks every day and time on the server
        if (!alive) return;
        try {
          const r = (await API.post("/engine/slot-options/", { ...reqFor(u), limit: 6 })).data;
          if (alive) setPreview((p) => ({ ...p, [ukey(u)]: { options: r.options || [], outside: r.outside_options || [], rooms: r.room_options || [], reason: r.reason } }));
        } catch (e) {
          if (alive) setPreview((p) => ({ ...p, [ukey(u)]: { error: e.response?.data?.detail || "Could not look up free times." } }));
        }
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unplaced.length]);

  const open = async (request, done, reason, preselect = "") => {
    setBusy("load"); setError(""); setNote(""); setChoice(preselect); setSplitMode(false); setSplitData(null); setSessionChoices(["", ""]);
    setData(null); setExtra(null); setWhy(reason || ""); setTarget({ request, done });
    try {
      const r = await API.post("/engine/slot-options/", request);
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Could not look up free times.");
      setExtra(e.response?.data || null);
      if (e.response?.data?.already_placed) { done(); }
    } finally { setBusy(""); }
  };
  useEffect(() => {
    if (startWith) open(startWith.request, () => {}, startWith.reason);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const confirm = async () => {
    setBusy("apply"); setError("");
    try {
      const body = splitMode
        ? { ...target.request, split_session: true, session_keys: sessionChoices }
        : { ...target.request, key: choice };
      const r = await API.post("/engine/slot-options/apply/", body);
      setNote(r.data.summary);
      target.done();
      if (onFixed) onFixed(r.data);
      setTarget(null); setData(null);
    } catch (e) {
      setError(e.response?.data?.detail || "Could not apply that time.");
      if (e.response?.data?.refresh) {
        setChoice(""); setSessionChoices(["", ""]);
        try {
          if (splitMode) setSplitData((await API.post("/engine/slot-options/", { ...target.request, split_session: true })).data);
          else setData((await API.post("/engine/slot-options/", target.request)).data);
        } catch (_e) { /* keep old list */ }
      }
    } finally { setBusy(""); }
  };

  const group = (list) => { const g = {}; (list || []).forEach((o) => { (g[o.days.join(" & ")] = g[o.days.join(" & ")] || []).push(o); }); return g; };
  const all = data ? [...data.options, ...(data.outside_options || []), ...(data.room_options || [])] : [];
  const picked = all.find((o) => o.key === choice);
  const anyOption = all.length > 0;
  const splitOptions = splitData ? [...(splitData.options || []), ...(splitData.outside_options || []), ...(splitData.room_options || [])] : [];
  const bySessionKey = (key) => splitOptions.find((o) => o.key === key);
  const firstSession = bySessionKey(sessionChoices[0]);
  const clockMinutes = (value) => { const [h, m] = String(value || "0:0").split(":").map(Number); return h * 60 + m; };
  const secondSessionOptions = firstSession ? splitOptions.filter((o) => {
    if (o.teacher_id !== firstSession.teacher_id || o.room_id !== firstSession.room_id) return false;
    const overlap = o.day === firstSession.day && Math.max(clockMinutes(o.start), clockMinutes(firstSession.start)) < Math.min(clockMinutes(o.end), clockMinutes(firstSession.end));
    return !overlap;
  }) : splitOptions;
  const splitCanApply = Boolean(sessionChoices[0] && sessionChoices[1] && secondSessionOptions.some((o) => o.key === sessionChoices[1]));
  const visibleReason = splitMode ? splitData?.reason : data?.reason;
  const visibleOptions = splitMode ? splitOptions : all;
  const selectSplitMode = async () => {
    if (!data?.split_allowed || !target) return;
    setBusy("load-split"); setError(""); setSessionChoices(["", ""]);
    try {
      setSplitData((await API.post("/engine/slot-options/", { ...target.request, split_session: true })).data);
      setSplitMode(true);
    } catch (e) {
      setError(e.response?.data?.detail || "Could not look up 1.5-hour sessions.");
    } finally { setBusy(""); }
  };
  const renderSessionChoices = (index, list) => (
    <>
      {Object.entries(group(list)).map(([day, items]) => (
        <div key={`${index}-${day}`} style={{ marginBottom: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: C.navy, marginBottom: 4 }}>{day}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {items.map((o) => (
              <label key={o.key} style={{ border: `1px solid ${sessionChoices[index] === o.key ? C.navy : C.line}`, background: sessionChoices[index] === o.key ? "#e6f0fa" : "#fff", borderRadius: 6, padding: "6px 10px", fontSize: 13, cursor: "pointer" }}>
                <input type="radio" name={`session-${index}`} checked={sessionChoices[index] === o.key} onChange={() => setSessionChoices((prev) => {
                  const next = [...prev]; next[index] = o.key;
                  if (index === 0 && !splitOptions.some((candidate) => candidate.key === next[1]
                    && candidate.teacher_id === o.teacher_id && candidate.room_id === o.room_id
                    && !(candidate.day === o.day && Math.max(clockMinutes(candidate.start), clockMinutes(o.start)) < Math.min(clockMinutes(candidate.end), clockMinutes(o.end))))) next[1] = "";
                  return next;
                })} style={{ marginRight: 6 }} />
                {o.label}{o.room ? <> · <strong>{o.room}</strong></> : null}{o.teacher ? <> · {o.teacher}</> : null}
              </label>
            ))}
          </div>
        </div>
      ))}
    </>
  );
  const renderChips = (list, showRoom) => (
    <>
      {Object.entries(group(list)).map(([day, items]) => (
        <div key={day} style={{ marginBottom: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: C.navy, marginBottom: 4 }}>{day}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {items.map((o) => (
              <label key={o.key} style={{ border: `1px solid ${choice === o.key ? C.navy : C.line}`, background: choice === o.key ? "#e6f0fa" : "#fff", borderRadius: 6, padding: "6px 10px", fontSize: 13, cursor: "pointer" }}>
                <input type="radio" name="slot" checked={choice === o.key} onChange={() => setChoice(o.key)} style={{ marginRight: 6 }} />
                {o.label.replace(/^[A-Za-z &]+? (?=\d)/, "")}{showRoom ? <> · <strong>{o.room}</strong></> : null}
              </label>
            ))}
          </div>
        </div>
      ))}
    </>
  );

  return (
    <div role="dialog" aria-modal="true" aria-label="Scheduling problems" style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: 14 }}>
      <div style={{ background: "#fff", borderRadius: 6, width: "100%", maxWidth: 760, maxHeight: "90vh", display: "flex", flexDirection: "column", boxShadow: "var(--shadow-pop)" }}>
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${C.line}`, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          <h3 style={{ margin: 0, color: C.navy }}>{target || startWith ? "Choose a day and time" : "Classes that need your decision"}</h3>
          <button onClick={onClose} style={btn("#fff", C.navy)}>Close</button>
        </div>
        <div style={{ padding: "14px 18px", overflowY: "auto" }}>
          {note && <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", color: C.ok, borderRadius: 6, padding: "8px 12px", fontSize: 13, marginBottom: 10 }}>{note}</div>}

          {!target && (
            <>
              {!unplaced.length && !clashes.length && <p style={{ color: C.ok }}>Nothing left to resolve.</p>}
              {unplaced.length > 0 && (
                <>
                  <h4 style={{ margin: "0 0 4px" }}>Classes that need your choice ({unplaced.length})</h4>
                  <p style={{ margin: "0 0 8px", fontSize: 13, color: "#4b5563" }}>
                    These did not fit your room and time, so they were <strong>not</strong> placed and no other class was moved.
                    Click a suggested time (same room, inside your time first), check it, then confirm.
                  </p>
                </>
              )}
              {unplaced.map((u) => {
                const [code, title] = split(u.subject);
                const pv = preview[ukey(u)];
                const chosen = { room: u.chosen_room || "", start: u.chosen_start || picks[u.subject_id]?.start || "", end: u.chosen_end || picks[u.subject_id]?.end || "" };
                const done = () => onFixed && onFixed({ unplaced: u });
                const quick = pv && !pv.error ? [...pv.options.map((o) => [o, "in"]), ...pv.outside.map((o) => [o, "out"])].slice(0, 6) : [];
                return (
                  <div key={`u${ukey(u)}`} style={{ border: `1px solid ${C.line}`, borderRadius: 6, padding: "10px 12px", marginBottom: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                      <Facts code={code} title={title} year={u.year_level || yearLevel} section={u.section} reason={u.reason} tone="warn" chosen={chosen} />
                      <button style={btn("#0b6b3a")} onClick={() => open(reqFor(u), done, u.reason)}>See all free times</button>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 13 }}>
                      {!pv && <span style={{ color: "#6b7280" }}>Looking for free days and times…</span>}
                      {pv?.error && <span style={{ color: C.bad }}>{pv.error}</span>}
                      {quick.length > 0 && (
                        <>
                          <span style={{ color: "#374151", marginRight: 6 }}>Suggested:</span>
                          {quick.map(([o, where]) => (
                            <button key={o.key} onClick={() => open(reqFor(u), done, u.reason, o.key)} title={where === "out" ? "Outside your Start / End Time, same room" : "Inside your Start / End Time"}
                              style={{ border: `1px solid ${where === "out" ? "#fde68a" : "#bbf7d0"}`, background: where === "out" ? "#fffbeb" : "#f0fdf4", color: "#111827", borderRadius: 6, padding: "2px 10px", margin: "2px 4px 2px 0", fontSize: 12, cursor: "pointer" }}>
                              {o.label}{o.room ? ` · ${o.room}` : ""}{where === "out" ? " (outside your time)" : ""}
                            </button>
                          ))}
                        </>
                      )}
                      {pv && !pv.error && !quick.length && (
                        <span style={{ color: C.bad }}>{pv.rooms.length ? "No free time in this room. Other rooms are possible: open \u201cSee all free times\u201d." : (pv.reason || "No free day and time was found.")}</span>
                      )}
                    </div>
                  </div>
                );
              })}
              {clashes.length > 0 && (
                <>
                  <h4 style={{ margin: unplaced.length ? "14px 0 4px" : "0 0 4px" }}>Conflicts ({clashes.length})</h4>
                  <p style={{ margin: "0 0 8px", fontSize: 13, color: "#4b5563" }}>
                    Two classes use the same teacher, room or students at the same time. Choose which of the two to move: you see only the
                    days and times that are really free for it (same room first). Nothing changes until you confirm.
                  </p>
                </>
              )}
              {clashes.map((c, i) => (
                <div key={`c${i}`} style={{ border: `1px solid ${C.line}`, borderRadius: 6, padding: "10px 12px", marginBottom: 8 }}>
                  <div style={{ fontSize: 13, marginBottom: 6 }}><strong style={{ color: C.bad }}>{c.kind_label} conflict</strong> — {c.message}</div>
                  {[c.a, c.b].map((x, j) => (
                    <div key={j} style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start", padding: "6px 0", borderTop: j ? `1px dashed ${C.line}` : "none" }}>
                      <Facts code={x.code} title={x.title} year={x.year_level} section={x.section} reason={`${c.kind_label} clash with ${j ? c.a.code : c.b.code}`} room={x.room} when={x.time} />
                      {!ownsClass(x)
                        ? <span style={{ fontSize: 12, color: "#6b7280", maxWidth: 170, textAlign: "right" }}>Owned by {ownerName(x)}. They move this side.</span>
                        : (x.status && x.status !== "draft")
                          ? <span style={{ fontSize: 12, color: "#6b7280", maxWidth: 170, textAlign: "right" }}>{x.status === "published" ? "Published" : "Approved"}: never moved. Move it back to Draft first, or move the other class.</span>
                          : x.shared
                            ? <span style={{ fontSize: 12, color: "#6b7280", maxWidth: 170, textAlign: "right" }}>Shared class (several programs): not moved from here.</span>
                            : <button style={btn("#0b6b3a")} onClick={() => open({ ids: x.ids }, () => onFixed && onFixed({ clash: i }), `${c.kind_label} clash with ${j ? c.a.code : c.b.code}`)}>Show free times</button>}
                    </div>
                  ))}
                </div>
              ))}
            </>
          )}

          {target && (
            <>
              {!startWith && <button onClick={() => { setTarget(null); setData(null); setError(""); }} style={{ ...btn("#fff", C.navy), marginBottom: 10 }}>Back to the list</button>}
              {busy === "load" && <p>Checking every day and time…</p>}
              {data && (
                <>
                  <div style={{ border: `1px solid ${C.line}`, borderRadius: 6, padding: "10px 12px", marginBottom: 10, background: "#f9fafb" }}>
                    <Facts code={data.class.code} title={data.class.title} year={data.class.year_level} section={data.class.section}
                      reason={why || (data.mode === "place" ? "No day and time yet" : "Needs a new day or time")} room={data.room.name} when={data.class.when} tone="warn" />
                    <div style={{ fontSize: 13, color: "#374151", marginTop: 4 }}>
                      Room <strong>{data.room.name || "(none yet)"}</strong> stays the same. {data.room.note}
                      {data.class.teacher ? ` Teacher: ${data.class.teacher}.` : ""} Only times when the teacher is available and free, the room is free and the students have no other class are listed.
                    </div>
                  </div>
                  {data.split_allowed && (
                    <div style={{ display: "flex", gap: 8, margin: "6px 0 12px", flexWrap: "wrap" }}>
                      <button type="button" onClick={() => { setSplitMode(false); setSplitData(null); setSessionChoices(["", ""]); }} style={btn(!splitMode ? C.navy : "#fff", !splitMode ? "#fff" : C.navy)}>One 3-hour session</button>
                      <button type="button" disabled={busy === "load-split"} onClick={selectSplitMode} style={{ ...btn(splitMode ? C.navy : "#fff", splitMode ? "#fff" : C.navy), opacity: busy === "load-split" ? 0.6 : 1 }}>
                        {busy === "load-split" ? "Loading sessions…" : "Two 1.5-hour sessions"}
                      </button>
                    </div>
                  )}
                  {!splitMode && data.options.length > 0 && <><div style={{ fontWeight: 600, fontSize: 13, margin: "4px 0", color: C.ok }}>{data.room.name ? `1. Free in ${data.room.name}, inside your time (recommended)` : "Free times"}</div>{renderChips(data.options, !data.room.kept)}</>}
                  {!splitMode && (data.outside_options || []).length > 0 && <><div style={{ fontWeight: 600, fontSize: 13, margin: "8px 0 4px", color: C.warn }}>2. Same room {data.room.name}, outside your Start / End Time</div>{renderChips(data.outside_options, false)}</>}
                  {!splitMode && (data.room_options || []).length > 0 && <><div style={{ fontWeight: 600, fontSize: 13, margin: "8px 0 4px", color: C.warn }}>3. Other free rooms (allowed for this subject; the room changes only if you confirm)</div>{renderChips(data.room_options, true)}</>}
                  {splitMode && splitData && <>
                    <div style={{ fontWeight: 600, fontSize: 13, margin: "4px 0", color: C.ok }}>Choose the first 1.5-hour session</div>
                    {renderSessionChoices(0, splitOptions)}
                    <div style={{ fontWeight: 600, fontSize: 13, margin: "8px 0 4px", color: C.ok }}>Choose the second 1.5-hour session</div>
                    {firstSession ? renderSessionChoices(1, secondSessionOptions) : <p style={{ color: "#6b7280", fontSize: 13 }}>Choose the first session to see compatible times for the second.</p>}
                    {!splitOptions.length && !splitData.half_hour_slots_available && <p style={{ color: C.bad, fontSize: 13 }}>Half-hour time slots have not been seeded. Ask your system administrator to run the time-slot seeder before using split sessions.</p>}
                    {!splitOptions.length && splitData.half_hour_slots_available && <p style={{ color: C.bad, fontSize: 13 }}>{splitData.reason || "No free 1.5-hour sessions are available."}</p>}
                    {firstSession && !secondSessionOptions.length && <p style={{ color: C.bad, fontSize: 13 }}>No other non-overlapping 1.5-hour session is available with the same teacher and room.</p>}
                  </>}
                  {visibleReason && <div style={{ background: visibleOptions.length ? "#fffbeb" : "#fef2f2", border: `1px solid ${visibleOptions.length ? "#fde68a" : "#fecaca"}`, color: visibleOptions.length ? "#7a4b00" : "#991b1b", borderRadius: 6, padding: "10px 12px", fontSize: 13, marginTop: 6 }}>{visibleReason}</div>}
                </>
              )}
              {error && <p style={{ color: C.bad, fontSize: 13 }}>{error}</p>}
              {extra?.replacements?.length > 0 && (
                <div style={{ background: "#f9fafb", border: `1px solid ${C.line}`, borderRadius: 6, padding: "8px 12px", fontSize: 13 }}>
                  <strong>Possible replacements (related degree or training, not yet recorded as a specialization):</strong>
                  <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>{extra.replacements.map((r) => <li key={r.faculty_id}>{r.name} — {r.fit}</li>)}</ul>
                </div>
              )}
              {((splitMode && splitCanApply) || (!splitMode && anyOption)) && (
                <div style={{ textAlign: "right", marginTop: 10 }}>
                  <button disabled={splitMode ? (!splitCanApply || busy === "apply") : (!choice || busy === "apply")} onClick={confirm} style={{ ...btn(C.navy), opacity: splitMode ? (splitCanApply ? 1 : 0.5) : (choice ? 1 : 0.5) }}>{busy === "apply" ? "Checking and saving…" : !splitMode && picked?.room_changed ? `Apply / Confirm (room changes to ${picked.room})` : "Apply / Confirm"}</button>
                </div>
              )}
            </>
          )}
          {!target && error && <p style={{ color: C.bad, fontSize: 13 }}>{error}</p>}
        </div>
      </div>
    </div>
  );
}
