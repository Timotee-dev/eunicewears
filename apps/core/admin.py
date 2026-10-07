from django.contrib import admin

from .models import AuditLog, SiteSetting

admin.site.register(SiteSetting)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_repr", "ip_address")
    list_filter = ("action",)
    search_fields = ("object_repr", "actor__email")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
