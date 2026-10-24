import React, { useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

const STATUS_STYLE = {
  pending:        { bg: "#fef3c7", color: "#b45309", label: "Pending" },
  approved:       { bg: "#dbeafe", color: "#1e40af", label: "Approved" },
  funds_released: { bg: "#dcfce7", color: "#15803d", label: "Funds Released" },
  rejected:       { bg: "#fee2e2", color: "#b91c1c", label: "Rejected" },
  cancelled:      { bg: "#f1f5f9", color: "#64748b", label: "Cancelled" },
};

export default function AdminExitRequests() {
  const [requests, setRequests]   = useState([]);
  const [loading,  setLoading]    = useState(true);
  const [filter,   setFilter]     = useState("pending");
  const [modal,    setModal]      = useState(null);   // { type, request }
  const [notes,    setNotes]      = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [actioning, setActioning] = useState(false);
  const [msg,      setMsg]        = useState(null);

  useEffect(() => { fetchRequests(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const res = await api.get(`admin/exit-requests/?status=${filter}`);
      setRequests(res.data);
    } catch { setMsg({ type: "error", text: "Failed to load exit requests." }); }
    finally { setLoading(false); }
  };

  const handleAction = async () => {
    if (!modal) return;
    setActioning(true);
    try {
      const payload = {
        action:           modal.type,
        notes:            notes,
        rejection_reason: rejectReason,
      };
      const res = await api.post(`admin/exit-requests/${modal.request.id}/review/`, payload);
      setMsg({ type: "success", text: res.data.message });
      setModal(null); setNotes(""); setRejectReason("");
      fetchRequests();
    } catch (err) {
      setMsg({ type: "error", text: err.response?.data?.error || "Action failed." });
    } finally { setActioning(false); }
  };

  const counts = { pending: 0, approved: 0, funds_released: 0, rejected: 0 };
  requests.forEach(r => { if (counts[r.status] !== undefined) counts[r.status]++; });

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">🚪 Exit Requests</h2>
          <p className="section-subtitle">Members requesting to leave the SACCO and withdraw BOSA funds</p>

          <div className="summary-grid" style={{ marginBottom: "20px" }}>
            {[
              ["⏳ Pending",        counts.pending,        "#f59e0b", "pending"],
              ["✅ Approved",       counts.approved,       "#2563eb", "approved"],
              ["💰 Funds Released", counts.funds_released, "#16a34a", "funds_released"],
              ["❌ Rejected",       counts.rejected,       "#dc2626", "rejected"],
            ].map(([label, count, color, key]) => (
              <div key={key} className="summary-card" style={{ borderTopColor: color, cursor: "pointer" }} onClick={() => setFilter(key)}>
                <h4>{label}</h4><h2 style={{ color }}>{count}</h2>
              </div>
            ))}
          </div>

          {/* Filter */}
          <div style={{ display: "flex", gap: "6px", marginBottom: "16px", flexWrap: "wrap" }}>
            {["all","pending","approved","funds_released","rejected","cancelled"].map(s => (
              <button key={s} onClick={() => setFilter(s)} style={{
                padding: "6px 14px", borderRadius: "20px", border: "1.5px solid",
                borderColor: filter === s ? "#2563eb" : "#e2e8f0",
                background:  filter === s ? "#eff6ff" : "#fff",
                color:       filter === s ? "#2563eb" : "#64748b",
                fontWeight: "600", fontSize: "13px", cursor: "pointer",
                textTransform: "capitalize",
              }}>{s.replace("_", " ")}</button>
            ))}
          </div>

          {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}
          {loading && <p style={{ color: "#94a3b8" }}>Loading...</p>}

          {!loading && (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th><th>Member</th><th>BOSA Balance</th><th>Active Loan</th>
                    <th>Active Pledge</th><th>Status</th><th>Release Date</th>
                    <th>Submitted</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.length === 0 ? (
                    <tr><td colSpan="9" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>No exit requests found.</td></tr>
                  ) : requests.map(r => {
                    const sc = STATUS_STYLE[r.status] || {};
                    return (
                      <tr key={r.id}>
                        <td>#{r.id}</td>
                        <td>
                          <div style={{ fontWeight: "600" }}>{r.member}</div>
                          <div style={{ fontSize: "11px", color: "#94a3b8" }}>{r.member_number}</div>
                        </td>
                        <td style={{ fontWeight: "700", color: "#1e3a8a" }}>KES {Number(r.bosa_balance).toLocaleString()}</td>
                        <td>{r.has_active_loan ? <span style={{ color: "#dc2626", fontWeight: "700" }}>⚠️ Yes</span> : <span style={{ color: "#16a34a" }}>✅ No</span>}</td>
                        <td>{r.has_guarantor_pledges ? <span style={{ color: "#dc2626", fontWeight: "700" }}>⚠️ Yes</span> : <span style={{ color: "#16a34a" }}>✅ No</span>}</td>
                        <td><span style={{ padding: "3px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: "700", background: sc.bg, color: sc.color }}>{sc.label}</span></td>
                        <td style={{ fontSize: "12px" }}>{r.release_date ? new Date(r.release_date).toLocaleDateString("en-KE") : "—"}{r.is_holding_period_over && r.status === "approved" && <span style={{ color: "#16a34a", marginLeft: "4px" }}>✅ Ready</span>}</td>
                        <td style={{ fontSize: "12px" }}>{new Date(r.created_at).toLocaleDateString("en-KE")}</td>
                        <td>
                          {r.status === "pending" && !r.has_active_loan && !r.has_guarantor_pledges && (
                            <div style={{ display: "flex", gap: "6px" }}>
                              <button onClick={() => { setModal({ type: "approve", request: r }); setNotes(""); setRejectReason(""); }} style={{ padding: "5px 10px", background: "#dcfce7", color: "#15803d", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}>✅ Approve</button>
                              <button onClick={() => { setModal({ type: "reject", request: r }); setNotes(""); setRejectReason(""); }} style={{ padding: "5px 10px", background: "#fee2e2", color: "#b91c1c", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}>❌ Reject</button>
                            </div>
                          )}
                          {r.status === "pending" && (r.has_active_loan || r.has_guarantor_pledges) && (
                            <span style={{ fontSize: "12px", color: "#b45309" }}>Must clear {r.has_active_loan ? "loan" : "guarantees"} first</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Review modal */}
          {modal && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 }}>
              <div style={{ background: "#fff", padding: "28px", borderRadius: "14px", width: "440px", boxShadow: "var(--shadow-lg)" }}>
                <h3 style={{ margin: "0 0 8px" }}>
                  {modal.type === "approve" ? "✅ Approve Exit Request" : "❌ Reject Exit Request"}
                </h3>
                <p style={{ margin: "0 0 16px", fontSize: "14px", color: "#64748b" }}>
                  {modal.request.member} — BOSA: KES {Number(modal.request.bosa_balance).toLocaleString()}
                </p>
                {modal.type === "approve" && (
                  <div style={{ background: "#eff6ff", borderRadius: "8px", padding: "12px 14px", marginBottom: "14px", fontSize: "13px", color: "#1e40af" }}>
                    Approving will start the <strong>{60}-day holding period</strong>. Member can withdraw BOSA after the release date.
                  </div>
                )}
                <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", marginBottom: "5px" }}>
                  {modal.type === "approve" ? "Approval Note (optional)" : "Rejection Reason *"}
                </label>
                {modal.type === "reject" && (
                  <textarea
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                    placeholder="e.g. Member has outstanding obligations..."
                    style={{ width: "100%", minHeight: "70px", padding: "10px", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "14px", resize: "vertical", boxSizing: "border-box", marginBottom: "10px" }}
                    required
                  />
                )}
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder="Internal notes..."
                  style={{ width: "100%", minHeight: "60px", padding: "10px", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "14px", resize: "vertical", boxSizing: "border-box" }}
                />
                <div style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
                  <button
                    onClick={handleAction}
                    disabled={actioning || (modal.type === "reject" && !rejectReason.trim())}
                    style={{ flex: 1, padding: "12px", border: "none", borderRadius: "8px", background: modal.type === "approve" ? "#16a34a" : "#dc2626", color: "#fff", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}
                  >
                    {actioning ? "Processing..." : `Confirm ${modal.type === "approve" ? "Approval" : "Rejection"}`}
                  </button>
                  <button onClick={() => setModal(null)} style={{ padding: "12px 20px", border: "1.5px solid #e2e8f0", borderRadius: "8px", background: "#f8fafc", fontWeight: "600", cursor: "pointer" }}>Cancel</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
