from rest_framework.permissions import BasePermission

from accounts.access import has_sacco_permission
from .services import _authorized_accountant, is_accounting_superadmin


def can_read_accounting(user):
    return has_sacco_permission(user, "accounting.read") or _authorized_accountant(user)


class CanReadAccounting(BasePermission):
    message = "Accounting read access is required."

    def has_permission(self, request, view):
        return can_read_accounting(request.user)


class IsActiveAccountant(BasePermission):
    message = "An active accountant or superadministrator is required."

    def has_permission(self, request, view):
        return _authorized_accountant(request.user)


class IsAccountingSuperAdmin(BasePermission):
    message = "An active superadministrator is required."

    def has_permission(self, request, view):
        return is_accounting_superadmin(request.user)
