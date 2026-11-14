import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Layout from "../components/Layout";
import MonthlyChart from "../components/MonthlyChart";
import MetricCard from "../components/ui/MetricCard";
import StatusBadge from "../components/ui/StatusBadge";
import Icon from "../components/ui/Icon";
import Button from "../components/ui/Button";
import PageHeading from "../components/ui/PageHeading";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import DataTable from "../components/ui/DataTable";
import LoadingState from "../components/ui/LoadingState";
import "../styles/premiumDashboard.css";
import "../styles/staffDashboard.css";

function formatKES(value) {
  if (value == null || (typeof value === "string" && !value.trim())) return "Unavailable";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "Unavailable";
  return `KES ${amount.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatCount(value) {
  if (value == null || !Number.isFinite(Number(value))) return "Unavailable";
  return Number(value).toLocaleString("en-KE");
}

function formatDate(value) {
  const date = value ? new Date(value) : null;
  return date && Number.isFinite(date.getTime())
    ? date.toLocaleString("en-KE", { timeZone: "Africa/Nairobi", dateStyle: "medium", timeStyle: "short" })
    : "Date unavailable";
}

function hasCount(value) {
  return value !== null && value !== undefined && value !== "" &&
    Number.isFinite(Number(value)) && Number(value) >= 0;
}

export default function AdminDashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState("6");
  const [updatedAt, setUpdatedAt] = useState(null);

  const fetchDashboard = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const response = await api.get("admin/dashboard/");
      if (!response.data || typeof response.data !== "object" || Array.isArray(response.data)) {
        throw new Error("Unexpected dashboard response");
      }
      setStats(response.data);
      setUpdatedAt(new Date());
    } catch {
      setError("Dashboard data could not be refreshed. Try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const chairman = user?.staff_role === "chairman";
  const hasLoanReviewPermission = user?.permissions?.includes("loans.appraise");
  const monthlySavingsProvided = Array.isArray(stats?.monthly_savings);
  const validMonthlySavings = monthlySavingsProvided
    ? stats.monthly_savings.filter((entry) => entry && typeof entry.month === "string" && entry.month.trim() && entry.total != null && Number.isFinite(Number(entry.total)))
    : null;
  const savingsByMonth = validMonthlySavings
    ? validMonthlySavings.slice(-Number(period))
    : null;
  const recentTransactions = Array.isArray(stats?.recent_transactions)
    ? stats.recent_transactions
    : null;
  const pendingLoans = formatCount(stats?.pending_loans);
  const pendingLoansKnown = hasCount(stats?.pending_loans);
  const asOf = updatedAt
    ? updatedAt.toLocaleString("en-KE", { timeZone: "Africa/Nairobi", dateStyle: "medium", timeStyle: "short" })
    : "";

  return (
    <Layout>
      <div className="staff-dashboard">
        <PageHeading
          eyebrow={chairman ? "Chairperson overview" : "Staff operations"}
          title={`${greeting}, ${user?.first_name || user?.username || "team"}`}
          description="A clear view of recorded SACCO activity and work awaiting review."
          actions={
            <>
              <StatusBadge status="active" label={chairman ? "Chairperson workspace" : "Staff workspace"} />
              <Button variant="secondary" onClick={fetchDashboard} loading={loading}>
                <Icon name="refresh" size={16} /> Refresh
              </Button>
            </>
          }
        />

        {error && (
          <FeedbackMessage
            tone={stats ? "warning" : "danger"}
            title={stats ? "Showing the last successful update" : "Dashboard unavailable"}
            action={<Button variant="secondary" onClick={fetchDashboard} loading={loading}>Retry</Button>}
          >
            {error}{asOf ? ` Last successful update: ${asOf}.` : ""}
          </FeedbackMessage>
        )}

        {loading && !stats && <LoadingState label="Loading operations data…" />}
        {loading && stats && <p className="staff-refresh-indicator" role="status">Refreshing recorded activity…</p>}

        {stats && (
          <>
            <section className="hero-metric-card" aria-labelledby="staff-hero-title">
              <div className="hero-metric-copy">
                <p className="hero-metric-eyebrow" id="staff-hero-title">Member savings recorded · all time</p>
                <p className="hero-metric-value">{formatKES(stats.total_savings)}</p>
                <p className="hero-metric-note">
                  Sum of recorded member savings entries. Savings and loan balances are reported separately.
                  {asOf ? ` Updated ${asOf}.` : ""}
                </p>
              </div>
              <div className="hero-metric-icon" aria-hidden="true"><Icon name="coins" size={48} /></div>
            </section>

            <section className="bento-grid staff-kpi-grid" aria-label="Recorded operational metrics">
              <MetricCard
                label="Registered member records"
                value={formatCount(stats.total_members)}
                helper="Member records in the system"
                icon="users"
              />
              <MetricCard
                label="Recorded approved-loan balances"
                value={formatKES(stats.active_loans)}
                helper="Stored balances; the system does not confirm loan disbursement"
                icon="bank"
              />
              <MetricCard
                label="Approved applications"
                value={formatCount(stats.approved_loans)}
                helper="Approval is separate from disbursement"
                icon="file"
              />
            </section>

            <section className="premium-chart-panel" aria-labelledby="staff-savings-chart-title">
              <div className="premium-chart-header">
                <div>
                  <h2 className="premium-chart-title" id="staff-savings-chart-title">Monthly savings entries</h2>
                  <p className="staff-dashboard-support">Recorded member savings amounts by entry month.</p>
                </div>
                <label className="staff-period-control">
                  <span className="sr-only">Chart time period</span>
                  <select
                    className="chart-period-select"
                    value={period}
                    onChange={(event) => setPeriod(event.target.value)}
                    aria-label="Chart time period"
                  >
                    <option value="6">6 latest available months</option>
                    <option value="12">12 latest available months</option>
                  </select>
                </label>
              </div>
              {savingsByMonth === null || (monthlySavingsProvided && stats.monthly_savings.length > 0 && savingsByMonth.length === 0) ? (
                <div className="ui-empty" role="status">
                  <strong>Monthly savings data unavailable</strong>
                  <p>This response did not include a usable monthly savings series.</p>
                </div>
              ) : savingsByMonth.length === 0 ? (
                <div className="ui-empty" role="status">
                  <strong>No monthly savings entries</strong>
                  <p>Monthly amounts will appear here when recorded data is available.</p>
                </div>
              ) : (
                <MonthlyChart title="Monthly savings amounts" data={savingsByMonth} color="var(--chart-primary)" />
              )}
            </section>

            <section className="staff-dashboard-lower-grid" aria-label="Work queue and recent activity">
              {hasLoanReviewPermission && (
                <article className="ui-panel staff-queue-panel">
                  <div className="ui-panel-header">
                    <div>
                      <h2 className="ui-panel-title">Loan review queue</h2>
                      <p className="staff-dashboard-support">Applications currently marked pending.</p>
                    </div>
                    {!pendingLoansKnown ? (
                      <StatusBadge status="needs_review" label="Count unavailable" />
                    ) : (
                      <StatusBadge
                        status={Number(stats.pending_loans) > 0 ? "pending" : "confirmed"}
                        label={Number(stats.pending_loans) > 0 ? "Needs review" : "Up to date"}
                      />
                    )}
                  </div>
                  <div className="ui-panel-body staff-queue-body">
                    <strong className="staff-queue-count">{pendingLoans}</strong>
                    <span>pending applications</span>
                    <Button as={Link} to="/admin/loans" variant="primary">
                      Review applications <Icon name="arrowRight" size={16} />
                    </Button>
                  </div>
                </article>
              )}

              <article className="ui-panel staff-activity-panel">
                <div className="ui-panel-header">
                  <div>
                    <h2 className="ui-panel-title">Recent account activity</h2>
                    <p className="staff-dashboard-support">Most recently recorded ledger transactions.</p>
                  </div>
                  <Icon name="receipt" size={18} aria-hidden="true" />
                </div>
                {recentTransactions === null ? (
                  <div className="ui-empty" role="status">
                    <strong>Recent activity unavailable</strong>
                    <p>This response did not include recent account activity.</p>
                  </div>
                ) : recentTransactions.length === 0 ? (
                  <div className="ui-empty" role="status">
                    <strong>No recent activity</strong>
                    <p>Recorded transactions will appear here.</p>
                  </div>
                ) : (
                  <DataTable label="Recent account activity" className="staff-activity-table">
                    <table className="ui-table">
                      <thead>
                        <tr><th scope="col">Member</th><th scope="col">Activity</th><th scope="col">Amount</th><th scope="col">Recorded</th></tr>
                      </thead>
                      <tbody>
                        {recentTransactions.map((transaction) => (
                          <tr key={transaction.id}>
                            <td>{transaction.member || "Member unavailable"}</td>
                            <td className="staff-activity-type">{String(transaction.type || "Activity").replaceAll("_", " ")}</td>
                            <td className="ui-money">{formatKES(transaction.amount)}</td>
                            <td>{formatDate(transaction.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </DataTable>
                )}
              </article>
            </section>
          </>
        )}
      </div>
    </Layout>
  );
}
