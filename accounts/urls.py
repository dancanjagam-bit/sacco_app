from django.urls import path
from .views import (
    register,
    logout,
    login_2fa,
    change_password,
    profile,
    forgot_password,
    verify_otp,
    reset_password,
    staff_list,
    staff_detail,
    notification_list,
    notification_read,
    notification_read_all,
    audit_log,
)

urlpatterns = [
    # Auth
    path("register/",        register,        name="register"),
    path("logout/",          logout,          name="logout"),
    path("login/2fa/",       login_2fa,       name="login-2fa"),
    path("change-password/", change_password, name="change-password"),
    path("profile/",         profile,         name="profile"),
    path("forgot-password/", forgot_password, name="forgot-password"),
    path("verify-otp/",      verify_otp,      name="verify-otp"),
    path("reset-password/",  reset_password,  name="reset-password"),

    # Staff management
    path("admin/staff/",              staff_list,   name="staff-list"),
    path("admin/staff/<int:staff_id>/", staff_detail, name="staff-detail"),

    # Notifications
    path("notifications/",                    notification_list,     name="notification-list"),
    path("notifications/<int:notif_id>/read/", notification_read,    name="notification-read"),
    path("notifications/read-all/",            notification_read_all, name="notification-read-all"),

    # Audit log
    path("admin/audit-log/", audit_log, name="audit-log"),
]
