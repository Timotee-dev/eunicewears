from django.contrib import admin

from .models import Order, Payment, ShippingMethod

admin.site.register(ShippingMethod)


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False  # financial records are never deleted


@admin.register(Order)
class OrderAdmin(ReadOnly):
    list_display = ("number", "user", "status", "payment_status", "total", "created_at")


@admin.register(Payment)
class PaymentAdmin(ReadOnly):
    list_display = ("reference", "order", "provider", "amount", "status", "paid_at")
