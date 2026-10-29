import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "../styles/sidebar.css";

function Sidebar() {
  const navigate  = useNavigate();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const isAdmin      = user?.is_staff || user?.is_superuser;
  const isSuperAdmin = user?.is_superuser || user?.staff_role === "superadmin";

  const handleLogout = () => { logout(); navigate("/"); };
  const close        = () => setOpen(false);

  const link = (to, icon, label) => (
    <NavLink
      to={to}
      onClick={close}
      className={({ isActive }) => isActive ? "sidebar-item active" : "sidebar-item"}
    >
      <span style={{ fontSize: "17px", flexShrink: 0 }}>{icon}</span>
      {label}
    </NavLink>
  );

  return (
    <>
      {/* Mobile hamburger */}
      <button className="sidebar-toggle" onClick={() => setOpen(true)} aria-label="Open menu">☰</button>

      {/* Overlay */}
      {open && <div className="sidebar-overlay" onClick={close} />}

      <div className={`sidebar${open ? " open" : ""}`}>
        <div className="sidebar-header">
          <span className="sidebar-logo">🏦</span>
          <h1 className="sidebar-title">SACCO</h1>
          <p className="sidebar-subtitle">Management System</p>
        </div>

        <div className="sidebar-nav">
          {isAdmin ? (
            <>
              <p className="sidebar-section-label">Overview</p>
              {link("/admin/dashboard", "📊", "Dashboard")}
              <p className="sidebar-section-label">Members</p>
              {link("/admin/members", "👥", "All Members")}
              {link("/admin/loans",   "🏦", "Loan Approvals")}
              <p className="sidebar-section-label">Reports</p>
              {link("/reports",       "📋", "Reports")}

              <p className="sidebar-section-label">Assets & Config</p>
              {link("/admin/assets",       "🏠", "Asset Registry")}
              {link("/admin/settings",     "⚙️", "SACCO Settings")}
              {link("/admin/exit-requests","🚪", "Exit Requests")}
              {link("/admin/audit",        "🔍", "Financial Audit")}

              {isSuperAdmin && (
                <>
                  <p className="sidebar-section-label">Administration</p>
                  {link("/admin/staff",     "👨‍💼", "Staff Management")}
                  {link("/admin/audit-log", "🔍",  "Audit Log")}
                </>
              )}
            </>
          ) : (
            <>
              <p className="sidebar-section-label">My Account</p>
              {link("/dashboard",    "🏠", "Dashboard")}
              {link("/savings",      "💰", "Savings")}
              {link("/loans",        "🏦", "Loans")}
              {link("/transactions", "💳", "Transactions")}
              {link("/reports",      "📋", "Reports")}
              <hr className="sidebar-divider" />
              <p className="sidebar-section-label">Profile</p>
              {link("/notifications",   "🔔", "Notifications")}
              {link("/profile",         "👤", "My Profile")}
              {link("/change-password", "🔒", "Change Password")}
            </>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-item logout" onClick={handleLogout}>
            <span style={{ fontSize: "17px" }}>🚪</span>
            Logout
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;
