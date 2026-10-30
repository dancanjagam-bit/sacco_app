import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";
import "../styles/auth.css";

function ChangePassword() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    old_password: "",
    new_password: "",
    confirm_password: "",
  });

  const [showOld,     setShowOld]     = useState(false);
  const [showNew,     setShowNew]     = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setMessage(null);
  };

  const pw = form.new_password;
  const pwChecks = {
    length: pw.length >= 8,
    letter: /[A-Za-z]/.test(pw),
    number: /\d/.test(pw),
  };
  const allGood = pwChecks.length && pwChecks.letter && pwChecks.number && form.new_password === form.confirm_password;

  const pwField = (label, name, showState, placeholder) => (
    <div className="auth-field">
      <label>{label}</label>
      <div className="auth-input-wrap">
        <span className="auth-input-icon">🔒</span>
        <input
          type={showState[0] ? "text" : "password"}
          name={name}
          value={form[name]}
          onChange={handleChange}
          placeholder={placeholder}
          required
          className="auth-input-with-icon"
          style={{ paddingRight: "48px" }}
        />
        <button type="button" onClick={() => showState[1](!showState[0])} className="auth-toggle-pw" tabIndex={-1}>
          {showState[0] ? "🙈" : "👁️"}
        </button>
      </div>
    </div>
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);

    if (form.new_password !== form.confirm_password) {
      setMessage({ type: "error", text: "New passwords do not match." });
      return;
    }

    if (form.new_password.length < 8) {
      setMessage({ type: "error", text: "New password must be at least 8 characters." });
      return;
    }

    setLoading(true);

    try {
      await api.post("change-password/", form);
      setMessage({ type: "success", text: "Password changed successfully! Redirecting..." });
      setForm({ old_password: "", new_password: "", confirm_password: "" });
      setTimeout(() => navigate("/dashboard"), 2000);
    } catch (err) {
      const data = err.response?.data;
      if (data?.error) {
        setMessage({ type: "error", text: data.error });
      } else if (data) {
        const msg = Object.entries(data)
          .map(([f, e]) => `${f.replace(/_/g, " ")}: ${Array.isArray(e) ? e[0] : e}`)
          .join(" - ");
        setMessage({ type: "error", text: msg });
      } else {
        setMessage({ type: "error", text: "Failed to change password." });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div style={{ maxWidth: "480px" }}>
        <h2 className="section-title">🔒 Change Password</h2>
        <p className="section-subtitle">Update your account password securely</p>

        {message && (
          <div className={`alert alert-${message.type}`} style={{ marginBottom: "16px" }}>
            {message.text}
          </div>
        )}

        <div style={{ background: "#fff", borderRadius: "16px", padding: "28px", boxShadow: "var(--shadow)" }}>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
            {pwField("Current Password", "old_password", [showOld, setShowOld], "Enter current password")}
            {pwField("New Password", "new_password", [showNew, setShowNew], "At least 8 characters")}

            {/* Live strength checklist */}
            {pw.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px", fontSize: "13px", margin: "-8px 0" }}>
                {[
                  ["length", "8+ characters"],
                  ["letter", "Contains a letter"],
                  ["number", "Contains a number"],
                ].map(([k, l]) => (
                  <span key={k} style={{ color: pwChecks[k] ? "#16a34a" : "#94a3b8" }}>
                    {pwChecks[k] ? "✅" : "○"} {l}
                  </span>
                ))}
              </div>
            )}

            {pwField("Confirm New Password", "confirm_password", [showConfirm, setShowConfirm], "Repeat new password")}

            {form.confirm_password && (
              <span style={{ fontSize: "13px", color: form.new_password === form.confirm_password ? "#16a34a" : "#dc2626" }}>
                {form.new_password === form.confirm_password ? "✅ Passwords match" : "⚠️ Passwords do not match"}
              </span>
            )}

            <button type="submit" disabled={loading || !allGood} className="auth-button" style={{ marginTop: "4px" }}>
              {loading ? (
                <>
                  <span className="auth-spinner" />
                  Updating...
                </>
              ) : (
                "🔒 Change Password"
              )}
            </button>
          </form>
        </div>
      </div>
    </Layout>
  );
}

export default ChangePassword;
