from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import Q


def welfare_document_storage():
    return FileSystemStorage(location=settings.WELFARE_PRIVATE_ROOT)


class WelfarePolicy(models.Model):
    version = models.CharField(max_length=60, unique=True)
    approval_reference = models.CharField(max_length=120)
    benefits = models.JSONField(help_text="Map each approved category to maximum_benefit and minimum_contributions in KES.")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("active",), condition=Q(active=True), name="single_active_welfare_policy"),
        ]

    def __str__(self):
        return self.version


class WelfareRequest(models.Model):
    member = models.ForeignKey("members.Member", on_delete=models.PROTECT, related_name="welfare_requests")
    category = models.CharField(max_length=60)
    description = models.TextField()
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ("submitted", "Submitted"),
        ("needs_information", "Needs additional information"),
        ("under_review", "Under review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ], default="submitted")
    policy = models.ForeignKey(WelfarePolicy, null=True, on_delete=models.PROTECT)
    decision_reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    decided_at = models.DateTimeField(null=True)
    # Officer requesting supplementary details from the member.
    review_notes = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="welfare_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WelfareDocument(models.Model):
    request = models.ForeignKey(WelfareRequest, on_delete=models.PROTECT, related_name="documents")
    file = models.FileField(upload_to="documents", storage=welfare_document_storage, max_length=200)
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)


class WelfareContribution(models.Model):
    """Member attribution for an existing posted journal credit."""
    member = models.ForeignKey("members.Member", on_delete=models.PROTECT, related_name="welfare_contributions")
    journal_line = models.OneToOneField("accounting.JournalLine", on_delete=models.PROTECT)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class WelfarePayout(models.Model):
    request = models.OneToOneField(WelfareRequest, on_delete=models.PROTECT, related_name="payout")
    status = models.CharField(max_length=22, choices=[
        ("awaiting_provider", "Awaiting payout provider"),
        ("pending", "Pending provider confirmation"), ("uncertain", "Provider outcome uncertain"),
        ("confirmed", "Confirmed"), ("failed", "Failed"),
    ], default="awaiting_provider")
    provider_reference = models.CharField(max_length=100, blank=True)
    provider_transaction_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    destination_phone = models.CharField(max_length=15, blank=True)
    confirmed_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
