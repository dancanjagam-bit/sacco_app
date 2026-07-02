from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from members.models import Member

User = get_user_model()


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    username = request.data.get("username")
    password = request.data.get("password")

    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    email = request.data.get("email")

    national_id = request.data.get("national_id")
    phone_number = request.data.get("phone_number")
    gender = request.data.get("gender")
    date_of_birth = request.data.get("date_of_birth")
    county = request.data.get("county")
    address = request.data.get("address")

    if not username or not password:
        return Response(
            {"error": "Username and password are required"},
            status=400,
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists"},
            status=400,
        )

    if Member.objects.filter(national_id=national_id).exists():
        return Response(
            {"error": "National ID already exists"},
            status=400,
        )

    with transaction.atomic():

        user = User.objects.create(
            username=username,
            password=make_password(password),
            first_name=first_name,
            last_name=last_name,
            email=email,
        )

        member_number = f"SACCO{Member.objects.count() + 1:06d}"

        Member.objects.create(
            user=user,
            member_number=member_number,
            national_id=national_id,
            phone_number=phone_number,
            gender=gender,
            date_of_birth=date_of_birth,
            county=county,
            address=address,
        )

    return Response(
        {
            "message": "Registration successful",
            "member_number": member_number,
        }
    )
