import React from "react";

/**
 * ConfirmModal — a non-blocking, accessible replacement for window.confirm and window.prompt.
 *
 * Props:
 *   title        string   — heading text
 *   message      string   — body message / warning
 *   confirmLabel string   — confirm button label (default "Confirm")
 *   cancelLabel  string   — cancel button label (default "Cancel")
 *   dangerous    bool     — if true the confirm button renders in red
 *   onConfirm    fn()     — called when user clicks confirm
 *   onCancel     fn()     — called when user clicks cancel or backdrop
 *   children             — optional extra content (e.g. a <textarea> for a reason)
 */
export default function ConfirmModal({
  title        = "Confirm Action",
  message      = "Are you sure?",
  confirmLabel = "Confirm",
  cancelLabel  = "Cancel",
  dangerous    = false,
  onConfirm,
  onCancel,
  children,
}) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.55)",
        display: "flex", justifyContent: "center", alignItems: "center",
        zIndex: 1000, padding: "16px",
      }}
      onClick={onCancel}
    >
      <div
        style={{
          background: "#fff", borderRadius: "14px", padding: "28px 32px",
          width: "100%", maxWidth: "420px", boxShadow: "0 24px 64px rgba(0,0,0,.2)",
        }}
        onClick={e => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-desc"
      >
        <h3 id="confirm-title" style={{ margin: "0 0 10px", fontSize: "17px", fontWeight: "800", color: "#0f172a" }}>
          {title}
        </h3>
        <p id="confirm-desc" style={{ margin: "0 0 16px", fontSize: "14px", color: "#475569", lineHeight: 1.6 }}>
          {message}
        </p>

        {children && <div style={{ marginBottom: "16px" }}>{children}</div>}

        <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{
              padding: "9px 20px", borderRadius: "8px", border: "1.5px solid #e2e8f0",
              background: "#fff", color: "#475569", fontWeight: "600", fontSize: "13px",
              cursor: "pointer",
            }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            autoFocus
            style={{
              padding: "9px 20px", borderRadius: "8px", border: "none",
              background: dangerous ? "#dc2626" : "var(--primary)",
              color: "#fff", fontWeight: "700", fontSize: "13px", cursor: "pointer",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
