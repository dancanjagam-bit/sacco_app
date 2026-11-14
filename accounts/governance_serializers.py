from rest_framework import serializers

from .models import CooperativeMeeting, MemberNotice


class CooperativeMeetingInput(serializers.ModelSerializer):
    class Meta:
        model = CooperativeMeeting
        fields = ("title", "meeting_type", "status", "scheduled_at", "location", "agenda", "minutes", "quorum_met")


class MemberNoticeInput(serializers.ModelSerializer):
    class Meta:
        model = MemberNotice
        fields = ("title", "body", "priority", "status", "expires_at")
