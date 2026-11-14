from django.urls import path
from .views import member_list, member_detail, suspend_member, member_approvals_list, member_approval_detail

urlpatterns = [
    path("members/",                  member_list),
    path("members/<int:id>/",         member_detail),
    path("members/<int:id>/suspend/", suspend_member),
    path("members/approvals/",             member_approvals_list,  name="member-approvals-list"),
    path("members/approvals/<int:approval_id>/", member_approval_detail, name="member-approval-detail"),
]
