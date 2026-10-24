import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import "../styles/dashboard.css";

const TYPE_STYLE = {
  success: { bg: "#f0fdf4", border: "#86efac", icon: "✅", color: "#15803d" },
  info:    { bg: "#eff6ff", border: "#93c5fd", icon: "ℹ️", color: "#1d4ed8" },
  warning: { bg: "#fffbeb", border: "#fcd34d", icon: "⚠️", color: "#b45309" },
  error:   { bg: "#fef2f2", border: "#fca5a5", icon: "❌", color: "#b91c1c" },
};

export default function Notifications() {
  const navigate = useNavigate();
  const [notifs,   setNotifs]   = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [unread,   setUnread]   = useState(0);

  useEffect(() => { fetchNotifs(); }, []);

  const fetchNotifs = async () => {
    setLoading(true);
    try {
      const res = await api.get("notifications/");
      setNotifs(res.data.notifications);
      setUnread(res.data.unread_count);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const markRead = async (id) => {
    await api.post(`notifications/${id}/read/`);
    setNotifs(notifs.map(n => n.id === id ? { ...n, is_read: true } : n));
    setUnread(prev => Math.max(0, prev - 1));
  };

  const markAllRead = async () => {
    await api.post("notifications/read-all/");
    setNotifs(notifs.map(n => ({ ...n, is_read: true })));
    setUnread(0);
  };

  return (
    <Layout>
      {() => (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div>
              <h2 className="section-title">🔔 Notifications</h2>
              <p className="section-subtitle">
                {unread > 0 ? `${unread} unread notification${unread > 1 ? "s" : ""}` : "All caught up!"}
              </p>
            </div>
            {unread > 0 && (
              <button
                onClick={markAllRead}
                style={{ padding: "9px 18px", background: "#f1f5f9", color: "#475569", border: "1.5px solid var(--border)", borderRadius: "8px", fontWeight: "600", fontSize: "13px", cursor: "pointer" }}
              >
                Mark all as read
              </button>
            )}
          </div>

          {loading ? (
            <p style={{ color: "#94a3b8" }}>Loading notifications...</p>
          ) : notifs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🔔</div>
              <h3>No notifications yet</h3>
              <p>You'll see updates about your account activity here.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {notifs.map((n) => {
                const s = TYPE_STYLE[n.type] || TYPE_STYLE.info;
                return (
                  <div
                    key={n.id}
                    onClick={() => {
                      if (!n.is_read) markRead(n.id);
                      if (n.link) navigate(n.link);
                    }}
                    style={{
                      background:   n.is_read ? "#fff"   : s.bg,
                      border:       `1.5px solid ${n.is_read ? "var(--border)" : s.border}`,
                      borderRadius: "10px",
                      padding:      "16px 20px",
                      cursor:       n.link ? "pointer" : "default",
                      display:      "flex",
                      gap:          "14px",
                      alignItems:   "flex-start",
                      transition:   "box-shadow .15s",
                      boxShadow:    n.is_read ? "none" : "var(--shadow-sm)",
                      opacity:      n.is_read ? 0.75 : 1,
                    }}
                  >
                    <span style={{ fontSize: "22px", flexShrink: 0 }}>{s.icon}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                        <h4 style={{ margin: 0, fontSize: "14px", fontWeight: "700", color: n.is_read ? "#64748b" : s.color }}>
                          {n.title}
                        </h4>
                        <span style={{ fontSize: "12px", color: "#94a3b8", whiteSpace: "nowrap", marginLeft: "12px" }}>
                          {new Date(n.created_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" })}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: "13px", color: "#475569" }}>{n.message}</p>
                    </div>
                    {!n.is_read && (
                      <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: s.color, flexShrink: 0, marginTop: "4px" }} />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
