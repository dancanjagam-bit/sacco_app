from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from members.models import Member
from core.models import Savings, Loan
from .models import OTPRequest, StaffProfile, Notification, AuditLog
from sacco.notifications import (
    send_otp as deliver_otp,
    send_welcome,
)
from accounts.services.id_verification_service import run_id_verification

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Permissions
# ─────────────────────────────────────────────────────────────────────────────
class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and (
                getattr(request.user, "is_admin", False)
                or request.user.is_staff
                or request.user.is_superuser
            )
        )


class IsSuperAdmin(BasePermission):
    """Only superuser or users with role='superadmin' can manage staff."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        try:
            return request.user.staff_profile.role == "superadmin"
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Helper: look up a user by username or email
# ─────────────────────────────────────────────────────────────────────────────
def _find_user(identifier: str):
    try:
        return User.objects.get(username=identifier)
    except User.DoesNotExist:
        pass
    try:
        return User.objects.get(email__iexact=identifier)
    except User.DoesNotExist:
        pass
    return None


def _send_otp(otp):
    destination = {
        "email":          otp.user.email,
        "recovery_email": otp.user.recovery_email,
        "phone":          getattr(getattr(otp.user, "member_profile", None), "phone_number", ""),
        "recovery_phone": otp.user.recovery_phone,
    }.get(otp.method, "")

    print(f"\n{'='*50}")
    print(f"  OTP CODE:  {otp.code}")
    print(f"  Via:       {otp.method}  ->  {destination}")
    print(f"  Expires:   {OTPRequest.EXPIRY_MINUTES} minutes")
    print(f"{'='*50}\n")

    return destination


def _mask(value: str) -> str:
    if "@" in value:
        local, domain = value.split("@", 1)
        return local[:2] + "***@" + domain
    if len(value) >= 6:
        return value[:3] + "****" + value[-3:]
    return "****"


def _profile_response(user):
    try:
        member = user.member_profile
    except Member.DoesNotExist:
        member = None

    staff_role = None
    try:
        staff_role = user.staff_profile.role
    except Exception:
        pass

    total_savings  = Savings.objects.filter(user=user).aggregate(t=Sum("amount"))["t"] or 0
    total_loans    = Loan.objects.filter(user=user).count()
    approved_loans = Loan.objects.filter(user=user, status="approved").count()

    return {
        "username":        user.username,
        "first_name":      user.first_name,
        "last_name":       user.last_name,
        "email":           user.email,
        "recovery_email":  user.recovery_email,
        "recovery_phone":  user.recovery_phone,
        "is_staff":        user.is_staff,
        "is_superuser":    user.is_superuser,
        "is_admin":        user.is_admin,
        "staff_role":      staff_role,
        "member_number":   member.member_number  if member else None,
        "phone_number":    member.phone_number   if member else None,
        "gender":          member.gender         if member else None,
        "date_of_birth":   str(member.date_of_birth)  if member else None,
        "county":          member.county         if member else None,
        "address":         member.address        if member else None,
        "status":          member.status         if member else None,
        "date_joined":     str(member.date_joined) if member else None,
        "total_savings":   total_savings,
        "total_loans":     total_loans,
        "approved_loans":  approved_loans,
    }


# ═════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    from .serializers import RegistrationSerializer

    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    member_number = None
    id_check      = {}

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=data["username"],
                password=data["password"],
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                email=data.get("email", ""),
                recovery_email=data.get("recovery_email", ""),
                recovery_phone=data.get("recovery_phone", ""),
            )

            last_id = Member.objects.aggregate(max_id=Max("id"))["max_id"] or 0
            member_number = f"SACCO{last_id + 1:06d}"

            Member.objects.create(
                user=user,
                member_number=member_number,
                national_id=data["national_id"],
                phone_number=data["phone_number"],
                gender=data["gender"],
                date_of_birth=data["date_of_birth"],
                county=data["county"],
                address=data["address"],
            )

            # ── ID Verification ──────────────────────────────────────────
            id_document_file = request.FILES.get("id_document")
            selfie_file      = request.FILES.get("selfie")
            id_check = run_id_verification(
                user=user,
                national_id=data["national_id"],
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                id_document_file=id_document_file,
                selfie_file=selfie_file,
            )

            if id_check.get("approved") is False:
                raise ValueError(id_check.get("message", "ID verification failed."))

            Notification.send(user, "Welcome to SACCO!", f"Your member number is {member_number}.", "success", "/dashboard")
            AuditLog.log(user, "register", f"Member {member_number}", {"username": user.username}, request)
            send_welcome(user, member_number)

    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)

    return Response({
        "message":       "Registration successful",
        "member_number": member_number,
        "id_status":     id_check.get("status", "pending"),
        "id_message":    id_check.get("message", ""),
    })


# ═════════════════════════════════════════════════════════════════════════════
# LOGOUT  (blacklists refresh token)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    refresh_token = request.data.get("refresh")
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            pass
    AuditLog.log(request.user, "logout", request=request)
    return Response({"message": "Logged out successfully."})


# ═════════════════════════════════════════════════════════════════════════════
# 2FA LOGIN — step 2 (admin accounts only)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([AllowAny])
def login_2fa(request):
    """
    Admin users with 2FA enabled get a short-lived token after password login
    and must call this endpoint with their OTP to get a full-access token.
    For now: any admin login triggers 2FA.
    """
    from .serializers import VerifyOTPSerializer
    from rest_framework_simplejwt.tokens import RefreshToken as JWTRefresh

    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    code       = serializer.validated_data["code"]

    user = _find_user(identifier)
    if not user:
        return Response({"error": "Invalid request."}, status=400)

    otp = (
        OTPRequest.objects.filter(user=user, code=code, used=False)
        .order_by("-created_at").first()
    )

    if not otp:
        return Response({"error": "Invalid OTP."}, status=400)
    if otp.is_expired:
        return Response({"error": "OTP expired. Please log in again."}, status=400)

    otp.used = True
    otp.save()

    refresh = JWTRefresh.for_user(user)
    AuditLog.log(user, "login", "2FA verified", request=request)

    return Response({
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
        "message": "2FA verified. Login successful.",
    })


# ═════════════════════════════════════════════════════════════════════════════
# CHANGE PASSWORD (authenticated)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    from .serializers import ChangePasswordSerializer

    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if not request.user.check_password(data["old_password"]):
        return Response({"old_password": "Incorrect current password."}, status=400)

    request.user.set_password(data["new_password"])
    request.user.save()
    AuditLog.log(request.user, "password_change", request=request)

    return Response({"message": "Password changed successfully."})


# ═════════════════════════════════════════════════════════════════════════════
# PROFILE
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def profile(request):
    if request.method == "GET":
        return Response(_profile_response(request.user))

    from .serializers import ProfileUpdateSerializer

    serializer = ProfileUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = request.user
    for field in ["first_name", "last_name", "email", "recovery_email", "recovery_phone"]:
        if field in data:
            setattr(user, field, data[field])
    user.save()

    try:
        member = user.member_profile
        for field in ["phone_number", "county", "address"]:
            if field in data:
                setattr(member, field, data[field])
        member.save()
    except Member.DoesNotExist:
        pass

    AuditLog.log(user, "member_update", f"Member {user.username}", request=request)
    return Response(_profile_response(user))


# ═════════════════════════════════════════════════════════════════════════════
# STAFF MANAGEMENT (SuperAdmin only)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET", "POST"])
@permission_classes([IsSuperAdmin])
def staff_list(request):
    if request.method == "GET":
        staffers = StaffProfile.objects.select_related("user", "created_by").all()
        return Response([
            {
                "id":           s.id,
                "user_id":      s.user.id,
                "username":     s.user.username,
                "full_name":    s.user.get_full_name(),
                "email":        s.user.email,
                "role":         s.role,
                "role_label":   s.get_role_display(),
                "department":   s.department,
                "hire_date":    s.hire_date,
                "status":       s.status,
                "is_active":    s.user.is_active,
                "created_at":   s.created_at,
                "created_by":   s.created_by.get_full_name() if s.created_by else "",
            }
            for s in staffers
        ])

    # POST — create new staff account
    from .serializers import CreateStaffSerializer

    serializer = CreateStaffSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    d = serializer.validated_data

    with transaction.atomic():
        new_user = User.objects.create_user(
            username=d["username"],
            password=d["password"],
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            email=d.get("email", ""),
            is_staff=True,
            is_admin=True,
        )

        staff = StaffProfile.objects.create(
            user=new_user,
            role=d["role"],
            department=d.get("department", ""),
            hire_date=d.get("hire_date"),
            created_by=request.user,
        )

        Notification.send(
            new_user, "Staff Account Created",
            f"Your SACCO staff account has been created with role: {staff.get_role_display()}.",
            "success",
        )
        AuditLog.log(request.user, "staff_create", f"Staff {new_user.username}", {
            "role": staff.role, "created_by": request.user.username,
        }, request)

    return Response({
        "message": f"Staff account created for {new_user.get_full_name() or new_user.username}.",
        "username": new_user.username,
        "role":     staff.role,
    }, status=201)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsSuperAdmin])
def staff_detail(request, staff_id):
    try:
        staff = StaffProfile.objects.select_related("user").get(id=staff_id)
    except StaffProfile.DoesNotExist:
        return Response({"error": "Staff member not found."}, status=404)

    if request.method == "GET":
        return Response({
            "id":         staff.id,
            "username":   staff.user.username,
            "full_name":  staff.user.get_full_name(),
            "email":      staff.user.email,
            "role":       staff.role,
            "role_label": staff.get_role_display(),
            "department": staff.department,
            "hire_date":  staff.hire_date,
            "status":     staff.status,
            "is_active":  staff.user.is_active,
        })

    if request.method == "PUT":
        from .serializers import UpdateStaffSerializer

        serializer = UpdateStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        if "role" in d:       staff.role       = d["role"]
        if "department" in d: staff.department = d["department"]
        if "hire_date" in d:  staff.hire_date  = d["hire_date"]
        if "status" in d:
            staff.status = d["status"]
            staff.user.is_active = (d["status"] == "active")
            staff.user.save()
        staff.save()

        AuditLog.log(request.user, "staff_update", f"Staff {staff.user.username}", d, request)
        return Response({"message": "Staff account updated."})

    # DELETE — soft deactivate, never hard delete
    if request.method == "DELETE":
        if staff.user == request.user:
            return Response({"error": "You cannot deactivate your own account."}, status=400)
        staff.status = "inactive"
        staff.user.is_active = False
        staff.user.is_staff  = False
        staff.user.is_admin  = False
        staff.user.save()
        staff.save()
        AuditLog.log(request.user, "staff_deactivate", f"Staff {staff.user.username}", request=request)
        return Response({"message": "Staff account deactivated."})


# ═════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request):
    notifs = Notification.objects.filter(user=request.user)
    unread = notifs.filter(is_read=False).count()
    notifs = notifs[:50]

    return Response({
        "unread_count": unread,
        "notifications": [
            {
                "id":         n.id,
                "type":       n.type,
                "title":      n.title,
                "message":    n.message,
                "is_read":    n.is_read,
                "link":       n.link,
                "created_at": n.created_at,
            }
            for n in notifs
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_read(request, notif_id):
    try:
        n = Notification.objects.get(id=notif_id, user=request.user)
        n.is_read = True
        n.save()
    except Notification.DoesNotExist:
        pass
    return Response({"message": "Marked as read."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_read_all(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"message": "All notifications marked as read."})


# ═════════════════════════════════════════════════════════════════════════════
# AUDIT LOG (SuperAdmin only)
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def audit_log(request):
    page      = int(request.query_params.get("page", 1))
    per_page  = 50
    offset    = (page - 1) * per_page

    qs    = AuditLog.objects.select_related("actor").all()
    total = qs.count()
    logs  = qs[offset: offset + per_page]

    return Response({
        "total": total,
        "page":  page,
        "pages": (total + per_page - 1) // per_page,
        "results": [
            {
                "id":         l.id,
                "actor":      l.actor.username if l.actor else "System",
                "action":     l.action,
                "action_label": l.get_action_display(),
                "target":     l.target,
                "details":    l.details,
                "ip_address": l.ip_address,
                "timestamp":  l.timestamp,
            }
            for l in logs
        ],
    })


# ═════════════════════════════════════════════════════════════════════════════
# OTP FORGOT PASSWORD
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    from .serializers import ForgotPasswordSerializer

    serializer = ForgotPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    method     = serializer.validated_data["method"]

    user = _find_user(identifier)
    if not user:
        return Response({"message": "If an account exists, an OTP has been sent."})

    destinations = {
        "email":          user.email,
        "recovery_email": user.recovery_email,
        "phone":          getattr(getattr(user, "member_profile", None), "phone_number", ""),
        "recovery_phone": user.recovery_phone,
    }
    destination = destinations.get(method, "")

    if not destination:
        return Response({"error": f"No {method.replace('_', ' ')} on file for this account."}, status=400)

    otp = OTPRequest.generate(user, method)
    _send_otp(otp)
    deliver_otp(user, otp.code, method)

    return Response({
        "message": f"OTP sent to {_mask(destination)}. Expires in {OTPRequest.EXPIRY_MINUTES} minutes.",
        "otp_code": otp.code,   # DEV ONLY — remove in production
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp(request):
    from .serializers import VerifyOTPSerializer

    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    code       = serializer.validated_data["code"]

    user = _find_user(identifier)
    if not user:
        return Response({"error": "Invalid request."}, status=400)

    otp = (
        OTPRequest.objects.filter(user=user, code=code, used=False)
        .order_by("-created_at").first()
    )

    if not otp:
        return Response({"error": "Invalid OTP code."}, status=400)
    if otp.is_expired:
        return Response({"error": "OTP has expired. Please request a new one."}, status=400)

    return Response({"message": "OTP verified.", "valid": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password(request):
    from .serializers import ResetPasswordSerializer

    serializer = ResetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = _find_user(data["identifier"])
    if not user:
        return Response({"error": "Invalid request."}, status=400)

    otp = (
        OTPRequest.objects.filter(user=user, code=data["code"], used=False)
        .order_by("-created_at").first()
    )

    if not otp:
        return Response({"error": "Invalid OTP code."}, status=400)
    if otp.is_expired:
        return Response({"error": "OTP has expired. Please request a new one."}, status=400)

    otp.used = True
    otp.save()
    user.set_password(data["new_password"])
    user.save()

    AuditLog.log(user, "password_reset", request=request)
    return Response({"message": "Password reset successfully. You can now log in."})


# ─────────────────────────────────────────────────────────────────────────────
# 🪪 ID Verification admin endpoints
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_id_verifications(request):
    """List all IDVerification records with optional status filter."""
    from .models import IDVerification
    status_filter = request.query_params.get("status")
    qs = IDVerification.objects.select_related("user").order_by("-created_at")
    if status_filter:
        qs = qs.filter(status=status_filter)
    data = []
    for v in qs:
        data.append({
            "id":          v.pk,
            "user_id":     v.user_id,
            "username":    v.user.username,
            "full_name":   v.user.get_full_name(),
            "national_id": v.national_id,
            "status":      v.status,
            "provider":    v.provider,
            "created_at":  v.created_at,
            "verified_at": v.verified_at,
        })
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_id_verification_detail(request, verification_id):
    """Retrieve a single IDVerification record with OCR result, file URLs, and face match score."""
    from .models import IDVerification
    from django.shortcuts import get_object_or_404
    v = get_object_or_404(IDVerification, pk=verification_id)
    return Response({
        "id":               v.pk,
        "user_id":          v.user_id,
        "username":         v.user.username,
        "full_name":        v.user.get_full_name(),
        "national_id":      v.national_id,
        "status":           v.status,
        "provider":         v.provider,
        "failure_reason":   v.failure_reason,
        "ocr_result":       v.ocr_result,
        "provider_response":v.provider_response,
        "face_match_score": v.face_match_score,
        "id_document_url":  request.build_absolute_uri(f"/api/media/protected/{v.id_document.name}") if v.id_document else None,
        "selfie_url":       request.build_absolute_uri(f"/api/media/protected/{v.selfie.name}") if v.selfie else None,
        "created_at":       v.created_at,
        "verified_at":      v.verified_at,
    })


@api_view(["POST"])
@permission_classes([IsAdmin])
def admin_id_verification_review(request, verification_id):
    """Staff manually set IDVerification status with notes."""
    from .models import IDVerification
    from django.shortcuts import get_object_or_404
    v = get_object_or_404(IDVerification, pk=verification_id)
    new_status = request.data.get("status")
    notes      = request.data.get("notes", "")
    allowed    = ("verified", "failed", "flagged", "pending")
    if new_status not in allowed:
        return Response({"error": f"status must be one of {allowed}"}, status=400)
    old_status = v.status
    v.status = new_status
    if new_status == "verified":
        v.verified_by = request.user
        v.verified_at = timezone.now()
    v.save()
    Notification.send(
        v.user,
        title="Identity Verification Update",
        message=f"Your ID verification status has been updated to '{new_status}' by SACCO staff.",
        ntype="success" if new_status == "verified" else "warning",
    )
    AuditLog.log(
        actor=request.user,
        action="id_verify_review",
        target=f"IDVerification #{v.pk}",
        details={"idverification_id": v.pk, "prev_status": old_status, "new_status": new_status, "notes": notes},
        request=request,
    )
    return Response({"message": f"Status updated to '{new_status}'.", "id": v.pk, "status": new_status})


# ─────────────────────────────────────────────────────────────────────────────
# 🔒 Protected media view — serves selfie and id_document files securely
# ─────────────────────────────────────────────────────────────────────────────
from rest_framework.views import APIView
from django.http import FileResponse
from django.conf import settings as django_settings
import os

class ProtectedMediaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, path):
        from .models import IDVerification
        from django.shortcuts import get_object_or_404
        from rest_framework.exceptions import PermissionDenied

        # Find the IDVerification record that owns this file
        verification = None
        for v in IDVerification.objects.select_related("user").all():
            if (v.id_document and v.id_document.name == path) or \
               (v.selfie and v.selfie.name == path):
                verification = v
                break

        if verification is None:
            return Response({"error": "File not found."}, status=404)

        is_owner = request.user == verification.user
        is_admin = (
            getattr(request.user, "is_admin", False)
            or request.user.is_staff
            or request.user.is_superuser
        )
        if not (is_owner or is_admin):
            raise PermissionDenied("You do not have permission to access this file.")

        full_path = os.path.join(django_settings.MEDIA_ROOT, path)
        if not os.path.exists(full_path):
            return Response({"error": "File not found on disk."}, status=404)

        return FileResponse(open(full_path, "rb"))
