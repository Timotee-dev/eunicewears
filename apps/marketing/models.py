import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import Product, ProductVariant
from apps.core.models import TimeStampedModel


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="one_wishlist_row_per_product")]


class Review(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        HIDDEN = "hidden", "Hidden"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120, blank=True)
    comment = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="one_review_per_customer_per_product"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
        ]


class PromoCode(TimeStampedModel):
    code = models.CharField(max_length=30, unique=True)
    percent_off = models.PositiveSmallIntegerField(null=True, blank=True)
    amount_off = models.BigIntegerField(null=True, blank=True, help_text="kobo")
    min_order = models.BigIntegerField(default=0, help_text="kobo")
    max_discount = models.BigIntegerField(null=True, blank=True, help_text="kobo; caps a percentage code")
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    per_customer_limit = models.PositiveIntegerField(null=True, blank=True, default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(percent_off__isnull=False, amount_off__isnull=True, percent_off__gte=1, percent_off__lte=100)
                           | Q(percent_off__isnull=True, amount_off__isnull=False, amount_off__gt=0)),
                name="promo_is_percent_or_amount",
            )
        ]

    def save(self, *args, **kwargs) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def discount_for(self, subtotal: int) -> int:
        if self.percent_off:
            discount = subtotal * self.percent_off // 100
            if self.max_discount is not None:
                discount = min(discount, self.max_discount)
        else:
            discount = self.amount_off or 0
        return max(0, min(discount, subtotal))

    def __str__(self) -> str:
        return self.code


class PromoCodeUsage(models.Model):
    """One row per order that used a code. Removed again if that order is cancelled or never paid."""

    promo = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name="usages")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="promo_usage")
    discount = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.email


class BackInStockRequest(models.Model):
    email = models.EmailField()
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="stock_requests")
    notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["email", "variant"], condition=Q(notified_at__isnull=True), name="one_open_stock_request")
        ]
