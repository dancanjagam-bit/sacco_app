"""
ID Verification Service
========================
Validates a Kenyan National ID through available checks:

1. Format check (5–8 digits, numeric only) — always runs
2. Known-invalid list (test IDs, sequential numbers) — always runs
3. Third-party KYC API (Smile Identity / future IPRS) — if configured
4. Manual fallback — admin reviews and approves

To connect a real KYC provider:
  1. Sign up at https://usesmileid.com/ (Smile Identity)
  2. Set SMILE_IDENTITY_API_KEY and SMILE_IDENTITY_PARTNER_ID in .env
  3. The call_smile_identity() function below will activate automatically

Current status: Format + heuristic checks only.
Real API call happens only when credentials are in .env.
"""

import re
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("sacco")


# ─────────────────────────────────────────────────────────────────────────────
# Basic format validator (mirrors the serializer check)
# ─────────────────────────────────────────────────────────────────────────────
def validate_id_format(national_id: str) -> tuple[bool, str]:
    """Returns (valid, reason)."""
    cleaned = national_id.strip()
    if not re.match(r"^\d{5,8}$", cleaned):
        return False, "National ID must be 5–8 digits (numbers only). Letters and special characters are not allowed."
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic rejection rules
# Known-invalid IDs that should never pass:
#   - All same digit (11111111, 22222222)
#   - Sequential (12345678, 87654321)
#   - Test IDs commonly used in dev
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_TEST_IDS = {
    "00000000", "11111111", "22222222", "33333333",
    "44444444", "55555555", "66666666", "77777777",
    "88888888", "99999999", "87654321",
    "00001", "99999",
}

def _is_sequential(nid: str) -> bool:
    digits = [int(d) for d in nid]
    asc  = all(digits[i] + 1 == digits[i + 1] for i in range(len(digits) - 1))
    desc = all(digits[i] - 1 == digits[i + 1] for i in range(len(digits) - 1))
    return asc or desc

def validate_id_heuristics(national_id: str) -> tuple[bool, str]:
    if national_id in KNOWN_TEST_IDS:
        return False, "This National ID number is not valid. Please enter your actual government-issued ID."
    if len(set(national_id)) == 1:
        return False, "National ID cannot consist of a single repeated digit."
    if _is_sequential(national_id):
        return False, "National ID appears to be a test number (sequential digits). Please enter your real ID."
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Smile Identity KYC API call
# Docs: https://docs.usesmileid.com/further-reading/verify-id-number
# ─────────────────────────────────────────────────────────────────────────────
def call_smile_identity(national_id: str, first_name: str, last_name: str) -> dict:
    """
    Call Smile Identity ID verification API.
    Returns: { success, status, full_name, dob, message }

    Only runs if SMILE_IDENTITY_API_KEY and SMILE_IDENTITY_PARTNER_ID are set.
    Falls back gracefully if the API is unavailable.
    """
    api_key    = getattr(settings, "SMILE_IDENTITY_API_KEY", "")
    partner_id = getattr(settings, "SMILE_IDENTITY_PARTNER_ID", "")

    if not api_key or not partner_id:
        # API not configured — return "not_checked" so manual review can proceed
        logger.info("Smile Identity not configured — skipping API verification for ID %s", national_id)
        return {
            "success":  None,
            "status":   "not_configured",
            "message":  "ID verification API not configured. ID will be manually reviewed by SACCO staff.",
            "provider": "smile_identity",
        }

    try:
        import requests
        import hashlib, time

        timestamp = str(int(time.time()))
        signature = hashlib.md5(f"{timestamp}{partner_id}{api_key}".encode()).hexdigest()

        payload = {
            "partner_id":   partner_id,
            "timestamp":    timestamp,
            "sec_key":      signature,
            "country":      "KE",
            "id_type":      "NATIONAL_ID",
            "id_number":    national_id,
            "first_name":   first_name,
            "last_name":    last_name,
        }

        resp = requests.post(
            "https://testapi.smileidentity.com/v1/id_verification",
            json=payload,
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            result_code = data.get("ResultCode", "")
            actions     = data.get("Actions", {})

            verified = result_code in ("1012", "1013") and actions.get("Verify_ID_Number") == "Verified"

            return {
                "success":   verified,
                "status":    "verified" if verified else "failed",
                "full_name": data.get("FullName", ""),
                "dob":       data.get("DOB", ""),
                "message":   data.get("ResultText", ""),
                "provider":  "smile_identity",
                "raw":       data,
            }
        else:
            logger.warning("Smile Identity returned %s for ID %s", resp.status_code, national_id)
            return {
                "success":  None,
                "status":   "api_error",
                "message":  f"KYC service returned error {resp.status_code}. ID will be manually reviewed.",
                "provider": "smile_identity",
            }

    except Exception as exc:
        logger.error("Smile Identity call failed: %s", exc)
        return {
            "success":  None,
            "status":   "api_error",
            "message":  "KYC service unavailable. ID will be manually reviewed.",
            "provider": "smile_identity",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Master verification function — called during registration
# ─────────────────────────────────────────────────────────────────────────────
def verify_national_id(user, national_id: str, first_name: str = "", last_name: str = "") -> dict:
    """
    Run all available checks for a National ID and save the result.
    Returns: { approved: bool, status: str, message: str }
    """
    from .models import IDVerification

    # Step 1: format
    ok, reason = validate_id_format(national_id)
    if not ok:
        return {"approved": False, "status": "failed", "message": reason}

    # Step 2: heuristics
    ok, reason = validate_id_heuristics(national_id)
    if not ok:
        return {"approved": False, "status": "flagged", "message": reason}

    # Step 3: third-party API (if configured)
    api_result = call_smile_identity(national_id, first_name, last_name)

    if api_result["success"] is False:
        # Definitive API rejection — block registration
        status   = "failed"
        approved = False
        message  = api_result.get("message", "ID could not be verified.")
    elif api_result["success"] is True:
        # Definitive API confirmation
        status   = "verified"
        approved = True
        message  = "National ID verified successfully."
    else:
        # API not configured or temporarily unavailable — allow registration
        # but flag for manual staff review
        status   = "pending"
        approved = True
        message  = api_result.get("message", "ID queued for manual verification by SACCO staff.")

    # Save record
    IDVerification.objects.update_or_create(
        user=user,
        defaults={
            "national_id":       national_id,
            "provider":          api_result.get("provider", "manual"),
            "status":            status,
            "provider_response": api_result,
            "verified_at":       timezone.now() if status == "verified" else None,
        },
    )

    return {"approved": approved, "status": status, "message": message}
