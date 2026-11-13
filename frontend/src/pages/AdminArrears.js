import React, { useState, useEffect } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useToast } from "../context/ToastContext";

const BUCKET_COLORS = {
  "1-30 days":  { bg: "#fef9c3", color: "#78350f", border: "#fde68a" },
  "31-60 days": { bg: "#ffedd5", color: "#9a3412", border: "#fed7aa" },
  "61-90 days": { bg: "#fef2f2", color: "#b91c1c", border: "#fca5a5" },
  "90+ days":   { bg: "#fee2e2", color: "#7f1d1d", border: "#f87171" },
};

export default function AdminArrears() {
  const showToast = useToast();
  const [data,     setData]     = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [bucket,   setBucket]   = useState("all");

  useEffect(() => {
    api.get("admin/arrears/")
      .then(r => setData(r.data))
      .catch(() => showToast("Failed to load arrears report.", "error"))
      .finally(() => setLoading(false));
  }, [showToast]);

  const loans = (data?.loans || []).filter(l => bucket === "all" || l.bucket === bucket);

  const fmt = (n) => Number(n).toLocaleString("en-KE", { minimumFractionDigits: 2 });

  return (
    <Layout>
      {() => (
        <div>
          <div style={{ marginBottom: "24px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", fontWeight: "800" }}>⚠️ Arrears & Delinquency</h2>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "13px" }}>
              Active loans with overdue installments — sorted by severity
            </p>
          </div>

          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading arrears report…</p>
          ) : !data ? null : (
            <>
              {/* Summary cards */}
              <div className="summary-grid" style={{ marginBottom: "20px" }}>
                <div className="summary-card" style={{ borderTopColor: "#dc2626" }}>
                  <h4>⚠️ Delinquent Loans</h4>
                  <h2 style={{ color: "#dc2626" }}>{data.total_delinquent_loans}</h2>
                </div>
                <div className="summary-card" style={{ borderTopColor: "#f59e0b" }}>
                  <h4>💰 Total Overdue</h4>
                  <h2>KES {fmt(data.total_overdue_amount)}</h2>
                </div>
                {Object.entries(data.buckets || {}).map(([b, s]) => (
                  <div key={b} className="summary-card" style={{ borderTopColor: BUCKET_COLORS[b]?.color || "#64748b" }}>
                    <h4>{b}</h4>
                    <h2>{s.count} loans</h2>
                    <p>KES {fmt(s.total_overdue)}</p>
                  </div>
                ))}
              </div>

              {/* Bucket filter */}
              <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
                {["all", "1-30 days", "31-60 days", "61-90 days", "90+ days"].map(b => (
                  <button key={b} onClick={() => setBucket(b)} style={{
                    padding: "7px 16px", borderRadius: "20px", border: "1.5px solid",
                    borderColor: bucket === b ? "var(--primary)" : "var(--border)",
                    background: bucket === b ? "var(--primary)" : "#fff",
                    color: bucket === b ? "#fff" : "var(--muted)",
                    fontWeight: "600", fontSize: "13px", cursor: "pointer",
                  }}>{b === "all" ? "All" : b}</button>
                ))}
              </div>

              {/* Table */}
              {loans.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">✅</div>
                  <h3>No overdue loans</h3>
                  <p>All active loans are current.</p>
                </div>
              ) : (
                <div style={{ background: "#fff", borderRadius: "12px", overflow: "hidden", boxShadow: "var(--shadow)" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ background: "linear-gradient(135deg,#1e293b,#334155)" }}>
                          {["Member", "Phone", "Loan Amount", "Balance", "Overdue Amt", "Overdue Installments", "Days Overdue", "Severity"].map(h => (
                            <th key={h} style={{ padding: "12px 14px", textAlign: "left", color: "rgba(255,255,255,.8)", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: ".5px", whiteSpace: "nowrap" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {loans.map(l => {
                          const bc = BUCKET_COLORS[l.bucket] || {};
                          return (
                            <tr key={l.loan_id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                              <td style={{ padding: "12px 14px" }}>
                                <p style={{ margin: 0, fontWeight: "600", fontSize: "13px" }}>{l.member}</p>
                                <p style={{ margin: 0, fontSize: "11px", color: "#64748b" }}>{l.member_number}</p>
                              </td>
                              <td style={{ padding: "12px 14px", fontSize: "13px", fontFamily: "monospace" }}>{l.phone || "—"}</td>
                              <td style={{ padding: "12px 14px", fontSize: "13px" }}>KES {fmt(l.loan_amount)}</td>
                              <td style={{ padding: "12px 14px", fontSize: "13px", fontWeight: "600" }}>KES {fmt(l.outstanding_balance)}</td>
                              <td style={{ padding: "12px 14px", fontSize: "13px", fontWeight: "700", color: "#dc2626" }}>KES {fmt(l.overdue_amount)}</td>
                              <td style={{ padding: "12px 14px", fontSize: "13px", textAlign: "center" }}>{l.overdue_installments}</td>
                              <td style={{ padding: "12px 14px", fontSize: "13px", fontWeight: "700", color: bc.color }}>{l.oldest_overdue_days} days</td>
                              <td style={{ padding: "12px 14px" }}>
                                <span style={{ padding: "3px 10px", borderRadius: "12px", fontSize: "11px", fontWeight: "700", background: bc.bg, color: bc.color, border: `1px solid ${bc.border}`, whiteSpace: "nowrap" }}>
                                  {l.bucket}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Layout>
  );
}
