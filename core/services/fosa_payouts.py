"""FOSA payout reservation and settlement primitives.

There is intentionally no live adapter here yet. Daraja STK Push/C2B collect
money into the SACCO; it is not a member disbursement API. The HTTP endpoint
remains disabled until an approved disbursement adapter and credentials exist.
These state transitions are exercised only with mocked provider clients.
"""
from decimal import Decimal
import re
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import AuditLog
from core.collateral import get_withdrawable_balance
from core.models import FosaWithdrawal, Savings, Transaction


class PayoutUnavailable(Exception):
    pass


class PayoutRejected(Exception):
    """The provider definitively rejected the payout before paying it."""

    def __init__(self, reason_code="provider_rejected"):
        self.reason_code = reason_code
        super().__init__(reason_code)


class PayoutTimedOut(Exception):
    """The provider outcome is unknown; funds must remain reserved."""

    def __init__(self, provider_reference=None):
        self.provider_reference = provider_reference
        super().__init__("provider_timeout")


class IdempotencyConflict(Exception):
    pass


class InsufficientPayoutFunds(Exception):
    pass


SUPPORTED_DESTINATIONS = {"mpesa"}
ACTIVE_RESERVATION_STATUSES = ("requested", "pending", "uncertain")


def normalize_payout_destination(destination_type, destination):
    if destination_type not in SUPPORTED_DESTINATIONS:
        raise ValueError("Unsupported payout destination.")
    cleaned = re.sub(r"[\s-]", "", str(destination or ""))
    if re.fullmatch(r"0[17]\d{8}", cleaned):
        return "+254" + cleaned[1:]
    if re.fullmatch(r"254[17]\d{8}", cleaned):
        return "+" + cleaned
    if re.fullmatch(r"\+254[17]\d{8}", cleaned):
        return cleaned
    raise ValueError("Enter a valid Kenyan M-Pesa number.")


def get_live_payout_provider():
    """Return the configured real adapter, if one exists.

    No disbursement provider is implemented in this repository. Never infer
    payout support from MPESA_ENV or STK/C2B settings.
    """
    return None


def reserve_and_submit_withdrawal(*, user, amount, destination_type,
                                  destination, client_request_id, provider):
    """Persist a reservation before a provider request; never settle on accept."""
    if provider is None:
        raise PayoutUnavailable
    try:
        normalized_destination = normalize_payout_destination(destination_type, destination)
        request_key = uuid.UUID(str(client_request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid payout destination or request reference.") from exc
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValueError("Withdrawal amount must be greater than zero.")

    User = get_user_model()
    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        existing = FosaWithdrawal.objects.filter(
            user=locked_user, client_request_id=request_key,
        ).first()
        if existing:
            if (
                existing.amount != amount
                or existing.destination_type != destination_type
                or existing.destination_phone != normalized_destination
            ):
                raise IdempotencyConflict
            return existing, False

        balances = get_withdrawable_balance(locked_user)
        available = Decimal(str(balances["fosa_withdrawable"]))
        if amount > max(available, Decimal("0.00")):
            raise InsufficientPayoutFunds

        withdrawal = FosaWithdrawal.objects.create(
            user=locked_user,
            client_request_id=request_key,
            amount=amount,
            destination_type=destination_type,
            destination_phone=normalized_destination,
            status="requested",
        )
        AuditLog.log(
            locked_user, "fosa_withdrawal_requested", str(withdrawal.reference),
            {"amount": str(amount), "destination_type": destination_type},
        )

    # The database reservation is committed before calling an external system.
    try:
        provider_result = provider.submit(withdrawal)
    except PayoutRejected as exc:
        FosaWithdrawal.objects.filter(pk=withdrawal.pk, status="requested").update(
            status="failed", failure_reason_code=exc.reason_code,
            settled_at=timezone.now(),
        )
        return FosaWithdrawal.objects.get(pk=withdrawal.pk), True
    except (PayoutTimedOut, TimeoutError) as exc:
        FosaWithdrawal.objects.filter(pk=withdrawal.pk, status="requested").update(
            status="uncertain", failure_reason_code="provider_timeout",
            provider_reference=getattr(exc, "provider_reference", None),
        )
        return FosaWithdrawal.objects.get(pk=withdrawal.pk), True
    except Exception:
        # Any unclassified exception after network submission may mean the
        # provider received it. Keep the hold and prohibit an automatic retry.
        FosaWithdrawal.objects.filter(pk=withdrawal.pk, status="requested").update(
            status="uncertain", failure_reason_code="provider_outcome_unknown",
        )
        return FosaWithdrawal.objects.get(pk=withdrawal.pk), True

    provider_reference = str(provider_result.get("provider_reference") or "").strip()
    if not provider_reference:
        FosaWithdrawal.objects.filter(pk=withdrawal.pk, status="requested").update(
            status="uncertain", failure_reason_code="missing_provider_reference",
        )
    else:
        FosaWithdrawal.objects.filter(pk=withdrawal.pk, status="requested").update(
            status="pending", provider_reference=provider_reference,
        )
    # A provider's request acceptance is never evidence of money delivered.
    return FosaWithdrawal.objects.get(pk=withdrawal.pk), True


@transaction.atomic
def process_payout_confirmation(*, provider_reference, outcome,
                                provider_transaction_id=None, reason_code=""):
    """Apply an authenticated provider result once, keyed by stored reference."""
    withdrawal = (
        FosaWithdrawal.objects.select_for_update()
        .filter(provider_reference=provider_reference)
        .first()
    )
    if not withdrawal:
        return None

    if outcome == "failed":
        if withdrawal.status in ("succeeded", "failed"):
            return withdrawal
        withdrawal.status = "failed"
        withdrawal.failure_reason_code = reason_code[:40] or "provider_failed"
        withdrawal.settled_at = timezone.now()
        withdrawal.save(update_fields=("status", "failure_reason_code", "settled_at", "updated_at"))
        AuditLog.log(
            withdrawal.user, "fosa_payout_failed", str(withdrawal.reference),
            {"provider_reference": provider_reference, "reason_code": withdrawal.failure_reason_code},
        )
        return withdrawal

    if outcome != "succeeded" or not provider_transaction_id:
        raise ValueError("A successful payout requires a provider transaction reference.")
    if withdrawal.status == "succeeded":
        if withdrawal.provider_transaction_id == provider_transaction_id:
            return withdrawal
        raise IdempotencyConflict
    if withdrawal.provider_transaction_id and withdrawal.provider_transaction_id != provider_transaction_id:
        raise IdempotencyConflict

    # A delayed provider success can supersede an earlier uncertain/failed
    # result. Post the debit now because confirmed external money has left.
    try:
        savings_entry = Savings.objects.create(
            user=withdrawal.user, amount=-withdrawal.amount, account_type="fosa",
        )
        ledger_entry = Transaction.objects.create(
            user=withdrawal.user, type="withdrawal", amount=withdrawal.amount,
            account_type="fosa",
            note=f"FOSA payout {withdrawal.reference}",
        )
    except IntegrityError:
        # The outer atomic block rolls back and a retry will observe the
        # settled row if another worker completed the same provider event.
        raise

    withdrawal.status = "succeeded"
    withdrawal.provider_transaction_id = str(provider_transaction_id)[:64]
    withdrawal.failure_reason_code = ""
    withdrawal.savings_entry = savings_entry
    withdrawal.ledger_transaction = ledger_entry
    withdrawal.settled_at = timezone.now()
    withdrawal.save(update_fields=(
        "status", "provider_transaction_id", "failure_reason_code",
        "savings_entry", "ledger_transaction", "settled_at", "updated_at",
    ))
    AuditLog.log(
        withdrawal.user, "fosa_payout_confirmed", str(withdrawal.reference),
        {"provider_reference": provider_reference,
         "provider_transaction_id": withdrawal.provider_transaction_id,
         "amount": str(withdrawal.amount)},
    )
    return withdrawal
