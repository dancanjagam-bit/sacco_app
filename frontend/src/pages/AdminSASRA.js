import React, { useState, useEffect, useCallback } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useToast } from "../context/ToastContext";

const STATUS_COLOR = {
  draft:     { bg: "#f1f5f9", text: "#475569" },
  generated: { bg: "#eff6ff", text: "#1d4ed8" },
  submitted: { bg: "#f0fdf4", text: "#15803d" },
};

const REPORT_TYPES = [
  { value: "quarterly", label: "Quarterly (Last 3 months)" },
  { value: "annual",    label: "Annual (Last 12 months)" },
  { value: "monthly",   label: "Monthly (Last 30 days)" },
  { value: "special",   label: "Special (Custom date range)" },
];

function fmt(n) {
  return Number(n || 0).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function AdminSASRA() {
  const showToast = useToast();
  const [reports,     setReports]     = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [generating,  setGenerating]  = useState(false);
  const [submitting,  setSubmitting]  = useState(null);
  const [expanded,    setExpanded]    = useState(null);

  // Generate form
  const [reportType,  setReportType]  = useState("quarterly");
  const [dateFrom,    setDateFrom]    = useState("");
  const [dateTo,      setDateTo]      = useState("");

  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("admin/sasra/");
      setReports(res.data);
    } catch {
      showToast("Failed to load SASRA reports.", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const generate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    try {
      const payload = { report_type: reportType };
      if (reportType === "special") {
        if (!dateFrom || !dateTo) {
          showToast("Please select both a start and end date for a special report.", "error");
          setGenerating(false);
          return;
        }
        payload.period_start = dateFrom;
        payload.period_end   = dateTo;
      }
      const res = await api.post("admin/sasra/", payload);
      showToast(`${res.data.report_type} SASRA report generated.`, "success");
      fetchReports();
      setExpanded(res.data.id);
    } catch (err) {
      showToast(err.response?.data?.error || "Report generation failed.", "error");
    } finally {
      setGenerating(false);
    }
  };

  const submit = async (id) => {
    setSubmitting(id);
    try {
      await api.post(`admin/sasra/${id}/submit/`);
      showToast("Report marked as submitted to SASRA.", "success");
      setReports(prev => prev.map(r => r.id === id ? { ...r, status: "submitted" } : r));
    } catch (err) {
      showToast(err.response?.data?.error || "Submit failed.", "error");
    } finally {
      setSubmitting(null);
    }
  };

  const StatusBadge = ({ status }) => {
    const s = STATUS_COLOR[status] || STATUS_COLOR.draft;
    return (
      <span style={{
        padding: "3px 10px", borderRadius: "12px",
        fontSize: "11px", fontWeight: "700",
        background: s.bg, color: s.text,
        textTransform: "capitalize",
      }}>
        {status}
      </span>
    );
  };

  return (
    <Layout>
      {() => (
        <div>
          <div style={{ marginBottom: "24px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", fontWeight: "800" }}>📋 SASRA Compliance Reports</h2>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "13px" }}>
              Generate and submit regulatory compliance reports to the Sacco Societies Regulatory Authority
            </p>
          </div>

          {/* Generate form */}
          <div style={{ background: "#fff", borderRadius: "12px", padding: "24px", boxShadow: "var(--shadow)", marginBottom: "24px", maxWidth: "680px" }}>
            <h3 style={{ margin: "0 0 16px", fontSize: "15px", fontWeight: "700" }}>📊 Generate New Report</h3>
            <form onSubmit={generate} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" }}>
                  Report Type
                </label>
                <select
                  value={reportType}
                  onChange={e => setReportType(e.target.value)}
                  style={{ width: "100%", padding: "10px 14px", borderRadius: "8px", border: "1.5px solid #e2e8f0", fontSize: "14px", background: "#f8fafc" }}
                >
                  {REPORT_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>

              {reportType === "special" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" }}>
                      From
                    </label>
                    <input
                      type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                      style={{ width: "100%", padding: "10px 14px", borderRadius: "8px", border: "1.5px solid #e2e8f0", fontSize: "14px", background: "#f8fafc", boxSizing: "border-box" }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: "5px" }}>
                      To
                    </label>
                    <input
                      type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                      style={{ width: "100%", padding: "10px 14px", borderRadius: "8px", border: "1.5px solid #e2e8f0", fontSize: "14px", background: "#f8fafc", boxSizing: "border-box" }}
                    />
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={generating}
                style={{ padding: "11px 20px", background: generating ? "#94a3b8" : "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: generating ? "not-allowed" : "pointer", alignSelf: "flex-start" }}
              >
                {generating ? "Generating…" : "⚡ Generate Report"}
              </button>
            </form>
          </div>

          {/* Reports list */}
          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading reports…</p>
          ) : reports.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📋</div>
              <h3>No SASRA reports yet</h3>
              <p>Use the form above to generate your first compliance report.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {reports.map(r => (
                <div key={r.id} style={{ background: "#fff", borderRadius: "12px", border: "1px solid var(--border-light)", boxShadow: "var(--shadow-sm)", overflow: "hidden" }}>
                  {/* Header row */}
                  <div
                    style={{ display: "flex", alignItems: "center", gap: "16px", padding: "16px 20px", cursor: "pointer" }}
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                        <span style={{ fontWeight: "700", fontSize: "14px", textTransform: "capitalize" }}>
                          {r.report_type} Report
                        </span>
                        <StatusBadge status={r.status} />
                      </div>
                      <div style={{ fontSize: "12px", color: "#64748b", marginTop: "3px" }}>
                        Period: {r.period_start} → {r.period_end} · Generated by {r.generated_by} · {new Date(r.created_at).toLocaleDateString("en-KE")}
                        {r.submitted_at && ` · Submitted ${new Date(r.submitted_at).toLocaleDateString("en-KE")}`}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
                      {r.status !== "submitted" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); submit(r.id); }}
                          disabled={submitting === r.id}
                          style={{ padding: "6px 14px", borderRadius: "8px", border: "none", background: "#059669", color: "#fff", fontWeight: "600", fontSize: "12px", cursor: "pointer" }}
                        >
                          {submitting === r.id ? "…" : "✅ Mark Submitted"}
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); setExpanded(expanded === r.id ? null : r.id); }}
                        style={{ padding: "6px 14px", borderRadius: "8px", border: "1.5px solid var(--border)", background: "#fff", color: "#475569", fontWeight: "600", fontSize: "12px", cursor: "pointer" }}
                      >
                        {expanded === r.id ? "▲ Hide" : "▼ Details"}
                      </button>
                    </div>
                  </div>

                  {/* Expandable snapshot */}
                  {expanded === r.id && r.data_snapshot && (
                    <div style={{ padding: "0 20px 20px", borderTop: "1px solid var(--border-light)" }}>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", marginTop: "16px" }}>

                        {/* Members */}
                        <div style={{ background: "#f8fafc", borderRadius: "10px", padding: "14px" }}>
                          <div style={{ fontSize: "11px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: "10px" }}>👥 Members</div>
                          {[
                            ["Total", r.data_snapshot.members?.total],
                            ["Active", r.data_snapshot.members?.active],
                          ].map(([k, v]) => (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: "13px", borderBottom: "1px solid #e2e8f0" }}>
                              <span style={{ color: "#64748b" }}>{k}</span>
                              <span style={{ fontWeight: "600" }}>{v}</span>
                            </div>
                          ))}
                        </div>

                        {/* Savings */}
                        <div style={{ background: "#f8fafc", borderRadius: "10px", padding: "14px" }}>
                          <div style={{ fontSize: "11px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: "10px" }}>💰 Savings</div>
                          {[
                            ["Total Balance", `KES ${fmt(r.data_snapshot.savings?.total)}`],
                            ["Deposits (period)", `KES ${fmt(r.data_snapshot.savings?.deposits_period)}`],
                            ["Withdrawals (period)", `KES ${fmt(r.data_snapshot.savings?.withdrawals_period)}`],
                          ].map(([k, v]) => (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: "13px", borderBottom: "1px solid #e2e8f0" }}>
                              <span style={{ color: "#64748b" }}>{k}</span>
                              <span style={{ fontWeight: "600" }}>{v}</span>
                            </div>
                          ))}
                        </div>

                        {/* Loans */}
                        <div style={{ background: "#f8fafc", borderRadius: "10px", padding: "14px" }}>
                          <div style={{ fontSize: "11px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: "10px" }}>🏦 Loans</div>
                          {[
                            ["Total Loans", r.data_snapshot.loans?.total],
                            ["Active", r.data_snapshot.loans?.active],
                            ["Outstanding", `KES ${fmt(r.data_snapshot.loans?.outstanding)}`],
                            ["Repayments (period)", `KES ${fmt(r.data_snapshot.loans?.repayments_period)}`],
                          ].map(([k, v]) => (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: "13px", borderBottom: "1px solid #e2e8f0" }}>
                              <span style={{ color: "#64748b" }}>{k}</span>
                              <span style={{ fontWeight: "600" }}>{v}</span>
                            </div>
                          ))}
                        </div>

                        {/* Collateral */}
                        <div style={{ background: "#f8fafc", borderRadius: "10px", padding: "14px" }}>
                          <div style={{ fontSize: "11px", fontWeight: "700", color: "#64748b", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: "10px" }}>🏠 Collateral</div>
                          {[
                            ["Total Asset Value", `KES ${fmt(r.data_snapshot.collateral?.total_asset_value)}`],
                            ["Currently Locked", `KES ${fmt(r.data_snapshot.collateral?.total_asset_locked)}`],
                          ].map(([k, v]) => (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: "13px", borderBottom: "1px solid #e2e8f0" }}>
                              <span style={{ color: "#64748b" }}>{k}</span>
                              <span style={{ fontWeight: "600" }}>{v}</span>
                            </div>
                          ))}
                        </div>

                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Layout>
  );
}
