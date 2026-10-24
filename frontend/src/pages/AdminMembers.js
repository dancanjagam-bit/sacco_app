import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/axios";
import Layout from "../components/Layout";
import "../styles/dashboard.css";

export default function AdminMembers() {
  const navigate = useNavigate();

  const [members, setMembers]   = useState([]);
  const [total,   setTotal]     = useState(0);
  const [pages,   setPages]     = useState(1);
  const [page,    setPage]      = useState(1);
  const [search,  setSearch]    = useState("");
  const [status,  setStatus]    = useState("all");
  const [loading, setLoading]   = useState(true);
  const [error,   setError]     = useState(null);

  const fetchMembers = useCallback(async (p = 1, s = search, st = status) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`members/?page=${p}&per_page=20&search=${encodeURIComponent(s)}&status=${st}`);
      setMembers(res.data.results);
      setTotal(res.data.total);
      setPages(res.data.pages);
      setPage(p);
    } catch {
      setError("Failed to load members.");
    } finally {
      setLoading(false);
    }
  }, [search, status]);

  useEffect(() => { fetchMembers(1); }, []);  // eslint-disable-line

  const handleSearch = (e) => {
    e.preventDefault();
    fetchMembers(1, search, status);
  };

  const handleSuspend = async (id, name, currentStatus) => {
    const action  = currentStatus === "active" ? "suspend" : "reinstate";
    const reason  = action === "suspend" ? window.prompt(`Reason for suspending ${name}?`) : null;
    if (action === "suspend" && reason === null) return;

    try {
      await api.post(`members/${id}/suspend/`, { action, reason: reason || "" });
      fetchMembers(page, search, status);
    } catch (err) {
      alert(err.response?.data?.error || "Action failed.");
    }
  };

  return (
    <Layout>
      {() => (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title">👥 Member Management</h2>
              <p className="section-subtitle">{total} total members</p>
            </div>
          </div>

          {/* Filters */}
          <form onSubmit={handleSearch} style={{ display: "flex", gap: "10px", marginBottom: "16px", flexWrap: "wrap" }}>
            <input
              className="amount-input"
              placeholder="Search by name, ID, phone, email..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ flex: 1, minWidth: "240px" }}
            />
            <select
              className="amount-input"
              value={status}
              onChange={e => { setStatus(e.target.value); fetchMembers(1, search, e.target.value); }}
              style={{ width: "150px" }}
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="suspended">Suspended</option>
            </select>
            <button type="submit" style={{ padding: "10px 20px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "8px", fontWeight: "600", cursor: "pointer" }}>
              🔍 Search
            </button>
          </form>

          {error && <div className="alert alert-error">{error}</div>}

          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading members...</p>
          ) : (
            <>
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Member No.</th>
                      <th>Name</th>
                      <th>Phone</th>
                      <th>Email</th>
                      <th>County</th>
                      <th>Status</th>
                      <th>Joined</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.length === 0 ? (
                      <tr><td colSpan="8" style={{ textAlign: "center", padding: "32px", color: "#94a3b8" }}>No members found.</td></tr>
                    ) : members.map(m => (
                      <tr key={m.id}>
                        <td><strong>{m.member_number}</strong></td>
                        <td>{m.full_name || m.username}</td>
                        <td style={{ fontSize: "13px" }}>{m.phone_number}</td>
                        <td style={{ fontSize: "12px", color: "#64748b" }}>{m.email}</td>
                        <td style={{ fontSize: "13px" }}>{m.county}</td>
                        <td>
                          <span className={`status status-${m.status === "active" ? "approved" : m.status === "suspended" ? "rejected" : "pending"}`}>
                            {m.status}
                          </span>
                        </td>
                        <td style={{ fontSize: "12px" }}>{m.date_joined ? new Date(m.date_joined).toLocaleDateString("en-KE") : "—"}</td>
                        <td>
                          <div style={{ display: "flex", gap: "6px" }}>
                            <button
                              onClick={() => navigate(`/admin/members/${m.id}`)}
                              style={{ padding: "5px 12px", background: "var(--primary)", color: "#fff", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}
                            >
                              View
                            </button>
                            <button
                              onClick={() => handleSuspend(m.id, m.full_name, m.status)}
                              style={{
                                padding: "5px 12px", border: "none", borderRadius: "6px", fontSize: "12px", fontWeight: "600", cursor: "pointer",
                                background: m.status === "active" ? "#fee2e2" : "#dcfce7",
                                color:      m.status === "active" ? "#b91c1c" : "#15803d",
                              }}
                            >
                              {m.status === "active" ? "Suspend" : "Reinstate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {pages > 1 && (
                <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginTop: "20px", alignItems: "center" }}>
                  <button disabled={page <= 1} onClick={() => fetchMembers(page - 1)} style={{ padding: "8px 16px", border: "1.5px solid var(--border)", borderRadius: "8px", background: "#fff", cursor: page > 1 ? "pointer" : "default", opacity: page <= 1 ? 0.4 : 1 }}>← Prev</button>
                  {Array.from({ length: Math.min(pages, 7) }, (_, i) => i + 1).map(p => (
                    <button key={p} onClick={() => fetchMembers(p)} style={{ padding: "8px 14px", border: `1.5px solid ${p === page ? "var(--primary)" : "var(--border)"}`, borderRadius: "8px", background: p === page ? "var(--primary)" : "#fff", color: p === page ? "#fff" : "#1e293b", fontWeight: p === page ? "700" : "400", cursor: "pointer" }}>{p}</button>
                  ))}
                  <button disabled={page >= pages} onClick={() => fetchMembers(page + 1)} style={{ padding: "8px 16px", border: "1.5px solid var(--border)", borderRadius: "8px", background: "#fff", cursor: page < pages ? "pointer" : "default", opacity: page >= pages ? 0.4 : 1 }}>Next →</button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </Layout>
  );
}
