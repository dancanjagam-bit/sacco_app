import React, { useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

const ASSET_TYPES = [
  ["title_deed",    "🏠 Title Deed (Land)"],
  ["logbook",       "🚗 Motor Vehicle Logbook"],
  ["equipment",     "🔧 Equipment / Machinery"],
  ["shares",        "📈 Share Certificate"],
  ["fixed_deposit", "💰 Fixed Deposit"],
  ["other",         "📋 Other Tangible Asset"],
];

const STATUS_COLORS = {
  pending_valuation:        { bg: "#fef3c7", color: "#b45309", label: "Pending Valuation" },
  valued:                   { bg: "#dbeafe", color: "#1e40af", label: "Valued — Awaiting Charge" },
  legal_charge_registered:  { bg: "#dcfce7", color: "#15803d", label: "Legal Charge Registered" },
  active:                   { bg: "#e0f2fe", color: "#0369a1", label: "Active (Loan Disbursed)" },
  discharged:               { bg: "#f1f5f9", color: "#475569", label: "Discharged" },
  rejected:                 { bg: "#fee2e2", color: "#b91c1c", label: "Rejected" },
};

export default function AdminAssets() {
  const [assets,   setAssets]   = useState([]);
  const [loading,  setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [msg,      setMsg]      = useState(null);
  const [editAsset, setEditAsset] = useState(null);

  const [form, setForm] = useState({
    user_id: "", asset_type: "title_deed", description: "",
    forced_sale_value: "", ltv_ratio: "80", status: "pending_valuation",
    registration_ref: "", valuation_date: "", valuer_name: "",
  });

  useEffect(() => { fetchAssets(); }, []);

  const fetchAssets = async () => {
    setLoading(true);
    try {
      const res = await api.get("admin/assets/");
      setAssets(res.data);
    } catch { setMsg({ type: "error", text: "Failed to load assets." }); }
    finally { setLoading(false); }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMsg(null);
    try {
      if (editAsset) {
        await api.put(`admin/assets/${editAsset.id}/`, form);
        setMsg({ type: "success", text: "Asset updated." });
      } else {
        await api.post("admin/assets/", form);
        setMsg({ type: "success", text: "Asset registered." });
      }
      setShowForm(false);
      setEditAsset(null);
      setForm({ user_id: "", asset_type: "title_deed", description: "", forced_sale_value: "", ltv_ratio: "80", status: "pending_valuation", registration_ref: "", valuation_date: "", valuer_name: "" });
      fetchAssets();
    } catch (err) {
      const data = err.response?.data;
      setMsg({ type: "error", text: data?.error || "Failed." });
    }
  };

  const startEdit = (asset) => {
    setEditAsset(asset);
    setForm({
      user_id: asset.user_id, asset_type: asset.asset_type, description: asset.description,
      forced_sale_value: String(asset.forced_sale_value), ltv_ratio: String(asset.ltv_ratio),
      status: asset.status, registration_ref: asset.registration_ref,
      valuation_date: asset.valuation_date || "", valuer_name: asset.valuer_name,
    });
    setShowForm(true);
  };

  const inputCls = { padding: "10px 14px", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "14px", width: "100%", boxSizing: "border-box", background: "#f8fafc" };
  const labelCls = { display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" };

  return (
    <Layout>
      {() => (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title">🏠 Asset Collateral Registry</h2>
              <p className="section-subtitle">Tangible assets pledged as loan security</p>
            </div>
            <button onClick={() => { setShowForm(!showForm); setEditAsset(null); setMsg(null); }} style={{ padding: "10px 20px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
              {showForm ? "✕ Cancel" : "+ Register Asset"}
            </button>
          </div>

          {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

          {/* Create/Edit form */}
          {showForm && (
            <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)", marginBottom: "24px" }}>
              <h3 style={{ margin: "0 0 16px", fontSize: "16px", fontWeight: "700" }}>
                {editAsset ? "Edit Asset" : "Register New Tangible Asset"}
              </h3>
              <form onSubmit={handleSubmit} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div>
                  <label style={labelCls}>Member User ID *</label>
                  <input type="number" name="user_id" value={form.user_id} onChange={e => setForm({...form, user_id: e.target.value})} style={inputCls} placeholder="Enter user ID" required />
                </div>
                <div>
                  <label style={labelCls}>Asset Type *</label>
                  <select name="asset_type" value={form.asset_type} onChange={e => setForm({...form, asset_type: e.target.value})} style={inputCls}>
                    {ASSET_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div style={{ gridColumn: "1/-1" }}>
                  <label style={labelCls}>Description</label>
                  <input type="text" name="description" value={form.description} onChange={e => setForm({...form, description: e.target.value})} style={inputCls} placeholder="e.g. Plot No. 1234, Kasarani, Nairobi" />
                </div>
                <div>
                  <label style={labelCls}>Forced Sale Value (KES) *</label>
                  <input type="number" name="forced_sale_value" value={form.forced_sale_value} onChange={e => setForm({...form, forced_sale_value: e.target.value})} style={inputCls} placeholder="e.g. 5000000" required />
                </div>
                <div>
                  <label style={labelCls}>LTV Ratio (%) *</label>
                  <input type="number" name="ltv_ratio" value={form.ltv_ratio} onChange={e => setForm({...form, ltv_ratio: e.target.value})} style={inputCls} min="0" max="100" step="1" required />
                </div>
                <div>
                  <label style={labelCls}>Status</label>
                  <select name="status" value={form.status} onChange={e => setForm({...form, status: e.target.value})} style={inputCls}>
                    {Object.entries(STATUS_COLORS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelCls}>Registration Reference</label>
                  <input type="text" name="registration_ref" value={form.registration_ref} onChange={e => setForm({...form, registration_ref: e.target.value})} style={inputCls} placeholder="e.g. LR No. 1234/567" />
                </div>
                <div>
                  <label style={labelCls}>Valuation Date</label>
                  <input type="date" name="valuation_date" value={form.valuation_date} onChange={e => setForm({...form, valuation_date: e.target.value})} style={inputCls} />
                </div>
                <div>
                  <label style={labelCls}>Valuer Name</label>
                  <input type="text" name="valuer_name" value={form.valuer_name} onChange={e => setForm({...form, valuer_name: e.target.value})} style={inputCls} placeholder="e.g. Tysons Valuers Ltd" />
                </div>
                <div style={{ gridColumn: "1/-1" }}>
                  <button type="submit" style={{ padding: "12px 28px", background: "var(--success)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
                    {editAsset ? "✅ Update Asset" : "✅ Register Asset"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Assets table */}
          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading assets...</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th><th>Member</th><th>Type</th><th>Description</th>
                    <th>Forced Sale Value</th><th>LTV</th><th>Max Loan Cap</th>
                    <th>Status</th><th>Reg. Ref</th><th>Loan</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.length === 0 ? (
                    <tr><td colSpan="11" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>No assets registered yet.</td></tr>
                  ) : assets.map(a => {
                    const sc = STATUS_COLORS[a.status] || {};
                    return (
                      <tr key={a.id}>
                        <td>#{a.id}</td>
                        <td style={{ fontWeight: "600" }}>{a.user}</td>
                        <td>{a.asset_type_label}</td>
                        <td style={{ fontSize: "12px", color: "#64748b", maxWidth: "160px" }}>{a.description || "—"}</td>
                        <td>KES {Number(a.forced_sale_value).toLocaleString()}</td>
                        <td>{a.ltv_ratio}%</td>
                        <td style={{ fontWeight: "700", color: "#16a34a" }}>KES {Number(a.max_loan_cap).toLocaleString()}</td>
                        <td><span style={{ padding: "3px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: "700", background: sc.bg, color: sc.color }}>{sc.label}</span></td>
                        <td style={{ fontSize: "12px", fontFamily: "monospace", color: "#64748b" }}>{a.registration_ref || "—"}</td>
                        <td>{a.loan_id ? `#${a.loan_id}` : "—"}</td>
                        <td><button onClick={() => startEdit(a)} style={{ padding: "5px 12px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}>Edit</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
