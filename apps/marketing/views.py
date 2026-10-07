from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.services import purchasable
from apps.catalog.models import ProductVariant
from apps.catalog.serializers import ProductListSerializer
from apps.catalog.views import public_products
from apps.orders.models import OrderItem, OrderStatus

from .models import BackInStockRequest, NewsletterSubscriber, Review, WishlistItem
from .serializers import (
    BackInStockSerializer,
    EmailOnlySerializer,
    MessageSerializer,
    ReviewInputSerializer,
    ReviewSerializer,
    WishlistInputSerializer,
)


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ProductListSerializer(many=True))
    def get(self, request) -> Response:
        products = public_products().filter(wishlisted__user=request.user).order_by("-wishlisted__created_at")
        return Response(ProductListSerializer(products, many=True).data)

    @extend_schema(request=WishlistInputSerializer, responses=MessageSerializer)
    def post(self, request) -> Response:
        data = WishlistInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = get_object_or_404(public_products(), pk=data.validated_data["product_id"])
        WishlistItem.objects.get_or_create(user=request.user, product=product)
        return Response({"message": "Saved to your wishlist."}, status=201)


class WishlistItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def delete(self, request, product_id: int) -> Response:
        WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
        return Response(status=204)


def has_bought(user, product) -> bool:
    return OrderItem.objects.filter(order__user=user, order__status=OrderStatus.DELIVERED, variant__product=product).exists()


class ProductReviewsView(APIView):
    """Anyone can read approved reviews. Only customers whose order was delivered can write one."""

    permission_classes = [AllowAny]
    throttle_scope = "reviews"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(responses=ReviewSerializer(many=True))
    def get(self, request, slug: str) -> Response:
        product = get_object_or_404(public_products(), slug=slug)
        approved = Review.objects.filter(product=product, status=Review.Status.APPROVED).select_related("user")
        stats = approved.aggregate(average=Avg("rating"), count=Count("id"))
        mine = None
        can_review = False
        if request.user.is_authenticated:
            can_review = has_bought(request.user, product)
            own = Review.objects.filter(product=product, user=request.user).first()
            mine = {"rating": own.rating, "title": own.title, "comment": own.comment, "status": own.status} if own else None
        return Response({
            "average": round(stats["average"], 1) if stats["average"] else None, "count": stats["count"],
            "can_review": can_review, "mine": mine, "results": ReviewSerializer(approved[:50], many=True).data,
        })

    @extend_schema(request=ReviewInputSerializer, responses=MessageSerializer)
    def post(self, request, slug: str) -> Response:
        if not request.user.is_authenticated:
            raise NotAuthenticated("Sign in to write a review.")
        product = get_object_or_404(public_products(), slug=slug)
        if not has_bought(request.user, product):
            raise PermissionDenied("You can review this once your order of it has been delivered.")
        data = ReviewInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        Review.objects.update_or_create(
            user=request.user, product=product, defaults={**data.validated_data, "status": Review.Status.PENDING})
        return Response({"message": "Thanks. Your review will show once we have checked it."}, status=201)


@method_decorator(csrf_protect, name="dispatch")
class PublicFormView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "signup_forms"


class NewsletterView(PublicFormView):
    @extend_schema(request=EmailOnlySerializer, responses=MessageSerializer)
    def post(self, request) -> Response:
        data = EmailOnlySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        subscriber, created = NewsletterSubscriber.objects.get_or_create(email=data.validated_data["email"].lower())
        if not created and not subscriber.is_active:
            subscriber.is_active = True
            subscriber.save(update_fields=["is_active", "updated_at"])
        return Response({"message": "You are on the list."})


class BackInStockView(PublicFormView):
    @extend_schema(request=BackInStockSerializer, responses=MessageSerializer)
    def post(self, request) -> Response:
        data = BackInStockSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = (data.validated_data.get("email") or (request.user.email if request.user.is_authenticated else "")).lower()
        if not email:
            raise ValidationError({"email": ["Enter your email."]})
        variant = ProductVariant.objects.select_related("product").filter(pk=data.validated_data["variant_id"]).first()
        if variant is None or not purchasable(variant):
            raise ValidationError("This item is no longer available.")
        if variant.stock > 0:
            raise ValidationError("Good news: this one is in stock right now.")
        BackInStockRequest.objects.get_or_create(email=email, variant=variant, notified_at__isnull=True,
                                                 defaults={"email": email, "variant": variant})
        return Response({"message": "We will email you when it is back."})
