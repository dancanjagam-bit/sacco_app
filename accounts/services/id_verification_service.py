"""
ID Verification Service Orchestrator
=====================================
Chains file validation → OCR → name matching → Smile Identity KYC
→ face verification (if selfie provided).

Called from the registration view after RegistrationSerializer validates
non-file fields.
"""
import logging
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger(__name__)


def run_id_verification(
    user,
    national_id: str,
    first_name: str,
    last_name: str,
    id_document_file=None,
    selfie_file=None,
    date_of_birth=None,
) -> dict:
    from accounts.models import IDVerification, AuditLog, Notification, StaffProfile
    from accounts.services.file_validator import validate_id_document, validate_selfie
    from accounts.services.ocr_pipeline import run_ocr
    from accounts.services.name_matcher import match_names
    from accounts.id_verification import (
        _check_format, _check_structure, _check_kenyan_nid_range,
        _check_duplicate, _check_dob_plausibility,
        _call_smile_identity as call_smile_identity,
    )

    # ── Pre-flight: run all non-API layers immediately ────────────────────
    for check_fn, args in [
        (_check_format,            (national_id,)),
        (_check_structure,         (national_id,)),
        (_check_kenyan_nid_range,  (national_id,)),
        (_check_duplicate,         (national_id, user)),
        (_check_dob_plausibility,  (str(date_of_birth) if date_of_birth else "",)),
    ]:
        ok, reason = check_fn(*args)
        if not ok:
            return {"approved": False, "status": "failed", "message": reason, "ocr_result": {}}

    # Step 1: validate id_document
    if id_document_file:
        try:
            validate_id_document(id_document_file)
        except ValidationError as exc:
            return {"approved": False, "status": "failed", "message": " ".join(exc.messages), "ocr_result": {}}

    # Step 2: validate selfie
    if selfie_file:
        try:
            validate_selfie(selfie_file)
        except ValidationError as exc:
            return {"approved": False, "status": "failed", "message": " ".join(exc.messages), "ocr_result": {}}

    # Step 3: create / update IDVerification record
    verification, _ = IDVerification.objects.update_or_create(
        user=user,
        defaults={"national_id": national_id, "provider": "smile_identity", "status": "pending"},
    )
    if id_document_file:
        verification.id_document = id_document_file
    if selfie_file:
        verification.selfie = selfie_file
    verification.save()

    # Step 4: OCR
    ocr_result = {}
    if id_document_file and verification.id_document:
        try:
            ocr_result = run_ocr(verification.id_document.path)
            verification.ocr_result = ocr_result
            verification.save(update_fields=["ocr_result"])
        except Exception as exc:
            logger.warning("OCR processing failed (%s)", type(exc).__name__)

    # Step 5: ID number cross-check (OCR vs form)
    ocr_id_number = (ocr_result.get("fields") or {}).get("id_number")
    if ocr_id_number and ocr_id_number.strip() != national_id.strip():
        # The number on the uploaded document does not match what was typed
        verification.status = "flagged"
        verification.failure_reason = (
            "The ID number suggested from your uploaded document does not match the number you entered. "
            "Review the details or ask SACCO staff for help."
        )
        verification.ocr_result = ocr_result
        verification.save()
        AuditLog.log(actor=user, action="id_verify_submit",
                     target=f"IDVerification #{verification.pk}",
                     details={
                         "idverification_id": verification.pk,
                         "status": "flagged",
                         "reason": "id_number_mismatch",
                     })
        _notify_member(user, "flagged")
        _notify_staff(user, "flagged")
        return {
            "approved": False,
            "status":   "flagged",
            "message":  verification.failure_reason,
            "ocr_result": ocr_result,
        }

    # Step 5b: name matching
    ocr_name = (ocr_result.get("fields") or {}).get("full_name")
    form_name = f"{first_name} {last_name}".strip()
    name_flagged = False
    if ocr_name:
        matched, score = match_names(ocr_name, form_name)
        if not matched:
            name_flagged = True

    # Step 6: Smile Identity KYC
    api_result = call_smile_identity(national_id, first_name, last_name)

    if api_result["success"] is False:
        verification.status = "failed"
        verification.failure_reason = api_result.get("message", "ID could not be verified.")
        verification.provider_response = api_result
        verification.save()
        AuditLog.log(actor=user, action="id_verify_submit",
                     target=f"IDVerification #{verification.pk}",
                     details={"idverification_id": verification.pk, "status": "failed", "provider": "smile_identity"})
        _notify_member(user, "failed")
        return {"approved": False, "status": "failed", "message": verification.failure_reason, "ocr_result": ocr_result}

    interim_status = "pending" if api_result["success"] is None else ("flagged" if name_flagged else "pending_face_check")

    # Step 7: face verification
    final_status = interim_status
    if selfie_file and id_document_file:
        try:
            from accounts.services.face_verification_service import verify as face_verify
            face_result = face_verify(selfie_file, id_document_file)
            verification.face_match_score = face_result.face_match_score
            merged = dict(api_result)
            merged["smart_selfie"] = face_result.raw_response
            verification.provider_response = merged
            AuditLog.log(actor=user, action="face_verify",
                         target=f"IDVerification #{verification.pk}",
                         details={"idverification_id": verification.pk,
                                  "outcome": face_result.outcome,
                                  "face_match_score": face_result.face_match_score,
                                  "liveness_passed": face_result.liveness_passed})
            if face_result.outcome == "flagged":
                final_status = "flagged"
            elif face_result.outcome == "pending":
                if final_status not in ("flagged",):
                    final_status = "pending"
            else:  # matched
                if final_status == "pending_face_check":
                    final_status = "verified"
        except Exception as exc:
            logger.error("Face verification processing failed (%s)", type(exc).__name__)
            if final_status == "pending_face_check":
                final_status = "pending"
    else:
        if final_status == "pending_face_check":
            final_status = "pending"

    if final_status == "pending_face_check":
        final_status = "pending"

    verification.status = final_status
    verification.provider_response = verification.provider_response or api_result
    if final_status == "verified":
        verification.verified_at = timezone.now()
    verification.save()

    AuditLog.log(actor=user, action="id_verify_submit",
                 target=f"IDVerification #{verification.pk}",
                 details={"idverification_id": verification.pk, "status": final_status, "provider": "smile_identity"})
    _notify_member(user, final_status)
    _notify_staff(user, final_status)

    messages_map = {
        "verified": "Your identity has been verified successfully.",
        "pending":  "Registration complete. SACCO staff will review your ID shortly.",
        "flagged":  "Registration complete. Your identity details need staff review.",
    }
    return {
        "approved": final_status != "failed",
        "status":   final_status,
        "message":  messages_map.get(final_status, "Registration submitted."),
        "ocr_result": ocr_result,
    }


def _notify_member(user, status: str):
    from accounts.models import Notification
    titles = {"verified": "Identity Verified", "failed": "Identity Verification Failed",
               "flagged": "Identity Under Review", "pending": "Registration Pending Review"}
    types  = {"verified": "success", "failed": "error", "flagged": "warning", "pending": "info"}
    Notification.send(user=user, title=titles.get(status, "Registration Update"),
                      message=f"Your ID verification status: {status}.",
                      ntype=types.get(status, "info"))


def _notify_staff(user, status: str):
    from accounts.models import Notification, StaffProfile
    if status not in ("flagged", "pending"):
        return
    for sp in StaffProfile.objects.filter(status="active").select_related("user"):
        Notification.send(user=sp.user,
                          title="New ID Verification Requires Review",
                          message=f"Member {user.get_full_name() or user.username} — status: {status}.",
                          ntype="warning")
