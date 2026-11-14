// Registered route vocabulary. Navigation items below never point at a
// placeholder or grant permissions; Django remains authoritative.
export const ROUTES = Object.freeze({
  login: "/", register: "/register", forgotPassword: "/forgot-password",
  verifyOtp: "/verify-otp", resetPassword: "/reset-password",
  dashboard: "/dashboard", savings: "/savings", loans: "/loans",
  loanCalculator: "/loans/calculator",
  welfare: "/welfare", staffWelfare: "/staff/welfare",
  transactions: "/transactions", reports: "/reports", profile: "/profile",
  changePassword: "/change-password", notifications: "/notifications",
  idVerification: "/id-verification", transportCrew: "/transport/crew",
  transportOwner: "/transport/owner", transportOwnerVehicle: "/transport/owner/vehicles/:vehicleId",
  staffClerk: "/staff/clerk", staffClerkCash: "/staff/clerk/cash",
  staffClerkAssignments: "/staff/clerk/assignments", staffClerkIssues: "/staff/clerk/issues",
  staffCredit: "/staff/credit", staffTreasury: "/staff/treasury",
  staffSecretary: "/staff/secretary", staffChairman: "/staff/chairman",
  adminDashboard: "/admin/dashboard", adminAccess: "/admin/access",
  adminFinancialReports: "/admin/reports", adminMembers: "/admin/members",
  adminMemberDetail: "/admin/members/:id", adminLoans: "/admin/loans",
  adminStaff: "/admin/staff", adminAuditLog: "/admin/audit-log",
  adminSettings: "/admin/settings", adminAssets: "/admin/assets",
  adminExitRequests: "/admin/exit-requests", adminAudit: "/admin/audit",
  adminIdVerifications: "/admin/id-verifications", adminCrbChecks: "/admin/crb-checks",
  adminSasra: "/admin/sasra", adminArrears: "/admin/arrears",
  adminReconciliation: "/admin/reconciliation", adminTransport: "/admin/transport",
  adminTransportExpenses: "/admin/transport-expenses",
  secretaryMeetings: "/secretary/meetings",
  secretaryNotices: "/secretary/notices",
  secretaryApprovals: "/secretary/approvals",
  staffTreasuryWelfare: "/staff/treasury/welfare",
  staffWelfarePolicy: "/staff/welfare/policy",
});

const item = (id, to, icon, label, permission) => ({ id, to, icon, label, permission });
const group = (id, label, items) => ({ id, label, items });

export const NAVIGATION_GROUPS = Object.freeze([
  {
    workspace: "member",
    groups: [
      group("overview", "Overview", [item("dashboard", ROUTES.dashboard, "home", "Home", "accounts.read_own")]),
      group("accounts", "Accounts and credit", [
        item("savings", ROUTES.savings, "wallet", "Savings and shares", "accounts.read_own"),
        item("loans", ROUTES.loans, "bank", "Loans", "loans.read_own"),
        item("loan-calculator", ROUTES.loanCalculator, "receipt", "Loan calculator", "loans.read_own"),
        item("transactions", ROUTES.transactions, "receipt", "Transactions and statements", "statements.read_own"),
        item("reports", ROUTES.reports, "file", "Loan and dividend reports", "statements.read_own"),
      ]),
      group("account", "Account and security", [
        item("member-welfare", ROUTES.welfare, "heart", "Welfare", "welfare.read_own"),
        item("notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"),
        item("identity", ROUTES.idVerification, "shield", "Identity verification", "profile.read_own"),
        item("profile", ROUTES.profile, "user", "Profile and security", "profile.read_own"),
        item("password", ROUTES.changePassword, "lock", "Change password", "profile.read_own"),
      ]),
    ],
  },
  {
    workspace: "welfare_officer",
    groups: [group("welfare-review", "Welfare", [
      item("welfare-requests", ROUTES.staffWelfare, "heart", "Support requests", "welfare.review"),
      item("welfare-policy", ROUTES.staffWelfarePolicy, "settings", "Welfare policy", "welfare.review"),
    ])],
  },
  {
    workspace: "crew",
    groups: [
      group("shift", "Transport operations", [item("crew-shift", ROUTES.transportCrew, "bus", "My shift and collections", "transport.read_assigned")]),
      group("crew-member", "Member services", [
        item("crew-dashboard", ROUTES.dashboard, "home", "Member home", "accounts.read_own"),
        item("crew-savings", ROUTES.savings, "wallet", "My accounts", "accounts.read_own"),
        item("crew-loans", ROUTES.loans, "bank", "My loans", "loans.read_own"),
      ]),
      group("crew-account", "Account", [
        item("crew-notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"),
        item("crew-profile", ROUTES.profile, "user", "Profile", "profile.read_own"),
      ]),
    ],
  },
  {
    workspace: "owner",
    groups: [
      group("owner-transport", "My vehicles", [item("owner-home", ROUTES.transportOwner, "truck", "Vehicle overview", "transport.read_owned")]),
      group("owner-member", "Member services", [
        item("owner-dashboard", ROUTES.dashboard, "home", "Member home", "accounts.read_own"),
        item("owner-accounts", ROUTES.savings, "wallet", "My accounts", "accounts.read_own"),
      ]),
    ],
  },
  {
    workspace: "staff",
    groups: [group("administration", "Administration", [
      item("admin-home", ROUTES.adminDashboard, "home", "System overview", "staff.manage"),
      item("access", ROUTES.adminAccess, "shield", "Role and duty assignments", "staff.manage"),
      item("staff", ROUTES.adminStaff, "users", "Staff accounts", "staff.manage"),
      item("transport-management", ROUTES.adminTransport, "truck", "Transport management", "staff.manage"),
      item("admin-welfare-policy", ROUTES.staffWelfarePolicy, "settings", "Welfare policy", "staff.manage"),
      item("settings", ROUTES.adminSettings, "settings", "Application settings", "staff.manage"),
      item("assets", ROUTES.adminAssets, "bank", "Asset registry", "staff.manage"),
      item("exit-requests", ROUTES.adminExitRequests, "file", "Exit requests", "staff.manage"),
      item("audit-rules", ROUTES.adminAudit, "shield", "Audit controls", "staff.manage"),
      item("sasra", ROUTES.adminSasra, "file", "SASRA reports", "staff.manage"),
      item("audit-log", ROUTES.adminAuditLog, "receipt", "Audit log", "audit.log.read"),
    ])],
  },
  {
    workspace: "clerk",
    groups: [
      group("clerk-operations", "Assigned duties", [
        item("clerk-home", ROUTES.staffClerk, "home", "Clerk overview", "transport.read_duties"),
        item("clerk-assignments", ROUTES.staffClerkAssignments, "truck", "Assigned transport work", "transport.assignments.manage_assigned"),
        item("clerk-issues", ROUTES.staffClerkIssues, "alert", "Assignment issues", "transport.issues.review_assigned"),
        item("clerk-cash", ROUTES.staffClerkCash, "receipt", "Cash handovers", "transport.cash_confirm_assigned"),
      ]),
      group("clerk-account", "Account", [item("clerk-notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"), item("clerk-profile", ROUTES.profile, "user", "Profile", "profile.read_own")]),
    ],
  },
  {
    workspace: "credit_officer",
    groups: [
      group("credit-review", "Credit review", [
        item("credit-home", ROUTES.staffCredit, "home", "Credit overview", "loans.appraise_assigned"),
        item("credit-applications", ROUTES.adminLoans, "bank", "Assigned applications", "loans.appraise_assigned"),
        item("credit-arrears", ROUTES.adminArrears, "alert", "Arrears review", "loans.appraise_assigned"),
        item("credit-reports", ROUTES.adminCrbChecks, "shield", "Credit report review", "loans.appraise_assigned"),
      ]),
      group("credit-account", "Account", [item("credit-notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"), item("credit-profile", ROUTES.profile, "user", "Profile", "profile.read_own")]),
    ],
  },
  {
    workspace: "treasurer",
    groups: [
      group("treasury-work", "Treasury", [
        item("treasury-home", ROUTES.staffTreasury, "home", "Treasury overview", "payments.reconcile"),
        item("treasury-payments", ROUTES.adminReconciliation, "receipt", "Payment reconciliation", "payments.reconcile"),
        item("treasury-welfare", ROUTES.staffTreasuryWelfare, "heart", "Welfare payout queue", "payments.reconcile"),
        item("treasury-expenses", ROUTES.adminTransportExpenses, "wallet", "Expense review", "transport.expenses.review"),
        item("treasury-reports", ROUTES.adminFinancialReports, "file", "Financial reports", "reports.financial.read"),
      ]),
      group("treasury-account", "Account", [item("treasury-notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"), item("treasury-profile", ROUTES.profile, "user", "Profile", "profile.read_own")]),
    ],
  },
  {
    workspace: "secretary",
    groups: [
      group("secretariat-work", "Membership", [
        item("secretary-home", ROUTES.staffSecretary, "home", "Secretary overview", "members.review"),
        item("secretary-members", ROUTES.adminMembers, "users", "Membership review", "members.review"),
        item("secretary-approvals", ROUTES.secretaryApprovals, "users", "Membership approvals", "membership.approve"),
        item("secretary-documents", ROUTES.adminIdVerifications, "id", "Document review", "kyc.review"),
        item("secretary-meetings", ROUTES.secretaryMeetings, "file", "Meetings", "members.review"),
        item("secretary-notices", ROUTES.secretaryNotices, "bell", "Member notices", "members.review"),
      ]),
      group("secretary-account", "Account", [item("secretary-notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"), item("secretary-profile", ROUTES.profile, "user", "Profile", "profile.read_own")]),
    ],
  },
  {
    workspace: "chairman",
    groups: [
      group("chairman-overview", "Cooperative oversight", [
        item("chairman-home", ROUTES.staffChairman, "home", "Oversight overview", "operations.summary.read"),
        item("chairman-approvals", ROUTES.adminLoans, "bank", "Assigned loan decisions", "loans.approve_assigned"),
        item("chairman-members", ROUTES.adminMembers, "users", "Members", "members.review"),
        item("chairman-transport", ROUTES.adminTransport, "truck", "Transport", "staff.manage"),
      ]),
      group("chairman-account", "Account", [item("chairman-notifications", ROUTES.notifications, "bell", "Notifications", "notifications.read_own"), item("chairman-profile", ROUTES.profile, "user", "Profile", "profile.read_own")]),
    ],
  },
  { workspace: "kyc_reviewer", groups: [group("kyc-review", "Identity review", [item("kyc-home", ROUTES.adminIdVerifications, "id", "Identity documents", "kyc.review")])] },
]);

export function hasPermission(user, code) {
  return Array.isArray(user?.permissions) && user.permissions.includes(code);
}

export function navigationFor(user, workspaceId) {
  const workspace = NAVIGATION_GROUPS.find((entry) => entry.workspace === workspaceId);
  if (!workspace) return [];
  return workspace.groups
    .map((entry) => ({ ...entry, items: entry.items.filter((link) => link.permission && hasPermission(user, link.permission)) }))
    .filter((entry) => entry.items.length > 0);
}

export function searchablePages(user) {
  const workspaceIds = new Set(Array.isArray(user?.workspaces) ? user.workspaces.map((ws) => ws.id) : []);
  const pages = NAVIGATION_GROUPS.filter((entry) => workspaceIds.has(entry.workspace))
    .flatMap((entry) => entry.groups.flatMap((navGroup) => navGroup.items))
    .filter((link) => link.permission && hasPermission(user, link.permission));
  const unique = new Map();
  pages.forEach((link) => { if (!unique.has(link.to)) unique.set(link.to, link); });
  return Array.from(unique.values());
}
