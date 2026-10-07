from django.db import transaction
from rest_framework.exceptions import APIException

from .models import InventoryTransaction, ProductVariant


class InsufficientStock(APIException):
    status_code = 409
    default_code = "insufficient_stock"
    default_detail = "Not enough stock for this item."


@transaction.atomic
def adjust_stock(variant_id: int, delta: int, reason: str, *, actor=None, order=None, note: str = "") -> ProductVariant:
    """The only way stock changes. Locks the row so concurrent buyers are served one at a time."""
    variant = ProductVariant.objects.select_for_update().select_related("product").get(pk=variant_id)
    if variant.stock + delta < 0:
        raise InsufficientStock(
            f"Only {variant.stock} left of {variant.product.name} ({variant.label})."
            if variant.stock
            else f"{variant.product.name} ({variant.label}) just sold out."
        )
    was_out = variant.stock == 0
    variant.stock += delta
    variant.save(update_fields=["stock", "updated_at"])
    InventoryTransaction.objects.create(
        variant=variant, delta=delta, balance_after=variant.stock, reason=reason, note=note, order=order, actor=actor
    )
    if was_out and variant.stock > 0:
        from apps.marketing.tasks import notify_back_in_stock

        transaction.on_commit(lambda: notify_back_in_stock.delay(variant.pk))
    return variant
