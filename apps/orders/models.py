from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import ProductVariant
from apps.core.models import TimeStampedModel


class ShippingMethod(TimeStampedModel):
    class Zone(models.TextChoices):
        LAGOS = "lagos", "Lagos"
        OTHER_STATES = "other_states", "Other Nigerian states"
        INTERNATIONAL = "international", "International"
        PICKUP = "pickup", "Pickup"

    name = models.CharField(max_length=80)
    zone = models.CharField(max_length=20, choices=Zone.choices)
    fee = models.BigIntegerField(default=0, help_text="kobo")
    free_over = models.BigIntegerField(null=True, blank=True, help_text="kobo; subtotal at which delivery is free")
    estimate = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending payment"
    PAID = "paid", "Paid"
    PROCESSING = "processing", "Processing"
    READY = "ready_for_delivery", "Ready for delivery"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    REFUND_REQUESTED = "refund_requested", "Refund requested"
    REFUNDED = "refunded", "Refunded"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCESSFUL = "successful", "Successful"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class Order(TimeStampedModel):
    number = models.CharField(max_length=20, unique=True, null=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING_PAYMENT, db_index=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    currency = models.CharField(max_length=3, default="NGN")
    subtotal = models.BigIntegerField(default=0)
    discount = models.BigIntegerField(default=0)
    promo_code = models.CharField(max_length=30, blank=True)
    shipping_fee = models.BigIntegerField(default=0)
    total = models.BigIntegerField(default=0)
    shipping_method = models.CharField(max_length=80)
    is_pickup = models.BooleanField(default=False)
    shipping_address = models.JSONField()  # snapshot; later address edits never rewrite history
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    tracking_number = models.CharField(max_length=80, blank=True)
    internal_notes = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(total__gte=0), name="order_total_not_negative")]

    def __str__(self) -> str:
        return self.number or f"order#{self.pk}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=160)
    variant_label = models.CharField(max_length=120)
    sku = models.CharField(max_length=64)
    unit_price = models.BigIntegerField()  # price at time of purchase
    quantity = models.PositiveIntegerField()
    line_total = models.BigIntegerField()


class OrderEvent(models.Model):
    """The order timeline customers see, and the trail the owner audits."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    note = models.CharField(max_length=255, blank=True)
    is_public = models.BooleanField(default=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Payment(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=20)
    reference = models.CharField(max_length=64, unique=True)
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    raw = models.JSONField(default=dict, blank=True)  # provider's verify response, for disputes
    paid_at = models.DateTimeField(null=True, blank=True)
