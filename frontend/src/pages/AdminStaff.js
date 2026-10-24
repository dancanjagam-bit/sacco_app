import React, { useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

const ROLES = [
  ["superadmin",   "Super Administrator"],
  ["loan_officer", "Loan Officer"],
  ["accountant",   "Accountant"],
  ["secretary",    "Secretary"],
  ["it_admin",     "IT Administrator"],
];

const ROLE_COLORS = {
  superadmin:   { bg: "#fef3c7", color: "#92400e" },
  loan_officer: { bg: "#dbeafe", color: "#1e40af" },
  accountant:   { bg: "#dcfce7", color: "#15803d" },
  secretary:    { bg: "#f3e8ff", color: "#7e22ce" },
  it_admin:     { bg: "#e0f2fe", color: "#0369a1" },
};

function RoleBadge({ role, label }) {
  const c = ROLE_COLORS[role] || { bg: "#f1f5f9", color: "#475569" };
  return (
    <span style={{ padding: "3px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: "700", background: c.bg, color: c.color }}>
      {label || role}
    </span>
  );
}

export default function AdminStaff() {
  const [staff,    setStaff]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [msg,      setMsg]      = useState(null);

  const [form, setForm] = useState({
    username: "", password: "", first_name: "", last_name: "",
    email: "", role: "loan_officer", department: "", hire_date: "",
  });

  useEffect(() => { fetchStaff(); }, []);

  const fetchStaff = async () => {
    setLoading(true);
    try {
      const res = await api.get("admin/staff/");
      setStaff(res.data);
    } catch (err) {
      setMsg({ type: "error", text: err.response?.data?.detail || "Failed to load staff." });
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const handleCreate = async (e) => {
    e.preventDefault();
    setMsg(null);
    try {
      const res = await api.post("admin/staff/", form);
      setMsg({ type: "success", text: res.data.message });
      setShowForm(false);
      setForm({ username: "", password: "", first_name: "", last_name: "", email: "", role: "loan_officer", department: "", hire_date: "" });
      fetchStaff();
    } catch (err) {
      const data = err.response?.data;
      const text = data?.error || Object.entries(data || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v[0] : v}`).join(" • ") || "Failed.";
      setMsg({ type: "error", text });
    }
  };

  const handleUpdate = async (staffId, updates) => {
    try {
      await api.put(`admin/staff/${staffId}/`, updates);
      setMsg({ type: "success", text: "Updated successfully." });
      fetchStaff();
    } catch (err) {
      setMsg({ type: "error", text: "Update failed." });
    }
  };

  const handleDeactivate = async (staffId, name) => {
    if (!window.confirm(`Deactivate ${name}? They will lose all admin access.`)) return;
    try {
      await api.delete(`admin/staff/${staffId}/`);
      setMsg({ type: "success", text: "Staff account deactivated." });
      fetchStaff();
    } catch (err) {
      setMsg({ type: "error", text: err.response?.data?.error || "Failed." });
    }
  };

  const fld = (label, name, type = "text", placeholder = "", required = false) => (
    <div>
      <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" }}>
        {label}{required && <span style={{ color: "#dc2626" }}> *</span>}
      </label>
      <input
        type={type} name={name} value={form[name]}
        onChange={handleChange} placeholder={placeholder}
        className="amount-input" style={{ width: "100%" }}
        required={required}
      />
    </div>
  );

  return (
    <Layout>
      {() => (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title">👨‍💼 Staff Management</h2>
              <p className="section-subtitle">Create and manage admin accounts and roles</p>
            </div>
            <button
              onClick={() => { setShowForm(!showForm); setMsg(null); }}
              style={{ padding: "10px 20px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}
            >
              {showForm ? "✕ Cancel" : "+ Add Staff"}
            </button>
          </div>

          {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

          {/* Create form */}
          {showForm && (
            <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)", marginBottom: "24px" }}>
              <h3 style={{ margin: "0 0 20px", fontSize: "16px", fontWeight: "700" }}>Create New Staff Account</h3>
              <form onSubmit={handleCreate} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                {fld("First Name",  "first_name",  "text", "e.g. Jane",          true)}
                {fld("Last Name",   "last_name",   "text", "e.g. Wanjiku",       true)}
                {fld("Username",    "username",    "text", "e.g. jane.w",        true)}
                {fld("Email",       "email",       "email","jane@sacco.co.ke",   true)}
                {fld("Password",    "password",    "password","Min 8 chars",     true)}
                {fld("Department",  "department",  "text", "e.g. Finance",       false)}
                {fld("Hire Date",   "hire_date",   "date", "",                   false)}
                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" }}>
                    Role <span style={{ color: "#dc2626" }}>*</span>
                  </label>
                  <select name="role" value={form.role} onChange={handleChange} className="amount-input" style={{ width: "100%" }} required>
                    {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div style={{ gridColumn: "1/-1" }}>
                  <button type="submit" style={{ padding: "12px 28px", background: "var(--success)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
                    ✅ Create Staff Account
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Staff table */}
          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading staff...</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {staff.length === 0 ? (
                  <tr><td colSpan="8" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>No staff accounts yet.</td></tr>
                ) : staff.map((s) => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: "600" }}>{s.full_name || s.username}</td>
                    <td style={{ color: "#64748b", fontSize: "13px" }}>{s.username}</td>
                    <td style={{ fontSize: "13px" }}>{s.email}</td>
                    <td><RoleBadge role={s.role} label={s.role_label} /></td>
                    <td style={{ fontSize: "13px", color: "#64748b" }}>{s.department || "—"}</td>
                    <td>
                      <span className={`status status-${s.status === "active" ? "approved" : "rejected"}`}>
                        {s.status}
                      </span>
                    </td>
                    <td style={{ fontSize: "12px" }}>{s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}</td>
                    <td>
                      <div style={{ display: "flex", gap: "6px" }}>
                        {/* Quick role change */}
                        <select
                          defaultValue={s.role}
                          onChange={(e) => handleUpdate(s.id, { role: e.target.value })}
                          style={{ padding: "5px 8px", borderRadius: "6px", border: "1px solid #e2e8f0", fontSize: "12px", cursor: "pointer" }}
                        >
                          {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                        {s.status === "active" && (
                          <button
                            onClick={() => handleDeactivate(s.id, s.full_name || s.username)}
                            style={{ padding: "5px 10px", background: "#fee2e2", color: "#b91c1c", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}
                          >
                            Deactivate
                          </button>
                        )}
                        {s.status !== "active" && (
                          <button
                            onClick={() => handleUpdate(s.id, { status: "active" })}
                            style={{ padding: "5px 10px", background: "#dcfce7", color: "#15803d", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}
                          >
                            Reactivate
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Layout>
  );
}
