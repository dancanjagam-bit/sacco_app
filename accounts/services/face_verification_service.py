"""
Face Verification Service
=========================
Calls the Smile Identity SmartSelfie biometric API to compare a selfie
against the face on an uploaded ID document.

Uses:
  - SMILE_IDENTITY_API_KEY      (from settings / .env)
  - SMILE_IDENTITY_PARTNER_ID   (from settings / .env)
  - SMILE_IDENTITY_ENV          (sandbox | production, default: sandbox)
  - FACE_MATCH_THRESHOLD        (int 0-100, default: 70)

Never raises — transient failures return outcome="pending".
"""
import base64
import hashlib
import logging
import time
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

SANDBOX_URL    = "https://testapi.smileidentity.com/v1/smile_selfie"
PRODUCTION_URL = "https://api.smileidentity.com/v1/smile_selfie"


def _get_threshold() -> int:
    return int(getattr(settings, "FACE_MATCH_THRESHOLD", 70))


def _encode_file(file_obj) -> str:
    """Base64-encode a file-like object. Seeks to 0 first."""
    file_obj.seek(0)
    return base64.b64encode(file_obj.read()).decode("utf-8")


@dataclass
class FaceVerificationResult:
    face_match_score: float | None
    liveness_passed: bool
    outcome: str           # "matched" | "flagged" | "pending"
    raw_response: dict = field(default_factory=dict)


_PENDING_NO_CREDS = FaceVerificationResult(
    face_match_score=None,
    liveness_passed=False,
    outcome="pending",
    raw_response={"reason": "SmartSelfie credentials not configured"},
)


def verify(selfie_file, id_document_file) -> FaceVerificationResult:
    """
    Compare selfie against ID document face via Smile Identity SmartSelfie.
    Returns FaceVerificationResult; never raises.
    """
    api_key    = getattr(settings, "SMILE_IDENTITY_API_KEY", "")
    partner_id = getattr(settings, "SMILE_IDENTITY_PARTNER_ID", "")

    if not api_key or not partner_id:
        logger.info("Smile Identity credentials absent — skipping face verification")
        return _PENDING_NO_CREDS

    try:
        import requests

        env      = getattr(settings, "SMILE_IDENTITY_ENV", "sandbox").lower()
        endpoint = PRODUCTION_URL if env == "production" else SANDBOX_URL

        timestamp = str(int(time.time()))
        signature = hashlib.md5(f"{timestamp}{partner_id}{api_key}".encode()).hexdigest()

        selfie_b64    = _encode_file(selfie_file)
        id_doc_b64    = _encode_file(id_document_file)

        payload = {
            "partner_id":        partner_id,
            "timestamp":         timestamp,
            "sec_key":           signature,
            "country":           "KE",
            "id_type":           "NATIONAL_ID",
            "selfie_image":      selfie_b64,
            "id_document_image": id_doc_b64,
            "partner_params": {
                "job_id":   f"face_{timestamp}",
                "job_type": 4,  # SmartSelfie job type
            },
        }

        resp = requests.post(endpoint, json=payload, timeout=30)
        resp.raise_for_status()
        raw = resp.json()

        actions        = raw.get("Actions", raw.get("actions", {}))
        liveness_raw   = actions.get("Liveness_Check", actions.get("liveness_check", ""))
        liveness_passed = str(liveness_raw).lower() == "passed"

        confidence_raw = (
            actions.get("Confidence_Value")
            or actions.get("confidence_value")
            or actions.get("Selfie_To_ID_Document_Compare")
            or 0
        )
        try:
            face_match_score = float(confidence_raw)
        except (TypeError, ValueError):
            face_match_score = 0.0

        threshold = _get_threshold()

        if not liveness_passed:
            outcome = "flagged"
        elif face_match_score < threshold:
            outcome = "flagged"
        else:
            outcome = "matched"

        return FaceVerificationResult(
            face_match_score=face_match_score,
            liveness_passed=liveness_passed,
            outcome=outcome,
            raw_response=raw,
        )

    except Exception as exc:
        logger.error("Face verification failed: %s", exc)
        return FaceVerificationResult(
            face_match_score=None,
            liveness_passed=False,
            outcome="pending",
            raw_response={"error": str(exc)},
        )
