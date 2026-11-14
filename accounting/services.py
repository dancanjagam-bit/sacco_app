import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import AuditLog, StaffProfile
from .models import JournalEntry, JournalLine, LedgerAccount, ShareCapitalMovement, ShareCapitalPolicy


class AccountingError(Exception):
    """Base error for rejected accounting commands."""


class AccountingPermissionDenied(AccountingError):
    pass


class AccountingConflict(AccountingError):
    pass


class InvalidJournal(AccountingError):
    pass


def _authorized_accountant(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return bool(
        user.is_staff
        and StaffProfile.objects.filter(
            user=user, status="active", role__in=("accountant", "superadmin")
        ).exists()
    )


def _require_accountant(user):
    if not _authorized_accountant(user):
        raise AccountingPermissionDenied("An active accountant or superadministrator is required.")


def is_accounting_superadmin(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return bool(
        user.is_staff
        and StaffProfile.objects.filter(user=user, status="active", role="superadmin").exists()
    )


def _require_superadmin(user):
    if not is_accounting_superadmin(user):
        raise AccountingPermissionDenied("An active superadministrator is required for policy approval.")


def create_share_capital_policy(*, version, terms, actor):
    _require_superadmin(actor)
    version = str(version or "").strip()
    if not version or len(version) > 64:
        raise InvalidJournal("A policy version of at most 64 characters is required.")
    if not isinstance(terms, dict) or not terms:
        raise InvalidJournal("Provide the cooperative-approved share terms as a non-empty object.")
    try:
        return ShareCapitalPolicy.objects.create(version=version, terms=terms, created_by=actor)
    except IntegrityError:
        raise AccountingConflict("That share-capital policy version already exists.") from None


def approve_share_capital_policy(*, policy_id, actor):
    _require_superadmin(actor)
    try:
        with transaction.atomic():
            try:
                policy = ShareCapitalPolicy.objects.select_for_update().get(pk=policy_id)
            except ShareCapitalPolicy.DoesNotExist:
                raise InvalidJournal("Share-capital policy was not found.") from None
            if policy.created_by_id == actor.pk:
                raise AccountingPermissionDenied("A different superadministrator must approve this policy.")
            if policy.active and policy.approved_at:
                return policy
            ShareCapitalPolicy.objects.filter(active=True).exclude(pk=policy.pk).update(active=False)
            policy.active = True
            policy.approved_by = actor
            policy.approved_at = timezone.now()
            policy.save(update_fields=("active", "approved_by", "approved_at"))
            AuditLog.log(
                actor,
                "other",
                target=f"Share-capital policy {policy.version}",
                details={"event": "share_capital_policy_approved", "version": policy.version},
            )
            return policy
    except IntegrityError:
        raise AccountingConflict("Another share-capital policy was activated concurrently; retry after review.") from None


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidJournal("Journal amounts must be valid decimal values.") from None
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise InvalidJournal("Journal amounts must be non-negative and use at most two decimal places.")
    return amount.quantize(Decimal("0.01"))


def _normalize_lines(lines, currency):
    if not isinstance(lines, (list, tuple)) or len(lines) < 2:
        raise InvalidJournal("A journal entry needs at least two lines.")
    normalized = []
    for index, raw in enumerate(lines, start=1):
        if not isinstance(raw, dict):
            raise InvalidJournal("Each journal line must be an object.")
        account_id = raw.get("account_id", getattr(raw.get("account"), "pk", raw.get("account")))
        try:
            account_id = int(account_id)
        except (TypeError, ValueError):
            raise InvalidJournal("Each journal line must reference a valid ledger account.") from None
        try:
            line_number = int(raw.get("line_number", index))
        except (TypeError, ValueError):
            raise InvalidJournal("Journal line numbers must be positive integers.") from None
        if line_number < 1 or line_number > 32767:
            raise InvalidJournal("Journal line numbers must be positive integers.")
        debit = _amount(raw.get("debit", 0))
        credit = _amount(raw.get("credit", 0))
        if (debit > 0) == (credit > 0):
            raise InvalidJournal("Each line must have exactly one positive debit or credit amount.")
        normalized.append({
            "account_id": account_id,
            "line_number": line_number,
            "debit": debit,
            "credit": credit,
            "memo": str(raw.get("memo", ""))[:240],
        })
    if len({line["line_number"] for line in normalized}) != len(normalized):
        raise InvalidJournal("Journal line numbers must be unique.")
    accounts = LedgerAccount.objects.in_bulk({line["account_id"] for line in normalized})
    if len(accounts) != len({line["account_id"] for line in normalized}):
        raise InvalidJournal("A journal line references an unknown ledger account.")
    for account in accounts.values():
        if not account.active or not account.permits_posting:
            raise InvalidJournal(f"Ledger account {account.code} is not open for posting.")
        if account.currency != currency:
            raise InvalidJournal("All journal accounts must use the entry currency.")
    return normalized


def _fingerprint(source_type, source_reference, description, reason, currency, lines, reverses, adjusts):
    payload = {
        "source_type": source_type,
        "source_reference": source_reference,
        "description": description,
        "reason": reason,
        "currency": currency,
        "reverses": str(reverses.pk) if reverses else None,
        "adjusts": str(adjusts.pk) if adjusts else None,
        "lines": [
            {
                **line,
                "debit": format(line["debit"], ".2f"),
                "credit": format(line["credit"], ".2f"),
            }
            for line in lines
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def post_journal_entry(
    *, idempotency_key, source_type, source_reference, description, lines,
    actor=None, reason="", currency="KES", reverses=None, adjusts=None,
    system_initiated=False,
):
    """Atomically validate and post one balanced journal entry.

    Human-initiated postings require an active accountant/superadministrator.
    `system_initiated=True` is reserved for trusted server-side settlement
    services and must never be exposed as a client-controlled API flag.
    """
    if not system_initiated:
        _require_accountant(actor)
    idempotency_key = str(idempotency_key or "").strip()
    source_type = str(source_type or "").strip()
    source_reference = str(source_reference or "").strip()
    description = str(description or "").strip()
    reason = str(reason or "").strip()
    currency = str(currency or "").strip().upper()
    if not idempotency_key or len(idempotency_key) > 128:
        raise InvalidJournal("A unique idempotency key of at most 128 characters is required.")
    if not source_type or len(source_type) > 48 or not source_reference or len(source_reference) > 128:
        raise InvalidJournal("Source type and source reference are required for traceability.")
    if not description or len(description) > 240:
        raise InvalidJournal("A description of at most 240 characters is required.")
    if len(currency) != 3 or not currency.isalpha() or not currency.isupper():
        raise InvalidJournal("Currency must be a three-letter uppercase code.")
    if (reverses or adjusts) and not reason:
        raise InvalidJournal("A reason is required for reversals and adjustments.")

    normalized = _normalize_lines(lines, currency)
    debit_total = sum((line["debit"] for line in normalized), Decimal("0.00"))
    credit_total = sum((line["credit"] for line in normalized), Decimal("0.00"))
    if debit_total != credit_total:
        raise InvalidJournal("Debits and credits must balance exactly.")
    fingerprint = _fingerprint(
        source_type, source_reference, description, reason, currency,
        normalized, reverses, adjusts,
    )

    try:
        with transaction.atomic():
            # The nested savepoint lets an idempotency race roll back only this
            # attempted insert before we inspect the winning request.
            with transaction.atomic():
                entry = JournalEntry.objects.create(
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                    source_type=source_type,
                    source_reference=source_reference,
                    description=description,
                    reason=reason,
                    currency=currency,
                    status="draft",
                    created_by=actor,
                    reverses=reverses,
                    adjusts=adjusts,
                )
            JournalLine.objects.bulk_create([
                JournalLine(entry=entry, **line) for line in normalized
            ])
            audit = AuditLog.log(
                actor,
                "journal_entry_posted",
                target=f"Journal {entry.pk}",
                details={
                    "source_type": source_type,
                    "source_reference": source_reference,
                    "currency": currency,
                    "debit_total": format(debit_total, ".2f"),
                    "credit_total": format(credit_total, ".2f"),
                    "system_initiated": bool(system_initiated),
                },
            )
            entry.status = "posted"
            entry.posted_by = actor
            entry.posted_at = timezone.now()
            entry.audit_log = audit
            entry.save(update_fields=("status", "posted_by", "posted_at", "audit_log"))
            return entry
    except IntegrityError:
        existing = JournalEntry.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise AccountingConflict("This idempotency key was already used for different journal data.") from None
            if existing.status != "posted":
                raise AccountingConflict("A matching draft exists and requires staff investigation.") from None
            return existing
        if reverses and JournalEntry.objects.filter(reverses=reverses).exists():
            raise AccountingConflict("This journal entry already has a full reversal.") from None
        raise AccountingConflict("The journal command conflicts with an existing accounting record.") from None


def reverse_journal_entry(*, entry_id, idempotency_key, reason, actor):
    """Post an exact, linked reversal; posted source rows remain unchanged."""
    _require_accountant(actor)
    reason = str(reason or "").strip()
    if not reason:
        raise InvalidJournal("A reason is required to reverse a posted entry.")
    with transaction.atomic():
        try:
            original = JournalEntry.objects.select_for_update().get(pk=entry_id)
        except JournalEntry.DoesNotExist:
            raise InvalidJournal("Journal entry was not found.") from None
        if original.status != "posted":
            raise AccountingConflict("Only posted journal entries can be reversed.")
        if original.source_type == "transport_receipt" and original.adjustment_entries.filter(
            source_type="transport_allocation", status="posted", reversal_entry__isnull=True,
        ).exists():
            raise AccountingConflict("Reverse the linked transport allocation before reversing its receipt.")
        existing_reversal = JournalEntry.objects.filter(reverses=original).first()
        if existing_reversal and existing_reversal.idempotency_key != str(idempotency_key).strip():
            raise AccountingConflict("This entry already has a full reversal.")
        reversal_lines = [
            {
                "account_id": line.account_id,
                "line_number": line.line_number,
                "debit": line.credit,
                "credit": line.debit,
                "memo": f"Reversal: {line.memo}"[:240],
            }
            for line in original.lines.select_related("account").all()
        ]
        if len(reversal_lines) < 2:
            raise InvalidJournal("The posted entry has no complete line set to reverse.")
        reversed_entry = post_journal_entry(
            idempotency_key=idempotency_key,
            source_type="reversal",
            source_reference=str(original.pk),
            description=f"Reversal of {original.description}"[:240],
            reason=reason,
            currency=original.currency,
            lines=reversal_lines,
            actor=actor,
            reverses=original,
        )
        if not existing_reversal:
            AuditLog.log(
                actor,
                "journal_entry_reversed",
                target=f"Journal {original.pk}",
                details={"reversal_entry": str(reversed_entry.pk), "reason": reason},
            )
        return reversed_entry


def record_share_capital_movement(
    *, idempotency_key, member, movement_type, units, amount, journal_line,
    policy, evidence_reference, actor,
):
    """Record only an approved-policy movement tied to a posted equity line."""
    _require_accountant(actor)
    try:
        units_value = Decimal(str(units))
        amount_value = _amount(amount)
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidJournal("Share units and amount must be valid decimals.") from None
    if not units_value.is_finite() or units_value <= 0 or units_value != units_value.quantize(Decimal("0.000001")):
        raise InvalidJournal("Share units must be positive and use at most six decimal places.")
    idempotency_key = str(idempotency_key or "").strip()
    evidence_reference = str(evidence_reference or "").strip()
    if not idempotency_key or len(idempotency_key) > 128:
        raise InvalidJournal("A unique share movement idempotency key is required.")
    if not evidence_reference or len(evidence_reference) > 128:
        raise InvalidJournal("An evidence reference is required.")
    if movement_type not in {"issue", "redeem"}:
        raise InvalidJournal("Share movement type must be issue or redeem.")

    try:
        with transaction.atomic():
            existing = ShareCapitalMovement.objects.select_for_update().filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                same = (
                    existing.member_id == member.pk
                    and existing.movement_type == movement_type
                    and existing.units == units_value
                    and existing.amount == amount_value
                    and existing.journal_line_id == journal_line.pk
                    and existing.policy_id == policy.pk
                    and existing.evidence_reference == evidence_reference
                )
                if not same:
                    raise AccountingConflict("This share movement key was already used for different data.")
                return existing
            try:
                policy = ShareCapitalPolicy.objects.select_for_update().get(pk=policy.pk, active=True)
                line = JournalLine.objects.select_for_update().select_related("entry", "account").get(pk=journal_line.pk)
            except (ShareCapitalPolicy.DoesNotExist, JournalLine.DoesNotExist):
                raise InvalidJournal("An active approved policy and a posted journal line are required.") from None
            if policy.approved_at is None or policy.approved_by_id is None:
                raise InvalidJournal("Share-capital movements are disabled until cooperative terms are approved.")
            if line.entry.status != "posted" or line.account.classification != "equity":
                raise InvalidJournal("Share-capital movements must reference a posted equity journal line.")
            required_source = "confirmed_share_receipt" if movement_type == "issue" else "confirmed_share_redemption"
            if line.entry.source_type != required_source:
                raise InvalidJournal(
                    "Share movements require a provider-confirmed receipt or an authorized confirmed redemption entry."
                )
            line_amount = line.credit if movement_type == "issue" else line.debit
            opposite_amount = line.debit if movement_type == "issue" else line.credit
            if line_amount != amount_value or opposite_amount != 0:
                raise InvalidJournal("Movement amount and direction must match its linked journal line exactly.")
            if line.entry.currency != line.account.currency:
                raise InvalidJournal("Journal and share-capital account currencies differ.")

            audit = AuditLog.log(
                actor,
                "other",
                target=f"Share-capital movement {idempotency_key}",
                details={
                    "event": "share_capital_movement_recorded",
                    "movement_type": movement_type,
                    "policy_version": policy.version,
                    "journal_entry": str(line.entry_id),
                    "journal_line": line.pk,
                },
            )
            with transaction.atomic():
                return ShareCapitalMovement.objects.create(
                    idempotency_key=idempotency_key,
                    member=member,
                    movement_type=movement_type,
                    units=units_value,
                    amount=amount_value,
                    currency=line.entry.currency,
                    journal_line=line,
                    policy=policy,
                    evidence_reference=evidence_reference,
                    recorded_by=actor,
                    audit_log=audit,
                )
    except IntegrityError:
        existing = ShareCapitalMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            same = (
                existing.member_id == member.pk
                and existing.movement_type == movement_type
                and existing.units == units_value
                and existing.amount == amount_value
                and existing.journal_line_id == journal_line.pk
                and existing.policy_id == policy.pk
                and existing.evidence_reference == evidence_reference
            )
            if same:
                return existing
            raise AccountingConflict("This share movement key was already used for different data.") from None
        raise AccountingConflict("The journal line is already attributed to another share movement.") from None
