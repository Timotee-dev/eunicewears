from django.contrib import admin

from .models import Category, Collection, InventoryTransaction, Product, ProductImage, ProductVariant

admin.site.register([Category, Collection])


class VariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    readonly_fields = ("stock",)  # stock changes go through the ledger


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_published", "archived_at")
    inlines = [VariantInline, ImageInline]


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "variant", "delta", "balance_after", "reason", "actor")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
