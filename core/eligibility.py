"""Loan eligibility from the currently approved, versioned database policy."""
from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from .models import Savings, LoanAssessmentPolicy


def get_active_policy():
    return LoanAssessmentPolicy.objects.filter(active=True, approved_at__isnull=False).order_by("-approved_at").first()


def get_valid_periods():
    policy=get_active_policy()
    return sorted(int(period) for period in (policy.rules.get("interest_rates",{}) if policy else {}))


def get_consistent_months(user, policy=None):
    policy=policy or get_active_policy()
    if not policy:return []
    lookback=int(policy.rules["lookback_months"])
    minimum=Decimal(str(policy.rules["min_monthly_amount"]))
    today=timezone.localdate()
    start=(today-relativedelta(months=lookback)).replace(day=1)
    monthly=(Savings.objects.filter(user=user,account_type="bosa",created_at__date__gte=start)
        .annotate(month=TruncMonth("created_at")).values("month").annotate(total=Sum("amount")).order_by("month"))
    totals={item["month"].date().replace(day=1):item["total"] for item in monthly}
    months=[]; cursor=start; current=today.replace(day=1)
    while cursor<current:
        total=totals.get(cursor,Decimal("0"))
        months.append({"month":cursor.strftime("%b %Y"),"month_date":cursor,"total":total,"qualifies":total>=minimum})
        cursor=(cursor+relativedelta(months=1)).replace(day=1)
    return months


def get_eligibility(user):
    policy=get_active_policy()
    savings_total= Savings.objects.filter(user=user).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    bosa= Savings.objects.filter(user=user,account_type="bosa").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    if not policy:
        return {"eligible":False,"consistent_months":0,"tier_label":None,"multiplier":Decimal("0"),
            "interest_band":None,"max_loan":Decimal("0"),"total_savings":savings_total,"bosa_balance":bosa,
            "months_detail":[],"months_needed":0,"next_tier_months":0,"rejection_reason":"No active approved loan policy is configured.",
            "policy_version":None,"interest_rates":{},"min_monthly_amount":None}
    rules=policy.rules
    details=get_consistent_months(user,policy)
    count=sum(1 for month in details if month["qualifies"])
    tiers=sorted(rules.get("tiers",[]),key=lambda item:int(item["min_months"]),reverse=True)
    selected=next((tier for tier in tiers if count>=int(tier["min_months"])),None)
    multiplier=Decimal(str(selected["multiplier"])) if selected else Decimal("0")
    band=selected.get("interest_band") if selected else None
    rates={str(k):{str(key):float(value) for key,value in v.items()} for k,v in rules.get("interest_rates",{}).items()}
    minimum=int(rules["min_saving_months"])
    needed=max(0,minimum-count)
    eligible=bool(selected and bosa>0)
    reason=""
    if not eligible:
        reason=("No BOSA savings are recorded." if bosa<=0 else
            f"You need at least {minimum} qualifying BOSA savings months; {count} currently qualify.")
    current_min=max((int(t["min_months"]) for t in tiers if count>=int(t["min_months"])),default=0)
    next_tier=min((int(t["min_months"]) for t in tiers if int(t["min_months"])>current_min),default=current_min)
    return {"eligible":eligible,"consistent_months":count,"tier_label":selected.get("label") if selected else None,
        "multiplier":multiplier,"interest_band":band,"max_loan":bosa*multiplier,"total_savings":savings_total,
        "bosa_balance":bosa,"months_detail":[{"month":m["month"],"total":float(m["total"]),"qualifies":m["qualifies"]} for m in details],
        "months_needed":needed,"next_tier_months":max(0,next_tier-count),"rejection_reason":reason,
        "min_monthly_amount":Decimal(str(rules["min_monthly_amount"])),"interest_rates":rates,"policy_version":policy.version}


def get_interest_rate(repayment_months, interest_band):
    policy=get_active_policy()
    if not policy:return None
    value=policy.rules.get("interest_rates",{}).get(str(repayment_months),{}).get(str(interest_band))
    return Decimal(str(value)) if value is not None else None
