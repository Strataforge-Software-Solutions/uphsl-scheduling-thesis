import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./DashboardTheme.css";
import usePopupPresence from "./usePopupPresence";

const toISODate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const parseISODate = (value) => {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
};
const sameDay = (a, b) => !!a && !!b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

export default function CustomDatePicker({ value, defaultValue = "", onChange, onBlur, className = "", style, disabled = false, min, max, "aria-label": ariaLabel = "Choose date" }) {
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const calendarRef = useRef(null);
  const dayRefs = useRef([]);
  const dialogId = React.useId();
  const [uncontrolledValue, setUncontrolledValue] = useState(defaultValue);
  const selectedValue = value !== undefined ? value : uncontrolledValue;
  const selectedDate = useMemo(() => parseISODate(selectedValue), [selectedValue]);
  const minDate = useMemo(() => parseISODate(min), [min]);
  const maxDate = useMemo(() => parseISODate(max), [max]);
  const today = useMemo(() => new Date(), []);
  const [open, setOpen] = useState(false);
  const { present: calendarPresent, closing: calendarClosing } = usePopupPresence(open);
  const [calendarPosition, setCalendarPosition] = useState(null);
  const [viewMonth, setViewMonth] = useState(() => new Date((selectedDate || today).getFullYear(), (selectedDate || today).getMonth(), 1));

  useLayoutEffect(() => {
    if (!open || !calendarPresent) return undefined;
    const updateCalendarPosition = () => {
      const trigger = triggerRef.current;
      const calendar = calendarRef.current;
      if (!trigger || !calendar) return;
      const triggerRect = trigger.getBoundingClientRect();
      const calendarRect = calendar.getBoundingClientRect();
      const centeredLeft = triggerRect.left + (triggerRect.width - calendarRect.width) / 2;
      const left = Math.max(8, Math.min(centeredLeft, window.innerWidth - calendarRect.width - 8));
      const below = triggerRect.bottom + 7;
      const above = triggerRect.top - calendarRect.height - 7;
      const preferredTop = below + calendarRect.height <= window.innerHeight - 8 || above < 8 ? below : above;
      const top = Math.max(8, Math.min(preferredTop, window.innerHeight - calendarRect.height - 8));
      setCalendarPosition({ left, top });
    };
    updateCalendarPosition();
    window.addEventListener("resize", updateCalendarPosition);
    window.addEventListener("scroll", updateCalendarPosition, true);
    return () => {
      window.removeEventListener("resize", updateCalendarPosition);
      window.removeEventListener("scroll", updateCalendarPosition, true);
    };
  }, [open, calendarPresent, viewMonth]);

  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event) => {
      if (!rootRef.current?.contains(event.target) && !calendarRef.current?.contains(event.target)) {
        setOpen(false);
        onBlur?.({ target: { value: selectedValue }, currentTarget: { value: selectedValue } });
      }
    };
    const closeEscape = (event) => { if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); } };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeEscape);
    };
  }, [open, onBlur, selectedValue]);

  const monthLabel = useMemo(() => viewMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" }), [viewMonth]);
  const calendarDays = useMemo(() => {
    const year = viewMonth.getFullYear();
    const month = viewMonth.getMonth();
    const offset = (new Date(year, month, 1).getDay() + 6) % 7;
    const count = new Date(year, month + 1, 0).getDate();
    const days = [...Array(offset).fill(null), ...Array.from({ length: count }, (_, index) => new Date(year, month, index + 1))];
    return [...days, ...Array(Math.max(0, 42 - days.length)).fill(null)];
  }, [viewMonth]);

  useEffect(() => {
    if (open && calendarPresent) {
      const showingCurrentMonth = today.getFullYear() === viewMonth.getFullYear() && today.getMonth() === viewMonth.getMonth();
      const focusDate = selectedDate && selectedDate.getFullYear() === viewMonth.getFullYear() && selectedDate.getMonth() === viewMonth.getMonth() ? selectedDate.getDate() : (showingCurrentMonth ? today.getDate() : 1);
      dayRefs.current[focusDate - 1]?.focus();
    }
  }, [open, calendarPresent, selectedDate, today, viewMonth]);

  const changeDate = (date) => {
    if (date && ((minDate && date < minDate) || (maxDate && date > maxDate))) return;
    const nextValue = date ? toISODate(date) : "";
    if (value === undefined) setUncontrolledValue(nextValue);
    onChange?.({ target: { value: nextValue }, currentTarget: { value: nextValue } });
    setOpen(false);
    triggerRef.current?.focus();
  };
  const shiftMonth = (delta) => setViewMonth((month) => new Date(month.getFullYear(), month.getMonth() + delta, 1));
  const dateIsDisabled = (date) => (minDate && date < minDate) || (maxDate && date > maxDate);
  const handleTriggerKeyDown = (event) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) { const date = selectedDate || new Date(); setViewMonth(new Date(date.getFullYear(), date.getMonth(), 1)); setOpen(true); }
    }
  };

  return (
    <div ref={rootRef} className={`custom-date-picker ${className}`.trim()} style={{
      display: style?.flex || style?.flexGrow ? "inline-flex" : "inline-block", position: "relative",
      width: style?.width || "auto", minWidth: style?.minWidth, maxWidth: style?.maxWidth,
      flex: style?.flex, flexGrow: style?.flexGrow, flexShrink: style?.flexShrink, alignSelf: style?.alignSelf,
      margin: style?.margin, marginLeft: style?.marginLeft, marginRight: style?.marginRight,
    }}>
      <button
        ref={triggerRef}
        type="button"
        className="custom-date-trigger"
        style={{ width: style?.width || "auto", minWidth: style?.minWidth, maxWidth: style?.maxWidth, height: style?.height }}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={dialogId}
        onClick={() => {
          if (!open) { const date = selectedDate || new Date(); setViewMonth(new Date(date.getFullYear(), date.getMonth(), 1)); }
          setOpen((wasOpen) => !wasOpen);
        }}
        onKeyDown={handleTriggerKeyDown}
        onBlur={(event) => { if (!rootRef.current?.contains(event.relatedTarget) && !calendarRef.current?.contains(event.relatedTarget)) onBlur?.({ target: { value: selectedValue }, currentTarget: { value: selectedValue } }); }}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6.5 2.5v3M13.5 2.5v3M3.5 8h13" /></svg>
        <span>{selectedDate ? selectedDate.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "Choose date"}</span>
        <svg className="custom-date-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7 5 5 5-5" /></svg>
      </button>
      {calendarPresent && createPortal(
        <div ref={calendarRef} id={dialogId} className={`custom-calendar popup-slide${calendarClosing ? " is-closing" : ""}`} role="dialog" aria-label="Choose a date" aria-hidden={calendarClosing} inert={calendarClosing ? "" : undefined}
          style={{ position: "fixed", left: calendarPosition?.left ?? 8, top: calendarPosition?.top ?? 8, visibility: calendarPosition ? "visible" : "hidden" }}>
          <div className="custom-calendar-header">
            <button type="button" className="custom-calendar-nav" aria-label="Previous month" onClick={() => shiftMonth(-1)}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4-6 6 6 6" /></svg></button>
            <strong>{monthLabel}</strong>
            <button type="button" className="custom-calendar-nav" aria-label="Next month" onClick={() => shiftMonth(1)}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 4 6 6-6 6" /></svg></button>
          </div>
          <div className="custom-calendar-grid" role="group" aria-label={monthLabel}>
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => <span key={day} className="custom-calendar-weekday">{day}</span>)}
            {calendarDays.map((date, index) => date ? (
              <button
                key={toISODate(date)}
                ref={(node) => { dayRefs.current[date.getDate() - 1] = node; }}
                type="button"
                aria-label={`${date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}${sameDay(date, selectedDate) ? ", selected" : ""}`}
                className={`custom-calendar-day${sameDay(date, selectedDate) ? " is-selected" : ""}${sameDay(date, today) ? " is-today" : ""}`}
                disabled={!!dateIsDisabled(date)}
                onClick={() => changeDate(date)}
                onKeyDown={(event) => {
                  const move = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
                  if (move) {
                    event.preventDefault();
                    const next = new Date(date.getFullYear(), date.getMonth(), date.getDate() + move);
                    setViewMonth(new Date(next.getFullYear(), next.getMonth(), 1));
                    if (next.getMonth() === date.getMonth()) dayRefs.current[next.getDate() - 1]?.focus();
                  } else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); changeDate(date); }
                }}
              >{date.getDate()}</button>
            ) : <span key={`blank-${index}`} aria-hidden="true" />)}
          </div>
          <div className="custom-calendar-footer">
            <button type="button" onClick={() => changeDate(null)} disabled={!value}>Clear</button>
            <button type="button" onClick={() => changeDate(today)} disabled={!!dateIsDisabled(today)}>Today</button>
          </div>
        </div>, document.body
      )}
    </div>
  );
}
