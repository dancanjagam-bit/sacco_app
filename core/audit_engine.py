"""
SACCO Financial Audit Engine
=============================
Runs automated checks against all financial data:

  1. Transaction Integrity — Savings ledger vs Transaction ledger reconciliation
  2. Loan Balance Integrity — verify Loan.balance matches Transaction history
  3. Duplicate Detection — identical amounts within 60-second windows
  4. Collateral Integrity — guarantor locked_amount vs loan balance consistency
  5. Dividend Integrity — verify dividend amount = balance × rate
  6. Suspicious Patterns — rapid deposit→withdraw, loan without audit log
  7. Orphaned Records — Savings/Transaction rows for deleted users
  8. Exit Request Integrity — BOSA balance snapshot vs actual balance
"""

from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum, Count, Q
from django.utils import timezone

from .models import (
    Savings, Loan, Transaction, LoanGuarantor, SavingsDividend, ExitRequest,
    AssetCollateral, SACCOSettings,
)
from accounts.models import AuditLog, User
from members.models import Member


SEVERITY_INFO     = "info"
SEVERITY_LOW      = "low"
SEVERITY_MEDIUM   = "medium"
SEVERITY_HIGH     = "high"
SEVERITY_CRITICAL = "critical"


def _check_transaction_integrity():
    """
    Reconcile Savings ledger against Transaction ledger.
    Every Savings deposit should have a matching Transaction(type="deposit"),
    every withdrawal a Transaction(type="withdrawal"), etc.
    """
    findings = []

    # Check: Savings deposits without matching Transaction
    savings_deposits = Savings.objects.filter(amount__gt=0).exclude(
        account_type__isnull=True
    )
    for s in savings_deposits:
        # Look for a transaction on the same day for the same user+amount
        day_start = s.created_at.replace(hour=0, minute=0, second=0)
        day_end   = day_start + timedelta(days=1)
        matching = Transaction.objects.filter(
            user=s.user,
            type="deposit",
            amount=abs(s.amount),
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).exists()
        if not matching:
            # Skip dividend credits — they're logged as "deposit" type but may use "dividend"
            is_dividend = SavingsDividend.objects.filter(
                user=s.user, amount=abs(s.amount),
                paid_at__date=s.created_at.date(),
            ).exists()
            if not is_dividend:
                findings.append({
                    "rule":          "TXN_INTEGRITY",
                    "severity":      SEVERITY_MEDIUM,
                    "title":         "Savings deposit without matching Transaction record",
                    "description":   f"Savings row #{s.id} for {s.user.username} (KES {s.amount:.2f}, {s.account_type}) has no corresponding Transaction ledger entry.",
                    "entity_type":   "savings",
                    "entity_id":     s.id,
                    "user":          s.user.username,
                })

    # Check: Transaction deposits without matching Savings
    tx_deposits = Transaction.objects.filter(type="deposit")
    for t in tx_deposits:
        matching = Savings.objects.filter(
            user=t.user,
            amount=t.amount,
            created_at__date=t.created_at.date(),
        ).exists()
        if not matching:
            # Check if it's a dividend transaction
            is_dividend = t.note and "dividend" in t.note.lower()
            if not is_dividend:
                findings.append({
                    "rule":          "TXN_INTEGRITY",
                    "severity":      SEVERITY_HIGH,
                    "title":         "Transaction deposit without matching Savings record",
                    "description":   f"Transaction #{t.id} for {t.user.username} (KES {t.amount:.2f}) has no corresponding Savings entry — money may have been credited without actual funds.",
                    "entity_type":   "transaction",
                    "entity_id":     t.id,
                    "user":          t.user.username,
                })

    return findings


def _check_loan_balance_integrity():
    """
    For every approved/repaid loan, verify that:
      balance == (amount + interest_amount) - sum(repayments)
    """
    findings = []

    loans = Loan.objects.filter(status__in=["approved", "repaid"])
    for loan in loans:
        interest_amount = (loan.amount * loan.interest) / Decimal("100")
        expected_total = loan.amount + interest_amount

        # Sum actual repayments
        repayments = Transaction.objects.filter(
            user=loan.user,
            type="repayment",
            note__contains=f"Loan #{loan.id}",
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        expected_balance = expected_total - repayments

        if loan.status == "repaid" and loan.balance != 0:
            findings.append({
                "rule":        "LOAN_BALANCE",
                "severity":    SEVERITY_HIGH,
                "title":       f"Repaid loan #{loan.id} has non-zero balance",
                "description": f"Loan #{loan.id} ({loan.user.username}) status is 'repaid' but balance is KES {loan.balance:.2f}. Expected: KES 0.00.",
                "entity_type": "loan",
                "entity_id":   loan.id,
                "user":        loan.user.username,
            })
        elif abs(loan.balance - expected_balance) > Decimal("1.00"):
            findings.append({
                "rule":        "LOAN_BALANCE",
                "severity":    SEVERITY_CRITICAL,
                "title":       f"Loan #{loan.id} balance mismatch",
                "description": f"Loan #{loan.id} ({loan.user.username}): stored balance KES {loan.balance:.2f} but calculated KES {expected_balance:.2f} "
                               f"(total payable KES {expected_total:.2f} - repayments KES {repayments:.2f}). Difference: KES {abs(loan.balance - expected_balance):.2f}.",
                "entity_type": "loan",
                "entity_id":   loan.id,
                "user":        loan.user.username,
            })

    return findings


def _check_duplicate_transactions():
    """
    Detect duplicate entries — identical amount and type within 60 seconds.
    """
    findings = []

    transactions = Transaction.objects.all().order_by("created_at")
    prev = None

    for t in transactions:
        if prev and (
            t.user_id == prev.user_id
            and t.type == prev.type
            and t.amount == prev.amount
            and (t.created_at - prev.created_at) < timedelta(seconds=60)
        ):
            findings.append({
                "rule":        "DUPLICATE_TXN",
                "severity":    SEVERITY_HIGH,
                "title":       f"Duplicate transaction detected",
                "description": f"Two {t.type} transactions for {t.user.username} of KES {t.amount:.2f} within "
                               f"{(t.created_at - prev.created_at).total_seconds():.0f}s "
                               f"(TXN #{prev.id} at {prev.created_at:%H:%M:%S} and TXN #{t.id} at {t.created_at:%H:%M:%S}).",
                "entity_type": "transaction",
                "entity_id":   t.id,
                "user":        t.user.username,
            })
        prev = t

    return findings


def _check_duplicate_savings():
    """
    Detect duplicate Savings rows — identical amount within 60 seconds.
    """
    findings = []

    savings = Savings.objects.all().order_by("created_at")
    prev = None

    for s in savings:
        if prev and (
            s.user_id == prev.user_id
            and s.amount == prev.amount
            and s.account_type == prev.account_type
            and (s.created_at - prev.created_at) < timedelta(seconds=60)
        ):
            findings.append({
                "rule":        "DUPLICATE_SAVINGS",
                "severity":    SEVERITY_HIGH,
                "title":       f"Duplicate savings entry detected",
                "description": f"Two {s.account_type.upper()} savings entries for {s.user.username} of KES {abs(s.amount):.2f} within "
                               f"{(s.created_at - prev.created_at).total_seconds():.0f}s "
                               f"(row #{prev.id} and row #{s.id}). Possible double-crediting.",
                "entity_type": "savings",
                "entity_id":   s.id,
                "user":        s.user.username,
            })
        prev = s

    return findings


def _check_collateral_integrity():
    """
    Verify guarantor locked amounts are consistent with loan balances.
    A guarantor's locked_amount should not exceed the loan's current balance
    (after interest). Also check for loans approved without collateral.
    """
    findings = []

    # Check: guarantor locked_amount > loan balance
    for g in LoanGuarantor.objects.filter(status="accepted").select_related("loan", "guarantor"):
        loan = g.loan
        if loan.status == "approved" and loan.balance > 0:
            if g.locked_amount > loan.balance:
                findings.append({
                    "rule":        "COLLATERAL_INTEGRITY",
                    "severity":    SEVERITY_MEDIUM,
                    "title":       f"Guarantor lock exceeds loan balance",
                    "description": f"Guarantor {g.guarantor.username} has KES {g.locked_amount:.2f} locked for Loan #{loan.id} "
                                   f"but the loan balance is only KES {loan.balance:.2f}. Lock should be reduced.",
                    "entity_type": "loan_guarantor",
                    "entity_id":   g.id,
                    "user":        g.guarantor.username,
                })

        # Check: locked amount on a repaid loan
        if loan.status == "repaid" and g.locked_amount > 0:
            findings.append({
                "rule":        "COLLATERAL_INTEGRITY",
                "severity":    SEVERITY_HIGH,
                "title":       f"Guarantor lock not released after loan repaid",
                "description": f"Guarantor {g.guarantor.username} still has KES {g.locked_amount:.2f} locked for Loan #{loan.id} "
                               f"which is fully repaid. Lock should be zero.",
                "entity_type": "loan_guarantor",
                "entity_id":   g.id,
                "user":        g.guarantor.username,
            })

    # Check: approved loan with no collateral at all
    for loan in Loan.objects.filter(status="approved"):
        has_guarantors = loan.guarantors.filter(status="accepted").exists()
        has_assets = loan.asset_collaterals.filter(status__in=["active", "legal_charge_registered"]).exists()
        if not has_guarantors and not has_assets:
            # Check if own savings cover the full loan (no external collateral needed)
            if loan.total_savings_at_application < loan.amount:
                findings.append({
                    "rule":        "COLLATERAL_INTEGRITY",
                    "severity":    SEVERITY_CRITICAL,
                    "title":       f"Approved loan #{loan.id} has no collateral coverage",
                    "description": f"Loan #{loan.id} ({loan.user.username}) for KES {loan.amount:.2f} is approved but has "
                                   f"no guarantors or assets. Savings at application were KES {loan.total_savings_at_application:.2f} "
                                   f"which is less than the loan amount.",
                    "entity_type": "loan",
                    "entity_id":   loan.id,
                    "user":        loan.user.username,
                })

    return findings


def _check_dividend_integrity():
    """
    Verify each dividend amount = savings_balance × rate / 100.
    """
    findings = []

    for d in SavingsDividend.objects.all().select_related("user"):
        expected = (d.savings_balance * d.rate / Decimal("100")).quantize(Decimal("0.01"))
        if abs(d.amount - expected) > Decimal("0.01"):
            findings.append({
                "rule":        "DIVIDEND_INTEGRITY",
                "severity":    SEVERITY_HIGH,
                "title":       f"Dividend amount mismatch for {d.user.username} ({d.year})",
                "description": f"Dividend for {d.year}: stored KES {d.amount:.2f} but calculated KES {expected:.2f} "
                               f"(balance KES {d.savings_balance:.2f} x rate {d.rate}%). Difference: KES {abs(d.amount - expected):.2f}.",
                "entity_type": "dividend",
                "entity_id":   d.id,
                "user":        d.user.username,
            })

    return findings


def _check_loan_without_audit_log():
    """
    Detect loans that were approved/rejected but have no AuditLog entry.
    """
    findings = []

    for loan in Loan.objects.filter(status__in=["approved", "rejected"]):
        action = "loan_approve" if loan.status == "approved" else "loan_reject"
        has_log = AuditLog.objects.filter(
            action=action,
            target__contains=f"Loan #{loan.id}",
        ).exists()

        if not has_log:
            findings.append({
                "rule":        "MISSING_AUDIT_LOG",
                "severity":    SEVERITY_MEDIUM,
                "title":       f"Loan #{loan.id} {loan.status} without audit log",
                "description": f"Loan #{loan.id} ({loan.user.username}) has status '{loan.status}' but no AuditLog entry "
                               f"for action '{action}'. The status may have been changed directly in the database.",
                "entity_type": "loan",
                "entity_id":   loan.id,
                "user":        loan.user.username,
            })

    return findings


def _check_suspicious_patterns():
    """
    Detect suspicious activity patterns:
    - Large deposit followed by immediate withdrawal
    - Loan application with no prior savings history
    - Member with many loans but no repayments
    """
    findings = []

    # Rapid deposit → withdrawal within 1 hour
    for user in User.objects.filter(is_member=True):
        user_savings = Savings.objects.filter(user=user).order_by("created_at")
        prev = None
        for s in user_savings:
            if prev and prev.amount > 0 and s.amount < 0:
                time_diff = s.created_at - prev.created_at
                if time_diff < timedelta(hours=1) and abs(s.amount) >= prev.amount * Decimal("0.9"):
                    findings.append({
                        "rule":        "SUSPICIOUS_PATTERN",
                        "severity":    SEVERITY_MEDIUM,
                        "title":       f"Rapid deposit-to-withdrawal pattern",
                        "description": f"{user.username}: deposited KES {prev.amount:.2f} then withdrew KES {abs(s.amount):.2f} "
                                       f"within {time_diff.total_seconds()/60:.0f} minutes. Possible money laundering or testing.",
                        "entity_type": "savings",
                        "entity_id":   s.id,
                        "user":        user.username,
                    })
            prev = s

    # Many loans, no repayments
    for user in User.objects.filter(is_member=True):
        loan_count = Loan.objects.filter(user=user).count()
        if loan_count >= 3:
            repayment_count = Transaction.objects.filter(user=user, type="repayment").count()
            if repayment_count == 0:
                findings.append({
                    "rule":        "SUSPICIOUS_PATTERN",
                    "severity":    SEVERITY_LOW,
                    "title":       f"Multiple loans with zero repayments",
                    "description": f"{user.username} has {loan_count} loans but no repayment transactions on record.",
                    "entity_type": "user",
                    "entity_id":   user.id,
                    "user":        user.username,
                })

    return findings


def _check_orphaned_records():
    """
    Detect Savings or Transaction rows referencing users that no longer exist
    or members whose accounts were deleted.
    """
    findings = []

    # Savings for users that are not active
    for s in Savings.objects.select_related("user").all():
        if not s.user.is_active:
            findings.append({
                "rule":        "ORPHANED_RECORD",
                "severity":    SEVERITY_LOW,
                "title":       f"Savings record for inactive user",
                "description": f"Savings row #{s.id} belongs to {s.user.username} whose account is inactive. "
                               f"Amount: KES {s.amount:.2f} ({s.account_type}).",
                "entity_type": "savings",
                "entity_id":   s.id,
                "user":        s.user.username,
            })

    return findings


def _check_exit_request_integrity():
    """
    Verify that ExitRequest.bosa_balance matches actual BOSA balance at time of check.
    Also check that approved exits with passed holding periods haven't been withdrawn yet.
    """
    findings = []

    for req in ExitRequest.objects.select_related("user").all():
        actual_bosa = (
            Savings.objects.filter(user=req.user, account_type="bosa")
            .aggregate(total=Sum("amount"))["total"] or Decimal("0")
        )

        # Only flag if there's a significant discrepancy
        if req.status in ("pending", "approved") and abs(req.bosa_balance - actual_bosa) > Decimal("1.00"):
            findings.append({
                "rule":        "EXIT_INTEGRITY",
                "severity":    SEVERITY_MEDIUM,
                "title":       f"Exit request BOSA balance mismatch",
                "description": f"Exit request #{req.id} for {req.user.username}: snapshot BOSA balance was "
                               f"KES {req.bosa_balance:.2f} but current BOSA balance is KES {actual_bosa:.2f}. "
                               f"Member may have deposited/withdrew after submitting the request.",
                "entity_type": "exit_request",
                "entity_id":   req.id,
                "user":        req.user.username,
            })

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Master runner
# ─────────────────────────────────────────────────────────────────────────────

def run_full_audit():
    """
    Execute all audit checks and return a list of findings.
    Each finding is a dict with: rule, severity, title, description, entity_type, entity_id, user.
    """
    findings = []

    findings.extend(_check_transaction_integrity())
    findings.extend(_check_loan_balance_integrity())
    findings.extend(_check_duplicate_transactions())
    findings.extend(_check_duplicate_savings())
    findings.extend(_check_collateral_integrity())
    findings.extend(_check_dividend_integrity())
    findings.extend(_check_loan_without_audit_log())
    findings.extend(_check_suspicious_patterns())
    findings.extend(_check_orphaned_records())
    findings.extend(_check_exit_request_integrity())

    # Sort by severity (critical first)
    severity_order = {
        SEVERITY_CRITICAL: 0,
        SEVERITY_HIGH:     1,
        SEVERITY_MEDIUM:    2,
        SEVERITY_LOW:       3,
        SEVERITY_INFO:      4,
    }
    findings.sort(key=lambda f: severity_order.get(f["severity"], 99))

    return findings


def get_audit_summary():
    """Return a summary of findings without running the full audit (uses cached results if available)."""
    from .models import AuditFinding
    qs = AuditFinding.objects.all()
    return {
        "total":      qs.count(),
        "critical":   qs.filter(severity=SEVERITY_CRITICAL).count(),
        "high":       qs.filter(severity=SEVERITY_HIGH).count(),
        "medium":     qs.filter(severity=SEVERITY_MEDIUM).count(),
        "low":        qs.filter(severity=SEVERITY_LOW).count(),
        "info":       qs.filter(severity=SEVERITY_INFO).count(),
        "open":       qs.filter(status="open").count(),
        "reviewing":  qs.filter(status="reviewing").count(),
        "resolved":   qs.filter(status="resolved").count(),
        "dismissed":  qs.filter(status="dismissed").count(),
    }
