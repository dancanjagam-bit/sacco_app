import React, { useState, useEffect } from "react";
import Layout from "../components/Layout";
import VerificationStatusBadge from "../components/VerificationStatusBadge";
import api from "../api/axios";

const TABS = ["all", "pending", "flagged", "verified", "failed"];

export default function AdminIDVerifications() {
  const [records, setRecords] = useState([]);
  const [tab, setTab] = useState("all");
  const [selected, setSelected] = useState(null);
  const [reviewStatus, setReviewStatus] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const fetchRecords = async () => {
    try {
      const params = tab !== "all" ? `?status=${tab}` : "";
      const res = await api.get(`accounts/admin/id-verifications/${params}`);
      setRecords(res.data);
    } catch (e) { console.error(e); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchRecords(); }, [tab]);

  const fetchDetail = async (id) => {
    try {
      const res = await api.get(`accounts/admin/id-verifications/${id}/`);
      setSelected(res.data);
      setReviewStatus(res.data.status);
      setReviewNotes("");
    } catch (e) { console.error(e); }
  };

  const submitReview = async () => {
    if (!selected) return;
    setLoading(true);
    setMsg(null);
    try {
      await api.post(`accounts/admin/id-verifications/${selected.id}/review/`, {
        status: reviewStatus,
        notes: reviewNotes,
      });
      setMsg({ type: "success", text: `Status updated to '${reviewStatus}'.` });
      fetchRecords();
      setSelected(prev => ({ ...prev, status: reviewStatus }));
    } catch (e) {
      setMsg({ type: "error", text: "Review failed. Please try again." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      {() => (
        <div>
          <div style={{ marginBottom: "24px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", fontWeight: "800" }}>🪪 ID Verifications</h2>
            <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "13px" }}>Review and approve member identity documents</p>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
            {TABS.map(t => (
              <button key={t} onClick={() => setTab(t)}
                style={{ padding: "7px 18px", borderRadius: "20px", border: "1.5px solid",
                  borderColor: tab === t ? "var(--primary)" : "var(--border)",
                  background: tab === t ? "var(--primary)" : "#fff",
                  color: tab === t ? "#fff" : "var(--muted)",
                  fontWeight: "600", fontSize: "13px", cursor: "pointer", textTransform: "capitalize" }}>
                {t}
              </button>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 380px" : "1fr", gap: "16px" }}>
            {/* Table */}
            <div style={{ background: "#fff", borderRadius: "12px", border: "1px solid var(--border-light)", overflow: "hidden", boxShadow: "var(--shadow-sm)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "linear-gradient(135deg,#1e293b,#334155)" }}>
                    {["Member", "National ID", "Submitted", "Status", "Action"].map(h => (
                      <th key={h} style={{ padding: "12px 16px", textAlign: "left", color: "rgba(255,255,255,.8)", fontSize: "11px", fontWeight: "700", textTransform: "uppercase", letterSpacing: ".6px" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr><td colSpan="5" style={{ padding: "40px", textAlign: "center", color: "#64748b" }}>No records found</td></tr>
                  ) : records.map(r => (
                    <tr key={r.id} style={{ borderBottom: "1px solid #f1f5f9", cursor: "pointer" }}
                      onMouseOver={e => e.currentTarget.style.background = "#f8fafc"}
                      onMouseOut={e => e.currentTarget.style.background = ""}>
                      <td style={{ padding: "12px 16px" }}>
                        <p style={{ margin: 0, fontWeight: "600", fontSize: "13px" }}>{r.full_name || r.username}</p>
                        <p style={{ margin: 0, fontSize: "11px", color: "#64748b" }}>@{r.username}</p>
                      </td>
                      <td style={{ padding: "12px 16px", fontSize: "13px", fontFamily: "monospace" }}>{r.national_id}</td>
                      <td style={{ padding: "12px 16px", fontSize: "12px", color: "#64748b" }}>{new Date(r.created_at).toLocaleDateString("en-KE")}</td>
                      <td style={{ padding: "12px 16px" }}><VerificationStatusBadge status={r.status} /></td>
                      <td style={{ padding: "12px 16px" }}>
                        <button onClick={() => fetchDetail(r.id)}
                          style={{ padding: "5px 14px", borderRadius: "8px", border: "1.5px solid var(--primary)", background: "#fff", color: "var(--primary)", fontWeight: "600", fontSize: "12px", cursor: "pointer" }}>
                          Review
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Detail panel */}
            {selected && (
              <div style={{ background: "#fff", borderRadius: "12px", border: "1px solid var(--border-light)", padding: "20px", boxShadow: "var(--shadow-sm)", overflowY: "auto", maxHeight: "80vh" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <h3 style={{ margin: 0, fontSize: "15px", fontWeight: "700" }}>{selected.full_name || selected.username}</h3>
                  <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", fontSize: "18px", cursor: "pointer", color: "#64748b" }}>✕</button>
                </div>

                {msg && <div style={{ padding: "10px 14px", borderRadius: "8px", marginBottom: "12px", fontSize: "13px", background: msg.type === "success" ? "#f0fdf4" : "#fef2f2", color: msg.type === "success" ? "#16a34a" : "#dc2626" }}>{msg.text}</div>}

                {/* File previews */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "16px" }}>
                  {selected.id_document_url && (
                    <div>
                      <p style={{ margin: "0 0 4px", fontSize: "11px", fontWeight: "700", color: "#64748b", textTransform: "uppercase" }}>ID Document</p>
                      <img src={selected.id_document_url} alt="ID Document" style={{ width: "100%", borderRadius: "8px", border: "1px solid #e2e8f0" }} onError={e => e.target.style.display = "none"} />
                    </div>
                  )}
                  {selected.selfie_url && (
                    <div>
                      <p style={{ margin: "0 0 4px", fontSize: "11px", fontWeight: "700", color: "#64748b", textTransform: "uppercase" }}>Selfie</p>
                      <img src={selected.selfie_url} alt="Selfie" style={{ width: "100%", borderRadius: "8px", border: "1px solid #e2e8f0" }} onError={e => e.target.style.display = "none"} />
                    </div>
                  )}
                </div>

                {/* Face match score */}
                {selected.face_match_score !== null && selected.face_match_score !== undefined && (
                  <div style={{ marginBottom: "12px", padding: "10px 14px", borderRadius: "8px", background: selected.face_match_score >= 70 ? "#f0fdf4" : selected.face_match_score >= 50 ? "#fef3c7" : "#fef2f2" }}>
                    <span style={{ fontSize: "12px", fontWeight: "700", color: selected.face_match_score >= 70 ? "#16a34a" : selected.face_match_score >= 50 ? "#d97706" : "#dc2626" }}>
                      Face Match Score: {selected.face_match_score?.toFixed(1)}%
                    </span>
                  </div>
                )}

                {/* OCR result */}
                {selected.ocr_result?.fields && (
                  <div style={{ marginBottom: "16px" }}>
                    <p style={{ margin: "0 0 8px", fontSize: "12px", fontWeight: "700", color: "#64748b", textTransform: "uppercase" }}>OCR Extracted Fields</p>
                    {Object.entries(selected.ocr_result.fields).map(([k, v]) => v && (
                      <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #f1f5f9", fontSize: "13px" }}>
                        <span style={{ color: "#64748b", textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                        <span style={{ fontWeight: "600" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Review form */}
                <div>
                  <p style={{ margin: "0 0 8px", fontSize: "12px", fontWeight: "700", color: "#64748b", textTransform: "uppercase" }}>Manual Review</p>
                  <select value={reviewStatus} onChange={e => setReviewStatus(e.target.value)}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: "8px", border: "1.5px solid #e2e8f0", marginBottom: "8px", fontSize: "13px", fontFamily: "inherit" }}>
                    {["pending","verified","flagged","failed"].map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <textarea value={reviewNotes} onChange={e => setReviewNotes(e.target.value)}
                    placeholder="Review notes..." rows={3}
                    style={{ width: "100%", padding: "9px 12px", borderRadius: "8px", border: "1.5px solid #e2e8f0", fontSize: "13px", fontFamily: "inherit", resize: "vertical", marginBottom: "8px" }} />
                  <button onClick={submitReview} disabled={loading}
                    style={{ width: "100%", padding: "10px", borderRadius: "8px", border: "none", background: "var(--primary)", color: "#fff", fontWeight: "700", fontSize: "13px", cursor: "pointer" }}>
                    {loading ? "Saving..." : "Save Review"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Layout>
  );
}
