from django.urls import path
from .views import member_list, member_detail, suspend_member

urlpatterns = [
    path("members/",                  member_list),
    path("members/<int:id>/",         member_detail),
    path("members/<int:id>/suspend/", suspend_member),
]
