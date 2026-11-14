import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import StatusBadge from "../components/ui/StatusBadge";
import Icon from "../components/ui/Icon";
import Button from "../components/ui/Button";
import PageHeading from "../components/ui/PageHeading";
import api from "../api/axios";
import "../styles/memberDashboard.css";

/* ── Helpers ────────────────────────────────────────────────────────────── */
function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function fmt(n) {
  if (n == null) return null;
  return `KES ${Number(n).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/* Hidden balance placeholder */
const MASK = "\u2022\u2022\u2022\u2022\u2022\u2022";

/* ── Component ──────────────────────────────────────────────────────────── */
export default function Dashboard() {
  const { user } = useAuth();
  const transportRoles = Array.isArray(user?.transport_roles) ? user.transport_roles : [];
  const isCrew = transportRoles.includes("driver") || transportRoles.includes("conductor");

  /* Collateral / FOSA data fetched independently from the user object */
  const [collateral,     setCollateral]     = useState(null);  // null = not yet loaded
  const [collateralErr,  setCollateralErr]  = useState(false);
  const [collateralLoad, setCollateralLoad] = useState(true);

  /* A crew home card must reflect the effective assignment API, not profile
     labels that may be absent or stale. */
  const [crewShift, setCrewShift] = useState(null);
  const [crewShiftState, setCrewShiftState] = useState(isCrew ? "loading" : "idle");

  /* Loan schedule (fetched per active loan) */
  const [schedule, setSchedule] = useState(null);

  /* Balance visibility */
  const [balancesHidden, setBalancesHidden] = useState(false);

  /* ── Fetch helpers ── */
  const fetchCollateral = useCallback(async () => {
    setCollateralLoad(true);
    setCollateralErr(false);
    // Clear stale data so a failed refresh never shows old numbers as current.
    setCollateral(null);
    try {
      const res = await api.get("collateral/status/");
      setCollateral(res.data);
    } catch {
      setCollateralErr(true);
    } finally {
      setCollateralLoad(false);
    }
  }, []);

  const fetchCrewShift = useCallback(async () => {
    setCrewShiftState("loading");
    setCrewShift(null);
    try {
      const response = await api.get("transport/crew/today/");
      if (!response.data || typeof response.data !== "object" || Array.isArray(response.data)) {
        throw new Error("Unexpected shift response");
      }
      if (response.data.assignment != null &&
          (typeof response.data.assignment !== "object" || Array.isArray(response.data.assignment))) {
        throw new Error("Unexpected assignment response");
      }
      setCrewShift(response.data);
      setCrewShiftState("ready");
    } catch {
      setCrewShift(null);
      setCrewShiftState("error");
    }
  }, []);

  /* Fetch on mount */
  useEffect(() => {
    fetchCollateral();
  }, [fetchCollateral]);

  useEffect(() => {
    if (isCrew) fetchCrewShift();
  }, [fetchCrewShift, isCrew]);

  /* Fetch schedule for active loan */
  const loans = user?.loans || [];
  const activeLoan = loans.find((l) => l.status === "approved" && Number(l.balance) > 0);

  useEffect(() => {
    if (!activeLoan?.id) return;
    api.get(`loan/${activeLoan.id}/schedule/`).then((r) => {
      setSchedule(r.data?.schedule ?? null);
    }).catch(() => {});
  }, [activeLoan?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Derived values ── */
  const transactions   = user?.transactions || [];

  /* BOSA savings */
  const bosaBalance = collateral?.bosa_balance != null
    ? Number(collateral.bosa_balance)
    : user?.bosa_savings != null
      ? Number(user.bosa_savings)
      : null;

  /* Total deposits */
  const totalDeposits = user?.total_deposits != null ? Number(user.total_deposits) : null;

  /* FOSA values — from collateral endpoint, not mixed with user object */
  const fosaRecorded   = collateral?.fosa_balance       != null ? Number(collateral.fosa_balance)       : null;
  const fosaWithdrawable = collateral?.fosa_withdrawable  != null ? Number(collateral.fosa_withdrawable)  : null;
  const fosaPending    = collateral?.fosa_withdrawals_pending != null
    ? Number(collateral.fosa_withdrawals_pending)
    : null;
  /* Available = withdrawable amount from server (already accounts for holds) */
  const fosaAvailable  = fosaWithdrawable;

  /* Repayment progress */
  const paidAmount = activeLoan
    ? Number(activeLoan.amount) - Number(activeLoan.balance)
    : 0;
  const repaidPct = activeLoan && Number(activeLoan.amount) > 0
    ? Math.round((paidAmount / Number(activeLoan.amount)) * 100)
    : 0;

  /* Next scheduled installment */
  const nextInstallment = Array.isArray(schedule)
    ? schedule.find((s) => s.status === "upcoming" || s.status === "overdue" || !s.paid)
    : null;
  const nextExpected = Number(nextInstallment?.expected);
  const nextPaid = Number(nextInstallment?.paid || 0);
  const nextDue = Number.isFinite(nextExpected) && Number.isFinite(nextPaid)
    ? Math.max(0, nextExpected - nextPaid)
    : null;
  const nextAmount = nextDue != null ? fmt(nextDue) : null;

  const recentTxns = transactions.slice(0, 5);

  /* ── Render ── */
  return (
    <Layout>
      {() => (
        <div className="member-dashboard">
          <PageHeading
            eyebrow="Member services"
            title={`${greeting()}, ${user?.first_name || user?.username || "Member"}`}
            description={`Member${user?.member_number ? ` ${user.member_number}` : ""} · Nairobi West Tuktuk Operators Transport Cooperative Society`}
            actions={
              <>
                <StatusBadge status="active" label="Member" />
                <button
                  type="button"
                  className="balance-toggle"
                  onClick={() => setBalancesHidden((value) => !value)}
                  aria-pressed={balancesHidden}
                  aria-label={balancesHidden ? "Show balances" : "Hide balances"}
                >
                  <Icon name={balancesHidden ? "eye" : "eyeOff"} size={15} />
                  {balancesHidden ? "Show balances" : "Hide balances"}
                </button>
              </>
            }
          />

          {/* ── Available FOSA hero region ── */}
          <section
            aria-label="Available FOSA"
            className="sacco-hero member-fosa-hero"
            style={{
              borderRadius: "var(--radius-card)",
              padding: "clamp(1rem,1.5vw,1.5rem)",
              marginBottom: "1rem",
              position: "relative",
              overflow: "hidden",
            }}
          >
            {/* Decorative circle */}
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                top: "-2rem",
                right: "-2rem",
                width: "10rem",
                height: "10rem",
                borderRadius: "50%",
                background: "rgba(255,255,255,0.05)",
                pointerEvents: "none",
              }}
            />

            <p
              style={{
                margin: "0 0 4px",
                fontSize: "var(--text-sm)",
                color: "var(--hero-text)",
                fontWeight: 600,
              }}
            >
              Available FOSA funds
            </p>

            {/* Loading state */}
            {collateralLoad && !collateralErr && (
              <p
                className="sacco-value"
                style={{ margin: "0 0 6px", color: "var(--hero-text)" }}
                aria-live="polite"
              >
                Loading&hellip;
              </p>
            )}

            {/* Error state */}
            {collateralErr && (
              <>
                <p
                  style={{
                    margin: "0 0 6px",
                    fontSize: "0.9375rem",
                    fontWeight: 700,
                    color: "var(--hero-text)",
                  }}
                  aria-live="assertive"
                >
                  FOSA availability could not be refreshed
                </p>
                <p
                  style={{ margin: "0 0 12px", fontSize: "var(--text-sm)", color: "var(--hero-text)" }}
                >
                  Unavailable
                </p>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="ui-button ui-button-secondary"
                    onClick={fetchCollateral}
                  >
                    Retry
                  </button>
                </div>
              </>
            )}

            {/* Loaded state */}
            {!collateralLoad && !collateralErr && (
              <>
                <p
                  className="sacco-value"
                  style={{ margin: "0 0 6px", color: "var(--hero-text)" }}
                  aria-live="polite"
                >
                  {balancesHidden
                    ? MASK
                    : fosaAvailable != null
                      ? fmt(fosaAvailable)
                      : "Unavailable"}
                </p>

                {/* Detail line */}
                <p
                  style={{
                    margin: "0 0 16px",
                    fontSize: "var(--text-sm)",
                    color: "var(--hero-text)",
                  }}
                >
                  {fosaRecorded != null ? (
                    <>
                      Recorded FOSA balance{" "}
                      <strong style={{ color: "var(--hero-text)" }}>
                        {balancesHidden ? MASK : fmt(fosaRecorded)}
                      </strong>
                      {fosaPending != null && (
                        <>
                          {" "}&middot;{" "}Held for pending withdrawals{" "}
                          <strong style={{ color: "var(--hero-text)" }}>
                            {balancesHidden ? MASK : fmt(fosaPending)}
                          </strong>
                        </>
                      )}
                    </>
                  ) : (
                    "FOSA balance not configured \u2014 contact your SACCO"
                  )}
                </p>

              </>
            )}
          </section>

          <div className="member-primary-actions" aria-label="Primary account actions">
            <Link to="/savings" className="ui-button ui-button-accent member-primary-action">
              <Icon name="download" size={17} /> Deposit
            </Link>
            <Link to="/savings" className="ui-button ui-button-secondary member-primary-action">
              <Icon name="wallet" size={17} /> Withdraw
            </Link>
            <Link to="/loans" className="ui-button ui-button-secondary member-primary-action">
              <Icon name="bank" size={17} /> Apply for loan
            </Link>
            <Link to="/transactions" className="ui-button ui-button-secondary member-primary-action">
              <Icon name="file" size={17} /> Statements
            </Link>
            <Button variant="secondary" onClick={fetchCollateral} loading={collateralLoad} aria-label="Refresh available FOSA funds" className="member-refresh-button">
              <Icon name="refresh" size={16} />
              <span className="member-refresh-label">Refresh balance</span>
            </Button>
          </div>

          {/* ── KPI regions ── */}
          <div className="sacco-grid member-summary-grid">
            {/* BOSA savings */}
            <section
              aria-label="BOSA savings"
              className="sacco-card sacco-span-4 member-summary-card"
            >
              <div className="member-summary-head">
                <p className="member-summary-label">BOSA savings</p>
                <span className="member-summary-icon" aria-hidden="true"><Icon name="bank" size={18} /></span>
              </div>
              <p className="member-summary-value" aria-live="polite">
                {balancesHidden
                  ? MASK
                  : bosaBalance != null
                    ? fmt(bosaBalance)
                    : "Unavailable"}
              </p>
              <p className="member-summary-helper">
                Recorded BOSA account balance
              </p>
            </section>

            {/* Total deposits */}
            <section
              aria-label="Total deposits recorded"
              className="sacco-card sacco-span-4 member-summary-card"
            >
              <div className="member-summary-head">
                <p className="member-summary-label">Total deposits recorded</p>
                <span className="member-summary-icon is-emerald" aria-hidden="true"><Icon name="coins" size={18} /></span>
              </div>
              <p className="member-summary-value" aria-live="polite">
                {balancesHidden
                  ? MASK
                  : totalDeposits != null
                    ? fmt(totalDeposits)
                    : "Unavailable"}
              </p>
              <p className="member-summary-helper">
                All-time cumulative deposits
              </p>
            </section>

            {/* Active loan balance */}
            <section
              aria-label="Balance on approved applications"
              className="sacco-card sacco-span-4 member-summary-card"
            >
              <div className="member-summary-head">
                <p className="member-summary-label">Balance on approved applications</p>
                <span className="member-summary-icon" aria-hidden="true"><Icon name="file" size={18} /></span>
              </div>
              <p className="member-summary-value" aria-live="polite">
                {balancesHidden
                  ? MASK
                  : activeLoan
                    ? fmt(activeLoan.balance)
                    : "None"}
              </p>
              <p className="member-summary-helper">
                Outstanding principal &mdash; disbursement is not tracked here
              </p>
            </section>
          </div>

          {/* ── Transport assignment ── */}
          {isCrew && (
            <section className="sacco-card dashboard-shift-card member-shift-card" aria-label="Today’s assigned shift">
              <span className="dashboard-shift-icon" aria-hidden="true"><Icon name="bus" size={22} /></span>
              <div className="dashboard-shift-copy">
                <p className="dashboard-shift-eyebrow">Today</p>
                {crewShiftState === "loading" ? (
                  <p role="status">Checking your assignment…</p>
                ) : crewShiftState === "error" ? (
                  <>
                    <p role="alert">Shift information is unavailable.</p>
                    <Button variant="secondary" onClick={fetchCrewShift}>Retry</Button>
                  </>
                ) : crewShift?.assignment ? (
                  <>
                    <strong>{crewShift.assignment.vehicle_registration || "Vehicle unavailable"}</strong>
                    <p>{crewShift.assignment.route_name || "Route unavailable"}{crewShift.assignment.stage_name ? ` · ${crewShift.assignment.stage_name}` : ""}</p>
                  </>
                ) : (
                  <>
                    <strong>No current shift assignment</strong>
                    <p>{crewShift?.message || "No active assignment was returned for today."}</p>
                  </>
                )}
              </div>
              {crewShift?.assignment && (
                <StatusBadge
                  status={crewShift.assignment.status || "unknown"}
                  label={crewShift.assignment.status_label || crewShift.assignment.status || "Status unavailable"}
                />
              )}
              <Link className="ui-button ui-button-secondary dashboard-shift-link" to="/transport/crew">
                {crewShiftState === "ready" && !crewShift?.assignment ? "View assignment help" : "Open shift"}
              </Link>
            </section>
          )}

          {/* ── Loan repayment progress ── */}
          {activeLoan && (
            <div
              className="sacco-card repayment-panel"
              style={{ marginBottom: "var(--grid-gap)" }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: "12px",
                  marginBottom: "10px",
                }}
              >
                <div>
                  <p style={{ margin: "0 0 2px", fontWeight: 700, fontSize: "14px", color: "var(--text)" }}>
                    Schedule status
                  </p>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted)" }}>
                    Principal repaid {repaidPct}%
                  </p>
                </div>
                <span style={{ fontWeight: 700, fontSize: "14px", color: "var(--text)" }}>
                  {repaidPct}%
                </span>
              </div>

              {/* Progress bar */}
              <div
                role="progressbar"
                aria-valuenow={repaidPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Loan repayment ${repaidPct}%`}
                style={{
                  height: "8px",
                  borderRadius: "999px",
                  background: "var(--surface-muted)",
                  overflow: "hidden",
                  margin: "0 0 12px",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${repaidPct}%`,
                    background: "var(--emerald)",
                    borderRadius: "999px",
                    transition: "width var(--duration-base, 180ms) var(--ease)",
                  }}
                />
              </div>

              {/* Next repayment */}
              <div className="next-repayment">
                <p
                  style={{
                    margin: "0 0 4px",
                    fontWeight: 600,
                    fontSize: "13px",
                    color: "var(--text-muted)",
                  }}
                >
                  Next repayment
                </p>
                <p
                  className="repayment-amount"
                  style={{
                    margin: 0,
                    fontWeight: 700,
                    fontSize: "14px",
                    color: "var(--text)",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {nextAmount ?? "Unavailable"}
                </p>
                {nextInstallment?.due_date && (
                  <p style={{ margin: "4px 0 0", fontSize: "12px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "5px" }}>
                    <Icon name="calendar" size={13} />
                    Due{" "}
                    {new Date(nextInstallment.due_date).toLocaleDateString("en-KE", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* ── Recent transactions ── */}
          <div
            className="sacco-card member-activity-panel"
            style={{ overflow: "hidden", padding: 0 }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "1rem var(--card-padding)",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <h2 style={{ margin: 0, fontSize: "0.9375rem", fontWeight: 700, color: "var(--text)" }}>
                Recent activity
              </h2>
              <Link
                to="/transactions"
                style={{
                  fontSize: "13px",
                  color: "var(--action)",
                  fontWeight: 700,
                  textDecoration: "none",
                }}
              >
                View all
              </Link>
            </div>

            {recentTxns.length === 0 ? (
              <div
                style={{
                  padding: "2rem 1rem",
                  textAlign: "center",
                  color: "var(--text-muted)",
                  fontSize: "14px",
                }}
              >
                <p style={{ margin: 0 }}>No transactions yet. Activity will appear here.</p>
              </div>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                {recentTxns.map((t) => {
                  const txStatus = t.withdrawal_status || t.status || "confirmed";
                  return (
                    <li
                      key={t.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "12px",
                        padding: "14px var(--card-padding)",
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      <span
                        aria-hidden="true"
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: "36px",
                          height: "36px",
                          borderRadius: "var(--radius-control)",
                          background: "var(--surface-muted)",
                          color: "var(--brand)",
                          flexShrink: 0,
                        }}
                      >
                        <Icon
                          name={
                            t.type === "deposit"    ? "download" :
                            t.type === "repayment"  ? "bank"     :
                            t.type === "withdrawal" ? "wallet"   :
                            "receipt"
                          }
                          size={16}
                        />
                      </span>

                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p
                          style={{
                            margin: "0 0 2px",
                            fontWeight: 700,
                            fontSize: "14px",
                            color: "var(--text)",
                            textTransform: "capitalize",
                          }}
                        >
                          {t.type}
                        </p>
                        <p style={{ margin: 0, fontSize: "12px", color: "var(--text-muted)" }}>
                          {new Date(t.created_at).toLocaleDateString("en-KE", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                          {t.note ? ` \u00b7 ${t.note}` : ""}
                        </p>
                      </div>

                      <div style={{ textAlign: "right", flexShrink: 0 }}>
                        <p
                          style={{
                            margin: "0 0 4px",
                            fontWeight: 700,
                            fontSize: "14px",
                            color: "var(--text)",
                            fontVariantNumeric: "tabular-nums",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {balancesHidden ? MASK : fmt(t.amount)}
                        </p>
                        <StatusBadge status={txStatus} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </Layout>
  );
}
