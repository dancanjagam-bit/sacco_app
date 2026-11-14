import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api, { authApi } from "../api/axios";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState("");

  const refreshUser = useCallback(async () => {
    const token = sessionStorage.getItem("access") || localStorage.getItem("access");
    setLoading(true);
    setAuthError("");
    if (!token) {
      setUser(null);
      setLoading(false);
      return null;
    }
    try {
      const res = await api.get("dashboard/");
      setUser(res.data);
      return res.data;
    } catch (err) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        localStorage.removeItem("access");
        localStorage.removeItem("refresh");
        sessionStorage.removeItem("access");
        sessionStorage.removeItem("refresh");
        setUser(null);
      } else {
        // Keep a valid-looking session so a temporary outage can be retried.
        setUser(null);
        setAuthError("We could not reach the SACCO service. Check your connection and retry.");
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  // Refresh the server-produced permission/workspace snapshot when a signed-in
  // user returns to the tab. This clears stale role-based navigation after an
  // administrator revokes an assignment; APIs still authorize every action.
  useEffect(() => {
    const refreshOnFocus = () => {
      if (document.visibilityState === "visible" && (sessionStorage.getItem("access") || localStorage.getItem("access"))) {
        refreshUser();
      }
    };
    document.addEventListener("visibilitychange", refreshOnFocus);
    return () => document.removeEventListener("visibilitychange", refreshOnFocus);
  }, [refreshUser]);

  const logout = useCallback(async () => {
    const access = sessionStorage.getItem("access") || localStorage.getItem("access");
    const refresh = sessionStorage.getItem("refresh") || localStorage.getItem("refresh");
    const revokeRequest = access && refresh
      ? authApi.post("logout/", { refresh }, { headers: { Authorization: `Bearer ${access}` } })
      : Promise.resolve();

    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    sessionStorage.removeItem("access");
    sessionStorage.removeItem("refresh");
    localStorage.removeItem("sacco_remember_session");
    setAuthError("");
    setUser(null);
    setLoading(false);
    await revokeRequest.catch(() => null);
  }, []);

  const hasSessionToken = Boolean(
    sessionStorage.getItem("access") || localStorage.getItem("access")
  );
  const permissions = Array.isArray(user?.permissions) ? user.permissions : [];
  const isAdmin = permissions.includes("staff.manage");
  const isSuperAdmin = permissions.includes("staff.manage");
  const value = useMemo(() => ({
    user, loading, authError, hasSessionToken, refreshUser, logout, isAdmin, isSuperAdmin,
  }), [user, loading, authError, hasSessionToken, refreshUser, logout, isAdmin, isSuperAdmin]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
