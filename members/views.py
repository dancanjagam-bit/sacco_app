from django.db.models import Sum
from django.contrib.auth import get_user_model

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response

from .models import Member
from .serializers import MemberSerializer, MemberUpdateSerializer
from core.models import Savings, Loan, Transaction
from accounts.models import Notification, AuditLog

User = get_user_model()


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and (
                getattr(request.user, "is_admin", False)
                or request.user.is_staff
                or request.user.is_superuser
            )
        )


@api_view(["GET"])
@permission_classes([IsAdmin])
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
    try:
        member = Member.objects.select_related("user").get(id=id)
    except Member.DoesNotExist:
        return Response({"error": "Member not found"}, status=404)

    if request.method == "PUT":
        if not (request.user.is_staff or request.user.is_superuser or
                getattr(request.user, "is_admin", False)):
            return Response({"error": "Admin access required."}, status=403)

        old_status = member.status
        serializer = MemberUpdateSerializer(member, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
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
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"error": "Admin access required."}, status=403)

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
@permission_classes([IsAdmin])
def suspend_member(request, id):
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
