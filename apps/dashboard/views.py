"""Owner dashboard API. Every endpoint states its minimum role; the server enforces it."""
from datetime import timedelta

from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.catalog.models import Category, InventoryTransaction, Product, ProductImage, ProductVariant
from apps.catalog.serializers import CategorySerializer, ImageSerializer
from apps.catalog.services import adjust_stock
from apps.core import audit
from apps.core.permissions import IsStaff, has_role
from apps.orders import services as order_services
from apps.orders.models import Order, OrderItem, OrderStatus, PaymentStatus

from .serializers import (
    AdminOrderDetailSerializer,
    AdminOrderListSerializer,
    AdminProductSerializer,
    AdminVariantSerializer,
    StockAdjustSerializer,
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Swatch colours for common colour names, so the owner never has to pick one by hand.
COLOUR_HEX = {
    "black": "#111111", "white": "#FFFFFF", "cream": "#EFE3D3", "brown": "#6B4226", "chocolate": "#4A2C18",
    "grey": "#8A8A8A", "gray": "#8A8A8A", "ash": "#B8B8B8", "navy": "#1F2A44", "blue": "#2F5DA8", "sky blue": "#8EC5E8",
    "red": "#B3261E", "wine": "#6A1B2A", "burgundy": "#6A1B2A", "green": "#2F6B45", "olive": "#5B5F3A",
    "pink": "#E8A0B4", "beige": "#D9C5A0", "khaki": "#B9A66B", "yellow": "#E6C229", "mustard": "#C99A1E",
    "orange": "#D9772B", "purple": "#6B4A8A", "lilac": "#B9A3D6", "nude": "#D8B49A", "tan": "#B88A5E",
}


class QuickSizesSerializer(serializers.Serializer):
    fit = serializers.ChoiceField(choices=["oversized", "regular", ""], allow_blank=True, default="")
    sizes = serializers.ListField(child=serializers.CharField(max_length=10), min_length=1, max_length=12)
    colors = serializers.ListField(child=serializers.CharField(max_length=40), min_length=1, max_length=12)
    quantity = serializers.IntegerField(min_value=0, max_value=100000)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class StaffReadAdminWrite(BasePermission):
    def has_permission(self, request, view) -> bool:
        return has_role(request.user, "staff" if request.method in SAFE_METHODS else "admin")


def paid_orders():
    return Order.objects.filter(payment_status=PaymentStatus.SUCCESSFUL).exclude(status=OrderStatus.CANCELLED)


class StatsView(APIView):
    permission_classes = [IsStaff]

    def get(self, request) -> Response:
        order_services.tidy_unpaid()
        now = timezone.localtime()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        def revenue(since=None) -> int:
            qs = paid_orders().filter(paid_at__gte=since) if since else paid_orders()
            return qs.aggregate(t=Sum("total"))["t"] or 0

        daily = []
        for offset in range(6, -1, -1):
            start = today - timedelta(days=offset)
            day_total = paid_orders().filter(paid_at__gte=start, paid_at__lt=start + timedelta(days=1)).aggregate(t=Sum("total"))["t"] or 0
            daily.append({"date": start.date().isoformat(), "revenue": day_total})
        low = ProductVariant.objects.filter(is_active=True, product__archived_at__isnull=True, stock__lte=F("low_stock_threshold"))
        top = (OrderItem.objects.filter(order__in=paid_orders()).values("product_name")
               .annotate(units=Sum("quantity"), revenue=Sum("line_total")).order_by("-units")[:5])
        return Response({
            "revenue": {"today": revenue(today), "week": revenue(today - timedelta(days=6)),
                        "month": revenue(today - timedelta(days=29)), "all_time": revenue()},
            "orders": {"total": Order.objects.count(),
                       "to_fulfil": Order.objects.filter(status__in=[OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.READY]).count(),
                       "awaiting_payment": Order.objects.filter(status=OrderStatus.PENDING_PAYMENT).count()},
            "customers": User.objects.filter(role=Role.CUSTOMER).count(),
            "products": Product.objects.filter(archived_at__isnull=True).count(),
            "daily_revenue": daily,
            "low_stock": [{"product_id": v.product_id, "product": v.product.name, "label": v.label, "stock": v.stock}
                          for v in low.select_related("product").order_by("stock")[:10]],
            "low_stock_count": low.count(),
            "top_products": list(top),
            "recent_orders": AdminOrderListSerializer(Order.objects.select_related("user")[:6], many=True).data,
        })


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = AdminProductSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_queryset(self):
        qs = Product.objects.filter(archived_at__isnull=True).select_related("category").prefetch_related("variants", "images")
        if q := self.request.query_params.get("q", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(variants__sku__icontains=q)).distinct()
        return qs

    def perform_create(self, serializer) -> None:
        audit.record("product.created", request=self.request, obj=serializer.save())

    def perform_update(self, serializer) -> None:
        audit.record("product.updated", request=self.request, obj=serializer.save(),
                     changes={k: str(v) for k, v in serializer.validated_data.items()})

    def perform_destroy(self, instance: Product) -> None:
        # Archive, never delete: past orders still point at this product.
        instance.archived_at, instance.is_published = timezone.now(), False
        instance.save(update_fields=["archived_at", "is_published", "updated_at"])
        audit.record("product.archived", request=self.request, obj=instance)

    @action(detail=True, methods=["post"], url_path="sizes")
    def quick_sizes(self, request, pk=None) -> Response:
        """Add every size in every colour in one go. A combination that already exists just gets the quantity added."""
        product = self.get_object()
        data = QuickSizesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        sizes = list(dict.fromkeys(s.strip().upper() for s in d["sizes"] if s.strip()))
        colors = list(dict.fromkeys(c.strip().title() for c in d["colors"] if c.strip()))
        if not sizes or not colors:
            raise serializers.ValidationError("Choose at least one size and one colour.")
        for color in colors:
            for size in sizes:
                variant = product.variants.filter(fit=d["fit"], size__iexact=size, color__iexact=color).first()
                if variant is None:
                    base = f"P{product.pk}-{(d['fit'][:3] or 'ONE')}-{color.replace(' ', '')[:4]}-{size}".upper()
                    sku, n = base, 2
                    while ProductVariant.objects.filter(sku=sku).exists():
                        sku, n = f"{base}-{n}", n + 1
                    variant = ProductVariant.objects.create(
                        product=product, fit=d["fit"], size=size, color=color, sku=sku,
                        color_hex=COLOUR_HEX.get(color.lower(), "#C9B8A3"))
                if d["quantity"]:
                    adjust_stock(variant.pk, d["quantity"], InventoryTransaction.Reason.RESTOCK, actor=request.user, note="Added from the product page")
        audit.record("product.sizes_added", request=request, obj=product,
                     changes={"fit": d["fit"], "sizes": sizes, "colors": colors, "quantity": d["quantity"]})
        return Response(AdminProductSerializer(self.get_queryset().get(pk=product.pk), context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="images")
    def upload_image(self, request, pk=None) -> Response:
        product = self.get_object()
        file = request.FILES.get("image")
        if file is None:
            raise serializers.ValidationError({"image": ["Choose an image to upload."]})
        if file.size > MAX_IMAGE_BYTES or file.content_type not in IMAGE_TYPES:
            raise serializers.ValidationError({"image": ["Use a JPG, PNG or WebP image under 5 MB."]})
        field = serializers.ImageField()  # Pillow confirms it really is an image
        image = ProductImage.objects.create(
            product=product, image=field.run_validation(file), alt=request.data.get("alt", "")[:160] or product.name,
            position=product.images.count(),
        )
        return Response(ImageSerializer(image).data, status=201)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request, pk=None) -> Response:
        product = self.get_object()
        ids = request.data.get("ids") or []
        images = {i.pk: i for i in product.images.all()}
        if sorted(ids) != sorted(images):
            raise serializers.ValidationError("Send every image id for this product exactly once.")
        for position, image_id in enumerate(ids):
            ProductImage.objects.filter(pk=image_id).update(position=position)
        return Response(ImageSerializer(product.images.all(), many=True).data)


class ImageDeleteView(generics.DestroyAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ImageSerializer
    queryset = ProductImage.objects.all()

    def perform_destroy(self, instance: ProductImage) -> None:
        instance.image.delete(save=False)
        instance.delete()


class VariantViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = AdminVariantSerializer
    queryset = ProductVariant.objects.select_related("product")

    @action(detail=True, methods=["post"], permission_classes=[IsStaff])
    def stock(self, request, pk=None) -> Response:
        data = StockAdjustSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        delta = data.validated_data["delta"]
        reason = InventoryTransaction.Reason.RESTOCK if delta > 0 else InventoryTransaction.Reason.ADJUSTMENT
        variant = adjust_stock(self.get_object().pk, delta, reason, actor=request.user, note=data.validated_data["note"])
        audit.record("inventory.adjusted", request=request, obj=variant, changes={"delta": delta, "stock": variant.stock})
        return Response(AdminVariantSerializer(variant).data)


class CategoryView(generics.ListCreateAPIView):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    pagination_class = None


class OrderListView(generics.ListAPIView):
    permission_classes = [IsStaff]
    serializer_class = AdminOrderListSerializer

    def get_queryset(self):
        qs = Order.objects.select_related("user")
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if q := p.get("q", "").strip():
            qs = qs.filter(Q(number__icontains=q) | Q(email__icontains=q) | Q(user__first_name__icontains=q)
                           | Q(user__last_name__icontains=q) | Q(phone__icontains=q))
        return qs


class OrderDetailView(APIView):
    permission_classes = [IsStaff]

    def get_order(self, number: str) -> Order:
        return get_object_or_404(Order.objects.select_related("user").prefetch_related("items", "events__actor", "payments"), number=number)

    def get(self, request, number: str) -> Response:
        return Response(AdminOrderDetailSerializer(self.get_order(number)).data)

    def patch(self, request, number: str) -> Response:
        order = self.get_order(number)
        order.internal_notes = str(request.data.get("internal_notes", order.internal_notes))[:5000]
        order.save(update_fields=["internal_notes", "updated_at"])
        return Response(AdminOrderDetailSerializer(order).data)


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    tracking_number = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class OrderStatusView(APIView):
    permission_classes = [IsStaff]

    def post(self, request, number: str) -> Response:
        data = OrderStatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = get_object_or_404(Order, number=number)
        v = data.validated_data
        order_services.change_status(order.pk, v["status"], request=request, note=v["note"], tracking_number=v["tracking_number"])
        return OrderDetailView().get(request, number)
