from django.contrib import admin
from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "member_number",
        "first_name",
        "last_name",
        "phone_number",
        "status",
    )

    search_fields = (
        "member_number",
        "first_name",
        "last_name",
        "national_id",
    )

    list_filter = (
        "status",
        "gender",
    )
