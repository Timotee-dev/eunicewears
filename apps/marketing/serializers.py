from rest_framework import serializers

from .models import PromoCode, Review


class ReviewInputSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "rating", "title", "comment", "author", "created_at"]

    def get_author(self, review: Review) -> str:
        u = review.user
        return f"{u.first_name} {u.last_name[:1]}.".strip() if u.last_name else u.first_name


class AdminReviewSerializer(ReviewSerializer):
    product = serializers.CharField(source="product.name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta(ReviewSerializer.Meta):
        fields = ReviewSerializer.Meta.fields + ["product", "email", "status"]
        read_only_fields = ["rating", "title", "comment"]


class EmailOnlySerializer(serializers.Serializer):
    email = serializers.EmailField()


class BackInStockSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    email = serializers.EmailField(required=False, allow_blank=True)


class WishlistInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class MessageSerializer(serializers.Serializer):
    message = serializers.CharField()


class AdminPromoSerializer(serializers.ModelSerializer):
    times_used = serializers.SerializerMethodField()
    discount_given = serializers.SerializerMethodField()

    class Meta:
        model = PromoCode
        fields = ["id", "code", "percent_off", "amount_off", "min_order", "max_discount", "starts_on", "ends_on",
                  "usage_limit", "per_customer_limit", "is_active", "times_used", "discount_given"]

    def get_times_used(self, promo: PromoCode) -> int:
        return len(promo.usages.all())

    def get_discount_given(self, promo: PromoCode) -> int:
        return sum(u.discount for u in promo.usages.all())

    def validate(self, attrs: dict) -> dict:
        get = lambda name: attrs.get(name, getattr(self.instance, name, None))  # noqa: E731
        percent, amount = get("percent_off"), get("amount_off")
        if bool(percent) == bool(amount):
            raise serializers.ValidationError({"percent_off": ["Set either a percentage or a fixed amount, not both."]})
        if percent and not 1 <= percent <= 100:
            raise serializers.ValidationError({"percent_off": ["Use a percentage from 1 to 100."]})
        if amount is not None and amount <= 0 and not percent:
            raise serializers.ValidationError({"amount_off": ["Amount must be above zero."]})
        if get("starts_on") and get("ends_on") and get("ends_on") < get("starts_on"):
            raise serializers.ValidationError({"ends_on": ["The end date is before the start date."]})
        attrs["percent_off"], attrs["amount_off"] = percent or None, amount or None
        return attrs
