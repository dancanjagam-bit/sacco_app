from decimal import Decimal, InvalidOperation
from django.utils import timezone

from django.db.models import Sum

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response

from .models import Savings, Loan, Transaction


# -----------------------------
# 🛡️ ADMIN PERMISSION
# -----------------------------
class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, "is_admin") and
            request.user.is_admin
        )


# -----------------------------
# 💰 DEPOSIT SAVINGS
# -----------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deposit(request):
    try:
        amount = Decimal(str(request.data.get("amount", "0")))
    except InvalidOperation:
        return Response({"error": "Invalid amount"}, status=400)

    if amount <= 0:
        return Response({"error": "Amount must be greater than zero"}, status=400)

    Savings.objects.create(
        user=request.user,
        amount=amount
    )

    Transaction.objects.create(
        user=request.user,
        type="deposit",
        amount=amount
    )

    return Response({"message": "Deposit successful"})


# -----------------------------
# 🏦 APPLY LOAN
# -----------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_loan(request):
    try:
        amount = Decimal(str(request.data.get("amount", "0")))
    except InvalidOperation:
        return Response({"error": "Invalid amount"}, status=400)

    if amount <= 0:
        return Response({"error": "Amount must be greater than zero"}, status=400)

    repayment_months = request.data.get(
        "repayment_months",
        12
    )
    loan = Loan.objects.create(
        user=request.user,
        amount=amount,
        repayment_months=repayment_months,
        balance=amount,
    )

    Transaction.objects.create(
        user=request.user,
        type="loan",
        amount=amount
    )

    return Response({
        "message": "Loan applied",
        "loan_id": loan.id
    })


# -----------------------------
# 👮 APPROVE LOAN (ADMIN ONLY)
# -----------------------------
@api_view(["POST"])
@permission_classes([IsAdmin])
def approve_loan(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found"}, status=404)

    loan.status = "approved"

    loan.approved_by = request.user

    loan.approved_at = timezone.now()

    interest_amount = (
    loan.amount * loan.interest
    ) / Decimal("100")

    loan.balance = loan.amount + interest_amount

    loan.save()

    return Response({"message": "Loan approved"})

# -----------------------------
# ❌ REJECT LOAN (ADMIN ONLY)
# -----------------------------
@api_view(["POST"])
@permission_classes([IsAdmin])
def reject_loan(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found"}, status=404)

    loan.status = "rejected"
    loan.save()

    return Response({"message": "Loan rejected"})


# -----------------------------
# 📋 LIST PENDING LOANS (ADMIN ONLY)
# -----------------------------
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_loans(request):
    loans = Loan.objects.all().order_by("-created_at")

    return Response([
        {
            "id": loan.id,
            "member": loan.user.get_full_name() or loan.user.username,
            "amount": loan.amount,
            "interest": loan.interest,
            "repayment_months": loan.repayment_months,
            "balance": loan.balance,
            "status": loan.status,
            "created_at": loan.created_at,
            "approved_at": loan.approved_at,
            "approved_by": (
                loan.approved_by.get_full_name()
                if loan.approved_by
                else ""
            ),
        }
        for loan in loans
    ])


# -----------------------------
# 📊 DASHBOARD
# -----------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    user = request.user

    total_savings = (
        Savings.objects.filter(user=user)
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    loans = Loan.objects.filter(user=user).order_by("-id")
    transactions = Transaction.objects.filter(user=user).order_by("-id")

    return Response({
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,

        "total_savings": total_savings,
        "total_loans": loans.count(),
        "pending_loans": loans.filter(status="pending").count(),
        "approved_loans": loans.filter(status="approved").count(),

        "loans": [
            {
                "id": loan.id,
                "amount": loan.amount,
                "status": loan.status,
            }
            for loan in loans
        ],

        "transactions": [
            {
                "type": t.type,
                "amount": t.amount,
            }
            for t in transactions
        ],
    })
