from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import ProductVariant
from apps.core.models import TimeStampedModel


class Cart(TimeStampedModel):
    """Signed-in: one cart per user. Guests: the cart id is kept in their server-side session."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="cart")


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="one_line_per_variant"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_quantity_positive"),
        ]
