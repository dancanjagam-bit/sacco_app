from django.conf import settings
from django.db import models
from django.utils import timezone
from decimal import Decimal

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# 💰 Savings
# ─────────────────────────────────────────────────────────────────────────────
class Savings(models.Model):
    ACCOUNT_TYPES = [
        ("bosa", "BOSA — Non-Withdrawable (Core Shares)"),
        ("fosa", "FOSA — Withdrawable Savings"),
    ]

    user         = models.ForeignKey(User, on_delete=models.CASCADE)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPES, default="fosa")
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# 🏦 Loan
# ─────────────────────────────────────────────────────────────────────────────
class Loan(models.Model):
    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("repaid",   "Repaid"),
    ]

    PURPOSE_CHOICES = [
        ("business",   "Business / Investment"),
        ("education",  "Education"),
        ("medical",    "Medical / Emergency"),
        ("asset",      "Asset Purchase"),
        ("housing",    "Housing / Construction"),
        ("farming",    "Farming / Agriculture"),
        ("personal",   "Personal Use"),
        ("other",      "Other"),
    ]

    COLLATERAL_TYPE_CHOICES = [
        ("internal", "Internal (Savings + Guarantors)"),
        ("external", "External (Tangible Asset)"),
        ("mixed",    "Mixed (Savings + Asset)"),
    ]

    user              = models.ForeignKey(User, on_delete=models.CASCADE, related_name="loans")
    amount            = models.DecimalField(max_digits=12, decimal_places=2)
    purpose           = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default="personal")
    purpose_details   = models.TextField(blank=True, default="")

    interest          = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    repayment_months  = models.PositiveIntegerField(default=12)
    balance           = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    remarks           = models.TextField(blank=True, default="")

    # Collateral classification
    collateral_type   = models.CharField(max_length=20, choices=COLLATERAL_TYPE_CHOICES, default="internal")

    # Snapshot of eligibility at time of application
    savings_months    = models.PositiveIntegerField(default=0)
    total_savings_at_application = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    approved_by       = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="approved_loans",
    )
    approved_at       = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# 💳 Transactions (Ledger)
# ─────────────────────────────────────────────────────────────────────────────
class Transaction(models.Model):
    TYPE_CHOICES = [
        ("deposit",   "Deposit"),
        ("repayment", "Repayment"),
        ("loan",      "Loan Disbursement"),
        ("withdrawal","Withdrawal"),
        ("dividend",  "Dividend Payout"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    type       = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    note       = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# 🤝 Loan Guarantor — with pledged amount tracking
# ─────────────────────────────────────────────────────────────────────────────
class LoanGuarantor(models.Model):
    STATUS_CHOICES = [
        ("pending",  "Pending Response"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]

    loan           = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="guarantors")
    guarantor      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guaranteeing")
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    message        = models.TextField(blank=True, default="")

    # The amount this guarantor is pledging as collateral
    pledged_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # The current locked portion (reduces as loan is repaid)
    locked_amount  = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    responded_at   = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("loan", "guarantor")
        ordering        = ["-created_at"]

    def __str__(self):
        return f"Guarantor {self.guarantor.username} for Loan #{self.loan_id} — KES {self.pledged_amount} ({self.status})"

    @property
    def released_amount(self):
        return self.pledged_amount - self.locked_amount


# ─────────────────────────────────────────────────────────────────────────────
# 🏠 Tangible Asset Collateral (Title Deeds, Logbooks, etc.)
# ─────────────────────────────────────────────────────────────────────────────
class AssetCollateral(models.Model):
    ASSET_TYPE_CHOICES = [
        ("title_deed",     "Title Deed (Land)"),
        ("logbook",        "Motor Vehicle Logbook"),
        ("equipment",      "Equipment / Machinery"),
        ("shares",         "Share Certificate"),
        ("fixed_deposit",  "Fixed Deposit"),
        ("other",          "Other Tangible Asset"),
    ]

    STATUS_CHOICES = [
        ("pending_valuation",   "Pending Valuation"),
        ("valued",              "Valued — Awaiting Legal Charge"),
        ("legal_charge_registered", "Legal Charge Registered"),
        ("active",              "Active (Loan Disbursed)"),
        ("discharged",          "Discharged (Loan Settled)"),
        ("rejected",            "Rejected"),
    ]

    loan            = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="asset_collaterals", null=True, blank=True)
    user             = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assets")
    asset_type       = models.CharField(max_length=30, choices=ASSET_TYPE_CHOICES)
    description      = models.CharField(max_length=200, blank=True, default="")

    # Valuation
    forced_sale_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    max_loan_cap      = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                            help_text="Forced Sale Value × LTV ratio (typically 80%)")
    ltv_ratio         = models.DecimalField(max_digits=5, decimal_places=2, default=80,
                                            help_text="Loan-to-Value ratio (%)")

    # Legal / registration
    status            = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending_valuation")
    registration_ref  = models.CharField(max_length=100, blank=True, default="",
                                         help_text="Charge registration reference (e.g., lands office / NTSA)")
    valuation_date    = models.DateField(null=True, blank=True)
    valuer_name       = models.CharField(max_length=100, blank=True, default="")
    discharge_ref     = models.CharField(max_length=100, blank=True, default="",
                                         help_text="Discharge reference when loan is settled")

    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_asset_type_display()} — {self.user.username} ({self.status})"

    def save(self, *args, **kwargs):
        # Auto-calculate max loan cap
        if self.forced_sale_value and self.ltv_ratio:
            self.max_loan_cap = (self.forced_sale_value * self.ltv_ratio / Decimal("100")).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# ⚙️ SACCO System Settings (admin-configurable)
# ─────────────────────────────────────────────────────────────────────────────
class SACCOSettings(models.Model):
    RELEASE_HIERARCHY_CHOICES = [
        ("guarantor_first", "Release Guarantor Pledges First"),
        ("proportional",    "Release Proportionally (Savings + Guarantors)"),
        ("borrower_first",   "Release Borrower's Own Lock First"),
    ]

    # Singleton — there should only be one row
    name = models.CharField(max_length=50, default="default", unique=True)

    # Collateral release hierarchy
    release_hierarchy = models.CharField(max_length=30, choices=RELEASE_HIERARCHY_CHOICES, default="guarantor_first")

    # LTV ratio for asset-backed loans
    default_ltv_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=80)

    # Minimum savings retention when member has a loan (as fraction, e.g., 0.33 = ⅓)
    min_savings_retention = models.DecimalField(max_digits=5, decimal_places=2, default=33,
                                                help_text="Minimum % of savings that stays locked during active loan")

    # SASRA reporting
    sasra_enabled = models.BooleanField(default=True, help_text="Enable SASRA compliance logging")
    sasra_report_interval_days = models.PositiveIntegerField(default=90, help_text="How often to generate SASRA reports")

    # BOSA mandatory contribution
    mandatory_monthly_bosa = models.DecimalField(
        max_digits=10, decimal_places=2, default=1000,
        help_text="Mandatory minimum monthly BOSA contribution (KES)",
    )
    bosa_exit_hold_days = models.PositiveIntegerField(
        default=60, help_text="Days the SACCO holds BOSA funds after exit approval before release",
    )

    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(name="default")
        return obj

    def __str__(self):
        return f"SACCO Settings ({self.release_hierarchy})"


# ─────────────────────────────────────────────────────────────────────────────
# 💹 Savings Dividend
# ─────────────────────────────────────────────────────────────────────────────
class SavingsDividend(models.Model):
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dividends")
    year          = models.PositiveIntegerField()
    rate          = models.DecimalField(max_digits=5, decimal_places=2,
                                        help_text="Annual interest rate applied (%)")
    savings_balance = models.DecimalField(max_digits=12, decimal_places=2,
                                          help_text="Balance at time of calculation")
    amount        = models.DecimalField(max_digits=12, decimal_places=2,
                                        help_text="Dividend paid out")
    paid_at       = models.DateTimeField(auto_now_add=True)
    note          = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("user", "year")
        ordering        = ["-year"]

    def __str__(self):
        return f"{self.user.username} — {self.year} dividend: KES {self.amount}"


# ─────────────────────────────────────────────────────────────────────────────
# 📋 SASRA Compliance Report
# ─────────────────────────────────────────────────────────────────────────────
class SASRAReport(models.Model):
    REPORT_TYPES = [
        ("quarterly",  "Quarterly Report"),
        ("annual",     "Annual Report"),
        ("monthly",    "Monthly Report"),
        ("special",    "Special Report"),
    ]

    STATUS_CHOICES = [
        ("draft",     "Draft"),
        ("generated",  "Generated"),
        ("submitted", "Submitted"),
    ]

    report_type   = models.CharField(max_length=20, choices=REPORT_TYPES)
    period_start  = models.DateField()
    period_end    = models.DateField()
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    data_snapshot = models.JSONField(default=dict, blank=True)
    generated_by  = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at    = models.DateTimeField(auto_now_add=True)
    submitted_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SASRA {self.report_type} — {self.period_start} to {self.period_end} ({self.status})"


# ─────────────────────────────────────────────────────────────────────────────
# 🚪 SACCO Exit Request (for BOSA withdrawal)
# ─────────────────────────────────────────────────────────────────────────────
class ExitRequest(models.Model):
    STATUS_CHOICES = [
        ("pending",         "Pending Review"),
        ("approved",        "Approved — In Holding Period"),
        ("funds_released",  "Funds Released"),
        ("rejected",        "Rejected"),
        ("cancelled",       "Cancelled by Member"),
    ]

    user             = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exit_requests")
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reason           = models.TextField(blank=True, default="")
    bosa_balance     = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="BOSA balance at time of request")

    # Collateral checks at time of request
    has_active_loan  = models.BooleanField(default=False)
    has_guarantor_pledges = models.BooleanField(default=False)

    # Admin review
    reviewed_by       = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_exits")
    reviewed_at       = models.DateTimeField(null=True, blank=True)
    review_notes      = models.TextField(blank=True, default="")
    rejection_reason  = models.TextField(blank=True, default="")

    # Holding period
    approved_at       = models.DateTimeField(null=True, blank=True)
    release_date      = models.DateField(null=True, blank=True,
                                          help_text="Date when funds can be released (approved + holding period)")
    released_at       = models.DateTimeField(null=True, blank=True)

    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Exit request — {self.user.username} ({self.status})"

    @property
    def is_holding_period_over(self):
        if self.status != "approved" or not self.release_date:
            return False
        from datetime import date
        return date.today() >= self.release_date


# ─────────────────────────────────────────────────────────────────────────────
# 🔍 Financial Audit Finding
# ─────────────────────────────────────────────────────────────────────────────
class AuditFinding(models.Model):
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("high",     "High"),
        ("medium",   "Medium"),
        ("low",      "Low"),
        ("info",     "Info"),
    ]
    STATUS_CHOICES = [
        ("open",      "Open"),
        ("reviewing", "Under Review"),
        ("resolved",  "Resolved"),
        ("dismissed", "Dismissed"),
    ]

    rule          = models.CharField(max_length=50, help_text="Audit rule that triggered this finding")
    severity      = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="medium")
    title         = models.CharField(max_length=200)
    description   = models.TextField()
    entity_type   = models.CharField(max_length=30, blank=True, default="")
    entity_id     = models.IntegerField(null=True, blank=True)
    user          = models.CharField(max_length=150, blank=True, default="")

    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    reviewed_by   = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_findings",
    )
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    review_notes  = models.TextField(blank=True, default="")
    resolution     = models.TextField(blank=True, default="", help_text="How the finding was resolved")

    # Batch tracking — which audit run discovered this
    audit_run_id  = models.CharField(max_length=50, blank=True, default="")
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"
