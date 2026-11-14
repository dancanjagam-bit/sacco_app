"""Administrative APIs for explicit staff roles and time-bounded work scopes."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Loan
from core.transport_models import CrewAssignment, TransportAssignmentIssue, TransportRole, TransportRoleGrant, Vehicle
from .access import is_staff_manager, staff_roles_for_user
from .access import access_snapshot, active_staff_duties
from .governance_serializers import CooperativeMeetingInput, MemberNoticeInput
from .models import AuditLog, IDVerification, KYCSubmission, MemberApproval, StaffDutyAssignment, StaffProfile, StaffRoleGrant

User = get_user_model()

ROLE_FOR_DUTY = {
    "transport_assignment": "clerk",
    "cash_handover": "clerk",
    "transport_issue": "clerk",
    "loan_appraisal": "credit_officer",
    "loan_approval": "chairman",
}


def _schema_ready():
    try:
        StaffRoleGrant.objects.exists()
        StaffDutyAssignment.objects.exists()
        return True
    except (OperationalError, ProgrammingError):
        return False


def _manager_required(request):
    return request.user.is_authenticated and is_staff_manager(request.user)


def _display_name(user):
    name = user.get_full_name().strip()
    return name or user.get_username()


def _duty_scope(duty):
    if duty == "transport_assignment":
        return {"vehicle", "crew_assignment"}
    if duty == "cash_handover":
        return {"crew_assignment"}
    if duty == "transport_issue":
        return {"transport_issue"}
    if duty in {"loan_appraisal", "loan_approval"}:
        return {"loan"}
    return set()


def _scope_label(item):
    if item.vehicle_id:
        return f"Vehicle {item.vehicle.registration}"
    if item.crew_assignment_id:
        assignment = item.crew_assignment
        return f"Shift {assignment.id} · {assignment.vehicle_label} · {assignment.route_label}"
    if item.transport_issue_id:
        return f"Transport issue {item.transport_issue_id}"
    if item.loan_id:
        return f"Loan #{item.loan_id} · KES {item.loan.amount} · {item.loan.status}"
    return "No scope"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_access_overview(request):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    grants = StaffRoleGrant.objects.select_related("user", "granted_by", "revoked_by").order_by("user__username", "role", "-granted_at")[:1000]
    duties = StaffDutyAssignment.objects.select_related(
        "staff", "assigned_by", "vehicle", "crew_assignment", "transport_issue", "loan",
    ).order_by("staff__username", "duty", "-starts_at")[:2000]
    return Response({
        "roles": [{
            "id": row.id, "user_id": row.user_id, "username": row.user.username,
            "display_name": _display_name(row.user), "role": row.role,
            "active": row.active, "reason": row.reason,
            "granted_by": _display_name(row.granted_by), "granted_at": row.granted_at,
            "revoked_by": _display_name(row.revoked_by) if row.revoked_by else None,
            "revoked_at": row.revoked_at,
        } for row in grants],
        "duties": [{
            "id": row.id, "staff_id": row.staff_id, "username": row.staff.username,
            "display_name": _display_name(row.staff), "duty": row.duty,
            "scope": _scope_label(row), "active": row.active,
            "starts_at": row.starts_at, "ends_at": row.ends_at,
            "reason": row.reason, "assigned_by": _display_name(row.assigned_by),
        } for row in duties],
        "transport_roles": [{
            "id": row.id, "user_id": row.user_id, "username": row.user.username,
            "display_name": _display_name(row.user), "role": row.role,
            "active": row.active,
        } for row in TransportRole.objects.select_related("user").order_by("user__username", "role")[:1000]],
        "legacy_profiles": [{
            "id": row.id, "user_id": row.user_id, "username": row.user.username,
            "display_name": _display_name(row.user), "role": row.role, "status": row.status,
        } for row in StaffProfile.objects.select_related("user").order_by("user__username")[:1000]],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_access_users(request):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    query = str(request.query_params.get("q", "")).strip()
    if len(query) < 2:
        return Response({"results": []})
    users = User.objects.filter(is_active=True).filter(
        Q(username__icontains=query)
        | Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
    ).order_by("username")[:25]
    return Response({"results": [{"id": user.id, "username": user.username, "display_name": _display_name(user)} for user in users]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_access_scopes(request):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    duty = request.query_params.get("duty", "")
    scope_type = request.query_params.get("scope_type", "")
    if duty not in ROLE_FOR_DUTY:
        return Response({"detail": "Select a supported duty."}, status=400)
    if duty == "transport_assignment":
        if scope_type == "crew_assignment":
            rows = CrewAssignment.objects.filter(status__in=("scheduled", "active")).order_by("-starts_at")[:250]
            results = [{"id": row.id, "scope_type": "crew_assignment", "label": f"Shift {row.id} · {row.vehicle_label} · {row.route_label}"} for row in rows]
        else:
            results = [{"id": row.id, "scope_type": "vehicle", "label": f"Vehicle {row.registration}"} for row in Vehicle.objects.filter(active=True).order_by("registration")[:250]]
    elif duty == "cash_handover":
        rows = CrewAssignment.objects.filter(status__in=("active", "ended")).order_by("-starts_at")[:250]
        results = [{"id": row.id, "scope_type": "crew_assignment", "label": f"Shift {row.id} · {row.vehicle_label} · {row.route_label}"} for row in rows]
    elif duty == "transport_issue":
        rows = TransportAssignmentIssue.objects.filter(status="pending").order_by("created_at")[:250]
        results = [{"id": row.id, "scope_type": "transport_issue", "label": f"Issue {row.id} · {row.created_at:%Y-%m-%d}"} for row in rows]
    else:
        rows = Loan.objects.filter(status__in=("pending", "flagged")).order_by("-created_at")[:250]
        results = [{"id": row.id, "scope_type": "loan", "label": f"Loan #{row.id} · KES {row.amount} · {row.status}"} for row in rows]
    return Response({"results": results})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_role_grant(request):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    try:
        target = User.objects.get(pk=request.data.get("user_id"), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Choose an existing active account."}, status=400)
    if target.pk == request.user.pk:
        return Response({"detail": "You cannot grant a privileged workspace role to yourself."}, status=403)
    role = str(request.data.get("role", ""))
    if role not in dict(StaffRoleGrant.ROLE_CHOICES):
        return Response({"detail": "Choose a supported workspace role."}, status=400)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return Response({"detail": "A reason is required for every role grant."}, status=400)
    if StaffRoleGrant.objects.filter(user=target, role=role, active=True).exists():
        return Response({"detail": "This account already holds that role."}, status=409)
    try:
        with transaction.atomic():
            grant = StaffRoleGrant.objects.create(user=target, role=role, granted_by=request.user, reason=reason[:500])
            AuditLog.log(request.user, "other", f"Staff role {role} granted to account #{target.pk}", {"operation": "staff_role_granted", "role": role, "reason": reason[:500]}, request)
    except IntegrityError:
        return Response({"detail": "This account already holds that role."}, status=409)
    return Response({"id": grant.id, "role": grant.role, "active": True}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_role_grant(request):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    try:
        target = User.objects.get(pk=request.data.get("user_id"), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Choose an existing active account."}, status=400)
    if target.pk == request.user.pk:
        return Response({"detail": "You cannot grant a transport role to yourself."}, status=403)
    role = str(request.data.get("role", ""))
    if role not in dict(TransportRole.ROLE_CHOICES):
        return Response({"detail": "Choose owner, driver, or conductor."}, status=400)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return Response({"detail": "A reason is required for every role grant."}, status=400)
    try:
        with transaction.atomic():
            transport_role, created = TransportRole.objects.get_or_create(user=target, role=role, defaults={"active": True})
            if not transport_role.active:
                transport_role.active = True
                transport_role.save(update_fields=("active",))
            TransportRoleGrant.objects.get_or_create(user=target, role=role, defaults={"granted_by": request.user})
            AuditLog.log(request.user, "other", f"Transport role {role} granted to account #{target.pk}", {
                "operation": "transport_role_granted", "role": role, "reason": reason[:500],
            }, request)
    except IntegrityError:
        return Response({"detail": "This account already holds that transport role."}, status=409)
    return Response({"id": transport_role.id, "role": role, "active": True}, status=201 if created else 200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_role_revoke(request, role_id):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return Response({"detail": "A reason is required to revoke a transport role."}, status=400)
    with transaction.atomic():
        role = TransportRole.objects.select_for_update().filter(pk=role_id, active=True).first()
        if not role:
            return Response({"detail": "Active transport role not found."}, status=404)
        if role.user_id == request.user.pk:
            return Response({"detail": "You cannot revoke your own transport role."}, status=403)
        role.active = False
        role.save(update_fields=("active",))
        AuditLog.log(request.user, "other", f"Transport role {role.role} revoked from account #{role.user_id}", {
            "operation": "transport_role_revoked", "role": role.role, "reason": reason[:500],
        }, request)
    return Response({"id": role.id, "active": False})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_role_revoke(request, grant_id):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return Response({"detail": "A reason is required to revoke a role."}, status=400)
    with transaction.atomic():
        grant = StaffRoleGrant.objects.select_for_update().filter(pk=grant_id, active=True).first()
        if not grant:
            return Response({"detail": "Active role assignment not found."}, status=404)
        if grant.user_id == request.user.pk:
            return Response({"detail": "You cannot revoke your own privileged assignment."}, status=403)
        grant.active = False
        grant.revoked_by = request.user
        grant.revoked_at = timezone.now()
        grant.reason = f"{grant.reason}\nRevoked: {reason}"[:500]
        grant.save(update_fields=("active", "revoked_by", "revoked_at", "reason"))
        duty_kinds = [duty for duty, role in ROLE_FOR_DUTY.items() if role == grant.role]
        StaffDutyAssignment.objects.filter(staff=grant.user, duty__in=duty_kinds, active=True).update(active=False, ends_at=timezone.now())
        AuditLog.log(request.user, "other", f"Staff role {grant.role} revoked from account #{grant.user_id}", {"operation": "staff_role_revoked", "role": grant.role, "reason": reason[:500]}, request)
    return Response({"id": grant.id, "role": grant.role, "active": False})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_duty_assign(request):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    try:
        target = User.objects.get(pk=request.data.get("staff_id"), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Choose an existing active staff account."}, status=400)
    if target.pk == request.user.pk:
        return Response({"detail": "You cannot assign privileged work to yourself."}, status=403)
    duty = str(request.data.get("duty", ""))
    required_role = ROLE_FOR_DUTY.get(duty)
    if not required_role:
        return Response({"detail": "Choose a supported staff duty."}, status=400)
    if required_role not in staff_roles_for_user(target):
        return Response({"detail": "Grant the matching staff role before assigning work."}, status=409)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return Response({"detail": "A reason is required for every duty assignment."}, status=400)
    scope_type = str(request.data.get("scope_type", ""))
    if scope_type not in _duty_scope(duty):
        return Response({"detail": "The selected scope does not match this duty."}, status=400)
    raw_scope_id = request.data.get("scope_id")
    if not str(raw_scope_id or "").isdigit():
        return Response({"detail": "Choose a valid scoped record."}, status=400)
    scope_model = {
        "vehicle": Vehicle,
        "crew_assignment": CrewAssignment,
        "transport_issue": TransportAssignmentIssue,
        "loan": Loan,
    }[scope_type]
    scope = get_object_or_404(scope_model, pk=int(raw_scope_id))
    starts_at = parse_datetime(str(request.data.get("starts_at", ""))) if request.data.get("starts_at") else timezone.now()
    ends_at = parse_datetime(str(request.data.get("ends_at", ""))) if request.data.get("ends_at") else None
    if starts_at is None or (request.data.get("ends_at") and ends_at is None):
        return Response({"detail": "Use valid ISO date and time values for the duty period."}, status=400)

    fields = {"staff": target, "duty": duty, "assigned_by": request.user,
              "starts_at": starts_at, "ends_at": ends_at, "reason": reason[:500]}
    fields[scope_type] = scope
    candidate = StaffDutyAssignment(**fields)
    try:
        candidate.full_clean()
    except DjangoValidationError as exc:
        return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
    duplicate_filter = {"staff": target, "duty": duty, "active": True, scope_type: scope}
    if StaffDutyAssignment.objects.filter(**duplicate_filter).exists():
        return Response({"detail": "This active scoped duty is already assigned."}, status=409)
    with transaction.atomic():
        candidate.save()
        AuditLog.log(request.user, "other", f"Staff duty {duty} assigned to account #{target.pk}", {"operation": "staff_duty_assigned", "duty": duty, "scope_type": scope_type, "scope_id": scope.pk, "reason": reason[:500]}, request)
    return Response({"id": candidate.id, "duty": duty, "scope": _scope_label(candidate), "active": True}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_duty_revoke(request, assignment_id):
    if not _manager_required(request):
        return Response({"detail": "Staff access management permission required."}, status=403)
    if not _schema_ready():
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return Response({"detail": "A reason is required to end a duty assignment."}, status=400)
    with transaction.atomic():
        duty = StaffDutyAssignment.objects.select_for_update().filter(pk=assignment_id, active=True).first()
        if not duty:
            return Response({"detail": "Active duty assignment not found."}, status=404)
        if duty.staff_id == request.user.pk:
            return Response({"detail": "You cannot end your own privileged duty assignment."}, status=403)
        duty.active = False
        duty.ends_at = timezone.now()
        duty.reason = f"{duty.reason}\nEnded: {reason}"[:500]
        duty.save(update_fields=("active", "ends_at", "reason"))
        AuditLog.log(request.user, "other", f"Staff duty {duty.duty} ended for account #{duty.staff_id}", {"operation": "staff_duty_ended", "duty": duty.duty, "reason": reason[:500]}, request)
    return Response({"id": duty.id, "active": False})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_workspace_summary(request, workspace):
    """Small, non-identifying dashboard summaries scoped to the assigned role."""
    snapshot = access_snapshot(request.user)
    if workspace not in {item["id"] for item in snapshot["workspaces"]}:
        return Response({"detail": "This workspace is not assigned to your account."}, status=403)
    if workspace not in {"staff", "clerk", "credit_officer", "treasurer", "secretary", "chairman", "kyc_reviewer", "welfare_officer"}:
        return Response({"detail": "No staff summary is available for this workspace."}, status=404)
    if not snapshot.get("staff_role_grants_available", True):
        return Response({"detail": "Staff role and duty migrations are pending on this database."}, status=503)

    from core.transport_models import TransportAssignmentIssue, TransportPayment, TransportPaymentReviewEvent, Vehicle
    from core.models import Loan
    from members.models import Member

    metrics = []
    unavailable = []
    if workspace == "staff":
        role_count = StaffRoleGrant.objects.filter(active=True).count()
        duty_count = StaffDutyAssignment.objects.filter(active=True, starts_at__lte=timezone.now()).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now())).count()
        metrics = [
            {"id": "staff_roles", "label": "Active staff role grants", "value": role_count},
            {"id": "scoped_duties", "label": "Current scoped duties", "value": duty_count},
            {"id": "active_transport_roles", "label": "Active transport role grants", "value": TransportRole.objects.filter(active=True).count()},
        ]
        unavailable.append("This account-management workspace does not grant payment, credit approval, or identity-review authority.")
    elif workspace == "clerk":
        assigned = active_staff_duties(request.user, "transport_assignment")
        cash_assignments = active_staff_duties(request.user, "cash_handover").values_list("crew_assignment_id", flat=True)
        issue_ids = active_staff_duties(request.user, "transport_issue").values_list("transport_issue_id", flat=True)
        cash_waiting = TransportPayment.objects.filter(
            remittance__assignment_id__in=cash_assignments, method="cash", status="pending", confirmed_at__isnull=True,
        ).count()
        metrics = [
            {"id": "transport_assignments", "label": "Assigned transport scopes", "value": assigned.count()},
            {"id": "cash_handover", "label": "Cash handovers awaiting your count", "value": cash_waiting},
            {"id": "transport_issues", "label": "Assigned issues awaiting review", "value": TransportAssignmentIssue.objects.filter(pk__in=issue_ids, status="pending").count()},
        ]
    elif workspace == "credit_officer":
        loan_ids = active_staff_duties(request.user, "loan_appraisal").values_list("loan_id", flat=True)
        metrics = [
            {"id": "assigned_appraisals", "label": "Assigned loan appraisals", "value": Loan.objects.filter(pk__in=loan_ids).count()},
            {"id": "pending_appraisals", "label": "Pending assigned applications", "value": Loan.objects.filter(pk__in=loan_ids, status__in=("pending", "flagged")).count()},
        ]
    elif workspace == "treasurer":
        queue_count = TransportPayment.objects.filter(
            status__in=("pending", "needs_review", "unmatched"),
        ).count() + TransportPaymentReviewEvent.objects.filter(status="pending").count()
        from accounts.welfare_models import WelfarePayout
        welfare_pending = WelfarePayout.objects.filter(status__in=("awaiting_provider", "pending")).count()
        metrics = [
            {"id": "payment_queue", "label": "Payments needing reconciliation", "value": queue_count},
            {"id": "unallocated_receipts", "label": "Received receipts not yet allocated", "value": TransportPayment.objects.filter(confirmed_at__isnull=False, unallocated_amount__gt=0).count()},
            {"id": "welfare_pending_payouts", "label": "Welfare payouts awaiting confirmation", "value": welfare_pending},
        ]
        unavailable.append("Balanced double-entry financial reporting is not established in this application.")
    elif workspace == "secretary":
        from accounts.models import CooperativeMeeting, MemberNotice
        upcoming_meetings = CooperativeMeeting.objects.filter(
            status="scheduled", scheduled_at__gte=timezone.now()
        ).count()
        active_notices = MemberNotice.objects.filter(status="published").count()
        metrics = [
            {"id": "membership_reviews", "label": "Membership decisions waiting", "value": MemberApproval.objects.filter(decision="pending", stage="secretary_review").count()},
            {"id": "document_reviews", "label": "Identity documents needing review", "value": IDVerification.objects.filter(status__in=("submitted", "needs_review", "pending", "flagged")).count()},
            {"id": "upcoming_meetings", "label": "Upcoming meetings", "value": upcoming_meetings},
            {"id": "active_notices", "label": "Active member notices", "value": active_notices},
        ]
    elif workspace == "chairman":
        approval_ids = active_staff_duties(request.user, "loan_approval").values_list("loan_id", flat=True)
        metrics = [
            {"id": "member_records", "label": "Member records", "value": Member.objects.count()},
            {"id": "registered_vehicles", "label": "Registered vehicles", "value": Vehicle.objects.count()},
            {"id": "assigned_decisions", "label": "Loan decisions assigned to you", "value": Loan.objects.filter(pk__in=approval_ids, status="pending").count()},
        ]
        unavailable.append("Formal voting and approval of minutes are not implemented yet.")
    elif workspace == "welfare_officer":
        from accounts.welfare_models import WelfareRequest, WelfarePayout, WelfarePolicy
        from accounting.models import JournalLine
        from django.db.models import Sum
        from decimal import Decimal
        base = WelfareRequest.objects.all()
        fund_account_qs = JournalLine.objects.filter(
            account__system_key="welfare_contributions",
            entry__status="posted", entry__reversal_entry__isnull=True,
        )
        fund_credits = fund_account_qs.aggregate(total=Sum("credit"))["total"] or Decimal("0")
        fund_debits = fund_account_qs.aggregate(total=Sum("debit"))["total"] or Decimal("0")
        metrics = [
            {"id": "pending_cases", "label": "Cases awaiting review", "value": base.filter(status="submitted").count()},
            {"id": "needs_info", "label": "Cases needing information", "value": base.filter(status="needs_information").count()},
            {"id": "approved_payouts", "label": "Approved payouts pending confirmation", "value": WelfarePayout.objects.filter(status__in=("awaiting_provider", "pending")).count()},
            {"id": "pooled_fund", "label": "Pooled welfare fund balance (KES)", "value": str(fund_credits - fund_debits)},
        ]
        unavailable.append("Payouts require a configured external provider. This workspace never sends funds.")
    else:
        metrics = [{
            "id": "identity_reviews", "label": "Identity submissions needing review",
            "value": IDVerification.objects.filter(status__in=("submitted", "needs_review", "pending", "flagged")).count(),
        }]

    return Response({"workspace": workspace, "metrics": metrics, "unavailable": unavailable})



# ─────────────────────────────────────────────────────────────────────────────
# 📅  Secretary: Meeting management
# ─────────────────────────────────────────────────────────────────────────────
def _secretary_access(user):
    """Return True if user holds secretary role or is a system manager."""
    from .access import staff_roles_for_user, is_staff_manager
    return is_staff_manager(user) or "secretary" in staff_roles_for_user(user)


def _governance_input_error(serializer):
    field, errors = next(iter(serializer.errors.items()))
    return Response({"detail": f"{field.replace('_', ' ').capitalize()}: {errors[0]}"}, status=400)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def meetings_list(request):
    from .models import CooperativeMeeting
    if not _secretary_access(request.user):
        return Response({"detail": "Secretary role required."}, status=403)

    if request.method == "POST":
        serializer = CooperativeMeetingInput(data=request.data)
        if not serializer.is_valid():
            return _governance_input_error(serializer)
        with transaction.atomic():
            meeting = serializer.save(recorded_by=request.user)
            AuditLog.log(request.user, "other", f"Meeting #{meeting.id} created", {"title": meeting.title}, request)
        return Response(_meeting_data(meeting), status=201)

    qs = CooperativeMeeting.objects.all().order_by("-scheduled_at")
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return Response([_meeting_data(m) for m in qs[:100]])


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def meeting_detail(request, meeting_id):
    from .models import CooperativeMeeting
    if not _secretary_access(request.user):
        return Response({"detail": "Secretary role required."}, status=403)
    if request.method == "PATCH":
        with transaction.atomic():
            meeting = get_object_or_404(CooperativeMeeting.objects.select_for_update(), pk=meeting_id)
            serializer = CooperativeMeetingInput(meeting, data=request.data, partial=True)
            if not serializer.is_valid():
                return _governance_input_error(serializer)
            meeting = serializer.save()
            AuditLog.log(request.user, "other", f"Meeting #{meeting.id} updated", {
                "updated_fields": sorted(serializer.validated_data),
            }, request)
    else:
        meeting = get_object_or_404(CooperativeMeeting, pk=meeting_id)
    return Response(_meeting_data(meeting))


def _meeting_data(m):
    return {
        "id": m.id, "title": m.title, "meeting_type": m.meeting_type,
        "meeting_type_display": m.get_meeting_type_display(),
        "status": m.status, "status_display": m.get_status_display(),
        "scheduled_at": m.scheduled_at, "location": m.location,
        "agenda": m.agenda, "minutes": m.minutes, "quorum_met": m.quorum_met,
        "recorded_by": m.recorded_by.get_full_name() or m.recorded_by.username,
        "created_at": m.created_at, "updated_at": m.updated_at,
        "attendee_count": m.attendees.count() if hasattr(m, "attendees") else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 📢  Secretary: Member notices
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def notices_list(request):
    from .models import MemberNotice
    if not _secretary_access(request.user):
        return Response({"detail": "Secretary role required."}, status=403)

    if request.method == "POST":
        serializer = MemberNoticeInput(data=request.data)
        if not serializer.is_valid():
            return _governance_input_error(serializer)
        published_at = timezone.now() if serializer.validated_data.get("status") == "published" else None
        with transaction.atomic():
            notice = serializer.save(created_by=request.user, published_at=published_at)
            AuditLog.log(request.user, "other", f"Notice #{notice.id} created", {
                "title": notice.title, "status": notice.status,
            }, request)
        return Response(_notice_data(notice), status=201)

    qs = MemberNotice.objects.all().order_by("-created_at")
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return Response([_notice_data(n) for n in qs[:200]])


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def notice_detail(request, notice_id):
    from .models import MemberNotice
    if not _secretary_access(request.user):
        return Response({"detail": "Secretary role required."}, status=403)
    if request.method == "PATCH":
        with transaction.atomic():
            notice = get_object_or_404(MemberNotice.objects.select_for_update(), pk=notice_id)
            serializer = MemberNoticeInput(notice, data=request.data, partial=True)
            if not serializer.is_valid():
                return _governance_input_error(serializer)
            published_at = notice.published_at
            if serializer.validated_data.get("status") == "published" and notice.status != "published":
                published_at = timezone.now()
            notice = serializer.save(published_at=published_at)
            AuditLog.log(request.user, "other", f"Notice #{notice.id} updated", {
                "updated_fields": sorted(serializer.validated_data), "status": notice.status,
            }, request)
    else:
        notice = get_object_or_404(MemberNotice, pk=notice_id)
    return Response(_notice_data(notice))


def _notice_data(n):
    return {
        "id": n.id, "title": n.title, "body": n.body,
        "priority": n.priority, "status": n.status,
        "published_at": n.published_at, "expires_at": n.expires_at,
        "created_by": n.created_by.get_full_name() or n.created_by.username,
        "created_at": n.created_at, "updated_at": n.updated_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Item 7: Meeting attendance records
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def meeting_attendees(request, meeting_id):
    from .models import CooperativeMeeting, MeetingAttendee
    if not _secretary_access(request.user):
        return Response({"detail": "Secretary role required."}, status=403)
    meeting = get_object_or_404(CooperativeMeeting, pk=meeting_id)

    if request.method == "GET":
        rows = MeetingAttendee.objects.filter(meeting=meeting).select_related("user")
        return Response([{
            "id": row.pk,
            "name": row.name,
            "role": row.role,
            "present": row.present,
            "notes": row.notes,
            "user_id": row.user_id,
            "user_username": row.user.username if row.user else None,
        } for row in rows])

    # POST
    name = str(request.data.get("name", "")).strip()
    if not name:
        return Response({"detail": "Name is required."}, status=400)
    role = str(request.data.get("role", "")).strip()
    present = bool(request.data.get("present", True))
    notes = str(request.data.get("notes", "")).strip()
    user_id = request.data.get("user_id")
    linked_user = None
    if user_id:
        linked_user = User.objects.filter(pk=user_id, is_active=True).first()
        if not linked_user:
            return Response({"detail": "User not found."}, status=400)
        # Use the linked user's display name if name not explicitly supplied
        if not name:
            name = linked_user.get_full_name().strip() or linked_user.username

    with transaction.atomic():
        attendee = MeetingAttendee.objects.create(
            meeting=meeting,
            user=linked_user,
            name=name[:150],
            role=role[:100],
            present=present,
            notes=notes[:300],
            recorded_by=request.user,
        )
    return Response({
        "id": attendee.pk,
        "name": attendee.name,
        "role": attendee.role,
        "present": attendee.present,
        "notes": attendee.notes,
        "user_id": attendee.user_id,
        "user_username": attendee.user.username if attendee.user else None,
    }, status=201)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def meeting_attendee_delete(request, meeting_id, attendee_id):
    from .models import CooperativeMeeting, MeetingAttendee
    if not _secretary_access(request.user):
        return Response({"detail": "Secretary role required."}, status=403)
    attendee = MeetingAttendee.objects.filter(pk=attendee_id, meeting_id=meeting_id).first()
    if not attendee:
        return Response({"detail": "Attendee record not found."}, status=404)
    attendee.delete()
    return Response({"id": attendee_id, "deleted": True})
