import React from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import "../styles/dashboard.css";

// Greeting by time of day
function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function KpiCard({ label, value, icon, color, iconBg, meta, trend }) {
  return (
    <div className="kpi-card" style={{ "--kpi-color": color, "--kpi-icon-bg": iconBg }}>
      <p className="kpi-label">{label}</p>
      <h2 className="kpi-value">{value}</h2>
      {meta && <p className="kpi-meta">{meta}</p>}
      {trend !== undefined && (
        <p className={`kpi-meta ${trend >= 0 ? "kpi-trend-up" : "kpi-trend-down"}`}>
          {trend >= 0 ? "▲" : "▼"} {Math.abs(trend)}% this month
        </p>
      )}
      <div className="kpi-icon">{icon}</div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();

  const savings      = Number(user?.total_savings  || 0);
  const totalLoans   = user?.total_loans    || 0;
  const pendingLoans = user?.pending_loans  || 0;
  const approved     = user?.approved_loans || 0;

  const loans        = user?.loans        || [];
  const transactions = user?.transactions || [];

  const activeLoan = loans.find(l => l.status === "approved" && Number(l.balance) > 0);
  const recentTxns = transactions.slice(0, 5);

  return (
    <Layout>
      {() => (
        <div>
          {/* ── Welcome banner ── */}
          <div style={{
            background: "linear-gradient(135deg, #0b1437 0%, #1e1b4b 45%, #3730a3 80%, #4f46e5 100%)",
            borderRadius: "20px",
            padding: "28px 32px",
            marginBottom: "24px",
            color: "#fff",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            boxShadow: "0 8px 40px rgba(79,70,229,.3)",
            overflow: "hidden",
            position: "relative",
          }}>
            {/* Background decoration */}
            <div style={{ position: "absolute", top: "-50px", right: "-50px", width: "220px", height: "220px", borderRadius: "50%", background: "rgba(129,140,248,.08)" }} />
            <div style={{ position: "absolute", bottom: "-70px", right: "130px", width: "180px", height: "180px", borderRadius: "50%", background: "rgba(52,211,153,.06)" }} />
            <div style={{ position: "absolute", top: "50%", left: "40%", width: "1px", height: "80%", background: "rgba(255,255,255,.04)", transform: "translateY(-50%) rotate(30deg)" }} />

            <div style={{ position: "relative" }}>
              <p style={{ margin: "0 0 4px", fontSize: "14px", color: "rgba(255,255,255,.65)", fontWeight: "500" }}>
                {greeting()},
              </p>
              <h1 style={{ margin: "0 0 6px", fontSize: "28px", fontWeight: "800", letterSpacing: "-.3px" }}>
                {user?.first_name || user?.username} 👋
              </h1>
              <p style={{ margin: 0, fontSize: "13px", color: "rgba(255,255,255,.55)" }}>
                Member {user?.member_number ? `#${user.member_number}` : ""} ·{" "}
                {new Date().toLocaleDateString("en-KE", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
              </p>
            </div>

            <div style={{ textAlign: "right", position: "relative" }}>
              <p style={{ margin: "0 0 4px", fontSize: "12px", color: "rgba(255,255,255,.5)", textTransform: "uppercase", letterSpacing: ".8px" }}>
                BOSA Balance
              </p>
              <h2 style={{ margin: 0, fontSize: "32px", fontWeight: "900", letterSpacing: "-.5px" }}>
                KES {savings.toLocaleString()}
              </h2>
            </div>
          </div>

          {/* ── KPI row ── */}
          <div className="kpi-grid">
            <KpiCard
              label="Total Savings"
              value={`KES ${savings.toLocaleString()}`}
              icon="💰"
              color="#059669"
              iconBg="#d1fae5"
              meta="All-time savings balance"
            />
            <KpiCard
              label="Total Loans"
              value={totalLoans}
              icon="🏦"
              color="#2563eb"
              iconBg="#eff6ff"
              meta={`${approved} approved`}
            />
            <KpiCard
              label="Pending Applications"
              value={pendingLoans}
              icon="⏳"
              color="#d97706"
              iconBg="#fef3c7"
              meta={pendingLoans > 0 ? "Awaiting admin review" : "No pending loans"}
            />
            <KpiCard
              label="Active Loan Balance"
              value={activeLoan ? `KES ${Number(activeLoan.balance).toLocaleString()}` : "—"}
              icon="📊"
              color="#7c3aed"
              iconBg="#ede9fe"
              meta={activeLoan ? `${activeLoan.repayment_months} months · ${activeLoan.interest}%` : "No active loan"}
            />
          </div>

          <div className="dashboard-row" style={{ marginBottom: "20px" }}>
            {/* Active loan card */}
            <div className="chart-panel">
              <p className="panel-title">🏦 Active Loan Status</p>
              {!activeLoan ? (
                <div className="empty-state" style={{ padding: "30px 0" }}>
                  <span className="empty-icon">✅</span>
                  <h3>No active loan</h3>
                  <p>You currently have no outstanding loan balance.</p>
                  <Link to="/loans" style={{ display: "inline-block", marginTop: "12px", padding: "8px 20px", background: "var(--primary)", color: "#fff", borderRadius: "8px", fontSize: "13px", fontWeight: "600", textDecoration: "none" }}>
                    Apply for a Loan
                  </Link>
                </div>
              ) : (
                <div>
                  {[
                    ["Principal",      `KES ${Number(activeLoan.amount).toLocaleString()}`],
                    ["Interest Rate",  `${activeLoan.interest}%`],
                    ["Period",         `${activeLoan.repayment_months} months`],
                    ["Outstanding",    `KES ${Number(activeLoan.balance).toLocaleString()}`],
                    ["Monthly Est.",   `KES ${Math.round(Number(activeLoan.amount) * (1 + Number(activeLoan.interest) / 100) / activeLoan.repayment_months).toLocaleString()}`],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border-light)", fontSize: "14px" }}>
                      <span style={{ color: "var(--muted)", fontWeight: "500" }}>{k}</span>
                      <span style={{ fontWeight: "700", color: "var(--text)" }}>{v}</span>
                    </div>
                  ))}
                  <Link to="/reports" style={{ display: "inline-block", marginTop: "14px", padding: "8px 18px", background: "var(--primary-light)", color: "var(--primary)", borderRadius: "8px", fontSize: "13px", fontWeight: "700", textDecoration: "none" }}>
                    View Repayment Schedule →
                  </Link>
                </div>
              )}
            </div>

            {/* Quick actions */}
            <div className="chart-panel">
              <p className="panel-title">⚡ Quick Actions</p>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {[
                  { to: "/savings",      icon: "💰", label: "Deposit Savings",    sub: "Add to your BOSA or FOSA account",     color: "#059669", bg: "#d1fae5" },
                  { to: "/loans",        icon: "🏦", label: "Apply for a Loan",   sub: "Based on your savings history",         color: "#2563eb", bg: "#eff6ff" },
                  { to: "/transactions", icon: "💳", label: "View Transactions",  sub: "Full history of all activity",          color: "#7c3aed", bg: "#ede9fe" },
                  { to: "/reports",      icon: "📄", label: "Download Statement", sub: "Export Excel or PDF",                   color: "#d97706", bg: "#fef3c7" },
                ].map(a => (
                  <Link key={a.to} to={a.to} style={{ display: "flex", alignItems: "center", gap: "14px", padding: "12px 14px", borderRadius: "10px", background: a.bg, textDecoration: "none", transition: "var(--transition)" }}
                    onMouseOver={e => e.currentTarget.style.transform = "translateX(4px)"}
                    onMouseOut={e => e.currentTarget.style.transform = "translateX(0)"}
                  >
                    <span style={{ fontSize: "22px" }}>{a.icon}</span>
                    <div>
                      <p style={{ margin: 0, fontWeight: "700", fontSize: "13px", color: a.color }}>{a.label}</p>
                      <p style={{ margin: 0, fontSize: "11px", color: "var(--muted)" }}>{a.sub}</p>
                    </div>
                    <span style={{ marginLeft: "auto", color: a.color, fontSize: "16px" }}>→</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          {/* Recent transactions */}
          {recentTxns.length > 0 && (
            <div className="chart-panel" style={{ marginBottom: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                <p className="panel-title" style={{ margin: 0 }}>📋 Recent Activity</p>
                <Link to="/transactions" style={{ fontSize: "13px", color: "var(--primary)", fontWeight: "600", textDecoration: "none" }}>View all →</Link>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Note</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {recentTxns.map(t => (
                    <tr key={t.id}>
                      <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                        {new Date(t.created_at).toLocaleDateString("en-KE")}
                      </td>
                      <td>
                        <span className={`status status-${t.type === "deposit" ? "approved" : t.type === "repayment" ? "repaid" : t.type === "withdrawal" ? "pending" : "info"}`}>
                          {t.type}
                        </span>
                      </td>
                      <td style={{ color: "var(--muted)", fontSize: "12px" }}>{t.note || "—"}</td>
                      <td style={{ fontWeight: "700" }}>KES {Number(t.amount).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Layout>
  );
}
