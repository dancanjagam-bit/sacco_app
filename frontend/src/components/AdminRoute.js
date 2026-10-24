import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function AdminRoute({ children, superAdminOnly = false }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", color: "#64748b" }}>
        Loading...
      </div>
    );
  }

  if (!user) return <Navigate to="/" replace />;

  const isAdmin = user.is_staff || user.is_superuser || user.is_admin;
  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  if (superAdminOnly) {
    const isSuperAdmin = user.is_superuser || user.staff_role === "superadmin";
    if (!isSuperAdmin) return <Navigate to="/admin/dashboard" replace />;
  }

  return children;
}

export default AdminRoute;
