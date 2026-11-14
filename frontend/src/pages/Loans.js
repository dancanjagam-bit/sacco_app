import React, { useState, useEffect, useCallback } from "react";
import { Link, useLocation } from "react-router-dom";

import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import LoanTable from "../components/LoanTable";
import api from "../api/axios";
import { ROUTES } from "../navigation/routes";

import "../styles/dashboard.css";

const PURPOSES = [
  ["business",  "🏢 Business / Investment"],
  ["education", "🎓 Education"],
  ["medical",   "🏥 Medical / Emergency"],
  ["asset",     "🚗 Asset Purchase"],
  ["housing",   "🏠 Housing / Construction"],
  ["farming",   "🌾 Farming / Agriculture"],
  ["personal",  "👤 Personal Use"],
  ["other",     "📋 Other"],
];

function EligibilityBadge({ tier }) {
  if (!tier) return null;
  const colors = {
    "Gold (12+ months)":    { bg: "#fef3c7", color: "#92400e", border: "#fcd34d" },
    "Silver (9–11 months)": { bg: "#f1f5f9", color: "#475569", border: "#94a3b8" },
    "Bronze (6–8 months)":  { bg: "#fef3c7", color: "#b45309", border: "#fcd34d" },
  };
  const s = colors[tier] || {};
  return (
    <span style={{
      padding: "3px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "700",
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>
      {tier === "Gold (12+ months)" ? "🥇" : tier === "Silver (9–11 months)" ? "🥈" : "🥉"} {tier}
    </span>
  );
}

function SavingsCalendar({ months }) {
  if (!months || months.length === 0) return null;

  return (
    <div>
      <p style={{ fontSize: "13px", fontWeight: "600", color: "#64748b", marginBottom: "8px" }}>
        Savings History (last 13 months)
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
        {months.map((m, i) => (
          <div key={i} title={`${m.month}: KES ${Number(m.total).toLocaleString()}`} style={{
            padding: "4px 10px",
            borderRadius: "6px",
            fontSize: "11px",
            fontWeight: "600",
            background: m.qualifies ? "#dcfce7" : m.total > 0 ? "#fef3c7" : "#f1f5f9",
            color:      m.qualifies ? "#15803d" : m.total > 0 ? "#b45309" : "#94a3b8",
            border:     `1px solid ${m.qualifies ? "#86efac" : m.total > 0 ? "#fcd34d" : "#e2e8f0"}`,
            cursor: "default",
          }}>
            {m.month}
            {m.qualifies ? " ✓" : m.total > 0 ? " ⚠" : " —"}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "16px", marginTop: "8px", fontSize: "11px", color: "#64748b" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#dcfce7", border: "1px solid #86efac", display: "inline-block" }} />
          Qualifies
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#fef3c7", border: "1px solid #fcd34d", display: "inline-block" }} />
          Below minimum
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#f1f5f9", border: "1px solid #e2e8f0", display: "inline-block" }} />
          No deposit
        </span>
      </div>
    </div>
  );
}

function GuarantorRequests() {
  const [requests, setRequests] = useState([]);
  const [acting,   setActing]   = useState(null);

  useEffect(() => {
    // Fetch pending guarantor requests for the current user
    api.get("guarantor/pending/").then(r => setRequests(r.data)).catch(() => {});
  }, []);

  const respond = async (id, action) => {
    setActing(id);
    try {
      await api.post(`guarantor/${id}/respond/`, { action });
      setRequests(requests.filter(r => r.id !== id));
    } catch { alert("Failed to respond."); }
    finally { setActing(null); }
  };

  if (requests.length === 0) return null;

  return (
    <div style={{ background: "#fff", borderRadius: "12px", padding: "20px 24px", boxShadow: "var(--shadow)", marginTop: "24px" }}>
      <h3 style={{ margin: "0 0 14px", fontSize: "16px", fontWeight: "700", color: "#b45309" }}>
        🤝 Pending Guarantor Requests ({requests.length})
      </h3>
      {requests.map(r => (
        <div key={r.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
          <div>
            <p style={{ margin: "0 0 4px", fontWeight: "600" }}>{r.borrower} requests you as guarantor</p>
            <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>Loan of KES {Number(r.loan_amount).toLocaleString()} for {r.loan_months} months</p>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button disabled={acting === r.id} onClick={() => respond(r.id, "accept")} style={{ padding: "7px 14px", background: "#16a34a", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "600", cursor: "pointer" }}>✅ Accept</button>
            <button disabled={acting === r.id} onClick={() => respond(r.id, "decline")} style={{ padding: "7px 14px", background: "#dc2626", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "600", cursor: "pointer" }}>❌ Decline</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function Loans() {  const { user, refreshUser } = useAuth();
  const { state } = useLocation();
  const prefill = state?.prefill;

  const [eligibility, setEligibility] = useState(null);
  const [loadingElig, setLoadingElig] = useState(true);

  const [amount,         setAmount]         = useState(prefill?.amount ?? "");
  const [repaymentMonths,setRepaymentMonths] = useState(prefill?.months ?? 12);
  const [purpose,        setPurpose]        = useState("personal");
  const [purposeDetails, setPurposeDetails] = useState("");
  const [submitting,     setSubmitting]     = useState(false);
  const [formMsg,        setFormMsg]        = useState(null);

  const loans = user?.loans || [];

  const fetchEligibility = useCallback(async () => {
    setLoadingElig(true);
    try {
      const res = await api.get("loan/eligibility/");
      setEligibility(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingElig(false);
    }
  }, []);

  useEffect(() => { fetchEligibility(); }, [fetchEligibility]);

  const periods = Object.keys(eligibility?.interest_rates || {}).map(Number);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormMsg(null);

    const value = parseFloat(amount);
    if (!amount || isNaN(value) || value <= 0) {
      setFormMsg({ type: "error", text: "Please enter a valid loan amount." });
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.post("loan/apply/", {
        product: prefill?.product,
        amount,
        repayment_months: repaymentMonths,
        purpose,
        purpose_details: purposeDetails,
      });

      setFormMsg({
        type: "success",
        text: `✅ ${res.data.message} | Tier: ${res.data.tier} | Rate: ${res.data.interest_rate}%`,
      });
      setAmount("");
      setPurposeDetails("");
      await refreshUser();
      await fetchEligibility();
    } catch (err) {
      const msg = err.response?.data?.error || "Application failed.";
      setFormMsg({ type: "error", text: msg });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">Loans</h2>
          <p className="section-subtitle">Apply for a loan based on your savings history</p>
          <Link className="ui-button ui-button-secondary" to={ROUTES.loanCalculator}>Loan calculator</Link>

          {/* ── Eligibility panel ── */}
          {loadingElig ? (
            <p style={{ color: "#94a3b8" }}>Checking eligibility...</p>
          ) : eligibility && (
            <div style={{
              background: "#fff", borderRadius: "12px", padding: "24px",
              boxShadow: "var(--shadow)", marginBottom: "24px",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: "700" }}>Loan Eligibility</h3>
                <EligibilityBadge tier={eligibility.tier_label} />
              </div>

              {/* Summary cards */}
              <div className="summary-grid" style={{ marginTop: 0, marginBottom: "20px" }}>
                <div className="summary-card" style={{ borderTopColor: eligibility.eligible ? "var(--success)" : "var(--danger)" }}>
                  <h4>Status</h4>
                  <h2 style={{ fontSize: "18px", color: eligibility.eligible ? "var(--success)" : "var(--danger)" }}>
                    {eligibility.eligible ? "✅ Eligible" : "❌ Not Eligible"}
                  </h2>
                </div>
                <div className="summary-card">
                  <h4>💰 Total Savings</h4>
                  <h2>KES {Number(eligibility.total_savings).toLocaleString()}</h2>
                </div>
                <div className="summary-card">
                  <h4>📅 Consistent Months</h4>
                  <h2>{eligibility.consistent_months}</h2>
                  <p>of last 13 months (min KES {Number(eligibility.min_monthly_amount).toLocaleString()}/mo)</p>
                </div>
                <div className="summary-card" style={{ borderTopColor: eligibility.eligible ? "var(--success)" : "#e2e8f0" }}>
                  <h4>🏦 Max Loan</h4>
                  <h2>KES {Number(eligibility.max_loan).toLocaleString()}</h2>
                  <p>{eligibility.multiplier}× savings {eligibility.tier_label ? `(${eligibility.tier_label})` : ""}</p>
                </div>
              </div>

              {/* Progress to next tier */}
              {eligibility.eligible && eligibility.next_tier_months > 0 && (
                <div style={{ background: "#f8fafc", borderRadius: "8px", padding: "12px 16px", marginBottom: "16px", fontSize: "13px", color: "#475569" }}>
                  💡 Save consistently for <strong>{eligibility.next_tier_months} more month(s)</strong> to unlock a higher tier and better rates.
                </div>
              )}

              {/* Not eligible message */}
              {!eligibility.eligible && eligibility.rejection_reason && (
                <div className="alert alert-warning" style={{ marginBottom: "16px" }}>
                  {eligibility.rejection_reason}
                </div>
              )}

              {/* Savings calendar */}
              <SavingsCalendar months={eligibility.months_detail} />
            </div>
          )}

          {/* ── Application form (only if eligible) ── */}
          {eligibility?.eligible && (
            <div style={{
              background: "#fff", borderRadius: "12px", padding: "24px",
              boxShadow: "var(--shadow)", marginBottom: "24px",
            }}>
              <h3 style={{ margin: "0 0 20px", fontSize: "16px", fontWeight: "700" }}>Apply for a Loan</h3>
              {prefill?.product === "savings_tier" && <p>Loan product: Savings-tier loan</p>}

              {formMsg && (
                <div className={`alert alert-${formMsg.type}`} style={{ marginBottom: "16px" }}>
                  {formMsg.text}
                </div>
              )}

              <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "600px" }}>
                {/* Amount */}
                <div>
                  <label htmlFor="loan-application-amount" style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                    Loan Amount (KES) — max KES {Number(eligibility.max_loan).toLocaleString()}
                  </label>
                  <input
                    id="loan-application-amount"
                    type="number"
                    step="0.01"
                    className="amount-input"
                    style={{ width: "100%" }}
                    placeholder="Enter amount"
                    value={amount}
                    min="1"
                    max={eligibility.max_loan}
                    onChange={(e) => setAmount(e.target.value)}
                    required
                  />
                </div>

                {/* Repayment period */}
                <div>
                  <label htmlFor="loan-application-period" style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                    Repayment Period
                  </label>
                  <select
                    id="loan-application-period"
                    className="amount-input"
                    style={{ width: "100%" }}
                    value={repaymentMonths}
                    onChange={(e) => setRepaymentMonths(Number(e.target.value))}
                  >
                    {periods.map((m) => {
                      const rate = eligibility.interest_rates?.[String(m)]?.[eligibility.interest_band];
                      return (
                        <option key={m} value={m}>
                          {m} Months{rate ? ` — ${rate}% interest (${eligibility.interest_band} tier)` : ""}
                        </option>
                      );
                    })}
                  </select>
                </div>

                {/* Purpose */}
                <div>
                  <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                    Loan Purpose
                  </label>
                  <select
                    className="amount-input"
                    style={{ width: "100%" }}
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                  >
                    {PURPOSES.map(([val, label]) => (
                      <option key={val} value={val}>{label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                    Purpose Details (optional)
                  </label>
                  <textarea
                    className="amount-input"
                    style={{ width: "100%", minHeight: "70px", resize: "vertical" }}
                    placeholder="Briefly describe how you plan to use this loan..."
                    value={purposeDetails}
                    onChange={(e) => setPurposeDetails(e.target.value)}
                  />
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    padding: "13px", border: "none", borderRadius: "10px",
                    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
                    color: "#fff", fontWeight: "700", fontSize: "15px", cursor: "pointer",
                  }}
                >
                  {submitting ? "Submitting..." : "🏦 Submit Loan Application"}
                </button>
              </form>
            </div>
          )}

          {/* ── Interest rate table ── */}
          {eligibility?.eligible && (
            <div style={{
              background: "#fff", borderRadius: "12px", padding: "20px 24px",
              boxShadow: "var(--shadow)", marginBottom: "24px",
            }}>
              <h3 style={{ margin: "0 0 14px", fontSize: "15px", fontWeight: "700" }}>
                Interest Rate Schedule — Your Tier: <EligibilityBadge tier={eligibility.tier_label} />
              </h3>
              <table className="table">
                <thead>
                  <tr>
                    <th>Period</th>
                    <th>🥉 Bronze (6+ mo)</th>
                    <th>🥈 Silver (9+ mo)</th>
                    <th>🥇 Gold (12+ mo)</th>
                  </tr>
                </thead>
                <tbody>
                  {periods.map((m) => {
                    const rates = eligibility.interest_rates?.[String(m)];
                    if (!rates) return null;
                    return (
                      <tr key={m} style={{ background: m === repaymentMonths ? "#eff6ff" : undefined }}>
                        <td><strong>{m} months</strong></td>
                        {["A", "B", "C"].map((band) => (
                          <td key={band} style={{
                            fontWeight: eligibility.interest_band === band ? "700" : "400",
                            color:      eligibility.interest_band === band ? "#2563eb" : "#1e293b",
                          }}>
                            {rates[band]}%
                            {eligibility.interest_band === band && " ← you"}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Loans history ── */}
          <LoanTable loans={loans} onUpdated={async () => { await refreshUser(); await fetchEligibility(); }} />

          {/* ── Guarantor requests I need to respond to ── */}
          <GuarantorRequests />
        </>
      )}
    </Layout>
  );
}

export default Loans;
