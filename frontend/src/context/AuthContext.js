import React, {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import api from "../api/axios";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    refreshUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshUser = async () => {
    const token = localStorage.getItem("access");
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api.get("dashboard/");
      setUser(res.data);
    } catch (err) {
      if (err.response?.status === 401) {
        localStorage.clear();
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.clear();
    setUser(null);
  };

  const isAdmin      = user?.is_staff || user?.is_superuser || false;
  const isSuperAdmin = user?.is_superuser || user?.staff_role === "superadmin" || false;

  return (
    <AuthContext.Provider value={{ user, loading, refreshUser, logout, isAdmin, isSuperAdmin }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
