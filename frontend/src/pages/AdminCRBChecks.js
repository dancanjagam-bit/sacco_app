import React, { useState, useEffect } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";

const STATUS_COLORS = { clear: "#059669", flagged: "#d97706", error: "#e11d48", pending: "#64748b", not_configured: "#7c3aed" };
const TABS = ["all","flagged","clear","error","pending"];

export default function AdminCRBChecks() {
  const [records, setRecords] = useState([]);
  const [tab, setTab] = useState("all");
  const [selected, setSelected] = useState(null);
  const [overrideNotes, setOverrideNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const fetchRecords = async () => {
    try {
      const params = tab !== "all" ? `?status=${tab}` : "";
      const res = await api.get(`core/admin/crb-checks/${params}`);
      setRecords(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchDetail = async (id) => {
    try {
      const res = await api.get(`core/admin/crb-checks/${id}/`);
      setSelected(res.data);
      setOverrideNotes("");
      setMsg(null);
    } catch (e) { console.error(e); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchRecords(); }, [tab]);

  const submitOverride = async () => {
    if (!selected) return;
    setLoading(true);
    setMsg(null);
    try {
      await api.post(`core/admin/crb-checks/${selected.id}/override/`, { notes: overrideNotes });
      setMsg({ type: "success", text: "Loan approved successfully." });
      fetchRecords();
      setSelected(prev => ({ ...prev, loan_status: "approved" }));
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "Override failed." });
    } finally { setLoading(false); }
  };

  const StatusBadge = ({ status }) => (
    <span style={{ padding: "3px 10px", borderRadius: "12px", fontSize: "11px", fontWeight: "700",
      background: STATUS_COLORS[status] + "20", color: STATUS_COLORS[status], textTransform: "capitalize" }}>
      {status?.replace(/_/g, " ")}
    </span>
  );

  return (
    <Layout>
      {() => (
        <div>
          <div style={{ marginBottom: "24px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", fontWeight: "800" }}>🔍 CRB Credit Checks</h2>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "13px" }}>Review bureau reports and override flagged loan applications</p>
          </div>

          <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
            {TABS.map(t => (
              <button key={t} onClick={() => setTab(t)}
                style={{ padding: "7px 18px", borderRadius: "20px", border: "1.5px solid",
                  borderColor: tab === t ? "var(--primary)" : "var(--border)",
                  background: tab === t ? "var(--primary)" : "#fff",
                  color: tab === t ? "#fff" : "var(--muted)",
                  fontWeight: "600", fontSize: "13px", cursor: "pointer", textTransform: "capitalize" }}>
                {t.replace(/_/g, " ")}
              </button>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 360px" : "1fr", gap: "16px" }}>
            <div style={{ background: "#fff", borderRadius: "12px", border: "1px solid var(--border-light)", overflow: "hidden", boxShadow: "var(--shadow-sm)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#1e293b,#334155)" }}>
                    {["Member","Loan Amount","Provider","Score","Active Loans","Checked","Status",""].map(h => (
                      <th key={h} style={{ padding: "12px 16px", textAlign: "left", color: "rgba(255,255,255,.8)", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: ".6px" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr><td colSpan="8" style={{ padding: "40px", textAlign: "center", color: "#64748b" }}>No CRB records found</td></tr>
                  ) : records.map(r => (
                    <tr key={r.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "12px 16px" }}>
                        <p style={{ margin: 0, fontWeight: "600", fontSize: "13px" }}>{r.member_name || r.member_username}</p>
                        <p style={{ margin: 0, fontSize: "11px", color: "#64748b" }}>Loan #{r.loan_id}</p>
                      </td>
                      <td style={{ padding: "12px 16px", fontWeight: "700", fontSize: "13px" }}>KES {Number(r.loan_amount).toLocaleString()}</td>
                      <td style={{ padding: "12px 16px", fontSize: "12px", textTransform: "capitalize" }}>{r.provider || "—"}</td>
                      <td style={{ padding: "12px 16px", fontSize: "13px", fontWeight: "600" }}>{r.score ?? "—"}</td>
                      <td style={{ padding: "12px 16px", fontSize: "13px" }}>{r.active_loans_count}</td>
                      <td style={{ padding: "12px 16px", fontSize: "12px", color: "#64748b" }}>{new Date(r.checked_at).toLocaleDateString("en-KE")}</td>
                      <td style={{ padding: "12px 16px" }}><StatusBadge status={r.status} /></td>
                      <td style={{ padding: "12px 16px" }}>
                        <button onClick={() => fetchDetail(r.id)}
                          style={{ padding: "5px 14px", borderRadius: "8px", border: "1.5px solid var(--primary)", background: "#fff", color: "var(--primary)", fontWeight: "600", fontSize: "12px", cursor: "pointer" }}>
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selected && (
              <div style={{ background: "#fff", borderRadius: "12px", border: "1px solid var(--border-light)", padding: "20px", boxShadow: "var(--shadow-sm)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                  <h3 style={{ margin: 0, fontSize: "15px", fontWeight: "700" }}>CRB Report #{selected.id}</h3>
                  <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", fontSize: "18px", cursor: "pointer", color: "#64748b" }}>✕</button>
                </div>

                {msg && <div style={{ padding: "10px 14px", borderRadius: "8px", marginBottom: "12px", fontSize: "13px", background: msg.type === "success" ? "#f0fdf4" : "#fef2f2", color: msg.type === "success" ? "#16a34a" : "#dc2626" }}>{msg.text}</div>}

                {[["Member", selected.member_name], ["Loan Amount", `KES ${Number(selected.loan_amount).toLocaleString()}`],
                  ["Loan Status", selected.loan_status], ["Bureau", selected.provider],
                  ["Credit Score", selected.score ?? "—"], ["Active External Loans", selected.active_loans_count],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderBottom: "1px solid #f1f5f9", fontSize: "13px" }}>
                    <span style={{ color: "#64748b" }}>{k}</span>
                    <span style={{ fontWeight: "600" }}>{v}</span>
                  </div>
                ))}

                {selected.loan_status === "flagged" && !selected.override_by && (
                  <div style={{ marginTop: "16px" }}>
                    <p style={{ margin: "0 0 8px", fontSize: "12px", fontWeight: "700", color: "#64748b", textTransform: "uppercase" }}>Override — Approve Loan</p>
                    <textarea value={overrideNotes} onChange={e => setOverrideNotes(e.target.value)}
                      placeholder="Reason for override..." rows={3}
                      style={{ width: "100%", padding: "9px 12px", borderRadius: "8px", border: "1.5px solid #e2e8f0", fontSize: "13px", fontFamily: "inherit", resize: "vertical", marginBottom: "8px" }} />
                    <button onClick={submitOverride} disabled={loading}
                      style={{ width: "100%", padding: "10px", borderRadius: "8px", border: "none", background: "#059669", color: "#fff", fontWeight: "700", fontSize: "13px", cursor: "pointer" }}>
                      {loading ? "Processing..." : "✅ Approve Loan"}
                    </button>
                  </div>
                )}
                {selected.override_by && (
                  <div style={{ marginTop: "16px", padding: "12px", borderRadius: "8px", background: "#f0fdf4" }}>
                    <p style={{ margin: 0, fontSize: "12px", color: "#16a34a", fontWeight: "700" }}>✅ Overridden by {selected.override_by}</p>
                    {selected.override_notes && <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#065f46" }}>{selected.override_notes}</p>}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Layout>
  );
}
