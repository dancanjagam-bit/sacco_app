import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class LedgerAccount(models.Model):
    CLASSIFICATIONS = [
        ("asset", "Asset"),
        ("liability", "Liability"),
        ("equity", "Equity"),
        ("income", "Income"),
        ("expense", "Expense"),
    ]
    NORMAL_BALANCES = [("debit", "Debit"), ("credit", "Credit")]

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    classification = models.CharField(max_length=16, choices=CLASSIFICATIONS)
    normal_balance = models.CharField(max_length=8, choices=NORMAL_BALANCES)
    currency = models.CharField(
        max_length=3,
        default="KES",
        validators=[RegexValidator(r"^[A-Z]{3}$", "Use an uppercase ISO 4217 code.")],
    )
    system_key = models.CharField(max_length=48, unique=True, null=True, blank=True)
    active = models.BooleanField(default=True)
    permits_posting = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "code", "name", "classification", "normal_balance", "currency", "system_key"
            ).first()
            if previous and self.journal_lines.exists():
                immutable = ("code", "name", "classification", "normal_balance", "currency", "system_key")
                if any(previous[field] != getattr(self, field) for field in immutable):
                    raise ValidationError("An account's chart identity cannot change after posting.")
        return super().save(*args, **kwargs)


class JournalEntry(models.Model):
    STATUS_CHOICES = [("draft", "Draft"), ("posted", "Posted")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    source_type = models.CharField(max_length=48)
    source_reference = models.CharField(max_length=128)
    description = models.CharField(max_length=240)
    reason = models.TextField(blank=True, default="")
    currency = models.CharField(
        max_length=3,
        default="KES",
        validators=[RegexValidator(r"^[A-Z]{3}$", "Use an uppercase ISO 4217 code.")],
    )
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="created_journal_entries",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="posted_journal_entries",
    )
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="reversal_entry",
    )
    adjusts = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="adjustment_entries",
    )
    audit_log = models.ForeignKey(
        "accounts.AuditLog", null=True, blank=True, on_delete=models.PROTECT,
        related_name="journal_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=("source_type", "source_reference"), name="acct_journal_source_idx"),
            models.Index(fields=("status", "posted_at"), name="acct_journal_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("source_type", "source_reference"), name="acct_journal_source_ref_uq"
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=r"^[A-Z]{3}$"),
                name="acct_journal_currency_iso_chk",
            ),
        ]

    def __str__(self):
        return f"{self.source_type}:{self.source_reference} ({self.status})"

    def save(self, *args, **kwargs):
        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous_status == "posted":
                raise ValidationError("Posted journal entries are immutable; post a linked reversal or adjustment.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == "posted":
            raise ValidationError("Posted journal entries cannot be deleted.")
        return super().delete(*args, **kwargs)


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="journal_lines")
    line_number = models.PositiveSmallIntegerField()
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    memo = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        ordering = ["line_number"]
        constraints = [
            models.UniqueConstraint(fields=("entry", "line_number"), name="acct_line_entry_num_uq"),
            models.CheckConstraint(condition=Q(debit__gte=0), name="acct_line_debit_nonneg_chk"),
            models.CheckConstraint(condition=Q(credit__gte=0), name="acct_line_credit_nonneg_chk"),
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(debit=0, credit__gt=0)),
                name="acct_line_one_side_only_chk",
            ),
        ]
        indexes = [models.Index(fields=("account", "entry"), name="acct_line_acct_entry_idx")]

    def __str__(self):
        return f"{self.entry_id}:{self.line_number} {self.account.code}"

    def save(self, *args, **kwargs):
        entry = self.entry if self.entry_id else None
        if entry is None or entry.status == "posted":
            raise ValidationError("Journal lines can only be changed while their entry is a draft.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.entry.status == "posted":
            raise ValidationError("Posted journal lines cannot be deleted.")
        return super().delete(*args, **kwargs)


class ShareCapitalPolicy(models.Model):
    """Versioned cooperative-approved terms; no share price is hard-coded."""

    version = models.CharField(max_length=64, unique=True)
    terms = models.JSONField(default=dict)
    active = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="created_share_capital_policies",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="approved_share_capital_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("active",), condition=Q(active=True), name="acct_one_active_share_policy_uq"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.active and (not self.approved_by_id or not self.approved_at):
            raise ValidationError("A share-capital policy needs a recorded second-person approval before activation.")
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "version", "terms", "created_by_id", "approved_by_id", "approved_at"
            ).first()
            if previous and previous["approved_at"] and any(
                previous[field] != getattr(self, field)
                for field in ("version", "terms", "created_by_id", "approved_by_id", "approved_at")
            ):
                raise ValidationError("An approved share-capital policy is immutable; create a new version.")
        return super().save(*args, **kwargs)


class ShareCapitalMovement(models.Model):
    MOVEMENT_TYPES = [("issue", "Share units issued"), ("redeem", "Share units redeemed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True)
    member = models.ForeignKey(
        "members.Member", on_delete=models.PROTECT, related_name="share_capital_movements"
    )
    movement_type = models.CharField(max_length=8, choices=MOVEMENT_TYPES)
    units = models.DecimalField(max_digits=16, decimal_places=6)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    journal_line = models.OneToOneField(
        JournalLine, on_delete=models.PROTECT, related_name="share_capital_movement"
    )
    policy = models.ForeignKey(
        ShareCapitalPolicy, on_delete=models.PROTECT, related_name="movements"
    )
    evidence_reference = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_share_capital_movements"
    )
    audit_log = models.ForeignKey(
        "accounts.AuditLog", on_delete=models.PROTECT, related_name="share_capital_movements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(units__gt=0), name="acct_share_units_positive_chk"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="acct_share_amount_positive_chk"),
        ]
        indexes = [models.Index(fields=("member", "created_at"), name="acct_share_member_date_idx")]

    def __str__(self):
        return f"{self.member.member_number} {self.movement_type} {self.units} units"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Share-capital movements are append-only; post a linked correction.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Share-capital movements cannot be deleted.")
