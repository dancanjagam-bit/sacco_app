"""Secure identity-document intake. OCR is advisory; no unapproved provider verifies ID."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


def run_id_verification(user, national_id, first_name="", last_name="", id_document_file=None,
                        id_document_back_file=None, selfie_file=None, date_of_birth=None,
                        member_consent=False, purpose="membership_onboarding"):
    from accounts.models import IDVerification, AuditLog
    from accounts.services.file_validator import validate_id_document, validate_selfie
    front=id_document_file
    back=id_document_back_file
    if front:
        try: validate_id_document(front)
        except ValidationError as exc: return {"approved":False,"status":"needs_review","message":" ".join(exc.messages)}
    if back:
        try: validate_id_document(back)
        except ValidationError as exc: return {"approved":False,"status":"needs_review","message":" ".join(exc.messages)}
    if selfie_file:
        try: validate_selfie(selfie_file)
        except ValidationError as exc: return {"approved":False,"status":"needs_review","message":" ".join(exc.messages)}
    if (front or back or selfie_file) and not member_consent:
        return {"approved":False,"status":"draft","message":"Consent is required before storing identity documents."}
    status="draft"
    with transaction.atomic():
        verification, _=IDVerification.objects.get_or_create(user=user,defaults={"national_id":national_id,"status":"draft"})
        verification.national_id=national_id
        verification.verification_purpose=purpose
        verification.member_consent=bool(member_consent)
        verification.consented_at=timezone.now() if member_consent else None
        verification.status=status
        if front:
            verification.id_document_front=front
        if back: verification.id_document_back=back
        if selfie_file: verification.selfie=selfie_file
        if front:
            verification.submitted_at=timezone.now()
        verification.save()
        if front:
            # OCR suggestions remain private to this member/staff; OCR never confirms identity.
            try:
                from accounts.services.ocr_pipeline import run_ocr
                ocr=run_ocr(verification.id_document_front.path)
                verification.ocr_result={"fields":ocr.get("fields",{}),"confidence":ocr.get("confidence",{})}
                verification.save(update_fields=["ocr_result","updated_at"])
            except Exception:
                verification.ocr_result={"fields":{},"available":False}
                verification.save(update_fields=["ocr_result","updated_at"])
            AuditLog.log(user,"id_verify_submit",f"IDVerification #{verification.pk}",
                         {"status":status,"purpose":purpose,"document_uploaded":True})
    return {"approved":True,"status":status,
            "message":"Document saved as a draft. Review the OCR suggestions and submit for staff review.",
            "ocr_result":verification.ocr_result}
