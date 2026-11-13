import React from "react";

/**
 * InactivityWarning
 * ~~~~~~~~~~~~~~~~~
 * Full-screen overlay that appears 60 seconds before auto-logout.
 * Shows a countdown and a "Stay Logged In" button.
 */
export default function InactivityWarning({ secondsLeft, onStayLoggedIn }) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(15,23,42,0.85)",
      display: "flex", justifyContent: "center", alignItems: "center",
      padding: "16px",
    }}>
      <div style={{
        background: "#fff", borderRadius: "16px",
        padding: "36px 40px", maxWidth: "420px", width: "100%",
        textAlign: "center", boxShadow: "0 24px 64px rgba(0,0,0,.3)",
      }}>
        {/* Warning icon */}
        <div style={{ fontSize: "52px", marginBottom: "12px" }}>⏰</div>

        <h2 style={{ margin: "0 0 10px", fontSize: "20px", fontWeight: "800", color: "#0f172a" }}>
          Still there?
        </h2>
        <p style={{ margin: "0 0 20px", fontSize: "14px", color: "#475569", lineHeight: 1.6 }}>
          For your security, you will be automatically logged out in
        </p>

        {/* Countdown */}
        <div style={{
          fontSize: "52px", fontWeight: "900",
          color: secondsLeft <= 10 ? "#dc2626" : "#2563eb",
          marginBottom: "24px", lineHeight: 1,
          transition: "color .3s",
        }}>
          {secondsLeft}s
        </div>

        <button
          onClick={onStayLoggedIn}
          autoFocus
          style={{
            width: "100%", padding: "13px", borderRadius: "10px",
            background: "var(--primary, #2563eb)", color: "#fff",
            border: "none", fontSize: "15px", fontWeight: "700",
            cursor: "pointer", marginBottom: "10px",
          }}
        >
          ✋ Stay Logged In
        </button>

        <p style={{ margin: 0, fontSize: "11px", color: "#94a3b8" }}>
          Using a shared computer? Log out now to protect your account.
        </p>
      </div>
    </div>
  );
}
