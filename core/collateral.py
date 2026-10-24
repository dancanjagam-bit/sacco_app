"""
SACCO Collateral Engine
========================
Handles:
  1. Internal collateral — locked savings + guarantor pledges
  2. External collateral — tangible asset registry + LTV enforcement
  3. Dynamic release — gradual collateral unlock as loan is repaid
  4. Withdrawable balance calculation
  5. Disbursement gate — blocks loan payout until collateral is verified

Formulas:
  Withdrawable = Total Savings − (Own Locked Savings + Guarantor Locked Total)
  Own Locked   = min(loan.balance, savings_at_application × retention_ratio)
  Guarantor Locked = reduces proportionally as loan balance drops
"""

from decimal import Decimal
from django.db.models import Sum, F, Q
from django.utils import timezone
from .models import (
    Savings, Loan, LoanGuarantor, AssetCollateral, SACCOSettings,
    ExitRequest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Balance helpers — split by account type
# ─────────────────────────────────────────────────────────────────────────────

def get_bosa_balance(user) -> Decimal:
    """BOSA = Non-Withdrawable Core Shares (loan multiplier base, earns dividends)."""
    return (
        Savings.objects.filter(user=user, account_type="bosa")
        .aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )


def get_fosa_balance(user) -> Decimal:
    """FOSA = Withdrawable Savings (bank-account style, withdraw anytime)."""
    return (
        Savings.objects.filter(user=user, account_type="fosa")
        .aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )


def get_total_savings(user) -> Decimal:
    """Grand total across both account types."""
    return get_bosa_balance(user) + get_fosa_balance(user)


def get_borrower_locked_savings(user) -> Decimal:
    """
    The portion of the borrower's BOSA savings that is locked as collateral
    for their own active loans. FOSA savings are never locked for own loans.
    """
    settings = SACCOSettings.get_settings()
    retention_pct = settings.min_savings_retention / Decimal("100")

    locked = Decimal("0")
    active_loans = Loan.objects.filter(user=user, status="approved", balance__gt=0)

    for loan in active_loans:
        # Lock = min(loan balance, savings at application × retention)
        max_lockable = loan.total_savings_at_application * retention_pct
        # Only BOSA is lockable; FOSA is always free
        bosa_balance = get_bosa_balance(user)
        lock = min(loan.balance, max_lockable, bosa_balance)
        locked += lock

    return locked


def get_guarantor_locked_total(user) -> Decimal:
    """
    Total amount locked in this user's account as guarantor pledges
    for other members' active loans.
    """
    result = (
        LoanGuarantor.objects
        .filter(guarantor=user, status="accepted", loan__status="approved", loan__balance__gt=0)
        .aggregate(total=Sum("locked_amount"))
    )
    return result["total"] or Decimal("0")


def get_guarantor_pledges_detail(user) -> list[dict]:
    """List all active guarantor pledges for this user with loan details."""
    pledges = (
        LoanGuarantor.objects
        .filter(guarantor=user, status="accepted")
        .select_related("loan__user")
        .order_by("-created_at")
    )
    details = []
    for g in pledges:
        loan_active = g.loan.status == "approved" and g.loan.balance > 0
        details.append({
            "loan_id":         g.loan_id,
            "borrower":        g.loan.user.get_full_name() or g.loan.user.username,
            "borrower_number": getattr(getattr(g.loan.user, "member_profile", None), "member_number", ""),
            "loan_amount":     float(g.loan.amount),
            "loan_balance":    float(g.loan.balance),
            "pledged":         float(g.pledged_amount),
            "locked":          float(g.locked_amount),
            "released":        float(g.pledged_amount - g.locked_amount) if loan_active else float(g.pledged_amount),
            "loan_status":     g.loan.status,
            "is_active":       loan_active,
            "created_at":      g.created_at,
        })
    return details


def get_withdrawable_balance(user) -> dict:
    """
    The master calculation. BOSA is non-withdrawable (unless exit approved).
    FOSA is withdrawable up to available balance (minus any guarantor locks
    that may have been placed against FOSA).

    Returns a full breakdown of both account types.
    """
    bosa_balance = get_bosa_balance(user)
    fosa_balance = get_fosa_balance(user)
    total_savings = bosa_balance + fosa_balance

    locked_own     = get_borrower_locked_savings(user)
    locked_guar    = get_guarantor_locked_total(user)
    total_locked   = locked_own + locked_guar

    # FOSA withdrawable = FOSA balance minus any guarantor locks against FOSA
    # (Guarantor pledges lock BOSA first, then FOSA if BOSA is insufficient)
    fosa_locked = max(locked_guar - max(locked_own, Decimal("0")), Decimal("0"))
    fosa_locked = min(fosa_locked, fosa_balance)
    fosa_withdrawable = max(fosa_balance - fosa_locked, Decimal("0"))

    # BOSA is never withdrawable through normal withdrawal
    bosa_withdrawable = Decimal("0")

    # Check if there's an approved exit request with passed holding period
    approved_exit = ExitRequest.objects.filter(
        user=user, status="approved", release_date__lte=timezone.now().date()
    ).first()
    if approved_exit:
        bosa_withdrawable = bosa_balance  # All BOSA can be withdrawn after exit

    total_withdrawable = fosa_withdrawable + bosa_withdrawable

    return {
        "bosa_balance":      float(bosa_balance),
        "fosa_balance":      float(fosa_balance),
        "total_savings":      float(total_savings),
        "locked_own_loans":  float(locked_own),
        "locked_guarantor":  float(locked_guar),
        "total_locked":       float(total_locked),
        "fosa_withdrawable":  float(fosa_withdrawable),
        "bosa_withdrawable":  float(bosa_withdrawable),
        "withdrawable":       float(total_withdrawable),
        "bosa_locked":        float(min(locked_own, bosa_balance)),
        "pledges_detail":     get_guarantor_pledges_detail(user),
        "has_exit_request":   ExitRequest.objects.filter(user=user, status__in=["pending", "approved"]).exists(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lock collateral on loan approval
# ─────────────────────────────────────────────────────────────────────────────

def lock_collateral_on_approval(loan: Loan):
    """
    Called when a loan is approved. Locks:
    1. The borrower's own savings up to the retention ratio
    2. Each accepted guarantor's pledged amount
    """
    settings = SACCOSettings.get_settings()
    retention_pct = settings.min_savings_retention / Decimal("100")

    # 1. Lock borrower's own savings
    max_lockable = loan.total_savings_at_application * retention_pct
    # Don't lock more than the loan balance
    own_lock = min(loan.balance, max_lockable, loan.total_savings_at_application)
    # We don't store a separate "locked_savings" record — the get_borrower_locked_savings()
    # function calculates it dynamically from the loan. So nothing to write here.

    # 2. Lock guarantor pledges
    guarantors = LoanGuarantor.objects.filter(loan=loan, status="accepted")
    total_guaranteed = sum(g.pledged_amount for g in guarantors)

    if total_guaranteed > 0:
        # The guarantor portion covers loan.balance - own_lock
        guarantor_portion = max(loan.balance - own_lock, Decimal("0"))

        for g in guarantors:
            if total_guaranteed > 0:
                # Each guarantor locks proportionally to their pledge
                ratio = g.pledged_amount / total_guaranteed
                g.locked_amount = min(
                    (guarantor_portion * ratio).quantize(Decimal("0.01")),
                    g.pledged_amount,
                )
            else:
                g.locked_amount = g.pledged_amount
            g.save()

    # 3. Activate asset collateral if any
    for asset in loan.asset_collaterals.filter(status="legal_charge_registered"):
        asset.status = "active"
        asset.save()


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic release — recalculate locked amounts after a repayment
# ─────────────────────────────────────────────────────────────────────────────

def recalculate_collateral_release(loan: Loan):
    """
    Called after every repayment. Reduces locked amounts based on the
    loan's new balance, following the admin-configured release hierarchy.
    """
    settings = SACCOSettings.get_settings()
    hierarchy = settings.release_hierarchy
    retention_pct = settings.min_savings_retention / Decimal("100")

    # Borrower's own lock (always recalculated from current balance)
    max_lockable = loan.total_savings_at_application * retention_pct
    own_lock = min(loan.balance, max_lockable, loan.total_savings_at_application)

    # Guarantor locks
    guarantors = list(LoanGuarantor.objects.filter(loan=loan, status="accepted"))
    total_pledged = sum(g.pledged_amount for g in guarantors)

    if loan.balance <= 0 or loan.status == "repaid":
        # Fully released — loan is settled
        for g in guarantors:
            g.locked_amount = Decimal("0")
            g.save()

        # Discharge assets
        for asset in loan.asset_collaterals.filter(status="active"):
            asset.status = "discharged"
            asset.save()
        return

    # The portion of the loan that needs guarantor backing
    guarantor_portion_needed = max(loan.balance - own_lock, Decimal("0"))

    if hierarchy == "guarantor_first":
        # Release guarantors first — reduce their locks before touching borrower's
        # Allocate guarantor_portion_needed across guarantors proportionally
        if total_pledged > 0:
            remaining_to_lock = guarantor_portion_needed
            for g in guarantors:
                ratio = g.pledged_amount / total_pledged
                target_lock = min(
                    (guarantor_portion_needed * ratio).quantize(Decimal("0.01")),
                    g.pledged_amount,
                )
                g.locked_amount = target_lock
                g.save()

    elif hierarchy == "proportional":
        # Release everyone proportionally based on loan balance vs original amount
        original_total = loan.amount + (loan.amount * loan.interest / Decimal("100"))
        if original_total > 0:
            release_ratio = max(Decimal("0"), Decimal("1") - (loan.balance / original_total))
            for g in guarantors:
                g.locked_amount = (g.pledged_amount * (Decimal("1") - release_ratio)).quantize(Decimal("0.01"))
                g.save()

    elif hierarchy == "borrower_first":
        # Keep guarantors locked until borrower's own lock is fully released
        # Only release guarantors when own_lock reaches 0
        if own_lock == 0 and guarantor_portion_needed > 0:
            # Now start releasing guarantors
            if total_pledged > 0:
                for g in guarantors:
                    ratio = g.pledged_amount / total_pledged
                    g.locked_amount = min(
                        (guarantor_portion_needed * ratio).quantize(Decimal("0.01")),
                        g.pledged_amount,
                    )
                    g.save()
        else:
            # Keep guarantors fully locked
            for g in guarantors:
                g.locked_amount = g.pledged_amount
                g.save()


# ─────────────────────────────────────────────────────────────────────────────
# Disbursement gate — verify all collateral before money goes out
# ─────────────────────────────────────────────────────────────────────────────

def check_disbursement_gate(loan: Loan) -> tuple[bool, str]:
    """
    Returns (can_disburse, reason).
    For internal collateral: checks guarantor coverage.
    For external collateral: checks legal charge status.
    """
    if loan.collateral_type in ("external", "mixed"):
        # Check asset collateral
        assets = loan.asset_collaterals.all()
        if not assets.exists():
            return False, "No tangible asset collateral registered for this loan."

        for asset in assets:
            if asset.status not in ("legal_charge_registered", "active"):
                return False, (
                    f"Asset '{asset.get_asset_type_display()}' is not legally charged. "
                    f"Current status: {asset.get_status_display()}. "
                    f"Disbursement blocked until legal charge is registered."
                )

        # Check LTV
        total_asset_cap = sum(a.max_loan_cap for a in assets)
        if loan.amount > total_asset_cap:
            return False, (
                f"Loan amount KES {loan.amount:,.2f} exceeds the maximum loan cap "
                f"of KES {total_asset_cap:,.2f} (based on Forced Sale Value × LTV)."
            )

    if loan.collateral_type in ("internal", "mixed"):
        # Check guarantor coverage for the gap beyond savings
        settings = SACCOSettings.get_settings()
        retention_pct = settings.min_savings_retention / Decimal("100")
        own_coverage = min(loan.total_savings_at_application, loan.amount)
        gap = loan.amount - own_coverage

        if gap > 0:
            accepted_guarantors = loan.guarantors.filter(status="accepted")
            total_guaranteed = sum(g.pledged_amount for g in accepted_guarantors)

            if total_guaranteed < gap:
                return False, (
                    f"Insufficient guarantor coverage. "
                    f"Gap beyond own savings: KES {gap:,.2f}. "
                    f"Guarantor pledges: KES {total_guaranteed:,.2f}. "
                    f"Shortfall: KES {gap - total_guaranteed:,.2f}."
                )

    return True, "All collateral checks passed."
