import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import "../styles/dashboard.css";

function Profile() {
  const { refreshUser } = useAuth();

  const [profile, setProfile]   = useState(null);
  const [editing, setEditing]   = useState(false);
  const [saving,  setSaving]    = useState(false);
  const [message, setMessage]   = useState(null);

  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone_number: "",
    county: "",
    address: "",
    recovery_email: "",
    recovery_phone: "",
  });

  useEffect(() => { fetchProfile(); }, []);

  const fetchProfile = async () => {
    try {
      const res = await api.get("profile/");
      setProfile(res.data);
      setForm({
        first_name:     res.data.first_name     || "",
        last_name:      res.data.last_name      || "",
        email:          res.data.email          || "",
        phone_number:   res.data.phone_number   || "",
        county:         res.data.county         || "",
        address:        res.data.address        || "",
        recovery_email: res.data.recovery_email || "",
        recovery_phone: res.data.recovery_phone || "",
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);

    try {
      await api.put("profile/", form);
      setMessage({ type: "success", text: "Profile updated successfully!" });
      setEditing(false);
      fetchProfile();
      refreshUser();
    } catch (err) {
      const data = err.response?.data;
      const msg = data?.error ||
        Object.entries(data || {})
          .map(([f, e]) => `${f.replace(/_/g," ")}: ${Array.isArray(e) ? e[0] : e}`)
          .join(" • ") ||
        "Update failed.";
      setMessage({ type: "error", text: msg });
    } finally {
      setSaving(false);
    }
  };

  const field = (label, key, type = "text", placeholder = "") => (
    <div style={{ marginBottom: "16px" }}>
      <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "6px" }}>
        {label}
      </label>
      {editing ? (
        type === "textarea" ? (
          <textarea
            name={key}
            value={form[key]}
            onChange={handleChange}
            className="amount-input"
            style={{ width: "100%", minHeight: "70px", resize: "vertical" }}
            placeholder={placeholder}
          />
        ) : (
          <input
            type={type}
            name={key}
            value={form[key]}
            onChange={handleChange}
            className="amount-input"
            style={{ width: "100%" }}
            placeholder={placeholder}
          />
        )
      ) : (
        <p style={{ margin: 0, fontSize: "15px", fontWeight: "500", color: "#1e293b" }}>
          {form[key] || <span style={{ color: "#94a3b8" }}>Not set</span>}
        </p>
      )}
    </div>
  );

  return (
    <Layout>
      <h2 className="section-title">👤 My Profile</h2>
      <p className="section-subtitle">View and update your personal information</p>

      {message && (
        <div className={`alert alert-${message.type}`} style={{ maxWidth: "680px" }}>
          {message.text}
        </div>
      )}

      {!profile ? (
        <p style={{ color: "#6b7280" }}>Loading profile...</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", maxWidth: "900px" }}>

          {/* Left — Personal info */}
          <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: "700" }}>Personal Information</h3>
              {!editing && (
                <button
                  onClick={() => { setEditing(true); setMessage(null); }}
                  style={{ padding: "6px 14px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "6px", fontSize: "13px", fontWeight: "600", cursor: "pointer" }}
                >
                  ✏️ Edit
                </button>
              )}
            </div>

            <form onSubmit={handleSave}>
              {field("First Name",    "first_name",   "text", "Enter first name")}
              {field("Last Name",     "last_name",    "text", "Enter last name")}
              {field("Email Address", "email",        "email","Enter email")}
              {field("Phone Number",  "phone_number", "text", "e.g. 0722 000 000")}
              {field("County",        "county",       "text", "County")}
              {field("Address",       "address",      "textarea", "Physical address")}

              <p style={{ fontSize:"12px", fontWeight:"700", color:"#94a3b8", textTransform:"uppercase", letterSpacing:".5px", margin:"4px 0" }}>
                Recovery Contacts
              </p>
              {field("Recovery Email", "recovery_email", "email", "backup@email.com")}
              {field("Recovery Phone", "recovery_phone", "text",  "e.g. 0733 000 000")}

              {editing && (
                <div style={{ display: "flex", gap: "10px", marginTop: "8px" }}>
                  <button
                    type="submit"
                    disabled={saving}
                    style={{ padding: "9px 20px", background: "var(--success)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}
                  >
                    {saving ? "Saving..." : "✅ Save Changes"}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setEditing(false); setMessage(null); }}
                    style={{ padding: "9px 20px", background: "#f1f5f9", color: "#475569", border: "1px solid var(--border)", borderRadius: "8px", fontWeight: "600", fontSize: "14px", cursor: "pointer" }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </form>
          </div>

          {/* Right — Account info + financial snapshot */}
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

            {/* Account details (read-only) */}
            <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)" }}>
              <h3 style={{ margin: "0 0 18px", fontSize: "16px", fontWeight: "700" }}>Account Details</h3>

              {[
                ["Member Number", profile.member_number],
                ["Username",      profile.username],
                ["Gender",        profile.gender],
                ["Date of Birth", profile.date_of_birth],
                ["Date Joined",   profile.date_joined],
                ["Status",        profile.status],
              ].map(([label, value]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid var(--border)", fontSize: "14px" }}>
                  <span style={{ color: "#64748b", fontWeight: "500" }}>{label}</span>
                  <span style={{ fontWeight: "600", color: "#1e293b" }}>{value || "—"}</span>
                </div>
              ))}
            </div>

            {/* Financial snapshot */}
            <div style={{ background: "linear-gradient(135deg, #1e3a8a, #2563eb)", borderRadius: "12px", padding: "24px", color: "#fff", boxShadow: "var(--shadow)" }}>
              <h3 style={{ margin: "0 0 18px", fontSize: "16px", fontWeight: "700", color: "#fff" }}>Financial Snapshot</h3>

              {[
                ["💰 Total Savings",    `KES ${Number(profile.total_savings || 0).toLocaleString()}`],
                ["🏦 Total Loans",      profile.total_loans ?? "0"],
                ["✅ Approved Loans",   profile.approved_loans ?? "0"],
              ].map(([label, value]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid rgba(255,255,255,.12)", fontSize: "14px" }}>
                  <span style={{ color: "rgba(255,255,255,.75)" }}>{label}</span>
                  <span style={{ fontWeight: "700" }}>{value}</span>
                </div>
              ))}
            </div>

            {/* Security link */}
            <div style={{ background: "#fff", borderRadius: "12px", padding: "20px 24px", boxShadow: "var(--shadow)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <p style={{ margin: "0 0 2px", fontWeight: "700", fontSize: "14px" }}>🔒 Password</p>
                <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>Update your login password</p>
              </div>
              <Link
                to="/change-password"
                style={{ padding: "8px 16px", background: "var(--primary)", color: "#fff", borderRadius: "8px", fontSize: "13px", fontWeight: "600", textDecoration: "none" }}
              >
                Change
              </Link>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}

export default Profile;
