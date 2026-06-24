from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password       = serializers.CharField(write_only=True, validators=[validate_password])
    password2      = serializers.CharField(write_only=True, label="Confirm password")
    terms_accepted = serializers.BooleanField(write_only=True)

    class Meta:
        model  = User
        fields = (
            "username", "email", "password", "password2", "role",
            "first_name", "last_name", "date_of_birth", "profile_photo",
            "phone_number", "terms_accepted",
        )
        extra_kwargs = {
            "email":         {"required": True},
            "first_name":    {"required": True},
            "last_name":     {"required": True},
            "date_of_birth": {"required": True},
            "phone_number":  {"required": True},
            "profile_photo": {"required": False},
        }

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the Privacy Policy and Terms to create an account."
            )
        return value

    def validate_phone_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("An account with that phone number already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        from django.utils import timezone
        from . import otp_service
        from .models import OtpCode

        validated_data.pop("terms_accepted", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.terms_accepted    = True
        user.terms_accepted_at = timezone.now()
        user.email_verified    = False
        user.save()

        # Kick off email verification immediately.
        otp_service.issue(user.email, OtpCode.PURPOSE_EMAIL_VERIFY, OtpCode.CHANNEL_EMAIL)
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Password login that accepts a username OR an email in the username field.

    The client sends `username` (which may actually be an email); we resolve it
    to the real username before the parent serializer authenticates.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"]     = user.role
        token["username"] = user.username
        return token

    def validate(self, attrs):
        identifier = attrs.get(self.username_field, "").strip()
        if identifier and "@" in identifier:
            match = User.objects.filter(email__iexact=identifier).first()
            if match:
                attrs[self.username_field] = match.username

        data              = super().validate(attrs)
        data["username"]  = self.user.username
        data["role"]      = self.user.role
        data["email"]     = self.user.email
        return data


# ─────────────────────────────────────────────
# OTP — email verification & phone login
# ─────────────────────────────────────────────

class OtpRequestSerializer(serializers.Serializer):
    """Request a code. `purpose` decides the channel and target lookup."""
    PURPOSES = ("email_verify", "phone_login", "phone_verify")

    identifier = serializers.CharField()   # email (email_verify) or phone (phone_*)
    purpose    = serializers.ChoiceField(choices=PURPOSES)

    def validate_identifier(self, value):
        return value.strip()


class OtpVerifySerializer(serializers.Serializer):
    identifier = serializers.CharField()
    purpose    = serializers.ChoiceField(choices=OtpRequestSerializer.PURPOSES)
    code       = serializers.CharField(max_length=10)

    def validate_identifier(self, value):
        return value.strip()


class UserProfileSerializer(serializers.ModelSerializer):
    profile_photo_url = serializers.SerializerMethodField()
    full_name         = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = (
            "id", "username", "email", "role", "bio", "avatar",
            "first_name", "last_name", "full_name",
            "phone_number", "date_of_birth", "profile_photo", "profile_photo_url",
            "email_verified", "phone_verified", "terms_accepted", "created_at",
        )
        # username/email change needs its own re-verification flow, so they're
        # read-only here; everything else is editable via PUT/PATCH /me.
        read_only_fields = ("id", "created_at", "role", "username", "email",
                            "terms_accepted", "email_verified", "phone_verified")
        extra_kwargs = {"profile_photo": {"write_only": True, "required": False}}

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_profile_photo_url(self, obj):
        request = self.context.get("request")
        if obj.profile_photo:
            url = obj.profile_photo.url
            return request.build_absolute_uri(url) if request else url
        return obj.avatar or None

    def validate_phone_number(self, value):
        # Normalise blank → None so it stays NULL (exempt from the unique
        # constraint); an empty string would clash with other phone-less users.
        if value is None or not value.strip():
            return None
        value = value.strip()
        qs = User.objects.filter(phone_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An account with that phone number already exists.")
        return value

    def update(self, instance, validated_data):
        # Changing the phone number invalidates any prior phone verification.
        new_phone = validated_data.get("phone_number", instance.phone_number)
        if new_phone != instance.phone_number:
            instance.phone_verified = False
        return super().update(instance, validated_data)


class PublicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "avatar",)
     



