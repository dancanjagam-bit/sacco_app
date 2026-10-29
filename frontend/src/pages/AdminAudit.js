import React, { useEffect, useState, useCallback } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

const SEVERITY_STYLE = {
  critical: { bg: "#fee2e2", color: "#991b1b", border: "#fca5a5", label: "CRITICAL" },
  high:     { bg: "#fef3c7", color: "#92400e", border: "#fcd34d", label: "HIGH" },
  medium:   { bg: "#dbeafe", color: "#1e40af", border: "#93c5fd", label: "MEDIUM" },
  low:      { bg: "#f1f5f9", color: "#475569", border: "#cbd5e1", label: "LOW" },
  info:     { bg: "#e0f2fe", color: "#0369a1", border: "#bae6fd", label: "INFO" },
};

const STATUS_STYLE = {
  open:      { bg: "#fee2e2", color: "#b91c1c", label: "Open" },
  reviewing: { bg: "#fef3c7", color: "#b45309", label: "Under Review" },
  resolved:  { bg: "#dcfce7", color: "#15803d", label: "Resolved" },
  dismissed: { bg: "#f1f5f9", color: "#64748b", label: "Dismissed" },
};

export default function AdminAudit() {
  const [findings,  setFindings]  = useState([]);
  const [summary,   setSummary]   = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [running,   setRunning]   = useState(false);
  const [page,      setPage]      = useState(1);
  const [pages,     setPages]     = useState(1);
  const [total,     setTotal]     = useState(0);
  const [filter,    setFilter]    = useState({ severity: "", status: "", search: "" });
  const [modal,     setModal]     = useState(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [resolution,  setResolution]  = useState("");
  const [actioning,  setActioning]   = useState(false);
  const [msg,        setMsg]        = useState(null);

  const fetchFindings = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      let url = `admin/audit/findings/?page=${p}&per_page=15`;
      if (filter.severity) url += `&severity=${filter.severity}`;
      if (filter.status)   url += `&status=${filter.status}`;
      if (filter.search)   url += `&search=${encodeURIComponent(filter.search)}`;
      const res = await api.get(url);
      setFindings(res.data.results);
      setSummary(res.data.summary);
      setTotal(res.data.total);
      setPages(res.data.pages);
      setPage(p);
    } catch { setMsg({ type: "error", text: "Failed to load findings." }); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { fetchFindings(1); }, [fetchFindings]);

  const runAudit = async () => {
    if (!window.confirm("Run a full financial audit? This will scan all transactions, loans, collateral, and dividend records.")) return;
    setRunning(true); setMsg(null);
    try {
      const res = await api.post("admin/audit/run/");
      setMsg({ type: "success", text: res.data.message });
      fetchFindings(1);
    } catch { setMsg({ type: "error", text: "Audit run failed." }); }
    finally { setRunning(false); }
  };

  const handleReview = async () => {
    if (!modal) return;
    setActioning(true);
    try {
      await api.post(`admin/audit/findings/${modal.id}/review/`, {
        status: modal.action,
        notes: reviewNotes,
        resolution: resolution,
      });
      setMsg({ type: "success", text: `Finding marked as ${modal.action}.` });
      setModal(null); setReviewNotes(""); setResolution("");
      fetchFindings(page);
    } catch { setMsg({ type: "error", text: "Failed to update finding." }); }
    finally { setActioning(false); }
  };

  const sevBadge = (s) => {
    const style = SEVERITY_STYLE[s] || SEVERITY_STYLE.info;
    return <span style={{ padding: "3px 10px", borderRadius: "20px", fontSize: "11px", fontWeight: "700", background: style.bg, color: style.color, border: `1px solid ${style.border}` }}>{style.label}</span>;
  };

  const statusBadge = (s) => {
    const style = STATUS_STYLE[s] || STATUS_STYLE.open;
    return <span style={{ padding: "3px 10px", borderRadius: "20px", fontSize: "11px", fontWeight: "600", background: style.bg, color: style.color }}>{style.label}</span>;
  };

  return (
    <Layout>
      {() => (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title">🔍 Financial Audit Engine</h2>
              <p className="section-subtitle">Automated integrity checks across all financial records</p>
            </div>
            <button onClick={runAudit} disabled={running} style={{ padding: "10px 20px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "700", fontSize: "14px", cursor: "pointer" }}>
              {running ? "Scanning..." : "▶ Run Full Audit"}
            </button>
          </div>

          {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

          {/* Summary cards */}
          {summary && (
            <div className="summary-grid" style={{ marginBottom: "20px" }}>
              <div className="summary-card" style={{ borderTopColor: summary.total > 0 ? "#dc2626" : "#16a34a" }}>
                <h4>📋 Total Findings</h4>
                <h2>{summary.total}</h2>
              </div>
              <div className="summary-card" style={{ borderTopColor: "#dc2626" }}>
                <h4>🔴 Critical</h4>
                <h2 style={{ color: summary.critical > 0 ? "#dc2626" : undefined }}>{summary.critical}</h2>
              </div>
              <div className="summary-card" style={{ borderTopColor: "#f59e0b" }}>
                <h4>🟠 High</h4>
                <h2 style={{ color: summary.high > 0 ? "#f59e0b" : undefined }}>{summary.high}</h2>
              </div>
              <div className="summary-card" style={{ borderTopColor: "#2563eb" }}>
                <h4>🔵 Medium</h4>
                <h2>{summary.medium}</h2>
              </div>
              <div className="summary-card" style={{ borderTopColor: "#16a34a" }}>
                <h4>✅ Resolved</h4>
                <h2>{summary.resolved}</h2>
              </div>
              <div className="summary-card" style={{ borderTopColor: "#f59e0b" }}>
                <h4>⏳ Open</h4>
                <h2 style={{ color: summary.open > 0 ? "#f59e0b" : undefined }}>{summary.open}</h2>
              </div>
            </div>
          )}

          {/* Filters */}
          <div style={{ display: "flex", gap: "10px", marginBottom: "16px", flexWrap: "wrap" }}>
            <select
              className="amount-input"
              style={{ width: "140px" }}
              value={filter.severity}
              onChange={(e) => setFilter({ ...filter, severity: e.target.value })}
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
            <select
              className="amount-input"
              style={{ width: "140px" }}
              value={filter.status}
              onChange={(e) => setFilter({ ...filter, status: e.target.value })}
            >
              <option value="">All Status</option>
              <option value="open">Open</option>
              <option value="reviewing">Under Review</option>
              <option value="resolved">Resolved</option>
              <option value="dismissed">Dismissed</option>
            </select>
            <input
              className="amount-input"
              style={{ flex: 1, maxWidth: "300px" }}
              placeholder="Search findings..."
              value={filter.search}
              onChange={(e) => setFilter({ ...filter, search: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && fetchFindings(1)}
            />
            <button onClick={() => fetchFindings(1)} style={{ padding: "10px 16px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "600", cursor: "pointer" }}>
              🔍 Filter
            </button>
          </div>

          {/* Findings table */}
          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading findings...</p>
          ) : findings.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">✅</div>
              <h3>No findings</h3>
              <p>Run a full audit to scan all financial records, or adjust your filters.</p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>#</th><th>Severity</th><th>Rule</th><th>Title</th>
                    <th>User</th><th>Status</th><th>Detected</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map(f => (
                    <tr key={f.id}>
                      <td style={{ fontWeight: "600" }}>#{f.id}</td>
                      <td>{sevBadge(f.severity)}</td>
                      <td style={{ fontSize: "12px", fontFamily: "monospace", color: "#64748b" }}>{f.rule}</td>
                      <td style={{ maxWidth: "300px" }}>
                        <div style={{ fontWeight: "600", fontSize: "13px" }}>{f.title}</div>
                        <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>{f.description.slice(0, 120)}{f.description.length > 120 ? "..." : ""}</div>
                      </td>
                      <td style={{ fontSize: "13px" }}>{f.user || "—"}</td>
                      <td>{statusBadge(f.status)}</td>
                      <td style={{ fontSize: "12px", color: "#94a3b8" }}>{new Date(f.created_at).toLocaleDateString("en-KE")}</td>
                      <td>
                        {(f.status === "open" || f.status === "reviewing") && (
                          <div style={{ display: "flex", gap: "6px" }}>
                            <button
                              onClick={() => { setModal({ ...f, action: "reviewing" }); setReviewNotes(f.review_notes || ""); setResolution(f.resolution || ""); }}
                              style={{ padding: "5px 10px", background: "#fef3c7", color: "#b45309", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}
                            >Review</button>
                            <button
                              onClick={() => { setModal({ ...f, action: "resolved" }); setReviewNotes(""); setResolution(""); }}
                              style={{ padding: "5px 10px", background: "#dcfce7", color: "#15803d", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}
                            >Resolve</button>
                            <button
                              onClick={() => { setModal({ ...f, action: "dismissed" }); setReviewNotes(""); setResolution(""); }}
                              style={{ padding: "5px 10px", background: "#f1f5f9", color: "#64748b", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}
                            >Dismiss</button>
                          </div>
                        )}
                        {f.status === "resolved" && <span style={{ fontSize: "12px", color: "#15803d" }}>✅ {f.resolution.slice(0, 30)}{f.resolution.length > 30 ? "..." : ""}</span>}
                        {f.status === "dismissed" && <span style={{ fontSize: "12px", color: "#64748b" }}>Dismissed</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {pages > 1 && (
            <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginTop: "20px", alignItems: "center" }}>
              <button disabled={page <= 1} onClick={() => fetchFindings(page - 1)} style={{ padding: "8px 16px", border: "1.5px solid var(--border)", borderRadius: "8px", background: "#fff", cursor: page > 1 ? "pointer" : "default", opacity: page <= 1 ? 0.4 : 1 }}>← Prev</button>
              <span style={{ padding: "8px 16px", fontSize: "13px", color: "#64748b" }}>Page {page} of {pages} ({total} total)</span>
              <button disabled={page >= pages} onClick={() => fetchFindings(page + 1)} style={{ padding: "8px 16px", border: "1.5px solid var(--border)", borderRadius: "8px", background: "#fff", cursor: page < pages ? "pointer" : "default", opacity: page >= pages ? 0.4 : 1 }}>Next →</button>
            </div>
          )}

          {/* Review modal */}
          {modal && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 1000 }}>
              <div style={{ background: "#fff", padding: "28px", borderRadius: "14px", width: "500px", maxHeight: "90vh", overflowY: "auto", boxShadow: "var(--shadow-lg)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                  <h3 style={{ margin: 0 }}>Finding #{modal.id}</h3>
                  {sevBadge(modal.severity)}
                </div>
                <p style={{ margin: "0 0 4px", fontWeight: "700", fontSize: "14px" }}>{modal.title}</p>
                <p style={{ margin: "0 0 14px", fontSize: "13px", color: "#475569" }}>{modal.description}</p>
                <div style={{ background: "#f8fafc", borderRadius: "8px", padding: "10px 14px", marginBottom: "14px", fontSize: "12px", color: "#64748b" }}>
                  <div>Rule: <strong>{modal.rule}</strong></div>
                  <div>User: <strong>{modal.user || "—"}</strong></div>
                  <div>Entity: <strong>{modal.entity_type} #{modal.entity_id || "—"}</strong></div>
                  <div>Status → <strong style={{ color: "#2563eb" }}>{modal.action}</strong></div>
                </div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", marginBottom: "5px" }}>Review Notes</label>
                <textarea
                  value={reviewNotes}
                  onChange={e => setReviewNotes(e.target.value)}
                  placeholder="Describe your investigation..."
                  style={{ width: "100%", minHeight: "60px", padding: "10px", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "14px", resize: "vertical", boxSizing: "border-box", marginBottom: "12px" }}
                />
                <label style={{ display: "block", fontSize: "12px", fontWeight: "600", color: "#475569", marginBottom: "5px" }}>Resolution (how it was addressed)</label>
                <textarea
                  value={resolution}
                  onChange={e => setResolution(e.target.value)}
                  placeholder="e.g. Verified with member, corrected balance..."
                  style={{ width: "100%", minHeight: "50px", padding: "10px", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "14px", resize: "vertical", boxSizing: "border-box", marginBottom: "16px" }}
                />
                <div style={{ display: "flex", gap: "10px" }}>
                  <button onClick={handleReview} disabled={actioning} style={{ flex: 1, padding: "12px", border: "none", borderRadius: "8px", background: modal.action === "resolved" ? "#16a34a" : modal.action === "dismissed" ? "#64748b" : "#f59e0b", color: "#fff", fontWeight: "700", cursor: "pointer" }}>
                    {actioning ? "Saving..." : `Confirm — ${modal.action}`}
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
