/**
 * MpesaPayModal
 * ~~~~~~~~~~~~~
 * Reusable M-Pesa STK push modal used for:
 *   - Registration fee  (payment_type="registration")
 *   - Savings deposit   (payment_type="deposit",   account_type="bosa"|"fosa")
 *   - Loan repayment    (payment_type="repayment", loan_id=<id>)
 *
 * Props
 * -----
 *   paymentType  : "registration" | "deposit" | "repayment"
 *   amount       : number  (ignored for registration — fee comes from backend)
 *   accountType  : "bosa" | "fosa"   (deposit only)
 *   loanId       : number            (repayment only)
 *   defaultPhone : string            (member's stored phone, pre-fills the field)
 *   onClose      : () => void        (called on cancel or after confirmed)
 *   onConfirmed  : () => void        (called after payment confirmed — parent refreshes)
 */

import React, { useState, useEffect, useRef } from "react";
import api from "../api/axios";

// ── Styles ────────────────────────────────────────────────────────────────────
const overlay = {
  position: "fixed", inset: 0,
  background: "rgba(15,23,42,0.55)",
  display: "flex", justifyContent: "center", alignItems: "center",
  zIndex: 1000,
};
const card = {
  background: "#fff", borderRadius: "16px",
  padding: "32px 28px", width: "100%", maxWidth: "420px",
  boxShadow: "0 20px 60px rgba(0,0,0,.18)",
  fontFamily: "inherit",
};
const label = {
  display: "block", fontSize: "13px", fontWeight: "600",
  color: "#374151", marginBottom: "6px",
};
const input = {
  width: "100%", padding: "10px 12px", borderRadius: "8px",
  border: "1.5px solid #d1d5db", fontSize: "15px",
  outline: "none", boxSizing: "border-box",
};
const btnPrimary = (disabled) => ({
  width: "100%", padding: "12px", borderRadius: "8px",
  background: disabled ? "#93c5fd" : "#2563eb",
  color: "#fff", border: "none", fontSize: "15px",
  fontWeight: "700", cursor: disabled ? "not-allowed" : "pointer",
  marginTop: "16px",
});
const btnSecondary = {
  width: "100%", padding: "11px", borderRadius: "8px",
  background: "transparent", color: "#6b7280",
  border: "1.5px solid #e5e7eb", fontSize: "14px",
  fontWeight: "600", cursor: "pointer", marginTop: "8px",
};

// ── Status icons ──────────────────────────────────────────────────────────────
const ICON = {
  pending:   "📱",
  confirmed: "✅",
  failed:    "❌",
  cancelled: "❌",
};

const POLL_INTERVAL_MS = 3000;   // poll every 3 s
const POLL_MAX_TRIES   = 40;     // give up after 2 minutes

export default function MpesaPayModal({
  paymentType,
  amount,
  accountType,
  loanId,
  defaultPhone = "",
  onClose,
  onConfirmed,
}) {
  const [phone,      setPhone]      = useState(defaultPhone);
  const [stage,      setStage]      = useState("form");   // "form" | "polling" | "done"
  const [pollStatus, setPollStatus] = useState("pending");
  const [receipt,    setReceipt]    = useState("");
  const [error,      setError]      = useState("");
  const [sending,    setSending]    = useState(false);

  const pollTimer   = useRef(null);
  const pollCount   = useRef(0);
  const checkoutRef = useRef("");

  // Clean up polling on unmount
  useEffect(() => () => clearInterval(pollTimer.current), []);

  const titleMap = {
    registration: "Pay Registration Fee",
    deposit:      `Deposit to ${(accountType || "").toUpperCase()}`,
    repayment:    "Repay Loan via M-Pesa",
  };

  const descMap = {
    registration: `KES ${amount || 500} one-time registration fee`,
    deposit:      `KES ${(amount || 0).toLocaleString()} → ${(accountType || "").toUpperCase()} account`,
    repayment:    `KES ${(amount || 0).toLocaleString()} loan repayment`,
  };

  // ── Submit: trigger STK push ───────────────────────────────────────────────
  const handleSubmit = async () => {
    setError("");
    if (!phone.trim()) { setError("Enter your M-Pesa phone number."); return; }

    setSending(true);
    try {
      const body = { payment_type: paymentType, phone: phone.trim() };
      if (paymentType === "deposit")   { body.amount = amount; body.account_type = accountType; }
      if (paymentType === "repayment") { body.amount = amount; body.loan_id = loanId; }

      const res = await api.post("payments/mpesa/stk/", body);
      checkoutRef.current = res.data.checkout_request_id;
      setStage("polling");
      startPolling(res.data.checkout_request_id);
    } catch (err) {
      setError(err.response?.data?.error || "Failed to send STK push. Try again.");
    } finally {
      setSending(false);
    }
  };

  // ── Poll for payment status ────────────────────────────────────────────────
  const startPolling = (cid) => {
    pollCount.current = 0;
    pollTimer.current = setInterval(async () => {
      pollCount.current += 1;
      try {
        const res = await api.get(`payments/mpesa/status/${cid}/`);
        const st  = res.data.status;
        setPollStatus(st);

        if (st === "confirmed") {
          setReceipt(res.data.mpesa_receipt || "");
          clearInterval(pollTimer.current);
          setStage("done");
          // Give parent 1.5 s then refresh data
          setTimeout(() => onConfirmed && onConfirmed(), 1500);
          return;
        }
        if (st === "failed" || st === "cancelled") {
          clearInterval(pollTimer.current);
          setStage("done");
          return;
        }
      } catch (_) { /* network hiccup — keep polling */ }

      if (pollCount.current >= POLL_MAX_TRIES) {
        clearInterval(pollTimer.current);
        setPollStatus("failed");
        setStage("done");
      }
    }, POLL_INTERVAL_MS);
  };

  // ── Render: Form ──────────────────────────────────────────────────────────
  if (stage === "form") {
    return (
      <div style={overlay} role="dialog" aria-modal="true" aria-label="M-Pesa payment">
        <div style={card}>
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "18px", fontWeight: "800", color: "#1e3a8a" }}>
                💚 {titleMap[paymentType]}
              </h2>
              <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#64748b" }}>
                {descMap[paymentType]}
              </p>
            </div>
            <button
              onClick={onClose}
              style={{ background: "none", border: "none", fontSize: "22px", cursor: "pointer", color: "#94a3b8", lineHeight: 1 }}
              aria-label="Close"
            >×</button>
          </div>

          {/* M-Pesa branding strip */}
          <div style={{
            background: "linear-gradient(135deg, #00a550, #007a3d)",
            borderRadius: "10px", padding: "12px 16px",
            marginBottom: "20px", color: "#fff",
            display: "flex", alignItems: "center", gap: "10px",
          }}>
            <span style={{ fontSize: "28px" }}>📲</span>
            <div>
              <div style={{ fontWeight: "700", fontSize: "15px" }}>Lipa Na M-Pesa</div>
              <div style={{ fontSize: "12px", opacity: 0.85 }}>
                An STK push will be sent to your phone. Enter your M-Pesa PIN to complete.
              </div>
            </div>
          </div>

          {/* Phone field */}
          <label style={label} htmlFor="mpesa-phone">M-Pesa Phone Number</label>
          <input
            id="mpesa-phone"
            type="tel"
            placeholder="07XXXXXXXX or +254XXXXXXXX"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            style={input}
            autoFocus
          />
          <p style={{ margin: "6px 0 0", fontSize: "12px", color: "#6b7280" }}>
            This should be the M-Pesa number you want to pay from.
          </p>

          {error && (
            <div style={{
              marginTop: "12px", padding: "10px 14px", borderRadius: "8px",
              background: "#fef2f2", color: "#dc2626", fontSize: "13px", fontWeight: "500",
            }}>
              {error}
            </div>
          )}

          <button
            style={btnPrimary(sending)}
            onClick={handleSubmit}
            disabled={sending}
          >
            {sending ? "Sending…" : "Send STK Push"}
          </button>
          <button style={btnSecondary} onClick={onClose}>Cancel</button>
        </div>
      </div>
    );
  }

  // ── Render: Polling ────────────────────────────────────────────────────────
  if (stage === "polling") {
    return (
      <div style={overlay} role="dialog" aria-modal="true" aria-label="Waiting for M-Pesa payment">
        <div style={{ ...card, textAlign: "center" }}>
          <div style={{ fontSize: "52px", marginBottom: "16px" }}>📱</div>
          <h2 style={{ margin: "0 0 8px", fontSize: "18px", fontWeight: "800", color: "#1e3a8a" }}>
            Check Your Phone
          </h2>
          <p style={{ color: "#64748b", fontSize: "14px", margin: "0 0 24px" }}>
            An M-Pesa prompt has been sent to <strong>{phone}</strong>.
            <br />Enter your PIN to complete the payment.
          </p>

          {/* Animated spinner */}
          <div style={{
            width: "48px", height: "48px", borderRadius: "50%",
            border: "4px solid #e5e7eb", borderTopColor: "#00a550",
            animation: "spin 0.9s linear infinite", margin: "0 auto 20px",
          }} />

          <p style={{ fontSize: "12px", color: "#94a3b8" }}>
            Waiting for confirmation… checking every 3 seconds
          </p>

          <button
            style={{ ...btnSecondary, marginTop: "20px" }}
            onClick={() => { clearInterval(pollTimer.current); onClose(); }}
          >
            Cancel
          </button>

          {/* Keyframe injected inline once */}
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  // ── Render: Done ───────────────────────────────────────────────────────────
  const success = pollStatus === "confirmed";
  return (
    <div style={overlay} role="dialog" aria-modal="true" aria-label="Payment result">
      <div style={{ ...card, textAlign: "center" }}>
        <div style={{ fontSize: "60px", marginBottom: "12px" }}>
          {ICON[pollStatus] || "❓"}
        </div>
        <h2 style={{
          margin: "0 0 8px", fontSize: "20px", fontWeight: "800",
          color: success ? "#16a34a" : "#dc2626",
        }}>
          {success ? "Payment Confirmed!" : "Payment Not Completed"}
        </h2>

        {success ? (
          <div style={{ color: "#374151", fontSize: "14px", lineHeight: "1.6" }}>
            <p style={{ margin: "0 0 8px" }}>
              <strong>KES {(amount || 0).toLocaleString()}</strong> received successfully.
            </p>
            {receipt && (
              <p style={{
                margin: "0", background: "#f0fdf4", border: "1px solid #bbf7d0",
                borderRadius: "8px", padding: "10px 14px",
                fontFamily: "monospace", fontSize: "15px", color: "#16a34a", fontWeight: "700",
              }}>
                M-Pesa Ref: {receipt}
              </p>
            )}
          </div>
        ) : (
          <p style={{ color: "#64748b", fontSize: "14px" }}>
            {pollStatus === "failed"    && "The payment was not completed. You may have cancelled or the request timed out."}
            {pollStatus === "cancelled" && "You cancelled the M-Pesa request."}
          </p>
        )}

        <button
          style={{ ...btnPrimary(false), marginTop: "20px", background: success ? "#16a34a" : "#2563eb" }}
          onClick={onClose}
        >
          {success ? "Done" : "Close"}
        </button>
      </div>
    </div>
  );
}
