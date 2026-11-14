"""
accounts/auth_views.py
~~~~~~~~~~~~~~~~~~~~~~~
Custom JWT login view that enforces 2FA for admin/staff accounts.

Flow for MEMBERS:
  POST /api/token/ → { access, refresh }  (unchanged)

Flow for STAFF:
  POST /api/token/ → { requires_2fa: true, challenge_token, delivery_status }
  POST /api/login/2fa/ { identifier, code } → { access, refresh }
  POST /api/login/2fa/resend/ { identifier, challenge_token } → updated challenge

No authentication token is issued until the login challenge is verified.
"""
import logging
import math
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuditLog, OTPRequest
from .access import requires_staff_login_2fa
from accounts.services.otp_delivery import dispatch_otp

logger = logging.getLogger("sacco")
User = get_user_model()


class LoginRateThrottle(AnonRateThrottle):
    """20 login attempts per hour per IP — blocks brute-force."""
    rate = "20/hour"


class LoginResendRateThrottle(AnonRateThrottle):
    """Limit repeated unauthenticated delivery retries from one IP."""
    rate = "10/hour"


LOGIN_2FA_COOLDOWN_SECONDS = 60
LOGIN_2FA_MAX_CODES_PER_HOUR = 5
LOGIN_2FA_CHALLENGE_MAX_AGE_SECONDS = 30 * 60
LOGIN_2FA_CHALLENGE_SALT = "sacco.login-2fa-resend"


def _masked_destination(user, method):
    destination = user.email if method == "email" else getattr(
        getattr(user, "member_profile", None), "phone_number", ""
    )
    if method == "email" and destination and "@" in destination:
        local, domain = destination.split("@", 1)
        return local[:2] + "***@" + domain
    if destination:
        return destination[:4] + "****" + destination[-3:]
    return "your registered contact"


def _login_challenge_token(otp):
    return signing.dumps(
        {"user_id": otp.user_id, "otp_id": otp.pk},
        salt=LOGIN_2FA_CHALLENGE_SALT,
        compress=True,
    )


def _login_challenge_response(user, otp, delivery, resend_after_seconds=LOGIN_2FA_COOLDOWN_SECONDS):
    destination = _masked_destination(user, otp.method)
    status = delivery["status"]
    channel = "email" if otp.method == "email" else "SMS"
    if status == "accepted":
        message = (
            f"Staff verification is required. The {channel} provider accepted a request for "
            f"{destination}; this does not confirm delivery to the inbox or handset. "
            "If it does not arrive, request another code after the countdown."
        )
    elif status == "unavailable":
        message = (
            f"Staff verification is required, but the {channel} delivery service is not configured. "
            "You can retry after the countdown or contact SACCO support."
        )
    else:
        message = (
            f"Staff verification is required, but the {channel} provider did not accept the request. "
            "You can retry after the countdown or contact SACCO support."
        )
    return Response({
        "requires_2fa": True,
        "account_workspace": "staff",
        "identifier": user.username,
        "method": otp.method,
        "masked_destination": destination,
        "delivery_status": status,
        "message": message,
        "challenge_token": _login_challenge_token(otp),
        "resend_after_seconds": max(0, int(resend_after_seconds)),
    })


def _login_otp_limit_wait(user, now=None):
    now = now or timezone.now()
    recent = OTPRequest.objects.filter(
        user=user,
        purpose="login_2fa",
        created_at__gte=now - timedelta(hours=1),
    ).order_by("created_at")
    if recent.count() < LOGIN_2FA_MAX_CODES_PER_HOUR:
        return 0
    oldest = recent.first()
    return max(1, math.ceil((oldest.created_at + timedelta(hours=1) - now).total_seconds()))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def custom_token_obtain(request):
    """
    Replace SimpleJWT's TokenObtainPairView with 2FA enforcement for staff.
    """
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")

    if not username or not password:
        return Response({"detail": "Username and password are required."}, status=400)

    # Case-insensitive lookup then password check
    try:
        user_obj = User.objects.get(username__iexact=username)
    except User.DoesNotExist:
        # Timing-safe: run the hasher anyway
        User().set_password(password)
        return Response({"detail": "No active account found with the given credentials."}, status=401)
    except User.MultipleObjectsReturned:
        # Two accounts share the same name differing only in case — fall back to
        # exact match to avoid ambiguity; if that also fails, treat as not found.
        try:
            user_obj = User.objects.get(username=username)
        except User.DoesNotExist:
            User().set_password(password)
            return Response({"detail": "No active account found with the given credentials."}, status=401)

    if not user_obj.check_password(password):
        return Response({"detail": "No active account found with the given credentials."}, status=401)

    if not user_obj.is_active:
        return Response({"detail": "Account is disabled."}, status=401)

    if requires_staff_login_2fa(user_obj):
        # Staff sign-in always requires a second factor. A provider acceptance is
        # not treated as proof that the message reached the recipient.
        now = timezone.now()
        current = OTPRequest.objects.filter(
            user=user_obj,
            purpose="login_2fa",
            used=False,
        ).order_by("-created_at").first()
        if current:
            last_attempt = current.delivery_attempted_at or current.created_at
            wait = math.ceil((last_attempt + timedelta(seconds=LOGIN_2FA_COOLDOWN_SECONDS) - now).total_seconds())
            if wait > 0:
                return _login_challenge_response(
                    user_obj,
                    current,
                    {"status": current.delivery_status, "reason_code": current.delivery_reason},
                    resend_after_seconds=wait,
                )

        retry_after = _login_otp_limit_wait(user_obj)
        if retry_after:
            return Response(
                {"detail": "Too many verification requests. Wait before trying again."},
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        # Determine available delivery channels for this staff account.
        # Phone comes from member_profile.phone_number or the recovery_phone field.
        staff_phone = (
            getattr(getattr(user_obj, "member_profile", None), "phone_number", "")
            or user_obj.recovery_phone
        )
        has_email = bool(user_obj.email)
        has_phone = bool(staff_phone)

        if has_email:
            method = "email"
        elif has_phone:
            method = "phone"
        else:
            # No delivery channel at all — still generate an OTP so the response
            # shape is consistent; delivery will come back as unavailable.
            method = "email"

        otp = OTPRequest.generate(user_obj, method, purpose="login_2fa")
        delivery = dispatch_otp(otp)
        logger.info("2FA OTP delivery status=%s via %s", delivery["status"], method)

        # If the primary channel failed or is unavailable, try SMS as a fallback
        # (only if we haven't already used phone and the user has a number).
        if delivery["status"] != "accepted" and method == "email" and has_phone:
            logger.info("Email delivery unavailable — falling back to SMS for 2FA")
            otp = OTPRequest.generate(user_obj, "phone", purpose="login_2fa")
            delivery = dispatch_otp(otp)
            logger.info("2FA OTP SMS fallback delivery status=%s", delivery["status"])

        if delivery["status"] != "accepted":
            AuditLog.log(
                user_obj,
                "otp_delivery_failure",
                "login_2fa",
                details={"reason_code": delivery["reason_code"]},
                request=request,
            )
        return _login_challenge_response(user_obj, otp, delivery)

    # --- Member path: return tokens immediately ---
    refresh = RefreshToken.for_user(user_obj)

    AuditLog.log(user_obj, "login", request=request)

    return Response({
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginResendRateThrottle])
def resend_login_2fa(request):
    """Resend only for a signed, short-lived challenge returned after password validation."""
    identifier = request.data.get("identifier", "")
    challenge_token = request.data.get("challenge_token", "")
    if not isinstance(identifier, str) or not isinstance(challenge_token, str):
        return Response({"detail": "This verification request is invalid. Sign in again."}, status=400)
    identifier = identifier.strip()
    if not identifier or len(identifier) > 150 or not challenge_token or len(challenge_token) > 2048:
        return Response({"detail": "This verification request is invalid. Sign in again."}, status=400)

    try:
        payload = signing.loads(
            challenge_token,
            salt=LOGIN_2FA_CHALLENGE_SALT,
            max_age=LOGIN_2FA_CHALLENGE_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        return Response({"detail": "This verification request has expired. Sign in again."}, status=400)

    if not isinstance(payload, dict):
        return Response({"detail": "This verification request is invalid. Sign in again."}, status=400)
    user = User.objects.filter(
        pk=payload.get("user_id"),
        username__iexact=identifier,
    ).first()
    if not user or not user.is_active or not (
        user.is_staff or user.is_superuser or getattr(user, "is_admin", False)
    ):
        return Response({"detail": "This verification request is invalid. Sign in again."}, status=400)

    now = timezone.now()
    with transaction.atomic():
        current = OTPRequest.objects.select_for_update().filter(
            pk=payload.get("otp_id"),
            user=user,
            purpose="login_2fa",
            used=False,
        ).first()
        if not current:
            return Response({"detail": "This verification request has expired. Sign in again."}, status=400)

        last_attempt = current.delivery_attempted_at or current.created_at
        wait = math.ceil((last_attempt + timedelta(seconds=LOGIN_2FA_COOLDOWN_SECONDS) - now).total_seconds())
        if wait > 0:
            return Response(
                {"detail": "Please wait before requesting another verification code.", "retry_after": wait},
                status=429,
                headers={"Retry-After": str(wait)},
            )

        retry_after = _login_otp_limit_wait(user, now=now)
        if retry_after:
            return Response(
                {"detail": "Too many verification requests. Wait before trying again.", "retry_after": retry_after},
                status=429,
                headers={"Retry-After": str(retry_after)},
            )

        # Compare-and-set makes a repeated request using this same challenge
        # unable to create a second code, even when requests arrive together.
        consumed = OTPRequest.objects.filter(pk=current.pk, user=user, used=False).update(used=True)
        if consumed != 1:
            return Response({"detail": "This verification request has expired. Sign in again."}, status=400)
        otp = OTPRequest.generate(user, current.method, purpose="login_2fa")

    delivery = dispatch_otp(otp)
    logger.info("2FA OTP resend delivery status=%s via %s", delivery["status"], otp.method)
    if delivery["status"] != "accepted":
        AuditLog.log(
            user,
            "otp_delivery_failure",
            "login_2fa_resend",
            details={"reason_code": delivery["reason_code"]},
            request=request,
        )
    return _login_challenge_response(user, otp, delivery)
