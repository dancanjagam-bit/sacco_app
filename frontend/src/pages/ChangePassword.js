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

  const [message, setMessage]   = useState(null);
  const [loading, setLoading]   = useState(false);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setMessage(null);
  };

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
          .map(([f, e]) => `${f.replace(/_/g," ")}: ${Array.isArray(e) ? e[0] : e}`)
          .join(" • ");
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
        <p className="section-subtitle">
          Update your account password. You'll need your current password.
        </p>

        {message && (
          <div className={`alert alert-${message.type}`}>
            {message.text}
          </div>
        )}

        <div style={{
          background: "#fff",
          borderRadius: "12px",
          padding: "28px",
          boxShadow: "var(--shadow)",
        }}>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div>
              <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                Current Password
              </label>
              <input
                type="password"
                name="old_password"
                value={form.old_password}
                onChange={handleChange}
                placeholder="Enter current password"
                required
                className="amount-input"
                style={{ width: "100%" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                New Password
              </label>
              <input
                type="password"
                name="new_password"
                value={form.new_password}
                onChange={handleChange}
                placeholder="At least 8 characters"
                required
                className="amount-input"
                style={{ width: "100%" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                Confirm New Password
              </label>
              <input
                type="password"
                name="confirm_password"
                value={form.confirm_password}
                onChange={handleChange}
                placeholder="Repeat new password"
                required
                className="amount-input"
                style={{ width: "100%" }}
              />
            </div>

            {/* Password strength hint */}
            {form.new_password && (
              <div style={{ fontSize: "12px", color: form.new_password.length >= 8 ? "#16a34a" : "#dc2626" }}>
                {form.new_password.length >= 8
                  ? "✅ Password length OK"
                  : `⚠️ ${8 - form.new_password.length} more character(s) needed`}
              </div>
            )}

            {form.confirm_password && (
              <div style={{ fontSize: "12px", color: form.new_password === form.confirm_password ? "#16a34a" : "#dc2626" }}>
                {form.new_password === form.confirm_password ? "✅ Passwords match" : "⚠️ Passwords do not match"}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="auth-button"
              style={{ marginTop: "8px" }}
            >
              {loading ? "Updating..." : "🔒 Change Password"}
            </button>
          </form>
        </div>
      </div>
    </Layout>
  );
}

export default ChangePassword;
