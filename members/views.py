from django.db.models import Sum

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Member
from core.models import Savings, Loan, Transaction


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def member_list(request):
    members = (
        Member.objects.select_related("user")
        .all()
        .order_by("member_number")
    )

    return Response([
        {
            "id": member.id,
            "member_number": member.member_number,
            "full_name": member.user.get_full_name(),
            "username": member.user.username,
            "email": member.user.email,
            "phone_number": member.phone_number,
            "county": member.county,
            "status": member.status,
        }
        for member in members
    ])


@api_view(["GET", "PUT","DELETE"])
@permission_classes([IsAuthenticated])
def member_detail(request, id):
    try:
        member = Member.objects.select_related("user").get(id=id)
    except Member.DoesNotExist:
        return Response(
            {"error": "Member not found"},
            status=404
        )

    # -----------------------------
    # UPDATE MEMBER
    # -----------------------------
    if request.method == "PUT":
        member.phone_number = request.data.get(
            "phone_number",
            member.phone_number,
        )

        member.county = request.data.get(
            "county",
            member.county,
        )

        member.address = request.data.get(
            "address",
            member.address,
        )

        member.status = request.data.get(
            "status",
            member.status,
        )

        member.save()

        return Response({
            "message": "Member updated successfully"
        })
    # -----------------------------
    # DELETE MEMBER
    # -----------------------------
    if request.method == "DELETE":
        user = member.user

        member.delete()
        user.delete()

        return Response({
            "message": "Member deleted successfully"
        })

    # -----------------------------
    # GET MEMBER DETAILS
    # -----------------------------
    user = member.user

    total_savings = (
        Savings.objects.filter(user=user)
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    loans = Loan.objects.filter(user=user)
    transactions = Transaction.objects.filter(user=user)

    return Response({
        "id": member.id,
        "member_number": member.member_number,
        "full_name": user.get_full_name(),
        "username": user.username,
        "email": user.email,
        "national_id": member.national_id,
        "phone_number": member.phone_number,
        "gender": member.gender,
        "date_of_birth": member.date_of_birth,
        "county": member.county,
        "address": member.address,
        "status": member.status,
        "date_joined": member.date_joined,

        "total_savings": total_savings,
        "total_loans": loans.count(),
        "approved_loans": loans.filter(status="approved").count(),
        "pending_loans": loans.filter(status="pending").count(),
        "rejected_loans": loans.filter(status="rejected").count(),
        "transactions": transactions.count(),
    })
