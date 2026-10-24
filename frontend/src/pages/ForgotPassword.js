import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../api/axios";
import "../styles/auth.css";

function ForgotPassword() {
  const navigate = useNavigate();

  const [identifier, setIdentifier] = useState("");
  const [method, setMethod]         = useState("email");
  const [loading, setLoading]       = useState(false);
  const [message, setMessage]       = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);
    setLoading(true);

    try {
      const res = await api.post("forgot-password/", { identifier, method });

      // In dev mode the API returns the OTP code directly
      const otpHint = res.data.otp_code
        ? ` (Dev mode — your OTP is: ${res.data.otp_code})`
        : "";

      setMessage({ type: "success", text: res.data.message + otpHint });

      // Move to verify page after 2 s
      setTimeout(() => {
        navigate("/verify-otp", { state: { identifier, method } });
      }, 2000);
    } catch (err) {
      const data = err.response?.data;
      setMessage({ type: "error", text: data?.error || "Request failed. Please try again." });
    } finally {
      setLoading(false);
    }
  };

  const methodLabels = {
    email:          "📧 Primary Email",
    recovery_email: "📧 Recovery Email",
    phone:          "📱 Phone Number (SMS)",
    recovery_phone: "📱 Recovery Phone (SMS)",
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🔑</div>
        <h1 className="auth-title">Forgot Password?</h1>
        <p className="auth-subtitle">
          Enter your username or email and choose how to receive your OTP
        </p>

        {message && (
          <div className={`auth-message ${message.type}`}>
            {message.text}
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div>
            <label>Username or Email</label>
            <input
              type="text"
              placeholder="Enter your username or email"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div>
            <label>Send OTP via</label>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              {Object.entries(methodLabels).map(([val, label]) => (
                <option key={val} value={val}>{label}</option>
              ))}
            </select>
          </div>

          <p style={{ fontSize: "12px", color: "#94a3b8", margin: 0 }}>
            Make sure you registered a {methodLabels[method].replace(/^.+? /, "")} to use this option.
          </p>

          <button className="auth-button" type="submit" disabled={loading}>
            {loading ? "Sending OTP..." : "Send OTP →"}
          </button>
        </form>

        <div className="auth-footer">
          <Link to="/">← Back to Login</Link>
        </div>
      </div>
    </div>
  );
}

export default ForgotPassword;
