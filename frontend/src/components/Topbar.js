import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import "../styles/topbar.css";

function Topbar({ user }) {
  const navigate  = useNavigate();
  const { logout } = useAuth();

  const [unread,   setUnread]   = useState(0);
  const [notifs,   setNotifs]   = useState([]);
  const [showDrop, setShowDrop] = useState(false);
  const dropRef = useRef(null);

  const today = new Date().toLocaleDateString("en-KE", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  // Fetch notification count every 30 seconds
  useEffect(() => {
    fetchNotifs();
    const interval = setInterval(fetchNotifs, 30000);
    return () => clearInterval(interval);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropRef.current && !dropRef.current.contains(e.target)) {
        setShowDrop(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const fetchNotifs = async () => {
    try {
      const res = await api.get("notifications/");
      setUnread(res.data.unread_count);
      setNotifs(res.data.notifications.slice(0, 5));
    } catch {
      // silent — don't break the topbar if this fails
    }
  };

  const markRead = async (id, link) => {
    try { await api.post(`notifications/${id}/read/`); } catch {}
    setUnread(prev => Math.max(0, prev - 1));
    setNotifs(notifs.map(n => n.id === id ? { ...n, is_read: true } : n));
    setShowDrop(false);
    if (link) navigate(link);
  };

  const handleLogout = async () => {
    try {
      const refresh = localStorage.getItem("refresh");
      if (refresh) await api.post("logout/", { refresh });
    } catch {}
    logout();
    navigate("/");
  };

  const typeIcon = { success: "✅", info: "ℹ️", warning: "⚠️", error: "❌" };

  return (
    <div className="topbar">
      <div className="topbar-left">
        <p className="topbar-greeting">Welcome back 👋</p>
        <h2 className="topbar-title">{user?.first_name || user?.username}</h2>
        <p className="topbar-role">
          {user?.is_staff || user?.is_superuser ? (
            user?.staff_role ? `${user.staff_role.replace("_", " ").toUpperCase()}` : "Administrator"
          ) : "Member"}
        </p>
      </div>

      <div className="topbar-right">
        <div className="topbar-date-box">
          <span className="date-icon">📅</span>
          <span>{today}</span>
        </div>

        {/* Notification bell */}
        <div ref={dropRef} style={{ position: "relative" }}>
          <div
            className="notification"
            onClick={() => setShowDrop(!showDrop)}
            title="Notifications"
          >
            🔔
            {unread > 0 && (
              <span style={{
                position: "absolute", top: "-4px", right: "-4px",
                background: "#dc2626", color: "#fff",
                borderRadius: "50%", width: "18px", height: "18px",
                fontSize: "11px", fontWeight: "700",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </div>

          {/* Dropdown */}
          {showDrop && (
            <div style={{
              position: "absolute", top: "54px", right: 0,
              background: "#fff", borderRadius: "12px",
              boxShadow: "var(--shadow-lg)",
              border: "1px solid var(--border)",
              width: "340px", zIndex: 1000,
            }}>
              <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: "700", fontSize: "14px" }}>
                  Notifications {unread > 0 && <span style={{ background: "#dc2626", color: "#fff", borderRadius: "20px", padding: "2px 8px", fontSize: "11px", marginLeft: "6px" }}>{unread}</span>}
                </span>
                <button onClick={() => { navigate("/notifications"); setShowDrop(false); }} style={{ background: "none", border: "none", color: "var(--primary)", fontSize: "12px", fontWeight: "600", cursor: "pointer" }}>
                  View all →
                </button>
              </div>

              {notifs.length === 0 ? (
                <div style={{ padding: "24px 16px", textAlign: "center", color: "#94a3b8", fontSize: "13px" }}>
                  No notifications yet
                </div>
              ) : notifs.map((n) => (
                <div
                  key={n.id}
                  onClick={() => markRead(n.id, n.link)}
                  style={{
                    padding: "12px 16px",
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                    background: n.is_read ? "#fff" : "#f8fafc",
                    display: "flex", gap: "10px", alignItems: "flex-start",
                  }}
                >
                  <span style={{ fontSize: "16px" }}>{typeIcon[n.type] || "🔔"}</span>
                  <div>
                    <p style={{ margin: "0 0 2px", fontWeight: "600", fontSize: "13px", color: n.is_read ? "#64748b" : "#1e293b" }}>{n.title}</p>
                    <p style={{ margin: 0, fontSize: "12px", color: "#94a3b8" }}>{n.message.slice(0, 60)}{n.message.length > 60 ? "..." : ""}</p>
                  </div>
                  {!n.is_read && (
                    <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#4f46e5", marginTop: "4px", flexShrink: 0 }} />
                  )}
                </div>
              ))}

              <div style={{ padding: "10px 16px", textAlign: "center" }}>
                <button
                  onClick={async () => { await api.post("notifications/read-all/"); setUnread(0); setNotifs(notifs.map(n => ({ ...n, is_read: true }))); }}
                  style={{ background: "none", border: "none", color: "#64748b", fontSize: "12px", cursor: "pointer" }}
                >
                  Mark all as read
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Avatar + logout */}
        <div
          className="avatar"
          onClick={handleLogout}
          title="Click to logout"
          style={{ cursor: "pointer" }}
        >
          {user?.first_name?.charAt(0).toUpperCase() || user?.username?.charAt(0).toUpperCase() || "U"}
        </div>
      </div>
    </div>
  );
}

export default Topbar;
