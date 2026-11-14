import hmac

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Max, Sum, Q
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from members.models import Member
from core.models import Savings, Loan
from .models import OTPRequest, StaffProfile, Notification, AuditLog, MemberNotice
from .access import has_sacco_permission, is_staff_manager, requires_staff_login_2fa
from sacco.notifications import send_welcome
from accounts.services.otp_delivery import dispatch_otp

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Permissions
# ─────────────────────────────────────────────────────────────────────────────
class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_staff_manager(request.user)


class IsSuperAdmin(BasePermission):
    """Only superuser or users with role='superadmin' can manage staff."""
    def has_permission(self, request, view):
        return is_staff_manager(request.user)


class IsKYCStaff(BasePermission):
    """Identity document review is an explicit capability, not a staff flag."""
    def has_permission(self, request, view):
        return has_sacco_permission(request.user, "kyc.review")


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






def _profile_response(user):
    from .access import access_snapshot

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

    access = access_snapshot(user)
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
        "permissions":     access["permissions"],
        "workspaces":      access["workspaces"],
        "default_workspace": access["default_workspace"],
    }


# ═════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════════════
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    from .serializers import RegistrationSerializer
    from .models import IDVerification, KYCSubmission, KYCConsentRecord, MemberApproval
    from accounts.services.kyc_privacy import hash_national_id, retention_date

    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    member_number = None
    id_status = "draft"

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

            # Derive the initial public member number from the newly allocated
            # user PK; the unique database constraint remains the authority.
            member_number = f"SACCO{user.pk:06d}"

            Member.objects.create(
                user=user,
                member_number=member_number,
                national_id=data["national_id"],
                phone_number=data["phone_number"],
                gender=data["gender"],
                date_of_birth=data["date_of_birth"],
                county=data["county"],
                address=data["address"],
                status="inactive",
            )

            front = data.get("id_document_front") or data.get("id_document")
            back = data.get("id_document_back")
            consent = bool(data.get("id_verification_consent"))
            now = timezone.now()
            verification = IDVerification.objects.create(
                user=user,
                national_id=data["national_id"],
                national_id_hash=hash_national_id(data["national_id"]),
                provider="manual",
                status="submitted" if (front or back) else "draft",
                verification_purpose="membership_onboarding",
                member_consent=consent,
                consented_at=now if consent else None,
                submitted_at=now if (front or back) else None,
                data_retention_until=retention_date() if consent else None,
            )
            if front or back:
                submission = KYCSubmission.objects.create(
                    verification=verification,
                    sequence=1,
                    status="submitted",
                    id_document_front=front,
                    id_document_back=back,
                    reviewed_fields={
                        "first_name": data.get("first_name", ""),
                        "last_name": data.get("last_name", ""),
                        "national_id": data["national_id"],
                        "date_of_birth": data["date_of_birth"].isoformat(),
                    },
                    consent_given=True,
                    consent_text_version=getattr(settings, "KYC_CONSENT_VERSION", "1.0"),
                    submitted_at=now,
                )
                # The top-level record points at the latest submission for
                # compatibility; the versioned submission retains evidence.
                verification.id_document_front = submission.id_document_front.name if front else ""
                verification.id_document_back = submission.id_document_back.name if back else ""
                verification.save(update_fields=("id_document_front", "id_document_back", "updated_at"))

            KYCConsentRecord.objects.create(
                user=user,
                purpose="id_verification",
                consent_given=consent,
                consent_text_version=getattr(settings, "KYC_CONSENT_VERSION", "1.0"),
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:300],
            )
            MemberApproval.objects.create(applicant=user, stage="secretary_review")
            id_status = verification.status
            Notification.send(
                user, "Membership application received",
                "Your account is ready for membership review. Identity documents remain pending staff review.",
                "info", "/id-verification",
            )
            AuditLog.log(user, "register", f"Member {member_number}", {"username": user.username}, request)
            transaction.on_commit(lambda: send_welcome(user, member_number))

    except IntegrityError:
        # Simultaneous retries may race on username, email, phone or ID
        # uniqueness. The atomic block rolls back all related rows.
        return Response({
            "error": "We could not complete this registration. Use account recovery or contact member support if you already registered.",
        }, status=409)

    return Response({
        "message":       "Registration successful",
        "member_number": member_number,
        "id_status":     id_status,
        "membership_status": "pending_review",
        "message_detail": "Your membership application is awaiting staff review.",
    }, status=201)


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
@ratelimit(key="ip", rate="10/h", block=True)
def login_2fa(request):
    """
    Active staff and superuser accounts must verify a delivery-accepted OTP
    after password login before receiving full-access tokens.
    """
    from .serializers import VerifyOTPSerializer
    from rest_framework_simplejwt.tokens import RefreshToken as JWTRefresh

    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    code       = serializer.validated_data["code"]

    user = _find_user(identifier)
    if not user:
        return Response({"error": "Invalid request or verification code."}, status=400)

    if not user.is_active or not requires_staff_login_2fa(user):
        return Response({"error": "This verification flow is only available to active staff accounts."}, status=403)

    with transaction.atomic():
        otp = (
            OTPRequest.objects.select_for_update()
            .filter(
                user=user,
                used=False,
                purpose="login_2fa",
                # A generated code is not a valid second factor until the
                # configured delivery provider has accepted the dispatch.
                delivery_status="accepted",
            )
            .order_by("-created_at")
            .first()
        )

        if not otp:
            return Response({"error": "Invalid or expired verification code. Sign in again to request a new code."}, status=400)
        if otp.is_expired:
            otp.used = True
            otp.save(update_fields=["used"])
            return Response({"error": "Verification code expired. Sign in again to request a new code."}, status=400)
        if otp.attempt_count >= 5:
            otp.used = True
            otp.save(update_fields=["used"])
            return Response({"error": "Verification attempts exceeded. Sign in again to request a new code."}, status=400)

        matches = hmac.compare_digest(otp.code, code)
        otp.attempt_count += 1
        if matches or otp.attempt_count >= 5:
            otp.used = True
        otp.save(update_fields=["attempt_count", "used"])
        if not matches:
            return Response({"error": "Invalid verification code. Check the code or sign in again to request a new one."}, status=400)

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
            if field == "recovery_email" and data[field] != user.recovery_email:
                user.recovery_email_verified = False
            if field == "recovery_phone" and data[field] != user.recovery_phone:
                user.recovery_phone_verified = False
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
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@ratelimit(key="user", rate="5/h", block=True)
def request_recovery_contact_verification(request):
    method = request.data.get("method")
    if method == "recovery_email":
        destination = request.user.recovery_email
    elif method == "recovery_phone":
        destination = request.user.recovery_phone
    else:
        return Response({"error": "Choose a recovery email or recovery phone saved on your profile."}, status=400)
    if not destination:
        return Response({"error": "Add this recovery contact to your profile before verifying it."}, status=400)

    now = timezone.now()
    attempts = OTPRequest.objects.filter(
        user=request.user, purpose="contact_verification",
        created_at__gte=now - timezone.timedelta(hours=1),
    )
    if attempts.count() >= 3 or attempts.filter(created_at__gte=now - timezone.timedelta(seconds=60)).exists():
        return Response({"error": "Verification resend limit reached. Try again later."}, status=429)

    otp = OTPRequest.generate(request.user, method, purpose="contact_verification")
    import hashlib
    import hmac
    from django.conf import settings as django_settings
    otp.destination_digest = hmac.new(
        django_settings.SECRET_KEY.encode(), destination.strip().lower().encode(), hashlib.sha256,
    ).hexdigest()
    otp.save(update_fields=("destination_digest",))
    outcome = dispatch_otp(otp)
    if outcome["status"] != "accepted":
        AuditLog.log(
            request.user, "otp_delivery_failure", "contact_verification",
            {"method": method, "reason_code": outcome["reason_code"]}, request,
        )
        return Response({"error": "The verification message could not be submitted. Contact the SACCO office or try later."}, status=503)
    return Response({"message": "The verification message was accepted by the configured provider. Enter its code to confirm this contact."}, status=202)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@ratelimit(key="user", rate="10/h", block=True)
def confirm_recovery_contact_verification(request):
    method = request.data.get("method")
    code = str(request.data.get("code", ""))
    if method not in ("recovery_email", "recovery_phone") or not code.isdigit() or len(code) != 6:
        return Response({"error": "Enter the six-digit code and the recovery contact type."}, status=400)
    destination = request.user.recovery_email if method == "recovery_email" else request.user.recovery_phone
    import hashlib
    import hmac
    from django.conf import settings as django_settings
    digest = hmac.new(
        django_settings.SECRET_KEY.encode(), destination.strip().lower().encode(), hashlib.sha256,
    ).hexdigest()
    with transaction.atomic():
        otp = OTPRequest.objects.select_for_update().filter(
            user=request.user, method=method, purpose="contact_verification", used=False,
        ).order_by("-created_at").first()
        if (
            not otp or otp.delivery_status != "accepted" or otp.is_expired
            or otp.attempt_count >= 5 or not hmac.compare_digest(otp.destination_digest, digest)
        ):
            return Response({"error": "Invalid or expired verification code."}, status=400)
        matches = hmac.compare_digest(otp.code, code)
        otp.attempt_count += 1
        if not matches and otp.attempt_count >= 5:
            otp.used = True
        otp.save(update_fields=("attempt_count", "used"))
        if not matches:
            return Response({"error": "Invalid or expired verification code."}, status=400)
        otp.used = True
        otp.save(update_fields=("used",))
        field = "recovery_email_verified" if method == "recovery_email" else "recovery_phone_verified"
        setattr(request.user, field, True)
        request.user.save(update_fields=(field,))
    AuditLog.log(request.user, "recovery_contact_verified", method, request=request)
    return Response({"message": "Recovery contact verified."})

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
    notices = []
    if request.user.is_member and Member.objects.filter(user=request.user, status="active").exists():
        now = timezone.now()
        notices = MemberNotice.objects.filter(
            status="published", published_at__lte=now,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).order_by("-published_at", "-pk").values(
            "id", "title", "body", "priority", "published_at",
        )[:50]

    return Response({
        "unread_count": unread,
        "member_notices": list(notices),
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
@ratelimit(key="ip", rate="5/h", block=True)
def forgot_password(request):
    from .serializers import ForgotPasswordSerializer

    serializer = ForgotPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    method     = serializer.validated_data["method"]

    user = _find_user(identifier)
    generic_message = "If the account and delivery method are valid, an OTP has been sent."
    if not user:
        return Response({"message": generic_message})

    verified_destination = (
        method == "recovery_email" and user.recovery_email_verified and bool(user.recovery_email)
    ) or (
        method == "recovery_phone" and user.recovery_phone_verified and bool(user.recovery_phone)
    )
    if not verified_destination:
        return Response({"message": generic_message})

    now = timezone.now()
    recent = OTPRequest.objects.filter(
        user=user, purpose="recovery", created_at__gte=now - timezone.timedelta(hours=1),
    )
    if recent.count() >= 3 or recent.filter(created_at__gte=now - timezone.timedelta(seconds=60)).exists():
        return Response({"message": generic_message})

    otp = OTPRequest.generate(user, method, purpose="recovery")
    outcome = dispatch_otp(otp)
    if outcome["status"] != "accepted":
        AuditLog.log(
            user, "otp_delivery_failure", "password_recovery",
            {"method": method, "reason_code": outcome["reason_code"]}, request,
        )

    return Response({"message": generic_message})


@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="20/h", block=True)
def verify_otp(request):
    from .serializers import VerifyOTPSerializer

    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data["identifier"]
    code       = serializer.validated_data["code"]

    user = _find_user(identifier)
    if not user:
        return Response({"error": "Invalid request or verification code."}, status=400)

    import hmac
    with transaction.atomic():
        otp = (
            OTPRequest.objects.select_for_update()
            .filter(user=user, used=False, purpose="recovery")
            .order_by("-created_at").first()
        )
        if not otp or otp.delivery_status != "accepted" or otp.is_expired or otp.attempt_count >= 5:
            return Response({"error": "Invalid request or verification code."}, status=400)
        matches = hmac.compare_digest(otp.code, code)
        otp.attempt_count += 1
        if not matches and otp.attempt_count >= 5:
            otp.used = True
        otp.save(update_fields=("attempt_count", "used"))
        if not matches:
            return Response({"error": "Invalid request or verification code."}, status=400)

    if otp.is_expired:
        return Response({"error": "Invalid request or verification code."}, status=400)

    return Response({"message": "OTP verified.", "valid": True})


@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="10/h", block=True)
def reset_password(request):
    from .serializers import ResetPasswordSerializer

    serializer = ResetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = _find_user(data["identifier"])
    if not user:
        return Response({"error": "Invalid request or verification code."}, status=400)

    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        import hmac
        otp = (
            OTPRequest.objects.select_for_update()
            .filter(user=user, used=False, purpose="recovery")
            .order_by("-created_at").first()
        )
        if not otp or otp.delivery_status != "accepted" or otp.attempt_count >= 5:
            return Response({"error": "Invalid request or verification code."}, status=400)
        if otp.is_expired:
            return Response({"error": "Invalid request or verification code."}, status=400)

        if not hmac.compare_digest(otp.code, data["code"]):
            otp.attempt_count += 1
            if otp.attempt_count >= 5:
                otp.used = True
            otp.save(update_fields=("attempt_count", "used"))
            return Response({"error": "Invalid request or verification code."}, status=400)

        otp.used = True
        otp.save(update_fields=["used"])
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])

        # A password reset ends existing refresh-token sessions on all devices.
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        outstanding = OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False)
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token=token) for token in outstanding],
            ignore_conflicts=True,
        )

    AuditLog.log(user, "password_reset", request=request)
    return Response({"message": "Password reset successfully. You can now log in."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_id_verification(request):
    """Return only the authenticated member's KYC status and their own review fields."""
    from .models import IDVerification, IDVerificationAttempt
    from accounts.services.kyc_privacy import mask_national_id
    member = getattr(request.user, "member_profile", None)
    verification = IDVerification.objects.filter(user=request.user).first()
    own_id = verification.national_id if verification else getattr(member, "national_id", "") if member else ""
    reviewed_fields = {
        "national_id": own_id,
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "date_of_birth": member.date_of_birth.isoformat() if member and member.date_of_birth else "",
    }
    if not verification:
        return Response({
            "status": "not_submitted", "national_id": mask_national_id(own_id),
            "reviewed_fields": reviewed_fields, "ocr_result": {},
            "created_at": None, "updated_at": None, "verified_at": None,
            "failure_reason": "", "provider": "", "member_consent": False,
            "submitted_at": None, "attempts": [],
        })
    attempts = IDVerificationAttempt.objects.filter(verification=verification).order_by("requested_at").values(
        "provider", "status", "provider_reference", "reason_code", "requested_at", "completed_at",
    )
    return Response({
        "status": verification.status,
        "national_id": mask_national_id(verification.national_id),
        "reviewed_fields": reviewed_fields,
        "ocr_result": verification.ocr_result if isinstance(verification.ocr_result, dict) else {},
        "created_at": verification.created_at, "updated_at": verification.updated_at,
        "verified_at": verification.verified_at, "failure_reason": verification.failure_reason,
        "provider": verification.provider, "member_consent": verification.member_consent,
        "submitted_at": verification.submitted_at, "attempts": list(attempts),
        "document_front_uploaded": bool(verification.id_document_front),
        "document_back_uploaded": bool(verification.id_document_back),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 🪪 ID Verification admin endpoints
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsKYCStaff])
def admin_id_verifications(request):
    """List all IDVerification records with optional status filter."""
    from .models import IDVerification
    from accounts.services.kyc_privacy import mask_national_id
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
            "national_id": mask_national_id(v.national_id),
            "status":      v.status,
            "provider":    v.provider,
            "created_at":  v.created_at,
            "verified_at": v.verified_at,
        })
    return Response(data)


@api_view(["GET"])
@permission_classes([IsKYCStaff])
def admin_id_verification_detail(request, verification_id):
    """Retrieve a single IDVerification record with OCR result, file URLs, and face match score."""
    from .models import IDVerification
    from django.shortcuts import get_object_or_404
    v = get_object_or_404(IDVerification, pk=verification_id)
    from .services.kyc_privacy import log_pii_access
    log_pii_access(v, request.user)
    latest_submission = v.submissions.order_by("-sequence").first()
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
        "face_match_score": v.face_match_score,
        "id_document_url":  request.build_absolute_uri(f"/api/media/protected/{v.id_document_front.name}") if v.id_document_front else None,
        "id_document_back_url": request.build_absolute_uri(f"/api/media/protected/{v.id_document_back.name}") if v.id_document_back else None,
        "latest_submission": ({
            "id": latest_submission.pk,
            "sequence": latest_submission.sequence,
            "status": latest_submission.status,
            "reviewed_fields": latest_submission.reviewed_fields,
            "submitted_at": latest_submission.submitted_at,
        } if latest_submission else None),
        "selfie_url":       request.build_absolute_uri(f"/api/media/protected/{v.selfie.name}") if v.selfie else None,
        "created_at":       v.created_at,
        "verified_at":      v.verified_at,
    })


@api_view(["POST"])
@permission_classes([IsKYCStaff])
def admin_id_verification_review(request, verification_id):
    """Staff manually set IDVerification status with notes."""
    from .models import IDVerification
    from django.shortcuts import get_object_or_404
    v = get_object_or_404(IDVerification, pk=verification_id)
    new_status = request.data.get("status")
    notes = str(request.data.get("notes", "")).strip()
    allowed = ("verified", "needs_review", "pending")
    if new_status not in allowed:
        return Response({"error": "status must be verified, needs_review, or pending"}, status=400)
    if len(notes) < 10:
        return Response({"error": "Provide a review reason of at least 10 characters."}, status=400)
    old_status = v.status
    v.status = new_status
    from .models import IDVerificationAttempt
    v.provider = "manual"
    if new_status == "verified":
        v.verified_by = request.user
        v.verified_at = timezone.now()
    v.failure_reason = "" if new_status == "verified" else notes
    v.save()
    latest_submission = v.submissions.order_by("-sequence").first()
    if latest_submission:
        latest_submission.status = "reviewed" if new_status == "verified" else "needs_information"
        latest_submission.save(update_fields=["status"])
    IDVerificationAttempt.objects.create(
        verification=v, provider="manual", status="verified" if new_status == "verified" else "needs_review",
        reason_code="manual_review_completed" if new_status == "verified" else "manual_review_follow_up",
        completed_at=timezone.now(),
    )
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
        details={"idverification_id": v.pk, "prev_status": old_status, "new_status": new_status, "method": "manual", "reason": notes[:500]},
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
        from django.core.files.storage import default_storage
        from django.shortcuts import get_object_or_404
        from rest_framework.exceptions import PermissionDenied
        from .services.kyc_privacy import log_pii_access

        verification = None
        for item in IDVerification.objects.select_related("user").iterator():
            names = [
                item.id_document.name if item.id_document else None,
                item.id_document_front.name if item.id_document_front else None,
                item.id_document_back.name if item.id_document_back else None,
                item.selfie.name if item.selfie else None,
            ]
            if path in names:
                verification = item
                break
            if item.submissions.filter(
                Q(id_document_front=path) | Q(id_document_back=path),
            ).exists():
                verification = item
                break
        if verification is None or not default_storage.exists(path):
            return Response({"error": "File not found."}, status=404)

        is_owner = request.user.pk == verification.user_id
        is_kyc_staff = IsKYCStaff().has_permission(request, self)
        if not (is_owner or is_kyc_staff):
            raise PermissionDenied("You do not have permission to access this file.")
        if is_kyc_staff and not is_owner:
            log_pii_access(verification, request.user)

        response = FileResponse(default_storage.open(path, "rb"))
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
