from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, CustomerProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "first_name", "last_name", "role", "is_active", "email_verified_at")
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Person", {"fields": ("first_name", "last_name", "phone")}),
        ("Access", {"fields": ("role", "is_active", "is_superuser", "email_verified_at")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "first_name", "last_name", "role", "password1", "password2")}),)


admin.site.register(CustomerProfile)
admin.site.register(Address)
