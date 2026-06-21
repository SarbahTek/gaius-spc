from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserProfileSerializer,
)


class RegisterView(generics.CreateAPIView):
    """
    POST /api/accounts/register/
    Creates account and returns JWT tokens immediately.
    No separate login step needed after registration.
    """
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token = CustomTokenObtainPairSerializer.get_token(user)

        return Response(
            {
                "message": "Account created successfully.",
                "user": {
                    "id":       user.pk,
                    "username": user.username,
                    "email":    user.email,
                    "role":     user.role,
                },
                "tokens": {
                    "access":  str(token.access_token),
                    "refresh": str(token),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """
    POST /api/accounts/login/
    Returns access + refresh tokens with role embedded.
    """
    serializer_class = CustomTokenObtainPairSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/accounts/me/  → own profile
    PUT  /api/accounts/me/  → update bio / avatar
    """
    serializer_class   = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user