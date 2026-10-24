from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Member

User = get_user_model()


class MemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Member
        fields = [
            'id',
            'member_number',
            'username',
            'full_name',
            'email',
            'national_id',
            'phone_number',
            'gender',
            'date_of_birth',
            'county',
            'address',
            'status',
            'date_joined',
        ]
        read_only_fields = ['id', 'member_number', 'username', 'full_name', 'email', 'date_joined']

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class MemberUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ['phone_number', 'county', 'address', 'status']

    def validate_status(self, value):
        if value not in dict(Member.STATUS_CHOICES):
            raise serializers.ValidationError('Invalid status value')
        return value
