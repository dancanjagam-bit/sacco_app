from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, OTPRequest, StaffProfile, Notification, AuditLog


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display  = ("username", "email", "first_name", "last_name", "is_staff", "is_admin", "is_active")
    list_filter   = ("is_staff", "is_superuser", "is_admin", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    fieldsets     = UserAdmin.fieldsets + (
        ("SACCO Flags", {"fields": ("is_admin", "is_member", "recovery_email", "recovery_phone")}),
    )


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display  = ("user", "role", "department", "status", "hire_date", "created_at")
    list_filter   = ("role", "status")
    search_fields = ("user__username", "user__first_name", "user__last_name", "department")


@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display  = ("user", "code", "method", "used", "created_at")
    list_filter   = ("method", "used")
    search_fields = ("user__username",)
    readonly_fields = ("code", "created_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ("user", "type", "title", "is_read", "created_at")
    list_filter   = ("type", "is_read")
    search_fields = ("user__username", "title")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ("actor", "action", "target", "ip_address", "timestamp")
    list_filter   = ("action",)
    search_fields = ("actor__username", "target")
    readonly_fields = ("actor", "action", "target", "details", "ip_address", "timestamp")
