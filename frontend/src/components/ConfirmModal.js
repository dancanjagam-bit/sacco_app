import React, { useEffect, useId, useRef } from "react";
import Button from "./ui/Button";

/** Shared confirmation dialog with Escape handling, focus containment and restore. */
export default function ConfirmModal({
  title = "Confirm action",
  message = "Are you sure?",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  dangerous = false,
  onConfirm,
  onCancel,
  children,
  loading = false,
}) {
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const cancelHandler = useRef(onCancel);
  const loadingRef = useRef(loading);
  const titleId = useId();
  const descriptionId = useId();
  cancelHandler.current = onCancel;
  loadingRef.current = loading;

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => {
      if (cancelRef.current && !cancelRef.current.disabled) cancelRef.current.focus();
      else dialogRef.current?.focus();
    });

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!loadingRef.current) cancelHandler.current?.();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ) || []).filter((element) => element.getClientRects().length > 0);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, []);

  return (
    <div className="ui-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !loading && onCancel?.()}>
      <section
        ref={dialogRef}
        className="ui-dialog"
        tabIndex={-1}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <h2 className="ui-dialog-title" id={titleId}>{title}</h2>
        <p className="ui-dialog-copy" id={descriptionId}>{message}</p>
        {children && <div className="ui-dialog-content">{children}</div>}
        <div className="ui-dialog-actions">
          <Button ref={cancelRef} variant="secondary" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={dangerous ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}
