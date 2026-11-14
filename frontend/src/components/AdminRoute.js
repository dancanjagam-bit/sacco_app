import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { hasPermission, ROUTES } from "../navigation/routes";
import { availableWorkspaces, portalDestination } from "../auth/portalDestination";
import LoadingState from "./ui/LoadingState";
import RouteAccessDenied from "./RouteAccessDenied";

function AdminRoute({ children, superAdminOnly = false, requiredPermission }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <main className="application-loading"><LoadingState label="Loading your secure workspace…" /></main>;
  }

  if (!user) return <Navigate to={ROUTES.login} replace />;

  // Navigation permissions mirror the backend access snapshot. Every API
  // still performs its own checks; this prevents a permitted link and a
  // generic frontend guard from disagreeing about module access.
  const required = requiredPermission || "staff.manage";
  const canAccess = (Array.isArray(required)
    ? required.some((permission) => hasPermission(user, permission))
    : hasPermission(user, required)) && (!superAdminOnly || hasPermission(user, "staff.manage"));
  if (!canAccess) {
    const permittedWorkspaces = availableWorkspaces(user);
    const destination = permittedWorkspaces.length ? portalDestination(user) : null;
    if (destination && destination !== location.pathname) return <Navigate to={destination} replace />;
    return <RouteAccessDenied destination={destination} />;
  }

  return children;
}

export default AdminRoute;
