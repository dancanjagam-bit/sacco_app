import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import { hasPermission, ROUTES } from "../navigation/routes";
import "../styles/chairmanDashboard.css";

const kes = (n, compact = false) => {
  if (n == null) return "Unavailable";
  const num = Number(n);
  if (compact) {
    if (num >= 1_000_000) return `KES ${(num / 1_000_000).toFixed(1)}M`;
    if (num >= 1_000) return `KES ${(num / 1_000).toFixed(1)}K`;
  }
  return `KES ${num.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

function ChairmanTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chairman-chart-tooltip">
      <p className="chairman-chart-tooltip-label">{label}</p>
      <p className="chairman-chart-tooltip-value">{kes(payload[0]?.value)}</p>
    </div>
  );
}

function MetricPill({ label, value, sublabel, tone = "neutral" }) {
  return (
    <div className={`chairman-metric chairman-metric-${tone}`}>
      <span className="chairman-metric-icon" aria-hidden="true">
        <Icon name={tone === "savings" ? "wallet" : tone === "loans" ? "bank" : "truck"} size={20} />
      </span>
      <div className="chairman-metric-body">
        <p className="chairman-metric-value">{value}</p>
        <p className="chairman-metric-label">{label}</p>
        {sublabel && <p className="chairman-metric-sub">{sublabel}</p>}
      </div>
    </div>
  );
}

function ActionCard({ title, count, badge, badgeTone = "warning", linkTo, linkLabel, icon }) {
  return (
    <div className="chairman-action-card">
      <div className="chairman-action-card-head">
        <span className="chairman-action-icon"><Icon name={icon} size={18} /></span>
        <div>
          <p className="chairman-action-title">{title}</p>
          <p className="chairman-action-count">{count}</p>
        </div>
        <StatusBadge status={badgeTone} label={badge} />
      </div>
      {linkTo && (
        <Link className="chairman-action-btn" to={linkTo}>
          {linkLabel} <Icon name="arrowRight" size={15} />
        </Link>
      )}
    </div>
  );
}

export default function ChairmanDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const [chartRange, setChartRange] = useState(6);

  const orgName = "Nairobi West Tuktuk Operators Transport Cooperative Society";
  const firstName = user?.first_name || user?.username || "Chairman";

  const load = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const response = await api.get("admin/chairman/summary/");
      setData(response.data);
      setState("ready");
    } catch (err) {
      setError(
        err.response?.status === 403
          ? "Chairman workspace is not assigned to your account."
          : "Dashboard data could not be loaded. Try again."
      );
      setState("error");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const chartData = Array.isArray(data?.monthly_remittances) ? data.monthly_remittances : [];

  return (
    <Layout>
      <main className="chairman-page">
        {/* ── Page heading ── */}
        <PageHeading
          eyebrow="Chairman oversight"
          title={`Welcome, ${firstName}`}
          description={orgName}
          actions={<StatusBadge status="active" label="Chairman workspace" />}
        />

        {error && (
          <FeedbackMessage tone="danger" title="Dashboard unavailable"
            action={<Button variant="secondary" onClick={load}>Retry</Button>}>
            {error}
          </FeedbackMessage>
        )}
        {state === "loading" && <LoadingState label="Loading cooperative overview…" />}

        {state === "ready" && data && (
          <>
            <section className="chairman-hero" aria-label="Confirmed remittances this month">
              <div className="chairman-hero-content">
                <p className="chairman-hero-eyebrow">Confirmed remittances · This month</p>
                <p className="chairman-hero-value">
                  {kes(data.confirmed_remittances_this_month)}
                </p>
              </div>
              <span className="chairman-hero-icon" aria-hidden="true">
                <Icon name="wallet" size={44} />
              </span>
            </section>

            {/* ── Three metric cards ── */}
            <div className="chairman-metrics" role="list">
              <MetricPill
                label="Member savings"
                value={kes(data.savings_liabilities, true)}
                sublabel="Savings liabilities"
                tone="savings"
              />
              <MetricPill
                label="Active loans"
                value={kes(data.loan_balance_outstanding, true)}
                sublabel="Outstanding loan balance"
                tone="loans"
              />
              <MetricPill
                label="On the register"
                value={data.registered_vehicles ?? "—"}
                sublabel="Registered vehicles"
                tone="vehicles"
              />
            </div>

            {/* ── Collections bar chart ── */}
            <section className="chairman-panel" aria-labelledby="collections-chart-title">
              <div className="chairman-panel-header">
                <h2 id="collections-chart-title">Confirmed remittances</h2>
                <div className="chairman-chart-controls">
                  {[3, 6].map((n) => (
                    <button
                      key={n}
                      className={`chairman-range-btn${chartRange === n ? " is-active" : ""}`}
                      onClick={() => setChartRange(n)}
                      aria-pressed={chartRange === n}
                    >
                      Last {n} months
                    </button>
                  ))}
                </div>
              </div>
              <div className="chairman-chart-wrap">
                {chartData.length === 0 ? (
                  <div className="chairman-chart-empty">
                    <p>No confirmed remittance data available yet.</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart
                      data={chartData.slice(-chartRange)}
                      margin={{ top: 16, right: 8, left: 8, bottom: 0 }}
                      barCategoryGap="28%"
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="month"
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: "var(--text-muted)", fontSize: 13 }}
                      />
                      <YAxis
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                        tickFormatter={(v) => v >= 1000 ? `KES ${(v / 1000).toFixed(0)}K` : `KES ${v}`}
                        width={82}
                      />
                      <Tooltip content={<ChairmanTooltip />} cursor={{ fill: "rgba(15,76,129,0.06)" }} />
                      <Bar
                        dataKey="total"
                        fill="var(--chart-primary)"
                        radius={[5, 5, 0, 0]}
                        label={{ position: "top", fill: "var(--text-muted)", fontSize: 11,
                          formatter: (v) => v >= 1000 ? `KES ${(v / 1000).toFixed(0)}K` : `KES ${v}` }}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            {/* ── Action cards ── */}
            <div className="chairman-actions" role="list">
              {hasPermission(user, "loans.approve_assigned") && <ActionCard
                icon="bank"
                title="Loan reviews"
                count={`${data.pending_loan_reviews ?? 0} pending`}
                badge={data.pending_loan_reviews > 0 ? "Pending" : "Up to date"}
                badgeTone={data.pending_loan_reviews > 0 ? "warning" : "active"}
                linkTo={ROUTES.adminLoans}
                linkLabel="Review loans"
              />}
            </div>

            {/* ── Upcoming meetings ── */}
            {Array.isArray(data.upcoming_meetings) && (
              <section className="chairman-panel" aria-labelledby="upcoming-meetings-title">
                <div className="chairman-panel-header">
                  <h2 id="upcoming-meetings-title">Upcoming meetings</h2>
                </div>
                {data.upcoming_meetings.length === 0 ? (
                  <p style={{ padding: "var(--space-3) var(--space-4)", color: "var(--text-muted)", margin: 0 }}>No meetings scheduled.</p>
                ) : (
                  <div style={{ padding: "var(--space-2) var(--space-4)", display: "grid", gap: "var(--space-2)" }}>
                    {data.upcoming_meetings.map((m) => (
                      <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--space-3)", padding: "var(--space-2) 0", borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
                        <div>
                          <strong>{m.title}</strong>
                          <span style={{ marginLeft: 8, fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>{m.meeting_type}</span>
                        </div>
                        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                          {new Date(m.scheduled_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" })}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {hasPermission(user, "members.review") && (
                  <div style={{ padding: "var(--space-2) var(--space-4) var(--space-3)" }}>
                    <Link className="chairman-link-item" to={ROUTES.secretaryMeetings} style={{ display: "inline-flex", fontSize: "var(--text-sm)" }}>
                      View all meetings <Icon name="arrowRight" size={14} />
                    </Link>
                  </div>
                )}
              </section>
            )}

            {/* ── Welfare overview ── */}
            {(data.welfare_submitted != null || data.welfare_pending_payout != null) && (
              <section className="chairman-panel" aria-labelledby="welfare-overview-title">
                <div className="chairman-panel-header">
                  <h2 id="welfare-overview-title">Welfare overview</h2>
                </div>
                <div style={{ padding: "var(--space-3) var(--space-4)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                  <div>
                    <p style={{ margin: "0 0 4px", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>Cases awaiting review</p>
                    <strong style={{ fontSize: "var(--text-xl)" }}>{data.welfare_submitted ?? "—"}</strong>
                  </div>
                  <div>
                    <p style={{ margin: "0 0 4px", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>Payouts awaiting confirmation</p>
                    <strong style={{ fontSize: "var(--text-xl)" }}>{data.welfare_pending_payout ?? "—"}</strong>
                  </div>
                </div>
                <p style={{ margin: "0 var(--space-4) var(--space-3)", fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                  Sensitive case details restricted. Contact the welfare officer for individual case information.
                </p>
              </section>
            )}

            {/* ── Quick links ── */}
            <section className="chairman-panel chairman-links" aria-label="Quick navigation">
              <div className="chairman-panel-header"><h2>Overview</h2></div>
              <div className="chairman-links-grid">
                {[
                  { to: ROUTES.adminMembers, icon: "users", label: "Members", count: data.total_members, permission: "members.review" },
                  { to: ROUTES.adminLoans, icon: "bank", label: "Loan decisions", count: data.pending_loan_reviews, permission: "loans.approve_assigned" },
                  { to: ROUTES.adminTransport, icon: "truck", label: "Transport", count: data.registered_vehicles, permission: "staff.manage" },
                  { to: ROUTES.adminFinancialReports, icon: "file", label: "Reports", count: null, permission: "reports.financial.read" },
                ].filter(({ to, permission }) => to && hasPermission(user, permission)).map(({ to, icon, label, count }) => (
                  <Link key={to} to={to} className="chairman-link-item">
                    <span className="chairman-link-icon"><Icon name={icon} size={18} /></span>
                    <span className="chairman-link-label">{label}</span>
                    {count != null && <span className="chairman-link-count">{count}</span>}
                    <Icon name="arrowRight" size={14} />
                  </Link>
                ))}
              </div>
            </section>
          </>
        )}

        {/* Refresh */}
        {state !== "loading" && (
          <div className="chairman-refresh">
            <Button variant="secondary" size="sm" onClick={load}>
              <Icon name="refresh" size={15} /> Refresh
            </Button>
          </div>
        )}
      </main>
    </Layout>
  );
}
