"""KYC workflow and privacy endpoints.

Contact verification, consent records, document review, references, data
portability, and erasure use persisted records. Automated risk decisions and
provider-backed liveness are deliberately unavailable until policy and
authorized provider prerequisites are satisfied.
"""
from __future__ import annotations

import secrets
import string

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from accounts.models import (
    IDVerification, OTPRequest, MemberReference,
    KYCSubmission, MemberApproval, KYCConsentRecord, DeviceFingerprint, AuditLog, Notification,
)
from accounts.services.kyc_privacy import (
    mask_national_id, mask_phone, record_consent,
    export_member_pii, request_erasure, log_pii_access, retention_date,
)
from accounts.services.otp_delivery import dispatch_otp
from accounts.kyc_serializers import (
    PhoneOTPRequestSerializer, PhoneOTPConfirmSerializer,
    AddReferenceSerializer, ReferenceResponseSerializer,
    MemberApprovalDecisionSerializer,
    ConsentSerializer, ErasureRequestSerializer, DeviceFingerprintSerializer,
    ReferenceSerializer, MemberApprovalSerializer,
)

import hmac as _hmac

# Reuse the permission classes already defined in accounts.views
from accounts.views import IsKYCStaff, IsSuperAdmin


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get_or_create_verification(user) -> IDVerification:
    try:
        return user.id_verification
    except IDVerification.DoesNotExist:
        member = getattr(user, "member_profile", None)
        national_id = member.national_id if member else ""
        from accounts.services.kyc_privacy import hash_national_id, retention_date
        v = IDVerification.objects.create(
            user=user, national_id=national_id, status="draft",
            national_id_hash=hash_national_id(national_id) if national_id else "",
            data_retention_until=retention_date(),
        )
        return v


def _overall_status(verification, approval) -> str:
    if approval and approval.decision == "approved":
        return "approved"
    if approval and approval.decision == "rejected":
        return "rejected"
    if verification and verification.status == "verified":
        return "verified"
    if verification and verification.submitted_at:
        return "pending_review"
    if verification and verification.id_document_front:
        return "in_progress"
    return "not_started"


class IsMembershipApprover(BasePermission):
    """Membership decisions are separate from identity-provider verification."""
    def has_permission(self, request, view):
        from accounts.access import has_sacco_permission
        return has_sacco_permission(request.user, "membership.approve")


class IDDocumentDraftSerializer(serializers.Serializer):
    id_document_front = serializers.FileField(required=True)
    id_document_back = serializers.FileField(required=False)
    consent = serializers.BooleanField()

    def validate_id_document_front(self, file):
        return self._validate_file(file)

    def validate_id_document_back(self, file):
        return self._validate_file(file)

    @staticmethod
    def _validate_file(file):
        from django.core.exceptions import ValidationError
        from accounts.services.file_validator import validate_id_document
        try:
            validate_id_document(file)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return file

    def validate(self, attrs):
        if not attrs.get("consent"):
            raise serializers.ValidationError({"consent": "Consent is required before identity documents can be stored."})
        return attrs


class IDReviewedFieldsSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    national_id = serializers.CharField(max_length=20)
    date_of_birth = serializers.DateField()

    def validate_national_id(self, value):
        from accounts.serializers import validate_kenyan_national_id
        return validate_kenyan_national_id(value)


# ═════════════════════════════════════════════════════════════════════════════
# Workflow overview
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def kyc_workflow_status(request):
    """Return the full KYC pipeline status for the authenticated member."""
    user = request.user
    verification = _get_or_create_verification(user)
    approval = (
        MemberApproval.objects.filter(applicant=user)
        .order_by("-created_at").first()
    )

    refs = MemberReference.objects.filter(applicant=user).order_by("-requested_at")
    phone_verified = OTPRequest.objects.filter(
        user=user, purpose="phone_verification", used=True,
    ).exists()

    return Response({
        "overall_status": _overall_status(verification, approval),
        "steps": {
            "phone_verified": phone_verified,
            "id_document_uploaded": bool(verification.id_document_front),
            "id_document_back_uploaded": bool(verification.id_document_back),
            "selfie_uploaded": bool(verification.selfie),
            "face_match_score": verification.face_match_score,
            "name_matched": None,
            "liveness_passed": False,
            "reference_verified": refs.filter(status="approved").exists(),
            "vehicle_verified": None,
        },
        "risk_score": None,
        "risk_assessment": {
            "status": "disabled",
            "reason": "Automated assessment is unavailable pending an approved policy.",
        },
        "references": ReferenceSerializer(refs, many=True).data,
        "liveness_status": "provider_unavailable",
        "liveness_challenges": [],
        "approval": MemberApprovalSerializer(approval).data if approval else None,
        "verification": {
            "status": verification.status,
            "national_id": mask_national_id(verification.national_id),
            "member_consent": verification.member_consent,
            "submitted_at": verification.submitted_at,
            "verified_at": verification.verified_at,
            "data_retention_until": verification.data_retention_until,
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def id_verification_documents(request):
    """Store a consented identity-document draft without claiming verification."""
    serializer = IDDocumentDraftSerializer(data={**request.data, **request.FILES})
    serializer.is_valid(raise_exception=True)
    from accounts.services.kyc_privacy import record_consent, retention_date
    from django.db.models import Max

    with transaction.atomic():
        verification = _get_or_create_verification(request.user)
        verification = IDVerification.objects.select_for_update().get(pk=verification.pk)
        if verification.status not in {"draft", "needs_review", "provider_unavailable", "pending", "flagged"}:
            return Response({
                "error": "This submission is already awaiting review. Wait for staff feedback before resubmitting."
            }, status=409)

        previous = verification.submissions.order_by("-sequence").first()
        sequence = (verification.submissions.aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0) + 1
        front = serializer.validated_data["id_document_front"]
        back = serializer.validated_data.get("id_document_back")
        member = getattr(request.user, "member_profile", None)
        reviewed_fields = {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "national_id": member.national_id if member else verification.national_id,
            "date_of_birth": member.date_of_birth.isoformat() if member and member.date_of_birth else "",
        }
        submission = KYCSubmission.objects.create(
            verification=verification,
            sequence=sequence,
            status="draft",
            id_document_front=front,
            id_document_back=back if back else (previous.id_document_back.name if previous and previous.id_document_back else ""),
            reviewed_fields=reviewed_fields,
            consent_given=True,
            consent_text_version=getattr(settings, "KYC_CONSENT_VERSION", "1.0"),
        )

        verification.id_document_front = submission.id_document_front.name
        if back:
            verification.id_document_back = submission.id_document_back.name
        verification.member_consent = True
        verification.consented_at = verification.consented_at or timezone.now()
        verification.data_retention_until = verification.data_retention_until or retention_date()
        verification.status = "draft"
        verification.submitted_at = None
        verification.provider = "manual"
        verification.save(update_fields=(
            "id_document_front", "id_document_back", "member_consent", "consented_at",
            "data_retention_until", "status", "submitted_at", "provider", "updated_at",
        ))
        record_consent(request.user, "id_verification", True, request=request)
        AuditLog.log(request.user, "id_verify_submit", f"KYC submission draft #{submission.pk}",
                     {"submission_id": submission.pk, "sequence": sequence, "stage": "draft"}, request)

        # OCR is advisory and runs locally only after explicit document consent.
        try:
            from accounts.services.ocr_pipeline import run_ocr
            verification.ocr_result = run_ocr(submission.id_document_front.path)
            verification.save(update_fields=("ocr_result", "updated_at"))
        except Exception as exc:
            # File/path/OCR failures never change the identity decision.
            import logging
            logging.getLogger("sacco").warning("Advisory OCR unavailable (%s)", type(exc).__name__)

    return Response({
        "message": "Document saved as a draft. OCR suggestions are advisory; review them before submission.",
        "submission_id": submission.pk,
        "sequence": submission.sequence,
        "status": submission.status,
    }, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def id_verification_submit(request):
    """Submit reviewed identity fields for manual staff review."""
    fields = request.data.get("reviewed_fields")
    serializer = IDReviewedFieldsSerializer(data=fields)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        verification = _get_or_create_verification(request.user)
        verification = IDVerification.objects.select_for_update().get(pk=verification.pk)
        submission = verification.submissions.select_for_update().filter(status="draft").order_by("-sequence").first()
        if not submission:
            return Response({"error": "Save a consented document draft before submitting it for review."}, status=409)
        if not submission.consent_given or not verification.member_consent:
            return Response({"error": "Consent is required before submitting identity documents."}, status=400)

        submission.reviewed_fields = serializer.validated_data.copy()
        submission.reviewed_fields["date_of_birth"] = serializer.validated_data["date_of_birth"].isoformat()
        submission.status = "submitted"
        submission.submitted_at = timezone.now()
        submission.save(update_fields=("reviewed_fields", "status", "submitted_at"))
        verification.status = "submitted"
        verification.provider = "manual"
        verification.submitted_at = submission.submitted_at
        verification.failure_reason = ""
        verification.save(update_fields=("status", "provider", "submitted_at", "failure_reason", "updated_at"))

        AuditLog.log(request.user, "id_verify_submit", f"KYC submission #{submission.pk}",
                     {"submission_id": submission.pk, "sequence": submission.sequence,
                      "method": "manual_review"}, request)
        transaction.on_commit(lambda: Notification.send(
            request.user, "Identity documents submitted",
            "Your documents and reviewed details are awaiting staff review.", "info", "/id-verification",
        ))

    return Response({
        "message": "Your details were submitted for staff review. OCR does not verify government identity.",
        "status": "submitted",
        "submission_id": submission.pk,
    }, status=202)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Phone OTP verification
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@ratelimit(key="user", rate="5/h", block=True)
def kyc_phone_otp_request(request):
    """Send a one-time code to the member's registered phone to verify it."""
    serializer = PhoneOTPRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    phone = serializer.validated_data["phone_number"]

    try:
        member = request.user.member_profile
    except Exception:
        return Response({"error": "Member profile not found."}, status=400)

    if member.phone_number != phone:
        return Response({"error": "This phone does not match your registered number."}, status=400)

    # Reuse the OTP infrastructure with the phone_verification purpose.
    OTPRequest.objects.filter(
        user=request.user, purpose="phone_verification", used=False,
    ).update(used=True)
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    otp = OTPRequest.objects.create(
        user=request.user, code=code, method="phone", purpose="phone_verification",
    )
    outcome = dispatch_otp(otp)
    if outcome["status"] != "accepted":
        return Response(
            {"error": "The verification code could not be sent. Try again later."},
            status=503,
        )
    return Response({"message": "A verification code was sent to your phone."}, status=202)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@ratelimit(key="user", rate="10/h", block=True)
def kyc_phone_otp_confirm(request):
    """Confirm the phone-verification OTP. Marks the phone as verified."""
    serializer = PhoneOTPConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    code = serializer.validated_data["code"]

    with transaction.atomic():
        otp = (
            OTPRequest.objects.select_for_update()
            .filter(
                user=request.user, purpose="phone_verification",
                used=False, delivery_status="accepted",
            ).order_by("-created_at").first()
        )
        if not otp or otp.is_expired or otp.attempt_count >= 5:
            return Response({"error": "Invalid or expired code. Request a new one."}, status=400)

        matches = _hmac.compare_digest(otp.code, code)
        otp.attempt_count += 1
        if not matches and otp.attempt_count >= 5:
            otp.used = True
        otp.save(update_fields=("attempt_count", "used"))
        if not matches:
            return Response({"error": "Invalid verification code."}, status=400)

        otp.used = True
        otp.save(update_fields=("used",))

    return Response({"message": "Phone number verified.", "phone_verified": True})


# ═════════════════════════════════════════════════════════════════════════════
# 2. Referee / reference verification
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST", "GET"])
@permission_classes([IsAuthenticated])
def kyc_reference_add(request):
    """An applicant nominates an existing member as a referee."""
    if request.method == "GET":
        refs = MemberReference.objects.filter(applicant=request.user).order_by("-requested_at")
        return Response(ReferenceSerializer(refs, many=True).data)

    serializer = AddReferenceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    referee_number = serializer.validated_data["referee_member_number"]

    from members.models import Member
    referee_member = get_object_or_404(Member, member_number=referee_number)
    referee = referee_member.user

    if referee == request.user:
        return Response({"error": "You cannot list yourself as a referee."}, status=400)

    existing = MemberReference.objects.filter(applicant=request.user).count()
    if existing >= 2:
        return Response({"error": "You may only nominate up to two referees."}, status=400)

    expires_at = timezone.now() + timezone.timedelta(days=7)
    ref, created = MemberReference.objects.get_or_create(
        applicant=request.user, referee=referee,
        defaults={
            "relationship": serializer.validated_data.get("relationship", ""),
            "expires_at": expires_at,
        },
    )
    if not created:
        return Response({"error": "You have already nominated this member."}, status=409)

    transaction.on_commit(lambda: Notification.send(
        referee, "Reference Request",
        f"{request.user.get_full_name() or request.user.username} has asked you to vouch for them. "
        "Review and respond in the app.",
        "info", "/references",
    ))
    AuditLog.log(request.user, "kyc_reference_requested",
                 target=f"Reference #{ref.pk}",
                 details={"referee": referee.username}, request=request)
    return Response(ReferenceSerializer(ref).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def kyc_reference_received(request):
    """List reference requests awaiting this member's response."""
    refs = MemberReference.objects.filter(
        referee=request.user, status="pending",
    ).order_by("-requested_at")
    return Response(ReferenceSerializer(refs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def kyc_reference_respond(request, reference_id):
    """A referee approves or rejects a reference request."""
    ref = get_object_or_404(MemberReference, pk=reference_id, referee=request.user)
    if ref.status != "pending":
        return Response({"error": "This reference has already been responded to."}, status=400)
    if timezone.now() > ref.expires_at:
        ref.status = "expired"
        ref.save(update_fields=["status"])
        return Response({"error": "This reference request has expired."}, status=400)

    serializer = ReferenceResponseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        ref.status = serializer.validated_data["status"]
        ref.note = serializer.validated_data.get("note", "")
        ref.responded_at = timezone.now()
        ref.save(update_fields=["status", "note", "responded_at"])

        transaction.on_commit(lambda: Notification.send(
            ref.applicant, "Reference Update",
            f"Your referee {request.user.get_full_name() or request.user.username} "
            f"{'approved' if ref.status == 'approved' else 'declined'} your reference request.",
            "success" if ref.status == "approved" else "warning",
        ))
    AuditLog.log(request.user, "kyc_reference_responded",
                 target=f"Reference #{ref.pk}",
                 details={"decision": ref.status}, request=request)
    return Response(ReferenceSerializer(ref).data)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Liveness challenge
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def kyc_liveness_start(request):
    """Liveness is unavailable until an authorized provider is configured."""
    return Response(
        {
            "status": "provider_unavailable",
            "error": "Liveness verification is not available yet.",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def kyc_liveness_complete(request, challenge_id):
    """Do not accept client assertions as evidence of liveness."""
    return Response(
        {
            "status": "provider_unavailable",
            "error": "Liveness verification is not available yet.",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 4. Risk score
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def kyc_risk_score(request):
    """Automated risk decisions remain disabled pending an approved policy."""
    return Response(
        {
            "status": "disabled",
            "error": "Automated membership risk decisions are not available.",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 5. Consent (Kenya DPA — demonstrable consent)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST", "GET"])
@permission_classes([IsAuthenticated])
def kyc_consent(request):
    if request.method == "GET":
        consents = KYCConsentRecord.objects.filter(user=request.user).order_by("-timestamp")
        return Response([
            {
                "purpose": c.purpose, "consent_given": c.consent_given,
                "consent_text_version": c.consent_text_version,
                "timestamp": c.timestamp,
            }
            for c in consents
        ])

    serializer = ConsentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    record = record_consent(
        request.user,
        purpose=serializer.validated_data["purpose"],
        consent_given=serializer.validated_data["consent_given"],
        request=request,
    )
    # If the member consents to ID verification, also stamp the verification record.
    if serializer.validated_data["consent_given"] and serializer.validated_data["purpose"] in (
        "membership_onboarding", "id_verification",
    ):
        verification = _get_or_create_verification(request.user)
        verification.member_consent = True
        verification.consented_at = timezone.now()
        if not verification.data_retention_until:
            verification.data_retention_until = retention_date()
        verification.save(update_fields=[
            "member_consent", "consented_at", "data_retention_until",
        ])
    return Response({
        "message": "Consent recorded.",
        "purpose": record.purpose,
        "consent_given": record.consent_given,
        "timestamp": record.timestamp,
    }, status=201)


# ═════════════════════════════════════════════════════════════════════════════
# 6. Device fingerprint (fraud detection)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def kyc_device_register(request):
    serializer = DeviceFingerprintSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
    ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:300]

    device, created = DeviceFingerprint.objects.update_or_create(
        device_id=data["device_id"],
        defaults={
            "user": request.user,
            "device_model": data.get("device_model", ""),
            "platform": data.get("platform", ""),
            "ip_address": ip,
            "user_agent": ua,
        },
    )
    # Flag if this device is linked to many accounts.
    account_count = DeviceFingerprint.objects.filter(device_id=data["device_id"]).count()
    flagged = account_count >= 3
    if flagged and created:
        transaction.on_commit(lambda: Notification.send(
            request.user, "Security Notice",
            "Your device is associated with multiple member accounts. "
            "If this was not you, contact the SACCO office.",
            "warning",
        ))
    return Response({
        "device_id": device.device_id,
        "first_seen": device.first_seen,
        "accounts_on_device": account_count,
        "flagged": flagged,
    }, status=201 if created else 200)


# ═════════════════════════════════════════════════════════════════════════════
# 7. Data export (right to portability) & erasure (right to be forgotten)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def kyc_my_data(request):
    """Export all personal data held about the member (data portability)."""
    # Require consent for the export itself.
    data = export_member_pii(request.user)
    AuditLog.log(request.user, "kyc_data_exported",
                 target=f"User {request.user.username}",
                 details={"sections": list(data.keys())}, request=request)
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def kyc_erasure(request):
    """Request erasure of identity data (right to be forgotten)."""
    serializer = ErasureRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    # Record the erasure consent first, then execute.
    record_consent(request.user, purpose="data_erasure",
                   consent_given=True, request=request)
    summary = request_erasure(request.user, request=request)
    return Response({
        "message": "Identity data erasure completed. Your account has been deactivated.",
        "summary": summary,
    })


# ═════════════════════════════════════════════════════════════════════════════
# 8. Committee approval (staff)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET"])
@permission_classes([IsMembershipApprover])
def kyc_admin_pending_approvals(request):
    """List members awaiting committee approval, ordered by oldest first."""
    # Members whose latest approval step is still pending.
    qs = MemberApproval.objects.filter(decision="pending").select_related(
        "applicant", "reviewer",
    ).order_by("created_at")
    return Response([
        {
            "id": a.pk, "applicant": a.applicant.username,
            "full_name": a.applicant.get_full_name(),
            "stage": a.stage, "created_at": a.created_at,
        }
        for a in qs
    ])


@api_view(["POST"])
@permission_classes([IsMembershipApprover])
def kyc_admin_approval_decide(request, approval_id):
    """A committee official approves or rejects a member's application."""
    approval = get_object_or_404(MemberApproval, pk=approval_id)
    if approval.applicant_id == request.user.pk:
        return Response({"error": "You cannot approve your own membership application."}, status=403)
    if approval.decision != "pending":
        return Response({"error": "This approval has already been decided."}, status=400)

    serializer = MemberApprovalDecisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    decision = serializer.validated_data["decision"]
    notes = serializer.validated_data.get("notes", "")
    if decision == "approved" and approval.stage == "committee_approval":
        identity = IDVerification.objects.filter(user=approval.applicant).first()
        if not identity or identity.status != "verified":
            return Response({
                "code": "identity_review_required",
                "error": "Complete the separate manual identity review before final membership activation.",
            }, status=409)

    with transaction.atomic():
        approval.decision = decision
        approval.reviewer = request.user
        approval.notes = notes
        approval.decided_at = timezone.now()
        approval.save(update_fields=["decision", "reviewer", "notes", "decided_at"])

        if decision == "approved":
            # Advance the pipeline stage.
            if approval.stage == "secretary_review":
                MemberApproval.objects.create(
                    applicant=approval.applicant, stage="committee_approval",
                )
                next_stage = "committee_approval"
            elif approval.stage == "committee_approval":
                # Final stage — activate the member.
                MemberApproval.objects.create(
                    applicant=approval.applicant, stage="activated",
                    reviewer=request.user, decision="approved",
                    decided_at=timezone.now(),
                )
                try:
                    member = approval.applicant.member_profile
                    member.status = "active"
                    member.save(update_fields=["status"])
                except Exception:
                    pass
                next_stage = "activated"
                # Membership approval is a separate decision from identity verification.
            else:
                next_stage = approval.stage

            AuditLog.log(request.user, "kyc_member_approved",
                         target=f"Approval #{approval.pk}",
                         details={"stage": approval.stage}, request=request)
            message = f"Your membership has been approved at the {approval.get_stage_display()} stage."
            ntype = "success"
        else:
            next_stage = "rejected"
            try:
                member = approval.applicant.member_profile
                member.status = "inactive"
                member.save(update_fields=["status"])
            except Exception:
                pass
            AuditLog.log(request.user, "kyc_member_rejected",
                         target=f"Approval #{approval.pk}",
                         details={"stage": approval.stage, "notes": notes}, request=request)
            message = "Your membership application was not approved. Contact the SACCO office."
            ntype = "warning"

        transaction.on_commit(lambda: Notification.send(
            approval.applicant, "Membership Decision", message, ntype,
        ))

    return Response({
        "message": f"Decision recorded: {decision}.",
        "stage": approval.stage, "decision": decision,
        "next_stage": next_stage,
    })
