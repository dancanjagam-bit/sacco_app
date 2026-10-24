import React, { useEffect, useState, useCallback } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

const ACTION_COLORS = {
  login:          "#dbeafe",  deposit:      "#dcfce7",
  logout:         "#f1f5f9",  withdrawal:   "#fef3c7",
  register:       "#dcfce7",  loan_apply:   "#dbeafe",
  password_change:"#f3e8ff",  loan_approve: "#dcfce7",
  password_reset: "#fef3c7",  loan_reject:  "#fee2e2",
  member_update:  "#e0f2fe",  loan_repayment:"#dcfce7",
  member_delete:  "#fee2e2",  staff_create: "#f3e8ff",
  member_suspend: "#fef3c7",  staff_update: "#e0f2fe",
  export:         "#f1f5f9",  staff_deactivate: "#fee2e2",
};

export default function AuditLog() {
  const [logs,    setLogs]    = useState([]);
  const [loading, setLoading] = useState(true);
  const [page,    setPage]    = useState(1);
  const [total,   setTotal]   = useState(0);
  const [pages,   setPages]   = useState(1);
  const [search,  setSearch]  = useState("");

  const fetchLogs = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const res = await api.get(`admin/audit-log/?page=${p}`);
      setLogs(res.data.results);
      setTotal(res.data.total);
      setPages(res.data.pages);
      setPage(p);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchLogs(1); }, [fetchLogs]);

  const filtered = search
    ? logs.filter(l =>
        l.actor.toLowerCase().includes(search.toLowerCase()) ||
        l.action_label.toLowerCase().includes(search.toLowerCase()) ||
        l.target.toLowerCase().includes(search.toLowerCase())
      )
    : logs;

  return (
    <Layout>
      {() => (
        <>
          <h2 className="section-title">🔍 Audit Log</h2>
          <p className="section-subtitle">
            Complete trail of all actions performed in the system — {total} total entries
          </p>

          {/* Search + stats */}
          <div style={{ display: "flex", gap: "12px", marginBottom: "16px", alignItems: "center" }}>
            <input
              className="amount-input"
              placeholder="Search by user, action, or target..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ flex: 1, maxWidth: "400px" }}
            />
            <button onClick={() => fetchLogs(page)} style={{ padding: "10px 16px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "600", cursor: "pointer" }}>
              🔄 Refresh
            </button>
          </div>

          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading audit log...</p>
          ) : (
            <>
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>User</th>
                      <th>Action</th>
                      <th>Target</th>
                      <th>IP Address</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.length === 0 ? (
                      <tr><td colSpan="6" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>No log entries found.</td></tr>
                    ) : filtered.map((log) => (
                      <tr key={log.id}>
                        <td style={{ fontSize: "12px", color: "#64748b", whiteSpace: "nowrap" }}>
                          {new Date(log.timestamp).toLocaleString("en-KE")}
                        </td>
                        <td style={{ fontWeight: "600", fontSize: "13px" }}>{log.actor}</td>
                        <td>
                          <span style={{
                            padding: "3px 10px", borderRadius: "20px",
                            fontSize: "12px", fontWeight: "600",
                            background: ACTION_COLORS[log.action] || "#f1f5f9",
                            color: "#1e293b",
                          }}>
                            {log.action_label}
                          </span>
                        </td>
                        <td style={{ fontSize: "13px", color: "#64748b" }}>{log.target || "—"}</td>
                        <td style={{ fontSize: "12px", color: "#94a3b8", fontFamily: "monospace" }}>
                          {log.ip_address || "—"}
                        </td>
                        <td style={{ fontSize: "12px", color: "#64748b", maxWidth: "200px" }}>
                          {Object.keys(log.details).length > 0
                            ? Object.entries(log.details)
                                .map(([k, v]) => `${k}: ${v}`)
                                .join(", ")
                                .slice(0, 80)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {pages > 1 && (
                <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginTop: "20px" }}>
                  <button
                    disabled={page <= 1}
                    onClick={() => fetchLogs(page - 1)}
                    style={{ padding: "8px 16px", border: "1.5px solid var(--border)", borderRadius: "8px", background: "#fff", cursor: page > 1 ? "pointer" : "default", opacity: page <= 1 ? 0.4 : 1 }}
                  >
                    ← Previous
                  </button>
                  <span style={{ padding: "8px 16px", fontSize: "14px", color: "#64748b" }}>
                    Page {page} of {pages}
                  </span>
                  <button
                    disabled={page >= pages}
                    onClick={() => fetchLogs(page + 1)}
                    style={{ padding: "8px 16px", border: "1.5px solid var(--border)", borderRadius: "8px", background: "#fff", cursor: page < pages ? "pointer" : "default", opacity: page >= pages ? 0.4 : 1 }}
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </Layout>
  );
}
