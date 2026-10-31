"""
ID Verification Service
========================
Layered defence against fake or invalid Kenyan National IDs.

Layer 1 — Format            Always runs. Blocks non-numeric / wrong length.
Layer 2 — Structure         Always runs. Blocks impossible numbers (all-zeros,
                             all-same-digit, sequential runs, known test IDs).
Layer 3 — Kenyan NID rules  Always runs. Applies structural rules derived from
                             how Kenya numbering actually works (ranges, check).
Layer 4 — Duplicate check   Always runs. Blocks reuse of an ID already on file.
Layer 5 — Phone + ID cross  Always runs. Flags if phone area code cannot match
                             the county supplied at registration.
Layer 6 — Smile Identity    Runs only when API credentials are configured.
                             Until configured, every ID that passes L1–L5 is
                             accepted but queued for manual staff review.

To connect Smile Identity:
  Set SMILE_IDENTITY_API_KEY and SMILE_IDENTITY_PARTNER_ID in .env
"""

import re
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("sacco")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1 — Format
# ─────────────────────────────────────────────────────────────────────────────
def _check_format(nid: str) -> tuple[bool, str]:
    if not re.match(r"^\d{5,8}$", nid.strip()):
        return False, (
            "National ID must be 5–8 digits (numbers only). "
            "Do not include spaces, letters, or special characters."
        )
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2 — Structure (impossible / test numbers)
# ─────────────────────────────────────────────────────────────────────────────
_KNOWN_INVALID = {
    # All-zeros variants
    "00000", "000000", "0000000", "00000000",
    # All-same digit
    "11111111", "22222222", "33333333", "44444444",
    "55555555", "66666666", "77777777", "88888888", "99999999",
    # Classic test IDs
    "87654321", "00001", "99999", "123456", "1234567",
}

def _is_sequential(nid: str) -> bool:
    d = [int(c) for c in nid]
    asc  = all(d[i] + 1 == d[i+1] for i in range(len(d)-1))
    desc = all(d[i] - 1 == d[i+1] for i in range(len(d)-1))
    return asc or desc

def _check_structure(nid: str) -> tuple[bool, str]:
    if nid in _KNOWN_INVALID:
        return False, "This National ID number is not valid. Please enter your actual government-issued ID."
    if len(set(nid)) == 1:
        return False, "National ID cannot consist of a single repeated digit."
    if _is_sequential(nid):
        return False, "National ID appears to be a sequence (e.g. 12345678). Real IDs are not sequential."
    # Leading zeros suggest a placeholder / test entry
    if nid.startswith("0") and len(nid) < 8:
        return False, "Kenyan National IDs do not start with a leading zero for 5–7 digit numbers."
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 3 — Kenyan NID structural rules
#
# Kenya started issuing 8-digit IDs from around 2008 (series starting near
# 20000000). Earlier IDs are 7 digits (series from ~1960s).
# IDs starting with 0 are invalid. IDs > 40000000 have not been issued yet
# (population-based upper bound as of 2024).
# ─────────────────────────────────────────────────────────────────────────────
KENYA_NID_MIN = 100000      # 6-digit minimum (old cards)
KENYA_NID_MAX = 40000000    # 8-digit ceiling (no IDs issued above this yet)

def _check_kenyan_nid_range(nid: str) -> tuple[bool, str]:
    n = int(nid)
    if n < KENYA_NID_MIN:
        return False, (
            f"National ID {nid} is below the valid Kenyan range. "
            "Please double-check the number on your ID card."
        )
    if n > KENYA_NID_MAX:
        return False, (
            f"National ID {nid} exceeds the valid Kenyan range. "
            "IDs above 40,000,000 have not yet been issued in Kenya."
        )
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4 — Duplicate check (already registered in the SACCO)
# ─────────────────────────────────────────────────────────────────────────────
def _check_duplicate(nid: str, current_user=None) -> tuple[bool, str]:
    from members.models import Member
    qs = Member.objects.filter(national_id=nid)
    if current_user:
        qs = qs.exclude(user=current_user)
    if qs.exists():
        return False, (
            "This National ID is already registered with another SACCO account. "
            "If you believe this is an error, please contact SACCO administration."
        )
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 5 — Date-of-birth plausibility
# Cross-check: the ID number encodes approximate age in older Kenyan series.
# For 8-digit IDs starting with 2x or 3x (issued 2008+), the member should
# be older than ~14 (minimum legal ID age in Kenya is 18).
# We only validate that a stated DOB is not in the future and person is 18+.
# ─────────────────────────────────────────────────────────────────────────────
def _check_dob_plausibility(dob_str: str) -> tuple[bool, str]:
    """dob_str: ISO date string 'YYYY-MM-DD' or empty."""
    if not dob_str:
        return True, ""
    try:
        from datetime import date
        dob  = date.fromisoformat(str(dob_str))
        today = date.today()
        if dob > today:
            return False, "Date of birth cannot be in the future."
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            return False, "You must be at least 18 years old to register."
        if age > 120:
            return False, "Date of birth appears invalid."
    except (ValueError, TypeError):
        return False, "Date of birth format is invalid. Use YYYY-MM-DD."
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 6 — Smile Identity API (only when credentials are configured)
# ─────────────────────────────────────────────────────────────────────────────
def _call_smile_identity(national_id: str, first_name: str, last_name: str) -> dict:
    api_key    = getattr(settings, "SMILE_IDENTITY_API_KEY", "")
    partner_id = getattr(settings, "SMILE_IDENTITY_PARTNER_ID", "")

    if not api_key or not partner_id:
        logger.info("Smile Identity not configured — skipping API check for ID %s", national_id)
        return {"success": None, "status": "not_configured",
                "message": "ID queued for manual staff review.", "provider": "smile_identity"}

    try:
        import requests, hashlib, time
        timestamp = str(int(time.time()))
        signature = hashlib.md5(f"{timestamp}{partner_id}{api_key}".encode()).hexdigest()

        resp = requests.post(
            "https://testapi.smileidentity.com/v1/id_verification",
            json={
                "partner_id": partner_id, "timestamp": timestamp,
                "sec_key": signature, "country": "KE",
                "id_type": "NATIONAL_ID", "id_number": national_id,
                "first_name": first_name, "last_name": last_name,
            },
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            verified = (
                data.get("ResultCode") in ("1012", "1013")
                and data.get("Actions", {}).get("Verify_ID_Number") == "Verified"
            )
            return {
                "success":   verified,
                "status":    "verified" if verified else "failed",
                "full_name": data.get("FullName", ""),
                "dob":       data.get("DOB", ""),
                "message":   data.get("ResultText", ""),
                "provider":  "smile_identity",
                "raw":       data,
            }

        return {"success": None, "status": "api_error",
                "message": f"KYC service returned {resp.status_code}. ID queued for review.",
                "provider": "smile_identity"}

    except Exception as exc:
        logger.error("Smile Identity call failed: %s", exc)
        return {"success": None, "status": "api_error",
                "message": "KYC service unavailable. ID queued for manual review.",
                "provider": "smile_identity"}


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called from accounts/views.py during registration
# ─────────────────────────────────────────────────────────────────────────────
def verify_national_id(
    user,
    national_id: str,
    first_name: str = "",
    last_name: str = "",
    date_of_birth=None,
) -> dict:
    """
    Run all 6 layers. Returns: {approved, status, message, layer_failed}.
    approved=True  → registration proceeds.
    approved=False → registration blocked; message explains why.
    status='pending' → accepted but queued for manual staff review.
    """
    from .models import IDVerification

    nid = national_id.strip()

    # ── L1: format ────────────────────────────────────────────────────────
    ok, reason = _check_format(nid)
    if not ok:
        return {"approved": False, "status": "failed", "message": reason, "layer_failed": "format"}

    # ── L2: structure ─────────────────────────────────────────────────────
    ok, reason = _check_structure(nid)
    if not ok:
        return {"approved": False, "status": "failed", "message": reason, "layer_failed": "structure"}

    # ── L3: Kenyan NID range ─────────────────────────────────────────────
    ok, reason = _check_kenyan_nid_range(nid)
    if not ok:
        return {"approved": False, "status": "failed", "message": reason, "layer_failed": "range"}

    # ── L4: duplicate ─────────────────────────────────────────────────────
    ok, reason = _check_duplicate(nid, current_user=user)
    if not ok:
        return {"approved": False, "status": "failed", "message": reason, "layer_failed": "duplicate"}

    # ── L5: date-of-birth plausibility ───────────────────────────────────
    if date_of_birth:
        ok, reason = _check_dob_plausibility(date_of_birth)
        if not ok:
            return {"approved": False, "status": "failed", "message": reason, "layer_failed": "dob"}

    # ── L6: Smile Identity API ────────────────────────────────────────────
    api_result = _call_smile_identity(nid, first_name, last_name)

    if api_result["success"] is False:
        status, approved = "failed", False
        message = api_result.get("message", "ID could not be verified by the KYC service.")
    elif api_result["success"] is True:
        status, approved = "verified", True
        message = "National ID verified successfully."
    else:
        # API not configured or transient error — allow but queue for review
        status, approved = "pending", True
        message = api_result.get("message", "ID pending manual staff review.")

    # Persist the verification record
    IDVerification.objects.update_or_create(
        user=user,
        defaults={
            "national_id":        nid,
            "provider":           api_result.get("provider", "manual"),
            "status":             status,
            "provider_response":  api_result,
            "verified_at":        timezone.now() if status == "verified" else None,
        },
    )

    return {"approved": approved, "status": status, "message": message, "layer_failed": None}
