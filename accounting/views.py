from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import CharField, Count, Exists, OuterRef, Sum
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from members.models import Member
from core.models import Savings, Transaction
from accounts.models import AuditLog
from .models import JournalEntry, JournalLine, LedgerAccount, ShareCapitalMovement, ShareCapitalPolicy
from .permissions import CanReadAccounting, IsActiveAccountant, IsAccountingSuperAdmin, can_read_accounting
from .services import (
    AccountingConflict,
    AccountingPermissionDenied,
    InvalidJournal,
    approve_share_capital_policy,
    create_share_capital_policy,
    is_accounting_superadmin,
    post_journal_entry,
    record_share_capital_movement,
    reverse_journal_entry,
    _authorized_accountant,
)


def _parse_date(value, field):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from None


def _error_response(exc):
    if isinstance(exc, AccountingPermissionDenied):
        return Response({"error": str(exc)}, status=403)
    if isinstance(exc, AccountingConflict):
        return Response({"error": str(exc)}, status=409)
    if isinstance(exc, (InvalidJournal, ValueError)):
        return Response({"error": str(exc)}, status=400)
    raise exc


def _account_response(account):
    return {
        "id": account.pk,
        "code": account.code,
        "name": account.name,
        "classification": account.classification,
        "normal_balance": account.normal_balance,
        "currency": account.currency,
        "system_key": account.system_key,
        "active": account.active,
        "permits_posting": account.permits_posting,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ledger_accounts(request):
    if request.method == "GET":
        if not can_read_accounting(request.user):
            return Response({"error": "Accounting read access is required."}, status=403)
        rows = LedgerAccount.objects.order_by("currency", "code")
        return Response({"results": [_account_response(row) for row in rows]})

    if not is_accounting_superadmin(request.user):
        return Response({"error": "An active superadministrator is required to configure the chart of accounts."}, status=403)
    data = request.data
    required = ("code", "name", "classification", "normal_balance")
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return Response({"error": "Required fields are missing.", "fields": missing}, status=400)
    account = LedgerAccount(
        code=str(data.get("code", "")).strip(),
        name=str(data.get("name", "")).strip(),
        classification=str(data.get("classification", "")).strip(),
        normal_balance=str(data.get("normal_balance", "")).strip(),
        currency=str(data.get("currency", "KES")).strip().upper(),
        system_key=str(data.get("system_key", "")).strip() or None,
    )
    try:
        with transaction.atomic():
            account.full_clean()
            account.save()
            AuditLog.log(
                request.user, "other", target=f"Ledger account {account.code}",
                details={"event": "ledger_account_created", "classification": account.classification,
                         "currency": account.currency, "system_key": account.system_key},
            )
    except ValidationError as exc:
        return Response({"error": "The account definition is invalid.", "fields": getattr(exc, "message_dict", {"error": exc.messages})}, status=400)
    except IntegrityError:
        return Response({"error": "The account code or system key already exists."}, status=409)
    return Response(_account_response(account), status=201)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_ledger_account(request, account_id):
    if not is_accounting_superadmin(request.user):
        return Response({"error": "An active superadministrator is required to configure the chart of accounts."}, status=403)
    allowed = {"name", "active", "permits_posting"}
    unknown = sorted(set(request.data.keys()) - allowed)
    if unknown:
        return Response({"error": "Only account name and posting status can be changed here.", "fields": unknown}, status=400)
    try:
        account = LedgerAccount.objects.get(pk=account_id)
    except LedgerAccount.DoesNotExist:
        return Response({"error": "Ledger account not found."}, status=404)
    changed_fields = []
    if "name" in request.data:
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response({"error": "Account name cannot be empty."}, status=400)
        account.name = name
        changed_fields.append("name")
    for field in ("active", "permits_posting"):
        if field in request.data:
            if not isinstance(request.data[field], bool):
                return Response({"error": f"{field} must be true or false."}, status=400)
            setattr(account, field, request.data[field])
            changed_fields.append(field)
    try:
        with transaction.atomic():
            account.full_clean()
            account.save()
            if changed_fields:
                AuditLog.log(
                    request.user, "other", target=f"Ledger account {account.code}",
                    details={"event": "ledger_account_updated", "changed_fields": changed_fields,
                             "active": account.active, "permits_posting": account.permits_posting},
                )
    except ValidationError as exc:
        return Response({"error": "The account update is invalid.", "fields": getattr(exc, "message_dict", {"error": exc.messages})}, status=400)
    return Response(_account_response(account))


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanReadAccounting])
def trial_balance(request):
    try:
        as_of = _parse_date(request.query_params.get("as_of"), "as_of") or timezone.localdate()
    except ValueError as exc:
        return _error_response(exc)

    posted_lines = JournalLine.objects.filter(
        entry__status="posted", entry__posted_at__isnull=False,
        entry__posted_at__date__lte=as_of,
    )
    totals = {
        (row["account_id"], row["entry__currency"]): row
        for row in posted_lines.values("account_id", "entry__currency").annotate(
            debits=Sum("debit"), credits=Sum("credit")
        )
    }
    currency_totals = {}
    rows = []
    for account in LedgerAccount.objects.order_by("currency", "code"):
        totals_row = totals.get((account.pk, account.currency), {})
        debits = totals_row.get("debits") or Decimal("0.00")
        credits = totals_row.get("credits") or Decimal("0.00")
        net = debits - credits
        debit_balance = max(net, Decimal("0.00"))
        credit_balance = max(-net, Decimal("0.00"))
        rows.append({
            "account": _account_response(account),
            "posted_debits": format(debits, ".2f"),
            "posted_credits": format(credits, ".2f"),
            "debit_balance": format(debit_balance, ".2f"),
            "credit_balance": format(credit_balance, ".2f"),
            "balance_side": "debit" if debit_balance else "credit" if credit_balance else "zero",
        })
        currency = currency_totals.setdefault(account.currency, {"debits": Decimal("0.00"), "credits": Decimal("0.00")})
        currency["debits"] += debit_balance
        currency["credits"] += credit_balance
    by_currency = {
        code: {
            "debit_balances": format(value["debits"], ".2f"),
            "credit_balances": format(value["credits"], ".2f"),
            "balanced": value["debits"] == value["credits"],
        }
        for code, value in sorted(currency_totals.items())
    }
    return Response({"as_of": as_of.isoformat(), "by_currency": by_currency, "results": rows})


class JournalEntryPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanReadAccounting])
def journal_entries(request):
    try:
        start_date = _parse_date(request.query_params.get("from"), "from")
        end_date = _parse_date(request.query_params.get("to"), "to")
    except ValueError as exc:
        return _error_response(exc)
    if start_date and end_date and start_date > end_date:
        return Response({"error": "The from date must not be after the to date."}, status=400)
    entries = JournalEntry.objects.filter(status="posted").select_related(
        "reverses", "adjusts", "audit_log", "posted_by"
    ).prefetch_related("lines__account")
    if start_date:
        entries = entries.filter(posted_at__date__gte=start_date)
    if end_date:
        entries = entries.filter(posted_at__date__lte=end_date)
    source_type = str(request.query_params.get("source_type", "")).strip()
    if source_type:
        if len(source_type) > 48:
            return Response({"error": "source_type is too long."}, status=400)
        entries = entries.filter(source_type=source_type)
    paginator = JournalEntryPagination()
    page = paginator.paginate_queryset(entries.order_by("-posted_at", "-id"), request)
    return paginator.get_paginated_response([_entry_response(entry) for entry in page])


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanReadAccounting])
def journal_entry_detail(request, entry_id):
    try:
        entry = JournalEntry.objects.filter(status="posted").prefetch_related("lines__account").get(pk=entry_id)
    except JournalEntry.DoesNotExist:
        return Response({"error": "Posted journal entry not found."}, status=404)
    return Response(_entry_response(entry))


@api_view(["GET"])
@permission_classes([IsAuthenticated, CanReadAccounting])
def legacy_reconciliation_report(request):
    """Read-only inventory of legacy records without a posted journal link.

    This deliberately does not pair Savings and Transaction rows by amount,
    timestamp, or member because the legacy schema has no authoritative link.
    """
    try:
        start_date = _parse_date(request.query_params.get("from"), "from")
        end_date = _parse_date(request.query_params.get("to"), "to")
    except ValueError as exc:
        return _error_response(exc)
    if start_date and end_date and start_date > end_date:
        return Response({"error": "The from date must not be after the to date."}, status=400)

    transactions = Transaction.objects.all()
    savings = Savings.objects.all()
    if start_date:
        transactions = transactions.filter(created_at__date__gte=start_date)
        savings = savings.filter(created_at__date__gte=start_date)
    if end_date:
        transactions = transactions.filter(created_at__date__lte=end_date)
        savings = savings.filter(created_at__date__lte=end_date)

    legacy_journals = JournalEntry.objects.filter(
        status="posted",
        source_type="legacy_transaction",
        source_reference=Cast(OuterRef("pk"), output_field=CharField()),
    )
    unjournaled = transactions.annotate(has_journal=Exists(legacy_journals)).filter(has_journal=False)
    transaction_count = transactions.count()
    transaction_sum = transactions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    unjournaled_count = unjournaled.count()
    unjournaled_sum = unjournaled.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    unjournaled_rows = list(unjournaled.order_by("id").values(
        "id", "type", "account_type", "amount", "created_at"
    )[:200])
    savings_sum = savings.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    by_type = transactions.values("type", "account_type").annotate(
        count=Count("id"), amount=Sum("amount")
    ).order_by("type", "account_type")

    posted_entries = JournalEntry.objects.filter(status="posted")
    posted_lines = JournalLine.objects.filter(entry__in=posted_entries)
    debit_total = posted_lines.aggregate(total=Sum("debit"))["total"] or Decimal("0.00")
    credit_total = posted_lines.aggregate(total=Sum("credit"))["total"] or Decimal("0.00")

    return Response({
        "report_type": "legacy_double_entry_reconciliation_inventory",
        "period": {"from": start_date.isoformat() if start_date else None,
                   "to": end_date.isoformat() if end_date else None},
        "matching_policy": "No inferred matching; legacy rows lack authoritative cross-ledger IDs.",
        "automatic_balancing_created": False,
        "transactions": {
            "count": transaction_count,
            "amount_sum": format(transaction_sum, ".2f"),
            "unjournaled_count": unjournaled_count,
            "unjournaled_amount_sum": format(unjournaled_sum, ".2f"),
            "by_type": [
                {"type": row["type"], "account_type": row["account_type"],
                 "count": row["count"], "amount_sum": format(row["amount"] or 0, ".2f")}
                for row in by_type
            ],
            "unjournaled_records": [
                {"transaction_id": row["id"], "type": row["type"],
                 "account_type": row["account_type"], "amount": format(row["amount"], ".2f"),
                 "created_at": timezone.localtime(row["created_at"]).isoformat(),
                 "status": "not_imported_to_double_entry"}
                for row in unjournaled_rows
            ],
            "records_truncated": unjournaled_count > 200,
        },
        "savings_records": {
            "count": savings.count(),
            "amount_sum": format(savings_sum, ".2f"),
            "paired_to_transactions": False,
        },
        "journal": {
            "posted_entries": posted_entries.count(),
            "debit_sum": format(debit_total, ".2f"),
            "credit_sum": format(credit_total, ".2f"),
            "balanced": debit_total == credit_total,
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsActiveAccountant])
def post_staff_adjustment(request):
    data = request.data
    if data.get("source_type") != "staff_adjustment":
        return Response({"error": "Staff API postings must be classified as staff_adjustment."}, status=400)
    try:
        adjusts = None
        if data.get("adjusts"):
            adjusts = JournalEntry.objects.get(pk=data["adjusts"], status="posted")
        entry = post_journal_entry(
            idempotency_key=data.get("idempotency_key"),
            source_type="staff_adjustment",
            source_reference=data.get("source_reference"),
            description=data.get("description"),
            reason=data.get("reason"),
            currency=data.get("currency", "KES"),
            lines=data.get("lines"),
            actor=request.user,
            adjusts=adjusts,
        )
    except JournalEntry.DoesNotExist:
        return Response({"error": "The journal entry to adjust was not found or is not posted."}, status=404)
    except (AccountingConflict, AccountingPermissionDenied, InvalidJournal) as exc:
        return _error_response(exc)
    return Response(_entry_response(entry), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsActiveAccountant])
def reverse_staff_entry(request, entry_id):
    try:
        entry = reverse_journal_entry(
            entry_id=entry_id,
            idempotency_key=request.data.get("idempotency_key"),
            reason=request.data.get("reason"),
            actor=request.user,
        )
    except (AccountingConflict, AccountingPermissionDenied, InvalidJournal) as exc:
        return _error_response(exc)
    return Response(_entry_response(entry), status=201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def share_capital_movements(request):
    if request.method == "GET":
        is_staff_accountant = can_read_accounting(request.user)
        if is_staff_accountant:
            movements = ShareCapitalMovement.objects.select_related(
                "member", "policy", "journal_line__entry"
            ).order_by("-created_at", "-id")
        else:
            member = Member.objects.filter(user=request.user).first()
            if member is None:
                return Response({"error": "No member share register is linked to this account."}, status=404)
            movements = ShareCapitalMovement.objects.filter(member=member).select_related(
                "policy", "journal_line__entry"
            ).order_by("-created_at", "-id")

        issued = movements.filter(movement_type="issue").aggregate(
            units=Sum("units"), amount=Sum("amount")
        )
        redeemed = movements.filter(movement_type="redeem").aggregate(
            units=Sum("units"), amount=Sum("amount")
        )
        issued_units = issued["units"] or Decimal("0.000000")
        redeemed_units = redeemed["units"] or Decimal("0.000000")
        issued_amount = issued["amount"] or Decimal("0.00")
        redeemed_amount = redeemed["amount"] or Decimal("0.00")
        paginator = PageNumberPagination()
        paginator.page_size = 50
        page = paginator.paginate_queryset(movements, request)
        results = []
        for movement in page:
            row = {
                "id": str(movement.pk),
                "type": movement.movement_type,
                "units": format(movement.units, ".6f"),
                "recorded_amount": format(movement.amount, ".2f"),
                "currency": movement.currency,
                "policy_version": movement.policy.version,
                "evidence_reference": movement.evidence_reference,
                "journal_entry": str(movement.journal_line.entry_id),
                "recorded_at": timezone.localtime(movement.created_at).isoformat(),
            }
            if is_staff_accountant:
                row["member_number"] = movement.member.member_number
            results.append(row)
        return paginator.get_paginated_response({
            "summary": {
                "units_issued": format(issued_units, ".6f"),
                "units_redeemed": format(redeemed_units, ".6f"),
                "units_recorded": format(issued_units - redeemed_units, ".6f"),
                "amount_issued": format(issued_amount, ".2f"),
                "amount_redeemed": format(redeemed_amount, ".2f"),
                "recorded_capital": format(issued_amount - redeemed_amount, ".2f"),
                "share_capital_is_separate_from_savings": True,
            },
            "results": results,
        })

    if not _authorized_accountant(request.user):
        return Response({"error": "An active accountant or superadministrator is required."}, status=403)
    data = request.data
    try:
        member = Member.objects.get(pk=data.get("member_id"))
        journal_line = JournalLine.objects.get(pk=data.get("journal_line_id"))
        policy = ShareCapitalPolicy.objects.get(pk=data.get("policy_id"))
        movement = record_share_capital_movement(
            idempotency_key=data.get("idempotency_key"),
            member=member,
            movement_type=data.get("type"),
            units=data.get("units"),
            amount=data.get("amount"),
            journal_line=journal_line,
            policy=policy,
            evidence_reference=data.get("evidence_reference"),
            actor=request.user,
        )
    except (Member.DoesNotExist, JournalLine.DoesNotExist, ShareCapitalPolicy.DoesNotExist):
        return Response({"error": "Member, journal line, or share policy was not found."}, status=404)
    except (AccountingConflict, AccountingPermissionDenied, InvalidJournal) as exc:
        return _error_response(exc)
    return Response({"id": str(movement.pk), "status": "recorded"}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountingSuperAdmin])
def create_share_policy(request):
    try:
        policy = create_share_capital_policy(
            version=request.data.get("version"),
            terms=request.data.get("terms"),
            actor=request.user,
        )
    except (AccountingConflict, AccountingPermissionDenied, InvalidJournal) as exc:
        return _error_response(exc)
    return Response({"id": policy.pk, "version": policy.version, "active": policy.active}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountingSuperAdmin])
def approve_share_policy(request, policy_id):
    try:
        policy = approve_share_capital_policy(policy_id=policy_id, actor=request.user)
    except (AccountingConflict, AccountingPermissionDenied, InvalidJournal) as exc:
        return _error_response(exc)
    return Response({"id": policy.pk, "version": policy.version, "active": policy.active}, status=200)


def _entry_response(entry):
    cached_lines = getattr(entry, "_prefetched_objects_cache", {}).get("lines")
    lines = list(cached_lines) if cached_lines is not None else list(
        entry.lines.select_related("account").order_by("line_number")
    )
    debit_total = sum((line.debit for line in lines), Decimal("0.00"))
    credit_total = sum((line.credit for line in lines), Decimal("0.00"))
    return {
        "id": str(entry.pk),
        "status": entry.status,
        "source_type": entry.source_type,
        "source_reference": entry.source_reference,
        "description": entry.description,
        "currency": entry.currency,
        "reverses": str(entry.reverses_id) if entry.reverses_id else None,
        "adjusts": str(entry.adjusts_id) if entry.adjusts_id else None,
        "debit_total": format(debit_total, ".2f"),
        "credit_total": format(credit_total, ".2f"),
        "posted_at": timezone.localtime(entry.posted_at).isoformat() if entry.posted_at else None,
        "lines": [
            {"account_code": line.account.code, "account_name": line.account.name,
             "debit": format(line.debit, ".2f"), "credit": format(line.credit, ".2f"),
             "memo": line.memo}
            for line in lines
        ],
    }
