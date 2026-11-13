"""
accounts/auth_views.py
~~~~~~~~~~~~~~~~~~~~~~~
Custom JWT login view that enforces 2FA for admin/staff accounts.

Flow for MEMBERS:
  POST /api/token/ → { access, refresh }  (unchanged)

Flow for ADMINS/STAFF:
  POST /api/token/ → { requires_2fa: true, identifier: "<username>" }
  POST /api/login/2fa/ { identifier, code } → { access, refresh }

The OTP is sent via the configured delivery method (email or SMS) the moment
the admin's password is verified, before any token is returned.
"""
import logging
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.backends import ModelBackend
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OTPRequest
from sacco.notifications import send_otp as deliver_otp

logger = logging.getLogger("sacco")
User = get_user_model()


class LoginRateThrottle(AnonRateThrottle):
    """20 login attempts per hour per IP — blocks brute-force."""
    rate = "20/hour"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def custom_token_obtain(request):
    """
    Replace SimpleJWT's TokenObtainPairView with 2FA enforcement for admins.
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

    if not user_obj.check_password(password):
        return Response({"detail": "No active account found with the given credentials."}, status=401)

    if not user_obj.is_active:
        return Response({"detail": "Account is disabled."}, status=401)

    is_admin = (
        user_obj.is_staff
        or user_obj.is_superuser
        or getattr(user_obj, "is_admin", False)
    )

    if is_admin:
        # --- Admin path: send OTP, do NOT return tokens yet ---
        # Pick delivery method: prefer email, fall back to phone
        method = "email" if user_obj.email else "phone"
        otp = OTPRequest.generate(user_obj, method)
        deliver_otp(user_obj, otp.code, method)
        logger.info("2FA OTP sent for admin user %s via %s", user_obj.username, method)

        destination = user_obj.email if method == "email" else getattr(
            getattr(user_obj, "member_profile", None), "phone_number", ""
        )

        # Mask the destination for the response
        if method == "email" and destination:
            parts = destination.split("@")
            masked = parts[0][:2] + "***@" + parts[1]
        elif destination:
            masked = destination[:4] + "****" + destination[-3:]
        else:
            masked = "configured contact"

        return Response({
            "requires_2fa": True,
            "identifier":   user_obj.username,
            "method":       method,
            "sent_to":      masked,
            "message":      f"A verification code has been sent to {masked}. Enter it to complete login.",
        })

    # --- Member path: return tokens immediately ---
    refresh = RefreshToken.for_user(user_obj)

    from accounts.models import AuditLog
    AuditLog.log(user_obj, "login", request=request)

    return Response({
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    })
