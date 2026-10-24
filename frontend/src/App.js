import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AdminRoute from "./components/AdminRoute";

// Auth pages
import Login         from "./pages/Login";
import Register      from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import VerifyOTP     from "./pages/VerifyOTP";
import ResetPassword from "./pages/ResetPassword";

// Member pages
import Dashboard     from "./pages/Dashboard";
import Savings       from "./pages/Savings";
import Loans         from "./pages/Loans";
import Transactions  from "./pages/Transactions";
import Reports       from "./pages/Reports";
import Profile       from "./pages/Profile";
import ChangePassword from "./pages/ChangePassword";
import Notifications from "./pages/Notifications";

// Admin pages
import AdminDashboard from "./pages/AdminDashboard";
import AdminLoans     from "./pages/AdminLoans";
import AdminMembers   from "./pages/AdminMembers";
import MemberProfile  from "./pages/MemberProfile";
import AdminStaff     from "./pages/AdminStaff";
import AuditLog       from "./pages/AuditLog";
import AdminSettings  from "./pages/AdminSettings";
import AdminAssets    from "./pages/AdminAssets";
import AdminExitRequests from "./pages/AdminExitRequests";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", color: "#64748b", fontSize: "15px" }}>
        Loading...
      </div>
    );
  }
  return user ? children : <Navigate to="/" replace />;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* ── Public / Auth ───────────────────────────────────────────── */}
          <Route path="/"               element={<Login />} />
          <Route path="/register"       element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/verify-otp"     element={<VerifyOTP />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* ── Member pages ─────────────────────────────────────────────── */}
          <Route path="/dashboard"      element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/savings"        element={<ProtectedRoute><Savings /></ProtectedRoute>} />
          <Route path="/loans"          element={<ProtectedRoute><Loans /></ProtectedRoute>} />
          <Route path="/transactions"   element={<ProtectedRoute><Transactions /></ProtectedRoute>} />
          <Route path="/reports"        element={<ProtectedRoute><Reports /></ProtectedRoute>} />
          <Route path="/profile"        element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          <Route path="/change-password" element={<ProtectedRoute><ChangePassword /></ProtectedRoute>} />
          <Route path="/notifications"  element={<ProtectedRoute><Notifications /></ProtectedRoute>} />

          {/* ── Admin pages ───────────────────────────────────────────────── */}
          <Route path="/admin/dashboard" element={<AdminRoute><AdminDashboard /></AdminRoute>} />
          <Route path="/admin/members"   element={<AdminRoute><AdminMembers /></AdminRoute>} />
          <Route path="/admin/members/:id" element={<AdminRoute><MemberProfile /></AdminRoute>} />
          <Route path="/admin/loans"     element={<AdminRoute><AdminLoans /></AdminRoute>} />

          {/* ── Super-admin only pages ────────────────────────────────────── */}
          <Route path="/admin/staff"     element={<AdminRoute superAdminOnly><AdminStaff /></AdminRoute>} />
          <Route path="/admin/audit-log" element={<AdminRoute superAdminOnly><AuditLog /></AdminRoute>} />

          {/* ── Admin settings + assets ─────────────────────────────────────── */}
          <Route path="/admin/settings" element={<AdminRoute><AdminSettings /></AdminRoute>} />
          <Route path="/admin/assets"   element={<AdminRoute><AdminAssets /></AdminRoute>} />
          <Route path="/admin/exit-requests" element={<AdminRoute><AdminExitRequests /></AdminRoute>} />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
