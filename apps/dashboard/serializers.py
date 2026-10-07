from rest_framework import serializers

from apps.catalog.models import InventoryTransaction, Product, ProductVariant
from apps.catalog.serializers import ImageSerializer
from apps.catalog.services import adjust_stock
from apps.orders.models import Order, OrderEvent, Payment
from apps.orders.serializers import OrderItemSerializer


class AdminVariantSerializer(serializers.ModelSerializer):
    initial_stock = serializers.IntegerField(min_value=0, write_only=True, required=False, default=0)

    class Meta:
        model = ProductVariant
        fields = ["id", "product", "fit", "size", "color", "color_hex", "sku", "price_override", "stock",
                  "low_stock_threshold", "is_active", "initial_stock"]
        read_only_fields = ["stock"]  # stock only moves through the ledger

    def validate_price_override(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Price must be above zero.")
        return value

    def create(self, validated_data: dict) -> ProductVariant:
        initial = validated_data.pop("initial_stock", 0)
        variant = super().create(validated_data)
        if initial:
            variant = adjust_stock(variant.pk, initial, InventoryTransaction.Reason.RESTOCK,
                                   actor=self.context["request"].user, note="Opening stock")
        return variant

    def update(self, instance, validated_data: dict) -> ProductVariant:
        validated_data.pop("initial_stock", None)
        validated_data.pop("product", None)
        return super().update(instance, validated_data)


class AdminProductSerializer(serializers.ModelSerializer):
    variants = AdminVariantSerializer(many=True, read_only=True)
    images = ImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "slug", "short_description", "description", "category", "category_name", "price",
                  "discount_price", "materials", "care_instructions", "is_published", "is_featured", "is_best_seller",
                  "is_new_arrival", "variants", "images", "total_stock", "created_at"]
        read_only_fields = ["slug"]

    def get_total_stock(self, p: Product) -> int:
        return sum(v.stock for v in p.variants.all())

    def validate(self, attrs: dict) -> dict:
        price = attrs.get("price", getattr(self.instance, "price", None))
        discount = attrs.get("discount_price", getattr(self.instance, "discount_price", None))
        if price is not None and price <= 0:
            raise serializers.ValidationError({"price": ["Price must be above zero."]})
        if discount is not None and not 0 < discount < price:
            raise serializers.ValidationError({"discount_price": ["Sale price must be above zero and below the price."]})
        return attrs


class StockAdjustSerializer(serializers.Serializer):
    delta = serializers.IntegerField()
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_delta(self, value: int) -> int:
        if value == 0:
            raise serializers.ValidationError("Enter how many units to add or remove.")
        return value


class AdminOrderListSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    customer = serializers.CharField(source="user.full_name")

    class Meta:
        model = Order
        fields = ["number", "customer", "email", "status", "status_label", "payment_status", "total", "created_at"]


class AdminEventSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    actor = serializers.CharField(source="actor.full_name", default="System")

    class Meta:
        model = OrderEvent
        fields = ["status_label", "note", "is_public", "actor", "created_at"]


class AdminPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["reference", "provider", "amount", "status", "paid_at"]


class AdminOrderDetailSerializer(AdminOrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = AdminEventSerializer(many=True, read_only=True)
    payments = AdminPaymentSerializer(many=True, read_only=True)
    next_statuses = serializers.SerializerMethodField()

    class Meta(AdminOrderListSerializer.Meta):
        fields = AdminOrderListSerializer.Meta.fields + [
            "phone", "subtotal", "discount", "promo_code", "shipping_fee", "shipping_method", "is_pickup", "shipping_address",
            "tracking_number", "internal_notes", "items", "events", "payments", "next_statuses",
        ]

    def get_next_statuses(self, order: Order) -> list[dict]:
        from apps.orders.models import OrderStatus
        from apps.orders.services import TRANSITIONS

        return [{"value": s, "label": OrderStatus(s).label} for s in sorted(TRANSITIONS[order.status])]
