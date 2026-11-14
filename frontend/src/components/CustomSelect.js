import React, { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./DashboardTheme.css";
import usePopupPresence from "./usePopupPresence";

function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  return textOf(node.props?.children);
}

/** Styled select replacement with a native-select-like value/onChange contract. */
export default function CustomSelect({
  children, value, defaultValue, onChange, style, className = "", disabled = false,
  name, id, title, required, "aria-label": ariaLabel, "aria-labelledby": ariaLabelledBy,
  onBlur, onFocus, portalMenu = false, ...rest
}) {
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const menuId = useId();
  const optionRefs = useRef([]);
  const typeaheadRef = useRef("");
  const typeaheadTimerRef = useRef(null);
  const [open, setOpen] = useState(false);
  const { present: menuPresent, closing: menuClosing } = usePopupPresence(open);
  const [menuPosition, setMenuPosition] = useState(null);
  const options = useMemo(() => React.Children.toArray(children)
    .filter((child) => React.isValidElement(child) && child.type === "option")
    .map((child) => ({
      value: String(child.props.value ?? textOf(child.props.children)),
      label: child.props.children,
      text: textOf(child.props.children).trim(),
      disabled: !!child.props.disabled,
    })), [children]);
  const [uncontrolledValue, setUncontrolledValue] = useState(defaultValue ?? options.find((option) => !option.disabled)?.value ?? "");
  const selectedValue = String(value !== undefined ? value : uncontrolledValue);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === selectedValue));
  const selectedOption = options.find((option) => option.value === selectedValue);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);

  useEffect(() => setActiveIndex(selectedIndex), [selectedIndex]);
  useEffect(() => {
    if (open && menuPresent) optionRefs.current[activeIndex]?.focus();
  }, [open, activeIndex, menuPresent]);
  useEffect(() => {
    if (!open) return undefined;
    const closeOutside = (event) => {
      if (!rootRef.current?.contains(event.target) && !menuRef.current?.contains(event.target)) setOpen(false);
    };
    const closeOnEscape = (event) => { if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); } };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);
  useLayoutEffect(() => {
    if (!open || !portalMenu) return undefined;
    const placeMenu = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const vw = window.innerWidth || 1024;
      const vh = window.innerHeight || 768;
      const width = Math.min(Math.max(rect.width, 170), vw - 16);
      const below = vh - rect.bottom - 12;
      const above = rect.top - 12;
      const openAbove = below < 160 && above > below;
      const maxHeight = Math.max(120, Math.min(280, openAbove ? above : below));
      setMenuPosition({
        left: Math.max(8, Math.min(rect.left, vw - width - 8)),
        width,
        maxHeight,
        ...(openAbove ? { bottom: vh - rect.top + 6 } : { top: rect.bottom + 6 }),
      });
    };
    placeMenu();
    window.addEventListener("resize", placeMenu);
    window.addEventListener("scroll", placeMenu, true);
    return () => {
      window.removeEventListener("resize", placeMenu);
      window.removeEventListener("scroll", placeMenu, true);
    };
  }, [open, portalMenu]);
  useEffect(() => () => clearTimeout(typeaheadTimerRef.current), []);

  const openAt = (index = selectedIndex) => {
    const firstEnabled = options.findIndex((option) => !option.disabled);
    const next = index >= 0 && !options[index]?.disabled ? index : Math.max(firstEnabled, 0);
    setActiveIndex(next);
    setOpen(true);
  };
  const choose = (option) => {
    if (!option || option.disabled) return;
    if (value === undefined) setUncontrolledValue(option.value);
    onChange?.({ target: { value: option.value, name }, currentTarget: { value: option.value, name } });
    setOpen(false);
    triggerRef.current?.focus();
  };
  const moveActive = (direction) => {
    if (!options.length) return;
    let next = activeIndex;
    for (let i = 0; i < options.length; i += 1) {
      next = (next + direction + options.length) % options.length;
      if (!options[next].disabled) { setActiveIndex(next); optionRefs.current[next]?.focus(); return; }
    }
  };
  const handleTriggerKeyDown = (event) => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      if (!open) openAt(selectedIndex + (event.key === "ArrowDown" ? 0 : -1));
      else moveActive(event.key === "ArrowDown" ? 1 : -1);
    } else if (["Enter", " "].includes(event.key)) {
      event.preventDefault();
      if (open) choose(options[activeIndex]); else openAt();
    } else if (event.key === "Escape" && open) {
      event.preventDefault(); setOpen(false);
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      typeaheadRef.current += event.key.toLocaleLowerCase();
      clearTimeout(typeaheadTimerRef.current);
      typeaheadTimerRef.current = setTimeout(() => { typeaheadRef.current = ""; }, 600);
      const matchIndex = options.findIndex((option) => !option.disabled && option.text.toLocaleLowerCase().startsWith(typeaheadRef.current));
      if (matchIndex >= 0) {
        setActiveIndex(matchIndex);
        if (open) optionRefs.current[matchIndex]?.focus(); else choose(options[matchIndex]);
      }
    }
  };

  return (
    <div ref={rootRef} className={`custom-select ${className}`.trim()} style={{
      display: style?.flex || style?.flexGrow ? "inline-flex" : "inline-block", position: "relative",
      width: style?.width || "auto", minWidth: style?.minWidth, maxWidth: style?.maxWidth,
      flex: style?.flex, flexGrow: style?.flexGrow, flexShrink: style?.flexShrink, alignSelf: style?.alignSelf,
      margin: style?.margin, marginLeft: style?.marginLeft, marginRight: style?.marginRight,
      verticalAlign: style?.verticalAlign,
    }}>
      <button
        {...rest}
        ref={triggerRef}
        id={id}
        title={title}
        type="button"
        className="custom-select-trigger"
        style={style}
        disabled={disabled}
        required={required}
        name={name}
        role="combobox"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        aria-haspopup="listbox"
        aria-controls={menuId}
        aria-expanded={open}
        aria-required={required || undefined}
        onBlur={onBlur}
        onFocus={onFocus}
        onClick={() => { if (!disabled) { if (open) setOpen(false); else openAt(); } }}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="custom-select-value">{selectedOption?.label ?? "Select an option"}</span>
        <svg className="custom-select-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7 5 5 5-5" /></svg>
      </button>
      {menuPresent && (!portalMenu || menuPosition) && (() => {
        const menu = (
        <div ref={menuRef} id={menuId} className={`custom-select-menu popup-slide${menuClosing ? " is-closing" : ""}`} role="listbox" aria-label={ariaLabel} aria-hidden={menuClosing} inert={menuClosing ? "" : undefined}
          style={portalMenu ? { position: "fixed", left: menuPosition.left, width: menuPosition.width,
            top: menuPosition.top ?? "auto", bottom: menuPosition.bottom ?? "auto",
            maxHeight: menuPosition.maxHeight, zIndex: 5000 } : undefined}>
          {options.map((option, index) => (
            <button
              key={`${option.value}-${index}`}
              ref={(node) => { optionRefs.current[index] = node; }}
              type="button"
              role="option"
              aria-selected={option.value === selectedValue}
              disabled={option.disabled}
              className={`custom-select-option${option.value === selectedValue ? " is-selected" : ""}${index === activeIndex ? " is-active" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(option)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); moveActive(event.key === "ArrowDown" ? 1 : -1); }
                else if (event.key === "Home" || event.key === "End") {
                  event.preventDefault();
                  const next = event.key === "Home" ? options.findIndex((item) => !item.disabled) : options.reduce((last, item, index) => item.disabled ? last : index, -1);
                  if (next >= 0) { setActiveIndex(next); optionRefs.current[next]?.focus(); }
                } else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(option); }
              }}
            >
              <span>{option.label}</span>
              {option.value === selectedValue && <span className="custom-select-check" aria-hidden="true">✓</span>}
            </button>
          ))}
        </div>
        );
        return portalMenu ? createPortal(menu, document.body) : menu;
      })()}
    </div>
  );
}
