from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OtpCode

# Register your models here.
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "phone_number", "role", "email_verified", "is_active", "created_at")
    list_filter      = ("role", "is_active", "is_staff", "email_verified", "phone_verified")
    search_fields    = ("username", "email", "phone_number")
    fieldsets        = BaseUserAdmin.fieldsets + (
        ("Platform", {"fields": (
            "role", "bio", "avatar", "phone_number", "date_of_birth", "profile_photo",
            "email_verified", "phone_verified", "terms_accepted", "terms_accepted_at",
        )}),
    )


@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display  = ("identifier", "purpose", "channel", "is_used", "attempts", "created_at", "expires_at")
    list_filter   = ("purpose", "channel", "is_used")
    search_fields = ("identifier",)
