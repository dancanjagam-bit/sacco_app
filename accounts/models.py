from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import secrets
import string


class User(AbstractUser):
    is_admin  = models.BooleanField(default=False)
    is_member = models.BooleanField(default=True)

    # Recovery contacts (optional)
    recovery_email = models.EmailField(blank=True, default="")
    recovery_phone = models.CharField(max_length=15, blank=True, default="")
    recovery_email_verified = models.BooleanField(default=False)
    recovery_phone_verified = models.BooleanField(default=False)

    def __str__(self):
        name = self.get_full_name()
        return f"{name} ({self.username})" if name.strip() else self.username


# ─────────────────────────────────────────────────────────────────────────────
# Staff / Role management
# ─────────────────────────────────────────────────────────────────────────────
class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ("superadmin",    "Super Administrator"),
        ("loan_officer",  "Loan Officer"),
        ("accountant",    "Accountant"),
        ("secretary",     "Secretary"),
        ("kyc_officer",   "KYC Officer"),
        ("it_admin",      "IT Administrator"),
    ]
    STATUS_CHOICES = [
        ("active",     "Active"),
        ("inactive",   "Inactive"),
        ("suspended",  "Suspended"),
    ]

    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    role        = models.CharField(max_length=30, choices=ROLE_CHOICES, default="loan_officer")
    department  = models.CharField(max_length=100, blank=True, default="")
    hire_date   = models.DateField(null=True, blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_by  = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_staff",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.get_role_display()}"


class StaffRoleGrant(models.Model):
    """A revocable application workspace role granted by an authorized admin.

    A Django staff flag is not itself an operational SACCO permission. Users
    may hold several of these roles, in addition to member/transport roles.
    """
    ROLE_CHOICES = [
        ("clerk", "Transport clerk"),
        ("credit_officer", "Credit officer"),
        ("treasurer", "Treasurer"),
        ("secretary", "Secretary"),
        ("chairman", "Chairman"),
        ("welfare_officer", "Welfare Officer"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_role_grants")
    role = models.CharField(max_length=24, choices=ROLE_CHOICES)
    active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="issued_staff_role_grants")
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="revoked_staff_role_grants")
    revoked_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500)

    class Meta:
        ordering = ["role", "user_id"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role"), condition=models.Q(active=True),
                name="unique_active_staff_role",
            ),
            models.CheckConstraint(
                condition=models.Q(active=True, revoked_at__isnull=True)
                | models.Q(active=False, revoked_at__isnull=False),
                name="staff_role_revocation_consistent",
            ),
        ]


class StaffDutyAssignment(models.Model):
    """Time-bounded work scope for staff who may only handle assigned items."""
    DUTY_CHOICES = [
        ("transport_assignment", "Manage assigned transport work"),
        ("cash_handover", "Confirm assigned cash handovers"),
        ("transport_issue", "Review assigned transport issues"),
        ("loan_appraisal", "Appraise assigned loan"),
        ("loan_approval", "Decide assigned loan"),
    ]

    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="staff_duty_assignments")
    duty = models.CharField(max_length=32, choices=DUTY_CHOICES)
    vehicle = models.ForeignKey("core.Vehicle", null=True, blank=True, on_delete=models.PROTECT, related_name="staff_duty_assignments")
    crew_assignment = models.ForeignKey("core.CrewAssignment", null=True, blank=True, on_delete=models.PROTECT, related_name="staff_duty_assignments")
    transport_issue = models.ForeignKey("core.TransportAssignmentIssue", null=True, blank=True, on_delete=models.PROTECT, related_name="staff_duty_assignments")
    loan = models.ForeignKey("core.Loan", null=True, blank=True, on_delete=models.PROTECT, related_name="staff_duty_assignments")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="assigned_staff_duties")
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500)

    class Meta:
        ordering = ["-starts_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=models.F("starts_at")),
                name="staff_duty_valid_period",
            ),
        ]
        indexes = [
            models.Index(fields=("staff", "duty", "active", "starts_at"), name="staffduty_scope_idx"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        targets = {
            "vehicle": self.vehicle_id,
            "crew_assignment": self.crew_assignment_id,
            "transport_issue": self.transport_issue_id,
            "loan": self.loan_id,
        }
        expected = {
            "transport_assignment": {"vehicle", "crew_assignment"},
            "cash_handover": {"crew_assignment"},
            "transport_issue": {"transport_issue"},
            "loan_appraisal": {"loan"},
            "loan_approval": {"loan"},
        }.get(self.duty, set())
        supplied = {name for name, value in targets.items() if value is not None}
        if self.duty == "transport_assignment":
            valid = supplied in ({"vehicle"}, {"crew_assignment"})
        else:
            valid = supplied == expected
        if not valid:
            raise ValidationError({"duty": "Choose exactly the record scope required for this duty."})
        if self.duty == "transport_assignment" and self.crew_assignment_id and self.vehicle_id:
            raise ValidationError({"vehicle": "Use either a vehicle or one crew assignment as the scope."})

    @property
    def is_current(self):
        now = timezone.now()
        return self.active and self.starts_at <= now and (self.ends_at is None or self.ends_at > now)


# ─────────────────────────────────────────────────────────────────────────────
# OTP for password reset
# ─────────────────────────────────────────────────────────────────────────────
class OTPRequest(models.Model):
    PURPOSE_CHOICES = [
        ("recovery", "Account recovery"),
        ("login_2fa", "Staff login verification"),
        ("contact_verification", "Recovery contact verification"),
        ("phone_verification", "Registration phone verification"),
    ]
    DELIVERY_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted by provider"),
        ("unavailable", "Provider unavailable"),
        ("failed", "Delivery failed"),
    ]
    METHOD_CHOICES = [
        ("email",          "Email"),
        ("phone",          "Phone / SMS"),
        ("recovery_email", "Recovery Email"),
        ("recovery_phone", "Recovery Phone"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_requests")
    code       = models.CharField(max_length=6)
    method     = models.CharField(max_length=20, choices=METHOD_CHOICES)
    purpose    = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default="recovery")
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    delivery_status = models.CharField(max_length=16, choices=DELIVERY_STATUS_CHOICES, default="pending")
    delivery_reason = models.CharField(max_length=40, blank=True, default="")
    delivery_attempted_at = models.DateTimeField(null=True, blank=True)
    destination_digest = models.CharField(max_length=64, blank=True, default="")

    EXPIRY_MINUTES = 10

    @classmethod
    def generate(cls, user, method, purpose="recovery"):
        cls.objects.filter(user=user, purpose=purpose, used=False).update(used=True)
        code = "".join(secrets.choice(string.digits) for _ in range(6))
        return cls.objects.create(user=user, code=code, method=method, purpose=purpose)

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=self.EXPIRY_MINUTES)

    def __str__(self):
        return f"{self.user.username} — OTP ({'used' if self.used else 'active'})"


# ─────────────────────────────────────────────────────────────────────────────
# In-app Notifications
# ─────────────────────────────────────────────────────────────────────────────
class Notification(models.Model):
    TYPE_CHOICES = [
        ("info",    "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error",   "Error"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type       = models.CharField(max_length=10, choices=TYPE_CHOICES, default="info")
    title      = models.CharField(max_length=100)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    link       = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.type}] {self.title} → {self.user.username}"

    @classmethod
    def send(cls, user, title, message, ntype="info", link=""):
        return cls.objects.create(user=user, type=ntype, title=title, message=message, link=link)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────
class AuditLog(models.Model):
    ACTION_CHOICES = [
        # Auth
        ("login",           "User Login"),
        ("logout",          "User Logout"),
        ("register",        "Member Registered"),
        ("password_change", "Password Changed"),
        ("password_reset",  "Password Reset"),
        ("otp_delivery_failure", "OTP Delivery Failure"),
        ("recovery_contact_verified", "Recovery Contact Verified"),
        # Members
        ("member_create",   "Member Created"),
        ("member_update",   "Member Updated"),
        ("member_delete",   "Member Deleted"),
        ("member_suspend",  "Member Suspended"),
        # Staff
        ("staff_create",    "Staff Created"),
        ("staff_update",    "Staff Updated"),
        ("staff_deactivate","Staff Deactivated"),
        # Finance
        ("deposit",         "Savings Deposit"),
        ("withdrawal",      "Savings Withdrawal"),
        ("fosa_withdrawal_requested", "FOSA Payout Requested"),
        ("fosa_payout_confirmed", "FOSA Payout Confirmed"),
        ("fosa_payout_failed", "FOSA Payout Failed"),
        ("withdrawal_correction_proposed", "Withdrawal Correction Proposed"),
        ("withdrawal_correction_approve", "Withdrawal Correction Approved"),
        ("withdrawal_correction_reject", "Withdrawal Correction Rejected"),
        ("journal_entry_posted", "Accounting Journal Entry Posted"),
        ("journal_entry_reversed", "Accounting Journal Entry Reversed"),
        ("loan_apply",      "Loan Applied"),
        ("loan_approve",    "Loan Approved"),
        ("loan_reject",     "Loan Rejected"),
        ("loan_repayment",  "Loan Repayment"),
        # System
        ("export",          "Data Exported"),
        ("other",           "Other"),
        # ID Verification & CRB
        ("id_verify_submit", "ID Verification Submitted"),
        ("id_verify_review", "ID Verification Reviewed"),
        ("crb_check_run",    "CRB Check Run"),
        ("crb_override",     "CRB Flagged Loan Override"),
        ("loan_flagged",     "Loan Flagged by CRB"),
        ("face_verify",      "Face Verification Run"),
        # KYC workflow & privacy (Kenya DPA 2019)
        ("kyc_risk_scored",       "KYC Risk Scored"),
        ("kyc_reference_requested","KYC Reference Requested"),
        ("kyc_reference_responded","KYC Reference Responded"),
        ("kyc_liveness_run",      "KYC Liveness Challenge Run"),
        ("kyc_member_approved",   "KYC Member Approved"),
        ("kyc_member_rejected",   "KYC Member Rejected"),
        ("kyc_pii_accessed",      "KYC PII Accessed"),
        ("kyc_consent_recorded",  "KYC Consent Recorded"),
        ("kyc_data_exported",     "KYC Data Exported"),
        ("kyc_erasure_requested", "KYC Data Erasure Requested"),
    ]

    actor      = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_actions")
    action     = models.CharField(max_length=30, choices=ACTION_CHOICES)
    target     = models.CharField(max_length=200, blank=True, default="")  # e.g. "Member #SACCO000003"
    details    = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        actor = self.actor.username if self.actor else "System"
        return f"{actor} → {self.get_action_display()} ({self.timestamp:%Y-%m-%d %H:%M})"

    @classmethod
    def log(cls, actor, action, target="", details=None, request=None):
        ip = None
        if request:
            x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
        return cls.objects.create(
            actor=actor, action=action, target=target,
            details=details or {}, ip_address=ip,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 🪪 ID Verification Record
# ─────────────────────────────────────────────────────────────────────────────
class IDVerification(models.Model):
    """
    Tracks the status of government ID verification for a member.
    Supports manual verification by staff and automated KYC via third-party providers.
    """
    PROVIDER_CHOICES = [
        ("manual",          "Manual Verification by Staff"),
        ("smile_identity",  "Smile Identity (KYC API)"),
        ("iprs_stub",       "IPRS Verification (Stub — not live)"),
    ]
    STATUS_CHOICES = [
        ("draft", "Draft"), ("submitted", "Submitted"),
        ("verification_pending", "Verification Pending"), ("verified", "Verified"),
        ("needs_review", "Needs Review"), ("provider_unavailable", "Provider Unavailable"),
        # Legacy values remain readable for already stored records.
        ("pending", "Legacy Pending"), ("failed", "Legacy Failed"), ("flagged", "Legacy Flagged"),
    ]

    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name="id_verification")
    national_id     = models.CharField(max_length=20)
    provider        = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default="manual")
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Provider response (raw JSON from the KYC API or manual notes)
    provider_response = models.JSONField(default=dict, blank=True)
    failure_reason   = models.TextField(blank=True, default="")

    # Uploaded document files
    id_document      = models.FileField(upload_to="id_documents/", null=True, blank=True)  # legacy single-document field
    id_document_front = models.FileField(upload_to="id_documents/", null=True, blank=True)
    id_document_back = models.FileField(upload_to="id_documents/", null=True, blank=True)
    ocr_result       = models.JSONField(default=dict, blank=True)  # raw extracted text and parsed fields
    verification_purpose = models.CharField(max_length=40, default="membership_onboarding")
    member_consent = models.BooleanField(default=False)
    consented_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Selfie / face verification
    selfie           = models.FileField(upload_to="selfies/", null=True, blank=True)
    face_match_score = models.FloatField(null=True, blank=True)

    # ── Privacy safeguards (Kenya Data Protection Act 2019) ───────────────
    # HMAC-SHA256 of the national_id enables duplicate lookup / uniqueness
    # checks without exposing the plaintext in database indexes or logs.
    national_id_hash = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        help_text="HMAC-SHA256 of national_id; never expose or log the plaintext.",
    )
    # Date after which the stored ID documents may be purged per retention policy.
    data_retention_until = models.DateField(
        null=True, blank=True,
        help_text="Earliest date raw ID/selfie files may be deleted per retention policy.",
    )
    # Every time a staff member views the raw documents/selfie, record who/when.
    pii_last_accessed_at = models.DateTimeField(null=True, blank=True)
    pii_last_accessed_by  = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pii_accesses",
    )

    # Who verified manually
    verified_by      = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="verifications_done",
    )
    verified_at      = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"IDVerification #{self.pk} for user #{self.user_id} — {self.status}"


class IDVerificationAttempt(models.Model):
    PROVIDER_CHOICES = [("sandbox", "Sandbox"), ("manual", "Manual review"), ("smile_identity", "Smile Identity")]
    STATUS_CHOICES = [("verification_pending", "Pending"), ("verified", "Verified"), ("needs_review", "Needs review"), ("provider_unavailable", "Provider unavailable")]
    verification = models.ForeignKey(IDVerification, on_delete=models.CASCADE, related_name="attempts")
    provider = models.CharField(max_length=24, choices=PROVIDER_CHOICES)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES)
    provider_reference = models.CharField(max_length=120, blank=True)
    reason_code = models.CharField(max_length=80, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class KYCSubmission(models.Model):
    """Append-only member evidence snapshot for identity review/resubmission."""
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("needs_information", "Needs information"),
        ("reviewed", "Reviewed"),
    ]

    verification = models.ForeignKey(
        IDVerification, on_delete=models.PROTECT, related_name="submissions",
    )
    sequence = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="draft")
    id_document_front = models.FileField(upload_to="id_documents/submissions/%Y/%m/", null=True, blank=True)
    id_document_back = models.FileField(upload_to="id_documents/submissions/%Y/%m/", null=True, blank=True)
    reviewed_fields = models.JSONField(default=dict, blank=True)
    consent_given = models.BooleanField(default=False)
    consent_text_version = models.CharField(max_length=20, default="1.0")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["verification", "sequence"], name="unique_kyc_submission_sequence",
            ),
        ]
        indexes = [models.Index(fields=["verification", "status"], name="kyc_sub_verify_status_idx")]


# ─────────────────────────────────────────────────────────────────────────────
# 🔒 KYC Privacy & Verification Workflow Models (Kenya Data Protection Act 2019)
# ─────────────────────────────────────────────────────────────────────────────
class KYCConsentRecord(models.Model):
    """
    Immutable audit trail of every consent decision a member makes about
    processing their personal / biometric data. The DPA requires demonstrable,
    time-stamped proof of consent that can be produced during an audit.
    Never update or delete a row — append a new row on every change of consent.
    """
    PURPOSE_CHOICES = [
        ("membership_onboarding", "Membership Onboarding"),
        ("id_verification",        "ID Verification"),
        ("face_biometric",         "Face Biometric Processing"),
        ("credit_check",           "Credit Reference Bureau Check"),
        ("data_export",            "Data Export Request"),
        ("data_erasure",           "Data Erasure Request"),
        ("marketing",              "Marketing / Notifications"),
    ]

    user                = models.ForeignKey(User, on_delete=models.CASCADE, related_name="kyc_consents")
    purpose             = models.CharField(max_length=40, choices=PURPOSE_CHOICES)
    consent_given       = models.BooleanField()
    consent_text_version = models.CharField(max_length=20, default="1.0")
    ip_address          = models.GenericIPAddressField(null=True, blank=True)
    user_agent          = models.CharField(max_length=300, blank=True, default="")
    timestamp           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        state = "granted" if self.consent_given else "denied"
        return f"{self.user.username} — {self.purpose} ({state}) @ {self.timestamp:%Y-%m-%d %H:%M}"


class MemberReference(models.Model):
    """
    A member may record a referee response for staff review.

    Reference data is not an automatic membership or identity decision.
    """
    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("expired",  "Expired"),
    ]

    applicant    = models.ForeignKey(User, on_delete=models.CASCADE, related_name="references_requested")
    referee      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="references_received")
    relationship = models.CharField(max_length=100, blank=True, default="")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    note         = models.CharField(max_length=200, blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at   = models.DateTimeField()

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["applicant", "referee"], name="unique_applicant_referee",
            )
        ]

    def __str__(self):
        return f"{self.applicant.username} ← {self.referee.username} ({self.status})"


class DeviceFingerprint(models.Model):
    """
    Tracks devices used to access accounts so the system can flag one device
    creating many accounts (a common signal of ghost-member registration).
    """
    user          = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="devices")
    device_id     = models.CharField(max_length=128, db_index=True)
    device_model  = models.CharField(max_length=120, blank=True, default="")
    platform      = models.CharField(max_length=40, blank=True, default="")
    ip_address    = models.GenericIPAddressField(null=True, blank=True)
    user_agent    = models.CharField(max_length=300, blank=True, default="")
    first_seen    = models.DateTimeField(auto_now_add=True)
    last_seen    = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["device_id"])]

    def __str__(self):
        return f"{self.device_id} ({self.device_model or 'unknown'})"


class LivenessChallenge(models.Model):
    """
    Legacy schema for liveness-provider attempts.

    The local challenge fields do not establish liveness. API actions remain
    disabled until an authorized provider is configured.
    """
    CHALLENGE_CHOICES = [
        ("blink",       "Blink"),
        ("turn_left",   "Turn Head Left"),
        ("turn_right",  "Turn Head Right"),
        ("smile",       "Smile"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("passed",  "Passed"),
        ("failed",  "Failed"),
        ("expired", "Expired"),
    ]

    verification      = models.ForeignKey(IDVerification, on_delete=models.CASCADE, related_name="liveness_challenges")
    challenge_type    = models.CharField(max_length=20, choices=CHALLENGE_CHOICES)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    requested_at      = models.DateTimeField(auto_now_add=True)
    completed_at      = models.DateTimeField(null=True, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)

    EXPIRY_MINUTES = 5

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Liveness #{self.pk} — {self.challenge_type} ({self.status})"


class KYCRiskScore(models.Model):
    """
    Legacy schema for a proposed automated KYC assessment.

    The unapproved score and decision rules are disabled and are not used to
    approve or reject members.
    """
    DECISION_CHOICES = [
        ("auto_approve",  "Auto Approve"),
        ("manual_review", "Manual Review"),
        ("reject",        "Reject"),
    ]

    verification        = models.OneToOneField(IDVerification, on_delete=models.CASCADE, related_name="risk_score")
    phone_verified      = models.BooleanField(default=False)
    id_uploaded         = models.BooleanField(default=False)
    name_matched        = models.BooleanField(default=False)
    selfie_matched      = models.BooleanField(default=False)
    liveness_passed     = models.BooleanField(default=False)
    reference_verified  = models.BooleanField(default=False)
    vehicle_verified    = models.BooleanField(default=False)
    total_score         = models.PositiveSmallIntegerField(default=0)
    decision            = models.CharField(max_length=20, choices=DECISION_CHOICES, default="manual_review")
    calculated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"RiskScore {self.total_score}/100 → {self.decision}"


class MemberApproval(models.Model):
    """
    Multi-stage committee approval pipeline for new member activation.
    A member is not "active" until an official signs off:
        secretary_review → committee_approval → activated
    Each transition is recorded as an immutable step.
    """
    STAGE_CHOICES = [
        ("secretary_review",   "Secretary Review"),
        ("committee_approval", "Committee Approval"),
        ("activated",          "Activated"),
        ("rejected",           "Rejected"),
    ]
    DECISION_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    applicant   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="approval_steps")
    stage       = models.CharField(max_length=30, choices=STAGE_CHOICES, default="secretary_review")
    reviewer    = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviews_done",
    )
    decision    = models.CharField(max_length=20, choices=DECISION_CHOICES, default="pending")
    notes       = models.TextField(blank=True, default="")
    created_at  = models.DateTimeField(auto_now_add=True)
    decided_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.applicant.username} — {self.stage} ({self.decision})"


# ─────────────────────────────────────────────────────────────────────────────
# Secretary: Meetings and Notices
# ─────────────────────────────────────────────────────────────────────────────

class CooperativeMeeting(models.Model):
    """Scheduled cooperative meeting recorded by the secretary."""

    MEETING_TYPE_CHOICES = [
        ("agm",       "Annual General Meeting"),
        ("sgm",       "Special General Meeting"),
        ("committee", "Committee Meeting"),
        ("board",     "Board Meeting"),
        ("other",     "Other"),
    ]
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("postponed", "Postponed"),
    ]

    title        = models.CharField(max_length=200)
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPE_CHOICES, default="committee")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    scheduled_at = models.DateTimeField()
    location     = models.CharField(max_length=300, blank=True, default="")
    agenda       = models.TextField(blank=True, default="")
    minutes      = models.TextField(blank=True, default="")
    quorum_met   = models.BooleanField(null=True, blank=True)
    recorded_by  = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="recorded_meetings",
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"{self.title} — {self.scheduled_at.date()}"


class MemberNotice(models.Model):
    """Cooperative notice or announcement visible to all active members."""

    PRIORITY_CHOICES = [
        ("normal", "Normal"),
        ("urgent", "Urgent"),
    ]
    STATUS_CHOICES = [
        ("draft",     "Draft"),
        ("published", "Published"),
        ("archived",  "Archived"),
    ]

    title        = models.CharField(max_length=200)
    body         = models.TextField()
    priority     = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    status       = models.CharField(max_length=12, choices=STATUS_CHOICES, default="draft")
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at   = models.DateTimeField(null=True, blank=True)
    created_by   = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_notices",
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class MeetingAttendee(models.Model):
    """Attendance record for a cooperative meeting."""
    meeting = models.ForeignKey(CooperativeMeeting, on_delete=models.CASCADE, related_name="attendees")
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="meeting_attendances",
    )
    name = models.CharField(max_length=150)  # captured at time of recording
    role = models.CharField(max_length=100, blank=True, default="")
    present = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True, default="")
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="recorded_attendances")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=("meeting", "user"),
                condition=models.Q(user__isnull=False),
                name="unique_meeting_attendee_user",
            )
        ]

    def __str__(self):
        return f"{self.name} at Meeting #{self.meeting_id}"


from .welfare_models import WelfareContribution, WelfareDocument, WelfarePayout, WelfarePolicy, WelfareRequest  # noqa: E402,F401
