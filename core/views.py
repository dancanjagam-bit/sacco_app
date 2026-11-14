from decimal import Decimal
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
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

from .models import (
    Savings, Loan, Transaction, LoanGuarantor, FosaWithdrawal,
    WithdrawalCorrectionProposal, MpesaTransaction, LoanAssessment,
)
from .serializers import (
    SavingsSerializer,
    LoanApplicationSerializer,
    RepaymentSerializer,
    LoanSerializer,
    TransactionSerializer,
    TransactionFilterSerializer,
)
from .eligibility import (
    get_eligibility,
)
from .services.loan_calculation import LoanCalculationError, calculate_flat_term, quote_savings_loan, serialize_quote
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
        from accounts.access import is_staff_manager
        return is_staff_manager(request.user)


def _active_loan_duty_ids(user, duty):
    """Return currently assigned loan ids, or None when duty tables are absent."""
    from accounts.access import active_staff_duties
    try:
        return set(active_staff_duties(user, duty).values_list("loan_id", flat=True))
    except (OperationalError, ProgrammingError):
        return None


def _loan_duty_allowed(user, loan_id, duty, permission):
    from accounts.access import has_sacco_permission
    if not has_sacco_permission(user, permission):
        return False, "denied"
    assigned = _active_loan_duty_ids(user, duty)
    if assigned is None:
        return False, "schema"
    return (loan_id in assigned), "scope"


# ─────────────────────────────────────────────────────────────────────────────
# 💰 Deposit savings
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deposit(request):
    """Post an evidenced staff deposit; members must use the provider flow.

    A request made by a member is not evidence that funds were received. The
    normal member path is the stored M-Pesa STK transaction and its callback.
    Manual deposits are limited to active accountants (or Django
    superusers), and require a reason so the posting is reviewable.
    """
    serializer = SavingsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount       = serializer.validated_data["amount"]
    account_type = serializer.validated_data.get("account_type", "fosa")
    staff_profile = getattr(request.user, "staff_profile", None)
    may_post_manual = request.user.is_superuser or bool(
        staff_profile
        and staff_profile.status == "active"
        and staff_profile.role == "accountant"
    )
    if not may_post_manual:
        return Response({
            "code": "provider_confirmation_required",
            "error": "Deposits must be confirmed through the M-Pesa payment flow.",
            "payment_endpoint": "/api/payments/mpesa/stk/",
        }, status=403)

    reason = str(request.data.get("reason", "")).strip()
    if len(reason) < 8:
        return Response({"reason": "Provide a reason of at least 8 characters for this manual posting."}, status=400)

    target_user = request.user
    target_user_id = request.data.get("user_id")
    if target_user_id:
        if not may_post_manual:
            return Response({"error": "Not authorized to post for another member."}, status=403)
        try:
            target_user = get_user_model().objects.get(pk=target_user_id, is_member=True)
        except (get_user_model().DoesNotExist, ValueError, TypeError):
            return Response({"error": "Member not found."}, status=404)

    with transaction.atomic():
        Savings.objects.create(
            user=target_user,
            amount=amount,
            account_type=account_type,
        )
        ledger_entry = Transaction.objects.create(
            user=target_user, type="deposit", amount=amount,
            account_type=account_type,
            note=f"{account_type.upper()} manual deposit: {reason[:120]}",
        )
        AuditLog.log(
            request.user, "deposit", f"Manual deposit transaction #{ledger_entry.pk}",
            {"amount": str(amount), "account": account_type,
             "member_user_id": target_user.pk, "reason": reason[:240],
             "method": "staff_manual"}, request,
        )
        total_after = Savings.objects.filter(
            user=target_user, account_type=account_type,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
        transaction.on_commit(lambda: Notification.send(
            target_user, "Deposit recorded",
            f"A staff-recorded deposit of KES {amount:,.2f} was posted to your {account_type.upper()} account.",
            "success", "/savings",
        ))
        transaction.on_commit(lambda: send_deposit_confirmation(
            target_user, float(amount), float(total_after),
        ))
    return Response({
        "message": f"Manual deposit posted to {account_type.upper()}.",
        "transaction_id": ledger_entry.pk,
        "status": "posted",
    }, status=201)


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

    # ── Eligibility check ───────────────────────────────────────────────
    report = get_eligibility(request.user)

    if not report["eligible"]:
        return Response({"error": report["rejection_reason"]}, status=400)

    try:
        quote = quote_savings_loan(serializer.validated_data["product"], amount, repayment_months, report["interest_band"])
    except LoanCalculationError as exc:
        return Response({"error": str(exc)}, status=400)

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
    interest = quote["interest_rate"]

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
        "repayment_estimate": serialize_quote(quote),
        "max_loan":      float(report["max_loan"]),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 👮 Approve loan (admin)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_loan(request, loan_id):
    try:
        loan = Loan.objects.select_related("user").get(id=loan_id)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    allowed, reason = _loan_duty_allowed(request.user, loan.id, "loan_approval", "loans.approve_assigned")
    if reason == "schema":
        return Response({"detail": "Scoped loan decision assignments are unavailable until the staff-access migration is applied."}, status=503)
    if not allowed:
        return Response({"detail": "This loan decision is not assigned to your account."}, status=403)

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

    try:
        loan.balance = calculate_flat_term(loan.amount, loan.repayment_months, loan.interest)["total_repayment"]
    except LoanCalculationError as exc:
        return Response({"error": str(exc)}, status=422)
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
@permission_classes([IsAuthenticated])
def reject_loan(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    allowed, reason = _loan_duty_allowed(request.user, loan.id, "loan_approval", "loans.approve_assigned")
    if reason == "schema":
        return Response({"detail": "Scoped loan decision assignments are unavailable until the staff-access migration is applied."}, status=503)
    if not allowed:
        return Response({"detail": "This loan decision is not assigned to your account."}, status=403)

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
@permission_classes([IsAuthenticated])
def admin_loans(request):
    from accounts.access import has_sacco_permission
    can_appraise = has_sacco_permission(request.user, "loans.appraise_assigned")
    can_decide = has_sacco_permission(request.user, "loans.approve_assigned")
    if not can_appraise and not can_decide:
        return Response({"detail": "Assigned loan review permission required."}, status=403)
    appraisal_ids = _active_loan_duty_ids(request.user, "loan_appraisal") if can_appraise else set()
    approval_ids = _active_loan_duty_ids(request.user, "loan_approval") if can_decide else set()
    if appraisal_ids is None or approval_ids is None:
        return Response({"detail": "Scoped loan assignments are unavailable until the staff-access migration is applied."}, status=503)
    allowed_ids = appraisal_ids | approval_ids
    # A reviewer with no current assignment sees a valid empty queue. Access
    # permission and record scope are distinct; an empty queue is not a denial.
    status_filter = request.query_params.get("status", "all")
    qs = Loan.objects.select_related("user", "approved_by").filter(pk__in=allowed_ids)

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
            "can_appraise": loan.id in appraisal_ids,
            "can_decide": loan.id in approval_ids,
        })

    return Response(loans)


# ─────────────────────────────────────────────────────────────────────────────
# 📊 Member dashboard
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    user = request.user
    member = getattr(user, "member_profile", None)
    from core.transport_models import TransportRole
    roles = list(TransportRole.objects.filter(user=user, active=True).order_by("role").values_list("role", flat=True))
    savings_totals = {row["account_type"]: row["total"] for row in Savings.objects.filter(user=user).values("account_type").annotate(total=Sum("amount"))}
    bosa = savings_totals.get("bosa") or Decimal("0.00")
    fosa = savings_totals.get("fosa") or Decimal("0.00")
    balance = get_withdrawable_balance(user)
    loans = Loan.objects.filter(user=user)
    transactions = Transaction.objects.filter(user=user).select_related("fosa_withdrawal", "mpesa_payment").order_by("-created_at", "-id")
    total_deposits = Transaction.objects.filter(user=user, type="deposit").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    from accounts.access import access_snapshot
    access = access_snapshot(user, transport_roles=roles)
    return Response({
        "id": user.pk,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_admin": bool(getattr(user, "is_admin", False)),
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "is_member": bool(getattr(user, "is_member", False)),
        "staff_role": getattr(getattr(user, "staff_profile", None), "role", None),
        "transport_roles": roles,
        "permissions": access["permissions"],
        "workspaces": access["workspaces"],
        "default_workspace": access["default_workspace"],
        "staff_roles": access.get("staff_roles", []),
        "staff_role_grants_available": access.get("staff_role_grants_available", True),
        "member_number": getattr(member, "member_number", "") if member else "",
        "phone_number": getattr(member, "phone_number", "") if member else "",
        "daraja_registered": getattr(member, "daraja_registered", False) if member else False,
        "total_savings": float(bosa + fosa),
        "total_deposits": float(total_deposits),
        "bosa_savings": float(bosa),
        "fosa_savings": float(fosa),
        "fosa_balance": float(balance["fosa_balance"]),
        "fosa_available": float(balance["fosa_withdrawable"]),
        "fosa_held_for_withdrawals": float(balance.get("fosa_withdrawals_pending", 0)),
        "fosa_locked_as_collateral": float(balance.get("fosa_collateral_locked", 0)),
        "share_capital": None,
        "total_loans": loans.count(),
        "pending_loans": loans.filter(status="pending").count(),
        "approved_loans": loans.filter(status="approved").count(),
        "outstanding_loan_balance": float(loans.filter(status="approved").aggregate(total=Sum("balance"))["total"] or Decimal("0.00")),
        "loans": LoanSerializer(loans, many=True).data,
        "transactions": TransactionSerializer(transactions[:25], many=True).data,
        "transaction_count": transactions.count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 💳 Repay loan
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def repay_loan(request, loan_id):
    # This legacy endpoint used to reduce a loan and create a ledger entry from
    # a member-supplied amount, without evidence that money was received. Keep
    # the URL for older clients, but require the stored M-Pesa request/callback
    # workflow so settlement is posted only after provider confirmation.
    return Response({
        "error": "Direct loan repayments are disabled. Start a payment through the confirmed M-Pesa repayment flow.",
        "payment_endpoint": "/api/payments/mpesa/stk/",
    }, status=409)


def _validated_statement_date_range(request):
    supplied = {}
    start = request.query_params.get("from", "").strip()
    end = request.query_params.get("to", "").strip()
    if start:
        supplied["from_date"] = start
    if end:
        supplied["to_date"] = end
    serializer = TransactionFilterSerializer(data=supplied)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data.get("from_date"), serializer.validated_data.get("to_date")

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

    # Rows. Date filters are intentionally scoped to the signed-in member.
    transactions = Transaction.objects.filter(user=request.user)
    from_date, to_date = _validated_statement_date_range(request)
    if from_date:
        transactions = transactions.filter(created_at__date__gte=from_date)
    if to_date:
        transactions = transactions.filter(created_at__date__lte=to_date)
    transactions = transactions.order_by("-created_at", "-id")
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
    from .services.fosa_payouts import (
        get_live_payout_provider, reserve_and_submit_withdrawal,
        IdempotencyConflict, InsufficientPayoutFunds, PayoutUnavailable,
    )

    serializer = WithdrawalSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    amount       = serializer.validated_data["amount"]
    account_type = serializer.validated_data.get("account_type", "fosa")

    if account_type == "fosa":
        provider = get_live_payout_provider()
        if provider is None:
            return Response({
                "code": "payout_unavailable",
                "status": "unavailable",
                "error": (
                    "FOSA withdrawals are temporarily unavailable because a live "
                    "disbursement provider is not configured. No funds were debited."
                ),
            }, status=503)
        try:
            payout, created = reserve_and_submit_withdrawal(
                user=request.user,
                amount=amount,
                destination_type=serializer.validated_data["destination_type"],
                destination=serializer.validated_data["destination"],
                client_request_id=serializer.validated_data["client_request_id"],
                provider=provider,
            )
        except IdempotencyConflict:
            return Response({"error": "This request reference was already used with different details."}, status=409)
        except InsufficientPayoutFunds:
            return Response({"error": "Insufficient available FOSA funds."}, status=400)
        except (PayoutUnavailable, ValueError) as exc:
            return Response({"error": str(exc) or "Payout is unavailable."}, status=503)
        return Response({
            "reference": str(payout.reference),
            "status": payout.status,
            "amount": str(payout.amount),
            "created": created,
            "message": "Withdrawal request received; payment remains pending provider confirmation.",
        }, status=202)

    collateral = get_withdrawable_balance(request.user)

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

        # Exit approvals do not themselves disburse money. Until a supported
        # payout adapter exists, do not post an accounting debit or claim release.
        if account_type == "bosa":
            return Response({
                "code": "payout_unavailable",
                "status": "unavailable",
                "error": "BOSA exit disbursement is not configured. No funds were released.",
            }, status=503)

        # All checks passed — release BOSA funds
        Savings.objects.create(user=request.user, amount=-amount, account_type="bosa")
        Transaction.objects.create(
            user=request.user, type="withdrawal", amount=amount,
            account_type="bosa",
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
def my_transactions(request):
    raw_filters = {
        "type": request.query_params.get("type", "all"),
        "from_date": request.query_params.get("from", ""),
        "to_date": request.query_params.get("to", ""),
        "search": request.query_params.get("search", ""),
    }
    filters = TransactionFilterSerializer(data={key: value for key, value in raw_filters.items() if value != ""})
    filters.is_valid(raise_exception=True)
    validated = filters.validated_data

    account_transactions = Transaction.objects.filter(user=request.user).select_related("fosa_withdrawal", "mpesa_payment")
    summary = account_transactions.aggregate(
        deposits=Sum("amount", filter=Q(type="deposit")),
        loans=Sum("amount", filter=Q(type="loan")),
        repayments=Sum("amount", filter=Q(type="repayment")),
        withdrawals=Sum("amount", filter=Q(type="withdrawal")),
        count=Count("id"),
    )
    queryset = account_transactions
    transaction_type = validated.get("type", "all")
    if transaction_type != "all":
        queryset = queryset.filter(type=transaction_type)
    start_date = validated.get("from_date")
    end_date = validated.get("to_date")
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    search = validated.get("search", "").strip()
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
        "deposits": str(summary["deposits"] or Decimal("0.00")),
        "loans": str(summary["loans"] or Decimal("0.00")),
        "repayments": str(summary["repayments"] or Decimal("0.00")),
        "withdrawals": str(summary["withdrawals"] or Decimal("0.00")),
        "count": summary["count"],
    }
    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_fosa_withdrawals(request):
    rows = FosaWithdrawal.objects.filter(user=request.user)[:50]
    return Response([{
        "reference": str(row.reference),
        "amount": str(row.amount),
        "destination_type": row.destination_type,
        "destination_masked": f"…{row.destination_phone[-3:]}",
        "status": row.status,
        "provider_reference": row.provider_reference or None,
        "provider_transaction_id": row.provider_transaction_id,
        "created_at": row.created_at,
        "settled_at": row.settled_at,
    } for row in rows])

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def withdrawal_reconciliation_report(request):
    """Restricted, privacy-minimized list of debits without verified payout evidence."""
    from accounts.access import has_sacco_permission
    if not has_sacco_permission(request.user, "payments.reconcile"):
        return Response({"detail": "Payment reconciliation permission required."}, status=403)
    transactions = Transaction.objects.filter(type="withdrawal").order_by("created_at")
    rows = []
    for txn in transactions:
        payout = getattr(txn, "fosa_withdrawal", None)
        if payout and payout.status == "succeeded" and payout.provider_transaction_id:
            continue
        proposals = txn.withdrawal_corrections.all()
        rows.append({
            "transaction_id": txn.id,
            "amount": str(txn.amount),
            "status": "needs_investigation",
            "provider_reference": payout.provider_reference or None if payout else None,
            "provider_transaction_id": payout.provider_transaction_id if payout else None,
            "category": "BOSA exit" if "bosa" in txn.note.lower() else "FOSA/legacy withdrawal",
            "correction_status": proposals.order_by("-created_at").values_list("status", flat=True).first(),
        })
    return Response({"count": len(rows), "withdrawals": rows})

class CanReviewWithdrawalCorrection(BasePermission):
    def has_permission(self, request, view):
        from accounts.access import has_sacco_permission
        return has_sacco_permission(request.user, "payments.reconcile")

@api_view(["GET", "POST"])
@permission_classes([CanReviewWithdrawalCorrection])
def withdrawal_correction_proposals(request):
    if request.method == "GET":
        proposals = WithdrawalCorrectionProposal.objects.select_related(
            "original_transaction", "proposed_by", "decided_by",
        ).all()[:200]
        return Response([{
            "id": item.id,
            "transaction_id": item.original_transaction_id,
            "amount": str(item.original_transaction.amount),
            "reason": item.reason,
            "evidence_reference": item.evidence_reference,
            "status": item.status,
            "created_at": item.created_at,
            "decided_at": item.decided_at,
        } for item in proposals])

    try:
        transaction_id = int(request.data.get("transaction_id"))
        savings_id = int(request.data.get("savings_id"))
    except (TypeError, ValueError):
        return Response({"error": "Valid transaction_id and savings_id are required."}, status=400)
    reason = str(request.data.get("reason", "")).strip()
    evidence = str(request.data.get("evidence_reference", "")).strip()
    if len(reason) < 10 or not evidence or len(evidence) > 120:
        return Response({"error": "Provide a correction reason and confirmed-failure evidence reference."}, status=400)
    try:
        original = Transaction.objects.get(pk=transaction_id, type="withdrawal")
        savings = Savings.objects.get(
            pk=savings_id, user=original.user, amount=-original.amount,
            account_type__in=("fosa", "bosa"),
        )
    except (Transaction.DoesNotExist, Savings.DoesNotExist):
        return Response({"error": "The withdrawal ledger and matching savings debit were not found."}, status=404)
    if getattr(original, "fosa_withdrawal", None):
        return Response({"error": "Provider-linked withdrawals cannot use legacy correction proposals."}, status=409)
    if Transaction.objects.filter(reverses=original).exists():
        return Response({"error": "This withdrawal already has a posted reversal."}, status=409)

    proposal, created = WithdrawalCorrectionProposal.objects.get_or_create(
        original_transaction=original,
        defaults={
            "original_savings": savings,
            "reason": reason,
            "evidence_reference": evidence,
            "proposed_by": request.user,
        },
    )
    if not created:
        return Response({"error": "An active correction proposal already exists for this transaction."}, status=409)
    AuditLog.log(
        request.user, "withdrawal_correction_proposed", str(transaction_id),
        {"savings_id": savings_id, "evidence_reference": evidence, "reason": reason}, request,
    )
    return Response({"id": proposal.id, "status": proposal.status}, status=201)

@api_view(["POST"])
@permission_classes([CanReviewWithdrawalCorrection])
def decide_withdrawal_correction(request, proposal_id):
    action = request.data.get("action")
    reason = str(request.data.get("reason", "")).strip()
    if action not in ("approve", "reject") or len(reason) < 10:
        return Response({"error": "Select approve or reject and provide a decision reason."}, status=400)
    with transaction.atomic():
        try:
            proposal = WithdrawalCorrectionProposal.objects.select_for_update().select_related(
                "original_transaction", "original_savings",
            ).get(pk=proposal_id)
        except WithdrawalCorrectionProposal.DoesNotExist:
            return Response({"error": "Correction proposal not found."}, status=404)
        if proposal.status != "proposed":
            return Response({"error": "This proposal has already been decided."}, status=409)
        if proposal.proposed_by_id == request.user.pk:
            return Response({"error": "A different authorized staff member must decide this correction."}, status=403)
        if action == "approve":
            if Transaction.objects.filter(reverses=proposal.original_transaction).exists():
                return Response({"error": "This withdrawal already has a posted reversal."}, status=409)
            credit = -proposal.original_savings.amount
            if credit <= 0:
                return Response({"error": "Only a verified negative savings debit can be reversed."}, status=409)
            saving_entry = Savings.objects.create(
                user=proposal.original_savings.user,
                amount=credit,
                account_type=proposal.original_savings.account_type,
            )
            correction = Transaction.objects.create(
                user=proposal.original_transaction.user,
                type="adjustment", amount=credit,
                account_type=proposal.original_transaction.account_type or proposal.original_savings.account_type,
                note=f"Approved reversal of withdrawal transaction {proposal.original_transaction_id}",
                reverses=proposal.original_transaction,
            )
            proposal.correction_transaction = correction
            proposal.status = "approved"
            target = f"withdrawal:{proposal.original_transaction_id}:savings:{saving_entry.pk}"
        else:
            proposal.status = "rejected"
            target = f"withdrawal:{proposal.original_transaction_id}"
        proposal.decided_by = request.user
        proposal.decided_at = timezone.now()
        proposal.save(update_fields=("status", "decided_by", "decided_at", "correction_transaction"))
        AuditLog.log(
            request.user, "withdrawal_correction_" + action, target,
            {"proposal_id": proposal.id, "reason": reason,
                "evidence_reference": proposal.evidence_reference}, request,
        )
    return Response({"id": proposal.id, "status": proposal.status})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def repayment_schedule(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id, user=request.user)
    except Loan.DoesNotExist:
        return Response({"error": "Loan not found."}, status=404)

    if loan.status not in ("approved", "repaid"):
        return Response({"error": "Schedule only available for approved/repaid loans."}, status=400)

    if loan.repayment_months < 1:
        return Response({
            "code": "invalid_repayment_schedule",
            "error": "A repayment schedule is unavailable because this loan has no valid repayment period recorded. Contact the SACCO office to review the loan terms.",
        }, status=422)

    terms = calculate_flat_term(loan.amount, loan.repayment_months, loan.interest)
    total_payable = terms["total_repayment"]
    monthly_payment = terms["estimated_installment"]
    start_date       = loan.approved_at or loan.created_at

    schedule = []
    repayments = list(_loan_repayment_transactions(loan).order_by("created_at", "pk"))

    running_balance = total_payable
    for row in terms["schedule"]:
        i = row["month"]
        expected = row["payment"]
        due_date      = timezone.localdate(start_date) + relativedelta(months=i)
        paid_amount   = Decimal("0")
        paid_on       = None
        status        = "upcoming"

        if i <= len(repayments):
            paid_amount = repayments[i - 1].amount
            paid_on     = repayments[i - 1].created_at.date()
            running_balance -= paid_amount
            status = "paid" if paid_amount >= expected else "partial"
        elif due_date < timezone.localdate():
            status = "overdue"

        schedule.append({
            "installment":   i,
            "due_date":      due_date,
            "expected":      float(expected),
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
    entries = Savings.objects.filter(user=request.user).order_by("created_at", "id")

    statement = []
    running_by_account = {"bosa": Decimal("0"), "fosa": Decimal("0")}
    for e in entries:
        account_type = e.account_type or "fosa"
        running_by_account[account_type] = running_by_account.get(account_type, Decimal("0")) + e.amount
        statement.append({
            "id":          e.id,
            "date":        e.created_at.date(),
            "type":        "Deposit" if e.amount > 0 else "Withdrawal",
            "account_type": account_type,
            "amount":      float(abs(e.amount)),
            "balance":     float(running_by_account[account_type]),
            "created_at":  e.created_at,
        })

    return Response({
        "total_balance": float(sum(running_by_account.values(), Decimal("0"))),
        "bosa_balance": float(running_by_account.get("bosa", Decimal("0"))),
        "fosa_balance": float(running_by_account.get("fosa", Decimal("0"))),
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
        SimpleDocTemplate, Table, LongTable, TableStyle, Paragraph,
        Spacer, HRFlowable, KeepTogether,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Line
    from reportlab.graphics import renderPDF
    from io import BytesIO
    import math
    from xml.sax.saxutils import escape as xml_escape

    # ── Colour palette ──────────────────────────────────────────────────────
    C_NAVY    = colors.HexColor("#0b1437")   # deep midnight navy
    C_INDIGO  = colors.HexColor("#4f46e5")   # electric indigo (primary brand)
    C_EMERALD = colors.HexColor("#047857")   # success / posted credit
    C_ROSE    = colors.HexColor("#BE123C")   # issue statuses only
    C_GOLD    = colors.HexColor("#FDE68A")   # restrained cooperative accent
    C_MUTED   = colors.HexColor("#52617E")   # readable supporting text
    C_BORDER  = colors.HexColor("#D6DFF0")   # subtle border
    C_BG_SOFT = colors.HexColor("#F0F4FF")   # page background
    C_BG_ROW  = colors.HexColor("#F8FAFF")   # alternating row tint
    C_WHITE   = colors.white

    # ── Data collection ─────────────────────────────────────────────────────
    user  = request.user
    now   = timezone.now()

    # Date range from query params (default: last 3 months). Invalid or
    # reversed user filters are a validation error, never a silent default.
    from datetime import datetime, time, timedelta
    from_date, to_date = _validated_statement_date_range(request)
    from_dt = timezone.make_aware(datetime.combine(from_date, time.min)) if from_date else now - timedelta(days=90)
    to_dt = timezone.make_aware(datetime.combine(to_date, time.max)) if to_date else now

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

    total_savings_val = Savings.objects.filter(user=user).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    bosa_balance = Savings.objects.filter(user=user, account_type="bosa").aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    fosa_balance = Savings.objects.filter(user=user, account_type="fosa").aggregate(t=Sum("amount"))["t"] or Decimal("0.00")

    # Transaction rows are ledger postings, except legacy loan applications
    # and FOSA withdrawals without a provider-settled reference. Keep those
    # visible in the review/pending section and out of settled balances.
    all_txns = list(
        Transaction.objects.filter(user=user).select_related("reverses", "mpesa_payment").order_by("created_at", "pk")
    )
    transactions_by_id = {entry.pk: entry for entry in all_txns}
    payout_by_transaction = {
        payout.ledger_transaction_id: payout
        for payout in FosaWithdrawal.objects.filter(user=user, ledger_transaction__isnull=False)
    }
    reversal_ids = set(
        Transaction.objects.filter(user=user, reverses_id__isnull=False).values_list("reverses_id", flat=True)
    )

    posted_cache = {}
    def is_posted_entry(entry, seen=None):
        if entry.pk in posted_cache:
            return posted_cache[entry.pk]
        seen = set() if seen is None else seen
        if entry.pk in seen:
            return False
        seen.add(entry.pk)
        if entry.type == "loan" and "application" in (entry.note or "").lower():
            posted = False
        elif entry.type == "withdrawal":
            payout = payout_by_transaction.get(entry.pk)
            is_bosa_exit = entry.account_type == "bosa" and "bosa exit" in (entry.note or "").lower()
            posted = is_bosa_exit or bool(
                payout and payout.status == "succeeded" and payout.provider_transaction_id
            ) or entry.pk in reversal_ids
        elif entry.type == "adjustment":
            original = transactions_by_id.get(entry.reverses_id)
            posted = bool(original and is_posted_entry(original, seen))
        else:
            posted = True
        posted_cache[entry.pk] = posted
        return posted

    def entry_effect(entry, seen=None):
        """Signed account movement; linked reversals exactly negate their source."""
        amount = abs(entry.amount)
        if entry.type == "adjustment":
            original = transactions_by_id.get(entry.reverses_id)
            if not original:
                return None
            original_effect = entry_effect(original, seen)
            return -original_effect if original_effect is not None else None
        if entry.type in ("deposit", "loan", "dividend"):
            return amount
        if entry.type in ("withdrawal", "repayment"):
            return -amount
        return None

    account_labels = {"bosa": "BOSA savings", "fosa": "FOSA savings", "loan": "Loan account", "other": "Other account activity"}
    posted_by_account = {key: [] for key in account_labels}
    unclassified_or_review = []
    for entry in all_txns:
        posted = is_posted_entry(entry)
        if not posted or entry.account_type not in account_labels or entry_effect(entry) is None:
            if from_dt <= entry.created_at <= to_dt:
                unclassified_or_review.append(entry)
            continue
        posted_by_account[entry.account_type].append(entry)

    opening_by_account = {
        account_type: sum(
            (entry_effect(entry) for entry in entries if entry.created_at < from_dt), Decimal("0.00")
        )
        for account_type, entries in posted_by_account.items()
    }
    period_by_account = {
        account_type: [entry for entry in entries if from_dt <= entry.created_at <= to_dt]
        for account_type, entries in posted_by_account.items()
    }

    unsettled_payments = list(
        MpesaTransaction.objects.filter(
            user=user, payment_type__in=("deposit", "repayment"), status="pending",
            created_at__gte=from_dt, created_at__lte=to_dt,
        ).order_by("created_at", "pk")
    )
    payout_requests = list(
        FosaWithdrawal.objects.filter(user=user, created_at__gte=from_dt, created_at__lte=to_dt)
        .exclude(status="succeeded", provider_transaction_id__gt="", ledger_transaction__isnull=False)
        .order_by("created_at", "pk")
    )

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
    CELL_DEBIT      = ps("cellDeb",   fontSize=8.5, textColor=C_NAVY,  fontName="Helvetica-Bold",
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

    # ── ① ORIGINAL NAIROBI WEST BRAND HEADER ───────────────────────────────
    # Cooperative tuktuk mark and identity sit beside the statement name.

    def _draw_logo_mark(drawing, x, y, sz):
        """Draw a compact Nairobi West three-wheeler mark for the statement."""
        from reportlab.graphics.shapes import Rect as RLRect, Circle as RLCircle, Line as RLLine, Polygon as RLPolygon
        scale = sz / 80.0

        def sc(value):
            return value * scale

        soft = colors.HexColor("#EEF2FF")
        indigo = colors.HexColor("#4F46E5")
        navy = colors.HexColor("#0B1437")
        emerald = colors.HexColor("#047857")
        white = colors.white

        backing = RLCircle(x + sc(40), y + sc(38), sc(37))
        backing.fillColor = soft
        backing.strokeColor = colors.HexColor("#C7D2FE")
        backing.strokeWidth = sc(1.5)
        drawing.add(backing)

        # Small passenger cabin and the raised canvas roof identify a tuk-tuk.
        roof = RLPolygon([
            x + sc(14), y + sc(43), x + sc(24), y + sc(61),
            x + sc(57), y + sc(61), x + sc(71), y + sc(46),
            x + sc(66), y + sc(42),
        ])
        roof.fillColor = indigo
        roof.strokeColor = navy
        roof.strokeWidth = sc(1.5)
        drawing.add(roof)

        body = RLPolygon([
            x + sc(12), y + sc(25), x + sc(57), y + sc(25),
            x + sc(74), y + sc(38), x + sc(73), y + sc(47),
            x + sc(12), y + sc(47),
        ])
        body.fillColor = navy
        body.strokeColor = navy
        drawing.add(body)

        rear_window = RLRect(x + sc(24), y + sc(43), sc(18), sc(13))
        rear_window.fillColor = colors.HexColor("#E0E7FF")
        rear_window.strokeColor = None
        drawing.add(rear_window)

        front_window = RLPolygon([
            x + sc(46), y + sc(43), x + sc(56), y + sc(57),
            x + sc(67), y + sc(46), x + sc(58), y + sc(43),
        ])
        front_window.fillColor = colors.HexColor("#C7D2FE")
        front_window.strokeColor = None
        drawing.add(front_window)

        belt = RLRect(x + sc(13), y + sc(31), sc(58), sc(4))
        belt.fillColor = emerald
        belt.strokeColor = None
        drawing.add(belt)

        for wheel_x in (25, 64):
            wheel = RLCircle(x + sc(wheel_x), y + sc(20), sc(7))
            wheel.fillColor = navy
            wheel.strokeColor = white
            wheel.strokeWidth = sc(1.8)
            drawing.add(wheel)
            hub = RLCircle(x + sc(wheel_x), y + sc(20), sc(2.5))
            hub.fillColor = colors.HexColor("#A5B4FC")
            hub.strokeColor = None
            drawing.add(hub)

        road = RLLine(x + sc(9), y + sc(10), x + sc(72), y + sc(10))
        road.strokeColor = emerald
        road.strokeWidth = sc(2)
        drawing.add(road)
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

    # ── ② MEMBER AND PERIOD DETAILS ────────────────────────────────────────
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

    # ── ④ POSTED ACCOUNT ACTIVITY ─────────────────────────────────────────
    story.append(Paragraph("Posted account activity", ps("postedActivity", fontSize=12, textColor=C_NAVY,
        fontName="Helvetica-Bold", leading=15, spaceAfter=4)))
    story.append(Paragraph(
        "Each account has its own opening, movement, and closing balance. Pending or unverified activity is listed separately and is excluded from these balances.",
        ps("accountNote", fontSize=8.5, textColor=C_MUTED, fontName="Helvetica", leading=12, spaceAfter=8),
    ))

    ACCOUNT_ORDER = ("bosa", "fosa", "loan", "other")
    TYPE_LABELS = {
        "deposit": "Savings deposit",
        "withdrawal": "Savings withdrawal",
        "repayment": "Loan repayment",
        "loan": "Loan disbursement",
        "dividend": "Dividend credit",
        "adjustment": "Linked account reversal",
    }
    for account_type in ACCOUNT_ORDER:
        label = account_labels[account_type]
        entries = period_by_account[account_type]
        history = posted_by_account[account_type]
        story.append(Paragraph(label, ps(f"account_{account_type}", fontSize=10.5, textColor=C_INDIGO,
            fontName="Helvetica-Bold", leading=13, spaceBefore=5, spaceAfter=2)))

        if not history:
            story.append(Paragraph(
                "No account-linked posted entries are available to calculate this account's balance.",
                ps(f"no_history_{account_type}", fontSize=8.5, textColor=C_MUTED, fontName="Helvetica", leading=12),
            ))
            story.append(Spacer(1, 0.2 * cm))
            continue

        opening_balance = opening_by_account[account_type]
        running_balance = opening_balance
        story.append(Paragraph(
            f"Opening balance before period: KES {opening_balance:,.2f}",
            ps(f"opening_{account_type}", fontSize=8.5, textColor=C_NAVY, fontName="Helvetica", leading=12, spaceAfter=4),
        ))
        if not entries:
            story.append(Paragraph(
                f"No posted entries in this period. Closing balance: KES {opening_balance:,.2f}.",
                ps(f"no_entries_{account_type}", fontSize=8.5, textColor=C_MUTED, fontName="Helvetica", leading=12),
            ))
            story.append(Spacer(1, 0.2 * cm))
            continue

        headers = [
            Paragraph("Activity and notes", ps(f"h_activity_{account_type}", fontSize=7.5, textColor=C_WHITE,
                fontName="Helvetica-Bold", leading=9)),
            Paragraph("Reference", ps(f"h_ref_{account_type}", fontSize=7.5, textColor=C_WHITE,
                fontName="Helvetica-Bold", leading=9)),
            Paragraph("Date", ps(f"h_date_{account_type}", fontSize=7.5, textColor=C_WHITE,
                fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
            Paragraph("Increase", ps(f"h_in_{account_type}", fontSize=7.5, textColor=C_WHITE,
                fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
            Paragraph("Decrease", ps(f"h_out_{account_type}", fontSize=7.5, textColor=C_WHITE,
                fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
            Paragraph("Balance", ps(f"h_bal_{account_type}", fontSize=7.5, textColor=C_WHITE,
                fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
        ]
        rows = [headers]
        row_styles = []
        increase_total = Decimal("0.00")
        decrease_total = Decimal("0.00")
        for row_number, entry in enumerate(entries, 1):
            movement = entry_effect(entry)
            if movement is None:
                continue
            running_balance += movement
            if movement >= 0:
                increase_total += movement
                increase_text, decrease_text = f"{movement:,.2f}", ""
            else:
                decrease_total += abs(movement)
                increase_text, decrease_text = "", f"{abs(movement):,.2f}"

            detail = TYPE_LABELS.get(entry.type, entry.type.replace("_", " ").title())
            note = xml_escape((entry.note or "").strip())
            if entry.type == "adjustment" and entry.reverses_id:
                detail = f"Reversal of TX{entry.reverses_id:08d}"
            if note:
                detail += f"<br/><font color='#52617E'>{note}</font>"

            reference = f"TX{entry.pk:08d}"
            if entry.type == "withdrawal":
                payout = payout_by_transaction.get(entry.pk)
                if payout:
                    reference = str(payout.provider_transaction_id or payout.provider_reference or payout.reference)
            else:
                payment = getattr(entry, "mpesa_payment", None)
                if payment:
                    reference = payment.mpesa_receipt or payment.checkout_request_id or reference

            rows.append([
                Paragraph(detail, ps(f"activity_{account_type}_{entry.pk}", fontSize=7.5, textColor=C_NAVY,
                    fontName="Helvetica", leading=9.5, splitLongWords=1)),
                Paragraph(xml_escape(str(reference)), ps(f"reference_{account_type}_{entry.pk}", fontSize=7,
                    textColor=C_MUTED, fontName="Helvetica", leading=9, splitLongWords=1)),
                Paragraph(timezone.localtime(entry.created_at).strftime("%d/%m/%Y"), CELL_MUTED_R),
                Paragraph(increase_text, ps(f"increase_{account_type}_{entry.pk}", fontSize=7.5,
                    textColor=C_EMERALD, fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
                Paragraph(decrease_text, ps(f"decrease_{account_type}_{entry.pk}", fontSize=7.5,
                    textColor=C_NAVY, fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
                Paragraph(f"{running_balance:,.2f}", CELL_BALANCE),
            ])
            row_styles.append(("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1),
                C_WHITE if row_number % 2 else C_BG_ROW))

        rows.append([
            Paragraph("Period totals", ps(f"total_{account_type}", fontSize=8, textColor=C_NAVY,
                fontName="Helvetica-Bold", leading=10)),
            Paragraph("", CELL_NORMAL), Paragraph("", CELL_NORMAL),
            Paragraph(f"{increase_total:,.2f}", CELL_CREDIT),
            Paragraph(f"{decrease_total:,.2f}", ps(f"total_decrease_{account_type}", fontSize=8,
                textColor=C_NAVY, fontName="Helvetica-Bold", leading=10, alignment=TA_RIGHT)),
            Paragraph(f"{running_balance:,.2f}", CELL_BALANCE),
        ])
        total_row = len(rows) - 1
        table = LongTable(rows, colWidths=[
            USABLE_W * .34, USABLE_W * .18, USABLE_W * .11,
            USABLE_W * .12, USABLE_W * .12, USABLE_W * .13,
        ], repeatRows=1, splitByRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            ("TOPPADDING", (0, 1), (-1, -2), 5),
            ("BOTTOMPADDING", (0, 1), (-1, -2), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), .25, C_BORDER),
            ("LINEBELOW", (0, 0), (-1, 0), .8, C_BORDER),
            ("BACKGROUND", (0, total_row), (-1, total_row), C_BG_SOFT),
            ("LINEABOVE", (0, total_row), (-1, total_row), 1, C_INDIGO),
            ("TOPPADDING", (0, total_row), (-1, total_row), 6),
            ("BOTTOMPADDING", (0, total_row), (-1, total_row), 6),
        ] + row_styles))
        story.append(table)
        story.append(Paragraph(
            f"Closing balance for period: KES {running_balance:,.2f}",
            ps(f"closing_{account_type}", fontSize=8.5, textColor=C_NAVY, fontName="Helvetica-Bold",
                leading=12, spaceBefore=4, spaceAfter=7),
        ))

    review_entries = [entry for entry in unclassified_or_review if entry.pk not in payout_by_transaction]
    pending_rows = []
    for entry in review_entries:
        if entry.type == "loan" and "application" in (entry.note or "").lower():
            state = "Application only — not disbursed"
        elif entry.type == "withdrawal":
            state = "Needs payout review"
        elif not entry.account_type:
            state = "Account type unavailable"
        else:
            state = "Not included in posted balances"
        pending_rows.append({
            "date": entry.created_at,
            "kind": TYPE_LABELS.get(entry.type, entry.type.replace("_", " ").title()),
            "reference": f"TX{entry.pk:08d}",
            "amount": abs(entry.amount),
            "state": state,
            "note": entry.note,
        })
    for payout in payout_requests:
        state = "Needs payout review" if payout.status == "succeeded" else payout.get_status_display()
        pending_rows.append({
            "date": payout.created_at,
            "kind": "FOSA withdrawal",
            "reference": str(payout.provider_reference or payout.reference),
            "amount": payout.amount,
            "state": state,
            "note": payout.ledger_transaction.note if payout.ledger_transaction_id else "Provider-confirmed settlement is not recorded.",
        })
    for payment in unsettled_payments:
        pending_rows.append({
            "date": payment.created_at,
            "kind": "M-Pesa " + ("deposit" if payment.payment_type == "deposit" else "loan repayment"),
            "reference": payment.checkout_request_id,
            "amount": payment.amount,
            "state": "Pending provider confirmation",
            "note": "This request is not a settled account entry.",
        })

    story.append(Paragraph("Pending and review items", ps("pendingTitle", fontSize=12, textColor=C_NAVY,
        fontName="Helvetica-Bold", leading=15, spaceBefore=8, spaceAfter=3)))
    story.append(Paragraph(
        "These items are not included in the posted account balances.",
        ps("pendingIntro", fontSize=8.5, textColor=C_MUTED, fontName="Helvetica", leading=12, spaceAfter=6),
    ))
    if pending_rows:
        pending_table_rows = [[
            Paragraph("Activity", ps("pending_h_activity", fontSize=7.5, textColor=C_WHITE, fontName="Helvetica-Bold", leading=9)),
            Paragraph("Reference", ps("pending_h_ref", fontSize=7.5, textColor=C_WHITE, fontName="Helvetica-Bold", leading=9)),
            Paragraph("Date", ps("pending_h_date", fontSize=7.5, textColor=C_WHITE, fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
            Paragraph("Amount (KES)", ps("pending_h_amount", fontSize=7.5, textColor=C_WHITE, fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
            Paragraph("Status and note", ps("pending_h_state", fontSize=7.5, textColor=C_WHITE, fontName="Helvetica-Bold", leading=9)),
        ]]
        for index, item in enumerate(sorted(pending_rows, key=lambda value: (value["date"], value["reference"]))):
            description = item["kind"]
            if item["note"]:
                description += "<br/><font color='#52617E'>" + xml_escape(str(item["note"])) + "</font>"
            pending_table_rows.append([
                Paragraph(description, ps(f"pending_activity_{index}", fontSize=7.5, textColor=C_NAVY, fontName="Helvetica", leading=9.5, splitLongWords=1)),
                Paragraph(xml_escape(str(item["reference"])), ps(f"pending_ref_{index}", fontSize=7, textColor=C_MUTED, fontName="Helvetica", leading=9, splitLongWords=1)),
                Paragraph(timezone.localtime(item["date"]).strftime("%d/%m/%Y"), CELL_MUTED_R),
                Paragraph(f"{item['amount']:,.2f}", ps(f"pending_amt_{index}", fontSize=7.5, textColor=C_NAVY, fontName="Helvetica-Bold", leading=9, alignment=TA_RIGHT)),
                Paragraph(xml_escape(str(item["state"])), ps(f"pending_state_{index}", fontSize=7.5, textColor=C_NAVY, fontName="Helvetica", leading=9.5, splitLongWords=1)),
            ])
        pending_table = LongTable(pending_table_rows, colWidths=[
            USABLE_W * .23, USABLE_W * .22, USABLE_W * .12, USABLE_W * .15, USABLE_W * .27,
        ], repeatRows=1, splitByRow=1)
        pending_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
            ("GRID", (0, 0), (-1, -1), .25, C_BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_BG_ROW]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(pending_table)
    else:
        story.append(Paragraph(
            "There are no pending or review items in this statement period.",
            ps("noPending", fontSize=8.5, textColor=C_MUTED, fontName="Helvetica-Oblique", leading=12),
        ))
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
        f"Printed: {now.strftime('%d/%m/%Y  %H:%M')}",
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
        canvas_obj.setFillColor(C_MUTED)
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(L_MARGIN, 0.8 * cm, "Nairobi West Transport Cooperative Society")
        canvas_obj.drawRightString(PAGE_W - R_MARGIN, 0.8 * cm, f"Page {canvas_obj.getPageNumber()}")
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
@permission_classes([IsAuthenticated])
def admin_reports(request):
    from accounts.access import has_sacco_permission
    if not has_sacco_permission(request.user, "reports.financial.read"):
        return Response({"detail": "Financial report permission required."}, status=403)
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
@permission_classes([IsAuthenticated])
def admin_crb_checks(request):
    """List bureau records only for loans assigned to this officer."""
    from .models import CRBCheck
    from accounts.access import has_sacco_permission, active_staff_duties
    if not has_sacco_permission(request.user, "loans.appraise_assigned"):
        return Response({"detail": "Assigned credit appraisal permission required."}, status=403)
    try:
        loan_ids = active_staff_duties(request.user, "loan_appraisal").values_list("loan_id", flat=True)
        qs = CRBCheck.objects.select_related("loan", "member").filter(loan_id__in=loan_ids).order_by("-checked_at")
    except (OperationalError, ProgrammingError):
        return Response({"detail": "Assigned loan review records are unavailable until the staff-access migration is applied."}, status=503)
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
@permission_classes([IsAuthenticated])
def admin_crb_check_detail(request, check_id):
    """Retrieve safe report fields for a specifically assigned loan."""
    from .models import CRBCheck
    from accounts.access import has_sacco_permission, active_staff_duties
    from django.shortcuts import get_object_or_404
    c = get_object_or_404(CRBCheck, pk=check_id)
    if not has_sacco_permission(request.user, "loans.appraise_assigned"):
        return Response({"detail": "Assigned credit appraisal permission required."}, status=403)
    try:
        if not active_staff_duties(request.user, "loan_appraisal").filter(loan_id=c.loan_id).exists():
            return Response({"detail": "This report is not linked to a loan assigned to your account."}, status=403)
    except (OperationalError, ProgrammingError):
        return Response({"detail": "Assigned loan review records are unavailable until the staff-access migration is applied."}, status=503)
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
        "request_reference": c.request_reference,
        "report_date": c.report_date,
        "expires_at": c.expires_at,
        "external_obligations": c.external_obligations,
        "repayment_default_information": c.repayment_default_information,
        "missing_data": c.missing_data,
        "coverage_limitations": c.coverage_limitations,
        "checked_at":        c.checked_at,
        "override_by":       c.override_by.username if c.override_by else None,
        "override_at":       c.override_at,
        "override_notes":    c.override_notes,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_loan_guarantors(request, loan_id):
    """Read guarantor review details only for a currently assigned appraisal."""
    from .models import LoanGuarantor
    from accounts.access import has_sacco_permission, active_staff_duties
    if not has_sacco_permission(request.user, "loans.guarantors.read_assigned"):
        return Response({"detail": "Assigned guarantor review permission required."}, status=403)
    try:
        if not active_staff_duties(request.user, "loan_appraisal").filter(loan_id=loan_id).exists():
            return Response({"detail": "This loan is not assigned for appraisal to your account."}, status=403)
    except (OperationalError, ProgrammingError):
        return Response({"detail": "Assigned loan review records are unavailable until the staff-access migration is applied."}, status=503)
    if not Loan.objects.filter(pk=loan_id).exists():
        return Response({"detail": "Loan not found."}, status=404)
    return Response([{
        "id": row.pk,
        "guarantor_name": row.guarantor.get_full_name() or row.guarantor.username,
        "member_number": getattr(getattr(row.guarantor, "member_profile", None), "member_number", ""),
        "status": row.status,
        "message": row.message,
        "responded_at": row.responded_at,
    } for row in LoanGuarantor.objects.filter(loan_id=loan_id).select_related("guarantor").order_by("created_at")])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_crb_override(request, check_id):
    """Keep the legacy URL but never turn a CRB result into a loan decision."""
    from .models import CRBCheck
    from accounts.access import has_sacco_permission, active_staff_duties
    if not has_sacco_permission(request.user, "loans.appraise_assigned"):
        return Response({"detail": "Assigned credit appraisal permission required."}, status=403)
    c = CRBCheck.objects.filter(pk=check_id).first()
    if not c:
        return Response({"detail": "Credit report not found."}, status=404)
    try:
        if not active_staff_duties(request.user, "loan_appraisal").filter(loan_id=c.loan_id).exists():
            return Response({"detail": "This report is not linked to a loan assigned to your account."}, status=403)
    except (OperationalError, ProgrammingError):
        return Response({"detail": "Assigned loan review records are unavailable until the staff-access migration is applied."}, status=503)
    return Response({
        "code": "separate_loan_decision_required",
        "detail": "A credit report review cannot approve or disburse a loan. Use the separately assigned loan decision workflow.",
    }, status=409)



# ─────────────────────────────────────────────────────────────────────────────
# ⚠️  Arrears report (Credit officer / authorised staff)
# ─────────────────────────────────────────────────────────────────────────────
def _loan_repayment_transactions(loan):
    return Transaction.objects.filter(
        user=loan.user_id, type="repayment", reversal_entry__isnull=True,
    ).filter(
        Q(mpesa_payment__loan=loan)
        | (Q(mpesa_payment__loan__isnull=True) & Q(note__iregex=rf"Loan #{loan.pk}([^0-9]|$)")),
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_arrears(request):
    """Return overdue instalment analysis for active loans.

    Access: credit officer with loan_appraisal duty, treasurer, or superadmin.
    The overdue calculation mirrors repayment_schedule: flat-rate interest,
    equal monthly instalments, due dates offset from approved_at.
    """
    from accounts.access import active_staff_duties, is_staff_manager, staff_roles_for_user
    roles = staff_roles_for_user(request.user)
    is_manager = is_staff_manager(request.user)
    is_credit = "credit_officer" in roles
    is_treasurer = "treasurer" in roles
    if not is_manager and not is_credit and not is_treasurer:
        return Response({"detail": "Credit officer or treasury permission is required."}, status=403)

    today = timezone.localdate()

    # Build per-loan overdue summary for every active (approved) loan that
    # has at least one instalment whose due date is strictly before today
    # and whose cumulative payments fall short.
    approved_loans = (
        Loan.objects.filter(status="approved", approved_at__isnull=False, repayment_months__gt=0)
        .select_related("user", "user__member_profile")
        .order_by("approved_at")
    )
    if not (is_manager or is_treasurer):
        loan_ids = active_staff_duties(request.user, "loan_appraisal").values_list("loan_id", flat=True)
        approved_loans = approved_loans.filter(pk__in=loan_ids)

    delinquent = []

    for loan in approved_loans:
        terms = calculate_flat_term(loan.amount, loan.repayment_months, loan.interest)
        paid_total = _loan_repayment_transactions(loan).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        approval_date = timezone.localdate(loan.approved_at)

        overdue_installments = 0
        overdue_amount = Decimal("0.00")
        oldest_overdue_days = 0
        for row in terms["schedule"]:
            due = approval_date + relativedelta(months=row["month"])
            if due >= today:
                break
            # expected paid by this due date
            expected_by_now = terms["total_repayment"] - row["remaining"]
            shortfall = expected_by_now - paid_total
            if shortfall > Decimal("0.00"):
                overdue_installments += 1
                overdue_amount = shortfall
                oldest_overdue_days = max(oldest_overdue_days, (today - due).days)

        if overdue_installments == 0:
            continue

        member = getattr(loan.user, "member_profile", None)
        member_number = getattr(member, "member_number", "—")
        phone = getattr(member, "phone_number", "") if member else ""

        if oldest_overdue_days <= 30:
            bucket = "1-30 days"
        elif oldest_overdue_days <= 60:
            bucket = "31-60 days"
        elif oldest_overdue_days <= 90:
            bucket = "61-90 days"
        else:
            bucket = "90+ days"

        delinquent.append({
            "loan_id": loan.id,
            "member": loan.user.get_full_name() or loan.user.username,
            "member_number": member_number,
            "phone": phone,
            "loan_amount": float(loan.amount),
            "outstanding_balance": float(loan.balance),
            "overdue_amount": float(overdue_amount),
            "overdue_installments": overdue_installments,
            "oldest_overdue_days": oldest_overdue_days,
            "bucket": bucket,
        })

    # Sort: most severe (oldest) first
    delinquent.sort(key=lambda x: -x["oldest_overdue_days"])

    buckets: dict[str, dict] = {}
    for entry in delinquent:
        b = entry["bucket"]
        if b not in buckets:
            buckets[b] = {"count": 0, "total_overdue": Decimal("0.00")}
        buckets[b]["count"] += 1
        buckets[b]["total_overdue"] += Decimal(str(entry["overdue_amount"]))

    return Response({
        "total_delinquent_loans": len(delinquent),
        "total_overdue_amount": float(sum(Decimal(str(e["overdue_amount"])) for e in delinquent)),
        "buckets": {k: {"count": v["count"], "total_overdue": float(v["total_overdue"])} for k, v in buckets.items()},
        "loans": delinquent,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 📊  Chairman cooperative summary  (GET admin/chairman/summary/)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chairman_summary(request):
    """Cooperative financial overview for the chairman workspace.

    Returns aggregate figures, monthly confirmed-remittance trend, and
    pending workflow counts. No individual member identity is exposed.
    """
    from accounts.access import active_staff_duties, has_sacco_permission, is_staff_manager
    is_manager = is_staff_manager(request.user)
    if not is_manager and not has_sacco_permission(request.user, "operations.summary.read"):
        return Response({"detail": "Chairman or system-manager access is required."}, status=403)

    from members.models import Member
    from core.transport_models import Vehicle, TransportPayment

    today = timezone.localdate()
    this_month = today.replace(day=1)
    first_month = this_month - relativedelta(months=5)
    window_start = timezone.make_aware(datetime.combine(first_month, time.min))
    as_of = timezone.now()
    monthly_receipts = (
        TransportPayment.objects.filter(
            remittance__isnull=False, confirmed_at__range=(window_start, as_of),
            received_amount__isnull=False,
        )
        .annotate(month=TruncMonth("confirmed_at"))
        .values("month")
        .annotate(total=Sum("received_amount"))
        .order_by()
    )
    totals = {row["month"].date(): row["total"] for row in monthly_receipts}
    monthly_collections = [
        {"month": month.strftime("%b"), "total": float(totals.get(month, 0))}
        for month in (first_month + relativedelta(months=offset) for offset in range(6))
    ]

    # Totals
    total_savings = Savings.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    active_loan_balance = (
        Loan.objects.filter(status="approved").aggregate(total=Sum("balance"))["total"] or Decimal("0.00")
    )
    pending_loan_reviews = Loan.objects.filter(status="pending")
    if not is_manager:
        loan_ids = active_staff_duties(request.user, "loan_approval").values_list("loan_id", flat=True)
        pending_loan_reviews = pending_loan_reviews.filter(pk__in=loan_ids)

    return Response({
        "confirmed_remittances_this_month": float(totals.get(this_month, 0)),
        "savings_liabilities": float(total_savings),
        "loan_balance_outstanding": float(active_loan_balance),
        "registered_vehicles": Vehicle.objects.count(),
        "total_members": Member.objects.count(),
        "pending_loan_reviews": pending_loan_reviews.count(),
        "monthly_remittances": monthly_collections,
        "upcoming_meetings": _chairman_upcoming_meetings(),
        "welfare_submitted": _chairman_welfare_submitted(),
        "welfare_pending_payout": _chairman_welfare_pending_payout(),
    })


def _chairman_upcoming_meetings():
    from accounts.models import CooperativeMeeting
    rows = CooperativeMeeting.objects.filter(
        status="scheduled", scheduled_at__gte=timezone.now()
    ).order_by("scheduled_at")[:5]
    return [
        {"id": m.id, "title": m.title, "meeting_type": m.get_meeting_type_display(),
         "scheduled_at": m.scheduled_at.isoformat()}
        for m in rows
    ]


def _chairman_welfare_submitted():
    from accounts.welfare_models import WelfareRequest
    return WelfareRequest.objects.filter(status="submitted").count()


def _chairman_welfare_pending_payout():
    from accounts.welfare_models import WelfarePayout
    return WelfarePayout.objects.filter(status__in=("awaiting_provider", "pending")).count()


# ─────────────────────────────────────────────────────────────────────────────
# Item 3: Credit officer loan appraisal write-back
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def loan_appraise(request, loan_id):
    """Record a credit officer appraisal for an assigned loan."""
    from accounts.access import has_sacco_permission, active_staff_duties
    from accounts.models import AuditLog
    if not has_sacco_permission(request.user, "loans.appraise_assigned"):
        return Response({"detail": "Assigned credit appraisal permission required."}, status=403)
    try:
        if not active_staff_duties(request.user, "loan_appraisal").filter(loan_id=loan_id).exists():
            return Response({"detail": "This loan is not assigned for appraisal to your account."}, status=403)
    except (OperationalError, ProgrammingError):
        return Response({"detail": "Assigned loan review records are unavailable until the staff-access migration is applied."}, status=503)
    loan = Loan.objects.filter(pk=loan_id).first()
    if not loan:
        return Response({"detail": "Loan not found."}, status=404)

    VALID_OUTCOMES = {
        "submitted_for_review", "recommend_approve",
        "recommend_reject", "needs_more_information",
    }
    outcome = str(request.data.get("outcome", "")).strip()
    if outcome not in VALID_OUTCOMES:
        return Response({"detail": "Outcome must be submitted_for_review, recommend_approve, recommend_reject, or needs_more_information."}, status=400)
    reasons = request.data.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    inputs = request.data.get("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}
    decision_reason = str(request.data.get("decision_reason", "")).strip()

    # Find active policy if any
    policy = None
    policy_version = ""
    try:
        from .models import LoanAssessmentPolicy
        policy = LoanAssessmentPolicy.objects.filter(active=True).first()
        if policy:
            policy_version = str(getattr(policy, "version", ""))
    except Exception:
        pass

    assessment = LoanAssessment.objects.create(
        loan=loan,
        policy=policy,
        policy_version=policy_version,
        inputs=inputs,
        reasons=reasons,
        outcome=outcome,
        decision_maker=request.user,
        decision_at=timezone.now(),
        decision_reason=decision_reason,
    )
    AuditLog.log(request.user, "other", f"Loan #{loan_id} appraisal #{assessment.pk}", {
        "operation": "loan_appraisal_recorded", "outcome": outcome,
    }, request)
    return Response({
        "id": assessment.pk,
        "loan_id": loan_id,
        "outcome": assessment.outcome,
        "decision_reason": assessment.decision_reason,
        "reasons": assessment.reasons,
        "inputs": assessment.inputs,
        "policy_version": assessment.policy_version,
        "created_at": assessment.created_at,
    }, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def loan_assessments(request, loan_id):
    """List appraisal records for an assigned loan."""
    from accounts.access import has_sacco_permission, active_staff_duties
    can_appraise = has_sacco_permission(request.user, "loans.appraise_assigned")
    can_decide = has_sacco_permission(request.user, "loans.approve_assigned")
    if not can_appraise and not can_decide:
        return Response({"detail": "Assigned credit appraisal or approval permission required."}, status=403)
    try:
        if can_appraise and not active_staff_duties(request.user, "loan_appraisal").filter(loan_id=loan_id).exists():
            if not can_decide:
                return Response({"detail": "This loan is not assigned to your account."}, status=403)
    except (OperationalError, ProgrammingError):
        return Response({"detail": "Assigned loan review records are unavailable until the staff-access migration is applied."}, status=503)
    if not Loan.objects.filter(pk=loan_id).exists():
        return Response({"detail": "Loan not found."}, status=404)
    assessments = LoanAssessment.objects.filter(loan_id=loan_id).select_related("decision_maker").order_by("-created_at")[:50]
    return Response([{
        "id": a.pk,
        "outcome": a.outcome,
        "decision_reason": a.decision_reason,
        "reasons": a.reasons,
        "inputs": a.inputs,
        "policy_version": a.policy_version,
        "decision_maker": (a.decision_maker.get_full_name() or a.decision_maker.username) if a.decision_maker else None,
        "created_at": a.created_at,
    } for a in assessments])
