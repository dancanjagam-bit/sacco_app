import React, { useState, useRef } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import api from "../api/axios";
import "../styles/auth.css";

function VerifyOTP() {
  const navigate  = useNavigate();
  const location  = useLocation();

  // Pre-filled from ForgotPassword navigation state
  const { identifier: preIdentifier = "", method = "" } = location.state || {};

  const [identifier, setIdentifier] = useState(preIdentifier);
  const [digits, setDigits]         = useState(Array(6).fill(""));
  const [loading, setLoading]       = useState(false);
  const [message, setMessage]       = useState(null);
  const inputRefs                   = useRef([]);

  const code = digits.join("");

  // ── OTP box input handler ──────────────────────────────────────────────
  const handleDigit = (index, value) => {
    if (!/^\d?$/.test(value)) return;           // digits only
    const next = [...digits];
    next[index] = value;
    setDigits(next);
    if (value && index < 5) inputRefs.current[index + 1]?.focus();
  };

  const handleKeyDown = (index, e) => {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 6) {
      setDigits(pasted.split(""));
      inputRefs.current[5]?.focus();
    }
    e.preventDefault();
  };

  // ── Submit ─────────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);

    if (code.length < 6) {
      setMessage({ type: "error", text: "Please enter the full 6-digit OTP." });
      return;
    }

    setLoading(true);

    try {
      await api.post("verify-otp/", { identifier, code });

      setMessage({ type: "success", text: "OTP verified! Redirecting to reset password..." });

      setTimeout(() => {
        navigate("/reset-password", { state: { identifier, code } });
      }, 1500);
    } catch (err) {
      const data = err.response?.data;
      setMessage({ type: "error", text: data?.error || "Invalid OTP. Please try again." });
      setDigits(Array(6).fill(""));
      inputRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  // ── Resend OTP ─────────────────────────────────────────────────────────
  const resendOTP = async () => {
    if (!identifier) return;
    setMessage(null);

    try {
      const res = await api.post("forgot-password/", {
        identifier,
        method: method || "email",
      });
      const hint = res.data.otp_code ? ` (Dev: ${res.data.otp_code})` : "";
      setMessage({ type: "success", text: "New OTP sent!" + hint });
    } catch {
      setMessage({ type: "error", text: "Failed to resend OTP." });
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🔢</div>
        <h1 className="auth-title">Enter OTP</h1>
        <p className="auth-subtitle">
          Enter the 6-digit code sent to your{" "}
          {method ? method.replace(/_/g, " ") : "registered contact"}
        </p>

        {message && (
          <div className={`auth-message ${message.type}`}>
            {message.text}
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          {/* Show identifier field if not pre-filled */}
          {!preIdentifier && (
            <div>
              <label>Username or Email</label>
              <input
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="Your username or email"
                required
              />
            </div>
          )}

          {/* 6-digit OTP boxes */}
          <div style={{
            display: "flex",
            gap: "10px",
            justifyContent: "center",
            margin: "8px 0",
          }}>
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => (inputRefs.current[i] = el)}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={d}
                onChange={(e) => handleDigit(i, e.target.value)}
                onKeyDown={(e) => handleKeyDown(i, e)}
                onPaste={i === 0 ? handlePaste : undefined}
                style={{
                  width: "48px",
                  height: "56px",
                  textAlign: "center",
                  fontSize: "24px",
                  fontWeight: "700",
                  border: `2px solid ${d ? "#2563eb" : "#e2e8f0"}`,
                  borderRadius: "10px",
                  outline: "none",
                  background: d ? "#eff6ff" : "#f8fafc",
                  transition: "border-color .15s",
                }}
                autoFocus={i === 0}
              />
            ))}
          </div>

          <button className="auth-button" type="submit" disabled={loading || code.length < 6}>
            {loading ? "Verifying..." : "Verify OTP →"}
          </button>
        </form>

        <div className="auth-footer" style={{ marginTop: "16px" }}>
          Didn't receive it?{" "}
          <button
            onClick={resendOTP}
            style={{ background: "none", border: "none", color: "#2563eb", fontWeight: "600", cursor: "pointer", fontSize: "14px", padding: 0 }}
          >
            Resend OTP
          </button>
        </div>

        <div className="auth-footer">
          <Link to="/forgot-password">← Change recovery method</Link>
        </div>
      </div>
    </div>
  );
}

export default VerifyOTP;
