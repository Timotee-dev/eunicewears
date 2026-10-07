from rest_framework import serializers

from .models import Order, OrderEvent, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["product_name", "variant_label", "sku", "unit_price", "quantity", "line_total"]


class OrderEventSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")

    class Meta:
        model = OrderEvent
        fields = ["status", "status_label", "note", "created_at"]


class OrderListSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    payment_status_label = serializers.CharField(source="get_payment_status_display")

    class Meta:
        model = Order
        fields = ["number", "status", "status_label", "payment_status", "payment_status_label", "total", "currency", "created_at"]


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True)
    events = serializers.SerializerMethodField()

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + [
            "subtotal", "discount", "promo_code", "shipping_fee", "shipping_method", "is_pickup", "shipping_address",
            "tracking_number", "items", "events",
        ]

    def get_events(self, order: Order) -> list[dict]:
        return OrderEventSerializer([e for e in order.events.all() if e.is_public], many=True).data


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    pickup = serializers.BooleanField(default=False)
    promo_code = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
