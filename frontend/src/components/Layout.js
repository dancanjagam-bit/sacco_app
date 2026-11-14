import React from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useInactivityLogout } from "../hooks/useInactivityLogout";
import { AppShell } from "./AppShell";
import AppTopbar from "./AppTopbar";
import AppSidebar from "./AppSidebar";
import SearchDialog from "./SearchDialog";
import InactivityWarning from "./InactivityWarning";
import AuthRecovery from "./AuthRecovery";
import LoadingState from "./ui/LoadingState";

function LayoutShell({ children, user, logout }) {
  const { showWarning, secondsLeft, stayLoggedIn } = useInactivityLogout(logout);

  return (
    <AppShell>
      <div className="app-layout">
        {/* The navigation rail owns the full desktop height; the topbar aligns
            only with the active workspace column, matching the product shell. */}
        <AppSidebar />

        <div className="app-content-region">
          <AppTopbar />

          {/* Main content — id used for skip-link and inert during mobile drawer */}
          <main
            id="app-main-content"
            className="app-main"
            tabIndex="-1"
          >
            <div className="app-main-inner">
              {typeof children === "function" ? children(user) : children}
            </div>
          </main>
        </div>

        {/* Global Ctrl+K search palette */}
        <SearchDialog />

        {/* Inactivity warning */}
        {showWarning && (
          <InactivityWarning
            secondsLeft={secondsLeft}
            onStayLoggedIn={stayLoggedIn}
          />
        )}
      </div>
    </AppShell>
  );
}

export default function Layout({ children }) {
  const { user, loading, authError, hasSessionToken, logout } = useAuth();

  if (loading) {
    return (
      <main className="application-loading">
        <LoadingState label="Loading your secure workspace…" />
      </main>
    );
  }

  if (!user) {
    if (authError && hasSessionToken) return <AuthRecovery />;
    return <Navigate to="/" replace />;
  }

  return <LayoutShell user={user} logout={logout}>{children}</LayoutShell>;
}
