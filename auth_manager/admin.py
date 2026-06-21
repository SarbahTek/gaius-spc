from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

# Register your models here.
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_active", "created_at")
    list_filter      = ("role", "is_active", "is_staff")
    search_fields    = ("username", "email")
    fieldsets        = BaseUserAdmin.fieldsets + (
        ("Platform", {"fields": ("role", "bio", "avatar")}),
    )
