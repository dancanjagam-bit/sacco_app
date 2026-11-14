import React, { useState, useEffect } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import api from "../api/axios";
import "../styles/dashboard.css";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import MemberReportsPage from "./MemberReportsPage";
import PageHeading from "../components/ui/PageHeading";

/* ── Admin Reports ───────────────────────────────────────────────────────── */
function AdminReports() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [divYear, setDivYear] = useState(new Date().getFullYear());
  const [divRate, setDivRate] = useState("8");
  const [paying,  setPaying]  = useState(false);
  const [divMsg,  setDivMsg]  = useState(null);

  useEffect(() => {
    api.get("admin/reports/").then(r => { setData(r.data); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const payDividends = async () => {
    if (!window.confirm(`Pay ${divRate}% dividend for ${divYear} to all members?`)) return;
    setPaying(true);
    try {
      const res = await api.post("admin/dividends/pay/", { year: divYear, rate: divRate });
      setDivMsg({ type: "success", text: res.data.message + ` Total paid: KES ${Number(res.data.total_paid).toLocaleString()}` });
    } catch (err) {
      setDivMsg({ type: "error", text: err.response?.data?.error || "Failed." });
    } finally { setPaying(false); }
  };

  if (loading) return <p style={{ color: "#94a3b8" }}>Loading reports...</p>;
  if (!data)   return <p style={{ color: "#dc2626" }}>Failed to load reports.</p>;

  return (
    <>
      {/* Member stats */}
      <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>👥 Membership</h3>
      <div className="summary-grid" style={{ marginBottom: "24px" }}>
        {[
          ["Total Members",    data.members.total,     "var(--primary)"],
          ["Active Members",   data.members.active,    "var(--success)"],
          ["Suspended",        data.members.suspended, "var(--danger)"],
        ].map(([h, v, c]) => (
          <div key={h} className="summary-card" style={{ borderTopColor: c }}>
            <h4>{h}</h4><h2>{v}</h2>
          </div>
        ))}
      </div>

      {/* Savings stats */}
      <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>💰 Savings</h3>
      <div className="summary-grid" style={{ marginBottom: "24px" }}>
        {[
          ["Total Deposited",  `KES ${Number(data.savings.total_deposited).toLocaleString()}`,  "var(--success)"],
          ["Total Withdrawn",  `KES ${Number(data.savings.total_withdrawn).toLocaleString()}`,  "var(--warning)"],
          ["Net Balance",      `KES ${Number(data.savings.net_balance).toLocaleString()}`,      "var(--primary)"],
        ].map(([h, v, c]) => (
          <div key={h} className="summary-card" style={{ borderTopColor: c }}>
            <h4>{h}</h4><h2>{v}</h2>
          </div>
        ))}
      </div>

      {/* Loan stats */}
      <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>🏦 Loans</h3>
      <div className="summary-grid" style={{ marginBottom: "24px" }}>
        {[
          ["Total Disbursed",     `KES ${Number(data.loans.total_disbursed).toLocaleString()}`,     "var(--primary)"],
          ["Outstanding Balance", `KES ${Number(data.loans.outstanding_balance).toLocaleString()}`, "var(--warning)"],
          ["Total Collected",     `KES ${Number(data.loans.total_collected).toLocaleString()}`,     "var(--success)"],
          ["Pending Approval",    data.loans.pending,   "var(--warning)"],
          ["Active Loans",        data.loans.approved,  "var(--primary)"],
          ["Fully Repaid",        data.loans.repaid,    "var(--success)"],
        ].map(([h, v, c]) => (
          <div key={h} className="summary-card" style={{ borderTopColor: c }}>
            <h4>{h}</h4><h2>{v}</h2>
          </div>
        ))}
      </div>

      {/* Monthly chart */}
      {data.monthly_savings_trend.length > 0 && (
        <>
          <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>📈 Monthly Savings Trend ({new Date().getFullYear()})</h3>
          <div style={{ background: "#fff", borderRadius: "12px", padding: "20px", boxShadow: "var(--shadow)", marginBottom: "24px" }}>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={data.monthly_savings_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={v => [`KES ${Number(v).toLocaleString()}`, "Savings"]} />
                <Bar dataKey="total" fill="#2563eb" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {/* Top savers */}
      <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>🏆 Top Savers</h3>
      <table className="table" style={{ marginBottom: "24px" }}>
        <thead><tr><th>Rank</th><th>Member</th><th>Total Savings</th></tr></thead>
        <tbody>
          {data.top_savers.map((s, i) => (
            <tr key={s.username}>
              <td>{i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `#${i+1}`}</td>
              <td><strong>{s.name}</strong> <span style={{ color: "#94a3b8", fontSize: "12px" }}>({s.username})</span></td>
              <td style={{ fontWeight: "700", color: "#15803d" }}>KES {Number(s.total).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Dividend payout (superadmin) */}
      <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>💹 Pay Annual Dividend</h3>
      <div style={{ background: "#fff", borderRadius: "12px", padding: "20px", boxShadow: "var(--shadow)", maxWidth: "480px" }}>
        {divMsg && <div className={`alert alert-${divMsg.type}`} style={{ marginBottom: "12px" }}>{divMsg.text}</div>}
        <div style={{ display: "flex", gap: "12px", marginBottom: "12px", flexWrap: "wrap" }}>
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", marginBottom: "4px" }}>Year</label>
            <input type="number" value={divYear} onChange={e => setDivYear(e.target.value)} className="amount-input" style={{ width: "120px" }} />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", marginBottom: "4px" }}>Rate (%)</label>
            <input type="number" value={divRate} onChange={e => setDivRate(e.target.value)} className="amount-input" style={{ width: "120px" }} step="0.5" min="0" max="100" />
          </div>
        </div>
        <button onClick={payDividends} disabled={paying} style={{ padding: "10px 20px", background: "#15803d", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", cursor: "pointer" }}>
          {paying ? "Processing..." : "💹 Pay Dividends to All Members"}
        </button>
      </div>
    </>
  );
}

/* ── Main page ──────────────────────────────────────────────────────────── */
export default function Reports() {
  const { user, isAdmin } = useAuth();
  const [tab, setTab] = useState("member");

  return (
    <Layout>
      {() => (
        <>
          {/* Admin tab switcher */}
          {isAdmin && (
            <div style={{ display: "flex", gap: "4px", marginBottom: "20px", background: "#f1f5f9", borderRadius: "10px", padding: "4px", width: "fit-content" }}>
              {[["member","My Account"],["admin","SACCO Overview"]].map(([k,l]) => (
                <button key={k} onClick={() => setTab(k)} style={{
                  padding: "8px 20px", border: "none", borderRadius: "8px", fontSize: "13px", fontWeight: "600", cursor: "pointer",
                  background: tab === k ? "#fff" : "transparent",
                  color:      tab === k ? "#2563eb" : "#64748b",
                  boxShadow:  tab === k ? "var(--shadow-sm)" : "none",
                }}>{l}</button>
              ))}
            </div>
          )}

          {tab === "member" ? <MemberReportsPage user={user} /> : <>
            <PageHeading eyebrow="Staff reporting" title="SACCO reports" description="Financial summaries for authorized staff." />
            <AdminReports />
          </>}
        </>
      )}
    </Layout>
  );
}
