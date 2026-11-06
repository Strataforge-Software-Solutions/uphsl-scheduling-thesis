import React from "react";

/* Warning pop-up shown when a day / time change clashes with another class. Lists each clash and offers the
   free start times on the chosen day; the caller keeps which one is picked and applies it. */
export const DAY_NAMES = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };
const overlay = { position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", display: "flex", alignItems: "center", justifyContent: "center", padding: "12px", zIndex: 1100 };

export default function ClashDialog({ clash, picked, onPick, onBack, onApply, busy, applyLabel = "Move with these times" }) {
  if (!clash) return null;
  const idKey = (c) => [...c.ids].sort((a, b) => a - b).join("-");
  const toMin = (t) => { const [h, m] = String(t || "0:0").split(":"); return Number(h) * 60 + Number(m); };
  const shares = (a, b) => (a.section_id && a.section_id === b.section_id)
    || (a.teacher_ids || []).some((x) => (b.teacher_ids || []).includes(x))
    || (a.room_ids || []).some((x) => (b.room_ids || []).includes(x));
  // an option is unavailable when it overlaps the time already chosen for ANOTHER selected class that
  // has the same section, teacher or room (two classes of one section cannot meet at the same time)
  const takenBy = (c, s) => clash.conflicts.find((o) => o !== c && picked[idKey(o)] && shares(c, o)
    && toMin(s.start_time) < toMin(picked[idKey(o)].end_time) && toMin(picked[idKey(o)].start_time) < toMin(s.end_time));
  const allPicked = clash.conflicts.every((c) => picked[idKey(c)]);
  return (
    <div style={overlay}>
      <div role="alertdialog" style={{ background: "white", borderRadius: 6, padding: "22px", width: "560px", maxWidth: "100%", maxHeight: "90vh", overflowY: "auto", borderTop: "5px solid #d97706" }}>
        <h3 style={{ margin: 0, color: "#92400e" }}>Schedule conflict</h3>
        <p style={{ margin: "6px 0 12px", fontSize: "13px", color: "#4b5563" }}>
          Nothing was changed. {clash.conflicts.length} class{clash.conflicts.length > 1 ? "es" : ""} clash{clash.conflicts.length > 1 ? "" : "es"} on {DAY_NAMES[clash.day] || clash.day}. Pick a time for each. A faded dashed time overlaps another class you picked: click it to switch (the other choice is cleared).
        </p>
        {clash.conflicts.map((c) => (
          <div key={idKey(c)} style={{ border: "1px solid #fde68a", background: "#fffbeb", borderRadius: 6, padding: "10px 12px", marginBottom: "10px" }}>
            <div style={{ fontWeight: 600, fontSize: "14px" }}>{c.label}</div>
            {c.messages.slice(0, 2).map((m, i) => <div key={i} style={{ fontSize: "13px", color: "#92400e", marginTop: "3px" }}>{m}</div>)}
            <div style={{ marginTop: "8px", fontSize: "12px", color: "#4b5563" }}>Available times:</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "4px" }}>
              {c.suggestions.length === 0 && <span style={{ fontSize: "13px", color: "#b91c1c" }}>No free time on this day. Try another day.</span>}
              {c.suggestions.map((s) => {
                const on = picked[idKey(c)]?.start_time === s.start_time;
                const other = !on && takenBy(c, s);
                return (
                  <button key={s.start_time} onClick={() => { if (other) onPick(other, null); onPick(c, s); }}
                          title={other ? `Overlaps the time chosen for ${other.label}. Clicking it clears that choice so you can pick this one.` : undefined}
                          style={{ padding: "5px 10px", borderRadius: "4px", fontSize: "13px", cursor: "pointer",
                                   border: on ? "1px solid #003366" : "1px solid #d1d5db", background: on ? "#003366" : "white",
                                   color: on ? "white" : other ? "#6b7280" : "#111827", textDecoration: "none", borderStyle: other ? "dashed" : "solid" }}>
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "14px" }}>
          <button onClick={onBack} style={{ background: "white", color: "#111827", border: "1px solid #d1d5db", padding: "9px 18px", borderRadius: "6px", cursor: "pointer" }}>Back</button>
          <button onClick={onApply} disabled={busy || !allPicked}
                  style={{ background: allPicked ? "#003366" : "#6b7280", color: "white", border: "none", padding: "9px 20px", borderRadius: "6px", fontWeight: 600, cursor: allPicked ? "pointer" : "default" }}>
            {busy ? "Applying…" : applyLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
