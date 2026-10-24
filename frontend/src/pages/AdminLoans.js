import React, { useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

function AdminLoans() {
  const [loans,    setLoans]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [filter,   setFilter]   = useState("pending");

  // Remarks modal state
  const [modal,    setModal]    = useState(null);   // { type: "approve"|"reject", loan }
  const [remarks,  setRemarks]  = useState("");
  const [actioning,setActioning]= useState(false);

  useEffect(() => { fetchLoans(); }, []);

  const fetchLoans = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("admin/loans/");
      setLoans(res.data);
    } catch {
      setError("Failed to load loans.");
    } finally {
      setLoading(false);
    }
  };

  const openModal = (type, loan) => {
    setModal({ type, loan });
    setRemarks("");
  };

  const closeModal = () => { setModal(null); setRemarks(""); };

  const handleAction = async () => {
    if (!modal) return;
    setActioning(true);
    try {
      const url = modal.type === "approve"
        ? `admin/loan/${modal.loan.id}/approve/`
        : `admin/loan/${modal.loan.id}/reject/`;

      await api.post(url, { remarks });
      closeModal();
      fetchLoans();
    } catch (err) {
      alert(err.response?.data?.error || "Action failed.");
    } finally {
      setActioning(false);
    }
  };

  const tierBadge = (months) => {
    const color = months >= 12 ? "#fef3c7:#92400e:#fcd34d" :
                  months >= 9  ? "#f1f5f9:#475569:#94a3b8" :
                  months >= 6  ? "#fef3c7:#b45309:#fcd34d" :
                                 "#fee2e2:#b91c1c:#fecaca";
    const [bg, fg, bd] = color.split(":");
    const label = months >= 12 ? "🥇 Gold" : months >= 9 ? "🥈 Silver" : months >= 6 ? "🥉 Bronze" : "❌ Ineligible";
    return (
      <span style={{ padding: "3px 10px", borderRadius: "20px", fontSize: "11px", fontWeight: "700", background: bg, color: fg, border: `1px solid ${bd}` }}>
        {label} ({months}mo)
      </span>
    );
  };

  const filtered = filter === "all" ? loans : loans.filter((l) => l.status === filter);

  const counts = {
    pending:  loans.filter((l) => l.status === "pending").length,
    approved: loans.filter((l) => l.status === "approved").length,
    repaid:   loans.filter((l) => l.status === "repaid").length,
    rejected: loans.filter((l) => l.status === "rejected").length,
  };

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">Loan Management</h2>
          <p className="section-subtitle">Review and action member loan applications</p>

          {/* Summary */}
          <div className="summary-grid" style={{ marginBottom: "20px" }}>
            {[
              ["⏳ Pending",  counts.pending,  "#f59e0b", "pending"],
              ["✅ Approved", counts.approved, "#16a34a", "approved"],
              ["🔄 Repaid",   counts.repaid,   "#2563eb", "repaid"],
              ["❌ Rejected", counts.rejected, "#dc2626", "rejected"],
            ].map(([label, count, color, key]) => (
              <div
                key={key}
                className="summary-card"
                style={{ borderTopColor: color, cursor: "pointer" }}
                onClick={() => setFilter(key)}
              >
                <h4>{label}</h4>
                <h2 style={{ color }}>{count}</h2>
                <p style={{ fontSize: "11px" }}>Click to filter</p>
              </div>
            ))}
          </div>

          {/* Filter bar */}
          <div style={{ marginBottom: "16px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {["all","pending","approved","repaid","rejected"].map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                style={{
                  padding: "6px 16px", borderRadius: "20px", border: "1.5px solid",
                  borderColor: filter === s ? "#2563eb" : "#e2e8f0",
                  background:  filter === s ? "#eff6ff"  : "#fff",
                  color:       filter === s ? "#2563eb"  : "#64748b",
                  fontWeight: "600", fontSize: "13px", cursor: "pointer",
                  textTransform: "capitalize",
                }}
              >
                {s} {s !== "all" && `(${counts[s] ?? 0})`}
              </button>
            ))}
          </div>

          {error  && <div className="alert alert-error">{error} <button onClick={fetchLoans}>Retry</button></div>}
          {loading && <p style={{ color: "#94a3b8" }}>Loading loans...</p>}

          {!loading && (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Member</th>
                    <th>Amount</th>
                    <th>Purpose</th>
                    <th>Period</th>
                    <th>Rate</th>
                    <th>Savings @ Apply</th>
                    <th>Saving Tier</th>
                    <th>Status</th>
                    <th>Remarks</th>
                    <th>Date</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan="12" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>
                        No {filter === "all" ? "" : filter} loans found.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((loan) => (
                      <tr key={loan.id}>
                        <td style={{ fontWeight: "600" }}>#{loan.id}</td>
                        <td>
                          <div style={{ fontWeight: "600" }}>{loan.member}</div>
                          <div style={{ fontSize: "11px", color: "#94a3b8" }}>{loan.member_number}</div>
                        </td>
                        <td>KES {Number(loan.amount).toLocaleString()}</td>
                        <td style={{ textTransform: "capitalize" }}>
                          {loan.purpose}
                          {loan.purpose_details && (
                            <div style={{ fontSize: "11px", color: "#94a3b8" }} title={loan.purpose_details}>
                              {loan.purpose_details.slice(0, 40)}{loan.purpose_details.length > 40 ? "…" : ""}
                            </div>
                          )}
                        </td>
                        <td>{loan.repayment_months} mo.</td>
                        <td>{loan.interest}%</td>
                        <td>KES {Number(loan.total_savings_at_application).toLocaleString()}</td>
                        <td>{tierBadge(loan.savings_months)}</td>
                        <td>
                          <span className={`status status-${loan.status}`}>{loan.status}</span>
                        </td>
                        <td style={{ fontSize: "12px", color: "#64748b", maxWidth: "160px" }}>
                          {loan.remarks || "—"}
                        </td>
                        <td style={{ fontSize: "12px" }}>
                          {new Date(loan.created_at).toLocaleDateString()}
                        </td>
                        <td>
                          {loan.status === "pending" ? (
                            <div className="loan-actions">
                              <button className="approve-btn" onClick={() => openModal("approve", loan)}>
                                ✅ Approve
                              </button>
                              <button className="reject-btn" onClick={() => openModal("reject", loan)}>
                                ❌ Reject
                              </button>
                            </div>
                          ) : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Action modal ── */}
          {modal && (
            <div style={{
              position: "fixed", inset: 0, background: "rgba(0,0,0,.5)",
              display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000,
            }}>
              <div style={{
                background: "#fff", padding: "28px", borderRadius: "14px",
                width: "440px", boxShadow: "var(--shadow-lg)",
              }}>
                <h3 style={{ margin: "0 0 6px" }}>
                  {modal.type === "approve" ? "✅ Approve Loan" : "❌ Reject Loan"}
                </h3>
                <p style={{ margin: "0 0 16px", fontSize: "14px", color: "#64748b" }}>
                  {modal.loan.member} — KES {Number(modal.loan.amount).toLocaleString()} / {modal.loan.repayment_months} months
                </p>

                {/* Eligibility summary in modal */}
                <div style={{ background: "#f8fafc", borderRadius: "8px", padding: "12px 14px", marginBottom: "16px", fontSize: "13px" }}>
                  <div>Savings at application: <strong>KES {Number(modal.loan.total_savings_at_application).toLocaleString()}</strong></div>
                  <div>Saving tier: {tierBadge(modal.loan.savings_months)}</div>
                  <div>Purpose: <strong style={{ textTransform: "capitalize" }}>{modal.loan.purpose}</strong>
                    {modal.loan.purpose_details ? ` — ${modal.loan.purpose_details}` : ""}
                  </div>
                </div>

                <label style={{ display: "block", fontSize: "13px", fontWeight: "600", color: "#475569", marginBottom: "6px" }}>
                  {modal.type === "approve" ? "Approval Note (optional)" : "Rejection Reason (required)"}
                </label>
                <textarea
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                  placeholder={
                    modal.type === "approve"
                      ? "e.g. Approved — member has excellent savings record"
                      : "e.g. Insufficient savings history, please save for 6+ months"
                  }
                  style={{
                    width: "100%", minHeight: "80px", padding: "10px 12px",
                    border: "1.5px solid #e2e8f0", borderRadius: "8px",
                    fontSize: "14px", resize: "vertical", boxSizing: "border-box",
                  }}
                  required={modal.type === "reject"}
                />

                <div style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
                  <button
                    onClick={handleAction}
                    disabled={actioning || (modal.type === "reject" && !remarks.trim())}
                    style={{
                      flex: 1, padding: "12px", border: "none", borderRadius: "8px",
                      background: modal.type === "approve" ? "#16a34a" : "#dc2626",
                      color: "#fff", fontWeight: "700", fontSize: "14px", cursor: "pointer",
                    }}
                  >
                    {actioning ? "Processing..." : modal.type === "approve" ? "Confirm Approve" : "Confirm Reject"}
                  </button>
                  <button
                    onClick={closeModal}
                    style={{
                      padding: "12px 20px", border: "1.5px solid #e2e8f0", borderRadius: "8px",
                      background: "#f8fafc", fontWeight: "600", fontSize: "14px", cursor: "pointer",
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </Layout>
  );
}

export default AdminLoans;
