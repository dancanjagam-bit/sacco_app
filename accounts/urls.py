from django.urls import path
from .auth_views import resend_login_2fa
from . import kyc_views
from . import access_views
from . import welfare_views
from .views import (
    register,
    logout,
    login_2fa,
    change_password,
    profile,
    request_recovery_contact_verification as views_request_recovery_contact_verification,
    confirm_recovery_contact_verification as views_confirm_recovery_contact_verification,
    forgot_password,
    verify_otp,
    reset_password,
    staff_list,
    staff_detail,
    notification_list,
    notification_read,
    notification_read_all,
    audit_log,
    my_id_verification,
    admin_id_verifications,
    admin_id_verification_detail,
    admin_id_verification_review,
    ProtectedMediaView,
)

urlpatterns = [
    # Auth
    path("register/",        register,        name="register"),
    path("logout/",          logout,          name="logout"),
    path("login/2fa/",       login_2fa,       name="login-2fa"),
    path("login/2fa/resend/", resend_login_2fa, name="login-2fa-resend"),
    path("change-password/", change_password, name="change-password"),
    path("profile/",         profile,         name="profile"),
    path("profile/recovery-contact/request/", views_request_recovery_contact_verification, name="recovery-contact-request"),
    path("profile/recovery-contact/confirm/", views_confirm_recovery_contact_verification, name="recovery-contact-confirm"),
    path("forgot-password/", forgot_password, name="forgot-password"),
    path("verify-otp/",      verify_otp,      name="verify-otp"),
    path("reset-password/",  reset_password,  name="reset-password"),

    # Staff management
    path("admin/staff/",              staff_list,   name="staff-list"),
    path("admin/staff/<int:staff_id>/", staff_detail, name="staff-detail"),
    path("admin/access/", access_views.staff_access_overview, name="staff-access-overview"),
    path("admin/access/users/", access_views.staff_access_users, name="staff-access-users"),
    path("admin/access/scopes/", access_views.staff_access_scopes, name="staff-access-scopes"),
    path("admin/access/roles/", access_views.staff_role_grant, name="staff-role-grant"),
    path("admin/access/roles/<int:grant_id>/revoke/", access_views.staff_role_revoke, name="staff-role-revoke"),
    path("admin/access/transport-roles/", access_views.transport_role_grant, name="transport-role-grant"),
    path("admin/access/transport-roles/<int:role_id>/revoke/", access_views.transport_role_revoke, name="transport-role-revoke"),
    path("admin/access/duties/", access_views.staff_duty_assign, name="staff-duty-assign"),
    path("admin/access/duties/<int:assignment_id>/revoke/", access_views.staff_duty_revoke, name="staff-duty-revoke"),
    path("staff/workspaces/<str:workspace>/summary/", access_views.staff_workspace_summary, name="staff-workspace-summary"),

    # Notifications
    path("notifications/",                    notification_list,     name="notification-list"),
    path("notifications/<int:notif_id>/read/", notification_read,    name="notification-read"),
    path("notifications/read-all/",            notification_read_all, name="notification-read-all"),

    # Audit log
    path("admin/audit-log/", audit_log, name="audit-log"),

    # Member-owned identity status
    path("id-verification/status/", my_id_verification, name="my-id-verification"),
    path("id-verification/documents/", kyc_views.id_verification_documents, name="id-verification-documents"),
    path("id-verification/submit/", kyc_views.id_verification_submit, name="id-verification-submit"),

    # ID Verification admin
    path("admin/id-verifications/", admin_id_verifications, name="admin-id-verifications"),
    path("admin/id-verifications/<int:verification_id>/", admin_id_verification_detail, name="admin-id-verification-detail"),
    path("admin/id-verifications/<int:verification_id>/review/", admin_id_verification_review, name="admin-id-verification-review"),


    # Persisted KYC workflow. Provider-backed liveness and automated decisions stay disabled.
    path("kyc/workflow/", kyc_views.kyc_workflow_status, name="kyc-workflow-status"),
    path("kyc/phone/otp/request/", kyc_views.kyc_phone_otp_request, name="kyc-phone-otp-request"),
    path("kyc/phone/otp/confirm/", kyc_views.kyc_phone_otp_confirm, name="kyc-phone-otp-confirm"),
    path("kyc/references/", kyc_views.kyc_reference_add, name="kyc-reference-add"),
    path("kyc/references/received/", kyc_views.kyc_reference_received, name="kyc-reference-received"),
    path("kyc/references/<int:reference_id>/respond/", kyc_views.kyc_reference_respond, name="kyc-reference-respond"),
    path("kyc/liveness/start/", kyc_views.kyc_liveness_start, name="kyc-liveness-start"),
    path("kyc/liveness/<int:challenge_id>/complete/", kyc_views.kyc_liveness_complete, name="kyc-liveness-complete"),
    path("kyc/risk-score/", kyc_views.kyc_risk_score, name="kyc-risk-score"),
    path("kyc/consent/", kyc_views.kyc_consent, name="kyc-consent"),
    path("kyc/device/", kyc_views.kyc_device_register, name="kyc-device-register"),
    path("kyc/my-data/", kyc_views.kyc_my_data, name="kyc-my-data"),
    path("kyc/erasure/", kyc_views.kyc_erasure, name="kyc-erasure"),
    path("admin/kyc/approvals/", kyc_views.kyc_admin_pending_approvals, name="kyc-admin-pending-approvals"),
    path("admin/kyc/approvals/<int:approval_id>/decide/", kyc_views.kyc_admin_approval_decide, name="kyc-admin-approval-decide"),

    # Protected media
    path("media/protected/<path:path>", ProtectedMediaView.as_view(), name="protected-media"),

    # Secretary: meetings and notices
    path("secretary/meetings/", access_views.meetings_list, name="secretary-meetings-list"),
    path("secretary/meetings/<int:meeting_id>/", access_views.meeting_detail, name="secretary-meeting-detail"),
    path("secretary/meetings/<int:meeting_id>/attendees/", access_views.meeting_attendees, name="meeting-attendees"),
    path("secretary/meetings/<int:meeting_id>/attendees/<int:attendee_id>/", access_views.meeting_attendee_delete, name="meeting-attendee-delete"),
    path("secretary/notices/", access_views.notices_list, name="secretary-notices-list"),
    path("secretary/notices/<int:notice_id>/", access_views.notice_detail, name="secretary-notice-detail"),
    path("welfare/requests/", welfare_views.welfare_requests, name="welfare-requests"),
    path("welfare/requests/<int:request_id>/documents/", welfare_views.welfare_upload, name="welfare-upload"),
    path("welfare/requests/<int:request_id>/decision/", welfare_views.welfare_decide, name="welfare-decide"),
    path("welfare/requests/<int:request_id>/info/", welfare_views.welfare_request_info, name="welfare-request-info"),
    path("welfare/requests/<int:request_id>/resubmit/", welfare_views.welfare_resubmit, name="welfare-resubmit"),
    path("welfare/documents/<int:document_id>/", welfare_views.welfare_document, name="welfare-document"),
    path("welfare/contributions/", welfare_views.welfare_contributions, name="welfare-contributions"),
    path("welfare/contributions/attribute/", welfare_views.welfare_attribute_contribution, name="welfare-attribute-contribution"),
    path("welfare/contributions/attribution/", welfare_views.welfare_attribution_candidates, name="welfare-attribution-candidates"),
    path("welfare/requests/<int:request_id>/payout/", welfare_views.welfare_link_payout, name="welfare-link-payout"),
    path("welfare/requests/<int:request_id>/payout/start/", welfare_views.welfare_start_payout, name="welfare-start-payout"),
    path("welfare/requests/<int:request_id>/payout/status/", welfare_views.welfare_refresh_payout, name="welfare-refresh-payout"),
    path("welfare/member-dashboard/", welfare_views.welfare_member_dashboard, name="welfare-member-dashboard"),
    path("welfare/officer-dashboard/", welfare_views.welfare_officer_dashboard, name="welfare-officer-dashboard"),
    path("welfare/treasurer-queue/", welfare_views.welfare_treasurer_queue, name="welfare-treasurer-queue"),
    path("welfare/policy/", welfare_views.welfare_policy, name="welfare-policy"),
]
