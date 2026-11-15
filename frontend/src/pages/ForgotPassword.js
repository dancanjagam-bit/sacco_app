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
      const { data } = await api.post("forgot-password/", { identifier, method });
      navigate("/verify-otp", { state: { identifier, method, deliveryMessage: data.message } });
    } catch (err) {
      const data = err.response?.data;
      setMessage({ type: "error", text: data?.error || "Request failed. Please try again." });
    } finally {
      setLoading(false);
    }
  };

  const methodLabels = {
    email:          "Registered email",
    recovery_email: "Recovery email, if verified",
    phone:          "Registered phone (SMS)",
    recovery_phone: "Recovery phone (SMS), if verified",
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
            <label htmlFor="recovery-identifier">Username or registered email</label>
            <input
              id="recovery-identifier"
              type="text"
              placeholder="Enter your username or email"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="recovery-method">Send code via</label>
            <select
              id="recovery-method"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              {Object.entries(methodLabels).map(([val, label]) => (
                <option key={val} value={val}>{label}</option>
              ))}
            </select>
          </div>

          {(method === "recovery_email" || method === "recovery_phone") && (
            <p className="auth-field-note">
              If you haven't verified a recovery contact, we'll use your registered {method === "recovery_email" ? "email" : "phone"}.
            </p>
          )}

          <button className="auth-button" type="submit" disabled={loading}>
            {loading ? "Sending OTP..." : "Send OTP →"}
          </button>
        </form>

        <div className="auth-footer">
          <Link to="/login">← Back to Login</Link>
        </div>
      </div>
    </div>
  );
}

export default ForgotPassword;
