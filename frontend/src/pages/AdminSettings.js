import React, { useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

export default function AdminSettings() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [saving,  setSaving]     = useState(false);
  const [msg,     setMsg]        = useState(null);

  const [form, setForm] = useState({
    release_hierarchy: "guarantor_first",
    default_ltv_ratio: "80",
    min_savings_retention: "33",
    sasra_enabled: true,
    sasra_report_interval_days: 90,
  });

  useEffect(() => { fetchSettings(); }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await api.get("admin/settings/");
      setSettings(res.data);
      setForm({
        release_hierarchy: res.data.release_hierarchy,
        default_ltv_ratio: String(res.data.default_ltv_ratio),
        min_savings_retention: String(res.data.min_savings_retention),
        sasra_enabled: res.data.sasra_enabled,
        sasra_report_interval_days: res.data.sasra_report_interval_days,
      });
    } catch { setMsg({ type: "error", text: "Failed to load settings." }); }
    finally { setLoading(false); }
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm({ ...form, [name]: type === "checkbox" ? checked : value });
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      await api.put("admin/settings/", form);
      setMsg({ type: "success", text: "Settings updated successfully." });
      fetchSettings();
    } catch {
      setMsg({ type: "error", text: "Update failed." });
    } finally { setSaving(false); }
  };

  const inputCls = { padding: "10px 14px", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "14px", width: "100%", boxSizing: "border-box", background: "#f8fafc" };
  const labelCls = { display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" };

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">⚙️ SACCO System Settings</h2>
          <p className="section-subtitle">Configure collateral rules, LTV ratios, and compliance settings</p>

          {msg && <div className={`alert alert-${msg.type}`} style={{ maxWidth: "600px" }}>{msg.text}</div>}
          {loading && <p style={{ color: "#94a3b8" }}>Loading settings...</p>}

          {!loading && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", maxWidth: "900px" }}>
              {/* Collateral rules */}
              <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)" }}>
                <h3 style={{ margin: "0 0 18px", fontSize: "16px", fontWeight: "700" }}>🔒 Collateral Rules</h3>
                <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div>
                    <label style={labelCls}>Release Hierarchy</label>
                    <select name="release_hierarchy" value={form.release_hierarchy} onChange={handleChange} style={inputCls}>
                      <option value="guarantor_first">Release Guarantor Pledges First</option>
                      <option value="proportional">Release Proportionally (All)</option>
                      <option value="borrower_first">Release Borrower's Own Lock First</option>
                    </select>
                    <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
                      How locked collateral is released as a loan is repaid.
                    </p>
                  </div>
                  <div>
                    <label style={labelCls}>Default LTV Ratio (%)</label>
                    <input type="number" name="default_ltv_ratio" value={form.default_ltv_ratio} onChange={handleChange} style={inputCls} min="0" max="100" step="1" />
                    <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
                      Max loan as % of asset's Forced Sale Value (typically 70–80%).
                    </p>
                  </div>
                  <div>
                    <label style={labelCls}>Min Savings Retention (%)</label>
                    <input type="number" name="min_savings_retention" value={form.min_savings_retention} onChange={handleChange} style={inputCls} min="0" max="100" step="1" />
                    <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
                      % of savings locked as collateral during an active loan (e.g., 33 = ⅓).
                    </p>
                  </div>
                  <button type="submit" disabled={saving} style={{ padding: "11px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", cursor: "pointer" }}>
                    {saving ? "Saving..." : "💾 Save Collateral Settings"}
                  </button>
                </form>
              </div>

              {/* SASRA compliance */}
              <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)" }}>
                <h3 style={{ margin: "0 0 18px", fontSize: "16px", fontWeight: "700" }}>📋 SASRA Compliance</h3>
                <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer" }}>
                    <input type="checkbox" name="sasra_enabled" checked={form.sasra_enabled} onChange={handleChange} style={{ width: "20px", height: "20px" }} />
                    <span style={{ fontSize: "14px", fontWeight: "600" }}>Enable SASRA Compliance Logging</span>
                  </label>
                  <div>
                    <label style={labelCls}>Report Interval (days)</label>
                    <input type="number" name="sasra_report_interval_days" value={form.sasra_report_interval_days} onChange={handleChange} style={inputCls} min="1" />
                    <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
                      How often to generate regulatory reports (e.g., 90 = quarterly).
                    </p>
                  </div>
                  <div style={{ background: "#f8fafc", borderRadius: "8px", padding: "14px", marginTop: "8px" }}>
                    <p style={{ margin: 0, fontSize: "13px", color: "#475569" }}>
                      📌 <strong>SASRA</strong> (Sacco Societies Regulatory Authority) requires deposit-taking SACCOs
                      to maintain regular financial reports. This setting enables automated report generation
                      and audit trails for regulatory compliance.
                    </p>
                  </div>
                  <button type="submit" disabled={saving} style={{ padding: "11px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", cursor: "pointer" }}>
                    {saving ? "Saving..." : "💾 Save Compliance Settings"}
                  </button>
                </form>
              </div>
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
