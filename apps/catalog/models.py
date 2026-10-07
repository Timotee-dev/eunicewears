"""Catalog and stock. All money is integer kobo; stock always lives on the variant."""
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


def unique_slug(model, name: str, pk=None) -> str:
    base = slugify(name)[:200] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exclude(pk=pk).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


class Category(TimeStampedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs) -> None:
        self.slug = self.slug or unique_slug(Category, self.name, self.pk)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Collection(TimeStampedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs) -> None:
        self.slug = self.slug or unique_slug(Collection, self.name, self.pk)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Product(TimeStampedModel):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    collections = models.ManyToManyField(Collection, blank=True, related_name="products")
    price = models.BigIntegerField(help_text="kobo")
    discount_price = models.BigIntegerField(null=True, blank=True, help_text="kobo; must be below price")
    materials = models.CharField(max_length=255, blank=True)
    care_instructions = models.TextField(blank=True)
    is_published = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False)
    is_best_seller = models.BooleanField(default=False)
    is_new_arrival = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)  # soft delete; order history keeps working

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(price__gt=0), name="product_price_positive"),
            models.CheckConstraint(
                condition=Q(discount_price__isnull=True) | Q(discount_price__gt=0, discount_price__lt=F("price")),
                name="product_discount_below_price",
            ),
        ]
        indexes = [models.Index(fields=["is_published", "archived_at", "-created_at"])]

    def save(self, *args, **kwargs) -> None:
        self.slug = self.slug or unique_slug(Product, self.name, self.pk)
        super().save(*args, **kwargs)

    @property
    def current_price(self) -> int:
        return self.discount_price or self.price

    def __str__(self) -> str:
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt = models.CharField(max_length=160, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]


class Fit(models.TextChoices):
    OVERSIZED = "oversized", "Oversized"
    REGULAR = "regular", "Regular"
    NONE = "", "One fit"


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    fit = models.CharField(max_length=20, choices=Fit.choices, blank=True)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=40)
    color_hex = models.CharField(max_length=7, blank=True)
    sku = models.CharField(max_length=64, unique=True)
    price_override = models.BigIntegerField(null=True, blank=True, help_text="kobo; blank = product price")
    stock = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["fit", "color", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "fit", "size", "color"], name="unique_variant_options"),
            models.CheckConstraint(condition=Q(stock__gte=0), name="variant_stock_not_negative"),
        ]

    @property
    def unit_price(self) -> int:
        return self.price_override or self.product.current_price

    @property
    def label(self) -> str:
        return " / ".join(p for p in [self.get_fit_display() if self.fit else "", self.size, self.color] if p)

    def __str__(self) -> str:
        return f"{self.product.name} ({self.label})"


class InventoryTransaction(models.Model):
    """Append-only stock ledger. variant.stock is the running total of these rows."""

    class Reason(models.TextChoices):
        RESTOCK = "restock", "Restock"
        SALE = "sale", "Sale"
        RELEASE = "release", "Released (unpaid or cancelled order)"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="transactions")
    delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.CharField(max_length=255, blank=True)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


HOME_PICKS_PER_CATEGORY = 10


class HomePick(models.Model):
    """A product the owner chose to show on the home page. Up to ten per category, in the owner's order."""

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="home_picks")
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="home_pick")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.product.name}"
