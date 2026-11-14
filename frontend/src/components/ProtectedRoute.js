import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AuthRecovery from "./AuthRecovery";
import LoadingState from "./ui/LoadingState";
import { hasPermission, ROUTES } from "../navigation/routes";
import { availableWorkspaces, portalDestination } from "../auth/portalDestination";
import RouteAccessDenied from "./RouteAccessDenied";

export default function ProtectedRoute({ children, requiredPermission }) {
  const { user, loading, authError, hasSessionToken } = useAuth();
  const location = useLocation();

  if (loading) {
    return <main className="application-loading"><LoadingState label="Loading your secure workspace…" /></main>;
  }
  if (!user && authError && hasSessionToken) return <AuthRecovery />;
  if (!user) return <Navigate to={ROUTES.login} replace />;
  const allowed = Array.isArray(requiredPermission)
    ? requiredPermission.some((permission) => hasPermission(user, permission))
    : !requiredPermission || hasPermission(user, requiredPermission);
  if (!allowed) {
    const destination = availableWorkspaces(user).length ? portalDestination(user) : null;
    if (destination && destination !== location.pathname) return <Navigate to={destination} replace />;
    return <RouteAccessDenied destination={destination} />;
  }
  return children;
}
