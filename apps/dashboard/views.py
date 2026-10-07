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
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class StaffReadAdminWrite(BasePermission):
    def has_permission(self, request, view) -> bool:
        return has_role(request.user, "staff" if request.method in SAFE_METHODS else "admin")


def paid_orders():
    return Order.objects.filter(payment_status=PaymentStatus.SUCCESSFUL).exclude(status=OrderStatus.CANCELLED)


class StatsView(APIView):
    permission_classes = [IsStaff]

    def get(self, request) -> Response:
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
