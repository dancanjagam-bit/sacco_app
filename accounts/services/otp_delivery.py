"""Safely record OTP-provider submission outcomes without storing payloads."""
import logging

from django.utils import timezone

from sacco.notifications import send_otp

logger = logging.getLogger("sacco")


def dispatch_otp(otp):
    try:
        outcome = send_otp(otp.user, otp.code, otp.method)
    except Exception as exc:
        # Provider exceptions are recorded without message contents, recipient
        # details, credentials, or the one-time code.
        logger.error("OTP provider dispatch failed (%s)", type(exc).__name__)
        outcome = {"status": "failed", "reason_code": "provider_error"}
    outcome = outcome if isinstance(outcome, dict) else {
        "status": "failed", "reason_code": "invalid_delivery_result",
    }
    status = outcome.get("status")
    if status not in {"accepted", "unavailable", "failed"}:
        status = "failed"
    reason = str(outcome.get("reason_code") or "")[:40]
    otp.delivery_status = status
    otp.delivery_reason = reason
    otp.delivery_attempted_at = timezone.now()
    otp.save(update_fields=("delivery_status", "delivery_reason", "delivery_attempted_at"))
    return {"status": status, "reason_code": reason}
