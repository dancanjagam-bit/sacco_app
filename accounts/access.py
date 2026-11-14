"""Server-produced workspace and capability snapshot.

The snapshot controls navigation only. API views must still call
``has_sacco_permission`` and apply the same object scope to their querysets.
System administration is deliberately separate from operational job roles.
"""
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError


WORKSPACES = {
    "member": {"id": "member", "label": "Member services", "short_label": "Member", "path": "/dashboard"},
    "crew": {"id": "crew", "label": "Transport crew", "short_label": "Crew", "path": "/transport/crew"},
    "owner": {"id": "owner", "label": "Vehicle owner", "short_label": "Owner", "path": "/transport/owner"},
    "clerk": {"id": "clerk", "label": "Transport clerk", "short_label": "Clerk", "path": "/staff/clerk"},
    "credit_officer": {"id": "credit_officer", "label": "Credit officer", "short_label": "Credit", "path": "/staff/credit"},
    "treasurer": {"id": "treasurer", "label": "Treasurer", "short_label": "Treasury", "path": "/staff/treasury"},
    "secretary": {"id": "secretary", "label": "Secretary", "short_label": "Secretary", "path": "/staff/secretary"},
    "chairman": {"id": "chairman", "label": "Chairman", "short_label": "Chair", "path": "/staff/chairman"},
    "welfare_officer": {"id": "welfare_officer", "label": "Welfare Officer", "short_label": "Welfare", "path": "/staff/welfare"},
    "kyc_reviewer": {"id": "kyc_reviewer", "label": "Identity review", "short_label": "KYC", "path": "/admin/id-verifications"},
    "staff": {"id": "staff", "label": "System administration", "short_label": "Admin", "path": "/admin/dashboard"},
}

ROLE_PERMISSIONS = {
    "welfare_officer": {"welfare.review"},
    "clerk": {
        "transport.read_duties", "transport.assignments.manage_assigned",
        "transport.cash_confirm_assigned", "transport.issues.review_assigned",
    },
    "credit_officer": {
        "loans.appraise_assigned", "loans.guarantors.read_assigned",
    },
    "treasurer": {
        "payments.reconcile", "accounting.read", "reports.financial.read",
        "transport.expenses.review",
    },
    "secretary": {
        "members.review", "kyc.review", "membership.approve",
    },
    "chairman": {
        "operations.summary.read", "reports.cooperative.read",
        "loans.approve_assigned",
    },
}

LEGACY_ROLE_MAP = {
    "loan_officer": "credit_officer",
    "accountant": "treasurer",
    "secretary": "secretary",
}

WORKSPACE_PRIORITY = (
    "staff", "chairman", "treasurer", "secretary", "credit_officer", "welfare_officer",
    "clerk", "owner", "crew", "member", "kyc_reviewer",
)


def _active_legacy_staff_profile(user):
    try:
        profile = user.staff_profile
    except Exception:
        return None
    return profile if profile.status == "active" else None


def _staff_role_codes(user):
    roles = set()
    role_schema_available = True
    try:
        from .models import StaffRoleGrant
        roles.update(StaffRoleGrant.objects.filter(user=user, active=True).values_list("role", flat=True))
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "no such table" not in message and "does not exist" not in message:
            raise
        # Existing local DBs may be intentionally held at the pre-workspace
        # schema while the migration is verified on a copy. Keep old paths
        # available, but do not manufacture any newly granted workspace.
        role_schema_available = False

    profile = _active_legacy_staff_profile(user)
    legacy_role = getattr(profile, "role", None)
    if legacy_role in LEGACY_ROLE_MAP:
        roles.add(LEGACY_ROLE_MAP[legacy_role])
    if legacy_role == "kyc_officer":
        roles.add("kyc_reviewer")
    return roles, role_schema_available, profile


def staff_roles_for_user(user):
    return _staff_role_codes(user)[0]


def is_staff_manager(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if bool(getattr(user, "is_superuser", False)):
        return True
    profile = _active_legacy_staff_profile(user)
    return bool(profile and profile.role == "superadmin")


def requires_staff_login_2fa(user):
    if any(bool(getattr(user, name, False)) for name in ("is_staff", "is_superuser", "is_admin")):
        return True
    roles, _, profile = _staff_role_codes(user)
    return bool(roles or profile)


def has_sacco_permission(user, permission):
    if not getattr(user, "is_authenticated", False):
        return False
    return permission in access_snapshot(user)["permissions"]


def active_staff_duties(user, duty=None):
    """Return only currently effective duty assignments for a staff user."""
    from django.utils import timezone
    from .models import StaffDutyAssignment

    now = timezone.now()
    queryset = StaffDutyAssignment.objects.filter(
        staff=user, active=True, starts_at__lte=now,
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    )
    if duty:
        queryset = queryset.filter(duty=duty)
    return queryset


def _workspace(workspace_id):
    return dict(WORKSPACES[workspace_id])


def access_snapshot(user, transport_roles=None):
    if not getattr(user, "is_authenticated", False):
        return {"permissions": [], "workspaces": [], "default_workspace": None, "staff_role_grants_available": True}

    permissions = {"notifications.read_own", "profile.read_own"}
    if bool(getattr(user, "is_member", False)):
        permissions.update({
            "accounts.read_own", "loans.read_own", "statements.read_own",
            "payments.initiate_own",
            "welfare.read_own",
        })

    roles, role_schema_available, profile = _staff_role_codes(user)
    legacy_role = getattr(profile, "role", None)
    for role in roles:
        permissions.update(ROLE_PERMISSIONS.get(role, set()))

    manager = is_staff_manager(user)
    if manager:
        permissions.update({"staff.manage", "audit.log.read"})

    # A legacy KYC officer keeps document review access without becoming a
    # membership approver or receiving the secretary workspace.
    if profile and profile.role == "kyc_officer":
        permissions.add("kyc.review")

    if transport_roles is None:
        from core.transport_models import TransportRole
        transport_roles = TransportRole.objects.filter(user=user, active=True).values_list("role", flat=True)
    transport_roles = set(transport_roles)
    if transport_roles.intersection({"driver", "conductor"}):
        permissions.add("transport.read_assigned")
    if "owner" in transport_roles:
        permissions.add("transport.read_owned")

    workspaces = []
    if bool(getattr(user, "is_member", False)):
        workspaces.append(_workspace("member"))
    if "transport.read_assigned" in permissions:
        workspaces.append(_workspace("crew"))
    if "transport.read_owned" in permissions:
        workspaces.append(_workspace("owner"))
    for role in ("clerk", "credit_officer", "treasurer", "secretary", "chairman", "welfare_officer"):
        if role in roles:
            workspaces.append(_workspace(role))
    if profile and profile.role == "kyc_officer":
        workspaces.append(_workspace("kyc_reviewer"))
    if manager:
        workspaces.append(_workspace("staff"))

    by_id = {item["id"]: item for item in workspaces}
    default_workspace = next((by_id[role] for role in WORKSPACE_PRIORITY if role in by_id), None)
    return {
        "permissions": sorted(permissions),
        "workspaces": workspaces,
        "default_workspace": default_workspace["id"] if default_workspace else None,
        "staff_role_grants_available": role_schema_available,
        "staff_role": legacy_role,
        "staff_roles": sorted(roles),
    }
