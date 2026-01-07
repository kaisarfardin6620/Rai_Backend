from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, OTP

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("id", "username", "email", "phone", "first_name", "last_name", "is_email_verified", "is_phone_verified", "is_staff", "is_active", "is_admin")
    search_fields = ("username", "email", "phone")
    ordering = ("username",)
    fieldsets = UserAdmin.fieldsets + ((None, {"fields": ("phone", "bio", "profile_picture", "date_of_birth", "is_email_verified", "is_phone_verified", "is_admin")}),)

@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("identifier", "code", "created_at")
    search_fields = ("identifier", "code")
    ordering = ("-created_at",)