import React, { useState, useEffect } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import api from "../api/axios";
import "../styles/dashboard.css";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

/* ── helpers ── */
const download = (blob, filename) => {
  const url  = window.URL.createObjectURL(new Blob([blob]));
  const link = document.createElement("a");
  link.href  = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

/* ── Member Reports ─────────────────────────────────────────────────────── */
function MemberReports({ user }) {
  const loans        = user?.loans        || [];
  const transactions = user?.transactions || [];

  const totalDeposits  = transactions.filter(t => t.type === "deposit").reduce((s, t) => s + Number(t.amount), 0);
  const totalLoansDis  = transactions.filter(t => t.type === "loan").reduce((s, t) => s + Number(t.amount), 0);
  const totalRepaid    = transactions.filter(t => t.type === "repayment").reduce((s, t) => s + Number(t.amount), 0);
  const totalWithdrawn = transactions.filter(t => t.type === "withdrawal").reduce((s, t) => s + Number(t.amount), 0);

  const [dividends,  setDividends]  = useState([]);
  const [exportingX, setExportingX] = useState(false);
  const [exportingP, setExportingP] = useState(false);
  const [scheduleData, setScheduleData] = useState(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);

  useEffect(() => {
    api.get("dividends/").then(r => setDividends(r.data)).catch(() => {});
  }, []);

  const activeLoan = loans.find(l => l.status === "approved" && Number(l.balance) > 0);

  const loadSchedule = async (loanId) => {
    setScheduleLoading(true);
    try {
      const res = await api.get(`loan/${loanId}/schedule/`);
      setScheduleData(res.data);
    } catch { setScheduleData(null); }
    finally { setScheduleLoading(false); }
  };

  const exportExcel = async () => {
    setExportingX(true);
    try {
      const r = await api.get("transactions/excel/", { responseType: "blob" });
      download(r.data, "sacco_statement.xlsx");
    } catch { alert("Export failed."); }
    finally { setExportingX(false); }
  };

  const exportPDF = async () => {
    setExportingP(true);
    try {
      const r = await api.get("statement/pdf/", { responseType: "blob" });
      download(r.data, "sacco_statement.pdf");
    } catch { alert("PDF export failed."); }
    finally { setExportingP(false); }
  };

  return (
    <>
      <div className="summary-grid">
        {[
          ["💰 Current Savings", `KES ${Number(user?.total_savings || 0).toLocaleString()}`, "var(--success)"],
          ["📥 Total Deposited", `KES ${totalDeposits.toLocaleString()}`, "var(--primary)"],
          ["📤 Total Withdrawn", `KES ${totalWithdrawn.toLocaleString()}`, "var(--warning)"],
          ["🏦 Loans Received",  `KES ${totalLoansDis.toLocaleString()}`,  "var(--purple)"],
          ["🔄 Total Repaid",    `KES ${totalRepaid.toLocaleString()}`,    "var(--info)"],
        ].map(([h, v, c]) => (
          <div key={h} className="summary-card" style={{ borderTopColor: c }}>
            <h4>{h}</h4><h2>{v}</h2>
          </div>
        ))}
      </div>

      {/* Active loan */}
      {activeLoan && (
        <>
          <h3 style={{ margin: "24px 0 12px", fontSize: "16px", fontWeight: "700" }}>Active Loan</h3>
          <div style={{ background: "#fff", borderRadius: "12px", padding: "20px", boxShadow: "var(--shadow)", marginBottom: "16px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: "12px", marginBottom: "16px" }}>
              {[
                ["Principal",      `KES ${Number(activeLoan.amount).toLocaleString()}`],
                ["Interest",       `${activeLoan.interest}%`],
                ["Period",         `${activeLoan.repayment_months} months`],
                ["Outstanding",    `KES ${Number(activeLoan.balance).toLocaleString()}`],
                ["Monthly",        `KES ${((Number(activeLoan.amount) * (1 + Number(activeLoan.interest)/100)) / activeLoan.repayment_months).toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
              ].map(([k, v]) => (
                <div key={k} style={{ background: "#f8fafc", borderRadius: "8px", padding: "12px" }}>
                  <div style={{ fontSize: "11px", fontWeight: "600", color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".4px" }}>{k}</div>
                  <div style={{ fontSize: "16px", fontWeight: "700", color: "#1e293b", marginTop: "4px" }}>{v}</div>
                </div>
              ))}
            </div>
            <button onClick={() => loadSchedule(activeLoan.id)} style={{ padding: "9px 18px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "600", fontSize: "13px", cursor: "pointer" }}>
              📅 View Repayment Schedule
            </button>
          </div>

          {scheduleLoading && <p style={{ color: "#94a3b8" }}>Loading schedule...</p>}
          {scheduleData && (
            <div style={{ background: "#fff", borderRadius: "12px", boxShadow: "var(--shadow)", marginBottom: "24px", overflowX: "auto" }}>
              <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", fontWeight: "700" }}>Repayment Schedule — Loan #{scheduleData.loan_id}</div>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th><th>Due Date</th><th>Expected</th><th>Paid</th><th>Paid On</th><th>Balance</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {scheduleData.schedule.map(row => (
                    <tr key={row.installment}>
                      <td>{row.installment}</td>
                      <td>{new Date(row.due_date).toLocaleDateString("en-KE")}</td>
                      <td>KES {Number(row.expected).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td>KES {Number(row.paid).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td>{row.paid_on ? new Date(row.paid_on).toLocaleDateString("en-KE") : "—"}</td>
                      <td>KES {Number(row.balance_after).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                      <td><span className={`status status-${row.status === "paid" ? "approved" : row.status === "overdue" ? "rejected" : row.status === "partial" ? "pending" : "info"}`}>{row.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Loans history */}
      {loans.length > 0 && (
        <>
          <h3 style={{ margin: "24px 0 12px", fontSize: "16px", fontWeight: "700" }}>Loan History</h3>
          <table className="table" style={{ marginBottom: "24px" }}>
            <thead><tr><th>ID</th><th>Amount</th><th>Interest</th><th>Period</th><th>Purpose</th><th>Balance</th><th>Status</th></tr></thead>
            <tbody>
              {loans.map(l => (
                <tr key={l.id}>
                  <td>#{l.id}</td>
                  <td>KES {Number(l.amount).toLocaleString()}</td>
                  <td>{l.interest}%</td>
                  <td>{l.repayment_months} mo.</td>
                  <td style={{ textTransform: "capitalize" }}>{l.purpose}</td>
                  <td>KES {Number(l.balance).toLocaleString()}</td>
                  <td><span className={`status status-${l.status}`}>{l.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {/* Dividends */}
      {dividends.length > 0 && (
        <>
          <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>💹 Dividend History</h3>
          <table className="table" style={{ marginBottom: "24px" }}>
            <thead><tr><th>Year</th><th>Rate</th><th>Balance at Year End</th><th>Dividend Earned</th></tr></thead>
            <tbody>
              {dividends.map(d => (
                <tr key={d.year}>
                  <td><strong>{d.year}</strong></td>
                  <td>{d.rate}%</td>
                  <td>KES {Number(d.balance).toLocaleString()}</td>
                  <td style={{ color: "#15803d", fontWeight: "700" }}>+ KES {Number(d.dividend).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {/* Downloads */}
      <h3 style={{ margin: "0 0 12px", fontSize: "16px", fontWeight: "700" }}>📥 Download Statements</h3>
      <div className="action-buttons">
        <button onClick={exportExcel} disabled={exportingX}>
          {exportingX ? "Generating..." : "📊 Excel Statement"}
        </button>
        <button onClick={exportPDF} disabled={exportingP} style={{ background: "#dc2626" }}>
          {exportingP ? "Generating..." : "📄 PDF Statement"}
        </button>
      </div>
    </>
  );
}

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
          <h2 className="section-title">📋 Reports & Statements</h2>
          <p className="section-subtitle">Financial summary and downloadable statements</p>

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

          {tab === "member" ? <MemberReports user={user} /> : <AdminReports />}
        </>
      )}
    </Layout>
  );
}
