import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import ModalPortal from "./ModalPortal";
import "./DashboardTheme.css";

const ConfirmContext = createContext(null);

export function ConfirmDialogProvider({ children }) {
  const [request, setRequest] = useState(null);
  const resolveRef = useRef(null);
  const confirm = useCallback((options = {}) => new Promise((resolve) => {
    resolveRef.current?.(false);
    resolveRef.current = resolve;
    setRequest({
      title: options.title || "Are you sure?",
      message: options.message || "This action cannot be undone.",
      confirmLabel: options.confirmLabel || "Confirm",
      cancelLabel: options.cancelLabel || "Cancel",
    });
  }), []);
  const close = useCallback((result) => {
    setRequest(null);
    const resolve = resolveRef.current;
    resolveRef.current = null;
    resolve?.(result);
  }, []);

  useEffect(() => {
    if (!request) return undefined;
    const onKeyDown = (event) => { if (event.key === "Escape") close(false); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [request, close]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <ModalPortal><div className="confirm-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) close(false); }}>
          <section className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-modal-title" aria-describedby="confirm-modal-message">
            <h2 id="confirm-modal-title">{request.title}</h2>
            <p id="confirm-modal-message">{request.message}</p>
            <div className="confirm-modal-actions">
              <button type="button" className="confirm-modal-cancel" onClick={() => close(false)}>{request.cancelLabel}</button>
              <button type="button" className="confirm-modal-accept" onClick={() => close(true)}>{request.confirmLabel}</button>
            </div>
          </section>
        </div></ModalPortal>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirmDialog() {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirmDialog must be used inside ConfirmDialogProvider");
  return confirm;
}
