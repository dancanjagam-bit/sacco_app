"""Post verified transport receipts through the existing accounting journal."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.db import transaction

from accounting.models import JournalEntry, LedgerAccount
from accounting.services import AccountingError, InvalidJournal, post_journal_entry
from core.transport_models import TransportAllocationRule, TransportPayment, TransportRemittance


RECEIPT_SOURCE = "transport_receipt"
ALLOCATION_SOURCE = "transport_allocation"
CLEARING_KEY = "transport_unallocated_receipts"
RECEIPT_ACCOUNT_KEYS = {
    "cash": "transport_cash_receipts",
    "stk": "transport_mpesa_receipts",
    "c2b": "transport_mpesa_receipts",
}
ALLOCATION_CATEGORIES = {"owner_payable", "welfare"}
CENT = Decimal("0.01")


def _posted_entry(source, payment):
    return JournalEntry.objects.filter(
        source_type=source, source_reference=str(payment.pk), status="posted",
    ).select_related("reversal_entry").first()


def _receipt_accounts(method):
    asset_key = RECEIPT_ACCOUNT_KEYS.get(method)
    if not asset_key:
        return None
    accounts = LedgerAccount.objects.filter(
        system_key__in=(asset_key, CLEARING_KEY), currency="KES", active=True, permits_posting=True,
    ).in_bulk(field_name="system_key")
    asset, clearing = accounts.get(asset_key), accounts.get(CLEARING_KEY)
    if (asset and clearing and asset.classification == "asset" and asset.normal_balance == "debit"
            and clearing.classification == "liability" and clearing.normal_balance == "credit"):
        return asset, clearing
    return None


@transaction.atomic
def record_transport_receipt(payment, actor=None):
    payment = TransportPayment.objects.select_for_update().get(pk=payment.pk)
    if payment.received_amount is None or payment.received_amount <= 0:
        return "unverified"
    existing = _posted_entry(RECEIPT_SOURCE, payment)
    if existing:
        return "reversed" if getattr(existing, "reversal_entry", None) else "posted"
    accounts = _receipt_accounts(payment.method)
    if not accounts:
        return "configuration_required"
    asset, clearing = accounts
    try:
        post_journal_entry(
            idempotency_key=f"transport-receipt:{payment.pk}",
            source_type=RECEIPT_SOURCE,
            source_reference=str(payment.pk),
            description=f"Verified transport payment #{payment.pk}",
            lines=[
                {"account_id": asset.pk, "debit": payment.received_amount},
                {"account_id": clearing.pk, "credit": payment.received_amount},
            ],
            actor=actor,
            system_initiated=True,
        )
    except AccountingError:
        return "posting_review"
    return "posted"


def allocation_terms(definition):
    """Validate the cooperative's explicit percentage and account mapping."""
    if not isinstance(definition, dict):
        raise InvalidJournal("Allocation terms must be an object.")
    reference = definition.get("approval_reference")
    lines = definition.get("lines")
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 120:
        raise InvalidJournal("Supply the cooperative approval reference (up to 120 characters).")
    if not isinstance(lines, list) or not lines:
        raise InvalidJournal("Supply the approved allocation lines.")
    terms = {}
    for row in lines:
        if not isinstance(row, dict) or not isinstance(row.get("category"), str):
            raise InvalidJournal("Each line must name an allocation category.")
        category = row["category"]
        if category not in ALLOCATION_CATEGORIES or category in terms:
            raise InvalidJournal("Use each supported category once: owner_payable or welfare.")
        try:
            account_id = int(row.get("account_id"))
            percentage = Decimal(str(row.get("percent")))
            if (account_id < 1 or not percentage.is_finite() or not 0 < percentage <= 100
                    or percentage != percentage.quantize(Decimal("0.0001"))):
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            raise InvalidJournal("Supply a valid account and a positive percentage with up to four decimal places.") from None
        terms[category] = (account_id, percentage)
    if sum(percentage for _, percentage in terms.values()) != 100:
        raise InvalidJournal("Approved percentages must total 100.")
    remainder = definition.get("rounding_remainder_category")
    if not isinstance(remainder, str) or remainder not in terms:
        raise InvalidJournal("Name the approved category that receives rounding remainders.")
    return terms, remainder


@transaction.atomic
def allocate_transport_receipt(payment_id, *, actor, reason):
    initial = TransportPayment.objects.only("remittance_id").get(pk=payment_id)
    remittance = TransportRemittance.objects.select_for_update().filter(pk=initial.remittance_id).first()
    payment = TransportPayment.objects.select_for_update().get(pk=payment_id)
    existing = _posted_entry(ALLOCATION_SOURCE, payment)
    if existing:
        if getattr(existing, "reversal_entry", None):
            raise InvalidJournal("The allocation was reversed. Use an audited accounting adjustment.")
        return existing
    if (not remittance or payment.remittance_id != remittance.pk or payment.status != "confirmed"
            or remittance.status != "confirmed" or remittance.payments.filter(status="needs_review").exists()):
        raise InvalidJournal("Resolve reconciliation and confirm the full remittance before allocating a receipt.")
    if payment.allocations.exists():
        raise InvalidJournal("This payment has legacy allocation records. Reconcile those entries before allocating again.")
    receipt = _posted_entry(RECEIPT_SOURCE, payment)
    if not receipt or getattr(receipt, "reversal_entry", None):
        raise InvalidJournal("A posted, unreversed receipt is required.")
    receipt = JournalEntry.objects.select_for_update().get(pk=receipt.pk)
    if getattr(receipt, "reversal_entry", None):
        raise InvalidJournal("A posted, unreversed receipt is required.")
    rules = list(TransportAllocationRule.objects.filter(
        active=True, approved_at__isnull=False, approved_by__isnull=False,
    )[:2])
    if len(rules) != 1:
        raise InvalidJournal("Configure exactly one active, approved transport allocation rule.")
    rule = rules[0]
    terms, remainder = allocation_terms(rule.allocations)
    clearing = receipt.lines.get(credit__gt=0)
    accounts = LedgerAccount.objects.in_bulk(account_id for account_id, _ in terms.values())
    if any(
        account_id not in accounts or account_id == clearing.account_id
        or accounts[account_id].classification != "liability"
        or accounts[account_id].normal_balance != "credit"
        for account_id, _ in terms.values()
    ):
        raise InvalidJournal("Allocation destinations must be credit-balance liability accounts distinct from clearing.")
    if len(accounts) != len(terms):
        raise InvalidJournal("Give each allocation category a distinct destination account.")
    shares = {
        category: (clearing.credit * percentage / 100).quantize(CENT, rounding=ROUND_DOWN)
        for category, (_, percentage) in terms.items()
    }
    shares[remainder] += clearing.credit - sum(shares.values())
    entry = post_journal_entry(
        idempotency_key=f"transport-allocation:{payment.pk}",
        source_type=ALLOCATION_SOURCE, source_reference=str(payment.pk),
        description=f"Transport payment #{payment.pk} allocation · {rule.version}",
        adjusts=receipt, reason=reason, actor=actor,
        lines=[{"account_id": clearing.account_id, "debit": clearing.credit}] + [
            {"account_id": terms[category][0], "credit": amount, "memo": category}
            for category, amount in sorted(shares.items()) if amount > 0
        ],
    )
    return entry


def transport_accounting_data(payment, entries):
    receipt = entries.get((RECEIPT_SOURCE, str(payment.pk)))
    allocation = entries.get((ALLOCATION_SOURCE, str(payment.pk)))
    reversed_receipt = receipt and getattr(receipt, "reversal_entry", None)
    reversed_allocation = allocation and getattr(allocation, "reversal_entry", None)
    active_allocation = allocation and not reversed_allocation and not reversed_receipt
    return {
        "accounting_status": (
            "reversed" if reversed_receipt else "posted" if receipt else
            "awaiting_journal" if payment.received_amount is not None else "unverified"
        ),
        "receipt_journal_id": str(receipt.pk) if receipt else None,
        "receipt_reversal_id": str(reversed_receipt.pk) if reversed_receipt else None,
        "allocation_journal_id": str(allocation.pk) if allocation else None,
        "allocation_reversal_id": str(reversed_allocation.pk) if reversed_allocation else None,
        "journal_allocations": [
            {"category": line.memo, "amount": str(line.credit), "journal_entry_id": str(allocation.pk)}
            for line in allocation.lines.all() if line.credit > 0
        ] if active_allocation else [],
        "journal_allocated_amount": str(sum(
            (line.credit for line in allocation.lines.all()), Decimal("0.00")
        )) if active_allocation else "0.00",
    }


def transport_journals(payment_ids):
    return {
        (entry.source_type, entry.source_reference): entry
        for entry in JournalEntry.objects.filter(
            source_type__in=(RECEIPT_SOURCE, ALLOCATION_SOURCE), status="posted",
            source_reference__in=[str(pk) for pk in payment_ids],
        ).select_related("reversal_entry").prefetch_related("lines")
    }
