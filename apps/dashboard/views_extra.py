"""Dashboard API, part two: analytics, customers, settings, reviews, promo codes, newsletter, content."""
import csv
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.catalog.models import HOME_PICKS_PER_CATEGORY, Category, HomePick, Product
from apps.core import audit
from apps.core import content as site_content
from apps.core.models import SiteSetting
from apps.core.permissions import IsAdmin, IsStaff
from apps.marketing.models import NewsletterSubscriber, PromoCode, Review
from apps.marketing.serializers import AdminPromoSerializer, AdminReviewSerializer
from apps.orders.models import Order, OrderItem, ShippingMethod

from .views import StaffReadAdminWrite, paid_orders


def _day(value: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat(value) if value else fallback
    except ValueError:
        return fallback


class AnalyticsView(APIView):
    """Sales for a date range. Every figure comes from orders whose payment the gateway confirmed."""

    permission_classes = [IsStaff]

    def get(self, request) -> Response:
        today = timezone.localdate()
        end = min(_day(request.query_params.get("to"), today), today)
        start = min(_day(request.query_params.get("from"), end - timedelta(days=29)), end)
        if (end - start).days > 730:
            start = end - timedelta(days=730)
        tz = timezone.get_current_timezone()
        orders = paid_orders().annotate(day=TruncDate("paid_at", tzinfo=tz)).filter(day__gte=start, day__lte=end)
        by_day = {r["day"]: r for r in orders.values("day").annotate(revenue=Sum("total"), orders=Count("id"))}
        series = []
        for offset in range((end - start).days + 1):
            d = start + timedelta(days=offset)
            row = by_day.get(d, {})
            series.append({"date": d.isoformat(), "revenue": row.get("revenue", 0), "orders": row.get("orders", 0)})
        totals = orders.aggregate(revenue=Sum("total"), orders=Count("id"), discounts=Sum("discount"), shipping=Sum("shipping_fee"))
        items = OrderItem.objects.filter(order__in=orders)
        count = totals["orders"] or 0
        new_customers = User.objects.filter(role=Role.CUSTOMER, date_joined__date__gte=start, date_joined__date__lte=end).count()
        return Response({
            "from": start.isoformat(), "to": end.isoformat(), "series": series,
            "totals": {"revenue": totals["revenue"] or 0, "orders": count, "discounts": totals["discounts"] or 0,
                       "shipping": totals["shipping"] or 0, "units": items.aggregate(n=Sum("quantity"))["n"] or 0,
                       "average_order": (totals["revenue"] or 0) // count if count else 0, "new_customers": new_customers},
            "top_products": list(items.values("product_name").annotate(units=Sum("quantity"), revenue=Sum("line_total")).order_by("-revenue")[:8]),
            "by_category": list(items.values(category=F("variant__product__category__name"))
                                .annotate(units=Sum("quantity"), revenue=Sum("line_total")).order_by("-revenue")),
            "top_customers": list(orders.values("email").annotate(orders=Count("id"), spent=Sum("total")).order_by("-spent")[:8]),
            "promo_codes": list(orders.exclude(promo_code="").values("promo_code").annotate(orders=Count("id"), discount=Sum("discount")).order_by("-orders")),
        })


class CustomerSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="full_name")
    orders = serializers.IntegerField(source="order_count")
    spent = serializers.IntegerField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "phone", "date_joined", "is_active", "email_verified", "orders", "spent"]


def customers():
    paid = Q(orders__payment_status="successful") & ~Q(orders__status="cancelled")
    return User.objects.filter(role=Role.CUSTOMER).annotate(
        order_count=Count("orders", filter=paid), spent=Sum("orders__total", filter=paid, default=0))


class CustomerListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = CustomerSerializer

    def get_queryset(self):
        qs = customers().order_by("-date_joined")
        if q := self.request.query_params.get("q", "").strip():
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
        return qs


class ActiveSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class CustomerActiveView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(request=ActiveSerializer, responses=CustomerSerializer)
    def post(self, request, pk: int) -> Response:
        data = ActiveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=pk, role=Role.CUSTOMER)  # staff accounts are managed in the back office
        user.is_active = data.validated_data["is_active"]
        user.save(update_fields=["is_active"])
        audit.record("customer.enabled" if user.is_active else "customer.disabled", request=request, obj=user)
        return Response(CustomerSerializer(customers().get(pk=pk)).data)


class ShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = ["id", "name", "zone", "fee", "free_over", "estimate", "is_active"]

    def validate_fee(self, value: int) -> int:
        if value < 0:
            raise serializers.ValidationError("The fee cannot be negative.")
        return value


class Audited:
    """Record who created or changed a dashboard-managed row."""

    audit_name = ""

    def perform_create(self, serializer) -> None:
        audit.record(f"{self.audit_name}.created", request=self.request, obj=serializer.save())

    def perform_update(self, serializer) -> None:
        audit.record(f"{self.audit_name}.updated", request=self.request, obj=serializer.save(),
                     changes={k: str(v) for k, v in serializer.validated_data.items()})


class NoDelete(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    pagination_class = None


class ShippingMethodViewSet(Audited, NoDelete):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = ShippingMethodSerializer
    queryset = ShippingMethod.objects.order_by("id")
    audit_name = "shipping"


class AdminCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "position", "is_active"]
        read_only_fields = ["slug"]


class CategoryViewSet(Audited, NoDelete):
    permission_classes = [StaffReadAdminWrite]
    serializer_class = AdminCategorySerializer
    queryset = Category.objects.all()
    audit_name = "category"


class PromoCodeViewSet(Audited, NoDelete):
    permission_classes = [IsAdmin]
    serializer_class = AdminPromoSerializer
    queryset = PromoCode.objects.prefetch_related("usages")
    audit_name = "promo"


class ReviewViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaff]
    serializer_class = AdminReviewSerializer

    def get_queryset(self):
        qs = Review.objects.select_related("user", "product")
        if status := self.request.query_params.get("status"):
            qs = qs.filter(status=status)
        return qs

    def perform_update(self, serializer) -> None:
        audit.record("review.moderated", request=self.request, obj=serializer.save(), changes={"status": serializer.instance.status})


class NewsletterView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request) -> Response:
        return Response({"active": NewsletterSubscriber.objects.filter(is_active=True).count()})


class NewsletterExportView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(responses={(200, "text/csv"): str})
    def get(self, request) -> HttpResponse:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="eunice-wears-subscribers.csv"'
        writer = csv.writer(response)
        writer.writerow(["email", "subscribed_on", "unsubscribe_link"])
        for s in NewsletterSubscriber.objects.filter(is_active=True).order_by("created_at"):
            email = "'" + s.email if s.email[0] in "=+-@" else s.email  # no spreadsheet formulas
            writer.writerow([email, s.created_at.date().isoformat(), f"{settings.SITE_URL}/newsletter/unsubscribe/{s.token}/"])
        audit.record("newsletter.exported", request=request)
        return response


class ContentView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request) -> Response:
        values = site_content.get_all()
        return Response([
            {"key": key, "label": spec["label"], "value": values[key],
             "fields": [{"name": n, "label": label, "max": limit, "multiline": multi} for n, label, limit, multi in spec["fields"]]}
            for key, spec in site_content.SCHEMA.items()
        ])


class ContentItemView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request, key: str) -> Response:
        if key not in site_content.SCHEMA:
            return Response({"error": {"code": "not_found", "message": "Unknown content block.", "fields": None}}, status=404)
        value = site_content.clean(key, request.data if isinstance(request.data, dict) else {})
        if key == "home" and not value["headline"]:
            raise serializers.ValidationError({"headline": ["The home page needs a headline."]})
        setting, _ = SiteSetting.objects.update_or_create(key=key, defaults={"value": value})
        audit.record("content.updated", request=request, obj=setting)
        return Response(value)


class HomePicksSerializer(serializers.Serializer):
    product_ids = serializers.ListField(child=serializers.IntegerField(), max_length=HOME_PICKS_PER_CATEGORY, allow_empty=True)


def _home_picks_payload() -> list[dict]:
    rows = []
    for category in Category.objects.filter(is_active=True):
        available = Product.objects.filter(category=category, is_published=True, archived_at__isnull=True).order_by("name")
        picks = HomePick.objects.filter(category=category, product__in=available).values_list("product_id", flat=True)
        rows.append({"id": category.pk, "name": category.name, "limit": HOME_PICKS_PER_CATEGORY,
                     "picks": list(picks), "products": [{"id": p.pk, "name": p.name} for p in available]})
    return rows


class HomePicksView(APIView):
    """Which products appear on the home page, per category."""

    permission_classes = [IsStaff]

    def get(self, request) -> Response:
        return Response(_home_picks_payload())


class HomePicksCategoryView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request, pk: int) -> Response:
        category = get_object_or_404(Category, pk=pk)
        data = HomePicksSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(data.validated_data["product_ids"]))  # keep order, drop repeats
        valid = set(Product.objects.filter(pk__in=ids, category=category, is_published=True, archived_at__isnull=True).values_list("pk", flat=True))
        if len(valid) != len(ids):
            raise serializers.ValidationError("One of those products is not published in this category. Refresh and choose again.")
        HomePick.objects.filter(category=category).delete()
        HomePick.objects.bulk_create([HomePick(category=category, product_id=pid, position=i) for i, pid in enumerate(ids)])
        audit.record("home.picks_updated", request=request, obj=category, changes={"product_ids": ids})
        return Response(_home_picks_payload())
