from decimal import Decimal
from django.utils import timezone
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.contrib.auth import get_user_model

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response

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
    VALID_PERIODS,
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
    serializer = SavingsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount       = serializer.validated_data["amount"]
    account_type = serializer.validated_data.get("account_type", "fosa")

    # Enforce mandatory BOSA minimum if account_type is bosa
    settings_obj = SACCOSettings.get_settings()

    Savings.objects.create(
        user=request.user,
        amount=amount,
        account_type=account_type,
    )
    Transaction.objects.create(
        user=request.user, type="deposit", amount=amount,
        note=f"{account_type.upper()} deposit",
    )
    Notification.send(
        request.user, "Deposit Confirmed",
        f"KES {amount:,.2f} deposited to your {account_type.upper()} account.",
        "success", "/savings",
    )
    AuditLog.log(request.user, "deposit", "", {"amount": float(amount), "account": account_type}, request)
    total_after = float((
        Savings.objects.filter(user=request.user, account_type=account_type)
        .aggregate(t=Sum("amount"))["t"] or 0
    ))
    send_deposit_confirmation(request.user, float(amount), total_after)
    return Response({"message": f"Deposit to {account_type.upper()} successful."})


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

    if repayment_months not in VALID_PERIODS:
        return Response(
            {"error": f"Repayment period must be one of: {VALID_PERIODS}."},
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

    return Response({
        "message": "Loan application submitted successfully.",
        "loan_id":       loan.id,
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
    transactions = Transaction.objects.filter(user=user)

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
        "transactions": TransactionSerializer(transactions, many=True).data,
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
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from io import BytesIO

    user  = request.user
    try:
        member = user.member_profile
        member_number = member.member_number
    except Exception:
        member_number = "N/A"

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                  fontSize=18, textColor=colors.HexColor("#1e3a8a"),
                                  spaceAfter=4)
    sub_style   = ParagraphStyle("sub",   parent=styles["Normal"],
                                  fontSize=10, textColor=colors.HexColor("#64748b"),
                                  spaceAfter=2)

    story.append(Paragraph("SACCO Management System", title_style))
    story.append(Paragraph("Member Transaction Statement", sub_style))
    story.append(Paragraph(f"Member: {user.get_full_name() or user.username}  |  "
                            f"Member No: {member_number}  |  "
                            f"Generated: {timezone.now().strftime('%d %B %Y %H:%M')}", sub_style))
    story.append(Spacer(1, 0.4*cm))

    # Summary boxes
    total_savings = float(Savings.objects.filter(user=user).aggregate(t=Sum("amount"))["t"] or 0)
    loans_qs      = Loan.objects.filter(user=user)
    active_loan   = loans_qs.filter(status="approved", balance__gt=0).first()

    summary_data = [
        ["Total Savings", f"KES {total_savings:,.2f}"],
        ["Total Loans",   str(loans_qs.count())],
        ["Active Loan Balance", f"KES {float(active_loan.balance):,.2f}" if active_loan else "None"],
    ]
    summary_table = Table(summary_data, colWidths=[6*cm, 8*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#eff6ff")),
        ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 10),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#bfdbfe")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#eff6ff"), colors.white]),
        ("PADDING",    (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.5*cm))

    # Transactions
    story.append(Paragraph("Transaction History", styles["Heading2"]))
    story.append(Spacer(1, 0.2*cm))

    txns     = Transaction.objects.filter(user=user).order_by("-created_at")
    tx_data  = [["#", "Date", "Type", "Note", "Amount (KES)"]]
    for i, t in enumerate(txns, 1):
        sign = "+" if t.type in ("deposit",) else ("−" if t.type in ("withdrawal",) else "")
        tx_data.append([
            str(i),
            t.created_at.strftime("%d/%m/%Y"),
            t.type.title(),
            t.note[:40] if t.note else "",
            f"{sign} {float(t.amount):,.2f}",
        ])

    if len(tx_data) > 1:
        tx_table = Table(tx_data, colWidths=[1*cm, 2.8*cm, 3*cm, 5*cm, 3.5*cm])
        tx_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0),   colors.HexColor("#1e3a8a")),
            ("TEXTCOLOR",  (0,0), (-1,0),   colors.white),
            ("FONTNAME",   (0,0), (-1,0),   "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1),  9),
            ("GRID",       (0,0), (-1,-1),  0.3, colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
            ("ALIGN",      (0,0), (-1,-1),  "LEFT"),
            ("PADDING",    (0,0), (-1,-1),  5),
        ]))
        story.append(tx_table)
    else:
        story.append(Paragraph("No transactions on record.", styles["Normal"]))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("— End of Statement —",
                            ParagraphStyle("footer", parent=styles["Normal"],
                                           fontSize=8, textColor=colors.HexColor("#94a3b8"),
                                           alignment=1)))

    doc.build(story)
    buf.seek(0)

    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="sacco_statement_{user.username}.pdf"'
    AuditLog.log(user, "export", "PDF statement", request=request)
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
        })

    # PUT
    settings.release_hierarchy       = request.data.get("release_hierarchy", settings.release_hierarchy)
    settings.default_ltv_ratio        = Decimal(str(request.data.get("default_ltv_ratio", settings.default_ltv_ratio)))
    settings.min_savings_retention    = Decimal(str(request.data.get("min_savings_retention", settings.min_savings_retention)))
    settings.sasra_enabled            = request.data.get("sasra_enabled", settings.sasra_enabled)
    settings.sasra_report_interval_days = int(request.data.get("sasra_report_interval_days", settings.sasra_report_interval_days))
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
