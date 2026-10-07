from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import CartItem


class AddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


@method_decorator(csrf_protect, name="dispatch")  # guests write here too, so CSRF is enforced explicitly
class CartBase(APIView):
    permission_classes = [AllowAny]

    def summary(self, request, code: int = 200) -> Response:
        return Response(services.summarize(services.get_cart(request)), status=code)


class CartView(CartBase):
    def get(self, request) -> Response:
        return self.summary(request)


class CartItemsView(CartBase):
    def post(self, request) -> Response:
        data = AddSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.add_item(services.get_cart(request, create=True), **data.validated_data)
        return self.summary(request, status.HTTP_201_CREATED)


class CartItemView(CartBase):
    def item(self, request, pk: int) -> CartItem:
        cart = services.get_cart(request)
        return get_object_or_404(CartItem.objects.select_related("variant__product"), pk=pk, cart=cart)  # own cart only

    def patch(self, request, pk: int) -> Response:
        data = QuantitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_quantity(self.item(request, pk), data.validated_data["quantity"])
        return self.summary(request)

    def delete(self, request, pk: int) -> Response:
        self.item(request, pk).delete()
        return self.summary(request)
