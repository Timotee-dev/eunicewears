import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Address

from . import services
from .models import Order, Payment
from .payments import InvalidWebhook, ProviderError, get_provider
from .serializers import CheckoutSerializer, OrderDetailSerializer, OrderListSerializer

logger = logging.getLogger("eunice.payments")


class CheckoutBase(APIView):
    permission_classes = [IsAuthenticated]

    def inputs(self, request) -> tuple[Address, bool, str]:
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        address = Address.objects.filter(pk=data.validated_data["address_id"], user=request.user).first()
        if address is None:
            raise serializers.ValidationError({"address_id": ["Choose a delivery address."]})
        return address, data.validated_data["pickup"], data.validated_data["promo_code"].strip()


class QuoteView(CheckoutBase):
    def post(self, request) -> Response:
        return Response(services.quote(request, *self.inputs(request)))


class CheckoutView(CheckoutBase):
    throttle_scope = "checkout"

    def post(self, request) -> Response:
        services.tidy_unpaid()
        order, payment, url = services.place_order(request, *self.inputs(request))
        return Response({"order_number": order.number, "reference": payment.reference, "authorization_url": url}, status=201)


class ReferenceSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=64)


class VerifyPaymentView(APIView):
    """The return page calls this. It reports what the gateway says, not what the browser claims."""

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        data = ReferenceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reference = data.validated_data["reference"]
        if not Payment.objects.filter(reference=reference, order__user=request.user).exists():
            raise NotFound("We could not find that payment.")
        try:
            payment = services.confirm_payment(reference)
        except ProviderError:
            payment = Payment.objects.get(reference=reference)  # still pending; the webhook will settle it
        order = Order.objects.get(pk=payment.order_id)
        return Response({"order_number": order.number, "payment_status": payment.status, "order_status": order.status, "total": order.total})


@csrf_exempt  # authenticated by the gateway's HMAC signature instead
@require_POST
def webhook(request) -> HttpResponse:
    try:
        reference = get_provider("paystack").parse_webhook(request.body, request.headers)
    except (InvalidWebhook, ProviderError):
        logger.warning("webhook_rejected")
        return HttpResponse(status=400)
    if reference and Payment.objects.filter(reference=reference).exists():
        try:
            services.confirm_payment(reference)
        except ProviderError:
            return HttpResponse(status=503)  # gateway unreachable: ask Paystack to retry later
    logger.info("webhook_processed ref=%s", reference)
    return HttpResponse(status=200)


class SandboxOutcomeView(APIView):
    """DEBUG-only stand-in for the Paystack payment page."""

    permission_classes = [IsAuthenticated]

    def post(self, request, reference: str) -> Response:
        if not (settings.DEBUG and settings.PAYMENT_PROVIDER == "sandbox"):
            raise NotFound()
        payment = get_object_or_404(Payment, reference=reference, order__user=request.user, provider="sandbox")
        outcome = request.data.get("outcome")
        if outcome not in ("success", "failed"):
            raise serializers.ValidationError("Choose approve or decline.")
        if not payment.raw.get("sandbox_outcome"):
            payment.raw = {"sandbox_outcome": outcome}
            payment.save(update_fields=["raw", "updated_at"])
        return Response({"reference": reference})


class OrderListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderDetailSerializer
    lookup_field = "number"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items", "events")
