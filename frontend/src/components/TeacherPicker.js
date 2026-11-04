import React, { useEffect, useMemo, useRef, useState } from "react";

/* ONE searchable teacher list, used by the Edit dialog, the Generate dialog's Professor column and the overload replacement picker.
   The list it is given is already the server's (only teachers the rules allow); this only filters and picks.

   options: [{ id, label, detail?, search?, group? }]  -- `search` adds text to match (employee ID, username, full name),
            `group` is the heading ("Suggested" first, then the order the groups first appear in).
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
  ariaLabel = "Teacher", title, compact = false, valueLabel = "" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const wrap = useRef(null), input = useRef(null), list = useRef(null);
  const all = useMemo(() => options || [], [options]);
  const shown = useMemo(() => grouped(filterOptions(all, query)), [all, query]);
  // the flat order the keyboard walks: "empty" entry first (when there is no search), then the groups in the order drawn
  const flat = useMemo(() => [...(emptyLabel && !query.trim() ? [{ id: "", label: emptyLabel }] : []), ...shown.flatMap((g) => g.items)],
    [shown, emptyLabel, query]);
  const current = all.find((o) => String(o.id) === String(value ?? ""));

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  useEffect(() => { if (open && input.current) input.current.focus(); }, [open]);
  useEffect(() => { setActive(0); }, [query, open]);
  useEffect(() => {
    const el = list.current && list.current.querySelector('[data-active="true"]');
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (o) => { onChange(o.id === "" ? "" : String(o.id)); setOpen(false); setQuery(""); };
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
    <div ref={wrap} style={{ position: "relative", width: "100%", minWidth: 0 }}>
      <button type="button" disabled={disabled} aria-label={ariaLabel} aria-haspopup="listbox" aria-expanded={open} title={title}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (["ArrowDown", "Enter", " "].includes(e.key) && !open) { e.preventDefault(); setOpen(true); } }}
        style={{ width: "100%", textAlign: "left", background: disabled ? "#f1f5f9" : "white", color: "#1f2937", border: "1px solid #cdd6e0",
          borderRadius: compact ? 4 : 8, padding: pad, fontSize: compact ? 12 : 14, cursor: disabled ? "not-allowed" : "pointer",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", boxShadow: "none", boxSizing: "border-box" }}>
        {fieldText}<span aria-hidden="true" style={{ float: "right", color: "#64748b", marginLeft: 6 }}>▾</span>
      </button>
      {open && (
        <div style={{ position: "absolute", zIndex: 1200, top: "100%", left: 0, marginTop: 4, width: "max(100%, min(360px, 92vw))", maxWidth: "92vw",
          background: "white", border: "1px solid #cdd6e0", borderRadius: 8, boxShadow: "0 10px 30px rgba(15,23,42,.18)" }}>
          <input ref={input} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} role="combobox"
            aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-label={`Search ${ariaLabel}`}
            aria-activedescendant={flat[active] ? `${listId}-${flat[active].id}` : undefined}
            placeholder="Search name or employee ID…"
            style={{ width: "100%", boxSizing: "border-box", border: "none", borderBottom: "1px solid #e2e8f0", padding: "9px 12px", fontSize: 13.5,
              outline: "none", borderRadius: "8px 8px 0 0" }} />
          <div ref={list} id={listId} role="listbox" aria-label={ariaLabel} style={{ maxHeight: 260, overflowY: "auto", padding: "4px 0" }}>
            {(() => {
              let i = -1;
              const row = (o) => {
                i += 1;
                const idx = i, on = idx === active, sel = String(o.id) === String(value ?? "");
                return (
                  <div key={`o-${o.id}`} id={`${listId}-${o.id}`} role="option" aria-selected={sel} data-active={on ? "true" : "false"}
                    onMouseDown={(e) => e.preventDefault()} onClick={() => pick(o)} onMouseEnter={() => setActive(idx)}
                    style={{ padding: "7px 12px", cursor: "pointer", fontSize: 13, background: on ? "#eef4fb" : "white",
                      color: "#1f2937", fontWeight: sel ? 700 : 400, overflowWrap: "anywhere" }}>
                    {o.label}
                    {o.detail && <div style={{ fontSize: 11.5, color: "#64748b", fontWeight: 400 }}>{o.detail}</div>}
                  </div>
                );
              };
              return (
                <>
                  {emptyLabel && !query.trim() && row({ id: "", label: emptyLabel })}
                  {shown.map((g) => (
                    <div key={`g-${g.group}`} role="group" aria-label={g.group || "Teachers"}>
                      {g.group && <div style={{ padding: "6px 12px 2px", fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.3 }}>{g.group}</div>}
                      {g.items.map(row)}
                    </div>
                  ))}
                  {shown.length === 0 && <div role="status" style={{ padding: "10px 12px", fontSize: 13, color: "#64748b" }}>No teacher found</div>}
                </>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
