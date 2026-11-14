import React, { useEffect, useMemo, useRef, useState } from "react";
import usePopupPresence from "./usePopupPresence";

/* The Room dropdown used by every scheduling screen (Dean, Registrar, SHS / JHS Principal).
   - a search box at the top filters by room name, label, building or room number ("309", "D-309", "309D", "lab c", "alta");
   - every room shows its name and capacity: "201M (45)";
   - the first option ("Automatic" by default) leaves the choice to the scheduling engine;
   - nothing is validated here: the server still checks availability, capacity and conflicts when the choice is saved. */
const norm = (s) => String(s == null ? "" : s).toLowerCase().replace(/[^a-z0-9]/g, "");

export function roomLabel(r) {
  const raw = r.text || r.name || [r.building, r.room_number].filter(Boolean).join(" ") || `Room ${r.id}`;
  const base = raw.replace(/^Demo room \((.*)\)$/, "$1").replace(/ \(([^()]*)\)$/, " – $1");   // "Comp Lab D (309D)" -> "Comp Lab D – 309D"
  return r.capacity != null ? `${base} (${r.capacity})` : base;
}

const BUILDING_NAME = { M: "Main Building", D: "Alta Building", N: "New Building", A: "Alfredo Building" };

export function roomMatches(r, query) {
  const q = norm(query);
  if (!q) return true;
  const hay = [r.text, r.name, r.label, r.building, r.room_number, BUILDING_NAME[r.building], r.code, `${r.building || ""}${r.room_number || ""}`, `${r.room_number || ""}${r.building || ""}`, r.department]
    .map(norm).join("|");
  return hay.includes(q);
}

export default function RoomSelect({
  rooms = [], value = "", onChange, autoLabel = "Automatic", allowAuto = true, groupBy = null, suffix = null, isDisabled = null,
  style = {}, ariaLabel = "Room", width = 190,
}) {
  const [open, setOpen] = useState(false);
  const { present: menuPresent, closing: menuClosing } = usePopupPresence(open);
  const [q, setQ] = useState("");
  const [pos, setPos] = useState(null);
  const btn = useRef(null), panel = useRef(null), input = useRef(null);
  const current = rooms.find((r) => String(r.id) === String(value));

  useEffect(() => {
    if (!open) return undefined;
    // My settings > Text size zooms the work area; positions from the screen are divided by that zoom
    const zoomed = btn.current.closest(".app-shell, .settings-page");
    const z = (zoomed && parseFloat(window.getComputedStyle(zoomed).zoom)) || 1;
    const b = btn.current.getBoundingClientRect();
    const r = { left: b.left / z, top: b.top / z, bottom: b.bottom / z, width: b.width / z };
    const vw = window.innerWidth / z, vh = window.innerHeight / z;
    const below = vh - r.bottom;
    const w = Math.min(Math.max(r.width, 260), vw - 16);          // the list stays on screen on a narrow window
    setPos({ left: Math.max(8, Math.min(r.left, vw - w - 8)), top: below > 280 ? r.bottom + 2 : undefined, bottom: below > 280 ? undefined : vh - r.top + 2, width: w });
    const away = (e) => { if (!panel.current?.contains(e.target) && !btn.current?.contains(e.target)) setOpen(false); };
    const close = (e) => { if (!panel.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", away);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => { document.removeEventListener("mousedown", away); window.removeEventListener("scroll", close, true); window.removeEventListener("resize", close); };
  }, [open]);
  useEffect(() => { if (open && menuPresent) input.current?.focus(); }, [open, menuPresent]);

  const shown = useMemo(() => rooms.filter((r) => roomMatches(r, q) || (String(r.id) === String(value) && !q)), [rooms, q, value]);
  const groups = useMemo(() => {
    if (!groupBy) return [[null, shown]];
    const m = new Map();
    shown.forEach((r) => { const g = groupBy(r) || ""; if (!m.has(g)) m.set(g, []); m.get(g).push(r); });
    return [...m.entries()];
  }, [shown, groupBy]);

  const pick = (id) => { onChange(String(id)); setOpen(false); setQ(""); };
  const text = current ? roomLabel(current) + (suffix ? suffix(current) : "") : (allowAuto ? autoLabel : "— Select room —");
  const row = { display: "block", width: "100%", textAlign: "left", border: "none", background: "none", boxShadow: "none", margin: 0, borderRadius: 0, padding: "6px 10px", fontSize: 13, cursor: "pointer", color: "#111827" };

  return (
    <>
      <button type="button" ref={btn} className="room-select-trigger" aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, width, maxWidth: "100%", textAlign: "left", background: "white", border: "1px solid #d1d5db",
          borderRadius: 6, padding: "6px 8px", fontSize: 13, cursor: "pointer", boxSizing: "border-box", color: "#111827", fontWeight: 400, ...style }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{text}</span><span aria-hidden="true" style={{ color: "#6b7280", fontSize: 10 }}>▼</span>
      </button>
      {menuPresent && pos && (
        <div ref={panel} role="listbox" className={`room-select-menu popup-slide${menuClosing ? " is-closing" : ""}`} aria-hidden={menuClosing} inert={menuClosing ? "" : undefined} style={{ position: "fixed", zIndex: 3000, left: pos.left, top: pos.top, bottom: pos.bottom, width: pos.width, background: "white", border: "1px solid #d1d5db",
          borderRadius: 6, boxShadow: "var(--shadow-pop)" }}>
          <div style={{ padding: 8, borderBottom: "1px solid #f3f4f6" }}>
            <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search room name, building or number…" aria-label="Search rooms"
              onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); if (e.key === "Enter" && shown.length === 1) pick(shown[0].id); }}
              style={{ width: "100%", boxSizing: "border-box", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13 }} />
          </div>
          <div style={{ maxHeight: 250, overflowY: "auto", paddingBottom: 4 }}>
            {allowAuto && !q && <button type="button" role="option" aria-selected={!value} onClick={() => pick("")} style={{ ...row, fontWeight: !value ? 700 : 400 }}>{autoLabel}</button>}
            {groups.map(([g, list]) => (
              <div key={g || "all"}>
                {g ? <div style={{ padding: "6px 10px 2px", fontSize: 12, color: "#6b7280", letterSpacing: ".04em" }}>{g}</div> : null}
                {list.map((r) => {
                  const off = isDisabled ? isDisabled(r) : false;
                  const on = String(r.id) === String(value);
                  return (
                    <button key={r.id} type="button" role="option" aria-selected={on} disabled={off} onClick={() => pick(r.id)}
                      style={{ ...row, background: on ? "#e8f0fb" : "none", fontWeight: on ? 700 : 400, opacity: off ? 0.45 : 1, cursor: off ? "not-allowed" : "pointer" }}>
                      {roomLabel(r)}{suffix ? suffix(r) : ""}
                    </button>
                  );
                })}
              </div>
            ))}
            {shown.length === 0 && <div style={{ padding: "10px", fontSize: 13, color: "#6b7280" }}>No room matches “{q}”.</div>}
          </div>
        </div>
      )}
    </>
  );
}
