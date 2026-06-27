from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

User = get_user_model()


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    username = request.data.get("username")
    email = request.data.get("email")
    password = request.data.get("password")

    if not username or not password:
        return Response(
            {"error": "Username and password are required"},
            status=400
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "User already exists"},
            status=400
        )

    User.objects.create(
        username=username,
        email=email,
        password=make_password(password)
    )

    return Response(
        {"message": "User created successfully"}
    )
