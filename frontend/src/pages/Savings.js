import React, { useState, useEffect, useCallback } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../context/AuthContext";
import api from "../api/axios";
import "../styles/dashboard.css";

export default function Savings() {
  const { user, refreshUser } = useAuth();

  const [tab,         setTab]         = useState("overview");
  const [msg,         setMsg]         = useState(null);
  const [collateral,  setCollateral]  = useState(null);
  const [statement,   setStatement]   = useState(null);
  const [exitReq,     setExitReq]     = useState(null);

  // Deposit form
  const [depositAmt,      setDepositAmt]      = useState("");
  const [depositAccount,  setDepositAccount]  = useState("bosa");
  const [depositing,      setDepositing]      = useState(false);

  // FOSA Withdrawal form
  const [withdrawAmt,   setWithdrawAmt]   = useState("");
  const [withdrawing,   setWithdrawing]   = useState(false);

  // Exit request form
  const [exitReason,    setExitReason]    = useState("");
  const [submittingExit, setSubmittingExit] = useState(false);

  const fetchCollateral = useCallback(async () => {
    try { const r = await api.get("collateral/status/"); setCollateral(r.data); } catch {}
  }, []);

  const fetchStatement = useCallback(async () => {
    try { const r = await api.get("savings/statement/"); setStatement(r.data); } catch {}
  }, []);

  const fetchExitReq = useCallback(async () => {
    try { const r = await api.get("exit-request/"); setExitReq(r.data.exit_request); } catch {}
  }, []);

  useEffect(() => {
    fetchCollateral();
    fetchExitReq();
  }, [fetchCollateral, fetchExitReq]);

  useEffect(() => {
    if (tab === "statement") fetchStatement();
  }, [tab, fetchStatement]);

  const bosa    = Number(collateral?.bosa_balance   || user?.total_savings || 0);
  const fosa    = Number(collateral?.fosa_balance    || 0);
  const fosaW   = Number(collateral?.fosa_withdrawable || 0);
  const locked  = Number(collateral?.total_locked    || 0);

  // ── Deposit ─────────────────────────────────────────────────────────────
  const handleDeposit = async () => {
    const value = parseFloat(depositAmt);
    if (!value || value <= 0) { setMsg({ type: "error", text: "Enter a valid amount." }); return; }
    setDepositing(true); setMsg(null);
    try {
      await api.post("deposit/", { amount: value, account_type: depositAccount });
      setDepositAmt("");
      await refreshUser();
      await fetchCollateral();
      setMsg({ type: "success", text: `KES ${value.toLocaleString()} deposited to ${depositAccount.toUpperCase()}.` });
    } catch (err) {
      setMsg({ type: "error", text: err.response?.data?.error || "Deposit failed." });
    } finally { setDepositing(false); }
  };

  // ── FOSA Withdraw ────────────────────────────────────────────────────────
  const handleWithdraw = async () => {
    const value = parseFloat(withdrawAmt);
    if (!value || value <= 0) { setMsg({ type: "error", text: "Enter a valid amount." }); return; }
    setWithdrawing(true); setMsg(null);
    try {
      const r = await api.post("withdraw/", { amount: value, account_type: "fosa" });
      setWithdrawAmt("");
      await refreshUser();
      await fetchCollateral();
      setMsg({ type: "success", text: r.data.message });
    } catch (err) {
      setMsg({ type: "error", text: err.response?.data?.error || "Withdrawal failed." });
    } finally { setWithdrawing(false); }
  };

  // ── Submit Exit Request ──────────────────────────────────────────────────
  const handleExitRequest = async () => {
    setSubmittingExit(true); setMsg(null);
    try {
      const r = await api.post("exit-request/", { reason: exitReason });
      setExitReason("");
      await fetchExitReq();
      setMsg({ type: "success", text: r.data.message });
    } catch (err) {
      setMsg({ type: "error", text: err.response?.data?.error || "Failed to submit exit request." });
    } finally { setSubmittingExit(false); }
  };

  const handleCancelExit = async () => {
    if (!exitReq || !window.confirm("Cancel your exit request?")) return;
    try {
      await api.post(`exit-request/${exitReq.id}/cancel/`);
      await fetchExitReq();
      setMsg({ type: "success", text: "Exit request cancelled." });
    } catch { setMsg({ type: "error", text: "Cancel failed." }); }
  };

  const TabBtn = ({ k, label }) => (
    <button onClick={() => setTab(k)} style={{
      padding: "8px 18px", border: "none", borderRadius: "8px", fontSize: "13px",
      fontWeight: "600", cursor: "pointer",
      background: tab === k ? "#fff" : "transparent",
      color:      tab === k ? "#2563eb" : "#64748b",
      boxShadow:  tab === k ? "var(--shadow-sm)" : "none",
    }}>{label}</button>
  );

  const exitStatusColor = { pending: "#f59e0b", approved: "#2563eb", funds_released: "#16a34a", rejected: "#dc2626", cancelled: "#94a3b8" };

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">💰 Savings</h2>
          <p className="section-subtitle">BOSA (Core Shares) + FOSA (Flexible Savings)</p>

          {/* Account summary cards */}
          <div className="summary-grid" style={{ marginBottom: "16px" }}>
            <div style={{ background: "linear-gradient(135deg, #1e3a8a, #2563eb)", borderRadius: "12px", padding: "22px", color: "#fff", boxShadow: "var(--shadow)" }}>
              <p style={{ margin: "0 0 4px", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: ".6px", color: "rgba(255,255,255,.65)" }}>BOSA — Core Shares</p>
              <h2 style={{ margin: "0 0 4px", fontSize: "28px", fontWeight: "800" }}>KES {bosa.toLocaleString()}</h2>
              <p style={{ margin: 0, fontSize: "11px", color: "rgba(255,255,255,.55)" }}>Loan multiplier base · Non-withdrawable · Earns dividends</p>
            </div>
            <div style={{ background: "linear-gradient(135deg, #065f46, #10b981)", borderRadius: "12px", padding: "22px", color: "#fff", boxShadow: "var(--shadow)" }}>
              <p style={{ margin: "0 0 4px", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: ".6px", color: "rgba(255,255,255,.65)" }}>FOSA — Flexible Savings</p>
              <h2 style={{ margin: "0 0 4px", fontSize: "28px", fontWeight: "800" }}>KES {fosa.toLocaleString()}</h2>
              <p style={{ margin: 0, fontSize: "11px", color: "rgba(255,255,255,.55)" }}>Withdrawable anytime · Voluntary deposits · Salary processing</p>
            </div>
            {locked > 0 && (
              <div className="summary-card" style={{ borderTopColor: "#f59e0b" }}>
                <h4>🔒 Total Locked</h4>
                <h2>KES {locked.toLocaleString()}</h2>
                <p>As loan collateral</p>
              </div>
            )}
            <div className="summary-card" style={{ borderTopColor: "#16a34a" }}>
              <h4>✅ FOSA Withdrawable</h4>
              <h2>KES {fosaW.toLocaleString()}</h2>
              <p>Available to withdraw now</p>
            </div>
          </div>

          {/* Collateral breakdown */}
          {collateral && collateral.total_locked > 0 && (
            <div style={{ background: "#fff", borderRadius: "12px", padding: "18px 22px", boxShadow: "var(--shadow)", marginBottom: "20px", borderLeft: "4px solid #f59e0b" }}>
              <p style={{ margin: "0 0 10px", fontWeight: "700", fontSize: "14px" }}>🔒 Locked Balance Breakdown</p>
              <div style={{ display: "flex", gap: "24px", flexWrap: "wrap", fontSize: "13px" }}>
                {collateral.locked_own_loans > 0 && <span>Own loan collateral: <strong>KES {Number(collateral.locked_own_loans).toLocaleString()}</strong></span>}
                {collateral.locked_guarantor > 0 && <span>Guarantor pledges: <strong>KES {Number(collateral.locked_guarantor).toLocaleString()}</strong></span>}
              </div>
              {collateral.pledges_detail?.filter(p => p.is_active && p.locked > 0).map((p, i) => (
                <p key={i} style={{ margin: "6px 0 0", fontSize: "12px", color: "#64748b" }}>
                  Guaranteeing {p.borrower} (Loan #{p.loan_id}): KES {Number(p.locked).toLocaleString()} locked · KES {Number(p.released).toLocaleString()} released
                </p>
              ))}
            </div>
          )}

          {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

          {/* Tab bar */}
          <div style={{ display: "flex", gap: "4px", marginBottom: "20px", background: "#f1f5f9", borderRadius: "10px", padding: "4px", width: "fit-content" }}>
            <TabBtn k="overview"   label="💳 Deposit & Withdraw" />
            <TabBtn k="statement"  label="📄 Statement" />
            <TabBtn k="exit"       label="🚪 Exit SACCO" />
          </div>

          {/* ── OVERVIEW TAB ── */}
          {tab === "overview" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>

              {/* Deposit */}
              <div style={{ background: "#fff", borderRadius: "12px", padding: "22px", boxShadow: "var(--shadow)" }}>
                <h3 style={{ margin: "0 0 16px", fontSize: "15px", fontWeight: "700" }}>📥 Make a Deposit</h3>
                <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", textTransform: "uppercase", marginBottom: "5px" }}>
                  Account Type
                </label>
                <div style={{ display: "flex", gap: "8px", marginBottom: "14px" }}>
                  {[["bosa","BOSA (Core Shares)"],["fosa","FOSA (Flexible)"]].map(([k,l]) => (
                    <button key={k} onClick={() => setDepositAccount(k)} style={{
                      flex: 1, padding: "10px", border: `2px solid ${depositAccount === k ? "#2563eb" : "#e2e8f0"}`,
                      borderRadius: "8px", background: depositAccount === k ? "#eff6ff" : "#f8fafc",
                      color: depositAccount === k ? "#2563eb" : "#64748b", fontWeight: "700",
                      fontSize: "13px", cursor: "pointer",
                    }}>{l}</button>
                  ))}
                </div>
                {depositAccount === "bosa" && (
                  <div style={{ background: "#eff6ff", borderRadius: "8px", padding: "10px 14px", marginBottom: "12px", fontSize: "12px", color: "#1e40af" }}>
                    💡 Mandatory minimum: KES 1,000/month. BOSA earns annual dividends and is your loan collateral base.
                  </div>
                )}
                <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", textTransform: "uppercase", marginBottom: "5px" }}>Amount (KES)</label>
                <input
                  type="number" className="amount-input" style={{ width: "100%", marginBottom: "12px" }}
                  placeholder="e.g. 2,000" value={depositAmt} min="1"
                  onChange={e => setDepositAmt(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleDeposit()}
                />
                <button onClick={handleDeposit} disabled={depositing} style={{ width: "100%", padding: "11px", border: "none", borderRadius: "8px", background: "#2563eb", color: "#fff", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
                  {depositing ? "Processing..." : `💰 Deposit to ${depositAccount.toUpperCase()}`}
                </button>
              </div>

              {/* FOSA Withdraw */}
              <div style={{ background: "#fff", borderRadius: "12px", padding: "22px", boxShadow: "var(--shadow)" }}>
                <h3 style={{ margin: "0 0 4px", fontSize: "15px", fontWeight: "700" }}>📤 FOSA Withdrawal</h3>
                <p style={{ margin: "0 0 14px", fontSize: "12px", color: "#64748b" }}>Withdraw from your flexible FOSA account anytime.</p>

                <div style={{ background: "#f0fdf4", borderRadius: "8px", padding: "10px 14px", marginBottom: "12px", fontSize: "12px", color: "#15803d" }}>
                  Available: <strong>KES {fosaW.toLocaleString()}</strong> of KES {fosa.toLocaleString()} FOSA balance
                </div>

                {fosa <= 0 ? (
                  <p style={{ color: "#94a3b8", fontSize: "13px" }}>No FOSA balance to withdraw.</p>
                ) : (
                  <>
                    <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", textTransform: "uppercase", marginBottom: "5px" }}>Amount (KES)</label>
                    <input
                      type="number" className="amount-input" style={{ width: "100%", marginBottom: "6px" }}
                      placeholder={`Max KES ${fosaW.toLocaleString()}`} value={withdrawAmt}
                      min="1" max={fosaW} onChange={e => setWithdrawAmt(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && handleWithdraw()}
                    />
                    <button onClick={handleWithdraw} disabled={withdrawing} style={{ width: "100%", padding: "11px", border: "none", borderRadius: "8px", background: "#10b981", color: "#fff", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
                      {withdrawing ? "Processing..." : "📤 Withdraw FOSA"}
                    </button>
                  </>
                )}

                <div style={{ marginTop: "16px", padding: "12px", background: "#fef2f2", borderRadius: "8px", fontSize: "12px", color: "#991b1b", borderLeft: "3px solid #fca5a5" }}>
                  🔒 <strong>BOSA is non-withdrawable</strong> while you are an active member. To access BOSA funds, submit an Exit Request.
                </div>
              </div>
            </div>
          )}

          {/* ── STATEMENT TAB ── */}
          {tab === "statement" && (
            <div style={{ background: "#fff", borderRadius: "12px", boxShadow: "var(--shadow)" }}>
              {!statement ? (
                <p style={{ padding: "20px", color: "#94a3b8" }}>Loading statement...</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr><th>Date</th><th>Account</th><th>Type</th><th>Amount</th><th>Balance</th></tr>
                  </thead>
                  <tbody>
                    {(statement.entries || []).length === 0 ? (
                      <tr><td colSpan="5" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>No transactions yet.</td></tr>
                    ) : (statement.entries || []).map((e, i) => (
                      <tr key={i}>
                        <td style={{ fontSize: "13px" }}>{new Date(e.created_at).toLocaleDateString("en-KE")}</td>
                        <td><span style={{ padding: "2px 8px", borderRadius: "12px", fontSize: "11px", fontWeight: "700", background: e.account_type === "bosa" ? "#dbeafe" : "#dcfce7", color: e.account_type === "bosa" ? "#1e40af" : "#15803d" }}>{(e.account_type || "fosa").toUpperCase()}</span></td>
                        <td><span className={`status status-${e.type === "Deposit" ? "approved" : "pending"}`}>{e.type}</span></td>
                        <td style={{ fontWeight: "600", color: e.type === "Deposit" ? "#15803d" : "#b45309" }}>
                          {e.type === "Deposit" ? "+" : "−"} KES {Number(e.amount).toLocaleString()}
                        </td>
                        <td style={{ fontWeight: "700" }}>KES {Number(e.balance).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* ── EXIT TAB ── */}
          {tab === "exit" && (
            <div style={{ maxWidth: "600px" }}>
              <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: "12px", padding: "18px 22px", marginBottom: "20px" }}>
                <h3 style={{ margin: "0 0 8px", fontSize: "15px", fontWeight: "700", color: "#9a3412" }}>⚠️ BOSA Withdrawal — Exit Process</h3>
                <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "13px", color: "#7c2d12", lineHeight: "1.7" }}>
                  <li>BOSA savings are <strong>non-withdrawable</strong> while you are an active SACCO member.</li>
                  <li>To withdraw BOSA funds, you must formally <strong>resign from the SACCO</strong>.</li>
                  <li>A <strong>60-day holding period</strong> applies after approval (SASRA requirement).</li>
                  <li>You <strong>cannot exit</strong> if you have an active unpaid loan or are guaranteeing another member's loan.</li>
                  <li>Current BOSA balance: <strong>KES {bosa.toLocaleString()}</strong></li>
                </ul>
              </div>

              {exitReq ? (
                <div style={{ background: "#fff", borderRadius: "12px", padding: "22px", boxShadow: "var(--shadow)" }}>
                  <h3 style={{ margin: "0 0 14px", fontSize: "15px", fontWeight: "700" }}>Your Exit Request</h3>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "14px" }}>
                    {[
                      ["Status",        <span style={{ padding: "3px 12px", borderRadius: "20px", fontSize: "13px", fontWeight: "700", background: exitStatusColor[exitReq.status] + "22", color: exitStatusColor[exitReq.status] }}>{exitReq.status_label}</span>],
                      ["BOSA at Request", `KES ${Number(exitReq.bosa_balance).toLocaleString()}`],
                      ["Submitted",     new Date(exitReq.created_at).toLocaleDateString("en-KE")],
                      ["Release Date",  exitReq.release_date ? new Date(exitReq.release_date).toLocaleDateString("en-KE") : "Pending approval"],
                    ].map(([k, v]) => (
                      <div key={k} style={{ background: "#f8fafc", borderRadius: "8px", padding: "10px 12px" }}>
                        <div style={{ fontSize: "11px", color: "#94a3b8", fontWeight: "600", textTransform: "uppercase", marginBottom: "4px" }}>{k}</div>
                        <div style={{ fontWeight: "700", fontSize: "14px" }}>{v}</div>
                      </div>
                    ))}
                  </div>

                  {exitReq.status === "approved" && !exitReq.is_holding_period_over && (
                    <div style={{ background: "#eff6ff", borderRadius: "8px", padding: "12px 14px", marginBottom: "14px", fontSize: "13px", color: "#1e40af" }}>
                      ⏳ Your exit is approved. Funds will be available on <strong>{new Date(exitReq.release_date).toLocaleDateString("en-KE")}</strong>.
                    </div>
                  )}

                  {exitReq.status === "approved" && exitReq.is_holding_period_over && (
                    <div style={{ background: "#f0fdf4", borderRadius: "8px", padding: "12px 14px", marginBottom: "14px", fontSize: "13px", color: "#15803d" }}>
                      ✅ Holding period complete. You can now withdraw your BOSA balance from the Deposit &amp; Withdraw tab.
                    </div>
                  )}

                  {exitReq.rejection_reason && (
                    <div style={{ background: "#fef2f2", borderRadius: "8px", padding: "12px 14px", marginBottom: "14px", fontSize: "13px", color: "#991b1b" }}>
                      ❌ Rejection reason: {exitReq.rejection_reason}
                    </div>
                  )}

                  {["pending", "approved"].includes(exitReq.status) && (
                    <button onClick={handleCancelExit} style={{ padding: "9px 20px", background: "#fee2e2", color: "#b91c1c", border: "none", borderRadius: "8px", fontWeight: "600", fontSize: "13px", cursor: "pointer" }}>
                      Cancel Exit Request
                    </button>
                  )}
                </div>
              ) : (
                <div style={{ background: "#fff", borderRadius: "12px", padding: "22px", boxShadow: "var(--shadow)" }}>
                  <h3 style={{ margin: "0 0 14px", fontSize: "15px", fontWeight: "700" }}>Submit Exit Request</h3>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", textTransform: "uppercase", marginBottom: "5px" }}>
                    Reason for Leaving (optional)
                  </label>
                  <textarea
                    className="amount-input"
                    style={{ width: "100%", minHeight: "80px", resize: "vertical", marginBottom: "14px" }}
                    placeholder="e.g. Relocating abroad, Financial reasons..."
                    value={exitReason}
                    onChange={e => setExitReason(e.target.value)}
                  />
                  <button onClick={handleExitRequest} disabled={submittingExit} style={{ padding: "11px 24px", background: "#dc2626", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
                    {submittingExit ? "Submitting..." : "🚪 Submit Exit Request"}
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
