"""
Kenya Data Protection Act 2019 — privacy safeguards for National ID & PII.

This module centralises every safeguard so the rest of the codebase never
handles a raw national ID, records consent, or accesses PII without going
through here. Key principles enforced:

  • Minimisation  — national IDs are masked in every API response; only the
    last 4 digits are ever shown to a member.
  • Hashed lookup — a HMAC-SHA256 of the national ID is stored for uniqueness
    / duplicate checks, so plaintext never lands in a database index.
  • Consent proof — every consent decision is written to an immutable audit
    row (KYCConsentRecord) that can be produced during a DPA audit.
  • Retention     — every verification record carries a data_retention_until
    date; expired documents can be purged by a scheduled job.
  • Access log    — each time a staff member opens the raw ID/selfie file we
    record who and when (pii_last_accessed_at / pii_last_accessed_by).
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# National ID hashing & masking
# ─────────────────────────────────────────────────────────────────────────────
def hash_national_id(national_id: str) -> str:
    """
    Return a HMAC-SHA256 hex digest of the national ID using SECRET_KEY as the
    keyed salt. This lets us detect duplicates and assert uniqueness without
    ever storing or indexing the plaintext ID in the database.
    """
    key = (settings.SECRET_KEY or "").encode()
    return hmac.new(key, national_id.strip().encode(), hashlib.sha256).hexdigest()


def mask_national_id(national_id: str) -> str:
    """Show only the last 4 digits, e.g. '*******1234'. Empty input → ''."""
    if not national_id:
        return ""
    n = len(national_id)
    if n <= 4:
        return "*" * n
    return "*" * (n - 4) + national_id[-4:]


def mask_phone(phone: str) -> str:
    """Mask the middle of a phone number, e.g. '0722****007'."""
    if not phone:
        return ""
    if len(phone) <= 7:
        return "*" * len(phone)
    return phone[:4] + "****" + phone[-3:]


# ─────────────────────────────────────────────────────────────────────────────
# Retention dates
# ─────────────────────────────────────────────────────────────────────────────
def retention_date(from_date=None) -> date:
    """
    Earliest date the raw ID / selfie files may be deleted, based on the
    configured retention window (KYC_DOCUMENT_RETENTION_DAYS, default 730).
    """
    days = int(getattr(settings, "KYC_DOCUMENT_RETENTION_DAYS", 730))
    base = from_date or timezone.now().date()
    if hasattr(base, "date"):
        base = base.date()
    return base + timedelta(days=days)


# ─────────────────────────────────────────────────────────────────────────────
# Consent recording (immutable audit trail)
# ─────────────────────────────────────────────────────────────────────────────
def record_consent(user, purpose: str, consent_given: bool, request=None, version: str = "1.0"):
    """
    Persist an immutable KYCConsentRecord. Returns the created record.
    Call this every time a member grants or withdraws consent for a purpose.
    """
    from accounts.models import KYCConsentRecord

    ip, ua = None, ""
    if request is not None:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
        ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:300]

    record = KYCConsentRecord.objects.create(
        user=user, purpose=purpose, consent_given=consent_given,
        consent_text_version=version, ip_address=ip, user_agent=ua,
    )
    # Also write an audit log entry.
    from accounts.models import AuditLog
    AuditLog.log(
        actor=user, action="kyc_consent_recorded",
        target=f"Consent #{record.pk}",
        details={"purpose": purpose, "consent_given": consent_given, "version": version},
        request=request,
    )
    return record


# ─────────────────────────────────────────────────────────────────────────────
# PII access logging
# ─────────────────────────────────────────────────────────────────────────────
def log_pii_access(verification, accessor):
    """
    Record that a staff member viewed the raw ID documents / selfie on a
    verification record. Called by the protected-media view before serving a
    sensitive file.
    """
    from accounts.models import AuditLog

    verification.pii_last_accessed_at = timezone.now()
    verification.pii_last_accessed_by = accessor
    verification.save(update_fields=["pii_last_accessed_at", "pii_last_accessed_by"])
    AuditLog.log(
        actor=accessor, action="kyc_pii_accessed",
        target=f"IDVerification #{verification.pk}",
        details={"owner": verification.user.username},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data export (right to portability) & erasure (right to be forgotten)
# ─────────────────────────────────────────────────────────────────────────────
def export_member_pii(user) -> dict:
    """
    Collect all personal data held about a member for a DPA data-portability
    request. Returns a JSON-serialisable dict. Never include raw ID document
    file bytes here — only metadata and a flag that the file exists.
    """
    from accounts.models import IDVerification, KYCConsentRecord, MemberReference, DeviceFingerprint

    data = {
        "account": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "recovery_email": user.recovery_email,
            "recovery_phone": mask_phone(user.recovery_phone) if user.recovery_phone else "",
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        }
    }

    try:
        member = user.member_profile
        data["member"] = {
            "member_number": member.member_number,
            "national_id": mask_national_id(member.national_id),
            "phone_number": mask_phone(member.phone_number),
            "gender": member.gender,
            "date_of_birth": member.date_of_birth.isoformat(),
            "county": member.county,
            "address": member.address,
            "status": member.status,
            "date_joined": member.date_joined.isoformat(),
        }
    except Exception:
        data["member"] = None

    try:
        v = user.id_verification
        data["id_verification"] = {
            "status": v.status,
            "national_id": mask_national_id(v.national_id),
            "provider": v.provider,
            "face_match_score": v.face_match_score,
            "has_id_front": bool(v.id_document_front),
            "has_id_back": bool(v.id_document_back),
            "has_selfie": bool(v.selfie),
            "member_consent": v.member_consent,
            "consented_at": v.consented_at.isoformat() if v.consented_at else None,
            "submitted_at": v.submitted_at.isoformat() if v.submitted_at else None,
            "verified_at": v.verified_at.isoformat() if v.verified_at else None,
            "data_retention_until": v.data_retention_until.isoformat() if v.data_retention_until else None,
        }
    except IDVerification.DoesNotExist:
        data["id_verification"] = None

    refs_out = MemberReference.objects.filter(applicant=user).values(
        "referee__username", "relationship", "status", "requested_at", "responded_at",
    )
    data["references_requested"] = list(refs_out)

    refs_in = MemberReference.objects.filter(referee=user).values(
        "applicant__username", "relationship", "status", "requested_at", "responded_at",
    )
    data["references_received"] = list(refs_in)

    data["devices"] = list(
        DeviceFingerprint.objects.filter(user=user).values(
            "device_id", "device_model", "platform", "first_seen", "last_seen",
        )
    )

    data["consents"] = list(
        KYCConsentRecord.objects.filter(user=user).values(
            "purpose", "consent_given", "consent_text_version", "timestamp",
        )
    )

    return data


def request_erasure(user, request=None):
    """
    Handle a right-to-erasure request. We DO NOT hard-delete financial records
    (ledger entries, loans) — those are retained by law. We instead:
      • redact the raw national_id on Member and IDVerification (replaced with mask)
      • delete the uploaded ID/selfie image files
      • keep an audit log entry recording the erasure.
    The member account itself is deactivated, not deleted.
    Returns a summary dict.
    """
    from accounts.models import IDVerification, AuditLog
    import os

    summary = {"redacted": [], "files_removed": [], "deactivated": False}

    try:
        member = user.member_profile
        if member.national_id:
            member.national_id = mask_national_id(member.national_id)
            member.save(update_fields=["national_id"])
            summary["redacted"].append("member.national_id")
    except Exception:
        pass

    try:
        v = user.id_verification
        for field_name in ("id_document", "id_document_front", "id_document_back", "selfie"):
            f = getattr(v, field_name, None)
            if f and f.name:
                try:
                    path = f.path
                    if path and os.path.exists(path):
                        os.remove(path)
                        summary["files_removed"].append(field_name)
                except Exception:
                    pass
                f.delete(save=False)
        v.national_id = mask_national_id(v.national_id)
        v.ocr_result = {}
        v.provider_response = {}
        v.save()
        summary["redacted"].append("id_verification.national_id")
    except IDVerification.DoesNotExist:
        pass

    user.is_active = False
    user.save(update_fields=["is_active"])
    summary["deactivated"] = True

    AuditLog.log(
        actor=user, action="kyc_erasure_requested",
        target=f"User {user.username}",
        details={"summary": summary}, request=request,
    )
    return summary
