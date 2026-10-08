from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent"]


class ImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "url", "alt", "position"]

    def get_url(self, obj: ProductImage) -> str:
        return obj.image.url


class PublicVariantSerializer(serializers.ModelSerializer):
    """Customers see availability, never the exact stock count unless it is genuinely low."""

    price = serializers.IntegerField(source="unit_price")
    availability = serializers.SerializerMethodField()
    left = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ["id", "fit", "size", "color", "color_hex", "price", "availability", "left"]

    def get_availability(self, v: ProductVariant) -> str:
        return "out" if v.stock == 0 else "low" if v.stock <= v.low_stock_threshold else "in_stock"

    def get_left(self, v: ProductVariant) -> int | None:
        return v.stock if 0 < v.stock <= v.low_stock_threshold else None


class ProductListSerializer(serializers.ModelSerializer):
    current_price = serializers.IntegerField()
    image = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()
    category = serializers.CharField(source="category.name")
    wholesale = serializers.SerializerMethodField()

    def get_wholesale(self, p: Product) -> dict | None:
        from .pricing import wholesale_terms

        terms = wholesale_terms(p)
        return {"pack": terms[0], "price": terms[1], "each": terms[1] // terms[0]} if terms else None

    class Meta:
        model = Product
        fields = ["id", "name", "slug", "short_description", "category", "price", "discount_price", "current_price",
                  "image", "in_stock", "colors", "is_new_arrival", "is_best_seller", "wholesale"]

    def _variants(self, p: Product) -> list[ProductVariant]:
        return [v for v in p.variants.all() if v.is_active]  # prefetched

    def get_image(self, p: Product) -> dict | None:
        images = list(p.images.all())
        return ImageSerializer(images[0]).data if images else None

    def get_in_stock(self, p: Product) -> bool:
        return any(v.stock > 0 for v in self._variants(p))

    def get_colors(self, p: Product) -> list[dict]:
        seen: dict[str, str] = {}
        for v in self._variants(p):
            seen.setdefault(v.color, v.color_hex)
        return [{"name": k, "hex": h} for k, h in seen.items()]


class ProductDetailSerializer(ProductListSerializer):
    images = ImageSerializer(many=True)
    variants = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ["description", "materials", "care_instructions", "images", "variants"]

    def get_variants(self, p: Product) -> list[dict]:
        return PublicVariantSerializer(self._variants(p), many=True).data
