from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework.views import APIView

from .models import User, OtpCode
from . import otp_service
from .serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserProfileSerializer,
    OtpRequestSerializer,
    OtpVerifySerializer,
)


class RegisterView(generics.CreateAPIView):
    """
    POST /api/accounts/register/
    Creates account and returns JWT tokens immediately.
    Accepts JSON or multipart/form-data (for the optional profile photo).
    No separate login step needed after registration.
    """
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token = CustomTokenObtainPairSerializer.get_token(user)

        return Response(
            {
                "message": "Account created successfully.",
                "user": {
                    "id":             user.pk,
                    "username":       user.username,
                    "email":          user.email,
                    "role":           user.role,
                    "first_name":     user.first_name,
                    "last_name":      user.last_name,
                    "phone_number":   user.phone_number,
                    "email_verified": user.email_verified,
                },
                "requires_email_verification": not user.email_verified,
                # Nested form (kept for backwards compatibility)…
                "tokens": {
                    "access":  str(token.access_token),
                    "refresh": str(token),
                },
                # …and flat form so clients can read tokens uniformly with login.
                "access":   str(token.access_token),
                "refresh":  str(token),
                "username": user.username,
                "role":     user.role,
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
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        return self.request.user


# ─────────────────────────────────────────────
# OTP — email verification & phone login
# ─────────────────────────────────────────────

def _user_for(purpose, identifier):
    """Resolve the user an OTP targets, or None."""
    if purpose == OtpCode.PURPOSE_EMAIL_VERIFY:
        return User.objects.filter(email__iexact=identifier).first()
    # phone_login / phone_verify
    return User.objects.filter(phone_number=identifier).first()


class OtpRequestView(APIView):
    """
    POST /api/accounts/otp/request/  body: {identifier, purpose}

    purpose=email_verify → emails a code to that address
    purpose=phone_login  → SMS a code to that phone (must belong to an account)
    purpose=phone_verify → SMS a code to verify a phone
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        purpose    = serializer.validated_data["purpose"]

        user = _user_for(purpose, identifier)
        # For phone_login we must have a matching account; for email_verify we
        # don't leak existence — always respond 200.
        if purpose == OtpCode.PURPOSE_PHONE_LOGIN and not user:
            return Response(
                {"detail": "No account is registered with that phone number."},
                status=status.HTTP_404_NOT_FOUND,
            )

        channel = OtpCode.CHANNEL_EMAIL if purpose == OtpCode.PURPOSE_EMAIL_VERIFY else OtpCode.CHANNEL_SMS
        if user or purpose == OtpCode.PURPOSE_EMAIL_VERIFY:
            otp_service.issue(identifier, purpose, channel)

        return Response({
            "message": "A verification code has been sent.",
            "channel": channel,
            "expires_in_minutes": otp_service._expiry_minutes(),
        })


class OtpVerifyView(APIView):
    """
    POST /api/accounts/otp/verify/  body: {identifier, purpose, code}

    email_verify → marks the account's email verified
    phone_login  → returns JWT tokens (this *is* the login)
    phone_verify → marks the account's phone verified
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        purpose    = serializer.validated_data["purpose"]
        code       = serializer.validated_data["code"]

        ok, error = otp_service.verify(identifier, purpose, code)
        if not ok:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        user = _user_for(purpose, identifier)

        if purpose == OtpCode.PURPOSE_EMAIL_VERIFY:
            if user:
                user.email_verified = True
                user.save(update_fields=["email_verified"])
            return Response({"verified": True, "email_verified": True})

        if purpose == OtpCode.PURPOSE_PHONE_VERIFY:
            if user:
                user.phone_verified = True
                user.save(update_fields=["phone_verified"])
            return Response({"verified": True, "phone_verified": True})

        # phone_login → issue tokens
        if not user:
            return Response({"detail": "No account for that phone number."},
                            status=status.HTTP_404_NOT_FOUND)
        token = CustomTokenObtainPairSerializer.get_token(user)
        return Response({
            "access":   str(token.access_token),
            "refresh":  str(token),
            "username": user.username,
            "role":     user.role,
            "email":    user.email,
        })