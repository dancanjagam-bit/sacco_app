from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response

from .models import Member
from .serializers import MemberSerializer, MemberUpdateSerializer
from core.models import Savings, Loan, Transaction
from accounts.models import Notification, AuditLog, MemberApproval

User = get_user_model()


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        from accounts.access import is_staff_manager
        return is_staff_manager(request.user)


class CanReviewMembers(BasePermission):
    def has_permission(self, request, view):
        from accounts.access import has_sacco_permission
        return has_sacco_permission(request.user, "members.review")


@api_view(["GET"])
@permission_classes([CanReviewMembers])
def member_list(request):
    page     = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 25))
    search   = request.query_params.get("search", "").strip()
    status_f = request.query_params.get("status", "all")

    qs = Member.objects.select_related("user").all()

    if search:
        qs = qs.filter(
            member_number__icontains=search
        ) | qs.filter(
            user__first_name__icontains=search
        ) | qs.filter(
            user__last_name__icontains=search
        ) | qs.filter(
            user__email__icontains=search
        ) | qs.filter(
            national_id__icontains=search
        ) | qs.filter(
            phone_number__icontains=search
        )

    if status_f != "all":
        qs = qs.filter(status=status_f)

    qs    = qs.order_by("member_number")
    total = qs.count()
    qs    = qs[(page - 1) * per_page: page * per_page]

    return Response({
        "total":   total,
        "page":    page,
        "pages":   (total + per_page - 1) // per_page,
        "results": MemberSerializer(qs, many=True).data,
    })


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def member_detail(request, id):
    from accounts.access import has_sacco_permission, is_staff_manager
    if request.method in ("GET", "PUT") and not has_sacco_permission(request.user, "members.review"):
        return Response({"detail": "Membership review permission required."}, status=403)
    if request.method == "DELETE" and not is_staff_manager(request.user):
        return Response({"detail": "System administration permission required."}, status=403)
    try:
        member = Member.objects.select_related("user").get(id=id)
    except Member.DoesNotExist:
        return Response({"error": "Member not found"}, status=404)

    if request.method == "PUT":
        old_status = member.status
        serializer = MemberUpdateSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data.get("status", old_status)
        if requested_status == "active" and old_status != "active" and not has_sacco_permission(request.user, "membership.approve"):
            return Response({"detail": "Membership approval permission is required to activate an applicant."}, status=403)
        serializer.save()
        new_status = member.status
        if old_status != new_status:
            if new_status == "suspended":
                # Suspend the Django user account too
                member.user.is_active = False
                member.user.save()
                Notification.send(
                    member.user, "Account Suspended",
                    "Your SACCO account has been suspended. Please contact the office.",
                    "error",
                )
            elif new_status == "active" and old_status == "suspended":
                member.user.is_active = True
                member.user.save()
                Notification.send(
                    member.user, "Account Reactivated",
                    "Your SACCO account has been reactivated. Welcome back!",
                    "success",
                )

        AuditLog.log(request.user, "member_update", f"Member {member.member_number}",
                     {"status": new_status}, request)
        return Response({"message": "Member updated successfully"})

    if request.method == "DELETE":
        user = member.user
        AuditLog.log(request.user, "member_delete", f"Member {member.member_number}", request=request)
        member.delete()
        user.delete()
        return Response({"message": "Member deleted successfully"})

    # GET — detail
    user  = member.user
    total_savings = (
        Savings.objects.filter(user=user).aggregate(total=Sum("amount"))["total"] or 0
    )
    loans        = Loan.objects.filter(user=user)
    transactions = Transaction.objects.filter(user=user)

    member_data = MemberSerializer(member).data
    member_data.update({
        "total_savings":   total_savings,
        "total_loans":     loans.count(),
        "approved_loans":  loans.filter(status="approved").count(),
        "pending_loans":   loans.filter(status="pending").count(),
        "rejected_loans":  loans.filter(status="rejected").count(),
        "repaid_loans":    loans.filter(status="repaid").count(),
        "transactions":    transactions.count(),
    })
    return Response(member_data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def suspend_member(request, id):
    from accounts.access import has_sacco_permission
    if not has_sacco_permission(request.user, "members.review"):
        return Response({"detail": "Membership review permission required."}, status=403)
    """Quick suspend/reinstate endpoint."""
    try:
        member = Member.objects.select_related("user").get(id=id)
    except Member.DoesNotExist:
        return Response({"error": "Member not found."}, status=404)

    action = request.data.get("action", "suspend")
    reason = request.data.get("reason", "")

    if action == "suspend":
        member.status          = "suspended"
        member.user.is_active  = False
        Notification.send(member.user, "Account Suspended",
                          f"Your account has been suspended. Reason: {reason or 'Contact SACCO office.'}",
                          "error")
    elif action == "reinstate":
        if not has_sacco_permission(request.user, "membership.approve"):
            return Response({"detail": "Membership approval permission is required to reinstate an account."}, status=403)
        member.status          = "active"
        member.user.is_active  = True
        Notification.send(member.user, "Account Reinstated",
                          "Your SACCO account is now active again.", "success")
    else:
        return Response({"error": "action must be 'suspend' or 'reinstate'."}, status=400)

    member.user.save()
    member.save()
    AuditLog.log(request.user, "member_suspend" if action == "suspend" else "member_update",
                 f"Member {member.member_number}", {"action": action, "reason": reason}, request)

    return Response({"message": f"Member {action}ed successfully."})


# ─────────────────────────────────────────────────────────────────────────────
# Member approval workflow (Item 1)
# ─────────────────────────────────────────────────────────────────────────────

def _approval_data(approval, include_profile=False):
    applicant = approval.applicant
    name = applicant.get_full_name().strip() or applicant.username
    data = {
        "id": approval.pk,
        "applicant_id": applicant.pk,
        "applicant_name": name,
        "applicant_username": applicant.username,
        "stage": approval.stage,
        "decision": approval.decision,
        "notes": approval.notes,
        "created_at": approval.created_at,
        "decided_at": approval.decided_at,
        "reviewer_name": (
            (approval.reviewer.get_full_name().strip() or approval.reviewer.username)
            if approval.reviewer else None
        ),
    }
    if include_profile:
        member = getattr(applicant, "member_profile", None)
        data.update({
            "member_number": getattr(member, "member_number", None),
            "national_id": getattr(member, "national_id", None),
            "phone_number": getattr(member, "phone_number", None),
            "member_status": getattr(member, "status", None),
        })
    return data


VALID_STAGES = {"secretary_review", "committee_approval", "activated", "rejected"}
VALID_DECISIONS = {"approved", "rejected"}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def member_approvals_list(request):
    from accounts.access import has_sacco_permission
    if request.method == "GET":
        if not has_sacco_permission(request.user, "members.review"):
            return Response({"detail": "Membership review permission required."}, status=403)
        qs = MemberApproval.objects.select_related("applicant", "reviewer").order_by("-created_at")
        stage_filter = request.query_params.get("stage", "")
        decision_filter = request.query_params.get("decision", "")
        if stage_filter:
            qs = qs.filter(stage=stage_filter)
        if decision_filter:
            qs = qs.filter(decision=decision_filter)
        return Response([_approval_data(a) for a in qs[:200]])

    # POST
    if not has_sacco_permission(request.user, "membership.approve"):
        return Response({"detail": "Membership approval permission required."}, status=403)
    applicant_id = request.data.get("applicant_id")
    stage = str(request.data.get("stage", "")).strip()
    decision = str(request.data.get("decision", "")).strip()
    notes = str(request.data.get("notes", "")).strip()

    if stage not in VALID_STAGES:
        return Response({"detail": "Stage must be secretary_review, committee_approval, activated, or rejected."}, status=400)
    if decision not in VALID_DECISIONS:
        return Response({"detail": "Decision must be approved or rejected."}, status=400)

    try:
        applicant = User.objects.get(pk=applicant_id)
    except (User.DoesNotExist, TypeError, ValueError):
        return Response({"detail": "Applicant not found."}, status=400)

    # Find or create the current approval step for this applicant/stage
    approval, _ = MemberApproval.objects.get_or_create(
        applicant=applicant,
        stage=stage,
        defaults={"decision": "pending"},
    )
    approval.decision = decision
    approval.notes = notes
    approval.reviewer = request.user
    approval.decided_at = timezone.now()
    approval.save(update_fields=["decision", "notes", "reviewer", "decided_at"])

    if decision == "approved":
        if stage == "secretary_review":
            # Advance to committee_approval
            MemberApproval.objects.get_or_create(
                applicant=applicant,
                stage="committee_approval",
                defaults={"decision": "pending"},
            )
        elif stage == "committee_approval":
            # Activate the member
            MemberApproval.objects.get_or_create(
                applicant=applicant,
                stage="activated",
                defaults={"decision": "approved", "reviewer": request.user, "decided_at": timezone.now()},
            )
            member = Member.objects.filter(user=applicant).first()
            if member:
                member.status = "active"
                member.save(update_fields=["status"])
                if not applicant.is_active:
                    applicant.is_active = True
                    applicant.save(update_fields=["is_active"])
            Notification.send(
                applicant,
                "Membership Approved",
                "Your membership application has been approved. Welcome to the cooperative!",
                "success",
            )
            AuditLog.log(request.user, "member_update", f"User #{applicant.pk} activated via committee_approval", {
                "operation": "member_activated", "stage": stage,
            }, request)
    else:
        # Rejected at any stage
        AuditLog.log(request.user, "member_update", f"User #{applicant.pk} rejected at {stage}", {
            "operation": "member_rejected", "stage": stage, "notes": notes[:200],
        }, request)

    if decision == "approved" and stage == "secretary_review":
        AuditLog.log(request.user, "member_create", f"User #{applicant.pk} advanced to committee_approval", {
            "operation": "member_advanced", "stage": "committee_approval",
        }, request)

    return Response(_approval_data(approval), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def member_approval_detail(request, approval_id):
    from accounts.access import has_sacco_permission
    if not has_sacco_permission(request.user, "members.review"):
        return Response({"detail": "Membership review permission required."}, status=403)
    try:
        approval = MemberApproval.objects.select_related("applicant", "reviewer").get(pk=approval_id)
    except MemberApproval.DoesNotExist:
        return Response({"detail": "Approval record not found."}, status=404)
    return Response(_approval_data(approval, include_profile=True))
