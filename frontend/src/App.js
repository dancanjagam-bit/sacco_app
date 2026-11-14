import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import { SaccoProvider } from "./context/SaccoContext";
import AdminRoute from "./components/AdminRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import { ROUTES } from "./navigation/routes";

// Auth pages
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import VerifyOTP from "./pages/VerifyOTP";
import ResetPassword from "./pages/ResetPassword";

// Member pages
import Dashboard from "./pages/Dashboard";
import Savings from "./pages/Savings";
import Loans from "./pages/Loans";
import Transactions from "./pages/Transactions";
import Reports from "./pages/Reports";
import Profile from "./pages/Profile";
import ChangePassword from "./pages/ChangePassword";
import Notifications from "./pages/Notifications";
import IDVerificationStatus from "./pages/IDVerificationStatus";

// Admin pages
import AdminLoans from "./pages/AdminLoans";
import AdminMembers from "./pages/AdminMembers";
import MemberProfile from "./pages/MemberProfile";
import AdminStaff from "./pages/AdminStaff";
import AuditLog from "./pages/AuditLog";
import AdminSettings from "./pages/AdminSettings";
import AdminAssets from "./pages/AdminAssets";
import AdminExitRequests from "./pages/AdminExitRequests";
import AdminAudit from "./pages/AdminAudit";
import AdminIDVerifications from "./pages/AdminIDVerifications";
import AdminCRBChecks from "./pages/AdminCRBChecks";
import AdminSASRA from "./pages/AdminSASRA";
import AdminArrears from "./pages/AdminArrears";
import TransportCrew from "./pages/TransportCrew";
import TransportOwner from "./pages/TransportOwner";
import TransportOperations from "./pages/TransportOperations";
import TransportReconciliation from "./pages/TransportReconciliation";
import TransportExpenseReview from "./pages/TransportExpenseReview";
import StaffWorkspaceDashboard from "./pages/StaffWorkspaceDashboard";
import AdminAccess from "./pages/AdminAccess";
import TransportClerkCash from "./pages/TransportClerkCash";
import StaffFinancialReports from "./pages/StaffFinancialReports";
import TransportClerkAssignments from "./pages/TransportClerkAssignments";
import TransportClerkIssues from "./pages/TransportClerkIssues";
import ChairmanDashboard from "./pages/ChairmanDashboard";
import LoanCalculator from "./pages/LoanCalculator";
import SecretaryMeetings from "./pages/SecretaryMeetings";
import SecretaryNotices from "./pages/SecretaryNotices";
import SecretaryApprovals from "./pages/SecretaryApprovals";
import TreasuryWelfareQueue from "./pages/TreasuryWelfareQueue";
import WelfarePolicy from "./pages/WelfarePolicy";
import Welfare from "./pages/Welfare";
import WelfareOfficer from "./pages/WelfareOfficer";

function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <SaccoProvider>
          <BrowserRouter>
            <Routes>
              {/* Public / Auth */}
              <Route path={ROUTES.login} element={<Login />} />
              <Route path={ROUTES.register} element={<Register />} />
              <Route path={ROUTES.forgotPassword} element={<ForgotPassword />} />
              <Route path={ROUTES.verifyOtp} element={<VerifyOTP />} />
              <Route path={ROUTES.resetPassword} element={<ResetPassword />} />

              {/* Member pages */}
              <Route path={ROUTES.dashboard} element={<ProtectedRoute requiredPermission="accounts.read_own"><Dashboard /></ProtectedRoute>} />
              <Route path={ROUTES.savings} element={<ProtectedRoute requiredPermission="accounts.read_own"><Savings /></ProtectedRoute>} />
              <Route path={ROUTES.loans} element={<ProtectedRoute requiredPermission="loans.read_own"><Loans /></ProtectedRoute>} />
              <Route path={ROUTES.loanCalculator} element={<ProtectedRoute requiredPermission="loans.read_own"><LoanCalculator /></ProtectedRoute>} />
              <Route path={ROUTES.welfare} element={<ProtectedRoute requiredPermission="welfare.read_own"><Welfare /></ProtectedRoute>} />
              <Route path={ROUTES.transactions} element={<ProtectedRoute requiredPermission="statements.read_own"><Transactions /></ProtectedRoute>} />
              <Route path={ROUTES.reports} element={<ProtectedRoute requiredPermission="statements.read_own"><Reports /></ProtectedRoute>} />
              <Route path={ROUTES.profile} element={<ProtectedRoute requiredPermission="profile.read_own"><Profile /></ProtectedRoute>} />
              <Route path={ROUTES.changePassword} element={<ProtectedRoute requiredPermission="profile.read_own"><ChangePassword /></ProtectedRoute>} />
              <Route path={ROUTES.notifications} element={<ProtectedRoute requiredPermission="notifications.read_own"><Notifications /></ProtectedRoute>} />
              <Route path={ROUTES.idVerification} element={<ProtectedRoute requiredPermission="profile.read_own"><IDVerificationStatus /></ProtectedRoute>} />
              <Route path={ROUTES.transportCrew} element={<ProtectedRoute requiredPermission="transport.read_assigned"><TransportCrew /></ProtectedRoute>} />
              <Route path={ROUTES.transportOwner} element={<ProtectedRoute requiredPermission="transport.read_owned"><TransportOwner /></ProtectedRoute>} />
              <Route path={ROUTES.transportOwnerVehicle} element={<ProtectedRoute requiredPermission="transport.read_owned"><TransportOwner /></ProtectedRoute>} />

              {/* Staff workspaces. These routes reflect the server's permission snapshot. */}
              <Route path={ROUTES.staffClerk} element={<ProtectedRoute requiredPermission="transport.read_duties"><StaffWorkspaceDashboard workspace="clerk" /></ProtectedRoute>} />
              <Route path={ROUTES.staffClerkAssignments} element={<ProtectedRoute requiredPermission="transport.assignments.manage_assigned"><TransportClerkAssignments /></ProtectedRoute>} />
              <Route path={ROUTES.staffClerkIssues} element={<ProtectedRoute requiredPermission="transport.issues.review_assigned"><TransportClerkIssues /></ProtectedRoute>} />
              <Route path={ROUTES.staffClerkCash} element={<ProtectedRoute requiredPermission="transport.cash_confirm_assigned"><TransportClerkCash /></ProtectedRoute>} />
              <Route path={ROUTES.staffCredit} element={<ProtectedRoute requiredPermission="loans.appraise_assigned"><StaffWorkspaceDashboard workspace="credit_officer" /></ProtectedRoute>} />
              <Route path={ROUTES.staffTreasury} element={<ProtectedRoute requiredPermission="payments.reconcile"><StaffWorkspaceDashboard workspace="treasurer" /></ProtectedRoute>} />
              <Route path={ROUTES.staffSecretary} element={<ProtectedRoute requiredPermission="members.review"><StaffWorkspaceDashboard workspace="secretary" /></ProtectedRoute>} />
              <Route path={ROUTES.staffChairman} element={<ProtectedRoute requiredPermission="operations.summary.read"><ChairmanDashboard /></ProtectedRoute>} />
              <Route path={ROUTES.staffWelfare} element={<ProtectedRoute requiredPermission="welfare.review"><WelfareOfficer /></ProtectedRoute>} />
              <Route path={ROUTES.secretaryMeetings} element={<ProtectedRoute requiredPermission="members.review"><SecretaryMeetings /></ProtectedRoute>} />
              <Route path={ROUTES.secretaryNotices} element={<ProtectedRoute requiredPermission="members.review"><SecretaryNotices /></ProtectedRoute>} />
              <Route path={ROUTES.secretaryApprovals} element={<ProtectedRoute requiredPermission="membership.approve"><SecretaryApprovals /></ProtectedRoute>} />
              <Route path={ROUTES.staffTreasuryWelfare} element={<ProtectedRoute requiredPermission="payments.reconcile"><TreasuryWelfareQueue /></ProtectedRoute>} />
              <Route path={ROUTES.staffWelfarePolicy} element={<ProtectedRoute requiredPermission={["welfare.review", "staff.manage"]}><WelfarePolicy /></ProtectedRoute>} />

              {/* Admin pages */}
              <Route path={ROUTES.adminDashboard} element={<AdminRoute requiredPermission="staff.manage"><StaffWorkspaceDashboard workspace="staff" /></AdminRoute>} />
              <Route path={ROUTES.adminAccess} element={<AdminRoute requiredPermission="staff.manage" superAdminOnly><AdminAccess /></AdminRoute>} />
              <Route path={ROUTES.adminFinancialReports} element={<AdminRoute requiredPermission="reports.financial.read"><StaffFinancialReports /></AdminRoute>} />
              <Route path={ROUTES.adminMembers} element={<AdminRoute requiredPermission="members.review"><AdminMembers /></AdminRoute>} />
              <Route path={ROUTES.adminMemberDetail} element={<AdminRoute requiredPermission="members.review"><MemberProfile /></AdminRoute>} />
              <Route path={ROUTES.adminLoans} element={<AdminRoute requiredPermission={["loans.appraise_assigned", "loans.approve_assigned"]}><AdminLoans /></AdminRoute>} />

              {/* Super-admin only */}
              <Route path={ROUTES.adminStaff} element={<AdminRoute requiredPermission="staff.manage" superAdminOnly><AdminStaff /></AdminRoute>} />
              <Route path={ROUTES.adminAuditLog} element={<AdminRoute requiredPermission="audit.log.read" superAdminOnly><AuditLog /></AdminRoute>} />

              {/* Admin settings + assets */}
              <Route path={ROUTES.adminSettings} element={<AdminRoute requiredPermission="staff.manage"><AdminSettings /></AdminRoute>} />
              <Route path={ROUTES.adminAssets} element={<AdminRoute requiredPermission="staff.manage"><AdminAssets /></AdminRoute>} />
              <Route path={ROUTES.adminExitRequests} element={<AdminRoute requiredPermission="staff.manage"><AdminExitRequests /></AdminRoute>} />
              <Route path={ROUTES.adminAudit} element={<AdminRoute requiredPermission="staff.manage"><AdminAudit /></AdminRoute>} />
              <Route path={ROUTES.adminIdVerifications} element={<AdminRoute requiredPermission="kyc.review"><AdminIDVerifications /></AdminRoute>} />
              <Route path={ROUTES.adminCrbChecks} element={<AdminRoute requiredPermission="loans.appraise_assigned"><AdminCRBChecks /></AdminRoute>} />
              <Route path={ROUTES.adminSasra} element={<AdminRoute requiredPermission="staff.manage"><AdminSASRA /></AdminRoute>} />
              <Route path={ROUTES.adminArrears} element={<ProtectedRoute requiredPermission="loans.appraise_assigned"><AdminArrears /></ProtectedRoute>} />
              <Route path={ROUTES.adminReconciliation} element={<AdminRoute requiredPermission="payments.reconcile"><TransportReconciliation /></AdminRoute>} />
              <Route path={ROUTES.adminTransport} element={<AdminRoute requiredPermission="staff.manage"><TransportOperations /></AdminRoute>} />
              <Route path={ROUTES.adminTransportExpenses} element={<AdminRoute requiredPermission="transport.expenses.review"><TransportExpenseReview /></AdminRoute>} />

              {/* Catch-all */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </SaccoProvider>
      </ToastProvider>
    </AuthProvider>
  );
}

export default App;
