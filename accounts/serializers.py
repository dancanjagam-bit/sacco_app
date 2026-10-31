import re
from datetime import date

from rest_framework import serializers
from django.contrib.auth import get_user_model
from members.models import Member

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Kenyan phone-number normaliser
# Accepts:  +254722000000 / 0722000000 / 722000000
# Returns:  07XXXXXXXX  (10-digit local format stored in DB)
# Kenyan mobile prefixes: 07xx, 01xx (Safaricom, Airtel, Telkom)
# ─────────────────────────────────────────────────────────────────────────────
KENYAN_PHONE_RE = re.compile(
    r"^(?:\+254|254|0)([17]\d{8})$"
)

def normalise_kenyan_phone(value: str) -> str:
    """Strip spaces/dashes then validate as a Kenyan mobile number."""
    cleaned = re.sub(r"[\s\-]", "", value)
    m = KENYAN_PHONE_RE.match(cleaned)
    if not m:
        raise serializers.ValidationError(
            "Enter a valid Kenyan mobile number "
            "(e.g. 0722 000 000 or +254 722 000 000)."
        )
    return "0" + m.group(1)          # normalise to 0XXXXXXXXX


# ─────────────────────────────────────────────────────────────────────────────
# Kenyan National ID validator
# Format: 7–8 digit number (current IDs) — older cards can be 5–6 digits too
# ─────────────────────────────────────────────────────────────────────────────
NATIONAL_ID_RE = re.compile(r"^\d{5,8}$")

def validate_kenyan_national_id(value: str) -> str:
    cleaned = value.strip()
    if not NATIONAL_ID_RE.match(cleaned):
        raise serializers.ValidationError(
            "Enter a valid Kenyan National ID number (5–8 digits, numbers only)."
        )
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# 47 Kenyan counties (full list)
# ─────────────────────────────────────────────────────────────────────────────
KENYA_COUNTIES = [
    "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita-Taveta",
    "Garissa", "Wajir", "Mandera", "Marsabit", "Isiolo", "Meru",
    "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni", "Nyandarua",
    "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana", "West Pokot",
    "Samburu", "Trans-Nzoia", "Uasin Gishu", "Elgeyo-Marakwet", "Nandi",
    "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado", "Kericho",
    "Bomet", "Kakamega", "Vihiga", "Bungoma", "Busia", "Siaya",
    "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira", "Nairobi",
]
KENYA_COUNTIES_LOWER = [c.lower() for c in KENYA_COUNTIES]


def validate_kenyan_county(value: str) -> str:
    if value.strip().lower() not in KENYA_COUNTIES_LOWER:
        raise serializers.ValidationError(
            f"'{value}' is not a recognised Kenyan county. "
            "Please enter one of the 47 official counties."
        )
    # Return it title-cased for consistency
    idx = KENYA_COUNTIES_LOWER.index(value.strip().lower())
    return KENYA_COUNTIES[idx]


# ─────────────────────────────────────────────────────────────────────────────
# Minimum age (18 years)
# ─────────────────────────────────────────────────────────────────────────────
def validate_minimum_age(value: date) -> date:
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < 18:
        raise serializers.ValidationError(
            "You must be at least 18 years old to register."
        )
    if age > 100:
        raise serializers.ValidationError(
            "Please enter a valid date of birth."
        )
    return value


# ─────────────────────────────────────────────────────────────────────────────
# Password strength
# ─────────────────────────────────────────────────────────────────────────────
def validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise serializers.ValidationError("Password must be at least 8 characters.")
    if not re.search(r"[A-Za-z]", value):
        raise serializers.ValidationError("Password must contain at least one letter.")
    if not re.search(r"\d", value):
        raise serializers.ValidationError("Password must contain at least one number.")
    return value


# ═════════════════════════════════════════════════════════════════════════════
# SERIALIZERS
# ═════════════════════════════════════════════════════════════════════════════

class RegistrationSerializer(serializers.Serializer):
    username         = serializers.CharField(max_length=150)
    password         = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()            # required — used for recovery

    national_id  = serializers.CharField(max_length=20)
    phone_number = serializers.CharField(max_length=20)
    gender       = serializers.ChoiceField(choices=Member.GENDER_CHOICES)
    date_of_birth= serializers.DateField()
    county       = serializers.CharField(max_length=100)
    address      = serializers.CharField()

    # Optional recovery contacts
    recovery_email = serializers.EmailField(required=False, allow_blank=True)
    recovery_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    # File uploads for ID verification
    id_document = serializers.FileField(required=False, allow_null=True)
    selfie      = serializers.FileField(required=False, allow_null=True)

    # ── Field-level validators ────────────────────────────────────────────
    def validate_username(self, v):
        if User.objects.filter(username=v).exists():
            raise serializers.ValidationError("Username already taken.")
        if not re.match(r"^[a-zA-Z0-9_]{3,30}$", v):
            raise serializers.ValidationError(
                "Username may only contain letters, numbers, and underscores (3–30 chars)."
            )
        return v

    def validate_password(self, v):
        return validate_password_strength(v)

    def validate_email(self, v):
        if User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return v.lower()

    def validate_national_id(self, v):
        v = validate_kenyan_national_id(v)
        if Member.objects.filter(national_id=v).exists():
            raise serializers.ValidationError("National ID already registered.")
        return v

    def validate_phone_number(self, v):
        v = normalise_kenyan_phone(v)
        if Member.objects.filter(phone_number=v).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return v

    def validate_date_of_birth(self, v):
        return validate_minimum_age(v)

    def validate_county(self, v):
        return validate_kenyan_county(v)

    def validate_recovery_phone(self, v):
        if v:
            return normalise_kenyan_phone(v)
        return v

    def validate_id_document(self, file):
        if file:
            from accounts.services.file_validator import validate_id_document
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_id_document(file)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)
        return file

    def validate_selfie(self, file):
        if file:
            from accounts.services.file_validator import validate_selfie
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_selfie(file)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)
        return file

    # ── Cross-field ───────────────────────────────────────────────────────
    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password     = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, v):
        return validate_password_strength(v)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "New password must differ from the old one."})
        return attrs


class ProfileUpdateSerializer(serializers.Serializer):
    first_name   = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name    = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email        = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20,  required=False, allow_blank=True)
    county       = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address      = serializers.CharField(required=False, allow_blank=True)
    recovery_email = serializers.EmailField(required=False, allow_blank=True)
    recovery_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_phone_number(self, v):
        if v:
            return normalise_kenyan_phone(v)
        return v

    def validate_recovery_phone(self, v):
        if v:
            return normalise_kenyan_phone(v)
        return v

    def validate_county(self, v):
        if v:
            return validate_kenyan_county(v)
        return v


class ForgotPasswordSerializer(serializers.Serializer):
    METHOD_CHOICES = ["email", "phone", "recovery_email", "recovery_phone"]
    identifier = serializers.CharField()          # username or email
    method     = serializers.ChoiceField(choices=METHOD_CHOICES)


class VerifyOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    code       = serializers.CharField(min_length=6, max_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    identifier       = serializers.CharField()
    code             = serializers.CharField(min_length=6, max_length=6)
    new_password     = serializers.CharField()
    confirm_password = serializers.CharField()

    def validate_new_password(self, v):
        return validate_password_strength(v)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


# ═════════════════════════════════════════════════════════════════════════════
# STAFF MANAGEMENT SERIALIZERS
# ═════════════════════════════════════════════════════════════════════════════
class CreateStaffSerializer(serializers.Serializer):
    ROLE_CHOICES = ["superadmin", "loan_officer", "accountant", "secretary", "it_admin"]

    username   = serializers.CharField(max_length=150)
    password   = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    role       = serializers.ChoiceField(choices=ROLE_CHOICES)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    hire_date  = serializers.DateField(required=False, allow_null=True)

    def validate_username(self, v):
        if User.objects.filter(username=v).exists():
            raise serializers.ValidationError("Username already taken.")
        if not re.match(r"^[a-zA-Z0-9_]{3,30}$", v):
            raise serializers.ValidationError("3–30 chars, letters/numbers/underscores only.")
        return v

    def validate_email(self, v):
        if User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError("Email already registered.")
        return v.lower()

    def validate_password(self, v):
        return validate_password_strength(v)


class UpdateStaffSerializer(serializers.Serializer):
    ROLE_CHOICES   = ["superadmin", "loan_officer", "accountant", "secretary", "it_admin"]
    STATUS_CHOICES = ["active", "inactive", "suspended"]

    role       = serializers.ChoiceField(choices=ROLE_CHOICES, required=False)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    hire_date  = serializers.DateField(required=False, allow_null=True)
    status     = serializers.ChoiceField(choices=STATUS_CHOICES, required=False)
