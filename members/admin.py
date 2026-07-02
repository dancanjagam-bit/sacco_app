from django.contrib import admin
from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "member_number",
        "user",
        "phone_number",
        "status",
    )

    search_fields = (
        "member_number",
        "user__username",
        "user__first_name",
        "user__last_name",
        "national_id",
    )

    list_filter = (
        "status",
        "gender",
    )
