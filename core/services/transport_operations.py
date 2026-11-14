"""Transport calculations shared by operational API handlers."""
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q, Sum

from core.transport_models import TransportDeductionRule, TransportExpense, TransportShift


@dataclass(frozen=True)
class ShiftClosureAmounts:
    reported_gross: Decimal
    approved_expenses: Decimal
    deductible_expenses: Decimal
    expected_remittance: Decimal | None
    rule_version: str
    status: str
    note: str


def calculate_shift_closure(shift: TransportShift) -> ShiftClosureAmounts:
    """Calculate a shift close without inventing a deduction policy.

    Expense approval is an operational review. Only categories named by an
    active, approved, versioned rule reduce the expected remittance.
    """
    gross = shift.collections.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    approved = shift.expenses.filter(status="approved")
    approved_total = approved.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    rule = TransportDeductionRule.objects.filter(
        scope="shift_deduction", active=True, approved_by__isnull=False,
        approved_at__isnull=False,
    ).exclude(approval_reference="").order_by("-approved_at").first()
    if not rule:
        return ShiftClosureAmounts(
            gross, approved_total, Decimal("0.00"), None, "", "rule_required",
            "No approved shift deduction rule is configured; expected remittance cannot be calculated.",
        )

    categories = [str(value).strip() for value in (rule.deductible_categories or []) if str(value).strip()]
    deductible = Decimal("0.00")
    if categories:
        deductible = approved.filter(category__in=categories).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if deductible > gross:
        return ShiftClosureAmounts(
            gross, approved_total, deductible, None, rule.version, "review_required",
            "Approved deductible expenses exceed reported collections; staff review is required.",
        )
    return ShiftClosureAmounts(
        gross, approved_total, deductible, gross - deductible, rule.version, "calculated",
        "Expected remittance uses the active approved deduction rule.",
    )
