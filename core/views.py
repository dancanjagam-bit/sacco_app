from decimal import Decimal
from django.utils import timezone
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from django.db.models import Sum, Count, Q, CharField
from django.db.models.functions import Cast
from django.db.models.functions import TruncMonth
from django.contrib.auth import get_user_model

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils.dateparse import parse_date

from .models import Savings, Loan, Transaction, LoanGuarantor
from .serializers import (
    SavingsSerializer,
    LoanApplicationSerializer,
    RepaymentSerializer,
    LoanSerializer,
    TransactionSerializer,
)
from .eligibility import (
    get_eligibility,
    get_interest_rate,
    get_valid_periods,
)
from accounts.models import Notification, AuditLog
from sacco.notifications import (
    send_deposit_confirmation,
    send_repayment_confirmation,
    send_loan_approved as deliver_loan_approved,
    send_loan_rejected as deliver_loan_rejected,
)
from .collateral import (
    get_withdrawable_balance,
    get_guarantor_pledges_detail,
    lock_collateral_on_approval,
    recalculate_collateral_release,
    check_disbursement_gate,
)
from .models import AssetCollateral, SACCOSettings, SASRAReport


# ─────────────────────────────────────────────────────────────────────────────
# 🛡️ Admin permission
# ─────────────────────────────────────────────────────────────────────────────
class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and (
                getattr(request.user, "is_admin", False)
                or request.user.is_staff
                or request.user.is_superuser
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# 💰 Deposit savings
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deposit(request):
    """
    Deposit to BOSA or FOSA.

    For regular members: ALL deposits must go through M-Pesa (Daraja STK push).
    Direct API deposits are blocked — the M-Pesa callback credits the account
    automatically after Safaricom confirms payment.

    For admin/staff: manual deposits are allowed (cash or bank transfer received
    at the SACCO office) and are audit-logged with a 'manual_cash' flag.
    """
    is_admin = (
        getattr(request.user, "is_admin", False)
        or request.user.is_staff
        or request.user.is_superuser
    )

    if not is_admin:
        return Response(
            {
                "error": (
                    "Direct deposits are not allowed. "
                    "Please use M-Pesa to deposit funds — "
                    "tap 'Pay via M-Pesa' on the Savings page."
                )
            },
            status=403,
        )

    # ── Admin manual deposit (cash / bank transfer received at office) ───────
    serializer = SavingsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount       = serializer.validated_data["amount"]
    account_type = serializer.validated_data.get("account_type", "fosa")

    # Allow admin to deposit on behalf of a specific member
    target_user_id = request.data.get("user_id")
    if target_user_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({"error": "Member not found."}, status=404)
    else:
        target_user = request.user

    Savings.objects.create(user=target_user, amount=amount, account_type=account_type)
    Transaction.objects.create(
        user=target_user, type="deposit", amount=amount,
        note=f"{account_type.upper()} manual deposit by {request.user.username}",
    )
    Notification.send(
        target_user, "Deposit Confirmed",
        f"KES {amount:,.2f} deposited to your {account_type.upper()} account by SACCO staff.",
        "success", "/savings",
    )
    AuditLog.log(
        request.user, "deposit",
        f"Member {target_user.username}",
        {"amount": float(amount), "account": account_type, "method": "manual_cash"},
        request,
    )
    total_after = float((
        Savings.objects.filter(user=target_user, account_type=account_type)
        .aggregate(t=Sum("amount"))["t"] or 0
    ))
    send_deposit_confirmation(target_user, float(amount), total_after)
    return Response({"message": f"Manual deposit to {account_type.upper()} successful."})


# ─────────────────────────────────────────────────────────────────────────────
# 📋 Loan eligibility check  (GET — no side effects)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def loan_eligibility(request):
    report = get_eligibility(request.user)

    return Response({
        "eligible":           report["eligible"],
        "consistent_months":  report["consistent_months"],
        "tier_label":         report["tier_label"],
        "multiplier":         float(report["multiplier"]),
        "interest_band":      report["interest_band"],
        "max_loan":           float(report["max_loan"]),
        "total_savings":      float(report["total_savings"]),
        "months_needed":      report["months_needed"],
        "next_tier_months":   report["next_tier_months"],
        "rejection_reason":   report["rejection_reason"],
        "min_monthly_amount": float(report["min_monthly_amount"]),
        "interest_rates":     report["interest_rates"],
        "months_detail": [
            {
                "month":     m["month"],
                "total":     float(m["total"]),
                "qualifies": m["qualifies"],
            }
            for m in report["months_detail"]
        ],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 🏦 Apply loan
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_loan(request):
    serializer = LoanApplicationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount           = serializer.validated_data["amount"]
    repayment_months = serializer.validated_data["repayment_months"]
    purpose          = serializer.validated_data.get("purpose", "personal")
    purpose_details  = serializer.validated_data.get("purpose_details", "")

    if repayment_months not in get_valid_periods():
        valid = get_valid_periods()
        return Response(
            {"error": f"Repayment period must be one of: {valid}."},
            status=400,
        )

    # ── Eligibility check ───────────────────────────────────────────────
    report = get_eligibility(request.user)

    if not report["eligible"]:
        return Response({"error": report["rejection_reason"]}, status=400)

    if amount > report["max_loan"]:
        return Response(
            {
                "error": (
                    f"Maximum loan for your tier ({report['tier_label']}) is "
                    f"KES {report['max_loan']:,.2f} "
                    f"({float(report['multiplier']):.0f}× your savings of "
                    f"KES {report['total_savings']:,.2f})."
                )
            },
            status=400,
        )

    # ── Duplicate checks ────────────────────────────────────────────────
    if Loan.objects.filter(user=request.user, status="pending").exists():
        return Response(
            {"error": "You already have a pending loan application."},
            status=400,
        )

    if Loan.objects.filter(user=request.user, status="approved", balance__gt=0).exists():
        return Response(
            {"error": "Please clear your current outstanding loan before applying for another."},
            status=400,
        )

    # ── Interest rate from tier ──────────────────────────────────────────
    interest = get_interest_rate(repayment_months, report["interest_band"])

    loan = Loan.objects.create(
        user=request.user,
        amount=amount,
        purpose=purpose,
        purpose_details=purpose_details,
        interest=interest,
        repayment_months=repayment_months,
        balance=amount,
        savings_months=report["consistent_months"],
        total_savings_at_application=report["total_savings"],
    )

    Transaction.objects.create(
        user=request.user, type="loan", amount=amount,
        note=f"Loan #{loan.id} application",
    )

    # ── CRB Check ────────────────────────────────────────────────────────────
    try:
        from core.services.crb_service import CRBService
        crb_check = CRBService().run_check(loan)
        crb_status = crb_check.status
        flag_reason = loan.remarks if loan.status == "flagged" else ""
    except Exception as crb_exc:
        import logging
        logging.getLogger(__name__).error("CRB check failed: %s", crb_exc)
        crb_status  = "error"
        flag_reason = ""

    return Response({
        "message": "Loan application submitted successfully.",
        "loan_id":       loan.id,
        "loan_status":   loan.status,          # may be "flagged"
        "crb_status":    crb_status,
        "flag_reason":   flag_reason,
        "tier":          report["tier_label"],
        "interest_rate": float(interest),
        "max_loan":      float(report["max_loan"]),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 👮 Approve loan (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAdmin])
def approve_loan(request, loan_id):
    try:
        loan = Loan.objects.select_related("user").get(id=loan_id)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    if loan.status != "pending":
        return Response(
            {"error": f"Cannot approve a loan with status '{loan.status}'."},
            status=400,
        )

    # ── Disbursement gate: verify collateral before approving ──────────────
    can_disburse, reason = check_disbursement_gate(loan)
    if not can_disburse:
        return Response({"error": f"Collateral check failed: {reason}"}, status=400)

    loan.status      = "approved"
    loan.approved_by = request.user
    loan.approved_at = timezone.now()
    loan.remarks     = request.data.get("remarks", "")

    interest_amount  = (loan.amount * loan.interest) / Decimal("100")
    loan.balance     = loan.amount + interest_amount
    loan.save()

    # ── Lock collateral ────────────────────────────────────────────────────
    lock_collateral_on_approval(loan)

    Notification.send(
        loan.user, "Loan Approved! 🎉",
        f"Your loan of KES {loan.amount:,.2f} has been approved. "
        f"Total payable: KES {loan.balance:,.2f} over {loan.repayment_months} months.",
        "success", "/loans",
    )
    AuditLog.log(request.user, "loan_approve", f"Loan #{loan.id}", {
        "member": loan.user.username, "amount": float(loan.amount),
    }, request)
    deliver_loan_approved(loan.user, loan)

    # Notify all guarantors that the loan they pledged against was approved
    for g in loan.guarantors.filter(status="accepted"):
        Notification.send(
            g.guarantor,
            "Guaranteed Loan Approved",
            f"The loan of KES {loan.amount:,.2f} you guaranteed for "
            f"{loan.user.get_full_name() or loan.user.username} has been approved.",
            "info", "/loans",
        )

    return Response({
        "message":        "Loan approved.",
        "interest_amount": float(interest_amount),
        "total_payable":   float(loan.balance),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ❌ Reject loan (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAdmin])
def reject_loan(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    if loan.status != "pending":
        return Response(
            {"error": f"Cannot reject a loan with status '{loan.status}'."},
            status=400,
        )

    loan.status  = "rejected"
    loan.remarks = request.data.get("remarks", "Loan application rejected.")
    loan.save()

    Notification.send(
        loan.user, "Loan Application Update",
        f"Your loan application of KES {loan.amount:,.2f} was not approved. "
        f"Reason: {loan.remarks}",
        "warning", "/loans",
    )
    AuditLog.log(request.user, "loan_reject", f"Loan #{loan.id}", {
        "member": loan.user.username, "reason": loan.remarks,
    }, request)
    deliver_loan_rejected(loan.user, loan)

    # Release guarantors and notify them
    for g in loan.guarantors.filter(status="accepted"):
        g.status = "released" if hasattr(g, "released") else g.status
        Notification.send(
            g.guarantor,
            "Guaranteed Loan Not Approved",
            f"The loan application of KES {loan.amount:,.2f} by "
            f"{loan.user.get_full_name() or loan.user.username} was not approved. "
            f"Your guarantee pledge has been released.",
            "info", "/loans",
        )

    return Response({"message": "Loan rejected."})


# ─────────────────────────────────────────────────────────────────────────────
# 📋 Admin — list all loans
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_loans(request):
    status_filter = request.query_params.get("status", "all")
    qs = Loan.objects.select_related("user", "approved_by").all()

    if status_filter != "all":
        qs = qs.filter(status=status_filter)

    loans = []
    for loan in qs:
        try:
            member = loan.user.member_profile
            member_number = member.member_number
            consistent_months = loan.savings_months
        except Exception:
            member_number = "—"
            consistent_months = 0

        loans.append({
            "id":               loan.id,
            "member":           loan.user.get_full_name() or loan.user.username,
            "member_number":    member_number,
            "username":         loan.user.username,
            "amount":           float(loan.amount),
            "interest":         float(loan.interest),
            "repayment_months": loan.repayment_months,
            "balance":          float(loan.balance),
            "purpose":          loan.purpose,
            "purpose_details":  loan.purpose_details,
            "status":           loan.status,
            "remarks":          loan.remarks,
            "savings_months":   consistent_months,
            "total_savings_at_application": float(loan.total_savings_at_application),
            "created_at":       loan.created_at,
            "approved_at":      loan.approved_at,
            "approved_by":      (
                loan.approved_by.get_full_name() or loan.approved_by.username
                if loan.approved_by else ""
            ),
        })

    return Response(loans)


# ─────────────────────────────────────────────────────────────────────────────
# 📊 Member dashboard
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    user  = request.user

    total_savings = (
        Savings.objects.filter(user=user)
        .aggregate(total=Sum("amount"))["total"] or 0
    )

    loans        = Loan.objects.filter(user=user)
    transactions = Transaction.objects.filter(user=user).order_by("-created_at", "-id")

    return Response({
        "username":      user.username,
        "is_staff":      user.is_staff,
        "is_superuser":  user.is_superuser,
        "staff_role":    getattr(getattr(user, "staff_profile", None), "role", None),

        "total_savings":  total_savings,
        "total_loans":    loans.count(),
        "pending_loans":  loans.filter(status="pending").count(),
        "approved_loans": loans.filter(status="approved").count(),

        "loans":        LoanSerializer(loans, many=True).data,
        "transactions": TransactionSerializer(transactions[:25], many=True).data,
        "transaction_count": transactions.count(),

        # Daraja / M-Pesa fields
        "daraja_registered": getattr(getattr(user, "member_profile", None), "daraja_registered", False),
        "phone_number":      getattr(getattr(user, "member_profile", None), "phone_number", ""),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 💳 Repay loan
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def repay_loan(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id, user=request.user)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    if loan.status != "approved":
        return Response(
            {"error": "Only approved loans can be repaid."},
            status=400,
        )

    serializer = RepaymentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount = serializer.validated_data["amount"]

    if amount > loan.balance:
        return Response(
            {"error": f"Repayment amount exceeds outstanding balance of KES {loan.balance:,.2f}."},
            status=400,
        )

    loan.balance -= amount
    if loan.balance == 0:
        loan.status = "repaid"
    loan.save()

    # ── Dynamic collateral release ─────────────────────────────────────────
    recalculate_collateral_release(loan)

    Transaction.objects.create(
        user=request.user, type="repayment", amount=amount,
        note=f"Repayment for Loan #{loan.id}",
    )

    # Notify member
    Notification.send(
        request.user,
        "Loan Repayment Received",
        f"KES {amount:,.2f} repayment for Loan #{loan.id} received. "
        + (f"Loan fully repaid!" if loan.status == "repaid" else f"Remaining balance: KES {loan.balance:,.2f}."),
        "success" if loan.status == "repaid" else "info",
        "/loans",
    )
    AuditLog.log(request.user, "loan_repayment", f"Loan #{loan.id}", {"amount": float(amount)}, request)
    send_repayment_confirmation(request.user, loan.id, float(amount), float(loan.balance))

    return Response({
        "message":           "Repayment successful.",
        "remaining_balance": float(loan.balance),
        "status":            loan.status,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 📋 Complete member transaction history
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_transactions(request):
    account_transactions = Transaction.objects.filter(user=request.user)
    summary = account_transactions.aggregate(
        deposits=Sum("amount", filter=Q(type="deposit")),
        loans=Sum("amount", filter=Q(type="loan")),
        repayments=Sum("amount", filter=Q(type="repayment")),
        withdrawals=Sum("amount", filter=Q(type="withdrawal")),
        count=Count("id"),
    )
    queryset = account_transactions
    transaction_type = request.query_params.get("type")
    if transaction_type and transaction_type != "all":
        queryset = queryset.filter(type=transaction_type)
    start_date = parse_date(request.query_params.get("from", ""))
    end_date = parse_date(request.query_params.get("to", ""))
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.annotate(amount_text=Cast("amount", output_field=CharField())).filter(
            Q(type__icontains=search) | Q(note__icontains=search) | Q(amount_text__icontains=search)
        )
    queryset = queryset.order_by("-created_at", "-id")
    paginator = PageNumberPagination()
    paginator.page_size = 50
    page = paginator.paginate_queryset(queryset, request)
    response = paginator.get_paginated_response(TransactionSerializer(page, many=True).data)
    response.data["summary"] = {
        "deposits": float(summary["deposits"] or 0),
        "loans": float(summary["loans"] or 0),
        "repayments": float(summary["repayments"] or 0),
        "withdrawals": float(summary["withdrawals"] or 0),
        "count": summary["count"],
    }
    return response


# ─────────────────────────────────────────────────────────────────────────────
# 📊 Export transactions to Excel
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_transactions_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"

    # Header block
    ws["A1"] = "SACCO MANAGEMENT SYSTEM"
    ws["A1"].font = Font(size=16, bold=True)
    ws["A2"] = "Transaction Statement"
    ws["A2"].font = Font(size=13, bold=True)
    ws["A4"] = f"Member: {request.user.get_full_name() or request.user.username}"
    ws["A5"] = f"Generated: {timezone.now().strftime('%d %B %Y %H:%M')}"
    ws.append([])

    # Column headers
    headers = ["#", "Date", "Type", "Note", "Amount (KES)"]
    ws.append(headers)
    hdr_row = ws.max_row
    blue_fill = PatternFill("solid", fgColor="2563EB")
    for cell in ws[hdr_row]:
        cell.font      = Font(bold=True, color="FFFFFF")
        cell.fill      = blue_fill
        cell.alignment = Alignment(horizontal="center")

    # Rows
    transactions = Transaction.objects.filter(user=request.user).order_by("-created_at")
    totals = {"deposit": 0, "loan": 0, "repayment": 0, "withdrawal": 0}

    for i, t in enumerate(transactions, 1):
        ws.append([
            i,
            t.created_at.strftime("%d/%m/%Y %H:%M"),
            t.type.title(),
            t.note,
            float(t.amount),
        ])
        totals[t.type] = totals.get(t.type, 0) + float(t.amount)

    ws.append([])
    ws.append(["Summary"])
    ws.append(["Total Deposits",   totals["deposit"]])
    ws.append(["Total Loans",      totals["loan"]])
    ws.append(["Total Repayments", totals["repayment"]])
    ws.append(["Net Balance (Deposits − Repayments)", totals["deposit"] - totals["repayment"]])

    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = (
            max(len(str(c.value or "")) for c in col) + 4
        )

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = 'attachment; filename="sacco_statement.xlsx"'
    wb.save(resp)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 📋 Arrears / Overdue Loans Report (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def arrears_report(request):
    """
    Returns all active loans with at least one overdue installment.
    Buckets by days overdue: 1-30, 31-60, 61-90, 90+ days.
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta

    today = date.today()
    active_loans = Loan.objects.filter(status="approved").select_related("user")

    report = []
    for loan in active_loans:
        if not loan.approved_at:
            continue

        total_payable   = loan.amount + (loan.amount * loan.interest / Decimal("100"))
        monthly_payment = total_payable / loan.repayment_months
        start_date      = loan.approved_at

        oldest_overdue_days = 0
        overdue_installments = 0
        overdue_amount = Decimal("0")

        repayments = list(
            Transaction.objects.filter(
                user=loan.user, type="repayment",
                note__contains=f"Loan #{loan.id}",
            ).order_by("created_at")
        )

        for i in range(1, loan.repayment_months + 1):
            due_date = (start_date + relativedelta(months=i)).date()
            if due_date > today:
                break  # future installments

            paid = repayments[i - 1].amount if i <= len(repayments) else Decimal("0")
            if paid < monthly_payment:
                days_late = (today - due_date).days
                if days_late > oldest_overdue_days:
                    oldest_overdue_days = days_late
                overdue_installments += 1
                overdue_amount += (monthly_payment - paid)

        if overdue_installments == 0:
            continue

        # Bucket by days overdue
        if oldest_overdue_days <= 30:
            bucket = "1-30 days"
        elif oldest_overdue_days <= 60:
            bucket = "31-60 days"
        elif oldest_overdue_days <= 90:
            bucket = "61-90 days"
        else:
            bucket = "90+ days"

        try:
            member_number = loan.user.member_profile.member_number
        except Exception:
            member_number = "—"

        report.append({
            "loan_id":             loan.id,
            "member":              loan.user.get_full_name() or loan.user.username,
            "member_number":       member_number,
            "phone":               getattr(getattr(loan.user, "member_profile", None), "phone_number", ""),
            "loan_amount":         float(loan.amount),
            "outstanding_balance": float(loan.balance),
            "overdue_installments": overdue_installments,
            "overdue_amount":      float(overdue_amount),
            "oldest_overdue_days": oldest_overdue_days,
            "bucket":              bucket,
            "monthly_payment":     float(monthly_payment),
        })

    # Sort worst first
    report.sort(key=lambda x: x["oldest_overdue_days"], reverse=True)

    # Summary buckets
    buckets = {}
    for r in report:
        b = r["bucket"]
        if b not in buckets:
            buckets[b] = {"count": 0, "total_overdue": 0.0}
        buckets[b]["count"] += 1
        buckets[b]["total_overdue"] += r["overdue_amount"]

    return Response({
        "total_delinquent_loans": len(report),
        "total_overdue_amount":   sum(r["overdue_amount"] for r in report),
        "buckets":                buckets,
        "loans":                  report,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 🏢 Public SACCO config — branding, paybill info (no auth required)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([])
def sacco_public_config(request):
    from django.conf import settings as django_settings
    return Response({
        "name":       django_settings.SACCO_NAME,
        "short_name": django_settings.SACCO_SHORT_NAME,
        "address":    django_settings.SACCO_ADDRESS,
        "phone":      django_settings.SACCO_PHONE,
        "email":      django_settings.SACCO_EMAIL,
        "paybill":    django_settings.SACCO_PAYBILL,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 📊 Admin dashboard
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_dashboard(request):
    from members.models import Member

    total_members  = Member.objects.count()
    total_savings  = Savings.objects.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    pending_loans  = Loan.objects.filter(status="pending").count()
    approved_loans = Loan.objects.filter(status="approved").count()
    repaid_loans   = Loan.objects.filter(status="repaid").count()
    rejected_loans = Loan.objects.filter(status="rejected").count()
    active_loans   = (
        Loan.objects.filter(status="approved").aggregate(t=Sum("balance"))["t"] or Decimal("0")
    )
    interest_earned = sum(
        max(loan.balance - loan.amount, Decimal("0"))
        for loan in Loan.objects.filter(status__in=["approved", "repaid"])
    )

    def fmt_monthly(qs):
        return [{"month": e["month"].strftime("%b %Y"), "total": float(e["total"] or 0)} for e in qs]

    monthly_savings = fmt_monthly(
        Savings.objects.annotate(month=TruncMonth("created_at"))
        .values("month").annotate(total=Sum("amount")).order_by("month")
    )
    monthly_loans = fmt_monthly(
        Loan.objects.annotate(month=TruncMonth("created_at"))
        .values("month").annotate(total=Sum("amount")).order_by("month")
    )
    monthly_repayments = fmt_monthly(
        Transaction.objects.filter(type="repayment")
        .annotate(month=TruncMonth("created_at"))
        .values("month").annotate(total=Sum("amount")).order_by("month")
    )

    recent_txns = Transaction.objects.select_related("user").order_by("-created_at")[:10]
    top_savers  = (
        Savings.objects.values("user__username")
        .annotate(total=Sum("amount")).order_by("-total")[:5]
    )

    return Response({
        "total_members":      total_members,
        "total_savings":      float(total_savings),
        "active_loans":       float(active_loans),
        "pending_loans":      pending_loans,
        "approved_loans":     approved_loans,
        "repaid_loans":       repaid_loans,
        "rejected_loans":     rejected_loans,
        "interest_earned":    float(interest_earned),
        "monthly_savings":    monthly_savings,
        "monthly_loans":      monthly_loans,
        "monthly_repayments": monthly_repayments,
        "loan_status": {
            "pending": pending_loans, "approved": approved_loans,
            "repaid": repaid_loans,   "rejected": rejected_loans,
        },
        "recent_transactions": [
            {
                "id":         t.id,
                "member":     t.user.get_full_name() or t.user.username,
                "type":       t.type,
                "amount":     float(t.amount),
                "created_at": t.created_at,
            }
            for t in recent_txns
        ],
        "top_savers": [
            {"username": s["user__username"], "total": float(s["total"])}
            for s in top_savers
        ],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 💸 Savings Withdrawal — BOSA/FOSA enforced
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def withdraw(request):
    from .serializers import WithdrawalSerializer
    from .models import ExitRequest

    serializer = WithdrawalSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount       = serializer.validated_data["amount"]
    account_type = serializer.validated_data.get("account_type", "fosa")

    collateral = get_withdrawable_balance(request.user)

    # ── FOSA withdrawal: can withdraw anytime up to available balance ─────
    if account_type == "fosa":
        fosa_balance    = Decimal(str(collateral["fosa_balance"]))
        fosa_withdrawable = Decimal(str(collateral["fosa_withdrawable"]))

        if amount > fosa_balance:
            return Response({
                "error": f"Insufficient FOSA balance. You have KES {fosa_balance:,.2f} in your FOSA account.",
            }, status=400)

        if amount > fosa_withdrawable:
            locked_guar = Decimal(str(collateral["locked_guarantor"]))
            return Response({
                "error": (
                    f"KES {fosa_balance - fosa_withdrawable:,.2f} of your FOSA balance is locked "
                    f"as a guarantor pledge. You can withdraw up to KES {fosa_withdrawable:,.2f} now."
                ),
            }, status=400)

        Savings.objects.create(user=request.user, amount=-amount, account_type="fosa")
        Transaction.objects.create(
            user=request.user, type="withdrawal", amount=amount,
            note="FOSA withdrawal",
        )
        Notification.send(
            request.user, "FOSA Withdrawal Processed",
            f"KES {amount:,.2f} withdrawn from your FOSA account. "
            f"Remaining FOSA balance: KES {fosa_balance - amount:,.2f}.",
            "info", "/savings",
        )
        AuditLog.log(request.user, "withdrawal", "FOSA", {"amount": float(amount)}, request)
        return Response({
            "message":       "FOSA withdrawal successful.",
            "withdrawn":     float(amount),
            "fosa_balance":  float(fosa_balance - amount),
        })

    # ── BOSA withdrawal: only if member is EXITING the SACCO ─────────────
    if account_type == "bosa":
        bosa_balance = Decimal(str(collateral["bosa_balance"]))

        if amount > bosa_balance:
            return Response({
                "error": f"Insufficient BOSA balance. You have KES {bosa_balance:,.2f}.",
            }, status=400)

        # Block: BOSA is never withdrawable for active members
        if collateral["bosa_withdrawable"] == 0:
            # Check if there's a pending exit
            pending_exit = ExitRequest.objects.filter(
                user=request.user, status__in=["pending", "approved"]
            ).first()

            if not pending_exit:
                return Response({
                    "error": (
                        "BOSA savings are non-withdrawable. They represent your ownership "
                        "stake in the SACCO and can only be accessed if you formally exit "
                        "the SACCO. Please submit an Exit Request from your savings page."
                    ),
                }, status=400)

            if pending_exit.status == "pending":
                return Response({
                    "error": (
                        "Your exit request is still under review by the SACCO. "
                        "You will be notified once it is approved and the holding period expires."
                    ),
                }, status=400)

            # Status = approved but holding period not over
            if not pending_exit.is_holding_period_over:
                return Response({
                    "error": (
                        f"Your exit has been approved. However, SASRA regulations require a "
                        f"{SACCOSettings.get_settings().bosa_exit_hold_days}-day holding period. "
                        f"Your funds will be available on {pending_exit.release_date.strftime('%d %B %Y')}."
                    ),
                }, status=400)

        # At this point: exit is approved AND holding period is over
        # Re-check collateral — must clear loans and guarantor pledges first
        active_loan = Loan.objects.filter(user=request.user, status="approved", balance__gt=0).exists()
        if active_loan:
            return Response({
                "error": "You have an active unpaid loan. Please clear your loan balance before exiting the SACCO.",
            }, status=400)

        active_pledge = LoanGuarantor.objects.filter(
            guarantor=request.user, status="accepted",
            loan__status="approved", loan__balance__gt=0,
        ).exists()
        if active_pledge:
            return Response({
                "error": (
                    "You are currently guaranteeing an active loan. "
                    "Please arrange for alternative guarantors before exiting."
                ),
            }, status=400)

        # All checks passed — release BOSA funds
        Savings.objects.create(user=request.user, amount=-amount, account_type="bosa")
        Transaction.objects.create(
            user=request.user, type="withdrawal", amount=amount,
            note="BOSA exit withdrawal",
        )

        # Mark exit as funds released if full balance withdrawn
        remaining = bosa_balance - amount
        if remaining <= 0:
            exit_req = ExitRequest.objects.filter(
                user=request.user, status="approved"
            ).first()
            if exit_req:
                exit_req.status = "funds_released"
                exit_req.released_at = timezone.now()
                exit_req.save()

        Notification.send(
            request.user, "BOSA Funds Released",
            f"KES {amount:,.2f} released from your BOSA account (exit withdrawal). "
            + (f"Remaining BOSA: KES {remaining:,.2f}." if remaining > 0 else "Your SACCO membership has been fully settled."),
            "info", "/savings",
        )
        AuditLog.log(request.user, "withdrawal", "BOSA exit", {"amount": float(amount)}, request)
        return Response({
            "message":       "BOSA exit withdrawal successful.",
            "withdrawn":     float(amount),
            "bosa_balance":  float(max(remaining, Decimal("0"))),
        })


# ─────────────────────────────────────────────────────────────────────────────
# 📅 Loan Repayment Schedule
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def repayment_schedule(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id, user=request.user)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    if loan.status not in ("approved", "repaid"):
        return Response({"error": "Schedule only available for approved/repaid loans."}, status=400)

    total_payable    = loan.amount + (loan.amount * loan.interest / Decimal("100"))
    monthly_payment  = total_payable / loan.repayment_months
    start_date       = loan.approved_at or loan.created_at

    schedule = []
    from dateutil.relativedelta import relativedelta
    from datetime import date

    # Get actual repayments made
    repayments = list(
        Transaction.objects.filter(
            user=request.user, type="repayment",
            note__contains=f"Loan #{loan.id}",
        ).order_by("created_at")
    )

    running_balance = total_payable
    for i in range(1, loan.repayment_months + 1):
        due_date      = (start_date + relativedelta(months=i)).date()
        paid_amount   = Decimal("0")
        paid_on       = None
        status        = "upcoming"

        if i <= len(repayments):
            paid_amount = repayments[i - 1].amount
            paid_on     = repayments[i - 1].created_at.date()
            running_balance -= paid_amount
            status = "paid" if paid_amount >= monthly_payment else "partial"
        elif due_date < date.today():
            status = "overdue"

        schedule.append({
            "installment":   i,
            "due_date":      due_date,
            "expected":      float(monthly_payment),
            "paid":          float(paid_amount),
            "paid_on":       paid_on,
            "status":        status,
            "balance_after": float(max(running_balance, Decimal("0"))),
        })

    return Response({
        "loan_id":          loan.id,
        "principal":        float(loan.amount),
        "interest_rate":    float(loan.interest),
        "total_payable":    float(total_payable),
        "monthly_payment":  float(monthly_payment),
        "repayment_months": loan.repayment_months,
        "status":           loan.status,
        "schedule":         schedule,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 📊 Savings Statement (running balance)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def savings_statement(request):
    entries = Savings.objects.filter(user=request.user).order_by("created_at")

    statement = []
    running = Decimal("0")
    for e in entries:
        running += e.amount
        statement.append({
            "id":          e.id,
            "date":        e.created_at.date(),
            "type":        "Deposit" if e.amount > 0 else "Withdrawal",
            "account_type": e.account_type,
            "amount":      float(abs(e.amount)),
            "balance":     float(running),
            "created_at":  e.created_at,
        })

    return Response({
        "total_balance": float(running),
        "entries":       list(reversed(statement)),   # newest first
    })


# ─────────────────────────────────────────────────────────────────────────────
# 📄 PDF Statement
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_statement_pdf(request):
    # ── Imports ────────────────────────────────────────────────────────────
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable, KeepTogether,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Line
    from reportlab.graphics import renderPDF
    from io import BytesIO
    import math

    # ── Colour palette ──────────────────────────────────────────────────────
    C_NAVY    = colors.HexColor("#0b1437")   # deep midnight navy
    C_INDIGO  = colors.HexColor("#4f46e5")   # electric indigo (primary brand)
    C_EMERALD = colors.HexColor("#10b981")   # emerald green (credit)
    C_ROSE    = colors.HexColor("#e11d48")   # rose red (debit)
    C_GOLD    = colors.HexColor("#f59e0b")   # gold accent
    C_MUTED   = colors.HexColor("#64748b")   # slate muted
    C_BORDER  = colors.HexColor("#e2e8f0")   # light border
    C_BG_SOFT = colors.HexColor("#f0f4ff")   # soft indigo bg
    C_BG_ROW  = colors.HexColor("#fafbff")   # alternating row tint
    C_WHITE   = colors.white

    # ── Data collection ─────────────────────────────────────────────────────
    user  = request.user
    now   = timezone.now()

    # Date range from query params (default: last 3 months)
    try:
        from_date_str = request.query_params.get("from")
        to_date_str   = request.query_params.get("to")
        from django.utils.dateparse import parse_date
        from datetime import timedelta
        if from_date_str:
            from_dt = timezone.make_aware(
                timezone.datetime.combine(parse_date(from_date_str), timezone.datetime.min.time())
            )
        else:
            from_dt = now - timedelta(days=90)
        if to_date_str:
            to_dt = timezone.make_aware(
                timezone.datetime.combine(parse_date(to_date_str), timezone.datetime.max.time())
            )
        else:
            to_dt = now
    except Exception:
        from datetime import timedelta
        from_dt = now - timedelta(days=90)
        to_dt   = now

    try:
        member        = user.member_profile
        member_number = member.member_number
        phone         = member.phone_number
        county        = member.county
        address       = member.address
        date_joined   = member.date_joined
    except Exception:
        member_number = "N/A"
        phone         = user.email
        county        = ""
        address       = ""
        date_joined   = user.date_joined

    full_name = user.get_full_name() or user.username

    total_savings_val = float(
        Savings.objects.filter(user=user).aggregate(t=Sum("amount"))["t"] or 0
    )
    bosa_balance = float(
        Savings.objects.filter(user=user, account_type="bosa").aggregate(t=Sum("amount"))["t"] or 0
    )
    fosa_balance = float(
        Savings.objects.filter(user=user, account_type="fosa").aggregate(t=Sum("amount"))["t"] or 0
    )

    txns = Transaction.objects.filter(
        user=user,
        created_at__gte=from_dt,
        created_at__lte=to_dt,
    ).order_by("created_at")

    total_credit = sum(float(t.amount) for t in txns if t.type in ("deposit",))
    total_debit  = sum(float(t.amount) for t in txns if t.type in ("withdrawal", "repayment"))

    # ── Document setup ──────────────────────────────────────────────────────
    buf = BytesIO()
    PAGE_W, PAGE_H = A4
    L_MARGIN = 1.8 * cm
    R_MARGIN = 1.8 * cm
    T_MARGIN = 1.5 * cm
    B_MARGIN = 2.0 * cm
    USABLE_W = PAGE_W - L_MARGIN - R_MARGIN

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=T_MARGIN,
        bottomMargin=B_MARGIN,
        leftMargin=L_MARGIN,
        rightMargin=R_MARGIN,
        title=f"Account Statement — {full_name}",
        author="Nairobi West Transport Cooperative Society",
    )

    styles  = getSampleStyleSheet()
    story   = []

    # ── Paragraph styles ────────────────────────────────────────────────────
    def ps(name, **kw):
        base = kw.pop("base", "Normal")
        return ParagraphStyle(name, parent=styles[base], **kw)

    ORG_NAME_STYLE  = ps("orgName",   fontSize=15, textColor=C_NAVY,   fontName="Helvetica-Bold",
                          leading=18, spaceBefore=0, spaceAfter=1)
    ORG_SUB_STYLE   = ps("orgSub",    fontSize=8.5, textColor=C_MUTED, fontName="Helvetica",
                          leading=11, spaceAfter=1)
    STMT_HDR_STYLE  = ps("stmtHdr",   fontSize=20, textColor=C_INDIGO, fontName="Helvetica-Bold",
                          leading=24, spaceAfter=0)
    STMT_SUB_STYLE  = ps("stmtSub",   fontSize=9,  textColor=C_MUTED,  fontName="Helvetica",
                          leading=12, spaceAfter=0)
    MEMBER_STYLE    = ps("memInfo",   fontSize=9.5, textColor=C_NAVY,  fontName="Helvetica-Bold",
                          leading=13)
    MEMBER_SUB      = ps("memSub",    fontSize=8.5, textColor=C_MUTED, fontName="Helvetica",
                          leading=12)
    SECTION_TITLE   = ps("secTitle",  fontSize=9,  textColor=C_WHITE,  fontName="Helvetica-Bold",
                          leading=11)
    CELL_NORMAL     = ps("cellNorm",  fontSize=8.5, textColor=C_NAVY,  fontName="Helvetica",
                          leading=11)
    CELL_BOLD       = ps("cellBold",  fontSize=8.5, textColor=C_NAVY,  fontName="Helvetica-Bold",
                          leading=11)
    CELL_CREDIT     = ps("cellCred",  fontSize=8.5, textColor=C_EMERALD, fontName="Helvetica-Bold",
                          leading=11, alignment=TA_RIGHT)
    CELL_DEBIT      = ps("cellDeb",   fontSize=8.5, textColor=C_ROSE,  fontName="Helvetica-Bold",
                          leading=11, alignment=TA_RIGHT)
    CELL_BALANCE    = ps("cellBal",   fontSize=8.5, textColor=C_NAVY,  fontName="Helvetica-Bold",
                          leading=11, alignment=TA_RIGHT)
    CELL_MUTED_R    = ps("cellMR",    fontSize=8,   textColor=C_MUTED, fontName="Helvetica",
                          leading=10, alignment=TA_RIGHT)
    CELL_MUTED_C    = ps("cellMC",    fontSize=8,   textColor=C_MUTED, fontName="Helvetica",
                          leading=10, alignment=TA_CENTER)
    FOOTER_STYLE    = ps("footer",    fontSize=7.5, textColor=C_MUTED, fontName="Helvetica",
                          leading=10, alignment=TA_CENTER)
    DISCLAIMER_STYLE = ps("disclaim", fontSize=7, textColor=C_MUTED, fontName="Helvetica",
                          leading=9, alignment=TA_CENTER)

    # ── ① HEADER SECTION — Logo left, "Account Statement" right ─────────────
    # Left: org logo placeholder + name stack
    # Right: "Account Statement" big text
    # (Mirrors Equity Bank layout: org branding left, statement title right)

    def _draw_logo_mark(drawing, x, y, sz):
        """Draw the NW Transport logo mark onto a ReportLab Drawing."""
        from reportlab.graphics.shapes import (
            Rect as RLRect, Circle as RLCircle, Line as RLLine,
            Polygon as RLPolygon, Path as RLPath,
        )
        indigo_hex  = "#4f46e5"
        emerald_hex = "#10b981"
        gold_hex    = "#f59e0b"
        navy_hex    = "#0b1437"
        scale = sz / 80.0

        def sc(v): return v * scale

        # Outer circle ring
        c_outer = RLCircle(x + sc(40), y + sc(40), sc(37))
        c_outer.strokeColor = colors.HexColor(indigo_hex)
        c_outer.strokeWidth = sc(3)
        c_outer.fillColor   = colors.HexColor("#eef2ff")
        drawing.add(c_outer)

        # Bus body
        body = RLRect(x + sc(14), y + sc(25), sc(52), sc(18))
        body.fillColor = colors.HexColor(indigo_hex)
        body.strokeColor = None
        drawing.add(body)

        # Roof / cab top
        roof = RLRect(x + sc(18), y + sc(34), sc(44), sc(10))
        roof.fillColor = colors.HexColor(indigo_hex)
        roof.strokeColor = None
        drawing.add(roof)

        # Windscreen
        wind = RLPolygon([
            x + sc(23), y + sc(34),
            x + sc(26), y + sc(28),
            x + sc(54), y + sc(28),
            x + sc(57), y + sc(34),
        ])
        wind.fillColor   = colors.HexColor("#eef2ff")
        wind.strokeColor = None
        drawing.add(wind)

        # Wheels
        for wx in [24, 56]:
            w = RLCircle(x + sc(wx), y + sc(18), sc(5))
            w.fillColor = colors.HexColor(navy_hex)
            w.strokeColor = colors.white
            w.strokeWidth = sc(1.5)
            drawing.add(w)
            wh = RLCircle(x + sc(wx), y + sc(18), sc(2.5))
            wh.fillColor = colors.HexColor(indigo_hex)
            wh.strokeColor = None
            drawing.add(wh)

        # Undercarriage bar
        bar = RLRect(x + sc(18), y + sc(19), sc(44), sc(3))
        bar.fillColor = colors.HexColor(navy_hex)
        bar.strokeColor = None
        drawing.add(bar)

        # Road line
        road = RLLine(x + sc(10), y + sc(10), x + sc(70), y + sc(10))
        road.strokeColor = colors.HexColor(emerald_hex)
        road.strokeWidth = sc(2.5)
        drawing.add(road)

        # Gold arc monogram — bezier path (Arc is not available in all reportlab versions)
        cx = x + sc(40)
        cy = y + sc(50)
        rx = sc(18)
        ry = sc(8)
        k  = 0.5523  # cubic bezier approximation for quarter-circle
        arc_path = RLPath()
        arc_path.moveTo(cx - rx, cy)
        arc_path.curveTo(cx - rx, cy + ry * k,  cx - rx * k, cy + ry,  cx,       cy + ry)
        arc_path.curveTo(cx + rx * k, cy + ry,  cx + rx, cy + ry * k,  cx + rx,  cy)
        arc_path.strokeColor = colors.HexColor(gold_hex)
        arc_path.strokeWidth = sc(2.2)
        arc_path.fillColor   = None
        drawing.add(arc_path)

        return drawing

    LOGO_SZ = 58   # px equivalent in the drawing
    logo_drawing = Drawing(LOGO_SZ * 0.75, LOGO_SZ * 0.75)
    _draw_logo_mark(logo_drawing, 0, 0, LOGO_SZ * 0.75)

    # Header table: [LOGO + ORG NAME | spacer | "Account Statement"]
    org_name_cell = [
        Paragraph("NAIROBI WEST TRANSPORT", ORG_NAME_STYLE),
        Paragraph("COOPERATIVE SOCIETY", ps("orgName2", fontSize=12, textColor=C_NAVY,
                   fontName="Helvetica-Bold", leading=14, spaceBefore=0, spaceAfter=2)),
        Paragraph("Nairobi West, Nairobi County, Kenya", ORG_SUB_STYLE),
        Paragraph("Tel: +254 700 000 000  |  info@nwtcs.co.ke", ORG_SUB_STYLE),
        Paragraph("www.nwtcs.co.ke", ORG_SUB_STYLE),
    ]
    stmt_title_cell = [
        Paragraph("Account", STMT_HDR_STYLE),
        Paragraph("Statement", STMT_HDR_STYLE),
        Spacer(1, 4),
        Paragraph(f"Statement Date: {now.strftime('%d/%m/%Y')}", STMT_SUB_STYLE),
        Paragraph(f"Generated: {now.strftime('%d %B %Y, %H:%M')}", STMT_SUB_STYLE),
    ]

    logo_col = [[logo_drawing, Spacer(1, 4)] + org_name_cell]

    header_table = Table(
        [[logo_col, "", stmt_title_cell]],
        colWidths=[USABLE_W * 0.52, USABLE_W * 0.04, USABLE_W * 0.44],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
        ("ALIGN",   (2, 0), (2, 0),   "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 2, C_INDIGO),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── ② MEMBER INFO + ACCOUNT DETAILS (2-column box like Equity) ──────────
    # Left: member name/address/contact
    # Right: account meta (number, currency, branch, period)

    member_info_rows = [
        Paragraph(full_name.upper(), MEMBER_STYLE),
        Paragraph(address or county or "Kenya", MEMBER_SUB),
        Paragraph(phone or "", MEMBER_SUB),
        Paragraph(user.email or "", MEMBER_SUB),
    ]
    account_meta_rows = [
        ["Member Number",   member_number],
        ["Currency",        "KES"],
        ["Branch / Region", "Nairobi West"],
        ["Statement Date",  now.strftime("%d/%m/%Y")],
        ["Statement Period",f"{from_dt.strftime('%d/%m/%Y')} – {to_dt.strftime('%d/%m/%Y')}"],
        ["Member Since",    date_joined.strftime("%d/%m/%Y") if date_joined else "—"],
    ]

    meta_table = Table(
        [[f, v] for f, v in account_meta_rows],
        colWidths=[3.8 * cm, 5.4 * cm],
    )
    meta_table.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",  (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1),  C_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1),  C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, C_BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), C_BG_SOFT),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
    ]))

    info_table = Table(
        [[member_info_rows, meta_table]],
        colWidths=[USABLE_W * 0.48, USABLE_W * 0.52],
    )
    info_table.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── ③ SAVINGS SUMMARY BOXES (3-up KPI row) ──────────────────────────────
    kpi_data = [
        ["TOTAL SAVINGS", f"KES {total_savings_val:>12,.2f}", C_INDIGO],
        ["BOSA BALANCE",  f"KES {bosa_balance:>12,.2f}",  C_EMERALD],
        ["FOSA BALANCE",  f"KES {fosa_balance:>12,.2f}",  C_NAVY],
    ]
    kpi_cells = []
    for label, value, col in kpi_data:
        kpi_cells.append([
            Paragraph(label, ps(f"kpi_l_{label}", fontSize=7.5, textColor=C_MUTED,
                                fontName="Helvetica-Bold", leading=9, spaceAfter=3)),
            Paragraph(value, ps(f"kpi_v_{label}", fontSize=12, textColor=col,
                                fontName="Helvetica-Bold", leading=15)),
        ])
    kpi_col_w = USABLE_W / 3 - 0.1 * cm
    kpi_table = Table(
        [kpi_cells],
        colWidths=[kpi_col_w] * 3,
        rowHeights=[1.6 * cm],
    )
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_WHITE),
        ("BOX",           (0, 0), (0, 0),   0.6, C_INDIGO),
        ("BOX",           (1, 0), (1, 0),   0.6, C_EMERALD),
        ("BOX",           (2, 0), (2, 0),   0.6, C_NAVY),
        ("LINEABOVE",     (0, 0), (0, 0),   3,   C_INDIGO),
        ("LINEABOVE",     (1, 0), (1, 0),   3,   C_EMERALD),
        ("LINEABOVE",     (2, 0), (2, 0),   3,   C_NAVY),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.55 * cm))

    # ── ④ TRANSACTIONS TABLE ─────────────────────────────────────────────────
    # Header row — full-width midnight navy band (Equity Bank style)
    TX_COLS = ["Transaction Details", "Ref No.", "Value Date", "Credit (Money In)", "Debit (Money Out)", "Balance"]
    COL_W   = [USABLE_W*0.34, USABLE_W*0.14, USABLE_W*0.10, USABLE_W*0.12, USABLE_W*0.14, USABLE_W*0.16]

    def _tx_hdr(text):
        return Paragraph(text, ps(f"txh_{text[:5]}", fontSize=8, textColor=C_WHITE,
                                   fontName="Helvetica-Bold", leading=10, alignment=TA_LEFT))
    def _tx_hdr_r(text):
        return Paragraph(text, ps(f"txhr_{text[:5]}", fontSize=8, textColor=C_WHITE,
                                   fontName="Helvetica-Bold", leading=10, alignment=TA_RIGHT))

    tx_rows = [
        [_tx_hdr("Transaction Details"), _tx_hdr("Payment Reference"),
         _tx_hdr_r("Value Date"), _tx_hdr_r("Credit\n(Money In)"),
         _tx_hdr_r("Debit\n(Money Out)"), _tx_hdr_r("Balance")],
    ]

    # Running balance calculation
    running_balance = total_savings_val
    prev_txns_total = float(
        Transaction.objects.filter(
            user=user, created_at__lt=from_dt
        ).aggregate(
            t=Sum("amount")
        )["t"] or 0
    )
    running_balance = prev_txns_total  # start from what was there before period

    row_styles = []
    for i, t in enumerate(txns, 1):
        amount = float(t.amount)
        is_credit = t.type in ("deposit",)
        is_debit  = t.type in ("withdrawal", "repayment")

        if is_credit:
            running_balance += amount
            credit_str = f"{amount:,.2f}"
            debit_str  = ""
        elif is_debit:
            running_balance -= amount
            credit_str = ""
            debit_str  = f"{amount:,.2f}"
        else:
            # loan disbursement — credit
            running_balance += amount
            credit_str = f"{amount:,.2f}"
            debit_str  = ""

        # ── Build a meaningful SACCO description for each transaction type ──
        TYPE_LABELS = {
            "deposit":    "Savings Deposit",
            "withdrawal": "Savings Withdrawal",
            "repayment":  "Loan Repayment",
            "loan":       "Loan Disbursement",
            "dividend":   "Dividend Payout",
        }
        base_label = TYPE_LABELS.get(t.type, t.type.replace("_", " ").title())

        # Determine account type hint from note for deposits
        if t.type == "deposit":
            note_upper = (t.note or "").upper()
            if "BOSA" in note_upper:
                base_label = "Savings Deposit — BOSA"
            elif "FOSA" in note_upper:
                base_label = "Savings Deposit — FOSA"
            else:
                base_label = "Savings Deposit"

        detail_lines = base_label
        # Add note on second line if it adds real information
        if t.note and t.note.strip().upper() not in (
            base_label.upper(), t.type.upper(), "BOSA DEPOSIT", "FOSA DEPOSIT",
            f"{base_label.upper()} DEPOSIT",
        ):
            detail_lines += f"\n{t.note[:55]}"

        row = [
            Paragraph(detail_lines, ps(f"td_{i}", fontSize=8, textColor=C_NAVY,
                                        fontName="Helvetica", leading=10)),
            Paragraph(f"TX{t.id:08d}", ps(f"tr_{i}", fontSize=7.5, textColor=C_MUTED,
                                           fontName="Helvetica", leading=10)),
            Paragraph(t.created_at.strftime("%d/%m/%Y"), CELL_MUTED_C),
            Paragraph(credit_str, CELL_CREDIT) if credit_str else Paragraph("", CELL_NORMAL),
            Paragraph(debit_str,  CELL_DEBIT)  if debit_str  else Paragraph("", CELL_NORMAL),
            Paragraph(f"{running_balance:,.2f}", CELL_BALANCE),
        ]
        tx_rows.append(row)

        # Alternate row shading
        bg = C_WHITE if i % 2 == 1 else C_BG_ROW
        row_styles.append(("BACKGROUND", (0, i), (-1, i), bg))

    # Totals row
    tx_rows.append([
        Paragraph("Total", ps("tottxt", fontSize=9, textColor=C_NAVY,
                               fontName="Helvetica-Bold", leading=11)),
        Paragraph("", CELL_NORMAL),
        Paragraph("", CELL_NORMAL),
        Paragraph(f"{total_credit:,.2f}",
                  ps("totcr", fontSize=9, textColor=C_EMERALD, fontName="Helvetica-Bold",
                     leading=11, alignment=TA_RIGHT)),
        Paragraph(f"{total_debit:,.2f}",
                  ps("totdb", fontSize=9, textColor=C_ROSE, fontName="Helvetica-Bold",
                     leading=11, alignment=TA_RIGHT)),
        Paragraph(f"{running_balance:,.2f}",
                  ps("totbal", fontSize=9, textColor=C_NAVY, fontName="Helvetica-Bold",
                     leading=11, alignment=TA_RIGHT)),
    ])

    total_row_idx = len(tx_rows) - 1

    tx_table = Table(tx_rows, colWidths=COL_W, repeatRows=1)
    base_styles = [
        # Header band
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        # All cells
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 1), (-1, -2), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -2), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Grid — light
        ("GRID",          (0, 0), (-1, -1), 0.25, C_BORDER),
        ("LINEBELOW",     (0, 0), (-1, 0),  1.0, C_BORDER),
        # Totals row
        ("BACKGROUND",    (0, total_row_idx), (-1, total_row_idx), C_BG_SOFT),
        ("LINEABOVE",     (0, total_row_idx), (-1, total_row_idx), 1.2, C_INDIGO),
        ("TOPPADDING",    (0, total_row_idx), (-1, total_row_idx), 7),
        ("BOTTOMPADDING", (0, total_row_idx), (-1, total_row_idx), 7),
    ] + row_styles

    tx_table.setStyle(TableStyle(base_styles))

    if len(tx_rows) > 1:
        story.append(tx_table)
    else:
        story.append(Paragraph("No transactions found in this statement period.",
                                ps("notx", fontSize=9, textColor=C_MUTED, fontName="Helvetica-Oblique")))

    story.append(Spacer(1, 0.8 * cm))

    # ── ⑤ FOOTER — disclaimer + page info ───────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(
        "Disclaimer: This record is produced for your personal use and is not transferable. "
        "Contact us for 24-hour assistance on <b>+254 700 000 000</b> or email "
        "<b>info@nwtcs.co.ke</b>. "
        "<i>*****COMPUTER GENERATED STATEMENT*****</i>",
        DISCLAIMER_STYLE,
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        f"Nairobi West Transport Cooperative Society  ·  "
        f"Nairobi West, Nairobi County, Kenya  ·  "
        f"Printed: {now.strftime('%d/%m/%Y  %H:%M')}   Page 1",
        FOOTER_STYLE,
    ))

    # ── Build ────────────────────────────────────────────────────────────────
    def _on_page(canvas_obj, doc_obj):
        """Draw a subtle indigo accent stripe at top and bottom of every page."""
        canvas_obj.saveState()
        # Top stripe
        canvas_obj.setFillColor(C_INDIGO)
        canvas_obj.rect(0, PAGE_H - 6, PAGE_W, 6, fill=1, stroke=0)
        # Gold accent line below top stripe
        canvas_obj.setFillColor(C_GOLD)
        canvas_obj.rect(0, PAGE_H - 9, PAGE_W, 3, fill=1, stroke=0)
        # Bottom stripe
        canvas_obj.setFillColor(C_INDIGO)
        canvas_obj.rect(0, 0, PAGE_W, 5, fill=1, stroke=0)
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    buf.seek(0)

    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="NWTCS_Statement_{member_number}_{now.strftime("%Y%m%d")}.pdf"'
    )
    AuditLog.log(user, "export", f"PDF statement {member_number}", request=request)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# 🤝 Guarantors
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def loan_guarantors(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id, user=request.user)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    from .models import LoanGuarantor
    from members.models import Member

    if request.method == "GET":
        return Response([
            {
                "id":           g.id,
                "guarantor":    g.guarantor.get_full_name() or g.guarantor.username,
                "member_number":getattr(getattr(g.guarantor, "member_profile", None), "member_number", ""),
                "status":       g.status,
                "message":      g.message,
                "responded_at": g.responded_at,
            }
            for g in loan.guarantors.select_related("guarantor").all()
        ])

    # POST — add a guarantor
    identifier = request.data.get("identifier", "").strip()
    if not identifier:
        return Response({"error": "Provide a member number or username."}, status=400)

    # Find guarantor by member number or username
    try:
        g_member = Member.objects.select_related("user").get(member_number=identifier)
        g_user   = g_member.user
    except Member.DoesNotExist:
        try:
            g_user = get_user_model().objects.get(username=identifier)
        except Exception:
            return Response({"error": "Member not found."}, status=404)

    if g_user == request.user:
        return Response({"error": "You cannot guarantee your own loan."}, status=400)

    if LoanGuarantor.objects.filter(loan=loan, guarantor=g_user).exists():
        return Response({"error": "This member is already a guarantor."}, status=400)

    g = LoanGuarantor.objects.create(loan=loan, guarantor=g_user)

    # Notify the guarantor
    from accounts.models import Notification
    Notification.send(
        g_user, "Guarantor Request",
        f"{request.user.get_full_name() or request.user.username} has requested you to guarantee "
        f"their loan of KES {loan.amount:,.2f}. Please respond.",
        "warning", "/loans",
    )

    return Response({"message": "Guarantor request sent.", "guarantor_id": g.id}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def guarantor_respond(request, guarantor_id):
    from .models import LoanGuarantor
    from django.utils import timezone as tz

    try:
        g = LoanGuarantor.objects.get(id=guarantor_id, guarantor=request.user)
    except LoanGuarantor.DoesNotExist:
        return Response({"error": "Guarantor record not found."}, status=404)

    action  = request.data.get("action", "")  # "accept" or "decline"
    message = request.data.get("message", "")

    if action == "accept":
        g.status = "accepted"
    elif action == "decline":
        g.status = "declined"
    else:
        return Response({"error": "action must be 'accept' or 'decline'."}, status=400)

    g.message      = message
    g.responded_at = tz.now()
    g.save()

    # Notify loan owner
    from accounts.models import Notification
    verb = "accepted" if action == "accept" else "declined"
    Notification.send(
        g.loan.user, f"Guarantor {verb.capitalize()}",
        f"{request.user.get_full_name() or request.user.username} has {verb} to be your guarantor for Loan #{g.loan_id}.",
        "success" if action == "accept" else "warning", "/loans",
    )
    return Response({"message": f"You have {verb} the guarantor request."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def guarantor_pending(request):
    """List all pending guarantor requests for the current user."""
    from .models import LoanGuarantor
    pending = (
        LoanGuarantor.objects
        .filter(guarantor=request.user, status="pending")
        .select_related("loan__user")
    )
    return Response([
        {
            "id":           g.id,
            "loan_id":      g.loan_id,
            "borrower":     g.loan.user.get_full_name() or g.loan.user.username,
            "loan_amount":  float(g.loan.amount),
            "loan_months":  g.loan.repayment_months,
            "loan_purpose": g.loan.purpose,
            "created_at":   g.created_at,
        }
        for g in pending
    ])


# ─────────────────────────────────────────────────────────────────────────────
# 💹 Dividends (admin: calculate & pay annual dividend)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_dividends(request):
    from .models import SavingsDividend
    divs = SavingsDividend.objects.filter(user=request.user)
    return Response([
        {
            "year":     d.year,
            "rate":     float(d.rate),
            "balance":  float(d.savings_balance),
            "dividend": float(d.amount),
            "paid_at":  d.paid_at,
            "note":     d.note,
        }
        for d in divs
    ])


@api_view(["POST"])
@permission_classes([IsAdmin])
def pay_dividends(request):
    """
    Admin posts: { year: 2025, rate: 8.0 }
    Calculates and records dividend for every member with positive savings.
    Idempotent — will not double-pay for the same year.
    """
    from .models import SavingsDividend
    from django.db import transaction as db_transaction
    from decimal import Decimal as D

    year = int(request.data.get("year", timezone.now().year))
    rate = D(str(request.data.get("rate", "8.00")))

    if rate <= 0 or rate > 100:
        return Response({"error": "Rate must be between 0 and 100."}, status=400)

    members_paid = 0
    total_paid   = D("0")

    with db_transaction.atomic():
        for user in get_user_model().objects.filter(is_member=True, is_active=True):
            balance = Savings.objects.filter(user=user).aggregate(t=Sum("amount"))["t"] or D("0")
            if balance <= 0:
                continue
            # Skip if already paid this year
            if SavingsDividend.objects.filter(user=user, year=year).exists():
                continue

            dividend = (balance * rate / D("100")).quantize(D("0.01"))
            SavingsDividend.objects.create(
                user=user, year=year, rate=rate,
                savings_balance=balance, amount=dividend,
                note=f"Annual dividend {year} @ {rate}%",
            )
            # Credit as a savings deposit
            Savings.objects.create(user=user, amount=dividend)
            Transaction.objects.create(
                user=user, type="deposit", amount=dividend,
                note=f"Annual dividend {year} @ {rate}%",
            )
            from accounts.models import Notification
            Notification.send(
                user, f"Dividend Paid — {year} 🎉",
                f"Your annual savings dividend for {year} has been paid: KES {dividend:,.2f} ({rate}% on KES {balance:,.2f}).",
                "success", "/savings",
            )
            members_paid += 1
            total_paid   += dividend

    AuditLog.log(request.user, "other", f"Dividends {year}", {
        "rate": float(rate), "members": members_paid, "total": float(total_paid),
    }, request)

    return Response({
        "message":      f"Dividend paid to {members_paid} member(s).",
        "year":         year,
        "rate":         float(rate),
        "members_paid": members_paid,
        "total_paid":   float(total_paid),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 📊 Admin member financial report
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_reports(request):
    from members.models import Member
    from django.db.models import Avg, Max as DMax, Min

    total_members   = Member.objects.count()
    active_members  = Member.objects.filter(status="active").count()
    suspended       = Member.objects.filter(status="suspended").count()

    total_savings   = float(Savings.objects.filter(amount__gt=0).aggregate(t=Sum("amount"))["t"] or 0)
    total_withdrawn = float(abs(Savings.objects.filter(amount__lt=0).aggregate(t=Sum("amount"))["t"] or 0))
    net_savings     = total_savings - total_withdrawn

    loans_pending   = Loan.objects.filter(status="pending").count()
    loans_approved  = Loan.objects.filter(status="approved").count()
    loans_repaid    = Loan.objects.filter(status="repaid").count()
    loans_rejected  = Loan.objects.filter(status="rejected").count()

    total_loaned    = float(Loan.objects.exclude(status="pending").aggregate(t=Sum("amount"))["t"] or 0)
    total_outstanding = float(Loan.objects.filter(status="approved").aggregate(t=Sum("balance"))["t"] or 0)
    total_collected = float(Transaction.objects.filter(type="repayment").aggregate(t=Sum("amount"))["t"] or 0)

    # Top savers
    top_savers = (
        Savings.objects.values("user__username", "user__first_name", "user__last_name")
        .annotate(total=Sum("amount"))
        .filter(total__gt=0)
        .order_by("-total")[:10]
    )

    # Monthly savings trend (current year)
    from django.db.models.functions import TruncMonth
    current_year = timezone.now().year
    monthly = (
        Savings.objects.filter(created_at__year=current_year, amount__gt=0)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    return Response({
        "members":         {"total": total_members, "active": active_members, "suspended": suspended},
        "savings":         {"total_deposited": total_savings, "total_withdrawn": total_withdrawn, "net_balance": net_savings},
        "loans": {
            "pending": loans_pending, "approved": loans_approved,
            "repaid":  loans_repaid,  "rejected": loans_rejected,
            "total_disbursed": total_loaned,
            "outstanding_balance": total_outstanding,
            "total_collected": total_collected,
        },
        "top_savers": [
            {
                "username":  s["user__username"],
                "name":      f"{s['user__first_name']} {s['user__last_name']}".strip() or s["user__username"],
                "total":     float(s["total"]),
            }
            for s in top_savers
        ],
        "monthly_savings_trend": [
            {"month": m["month"].strftime("%b %Y"), "total": float(m["total"])}
            for m in monthly
        ],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 🔒 Collateral status — member view
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def collateral_status(request):
    """Member views their own collateral/lock situation."""
    breakdown = get_withdrawable_balance(request.user)
    return Response(breakdown)


# ─────────────────────────────────────────────────────────────────────────────
# 🏠 Asset Collateral Registry (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([IsAdmin])
def asset_registry(request):
    if request.method == "GET":
        assets = AssetCollateral.objects.select_related("user", "loan").all()
        return Response([
            {
                "id":                 a.id,
                "user":               a.user.get_full_name() or a.user.username,
                "user_id":            a.user_id,
                "asset_type":         a.asset_type,
                "asset_type_label":   a.get_asset_type_display(),
                "description":        a.description,
                "forced_sale_value":  float(a.forced_sale_value),
                "ltv_ratio":          float(a.ltv_ratio),
                "max_loan_cap":       float(a.max_loan_cap),
                "status":             a.status,
                "status_label":       a.get_status_display(),
                "registration_ref":   a.registration_ref,
                "valuation_date":     a.valuation_date,
                "valuer_name":        a.valuer_name,
                "discharge_ref":      a.discharge_ref,
                "loan_id":            a.loan_id,
                "created_at":          a.created_at,
            }
            for a in assets
        ])

    # POST — create new asset
    from decimal import Decimal as D
    asset = AssetCollateral.objects.create(
        user_id             = request.data.get("user_id"),
        asset_type          = request.data.get("asset_type", "other"),
        description         = request.data.get("description", ""),
        forced_sale_value   = D(str(request.data.get("forced_sale_value", "0"))),
        ltv_ratio           = D(str(request.data.get("ltv_ratio", "80"))),
        status              = request.data.get("status", "pending_valuation"),
        registration_ref    = request.data.get("registration_ref", ""),
        valuation_date      = request.data.get("valuation_date"),
        valuer_name         = request.data.get("valuer_name", ""),
    )
    AuditLog.log(request.user, "other", f"Asset registered for user #{asset.user_id}",
                 {"type": asset.asset_type, "fsv": float(asset.forced_sale_value)}, request)
    return Response({"message": "Asset registered.", "id": asset.id,
                     "max_loan_cap": float(asset.max_loan_cap)}, status=201)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAdmin])
def asset_detail(request, asset_id):
    try:
        asset = AssetCollateral.objects.get(id=asset_id)
    except AssetCollateral.DoesNotExist:
        return Response({"error": "Asset not found."}, status=404)

    if request.method == "GET":
        return Response({
            "id":                 asset.id,
            "user":               asset.user.get_full_name() or asset.user.username,
            "user_id":            asset.user_id,
            "asset_type":         asset.asset_type,
            "asset_type_label":   asset.get_asset_type_display(),
            "description":        asset.description,
            "forced_sale_value":  float(asset.forced_sale_value),
            "ltv_ratio":          float(asset.ltv_ratio),
            "max_loan_cap":       float(asset.max_loan_cap),
            "status":             asset.status,
            "status_label":       asset.get_status_display(),
            "registration_ref":   asset.registration_ref,
            "valuation_date":     asset.valuation_date,
            "valuer_name":        asset.valuer_name,
            "discharge_ref":      asset.discharge_ref,
            "loan_id":            asset.loan_id,
            "created_at":          asset.created_at,
        })

    if request.method == "PUT":
        from decimal import Decimal as D
        fields = ["asset_type", "description", "forced_sale_value", "ltv_ratio",
                   "status", "registration_ref", "valuation_date", "valuer_name",
                   "discharge_ref"]
        for f in fields:
            if f in request.data:
                val = request.data[f]
                if f in ("forced_sale_value", "ltv_ratio"):
                    val = D(str(val))
                setattr(asset, f, val)
        asset.save()

        # Disbursement gate check if status changed to legal_charge_registered
        if asset.loan_id and asset.status == "legal_charge_registered":
            can_disburse, reason = check_disbursement_gate(asset.loan)
            AuditLog.log(request.user, "other", f"Asset #{asset.id} status → {asset.status}",
                         {"can_disburse": can_disburse, "reason": reason}, request)
        else:
            AuditLog.log(request.user, "other", f"Asset #{asset.id} updated",
                         {"status": asset.status}, request)
        return Response({"message": "Asset updated."})

    # DELETE
    AuditLog.log(request.user, "other", f"Asset #{asset.id} deleted", request=request)
    asset.delete()
    return Response({"message": "Asset deleted."})


# ─────────────────────────────────────────────────────────────────────────────
# ⚙️ SACCO Settings (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "PUT"])
@permission_classes([IsAdmin])
def sacco_settings(request):
    settings = SACCOSettings.get_settings()

    if request.method == "GET":
        return Response({
            "release_hierarchy":        settings.release_hierarchy,
            "release_hierarchy_label":  settings.get_release_hierarchy_display(),
            "default_ltv_ratio":        float(settings.default_ltv_ratio),
            "min_savings_retention":    float(settings.min_savings_retention),
            "sasra_enabled":            settings.sasra_enabled,
            "sasra_report_interval_days": settings.sasra_report_interval_days,
            "mandatory_monthly_bosa":   float(settings.mandatory_monthly_bosa),
            "bosa_exit_hold_days":      settings.bosa_exit_hold_days,
        })

    # PUT
    settings.release_hierarchy       = request.data.get("release_hierarchy", settings.release_hierarchy)
    settings.default_ltv_ratio        = Decimal(str(request.data.get("default_ltv_ratio", settings.default_ltv_ratio)))
    settings.min_savings_retention    = Decimal(str(request.data.get("min_savings_retention", settings.min_savings_retention)))
    settings.sasra_enabled            = request.data.get("sasra_enabled", settings.sasra_enabled)
    settings.sasra_report_interval_days = int(request.data.get("sasra_report_interval_days", settings.sasra_report_interval_days))
    if "mandatory_monthly_bosa" in request.data:
        settings.mandatory_monthly_bosa = Decimal(str(request.data["mandatory_monthly_bosa"]))
    if "bosa_exit_hold_days" in request.data:
        settings.bosa_exit_hold_days = int(request.data["bosa_exit_hold_days"])
    settings.save()

    AuditLog.log(request.user, "other", "SACCO settings updated",
                 {"release_hierarchy": settings.release_hierarchy}, request)
    return Response({"message": "Settings updated."})


# ─────────────────────────────────────────────────────────────────────────────
# 📋 SASRA Compliance Reports (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([IsAdmin])
def sasra_reports(request):
    if request.method == "GET":
        reports = SASRAReport.objects.select_related("generated_by").all()
        return Response([
            {
                "id":           r.id,
                "report_type":  r.report_type,
                "period_start": r.period_start,
                "period_end":   r.period_end,
                "status":       r.status,
                "data_snapshot": r.data_snapshot,
                "generated_by": r.generated_by.username if r.generated_by else "System",
                "created_at":   r.created_at,
                "submitted_at":  r.submitted_at,
            }
            for r in reports
        ])

    # POST — generate a new SASRA report
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from members.models import Member

    report_type = request.data.get("report_type", "quarterly")
    today = date.today()

    if report_type == "quarterly":
        period_end = today
        period_start = today - relativedelta(months=3)
    elif report_type == "annual":
        period_end = today
        period_start = today - relativedelta(years=1)
    elif report_type == "monthly":
        period_end = today
        period_start = today - relativedelta(months=1)
    else:
        period_start = date.fromisoformat(request.data.get("period_start", today.isoformat()))
        period_end   = date.fromisoformat(request.data.get("period_end", today.isoformat()))

    # Gather data snapshot
    total_members   = Member.objects.count()
    active_members  = Member.objects.filter(status="active").count()
    total_savings   = float(Savings.objects.filter(amount__gt=0).aggregate(t=Sum("amount"))["t"] or 0)
    total_loans     = Loan.objects.exclude(status="pending").count()
    active_loans    = Loan.objects.filter(status="approved").count()
    total_outstanding = float(Loan.objects.filter(status="approved").aggregate(t=Sum("balance"))["t"] or 0)
    total_repaid    = float(Transaction.objects.filter(type="repayment", created_at__date__gte=period_start).aggregate(t=Sum("amount"))["t"] or 0)
    total_deposits  = float(Savings.objects.filter(amount__gt=0, created_at__date__gte=period_start).aggregate(t=Sum("amount"))["t"] or 0)
    total_withdrawals = float(abs(Savings.objects.filter(amount__lt=0, created_at__date__gte=period_start).aggregate(t=Sum("amount"))["t"] or 0))

    # Asset collateral summary
    total_asset_value = float(AssetCollateral.objects.exclude(status="rejected").aggregate(t=Sum("forced_sale_value"))["t"] or 0)
    total_asset_locked = float(AssetCollateral.objects.filter(status="active").aggregate(t=Sum("forced_sale_value"))["t"] or 0)

    report = SASRAReport.objects.create(
        report_type=report_type,
        period_start=period_start,
        period_end=period_end,
        status="generated",
        generated_by=request.user,
        data_snapshot={
            "members": {"total": total_members, "active": active_members},
            "savings": {"total": total_savings, "deposits_period": total_deposits, "withdrawals_period": total_withdrawals},
            "loans": {"total": total_loans, "active": active_loans, "outstanding": total_outstanding, "repayments_period": total_repaid},
            "collateral": {"total_asset_value": total_asset_value, "total_asset_locked": total_asset_locked},
        },
    )

    AuditLog.log(request.user, "other", f"SASRA {report_type} report generated",
                 {"period": f"{period_start} to {period_end}"}, request)

    return Response({
        "message": "SASRA report generated.",
        "id": report.id,
        "report_type": report.report_type,
        "period_start": period_start,
        "period_end": period_end,
        "data_snapshot": report.data_snapshot,
    })


@api_view(["POST"])
@permission_classes([IsAdmin])
def sasra_submit(request, report_id):
    """Mark a SASRA report as submitted to the regulator."""
    try:
        report = SASRAReport.objects.get(id=report_id)
    except SASRAReport.DoesNotExist:
        return Response({"error": "Report not found."}, status=404)

    report.status = "submitted"
    report.submitted_at = timezone.now()
    report.save()

    AuditLog.log(request.user, "other", f"SASRA report #{report.id} submitted",
                 {"report_type": report.report_type}, request)
    return Response({"message": "SASRA report marked as submitted."})


# ─────────────────────────────────────────────────────────────────────────────
# 🚪 Exit Request — member submits formal exit from SACCO
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def exit_request(request):
    from .models import ExitRequest
    from .serializers import ExitRequestSerializer

    if request.method == "GET":
        req = ExitRequest.objects.filter(user=request.user).first()
        if not req:
            return Response({"exit_request": None})

        return Response({
            "exit_request": {
                "id":             req.id,
                "status":         req.status,
                "status_label":   req.get_status_display(),
                "reason":         req.reason,
                "bosa_balance":   float(req.bosa_balance),
                "approved_at":    req.approved_at,
                "release_date":   req.release_date,
                "released_at":    req.released_at,
                "review_notes":   req.review_notes,
                "rejection_reason": req.rejection_reason,
                "created_at":     req.created_at,
                "is_holding_period_over": req.is_holding_period_over,
            }
        })

    # POST — submit a new exit request
    serializer = ExitRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    # Block: cannot request exit if already have an open request
    if ExitRequest.objects.filter(
        user=request.user, status__in=["pending", "approved"]
    ).exists():
        return Response({
            "error": "You already have an active exit request. Please wait for it to be reviewed."
        }, status=400)

    from .collateral import get_bosa_balance, get_guarantor_pledges_detail

    bosa = get_bosa_balance(request.user)
    has_loan = Loan.objects.filter(
        user=request.user, status="approved", balance__gt=0
    ).exists()
    has_pledge = LoanGuarantor.objects.filter(
        guarantor=request.user, status="accepted",
        loan__status="approved", loan__balance__gt=0,
    ).exists()

    req = ExitRequest.objects.create(
        user=request.user,
        reason=serializer.validated_data.get("reason", ""),
        bosa_balance=bosa,
        has_active_loan=has_loan,
        has_guarantor_pledges=has_pledge,
    )

    Notification.send(
        request.user, "Exit Request Submitted",
        "Your request to exit the SACCO has been submitted and is under review. "
        "You will be notified once it is processed.",
        "info",
    )
    AuditLog.log(
        request.user, "other", "Exit request submitted",
        {"bosa": float(bosa), "has_loan": has_loan, "has_pledge": has_pledge}, request,
    )

    return Response({
        "message": "Exit request submitted. Our team will review it within 5 business days.",
        "id": req.id,
        "bosa_balance": float(bosa),
        "has_active_loan": has_loan,
        "has_guarantor_pledges": has_pledge,
    }, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_exit_request(request, exit_id):
    from .models import ExitRequest
    try:
        req = ExitRequest.objects.get(id=exit_id, user=request.user)
    except ExitRequest.DoesNotExist:
        return Response({"error": "Exit request not found."}, status=404)

    if req.status not in ("pending", "approved"):
        return Response({"error": f"Cannot cancel a request with status '{req.status}'."}, status=400)

    req.status = "cancelled"
    req.save()
    AuditLog.log(request.user, "other", "Exit request cancelled", request=request)
    return Response({"message": "Exit request cancelled."})


# ─────────────────────────────────────────────────────────────────────────────
# 🔑 Admin — review exit requests
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_exit_requests(request):
    from .models import ExitRequest
    status_filter = request.query_params.get("status", "all")
    qs = ExitRequest.objects.select_related("user", "reviewed_by").all()
    if status_filter != "all":
        qs = qs.filter(status=status_filter)

    return Response([
        {
            "id":             r.id,
            "member":         r.user.get_full_name() or r.user.username,
            "username":       r.user.username,
            "member_number":  getattr(getattr(r.user, "member_profile", None), "member_number", ""),
            "status":         r.status,
            "status_label":   r.get_status_display(),
            "reason":         r.reason,
            "bosa_balance":   float(r.bosa_balance),
            "has_active_loan": r.has_active_loan,
            "has_guarantor_pledges": r.has_guarantor_pledges,
            "approved_at":    r.approved_at,
            "release_date":   r.release_date,
            "released_at":    r.released_at,
            "review_notes":   r.review_notes,
            "rejection_reason": r.rejection_reason,
            "created_at":     r.created_at,
            "is_holding_period_over": r.is_holding_period_over,
        }
        for r in qs
    ])


@api_view(["POST"])
@permission_classes([IsAdmin])
def admin_review_exit(request, exit_id):
    from .models import ExitRequest
    from .serializers import ExitReviewSerializer
    from datetime import date, timedelta

    try:
        req = ExitRequest.objects.select_related("user").get(id=exit_id)
    except ExitRequest.DoesNotExist:
        return Response({"error": "Exit request not found."}, status=404)

    if req.status != "pending":
        return Response({"error": f"Request is already '{req.status}'."}, status=400)

    serializer = ExitReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    action = serializer.validated_data["action"]

    if action == "approve":
        # Re-check collateral before approving
        active_loan = Loan.objects.filter(
            user=req.user, status="approved", balance__gt=0
        ).exists()
        active_pledge = LoanGuarantor.objects.filter(
            guarantor=req.user, status="accepted",
            loan__status="approved", loan__balance__gt=0,
        ).exists()

        if active_loan:
            return Response({
                "error": "Cannot approve exit: member has an active unpaid loan."
            }, status=400)
        if active_pledge:
            return Response({
                "error": "Cannot approve exit: member is currently guaranteeing an active loan."
            }, status=400)

        hold_days = SACCOSettings.get_settings().bosa_exit_hold_days
        req.status      = "approved"
        req.approved_at = timezone.now()
        req.release_date = date.today() + timedelta(days=hold_days)
        req.reviewed_by  = request.user
        req.review_notes = serializer.validated_data.get("notes", "")
        req.save()

        Notification.send(
            req.user, "Exit Request Approved",
            f"Your exit request has been approved. Your BOSA funds of KES {req.bosa_balance:,.2f} "
            f"will be available for withdrawal on {req.release_date.strftime('%d %B %Y')} "
            f"({hold_days}-day holding period).",
            "success", "/savings",
        )
        AuditLog.log(
            request.user, "other", f"Exit approved for {req.user.username}",
            {"release_date": str(req.release_date)}, request,
        )
        return Response({
            "message":      f"Exit approved. Funds released on {req.release_date}.",
            "release_date": req.release_date,
        })

    else:  # reject
        req.status           = "rejected"
        req.reviewed_by      = request.user
        req.review_notes     = serializer.validated_data.get("notes", "")
        req.rejection_reason = serializer.validated_data.get("rejection_reason", "")
        req.save()

        Notification.send(
            req.user, "Exit Request Not Approved",
            f"Your exit request has not been approved at this time. "
            f"Reason: {req.rejection_reason or 'Please contact the SACCO office.'}",
            "warning",
        )
        AuditLog.log(
            request.user, "other", f"Exit rejected for {req.user.username}",
            {"reason": req.rejection_reason}, request,
        )
        return Response({"message": "Exit request rejected."})


# ─────────────────────────────────────────────────────────────────────────────
# 🔍 Financial Audit Engine endpoints
# ─────────────────────────────────────────────────────────────────────────────
from .audit_engine import run_full_audit, get_audit_summary
from .models import AuditFinding


@api_view(["POST"])
@permission_classes([IsAdmin])
def run_audit(request):
    """
    Execute the full financial audit engine.
    Clears previous open findings and stores new ones.
    Returns a summary of what was found.
    """
    import uuid

    run_id = str(uuid.uuid4())[:8]

    # Mark all previous open findings as superseded (dismissed) — they'll be re-checked
    AuditFinding.objects.filter(status="open").update(
        status="dismissed",
        review_notes="Superseded by new audit run",
    )

    findings = run_full_audit()

    created = []
    for f in findings:
        obj = AuditFinding.objects.create(
            rule=f["rule"],
            severity=f["severity"],
            title=f["title"],
            description=f["description"],
            entity_type=f.get("entity_type", ""),
            entity_id=f.get("entity_id"),
            user=f.get("user", ""),
            audit_run_id=run_id,
        )
        created.append(obj.id)

    AuditLog.log(
        request.user, "other", "Financial audit run",
        {"run_id": run_id, "findings": len(findings)}, request,
    )

    return Response({
        "message":    f"Audit complete: {len(findings)} finding(s) detected.",
        "run_id":     run_id,
        "summary":    get_audit_summary(),
        "findings":   len(findings),
    })


@api_view(["GET"])
@permission_classes([IsAdmin])
def audit_findings(request):
    """
    List all audit findings with optional filters.
    Query params: severity, status, rule, search
    """
    qs = AuditFinding.objects.all()

    severity = request.query_params.get("severity")
    if severity:
        qs = qs.filter(severity=severity)

    status_f = request.query_params.get("status")
    if status_f:
        qs = qs.filter(status=status_f)

    rule = request.query_params.get("rule")
    if rule:
        qs = qs.filter(rule=rule)

    search = request.query_params.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(user__icontains=search)
        )

    # Paginate
    page    = int(request.query_params.get("page", 1))
    per_page = int(request.query_params.get("per_page", 25))
    total   = qs.count()
    qs      = qs[(page - 1) * per_page: page * per_page]

    return Response({
        "total":   total,
        "page":    page,
        "pages":   (total + per_page - 1) // per_page,
        "summary": get_audit_summary(),
        "results": [
            {
                "id":            f.id,
                "rule":          f.rule,
                "severity":      f.severity,
                "title":         f.title,
                "description":    f.description,
                "entity_type":   f.entity_type,
                "entity_id":     f.entity_id,
                "user":          f.user,
                "status":        f.status,
                "reviewed_by":    f.reviewed_by.username if f.reviewed_by else "",
                "reviewed_at":   f.reviewed_at,
                "review_notes":  f.review_notes,
                "resolution":    f.resolution,
                "audit_run_id":  f.audit_run_id,
                "created_at":    f.created_at,
            }
            for f in qs
        ],
    })


@api_view(["POST"])
@permission_classes([IsAdmin])
def review_finding(request, finding_id):
    """
    Review/resolve an audit finding.
    Body: { status: "reviewing"|"resolved"|"dismissed", notes: "...", resolution: "..." }
    """
    try:
        finding = AuditFinding.objects.get(id=finding_id)
    except AuditFinding.DoesNotExist:
        return Response({"error": "Finding not found."}, status=404)

    new_status = request.data.get("status", "")
    if new_status not in ("reviewing", "resolved", "dismissed", "open"):
        return Response({"error": "Invalid status."}, status=400)

    finding.status       = new_status
    finding.reviewed_by   = request.user
    finding.reviewed_at   = timezone.now()
    finding.review_notes  = request.data.get("notes", "")
    finding.resolution    = request.data.get("resolution", "")
    finding.save()

    AuditLog.log(
        request.user, "other", f"Audit finding #{finding.id} → {new_status}",
        {"rule": finding.rule, "severity": finding.severity}, request,
    )

    return Response({"message": f"Finding marked as {new_status}."})


@api_view(["GET"])
@permission_classes([IsAdmin])
def audit_report(request):
    """
    Generate a full audit report with all findings grouped by rule and severity.
    """
    summary = get_audit_summary()
    findings = AuditFinding.objects.filter(status__in=["open", "reviewing"]).order_by(
        "-severity", "-created_at"
    )

    # Group by rule
    by_rule = {}
    for f in findings:
        if f.rule not in by_rule:
            by_rule[f.rule] = {"count": 0, "findings": []}
        by_rule[f.rule]["count"] += 1
        by_rule[f.rule]["findings"].append({
            "id":          f.id,
            "severity":    f.severity,
            "title":       f.title,
            "description": f.description,
            "user":        f.user,
            "status":      f.status,
            "created_at":  f.created_at,
        })

    return Response({
        "summary":    summary,
        "open_count": findings.filter(status="open").count(),
        "reviewing_count": findings.filter(status="reviewing").count(),
        "by_rule":    by_rule,
        "generated_at": timezone.now(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 🔍 CRB Check admin endpoints
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_crb_checks(request):
    """List all CRBCheck records, filterable by status and loan_id."""
    from .models import CRBCheck
    qs = CRBCheck.objects.select_related("loan", "member").order_by("-checked_at")
    status_filter  = request.query_params.get("status")
    loan_filter    = request.query_params.get("loan_id")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if loan_filter:
        qs = qs.filter(loan_id=loan_filter)
    data = []
    for c in qs:
        data.append({
            "id":                c.pk,
            "loan_id":           c.loan_id,
            "loan_amount":       float(c.loan.amount),
            "member_username":   c.member.username,
            "member_name":       c.member.get_full_name(),
            "provider":          c.provider,
            "status":            c.status,
            "score":             c.score,
            "active_loans_count":c.active_loans_count,
            "checked_at":        c.checked_at,
        })
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_crb_check_detail(request, check_id):
    """Retrieve a single CRBCheck record with raw_response."""
    from .models import CRBCheck
    from django.shortcuts import get_object_or_404
    c = get_object_or_404(CRBCheck, pk=check_id)
    return Response({
        "id":                c.pk,
        "loan_id":           c.loan_id,
        "loan_amount":       float(c.loan.amount),
        "loan_status":       c.loan.status,
        "member_username":   c.member.username,
        "member_name":       c.member.get_full_name(),
        "provider":          c.provider,
        "status":            c.status,
        "score":             c.score,
        "active_loans_count":c.active_loans_count,
        "raw_response":      c.raw_response,
        "checked_at":        c.checked_at,
        "override_by":       c.override_by.username if c.override_by else None,
        "override_at":       c.override_at,
        "override_notes":    c.override_notes,
    })


@api_view(["POST"])
@permission_classes([IsAdmin])
def admin_crb_override(request, check_id):
    """Override a flagged CRBCheck — set loan to approved and record override details."""
    from .models import CRBCheck
    from django.shortcuts import get_object_or_404
    from accounts.models import Notification, AuditLog

    c = get_object_or_404(CRBCheck, pk=check_id)
    notes = request.data.get("notes", "")

    if c.loan.status not in ("flagged",):
        return Response({"error": "Only flagged loans can be overridden."}, status=400)

    c.loan.status = "approved"
    c.loan.save(update_fields=["status"])

    c.override_by    = request.user
    c.override_at    = timezone.now()
    c.override_notes = notes
    c.save(update_fields=["override_by", "override_at", "override_notes"])

    Notification.send(
        c.member,
        title="Loan Application Approved",
        message=f"Your loan application of KES {c.loan.amount:,} has been approved by a loan officer.",
        ntype="success",
    )
    AuditLog.log(
        actor=request.user,
        action="crb_override",
        target=f"Loan #{c.loan_id}",
        details={
            "crb_check_id": c.pk,
            "loan_id": c.loan_id,
            "override_by_username": request.user.username,
            "notes": notes,
        },
        request=request,
    )
    return Response({"message": "Loan approved. CRB override recorded.", "loan_id": c.loan_id})
