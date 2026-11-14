"""
Serializers for the KYC verification workflow API.

Covers: registration phone OTP, referee references, liveness challenges,
committee approval, consent, data export, and erasure requests.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from accounts.models import (
    MemberReference, LivenessChallenge, MemberApproval, KYCRiskScore,
)
from accounts.serializers import normalise_kenyan_phone

User = get_user_model()


# ═════════════════════════════════════════════════════════════════════════════
# 1. Registration phone OTP
# ═════════════════════════════════════════════════════════════════════════════
class PhoneOTPRequestSerializer(serializers.Serializer):
    """Request a one-time code to verify the phone number during sign-up."""
    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, v):
        return normalise_kenyan_phone(v)


class PhoneOTPConfirmSerializer(serializers.Serializer):
    """Confirm the phone OTP issued during registration."""
    phone_number = serializers.CharField(max_length=20)
    code = serializers.CharField(min_length=6, max_length=6)

    def validate_phone_number(self, v):
        return normalise_kenyan_phone(v)


# ═════════════════════════════════════════════════════════════════════════════
# 2. Referee / reference verification
# ═════════════════════════════════════════════════════════════════════════════
class AddReferenceSerializer(serializers.Serializer):
    """An applicant nominates an existing member as a referee."""
    referee_member_number = serializers.CharField(max_length=20)
    relationship = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_referee_member_number(self, v):
        from members.models import Member
        try:
            referee_member = Member.objects.get(member_number=v.strip())
        except Member.DoesNotExist:
            raise serializers.ValidationError(
                "No active member found with that membership number."
            )
        if not referee_member.user.is_active:
            raise serializers.ValidationError("That member account is not active.")
        return v.strip()


class ReferenceResponseSerializer(serializers.Serializer):
    """A referee approves or declines a reference request."""
    STATUS_CHOICES = [("approved", "Approve"), ("rejected", "Reject")]
    status = serializers.ChoiceField(choices=STATUS_CHOICES)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Liveness challenge
# ═════════════════════════════════════════════════════════════════════════════
class LivenessCompleteSerializer(serializers.Serializer):
    """
    Submit the result of a liveness challenge. In production this result is
    set by the biometric provider callback (e.g. Smile Identity job_type 1);
    in the sandbox the member app submits it directly so the workflow can be
    exercised end-to-end.
    """
    STATUS_CHOICES = [("passed", "Passed"), ("failed", "Failed")]
    status = serializers.ChoiceField(choices=STATUS_CHOICES)
    provider_response = serializers.JSONField(required=False)


# ═════════════════════════════════════════════════════════════════════════════
# 4. Committee approval
# ═════════════════════════════════════════════════════════════════════════════
class MemberApprovalDecisionSerializer(serializers.Serializer):
    """A committee official records a decision on a member's application."""
    DECISION_CHOICES = [("approved", "Approve"), ("rejected", "Reject")]
    decision = serializers.ChoiceField(choices=DECISION_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["decision"] == "approved" and not attrs.get("notes", "").strip():
            raise serializers.ValidationError(
                {"notes": "A reason is required when approving a new member."}
            )
        return attrs


# ═════════════════════════════════════════════════════════════════════════════
# 5. Consent
# ═════════════════════════════════════════════════════════════════════════════
class ConsentSerializer(serializers.Serializer):
    """Record a member's consent decision for a processing purpose."""
    PURPOSE_CHOICES = [
        ("membership_onboarding", "Membership Onboarding"),
        ("id_verification", "ID Verification"),
        ("face_biometric", "Face Biometric Processing"),
        ("credit_check", "Credit Reference Bureau Check"),
        ("marketing", "Marketing / Notifications"),
    ]
    purpose = serializers.ChoiceField(choices=PURPOSE_CHOICES)
    consent_given = serializers.BooleanField()


# ═════════════════════════════════════════════════════════════════════════════
# 6. Data erasure request
# ═════════════════════════════════════════════════════════════════════════════
class ErasureRequestSerializer(serializers.Serializer):
    """
    Confirms a member's explicit request to have their identity data erased.
    The member must type CONFIRM so the action is deliberate.
    """
    confirm = serializers.CharField()

    def validate_confirm(self, v):
        if v.strip().upper() != "CONFIRM":
            raise serializers.ValidationError(
                "Type CONFIRM to authorise erasure of your identity data."
            )
        return v


# ═════════════════════════════════════════════════════════════════════════════
# 7. Device fingerprint (optional, sent by the mobile app)
# ═════════════════════════════════════════════════════════════════════════════
class DeviceFingerprintSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=128)
    device_model = serializers.CharField(max_length=120, required=False, allow_blank=True)
    platform = serializers.CharField(max_length=40, required=False, allow_blank=True)


# ═════════════════════════════════════════════════════════════════════════════
# Read-only serializers for responses
# ═════════════════════════════════════════════════════════════════════════════
class ReferenceSerializer(serializers.ModelSerializer):
    applicant = serializers.CharField(source="applicant.username", read_only=True)
    referee = serializers.CharField(source="referee.username", read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = MemberReference
        fields = [
            "id", "applicant", "referee", "relationship",
            "status", "note", "requested_at", "responded_at", "expires_at",
        ]
        read_only_fields = fields


class LivenessChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LivenessChallenge
        fields = [
            "id", "challenge_type", "status",
            "requested_at", "completed_at",
        ]
        read_only_fields = fields


class KYCRiskScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCRiskScore
        fields = [
            "phone_verified", "id_uploaded", "name_matched",
            "selfie_matched", "liveness_passed",
            "reference_verified", "vehicle_verified",
            "total_score", "decision", "calculated_at",
        ]
        read_only_fields = fields


class MemberApprovalSerializer(serializers.ModelSerializer):
    applicant = serializers.CharField(source="applicant.username", read_only=True)
    reviewer = serializers.CharField(source="reviewer.username", read_only=True)

    class Meta:
        model = MemberApproval
        fields = [
            "id", "applicant", "reviewer", "stage",
            "decision", "notes", "created_at", "decided_at",
        ]
        read_only_fields = ["id", "applicant", "reviewer", "created_at", "decided_at", "stage"]
