from django.urls import path

from .views import member_list, member_detail

urlpatterns = [
    path("members/", member_list),
    path("members/<int:id>/", member_detail),
]
