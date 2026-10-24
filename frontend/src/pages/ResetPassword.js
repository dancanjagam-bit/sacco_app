import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import api from "../api/axios";
import "../styles/auth.css";

function ResetPassword() {
  const navigate  = useNavigate();
  const location  = useLocation();

  const { identifier = "", code = "" } = location.state || {};

  const [form, setForm]     = useState({ new_password: "", confirm_password: "" });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setMessage(null);
  };

  // Live password-strength checks
  const pw = form.new_password;
  const checks = {
    length:  pw.length >= 8,
    letter:  /[A-Za-z]/.test(pw),
    number:  /\d/.test(pw),
    match:   pw === form.confirm_password && pw.length > 0,
  };
  const allGood = Object.values(checks).every(Boolean);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);

    if (!allGood) {
      setMessage({ type: "error", text: "Please satisfy all password requirements." });
      return;
    }

    setLoading(true);

    try {
      const res = await api.post("reset-password/", {
        identifier,
        code,
        new_password:     form.new_password,
        confirm_password: form.confirm_password,
      });

      setMessage({ type: "success", text: res.data.message + " Redirecting to login..." });

      setTimeout(() => navigate("/"), 2500);
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.error ||
        Object.entries(data || {})
          .map(([f, e]) => `${f.replace(/_/g, " ")}: ${Array.isArray(e) ? e[0] : e}`)
          .join(" • ") ||
        "Reset failed.";
      setMessage({ type: "error", text: msg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🔐</div>
        <h1 className="auth-title">Set New Password</h1>
        <p className="auth-subtitle">
          Choose a strong password for your account
        </p>

        {message && (
          <div className={`auth-message ${message.type}`}>
            {message.text}
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div>
            <label>New Password</label>
            <input
              type="password"
              name="new_password"
              value={form.new_password}
              onChange={handleChange}
              placeholder="Enter new password"
              required
              autoFocus
            />
          </div>

          {/* Live strength checklist */}
          {pw.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "4px", fontSize: "13px" }}>
              {[
                ["length",  "At least 8 characters"],
                ["letter",  "Contains a letter"],
                ["number",  "Contains a number"],
              ].map(([key, label]) => (
                <span key={key} style={{ color: checks[key] ? "#16a34a" : "#94a3b8" }}>
                  {checks[key] ? "✅" : "○"} {label}
                </span>
              ))}
            </div>
          )}

          <div>
            <label>Confirm Password</label>
            <input
              type="password"
              name="confirm_password"
              value={form.confirm_password}
              onChange={handleChange}
              placeholder="Repeat new password"
              required
            />
          </div>

          {form.confirm_password.length > 0 && (
            <span style={{ fontSize: "13px", color: checks.match ? "#16a34a" : "#dc2626" }}>
              {checks.match ? "✅ Passwords match" : "⚠️ Passwords do not match"}
            </span>
          )}

          <button
            className="auth-button"
            type="submit"
            disabled={loading || !allGood}
          >
            {loading ? "Resetting..." : "🔐 Reset Password"}
          </button>
        </form>

        <div className="auth-footer">
          <Link to="/">← Back to Login</Link>
        </div>
      </div>
    </div>
  );
}

export default ResetPassword;
