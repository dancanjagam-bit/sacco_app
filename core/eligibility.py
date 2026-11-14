"""
SACCO Loan Eligibility Engine
==============================
Rules:
  1. Member must have at least MIN_SAVING_MONTHS distinct calendar months
     of savings in the last LOOKBACK_MONTHS months.
  2. Each qualifying month must have at least MIN_MONTHLY_AMOUNT deposited.
  3. Loan multiplier scales with the number of consistent months:
       < 6  months  →  not eligible
       6–8  months  →  3× savings, interest band A
       9–11 months  →  4× savings, interest band B
       12+  months  →  5× savings, interest band C (best rates)
  4. Interest rates per repayment period also depend on the tier.
"""

from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from django.db.models import Sum
from .models import Savings


# ── Configuration ─────────────────────────────────────────────────────────────
MIN_SAVING_MONTHS  = 6          # minimum consecutive/consistent months to qualify
LOOKBACK_MONTHS    = 13         # how far back we look (slightly more than 1 year)
MIN_MONTHLY_AMOUNT = Decimal("500.00")   # minimum deposit per qualifying month


# ── Multiplier tiers ──────────────────────────────────────────────────────────
TIERS = [
    # (min_months, label,        multiplier, interest_band)
    (12, "Gold (12+ months)",   Decimal("5"), "C"),
    (9,  "Silver (9–11 months)",Decimal("4"), "B"),
    (6,  "Bronze (6–8 months)", Decimal("3"), "A"),
]

# ── Interest rates per band per repayment period ──────────────────────────────
INTEREST_RATES = {
    #  months:  {band A, band B, band C}
    3:  {"A": Decimal("5.00"), "B": Decimal("4.50"), "C": Decimal("4.00")},
    6:  {"A": Decimal("7.00"), "B": Decimal("6.50"), "C": Decimal("6.00")},
    12: {"A": Decimal("10.00"),"B": Decimal("9.00"), "C": Decimal("8.00")},
    18: {"A": Decimal("12.00"),"B": Decimal("11.00"),"C": Decimal("10.00")},
    24: {"A": Decimal("15.00"),"B": Decimal("13.00"),"C": Decimal("12.00")},
    36: {"A": Decimal("18.00"),"B": Decimal("16.00"),"C": Decimal("14.00")},
}
VALID_PERIODS = sorted(INTEREST_RATES.keys())


def get_consistent_months(user) -> list[dict]:
    """
    Return a list of qualifying months for this user.
    Each entry: { 'month': 'Jan 2026', 'total': Decimal, 'qualifies': bool }
    Covers the last LOOKBACK_MONTHS calendar months (excluding the current month).
    """
    today       = date.today()
    # Start from LOOKBACK_MONTHS months ago, beginning of that month
    start_date  = (today - relativedelta(months=LOOKBACK_MONTHS)).replace(day=1)

    # Aggregate deposits per calendar month
    from django.db.models.functions import TruncMonth
    monthly_qs = (
        Savings.objects.filter(user=user, created_at__date__gte=start_date)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    totals_by_month = {
        entry["month"].date().replace(day=1): entry["total"]
        for entry in monthly_qs
    }

    months = []
    cursor = start_date
    # Walk each calendar month up to (but not including) the current month
    current_month_start = today.replace(day=1)
    while cursor < current_month_start:
        total     = totals_by_month.get(cursor, Decimal("0"))
        qualifies = total >= MIN_MONTHLY_AMOUNT
        months.append({
            "month":     cursor.strftime("%b %Y"),
            "month_date": cursor,
            "total":     total,
            "qualifies": qualifies,
        })
        cursor = (cursor + relativedelta(months=1)).replace(day=1)

    return months


def get_eligibility(user) -> dict:
    """
    Full eligibility report for a user.
    Returns a dict with:
      eligible         bool
      consistent_months int  (number of qualifying months in lookback window)
      tier_label       str
      multiplier       Decimal
      interest_band    str ("A"/"B"/"C" or None)
      max_loan         Decimal
      total_savings    Decimal
      months_detail    list[dict]
      months_needed    int  (how many more months needed to qualify)
      next_tier_months int  (months needed to reach next tier)
      rejection_reason str  (if not eligible)
    """
    months_detail  = get_consistent_months(user)
    qualifying     = [m for m in months_detail if m["qualifies"]]
    consistent_count = len(qualifying)

    # BOSA balance is the multiplier base (core shares only)
    bosa_balance = (
        Savings.objects.filter(user=user, account_type="bosa")
        .aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )
    # Total savings for context display
    total_savings = (
        Savings.objects.filter(user=user)
        .aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )

    # Determine tier
    tier_label    = None
    multiplier    = Decimal("0")
    interest_band = None
    for min_m, label, mult, band in TIERS:
        if consistent_count >= min_m:
            tier_label    = label
            multiplier    = mult
            interest_band = band
            break

    eligible = multiplier > 0
    max_loan = bosa_balance * multiplier

    months_needed = max(0, MIN_SAVING_MONTHS - consistent_count)

    # Next tier
    next_tier_months = 0
    current_min = next(
        (min_m for min_m, *_ in TIERS if consistent_count >= min_m),
        0
    )
    higher_tiers = [(m, *r) for m, *r in TIERS if m > current_min]
    if higher_tiers:
        next_tier_months = higher_tiers[-1][0] - consistent_count

    rejection_reason = ""
    if not eligible:
        if bosa_balance <= 0:
            rejection_reason = "You have no BOSA (core share) savings on record. Loan eligibility is based on BOSA savings only."
        else:
            rejection_reason = (
                f"You need at least {MIN_SAVING_MONTHS} months of consistent BOSA savings "
                f"(minimum KES {MIN_MONTHLY_AMOUNT:,.0f}/month). "
                f"You currently have {consistent_count} qualifying month(s). "
                f"Save for {months_needed} more month(s) to become eligible."
            )

    return {
        "eligible":          eligible,
        "consistent_months": consistent_count,
        "tier_label":        tier_label,
        "multiplier":        multiplier,
        "interest_band":     interest_band,
        "max_loan":          max_loan,
        "total_savings":     total_savings,
        "bosa_balance":      bosa_balance,
        "months_detail":     months_detail,
        "months_needed":     months_needed,
        "next_tier_months":  next_tier_months,
        "rejection_reason":  rejection_reason,
        "min_monthly_amount": MIN_MONTHLY_AMOUNT,
        "interest_rates":    {
            str(k): {
                band: float(rate)
                for band, rate in v.items()
            }
            for k, v in INTEREST_RATES.items()
        },
    }


def get_interest_rate(repayment_months: int, interest_band: str) -> Decimal:
    rates = INTEREST_RATES.get(repayment_months)
    if not rates:
        # Default to nearest valid period
        nearest = min(VALID_PERIODS, key=lambda p: abs(p - repayment_months))
        rates = INTEREST_RATES[nearest]
    return rates.get(interest_band, Decimal("10.00"))
