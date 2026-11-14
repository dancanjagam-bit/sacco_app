"""Receipt correlation and balances for persisted transport payment attempts."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from accounts.models import AuditLog
from core.models import MpesaTransaction, Transaction
from core.transport_models import TransportPayment, TransportPaymentReviewEvent, TransportRemittance
from .daraja_service import DarajaError, to_safaricom_phone


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")


def payment_amount(value, *, allow_zero=False):
    """Validate a submitted amount before any database rounding can occur."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not ZERO <= amount <= MAX_AMOUNT:
            raise ValueError
        if amount != amount.quantize(CENT) or (not allow_zero and not amount):
            raise ValueError
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid KES amount with at most two decimal places.") from None
    return amount.quantize(CENT)


def verified_amount(payment):
    if payment.confirmed_at or payment.status == "confirmed" or (
        payment.method == "c2b" and payment.status == "unmatched"
    ):
        return payment.received_amount
    return None


@dataclass(frozen=True)
class RemittanceBalance:
    received: Decimal
    outstanding: Decimal
    available_to_pay: Decimal


def remittance_balance(remittance, payments=None):
    if payments is None:
        payments = remittance.payments.all()
    received = reserved = ZERO
    for payment in payments:
        amount = verified_amount(payment)
        if amount is not None:
            received += amount
        elif payment.status in {"pending", "needs_review", "confirmed"}:
            # Unsettled attempts can still receive money. Staff must release an
            # uncertain attempt before another request can use its balance.
            reserved += payment.amount
    outstanding = max(ZERO, remittance.amount - received)
    return RemittanceBalance(received, outstanding, max(ZERO, outstanding - reserved))


def refresh_remittance(remittance):
    """Refresh while holding the remittance row lock."""
    payments = list(remittance.payments.all())
    total = remittance_balance(remittance, payments).received
    if total > remittance.amount:
        status = "needs_review"
    elif total == remittance.amount:
        status = "confirmed"
    elif total > ZERO:
        status = "partial"
    elif any(payment.status == "needs_review" for payment in payments):
        status = "needs_review"
    elif payments and all(payment.status == "failed" for payment in payments):
        status = "failed"
    else:
        status = "pending"
    if remittance.status != status:
        remittance.status = status
        remittance.save(update_fields=["status", "updated_at"])


def _attempt_signature(payment, secret=None):
    return salted_hmac(
        "transport-stk-callback-v1", f"{payment.pk}:{payment.idempotency_key}", secret=secret, algorithm="sha256",
    ).hexdigest()


def stk_callback_tag(payment):
    return f"transport-stk/{payment.pk}/{_attempt_signature(payment)}"


def review_callback(channel, reason, *, reference, receipt="", amount=None, payment=None):
    key = sha256(f"{channel}|{reason}|{reference}|{receipt}|{amount}".encode()).hexdigest()
    return TransportPaymentReviewEvent.objects.get_or_create(event_key=key, defaults={
        "payment": payment,
        "receipt": receipt[:20],
        "provider_reference": reference[:120],
        "observed_amount": amount,
        "reason": reason,
    })[0]


def _provider_id(value, *, max_length=100):
    value = str(value or "").strip()
    return value if len(value) <= max_length else ""


def _provider_receipt(value):
    return _provider_id(value, max_length=20).upper()


def _conflicting_receipt(receipt, *, payment_id=None, mpesa_id=None):
    return (
        TransportPayment.objects.filter(mpesa_receipt=receipt).exclude(pk=payment_id).exists()
        or MpesaTransaction.objects.filter(mpesa_receipt=receipt).exclude(pk=mpesa_id).exists()
        or Transaction.objects.filter(note__startswith="Paybill deposit (").filter(note__icontains=f"— {receipt}").exists()
    )


def _save_provider_link(payment, checkout, merchant):
    """Bind an attempt to the provider's exact identifiers under its lock."""
    if payment.mpesa_transaction_id:
        provider = MpesaTransaction.objects.select_for_update().get(pk=payment.mpesa_transaction_id)
        if provider.checkout_request_id != checkout or (
            merchant and provider.merchant_request_id and provider.merchant_request_id != merchant
        ):
            return None
        if merchant and not provider.merchant_request_id:
            provider.merchant_request_id = merchant
            provider.save(update_fields=["merchant_request_id", "updated_at"])
        return provider

    try:
        with transaction.atomic():
            provider = MpesaTransaction.objects.create(
                user=payment.requested_by, phone=payment.payer_phone,
                payment_type="transport_remittance", amount=payment.amount,
                checkout_request_id=checkout, merchant_request_id=merchant,
                transport_remittance_id=payment.remittance_id,
            )
    except IntegrityError:
        return None
    payment.mpesa_transaction = provider
    payment.provider_reference = checkout
    payment.save(update_fields=["mpesa_transaction", "provider_reference"])
    return provider


def _lock_attempt(payment):
    remittance = TransportRemittance.objects.select_for_update().get(pk=payment.remittance_id)
    return TransportPayment.objects.select_for_update().get(pk=payment.pk), remittance


def _mark_attempt_for_review(payment, reason):
    if verified_amount(payment) is None:
        payment.status = "needs_review"
        payment.review_reason = reason
        payment.save(update_fields=["status", "review_reason"])


@transaction.atomic
def record_stk_initiation(payment, response=None):
    """Persist the synchronous provider response without racing a callback."""
    payment, remittance = _lock_attempt(payment)
    if response is None:
        if not payment.mpesa_transaction_id:
            _mark_attempt_for_review(payment, "The provider request outcome is uncertain. Verify it before retrying.")
            refresh_remittance(remittance)
        return payment

    checkout = _provider_id(response.get("CheckoutRequestID"))
    merchant = _provider_id(response.get("MerchantRequestID"))
    if not checkout or not _save_provider_link(payment, checkout, merchant):
        reason = "The STK initiation response could not be matched to the stored payment attempt."
        _mark_attempt_for_review(payment, reason)
        review_callback("stk", reason, reference=checkout, payment=payment)
        refresh_remittance(remittance)
    return payment


@transaction.atomic
def record_stk_callback(parsed, payload, *, payment_id=None, signature=None, provider=None):
    """Accept a signed new attempt or a checkout-matched legacy attempt."""
    if payment_id is not None:
        if not 0 < payment_id <= 2**63 - 1:
            return False
        payment = TransportPayment.objects.filter(pk=payment_id, method="stk", requires_signed_callback=True).first()
        if not payment or not any(
            constant_time_compare(signature or "", _attempt_signature(payment, secret))
            for secret in (settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS)
        ):
            return False
    else:
        payment = TransportPayment.objects.filter(mpesa_transaction=provider, method="stk", requires_signed_callback=False).first()
        if not payment:
            return False

    payment, remittance = _lock_attempt(payment)
    checkout = _provider_id(parsed["checkout_request_id"])
    merchant = _provider_id(parsed.get("merchant_request_id"))
    receipt = _provider_receipt(parsed.get("mpesa_receipt"))
    try:
        amount = payment_amount(parsed.get("amount")) if parsed["success"] else None
        phone = to_safaricom_phone(parsed.get("phone") or "") if parsed["success"] else None
    except (ValueError, DarajaError):
        amount = phone = None
    if not checkout or (parsed["success"] and (not receipt or amount != payment.amount or phone != payment.payer_phone)):
        reason = "STK callback details do not match the stored payment attempt."
        _mark_attempt_for_review(payment, reason)
        review_callback("stk", reason, reference=checkout, receipt=receipt, amount=amount, payment=payment)
        refresh_remittance(remittance)
        return True

    provider = _save_provider_link(payment, checkout, merchant)
    if provider is None:
        reason = "The STK provider identifiers were already used or do not match the stored attempt."
        _mark_attempt_for_review(payment, reason)
        review_callback("stk", reason, reference=checkout, receipt=receipt, amount=amount, payment=payment)
        refresh_remittance(remittance)
        return True

    if provider.status != "pending":
        if (provider.status == "confirmed" and parsed["success"] and provider.mpesa_receipt == receipt) or (
            provider.status == "failed" and not parsed["success"] and provider.result_code == parsed["result_code"]
        ):
            return True
        reason = "The STK callback conflicts with a previously recorded final result. Verify both with the provider."
        review_callback("stk", reason, reference=checkout, receipt=receipt, amount=amount, payment=payment)
        # A signed success with a matching amount and unique receipt can
        # arrive after a failed status. Preserve both observations for review.
        if not (provider.status == "failed" and parsed["success"] and payment.requires_signed_callback):
            _mark_attempt_for_review(payment, reason)
            refresh_remittance(remittance)
            return True

    if parsed["success"]:
        try:
            with transaction.atomic():
                if _conflicting_receipt(receipt, payment_id=payment.pk, mpesa_id=provider.pk):
                    raise IntegrityError("Provider receipt is already in use.")
                payment.mpesa_receipt = receipt
                _confirm_provider_receipt(payment, amount)
        except IntegrityError:
            reason = "The provider receipt was already used for another payment."
            _mark_attempt_for_review(payment, reason)
            review_callback("stk", reason, reference=checkout, receipt=receipt, amount=amount, payment=payment)
            refresh_remittance(remittance)
            return True
        provider.status = "confirmed"
        provider.mpesa_receipt = receipt
        _post_provider_receipt(payment)
    else:
        provider.status = "failed"
        payment.status = "failed"
        payment.review_reason = "Daraja returned a failed payment result."
        payment.save(update_fields=["status", "review_reason"])

    provider.result_code = parsed["result_code"]
    provider.result_desc = parsed["result_desc"]
    provider.raw_callback = payload
    provider.save(update_fields=["status", "mpesa_receipt", "result_code", "result_desc", "raw_callback", "updated_at"])
    refresh_remittance(remittance)
    return True


def _confirm_provider_receipt(payment, amount):
    payment.status = "confirmed" if payment.remittance_id else "unmatched"
    payment.confirmed_at = timezone.now()
    payment.received_amount = amount
    payment.unallocated_amount = amount
    payment.review_reason = ""
    payment.save()


def _post_provider_receipt(payment):
    from .transport_accounting import record_transport_receipt

    accounting_status = record_transport_receipt(payment)
    AuditLog.log(None, "other", f"Transport payment #{payment.pk}", {
        "event": "provider_confirmed" if payment.remittance_id else "provider_receipt_unmatched",
        "amount": str(payment.received_amount), "receipt": payment.mpesa_receipt,
        "accounting_status": accounting_status,
    })


@transaction.atomic
def record_c2b_receipt(data, reference, remittance):
    receipt = _provider_receipt(data.get("TransID"))
    try:
        amount = payment_amount(data.get("TransAmount"))
    except ValueError:
        review_callback("c2b", "The provider callback amount was invalid.", reference=reference, receipt=receipt)
        return
    if not receipt:
        review_callback("c2b", "The provider callback did not include a valid receipt.", reference=reference, amount=amount)
        return
    if remittance:
        remittance = TransportRemittance.objects.select_for_update().get(pk=remittance.pk)

    try:
        with transaction.atomic():
            if _conflicting_receipt(receipt):
                raise IntegrityError("Provider receipt is already in use.")
            payment = TransportPayment(
                remittance=remittance, method="c2b", amount=amount, mpesa_receipt=receipt,
                provider_reference=reference[:120], payer_phone=_provider_id(data.get("MSISDN"), max_length=15),
            )
            _confirm_provider_receipt(payment, amount)
    except IntegrityError:
        existing = TransportPayment.objects.filter(mpesa_receipt=receipt).first()
        if existing and existing.method == "c2b" and existing.amount == amount and existing.provider_reference == reference:
            return
        review_callback(
            "c2b", "The provider receipt was already used for another reference or amount.",
            reference=reference, receipt=receipt, amount=amount, payment=existing,
        )
        return

    _post_provider_receipt(payment)
    if remittance:
        refresh_remittance(remittance)
