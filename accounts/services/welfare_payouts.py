"""Treasury-controlled welfare payout orchestration and journal settlement."""
from decimal import Decimal, InvalidOperation
from logging import getLogger

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.module_loading import import_string

from accounting.models import LedgerAccount
from accounting.services import AccountingError, post_journal_entry
from accounts.models import AuditLog
from accounts.welfare_models import WelfarePayout
from core.services.fosa_payouts import PayoutRejected, PayoutUnavailable, normalize_payout_destination


logger = getLogger(__name__)


class WelfarePayoutConflict(Exception):
    pass


def get_welfare_provider():
    """The configured factory returns an approved outbound adapter or None."""
    if not settings.WELFARE_PAYOUT_PROVIDER:
        return None
    try:
        provider = import_string(settings.WELFARE_PAYOUT_PROVIDER)()
        return provider if callable(getattr(provider, "submit", None)) and callable(getattr(provider, "status", None)) else None
    except Exception:
        logger.error("Welfare payout provider could not be loaded.")
        return None


def payout_accounts():
    accounts = LedgerAccount.objects.filter(currency="KES", active=True, permits_posting=True).in_bulk(field_name="system_key")
    benefit = accounts.get("welfare_benefits")
    cash = accounts.get("welfare_payout_cash")
    if not benefit or not cash or benefit.classification != "expense" or cash.classification != "asset":
        raise PayoutUnavailable("Configure open KES welfare benefit and payout asset accounts before submitting.")
    if benefit.normal_balance != "debit" or cash.normal_balance != "debit":
        raise PayoutUnavailable("Welfare benefit and payout asset accounts must have a normal debit balance.")
    return benefit, cash


def _arguments(payout):
    return {
        "client_reference": f"welfare-payout:{payout.pk}",
        "amount": payout.request.approved_amount,
        "destination": payout.destination_phone,
    }


def _audit(payout, actor, operation, **details):
    AuditLog.log(actor, "other", f"Welfare payout #{payout.pk}", {
        "operation": operation, "request_id": payout.request_id, **details,
    })


@transaction.atomic
def _update_outcome(payout_id, provider_reference, outcome, actor):
    payout = WelfarePayout.objects.select_for_update().get(pk=payout_id)
    if payout.status not in {"pending", "uncertain"}:
        return payout
    if provider_reference:
        if payout.provider_reference and payout.provider_reference != provider_reference:
            raise WelfarePayoutConflict("The provider reference changed. Reconcile before taking another action.")
        payout.provider_reference = provider_reference
    payout.status = outcome
    payout.save(update_fields=("provider_reference", "status"))
    _audit(payout, actor, "welfare_payout_status", status=outcome)
    return payout


def start_welfare_payout(request_id, actor, provider):
    with transaction.atomic():
        payout = WelfarePayout.objects.select_for_update().filter(request_id=request_id).first()
        if not payout:
            raise WelfarePayout.DoesNotExist
        case = payout.request
        if case.member.user_id == actor.pk:
            raise WelfarePayoutConflict("A treasury user cannot initiate their own payout.")
        if payout.status != "awaiting_provider":
            return payout, False
        if not provider:
            raise PayoutUnavailable("An outbound Welfare payout provider must be configured.")
        payout_accounts()
        if case.status != "approved" or not case.approved_amount or case.member.status != "active":
            raise WelfarePayoutConflict("An approved amount and active membership are required.")
        try:
            payout.destination_phone = normalize_payout_destination("mpesa", case.member.phone_number)
        except ValueError as exc:
            raise WelfarePayoutConflict("The member needs a valid registered M-Pesa phone.") from exc
        payout.status = "pending"
        payout.save(update_fields=("status", "destination_phone"))
        _audit(payout, actor, "welfare_payout_submitted", amount=str(case.approved_amount))

    try:
        result = provider.submit(**_arguments(payout))
        reference = _identifier(result.get("provider_reference"))
    except PayoutRejected:
        return _update_outcome(payout.pk, "", "failed", actor), True
    except Exception:
        return _update_outcome(payout.pk, "", "uncertain", actor), True
    return _update_outcome(payout.pk, reference, "pending" if reference else "uncertain", actor), True


def _identifier(value):
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= 100 else ""


@transaction.atomic
def _settle(payout_id, result, actor):
    payout = WelfarePayout.objects.select_for_update().get(pk=payout_id)
    if payout.status not in {"pending", "uncertain"}:
        return payout
    reference = _identifier(result.get("provider_reference"))
    if (result.get("client_reference") != _arguments(payout)["client_reference"] or not reference
            or (payout.provider_reference and payout.provider_reference != reference)):
        raise WelfarePayoutConflict("Provider evidence did not match the stored payout request.")
    outcome = result.get("outcome")
    if outcome in {"pending", "failed"}:
        return _update_outcome(payout.pk, reference, outcome, actor)
    if outcome != "confirmed":
        raise WelfarePayoutConflict("The provider returned an unrecognized payout status.")
    try:
        amount = Decimal(str(result.get("amount")))
        destination = normalize_payout_destination("mpesa", result.get("destination"))
    except (InvalidOperation, ValueError) as exc:
        raise WelfarePayoutConflict("The provider omitted the verified amount or destination.") from exc
    receipt = _identifier(result.get("transaction_id"))
    if amount != payout.request.approved_amount or destination != payout.destination_phone or not receipt:
        raise WelfarePayoutConflict("The verified amount, destination or receipt does not match.")
    if WelfarePayout.objects.filter(provider_transaction_id=receipt).exclude(pk=payout.pk).exists():
        raise WelfarePayoutConflict("This provider transaction is already linked to another payout.")
    benefit, cash = payout_accounts()
    entry = post_journal_entry(
        idempotency_key=f"welfare-payout:{payout.pk}", source_type="welfare_payout",
        source_reference=f"{payout.request_id}:{receipt}", description=f"Welfare payout for request #{payout.request_id}",
        lines=[{"account_id": benefit.pk, "debit": amount}, {"account_id": cash.pk, "credit": amount}],
        actor=actor, system_initiated=True,
    )
    payout.status = "confirmed"
    payout.provider_reference = reference
    payout.provider_transaction_id = receipt
    payout.confirmed_entry = entry
    payout.save(update_fields=("status", "provider_reference", "provider_transaction_id", "confirmed_entry"))
    _audit(payout, actor, "welfare_payout_confirmed", entry=str(entry.pk))
    return payout


def refresh_welfare_payout(request_id, actor, provider):
    payout = WelfarePayout.objects.get(request_id=request_id)
    if payout.request.member.user_id == actor.pk:
        raise WelfarePayoutConflict("A treasury user cannot reconcile their own payout.")
    if payout.status not in {"pending", "uncertain"}:
        return payout
    if not provider or not payout.destination_phone:
        raise PayoutUnavailable("An outbound provider and a stored destination are required for status checks.")
    try:
        result = provider.status(**_arguments(payout), provider_reference=payout.provider_reference)
        if not isinstance(result, dict):
            raise ValueError
    except Exception as exc:
        raise PayoutUnavailable("Payout status could not be verified. The existing attempt remains on record.") from exc
    try:
        return _settle(payout.pk, result, actor)
    except (AccountingError, IntegrityError) as exc:
        raise WelfarePayoutConflict("The provider result needs accounting reconciliation before it can be confirmed.") from exc
