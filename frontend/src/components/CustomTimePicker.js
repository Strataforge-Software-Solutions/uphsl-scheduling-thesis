import React, { useEffect, useMemo, useRef, useState } from "react";
import "./DashboardTheme.css";
import usePopupPresence from "./usePopupPresence";

function parseTime(value) {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const hour24 = Number(match[1]);
  const minute = Number(match[2]);
  if (hour24 < 0 || hour24 > 23 || minute < 0 || minute > 59) return null;
  return { hour: hour24 % 12 || 12, minute, period: hour24 < 12 ? "AM" : "PM" };
}
function formatTime(parts) {
  let hour24 = parts.hour % 12;
  if (parts.period === "PM") hour24 += 12;
  return `${String(hour24).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
}

export default function CustomTimePicker({ value = "", onChange, className = "", style, disabled = false, "aria-label": ariaLabel = "Choose time" }) {
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const hourRefs = useRef([]);
  const minuteRefs = useRef([]);
  const dialogId = React.useId();
  const selected = useMemo(() => parseTime(value), [value]);
  const [open, setOpen] = useState(false);
  const { present: menuPresent, closing: menuClosing } = usePopupPresence(open);
  const [draft, setDraft] = useState(() => selected || { hour: 8, minute: 0, period: "AM" });

  useEffect(() => { if (!open && selected) setDraft(selected); }, [open, selected]);
  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    const closeEscape = (event) => { if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); } };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, [open]);
  useEffect(() => {
    if (open && menuPresent) {
      hourRefs.current[draft.hour - 1]?.scrollIntoView({ block: "center" });
      minuteRefs.current[draft.minute]?.scrollIntoView({ block: "center" });
    }
  }, [open, menuPresent, draft.hour, draft.minute]);

  const updatePart = (key, partValue) => {
    const next = { ...draft, [key]: partValue };
    setDraft(next);
    onChange?.({ target: { value: formatTime(next) }, currentTarget: { value: formatTime(next) } });
  };
  const clear = () => {
    onChange?.({ target: { value: "" }, currentTarget: { value: "" } });
    setOpen(false);
    triggerRef.current?.focus();
  };
  const displayValue = selected ? `${String(selected.hour).padStart(2, "0")}:${String(selected.minute).padStart(2, "0")} ${selected.period}` : "Choose time";

  return (
    <div ref={rootRef} className={`custom-time-picker ${className}`.trim()} style={{
      display: style?.flex || style?.flexGrow ? "inline-flex" : "inline-block", position: "relative",
      width: style?.width || "auto", minWidth: style?.minWidth, maxWidth: style?.maxWidth,
      flex: style?.flex, flexGrow: style?.flexGrow, flexShrink: style?.flexShrink, alignSelf: style?.alignSelf,
      margin: style?.margin, marginLeft: style?.marginLeft, marginRight: style?.marginRight,
    }}>
      <button
        ref={triggerRef}
        type="button"
        className="custom-time-trigger"
        style={{ width: style?.width || "auto", minWidth: style?.minWidth, maxWidth: style?.maxWidth, height: style?.height }}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={dialogId}
        onClick={() => {
          if (!open) setDraft(selected || { hour: 8, minute: 0, period: "AM" });
          setOpen((wasOpen) => !wasOpen);
        }}
      >
        <svg className="custom-time-icon" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" /><path d="M10 6v4l2.7 1.8" /></svg>
        <span>{displayValue}</span>
        <svg className="custom-time-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7 5 5 5-5" /></svg>
      </button>
      {menuPresent && (
        <div id={dialogId} className={`custom-time-menu popup-slide${menuClosing ? " is-closing" : ""}`} role="dialog" aria-label="Choose a time" aria-hidden={menuClosing} inert={menuClosing ? "" : undefined}>
          <div className="custom-time-columns">
            <div className="custom-time-column" role="group" aria-label="Hour">
              <div className="custom-time-column-label">Hour</div>
              {[...Array(12)].map((_, index) => {
                const hour = index + 1;
                return <button key={hour} ref={(node) => { hourRefs.current[index] = node; }} type="button" className={`custom-time-option${draft.hour === hour ? " is-selected" : ""}`} aria-current={draft.hour === hour ? "true" : undefined} onClick={() => updatePart("hour", hour)}>{String(hour).padStart(2, "0")}</button>;
              })}
            </div>
            <div className="custom-time-column" role="group" aria-label="Minute">
              <div className="custom-time-column-label">Minute</div>
              {[...Array(60)].map((_, minute) => (
                <button key={minute} ref={(node) => { minuteRefs.current[minute] = node; }} type="button" className={`custom-time-option${draft.minute === minute ? " is-selected" : ""}`} aria-current={draft.minute === minute ? "true" : undefined} onClick={() => updatePart("minute", minute)}>{String(minute).padStart(2, "0")}</button>
              ))}
            </div>
            <div className="custom-time-column custom-time-period" role="group" aria-label="AM or PM">
              <div className="custom-time-column-label">Period</div>
              {["AM", "PM"].map((period) => <button key={period} type="button" className={`custom-time-option${draft.period === period ? " is-selected" : ""}`} aria-current={draft.period === period ? "true" : undefined} onClick={() => updatePart("period", period)}>{period}</button>)}
            </div>
          </div>
          <div className="custom-time-footer">
            <button type="button" onClick={clear} disabled={!value}>Clear</button>
            <button type="button" onClick={() => { setOpen(false); triggerRef.current?.focus(); }}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
