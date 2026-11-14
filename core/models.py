from django.conf import settings
from django.db import models
from django.utils import timezone
from decimal import Decimal
import uuid

# Transport records are separated from this financial ledger module only for
# maintainability; importing them here makes Django discover their migrations.
from .transport_models import (TransportRole, TransportRoleGrant, TransportRoute, Vehicle,
    VehicleOwnership, CrewAssignment, TransportShift, TransportCollection, TransportRemittance,
    TransportPayment, TransportAllocationRule, TransportPaymentAllocation,
    TransportAssignmentIssue, TransportDeductionRule, TransportExpense,
    TransportShiftClosure, TransportPaymentReviewEvent)

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
        ("flagged",  "Flagged for CRB Review"),
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
    credit_report_authorized = models.BooleanField(default=False)
    credit_report_authorized_at = models.DateTimeField(null=True, blank=True)

    approved_by       = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="approved_loans",
    )
    approved_at       = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class LoanAssessmentPolicy(models.Model):
    version=models.CharField(max_length=60,unique=True)
    rules=models.JSONField(default=dict)
    active=models.BooleanField(default=False)
    created_by=models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL,related_name="created_loan_assessment_policies")
    approved_by=models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL,related_name="approved_loan_assessment_policies")
    approved_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-created_at"]


class LoanAssessment(models.Model):
    loan=models.ForeignKey(Loan,on_delete=models.PROTECT,related_name="assessments")
    policy=models.ForeignKey(LoanAssessmentPolicy,null=True,blank=True,on_delete=models.PROTECT,related_name="assessments")
    policy_version=models.CharField(max_length=60)
    inputs=models.JSONField(default=dict)
    reasons=models.JSONField(default=list)
    outcome=models.CharField(max_length=24,default="submitted_for_review")
    decision_maker=models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL,related_name="loan_assessment_decisions")
    decision_at=models.DateTimeField(null=True,blank=True)
    decision_reason=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-created_at"]


# ─────────────────────────────────────────────────────────────────────────────
# 💳 Transactions (Ledger)
# ─────────────────────────────────────────────────────────────────────────────
class Transaction(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ("bosa", "BOSA savings"),
        ("fosa", "FOSA savings"),
        ("loan", "Loan account"),
        ("other", "Other account activity"),
    ]
    TYPE_CHOICES = [
        ("deposit",   "Deposit"),
        ("repayment", "Repayment"),
        ("loan",      "Loan Disbursement"),
        ("withdrawal","Withdrawal"),
        ("dividend",  "Dividend Payout"),
        ("adjustment", "Audited Adjustment"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    type       = models.CharField(max_length=20, choices=TYPE_CHOICES)
    # Blank is retained for legacy entries whose account cannot be attributed
    # safely from an authoritative payment/account link.
    account_type = models.CharField(max_length=16, choices=ACCOUNT_TYPE_CHOICES, blank=True, default="")
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    note       = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    reverses   = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="reversal_entry",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=("user", "account_type", "created_at"), name="txn_user_account_date_idx")]


class FosaWithdrawal(models.Model):
    """A payout request and reservation; this is not itself a ledger debit."""
    DESTINATION_CHOICES = [("mpesa", "M-Pesa")]
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("pending", "Pending provider confirmation"),
        ("uncertain", "Needs provider investigation"),
        ("succeeded", "Paid"),
        ("failed", "Definitively failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client_request_id = models.UUIDField()
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="fosa_withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    destination_type = models.CharField(max_length=16, choices=DESTINATION_CHOICES)
    destination_phone = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="requested")
    provider_reference = models.CharField(max_length=100, null=True, blank=True, unique=True)
    provider_transaction_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    failure_reason_code = models.CharField(max_length=40, blank=True, default="")
    ledger_transaction = models.OneToOneField(
        Transaction, null=True, blank=True, on_delete=models.PROTECT,
        related_name="fosa_withdrawal",
    )
    savings_entry = models.OneToOneField(
        Savings, null=True, blank=True, on_delete=models.PROTECT,
        related_name="fosa_withdrawal",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "client_request_id"),
                name="uniq_fosa_withdrawal_user_request",
            ),
        ]


class WithdrawalCorrectionProposal(models.Model):
    """A staff-reviewed reversal proposal for a verified failed legacy payout."""
    STATUS_CHOICES = [
        ("proposed", "Awaiting approval"),
        ("approved", "Approved and posted"),
        ("rejected", "Rejected"),
    ]
    original_transaction = models.ForeignKey(
        Transaction, on_delete=models.PROTECT, related_name="withdrawal_corrections",
    )
    original_savings = models.ForeignKey(
        Savings, on_delete=models.PROTECT, related_name="withdrawal_corrections",
    )
    reason = models.TextField()
    evidence_reference = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="proposed")
    proposed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="proposed_withdrawal_corrections",
    )
    decided_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT,
        related_name="decided_withdrawal_corrections",
    )
    correction_transaction = models.OneToOneField(
        Transaction, null=True, blank=True, on_delete=models.PROTECT,
        related_name="withdrawal_correction",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("original_transaction",),
                condition=models.Q(status__in=("proposed", "approved")),
                name="uniq_active_withdrawal_correction",
            ),
        ]


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


# ─────────────────────────────────────────────────────────────────────────────
# 🔎 CRB Check — Credit Reference Bureau result per loan application
# ─────────────────────────────────────────────────────────────────────────────
class CRBCheck(models.Model):
    PROVIDER_CHOICES = [
        ("transunion", "TransUnion Kenya"),
        ("metropol",   "Metropol"),
        ("stub",       "Stub"),
    ]
    STATUS_CHOICES = [
        ("pending",        "Pending"),
        ("clear",          "Clear"),
        ("flagged",        "Flagged"),
        ("error",          "Error"),
        ("not_configured", "Not Configured"),
        ("not_authorized", "Not Authorized"),
        ("needs_review", "Needs Review"),
        ("disputed", "Disputed"),
    ]

    loan              = models.OneToOneField(
        Loan, on_delete=models.CASCADE, related_name="crb_check",
    )
    member            = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="crb_checks",
    )
    provider          = models.CharField(
        max_length=20, choices=PROVIDER_CHOICES, blank=True, default="",
    )
    status            = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending",
    )
    score             = models.IntegerField(null=True, blank=True)
    active_loans_count = models.IntegerField(null=True, blank=True, default=None)
    request_reference = models.CharField(max_length=120, blank=True)
    report_date = models.DateField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    external_obligations = models.JSONField(null=True, blank=True, default=None)
    repayment_default_information = models.JSONField(null=True, blank=True, default=None)
    missing_data = models.JSONField(default=list, blank=True)
    coverage_limitations = models.TextField(blank=True)
    raw_response      = models.JSONField(default=dict, blank=True)
    checked_at        = models.DateTimeField(auto_now_add=True)

    # Officer override fields
    override_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crb_overrides",
    )
    override_at       = models.DateTimeField(null=True, blank=True)
    override_notes    = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self):
        return f"CRBCheck — Loan #{self.loan_id} ({self.provider or 'n/a'}) → {self.status}"


# ─────────────────────────────────────────────────────────────────────────────
# 📲 M-Pesa / Daraja STK Push Transaction
# Tracks every payment initiated via Lipa Na M-Pesa Online (STK push).
# One row per STK push attempt; the callback view updates it when Daraja
# posts back the result.
# ─────────────────────────────────────────────────────────────────────────────
class MpesaTransaction(models.Model):
    PAYMENT_TYPE_CHOICES = [
        ("registration", "Registration Fee"),
        ("deposit",      "Savings Deposit"),
        ("repayment",    "Loan Repayment"),
        ("fee",          "Other Fee"),
        ("transport_remittance", "Transport Remittance"),
    ]

    STATUS_CHOICES = [
        ("pending",   "Pending — waiting for member to enter PIN"),
        ("confirmed", "Confirmed — payment received"),
        ("failed",    "Failed — member cancelled or timeout"),
        ("cancelled", "Cancelled by member"),
    ]

    # Who is paying
    user         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mpesa_transactions",
    )
    phone        = models.CharField(
        max_length=15,
        help_text="Phone number used for payment in 254XXXXXXXXX format",
    )

    # Payment details
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)

    # Daraja request tracking
    checkout_request_id  = models.CharField(
        max_length=100, unique=True,
        help_text="Daraja CheckoutRequestID — used to match the callback",
    )
    merchant_request_id  = models.CharField(max_length=100, blank=True, default="")

    # Daraja callback result
    status               = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")
    mpesa_receipt        = models.CharField(
        max_length=20, blank=True, default="",
        help_text="M-Pesa receipt code e.g. QJL7XXXXXX",
    )
    result_code          = models.IntegerField(null=True, blank=True)
    result_desc          = models.TextField(blank=True, default="")

    # Optional link to the core Transaction record created on confirmation
    transaction          = models.OneToOneField(
        Transaction,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="mpesa_payment",
        help_text="Core ledger Transaction created when this payment confirmed",
    )

    # Optional loan link (set when payment_type='repayment')
    loan                 = models.ForeignKey(
        Loan,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="mpesa_repayments",
    )

    transport_remittance = models.ForeignKey(
        "core.TransportRemittance", null=True, blank=True, on_delete=models.PROTECT,
        related_name="mpesa_transactions",
    )

    # Optional savings account type (set when payment_type='deposit')
    account_type         = models.CharField(
        max_length=10, blank=True, default="",
        help_text="'bosa' or 'fosa' — only relevant for deposit payments",
    )

    # Raw Daraja callback payload for audit / debugging
    raw_callback         = models.JSONField(default=dict, blank=True)

    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"MpesaTxn #{self.id} — {self.user.username} "
            f"{self.payment_type} KES {self.amount} [{self.status}]"
        )
