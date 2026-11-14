"""Pricing and repayment estimates for the configured savings-tier loan."""
from decimal import Decimal, ROUND_HALF_UP

from core.eligibility import INTEREST_RATES, VALID_PERIODS


PRODUCT = "savings_tier"
PRODUCT_NAME = "Savings-tier loan"
MINIMUM_AMOUNT = Decimal("1.00")
MAXIMUM_BALANCE = Decimal("9999999999.99")
CENT = Decimal("0.01")


class LoanCalculationError(ValueError):
    pass


def calculate_flat_term(amount, months, rate):
    if months < 1:
        raise LoanCalculationError("A valid repayment period is required.")
    total_interest = (amount * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    # This product's existing approval flow charges no fees.
    fees = Decimal("0.00")
    total = amount + total_interest + fees
    schedule = []
    previous_principal = previous_interest = Decimal("0.00")
    for month in range(1, months + 1):
        principal_to_date = (amount * month / months).quantize(CENT, rounding=ROUND_HALF_UP)
        interest_to_date = (total_interest * month / months).quantize(CENT, rounding=ROUND_HALF_UP)
        principal = principal_to_date - previous_principal
        interest = interest_to_date - previous_interest
        schedule.append({
            "month": month, "principal": principal, "interest": interest,
            "payment": principal + interest, "remaining": total - principal_to_date - interest_to_date,
        })
        previous_principal, previous_interest = principal_to_date, interest_to_date
    return {
        "amount": amount, "repayment_months": months, "interest_rate": rate,
        "interest_method": "flat_term", "fees": fees, "total_interest": total_interest,
        "total_repayment": total, "estimated_installment": schedule[0]["payment"],
        "schedule": schedule,
    }


def quote_savings_loan(product, amount, months, band):
    if product != PRODUCT:
        raise LoanCalculationError("Choose an available loan product.")
    if months not in VALID_PERIODS:
        raise LoanCalculationError(f"Repayment period must be one of: {VALID_PERIODS}.")
    rate = INTEREST_RATES[months].get(band)
    if rate is None:
        raise LoanCalculationError("An applicable rate is unavailable until a savings tier is established.")
    quote = calculate_flat_term(amount, months, rate)
    if quote["total_repayment"] > MAXIMUM_BALANCE:
        raise LoanCalculationError("The total repayment exceeds the supported amount. Enter a lower principal.")
    return {"product": PRODUCT, "product_name": PRODUCT_NAME, **quote}


def serialize_quote(quote):
    return {
        **{key: str(value) if isinstance(value, Decimal) else value for key, value in quote.items()},
        "schedule": [
            {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
            for row in quote["schedule"]
        ],
    }
