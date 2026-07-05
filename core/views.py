from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
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
                "balance": loan.balance,
                "interest": loan.interest,
                "repayment_months": loan.repayment_months,
                "status": loan.status,
             }
             for loan in loans
          ],

        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "created_at": t.created_at,
            }
            for t in transactions
        ],
    })


# -----------------------------
# 💳 REPAY LOAN
# -----------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def repay_loan(request, loan_id):
    try:
        loan = Loan.objects.get(
            id=loan_id,
            user=request.user,
        )
    except Loan.DoesNotExist:
        return Response(
            {"error": "Loan not found"},
            status=404,
        )

    if loan.status != "approved":
        return Response(
            {"error": "Only approved loans can be repaid"},
            status=400,
        )

    try:
        amount = Decimal(
            str(request.data.get("amount", "0"))
        )
    except InvalidOperation:
        return Response(
            {"error": "Invalid amount"},
            status=400,
        )

    if amount <= 0:
        return Response(
            {"error": "Amount must be greater than zero"},
            status=400,
        )

    if amount > loan.balance:
        return Response(
            {"error": "Repayment exceeds outstanding balance"},
            status=400,
        )

    loan.balance -= amount

    if loan.balance == 0:
        loan.status = "repaid"

    loan.save()

    Transaction.objects.create(
        user=request.user,
        type="repayment",
        amount=amount,
    )

    return Response({
        "message": "Repayment successful",
        "balance": loan.balance,
        "status": loan.status,
    })

# -----------------------------
# 📊 EXPORT TRANSACTIONS TO EXCEL
# -----------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_transactions_excel(request):

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transaction Statement"

    sheet["A1"] = "SACCO MANAGEMENT SYSTEM"
    sheet["A1"].font = Font(size=16, bold=True)

    sheet["A2"] = "Transaction Statement"
    sheet["A2"].font = Font(size=13, bold=True)

    sheet["A4"] = f"Member: {request.user.get_full_name() or request.user.username}"
    sheet["A5"] = "Generated: " + timezone.now().strftime("%d %B %Y %H:%M")

    sheet.append([])

    headers = ["ID", "Date", "Type", "Amount"]
    sheet.append(headers)

    header_row = 7

    for cell in sheet[header_row]:
        cell.font = Font(bold=True)

    transactions = Transaction.objects.filter(
        user=request.user
    ).order_by("-created_at")

    for transaction in transactions:
        sheet.append([
            transaction.id,
            transaction.created_at.strftime("%d/%m/%Y"),
            transaction.type.title(),
            float(transaction.amount),
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    response["Content-Disposition"] = (
        'attachment; filename="transactions.xlsx"'
    )
    sheet.append([])
    sheet.append(["Summary"])

    deposit_total = 0
    loan_total = 0
    repayment_total = 0

    for transaction in transactions:
        if transaction.type == "deposit":
            deposit_total += float(transaction.amount)
        elif transaction.type == "loan":
            loan_total += float(transaction.amount)
        elif transaction.type == "repayment":
            repayment_total += float(transaction.amount)

    sheet.append(["Total Deposits", deposit_total])
    sheet.append(["Total Loans", loan_total])
    sheet.append(["Total Repayments", repayment_total])

    for column in sheet.columns:
        length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[
            get_column_letter(column[0].column)
        ].width = length + 4

    workbook.save(response)

    return response
