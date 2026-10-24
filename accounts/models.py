from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import random
import string


class User(AbstractUser):
    is_admin  = models.BooleanField(default=False)
    is_member = models.BooleanField(default=True)

    # Recovery contacts (optional)
    recovery_email = models.EmailField(blank=True, default="")
    recovery_phone = models.CharField(max_length=15, blank=True, default="")

    def __str__(self):
        name = self.get_full_name()
        return f"{name} ({self.username})" if name.strip() else self.username


# ─────────────────────────────────────────────────────────────────────────────
# Staff / Role management
# ─────────────────────────────────────────────────────────────────────────────
class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ("superadmin",    "Super Administrator"),
        ("loan_officer",  "Loan Officer"),
        ("accountant",    "Accountant"),
        ("secretary",     "Secretary"),
        ("it_admin",      "IT Administrator"),
    ]
    STATUS_CHOICES = [
        ("active",     "Active"),
        ("inactive",   "Inactive"),
        ("suspended",  "Suspended"),
    ]

    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    role        = models.CharField(max_length=30, choices=ROLE_CHOICES, default="loan_officer")
    department  = models.CharField(max_length=100, blank=True, default="")
    hire_date   = models.DateField(null=True, blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_by  = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_staff",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.get_role_display()}"


# ─────────────────────────────────────────────────────────────────────────────
# OTP for password reset
# ─────────────────────────────────────────────────────────────────────────────
class OTPRequest(models.Model):
    METHOD_CHOICES = [
        ("email",          "Email"),
        ("phone",          "Phone / SMS"),
        ("recovery_email", "Recovery Email"),
        ("recovery_phone", "Recovery Phone"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_requests")
    code       = models.CharField(max_length=6)
    method     = models.CharField(max_length=20, choices=METHOD_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)

    EXPIRY_MINUTES = 10

    @classmethod
    def generate(cls, user, method):
        cls.objects.filter(user=user, used=False).update(used=True)
        code = "".join(random.choices(string.digits, k=6))
        return cls.objects.create(user=user, code=code, method=method)

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=self.EXPIRY_MINUTES)

    def __str__(self):
        return f"{self.user.username} — {self.code} ({'used' if self.used else 'active'})"


# ─────────────────────────────────────────────────────────────────────────────
# In-app Notifications
# ─────────────────────────────────────────────────────────────────────────────
class Notification(models.Model):
    TYPE_CHOICES = [
        ("info",    "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error",   "Error"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type       = models.CharField(max_length=10, choices=TYPE_CHOICES, default="info")
    title      = models.CharField(max_length=100)
    message    = models.TextField()
    is_read    = models.BooleanField(default=False)
    link       = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.type}] {self.title} → {self.user.username}"

    @classmethod
    def send(cls, user, title, message, ntype="info", link=""):
        return cls.objects.create(user=user, type=ntype, title=title, message=message, link=link)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────────────────────────
class AuditLog(models.Model):
    ACTION_CHOICES = [
        # Auth
        ("login",           "User Login"),
        ("logout",          "User Logout"),
        ("register",        "Member Registered"),
        ("password_change", "Password Changed"),
        ("password_reset",  "Password Reset"),
        # Members
        ("member_create",   "Member Created"),
        ("member_update",   "Member Updated"),
        ("member_delete",   "Member Deleted"),
        ("member_suspend",  "Member Suspended"),
        # Staff
        ("staff_create",    "Staff Created"),
        ("staff_update",    "Staff Updated"),
        ("staff_deactivate","Staff Deactivated"),
        # Finance
        ("deposit",         "Savings Deposit"),
        ("withdrawal",      "Savings Withdrawal"),
        ("loan_apply",      "Loan Applied"),
        ("loan_approve",    "Loan Approved"),
        ("loan_reject",     "Loan Rejected"),
        ("loan_repayment",  "Loan Repayment"),
        # System
        ("export",          "Data Exported"),
        ("other",           "Other"),
    ]

    actor      = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_actions")
    action     = models.CharField(max_length=30, choices=ACTION_CHOICES)
    target     = models.CharField(max_length=200, blank=True, default="")  # e.g. "Member #SACCO000003"
    details    = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        actor = self.actor.username if self.actor else "System"
        return f"{actor} → {self.get_action_display()} ({self.timestamp:%Y-%m-%d %H:%M})"

    @classmethod
    def log(cls, actor, action, target="", details=None, request=None):
        ip = None
        if request:
            x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
        return cls.objects.create(
            actor=actor, action=action, target=target,
            details=details or {}, ip_address=ip,
        )
