from rest_framework.permissions import BasePermission

from .access import has_sacco_permission, is_staff_manager


class HasSaccoPermission(BasePermission):
    """DRF permission backed by the same snapshot used for workspace routes."""
    permission_code = None

    def has_permission(self, request, view):
        return bool(self.permission_code and has_sacco_permission(request.user, self.permission_code))


class IsStaffManager(BasePermission):
    def has_permission(self, request, view):
        return is_staff_manager(request.user)


class CanAppraiseAssignedLoans(HasSaccoPermission):
    permission_code = "loans.appraise_assigned"


class CanDecideAssignedLoans(HasSaccoPermission):
    permission_code = "loans.approve_assigned"


class CanReconcilePayments(HasSaccoPermission):
    permission_code = "payments.reconcile"


class CanReadFinancialReports(HasSaccoPermission):
    permission_code = "reports.financial.read"


class CanReadCooperativeSummary(HasSaccoPermission):
    permission_code = "operations.summary.read"


class CanReviewMembers(HasSaccoPermission):
    permission_code = "members.review"


class CanReviewKYC(HasSaccoPermission):
    permission_code = "kyc.review"


class CanManageTransport(HasSaccoPermission):
    permission_code = "transport.manage"


class CanReviewTransportExpenses(HasSaccoPermission):
    permission_code = "transport.expenses.review"
