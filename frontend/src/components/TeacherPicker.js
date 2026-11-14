import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import usePopupPresence from "./usePopupPresence";

/* ONE searchable teacher list, used by the Edit dialog, the Generate dialog's Professor column and the overload replacement picker.
   The list it is given is already the server's (only teachers the rules allow); this only filters and picks.

   options: [{ id, label, detail?, search?, group?, disabled? }]  -- `search` adds text to match (employee ID, username, full name),
            `group` is the heading ("Suggested" first, then the order the groups first appear in), `disabled` = listed (muted, with
            its reason in `detail`) but not selectable.
   groupNotes: { heading: text } shown under a heading. footer: one muted line at the end. emptyText: when nothing is listed.
   onChange(id, option) -- the option is passed too (e.g. to ask for confirmation first).
   value / onChange(id | "")  -- ids are compared as strings.
   valueLabel: text for a value that is not among the options (shown, never offered).
   emptyLabel: when set, a first entry with value "" (e.g. "Automatic"); without it nothing-chosen shows `placeholder`.
   Keyboard: the field opens with Enter / Space / ArrowDown; in the search box ArrowUp / ArrowDown move, Enter picks, Esc closes. */

export const normalize = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();

/* Every word typed must appear in the teacher's label, detail or search text (name, employee ID, username). */
export function filterOptions(options, query) {
  const words = normalize(query).split(" ").filter(Boolean);
  if (!words.length) return options;
  return options.filter((o) => {
    const hay = normalize(`${o.label} ${o.search || ""}`);
    return words.every((w) => hay.includes(w));
  });
}

function grouped(list) {
  const order = [], by = {};
  list.forEach((o) => {
    const g = o.group || "";
    if (!(g in by)) { by[g] = []; order.push(g); }
    by[g].push(o);
  });
  order.sort((a, b) => (a === "Suggested" ? -1 : b === "Suggested" ? 1 : 0));
  return order.map((g) => ({ group: g, items: by[g] }));
}

export default function TeacherPicker({ options, value, onChange, emptyLabel, placeholder = "Choose a teacher", disabled = false,
  ariaLabel = "Teacher", title, compact = false, valueLabel = "", groupNotes = {}, footer = "", emptyText = "No teacher found", className = "" }) {
  const [open, setOpen] = useState(false);
  const { present: menuPresent, closing: menuClosing } = usePopupPresence(open);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const wrap = useRef(null), input = useRef(null), list = useRef(null), pop = useRef(null);
  const [pos, setPos] = useState(null);
  const all = useMemo(() => options || [], [options]);
  const shown = useMemo(() => grouped(filterOptions(all, query)), [all, query]);
  // the flat order the keyboard walks: "empty" entry first (when there is no search), then the groups in the order drawn
  const flat = useMemo(() => [...(emptyLabel && !query.trim() ? [{ id: "", label: emptyLabel }] : []),
    ...shown.flatMap((g) => g.items).filter((o) => !o.disabled)], [shown, emptyLabel, query]);
  const current = all.find((o) => String(o.id) === String(value ?? ""));

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => {
      if ((wrap.current && wrap.current.contains(e.target)) || (pop.current && pop.current.contains(e.target))) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  /* The list floats above the page (a portal with fixed position), so a table's scroll box or a dialog never cuts it off. It opens
     below the field, or above it when there is no room below, and follows the field when the page or table scrolls. */
  useLayoutEffect(() => {
    if (!open) return undefined;
    const place = () => {
      const r = wrap.current ? wrap.current.getBoundingClientRect() : null;
      if (!r) return;
      const vw = window.innerWidth || 1024, vh = window.innerHeight || 768;
      const width = Math.min(Math.max(r.width, Math.min(360, vw * 0.92)), vw - 16);
      const below = vh - r.bottom, above = r.top;
      const up = below < 260 && above > below;
      setPos({ left: Math.max(8, Math.min(r.left, vw - width - 8)), width, maxList: Math.max(120, Math.min(300, (up ? above : below) - 60)),
        ...(up ? { bottom: vh - r.top + 4 } : { top: r.bottom + 4 }) });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open]);
  useEffect(() => { if (open && menuPresent && input.current) input.current.focus(); }, [open, menuPresent, pos]);
  useEffect(() => { setActive(0); }, [query, open]);
  useEffect(() => {
    const el = list.current && list.current.querySelector('[data-active="true"]');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (o) => { if (o.disabled) return; onChange(o.id === "" ? "" : String(o.id), o); setOpen(false); setQuery(""); };
  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); if (flat[active]) pick(flat[active]); }
    else if (e.key === "Escape") { e.preventDefault(); setOpen(false); setQuery(""); }
  };
  // valueLabel: the name of a chosen teacher who is not in the list (e.g. older data from another department, never offered)
  const fieldText = current ? current.label : (value ? (valueLabel || placeholder) : (emptyLabel || placeholder));
  const pad = compact ? "3px 6px" : "9px 12px";
  const listId = `${ariaLabel.replace(/\W+/g, "-")}-list`;

  return (
    <div ref={wrap} className={className || undefined} style={{ position: "relative", width: "100%", minWidth: 0 }}>
      <button type="button" className="teacher-picker-trigger" disabled={disabled} aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} title={title}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (["ArrowDown", "Enter", " "].includes(e.key) && !open) { e.preventDefault(); setOpen(true); } }}
        style={{ width: "100%", textAlign: "left", background: disabled ? "#f3f4f6" : "white", color: "#111827", border: "1px solid #d1d5db",
          borderRadius: compact ? 4 : 8, padding: pad, fontSize: compact ? 12 : 14, cursor: disabled ? "not-allowed" : "pointer",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", boxShadow: "none", boxSizing: "border-box" }}>
        {fieldText}<span aria-hidden="true" style={{ float: "right", color: "#6b7280", marginLeft: 6 }}>▾</span>
      </button>
      {menuPresent && pos && createPortal(
        <div ref={pop} className={`teacher-picker-menu popup-slide${menuClosing ? " is-closing" : ""}`} aria-hidden={menuClosing} inert={menuClosing ? "" : undefined} style={{ position: "fixed", zIndex: 5000, left: pos.left, width: pos.width, top: pos.top, bottom: pos.bottom,
          background: "white", border: "1px solid #d1d5db", borderRadius: 6, boxShadow: "var(--shadow-pop)" }}>
          <input ref={input} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} role="combobox"
            aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-label={`Search ${ariaLabel}`}
            aria-activedescendant={flat[active] ? `${listId}-${flat[active].id}` : undefined}
            placeholder="Search name or employee ID…"
            style={{ width: "100%", boxSizing: "border-box", border: "none", borderBottom: "1px solid #e5e7eb", padding: "9px 12px", fontSize: 14,
              outline: "none", borderRadius: "6px 6px 0 0" }} />
          <div ref={list} id={listId} role="listbox" aria-label={ariaLabel} style={{ maxHeight: pos.maxList, overflowY: "auto", padding: "4px 0" }}>
            {(() => {
              let i = -1;
              const row = (o) => {
                if (o.disabled) {
                  return (
                    <div key={`o-${o.id}`} role="option" aria-disabled="true" aria-selected={false}
                      style={{ padding: "7px 12px", fontSize: 13, color: "#6b7280", cursor: "not-allowed", overflowWrap: "anywhere" }}>
                      {o.label}
                      {o.detail && <div style={{ fontSize: 12, color: "#6b7280" }}>{o.detail}</div>}
                    </div>
                  );
                }
                i += 1;
                const idx = i, on = idx === active, sel = String(o.id) === String(value ?? "");
                return (
                  <div key={`o-${o.id}`} id={`${listId}-${o.id}`} role="option" aria-selected={sel} data-active={on ? "true" : "false"}
                    onMouseDown={(e) => e.preventDefault()} onClick={() => pick(o)} onMouseEnter={() => setActive(idx)}
                    style={{ padding: "7px 12px", cursor: "pointer", fontSize: 13, background: on ? "#eef4fb" : "white",
                      color: "#111827", fontWeight: sel ? 700 : 400, overflowWrap: "anywhere" }}>
                    {o.label}
                    {o.detail && <div style={{ fontSize: 12, color: "#6b7280", fontWeight: 400 }}>{o.detail}</div>}
                  </div>
                );
              };
              return (
                <>
                  {emptyLabel && !query.trim() && row({ id: "", label: emptyLabel })}
                  {shown.map((g) => (
                    <div key={`g-${g.group}`} role="group" aria-label={g.group || "Teachers"}>
                      {g.group && <div className="teacher-picker-group-heading" style={{ padding: "6px 12px 2px", fontSize: 12, fontWeight: 600, color: "#374151" }}>{g.group}</div>}
                      {g.group && groupNotes[g.group] && <div style={{ padding: "0 12px 4px", fontSize: 12, color: "#92400e" }}>{groupNotes[g.group]}</div>}
                      {g.items.map(row)}
                    </div>
                  ))}
                  {shown.length === 0 && <div role="status" style={{ padding: "10px 12px", fontSize: 13, color: "#6b7280" }}>{query.trim() ? "No teacher found" : emptyText}</div>}
                  {footer && !query.trim() && <div style={{ padding: "6px 12px", fontSize: 12, color: "#6b7280", borderTop: "1px solid #f3f4f6" }}>{footer}</div>}
                </>
              );
            })()}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
