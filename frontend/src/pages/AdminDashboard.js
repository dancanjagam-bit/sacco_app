import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Layout from "../components/Layout";
import MonthlyChart from "../components/MonthlyChart";
import LoanStatusChart from "../components/LoanStatusChart";
import "../styles/dashboard.css";

function KpiCard({ label, value, icon, color, iconBg, meta, link }) {
  const inner = (
    <div className="kpi-card" style={{ "--kpi-color": color, "--kpi-icon-bg": iconBg, cursor: link ? "pointer" : "default" }}>
      <p className="kpi-label">{label}</p>
      <h2 className="kpi-value">{value}</h2>
      {meta && <p className="kpi-meta" style={{ color: "var(--muted)" }}>{meta}</p>}
      <div className="kpi-icon">{icon}</div>
    </div>
  );
  return link ? <Link to={link} style={{ textDecoration: "none" }}>{inner}</Link> : inner;
}

export default function AdminDashboard() {
  const { user } = useAuth();
  const [stats,   setStats]   = useState(null);
  const [error,   setError]   = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { fetchDashboard(); }, []);

  const fetchDashboard = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await api.get("admin/dashboard/");
      setStats(res.data);
    } catch {
      setError("Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  };

  const h = new Date().getHours();
  const greet = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";

  return (
    <Layout>
      {() => (
        <div>
          {/* ── Welcome banner ── */}
          <div style={{
            background: "linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #2563eb 100%)",
            borderRadius: "16px", padding: "24px 32px", marginBottom: "24px",
            color: "#fff", display: "flex", justifyContent: "space-between", alignItems: "center",
            boxShadow: "0 8px 32px rgba(37,99,235,.25)", position: "relative", overflow: "hidden",
          }}>
            <div style={{ position: "absolute", top: "-40px", right: "60px", width: "180px", height: "180px", borderRadius: "50%", background: "rgba(255,255,255,.04)" }} />
            <div>
              <p style={{ margin: "0 0 2px", fontSize: "13px", color: "rgba(255,255,255,.6)" }}>{greet},</p>
              <h1 style={{ margin: "0 0 4px", fontSize: "24px", fontWeight: "800" }}>
                {user?.first_name || user?.username} 👋
              </h1>
              <p style={{ margin: 0, fontSize: "12px", color: "rgba(255,255,255,.5)" }}>
                SACCO Administration · {new Date().toLocaleDateString("en-KE", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              <button onClick={fetchDashboard} style={{ padding: "8px 18px", background: "rgba(255,255,255,.12)", color: "#fff", border: "1px solid rgba(255,255,255,.2)", borderRadius: "8px", cursor: "pointer", fontSize: "13px", fontWeight: "600", backdropFilter: "blur(8px)" }}>
                🔄 Refresh
              </button>
            </div>
          </div>

          {error && (
            <div className="alert alert-error" style={{ marginBottom: "20px" }}>
              ⚠️ {error}
              <button onClick={fetchDashboard} style={{ marginLeft: "12px", padding: "4px 12px", background: "none", border: "1px solid currentColor", borderRadius: "6px", cursor: "pointer", color: "inherit", fontSize: "12px" }}>
                Retry
              </button>
            </div>
          )}

          {loading && !stats && (
            <div style={{ display: "flex", justifyContent: "center", padding: "60px", color: "var(--muted)", gap: "12px", fontSize: "14px" }}>
              <span style={{ animation: "spin .6s linear infinite", display: "inline-block" }}>⟳</span>
              Loading dashboard...
            </div>
          )}

          {stats && (
            <>
              {/* ── KPI row 1: Members & Money ── */}
              <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
                <KpiCard label="Total Members"    value={stats.total_members}    icon="👥" color="#2563eb" iconBg="#eff6ff" meta="Active SACCO members" link="/admin/members" />
                <KpiCard label="Total Savings"    value={`KES ${Number(stats.total_savings).toLocaleString()}`}    icon="💰" color="#059669" iconBg="#d1fae5" meta="Net member deposits" />
                <KpiCard label="Active Loan Book" value={`KES ${Number(stats.active_loans).toLocaleString()}`}    icon="🏦" color="#7c3aed" iconBg="#ede9fe" meta="Outstanding balances" />
                <KpiCard label="Interest Earned"  value={`KES ${Number(stats.interest_earned).toLocaleString()}`} icon="📈" color="#d97706" iconBg="#fef3c7" meta="Total interest revenue" />
              </div>

              {/* ── KPI row 2: Loan pipeline ── */}
              <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", marginBottom: "24px" }}>
                <KpiCard label="Pending Approval"  value={stats.pending_loans}  icon="⏳" color="#d97706" iconBg="#fef3c7" meta="Awaiting decision" link="/admin/loans" />
                <KpiCard label="Approved Loans"    value={stats.approved_loans} icon="✅" color="#059669" iconBg="#d1fae5" meta="Currently active" link="/admin/loans" />
                <KpiCard label="Repaid Loans"      value={stats.repaid_loans}   icon="🎉" color="#2563eb" iconBg="#eff6ff" meta="Fully settled" />
                <KpiCard label="Rejected Loans"    value={stats.rejected_loans} icon="❌" color="#e11d48" iconBg="#ffe4e6" meta="Not approved" />
              </div>

              {/* ── Charts row 1 ── */}
              <div className="dashboard-row">
                <div className="chart-panel">
                  <MonthlyChart title="📈 Monthly Savings Trend" data={stats.monthly_savings} color="#059669" />
                </div>
                <div className="chart-panel">
                  <LoanStatusChart data={stats.loan_status} />
                </div>
              </div>

              {/* ── Charts row 2 ── */}
              <div className="dashboard-row">
                <div className="chart-panel">
                  <MonthlyChart title="💸 Monthly Disbursements" data={stats.monthly_loans} color="#7c3aed" />
                </div>
                <div className="chart-panel">
                  <MonthlyChart title="🔄 Monthly Repayments" data={stats.monthly_repayments} color="#2563eb" />
                </div>
              </div>

              {/* ── Bottom row: activity + savers ── */}
              <div className="dashboard-row">
                {/* Recent transactions */}
                <div className="chart-panel">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                    <p className="panel-title" style={{ margin: 0 }}>📋 Recent Activity</p>
                    <Link to="/admin/loans" style={{ fontSize: "12px", color: "var(--primary)", fontWeight: "600", textDecoration: "none" }}>View all →</Link>
                  </div>
                  <table className="table">
                    <thead>
                      <tr><th>Member</th><th>Type</th><th>Amount</th><th>Date</th></tr>
                    </thead>
                    <tbody>
                      {(stats.recent_transactions || []).length === 0 ? (
                        <tr><td colSpan="4" style={{ textAlign: "center", color: "var(--muted)", padding: "20px" }}>No transactions yet</td></tr>
                      ) : (stats.recent_transactions || []).map(t => (
                        <tr key={t.id}>
                          <td style={{ fontWeight: "600" }}>{t.member}</td>
                          <td>
                            <span className={`status status-${t.type === "deposit" ? "approved" : t.type === "repayment" ? "repaid" : "pending"}`}>
                              {t.type}
                            </span>
                          </td>
                          <td style={{ fontWeight: "700" }}>KES {Number(t.amount).toLocaleString()}</td>
                          <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                            {new Date(t.created_at).toLocaleDateString("en-KE")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Top savers */}
                <div className="chart-panel">
                  <p className="panel-title">🏆 Top Savers</p>
                  {(stats.top_savers || []).length === 0 ? (
                    <div className="empty-state" style={{ padding: "30px 0" }}>
                      <span className="empty-icon">💰</span>
                      <p>No savings on record yet.</p>
                    </div>
                  ) : (stats.top_savers || []).map((s, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "14px", padding: "12px 0", borderBottom: i < (stats.top_savers.length - 1) ? "1px solid var(--border-light)" : "none" }}>
                      <div style={{
                        width: "36px", height: "36px", borderRadius: "50%",
                        background: i === 0 ? "#fef3c7" : i === 1 ? "#f1f5f9" : i === 2 ? "#fef3c7" : "var(--primary-light)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "18px", fontWeight: "700", flexShrink: 0,
                      }}>
                        {i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `${i + 1}`}
                      </div>
                      <div style={{ flex: 1 }}>
                        <p style={{ margin: 0, fontWeight: "700", fontSize: "13px" }}>{s.username}</p>
                      </div>
                      <span style={{ fontWeight: "800", fontSize: "13px", color: "var(--emerald)" }}>
                        KES {Number(s.total).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* ── Quick links ── */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px", marginBottom: "20px" }}>
                {[
                  { to: "/admin/members",       icon: "👥", label: "Members",       color: "#2563eb", bg: "#eff6ff" },
                  { to: "/admin/loans",          icon: "🏦", label: "Loan Approvals",color: "#7c3aed", bg: "#ede9fe" },
                  { to: "/admin/exit-requests",  icon: "🚪", label: "Exit Requests", color: "#d97706", bg: "#fef3c7" },
                  { to: "/admin/audit",          icon: "🔍", label: "Audit Engine",  color: "#e11d48", bg: "#ffe4e6" },
                  { to: "/reports",              icon: "📊", label: "Reports",       color: "#059669", bg: "#d1fae5" },
                  { to: "/admin/settings",       icon: "⚙️", label: "Settings",     color: "#0891b2", bg: "#cffafe" },
                ].map(a => (
                  <Link key={a.to} to={a.to} style={{ display: "flex", alignItems: "center", gap: "10px", padding: "14px 16px", borderRadius: "10px", background: a.bg, textDecoration: "none", transition: "var(--transition)", border: "1px solid transparent" }}
                    onMouseOver={e => { e.currentTarget.style.borderColor = a.color; e.currentTarget.style.transform = "translateY(-2px)"; }}
                    onMouseOut={e => { e.currentTarget.style.borderColor = "transparent"; e.currentTarget.style.transform = "translateY(0)"; }}
                  >
                    <span style={{ fontSize: "20px" }}>{a.icon}</span>
                    <span style={{ fontWeight: "700", fontSize: "12px", color: a.color }}>{a.label}</span>
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </Layout>
  );
}
