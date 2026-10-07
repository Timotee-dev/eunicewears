"""Checkout, payment confirmation and the order lifecycle. Every number here is computed server-side."""
import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.accounts.models import Address
from apps.cart import services as cart_services
from apps.catalog.models import InventoryTransaction
from apps.catalog.services import adjust_stock
from apps.core import audit
from apps.core.mail import deliver_template
from apps.core.permissions import has_role
from apps.marketing.models import PromoCodeUsage
from apps.marketing.services import apply_promo

from .models import Order, OrderEvent, OrderItem, OrderStatus, Payment, PaymentStatus, ShippingMethod
from .payments import ProviderError, get_provider

logger = logging.getLogger("eunice.orders")
S = OrderStatus

# The only moves the owner's dashboard may make.
TRANSITIONS: dict[str, set[str]] = {
    S.PENDING_PAYMENT: {S.CANCELLED},
    S.PAID: {S.PROCESSING, S.CANCELLED},
    S.PROCESSING: {S.READY, S.SHIPPED, S.CANCELLED},
    S.READY: {S.SHIPPED, S.DELIVERED, S.CANCELLED},
    S.SHIPPED: {S.DELIVERED},
    S.DELIVERED: {S.REFUND_REQUESTED},
    S.REFUND_REQUESTED: {S.REFUNDED, S.DELIVERED},
    S.CANCELLED: set(),
    S.REFUNDED: set(),
}


class PaymentUnavailable(APIException):
    status_code = 502
    default_code = "payment_unavailable"
    default_detail = "We could not reach the payment provider. Nothing was charged; try again in a moment."


def shipping_for(address: Address, pickup: bool, subtotal: int) -> tuple[ShippingMethod, int]:
    Zone = ShippingMethod.Zone
    if pickup:
        zone = Zone.PICKUP
    elif address.country.upper() != "NG":
        zone = Zone.INTERNATIONAL
    elif address.state.strip().lower() in ("lagos", "lagos state"):
        zone = Zone.LAGOS
    else:
        zone = Zone.OTHER_STATES
    method = ShippingMethod.objects.filter(zone=zone, is_active=True).order_by("id").first()
    if method is None:
        raise ValidationError("Pickup is not available right now." if pickup else "We do not deliver to this location yet.")
    free = method.free_over is not None and subtotal >= method.free_over
    return method, 0 if free else method.fee


def quote(request, address: Address, pickup: bool, promo_code: str = "") -> dict:
    summary = cart_services.summarize(cart_services.get_cart(request))
    if not summary["items"]:
        raise ValidationError("Your cart is empty.")
    method, fee = shipping_for(address, pickup, summary["subtotal"])
    discount = apply_promo(promo_code, request.user, summary["subtotal"])[1] if promo_code else 0
    return {**summary, "shipping_method": method.name, "shipping_estimate": method.estimate, "shipping_fee": fee,
            "discount": discount, "promo_code": promo_code.upper() if promo_code else "",
            "total": summary["subtotal"] - discount + fee}


def _snapshot(a: Address) -> dict:
    return {k: getattr(a, k) for k in
            ("first_name", "last_name", "phone", "country", "state", "city", "line1", "line2", "postal_code", "delivery_instructions")}


def place_order(request, address: Address, pickup: bool, promo_code: str = "") -> tuple[Order, Payment, str]:
    """Runs inside the request transaction: any failure (stock, gateway) rolls the whole thing back."""
    user = request.user
    cart = cart_services.get_cart(request)
    lines = list(cart.items.order_by("variant_id")) if cart else []  # fixed lock order prevents deadlocks
    if not lines:
        raise ValidationError("Your cart is empty.")

    order = Order.objects.create(
        user=user, email=user.email, phone=address.phone, shipping_address=_snapshot(address),
        shipping_method="", is_pickup=pickup, currency=settings.DEFAULT_CURRENCY,
    )
    subtotal = 0
    for line in lines:
        # Locks the variant row, re-reads live stock and price, and reserves the units.
        variant = adjust_stock(line.variant_id, -line.quantity, InventoryTransaction.Reason.SALE, actor=user, order=order)
        if not cart_services.purchasable(variant):
            raise ValidationError(f"{variant.product.name} is no longer available. Remove it from your cart to continue.")
        line_total = variant.unit_price * line.quantity
        subtotal += line_total
        OrderItem.objects.create(
            order=order, variant=variant, product_name=variant.product.name, variant_label=variant.label,
            sku=variant.sku, unit_price=variant.unit_price, quantity=line.quantity, line_total=line_total,
        )
    method, fee = shipping_for(address, pickup, subtotal)
    order.number = f"EW-{order.created_at.year}-{order.pk:06d}"
    discount = 0
    if promo_code:
        # Row lock on the code: two customers cannot both take its last use.
        promo, discount = apply_promo(promo_code, user, subtotal, lock=True)
        PromoCodeUsage.objects.create(promo=promo, user=user, order=order, discount=discount)
        order.promo_code, order.discount = promo.code, discount
    order.subtotal, order.shipping_fee, order.shipping_method = subtotal, fee, method.name
    order.total = subtotal - discount + fee
    order.save()
    OrderEvent.objects.create(order=order, status=S.PENDING_PAYMENT, note="Order placed", actor=user)

    try:
        provider = get_provider()
        payment = Payment.objects.create(
            order=order, provider=provider.name, reference=f"EW{order.pk}-{secrets.token_hex(8)}",
            amount=order.total, currency=order.currency,
        )
        init = provider.initialize(
            reference=payment.reference, amount=payment.amount, currency=payment.currency, email=user.email,
            callback_url=f"{settings.SITE_URL}/order-success/", metadata={"order_number": order.number},
        )
    except ProviderError as exc:
        logger.error("payment_init_failed order=%s error=%s", order.number, exc)
        raise PaymentUnavailable() from exc
    cart.items.all().delete()
    logger.info("order_placed order=%s total=%s", order.number, order.total)
    return order, payment, init.authorization_url


def _release_stock(order: Order, actor=None) -> None:
    PromoCodeUsage.objects.filter(order=order).delete()  # an order that did not happen does not use up a code
    for item in order.items.order_by("variant_id"):
        adjust_stock(item.variant_id, item.quantity, InventoryTransaction.Reason.RELEASE, actor=actor, order=order)


def _send_confirmation(order_id: int) -> None:
    order = Order.objects.prefetch_related("items").get(pk=order_id)
    deliver_template(
        order.email, f"Order {order.number} confirmed", "order_confirmed",
        f"Payment received for order {order.number}. Track it at {settings.SITE_URL}/account/orders/{order.number}/",
        {"order": order},
    )


STATUS_EMAILS = {
    S.PROCESSING: ("We are preparing order {n}", "We are getting your order ready."),
    S.SHIPPED: ("Order {n} is on its way", "Your order has left us and is on its way to you."),
    S.DELIVERED: ("Order {n} was delivered", "Your order has been delivered. We hope you love it."),
    S.CANCELLED: ("Order {n} was cancelled", "Your order has been cancelled. If you paid, the refund is on its way back to you."),
    S.REFUNDED: ("Order {n} was refunded", "We have sent your refund. Banks usually take a few working days to show it."),
}


def _send_status_email(order_id: int, status: str, note: str) -> None:
    order = Order.objects.get(pk=order_id)
    subject, body = STATUS_EMAILS[status]
    deliver_template(
        order.email, subject.format(n=order.number), "order_update",
        f"{body} {settings.SITE_URL}/account/orders/{order.number}/",
        {"order": order, "heading": subject.format(n=order.number), "body": body, "note": note,
         "can_review": status == S.DELIVERED},
    )


def _refund(order: Order, request) -> str:
    """Send the customer's money back through the gateway. Raises before anything is saved if it refuses."""
    if not has_role(request.user, "admin"):
        raise PermissionDenied("Only an admin can refund a paid order.")
    payment = order.payments.filter(status=PaymentStatus.SUCCESSFUL).first()
    if payment is None:
        return ""
    try:
        get_provider(payment.provider).refund(payment.reference, payment.amount)
    except ProviderError as exc:
        raise ValidationError(f"The refund was not accepted ({exc}). The order has not been changed.") from exc
    payment.status = PaymentStatus.REFUNDED
    payment.save(update_fields=["status", "updated_at"])
    order.payment_status = PaymentStatus.REFUNDED
    audit.record("order.refunded", request=request, obj=order, changes={"reference": payment.reference, "amount": payment.amount})
    return "Refund sent through the payment provider."


@transaction.atomic
def confirm_payment(reference: str) -> Payment:
    """Single source of truth for 'is this paid?'. Called by the return page, the webhook and the
    expiry job; safe to call any number of times, in any order."""
    payment = Payment.objects.select_for_update().select_related("order").get(reference=reference)
    if payment.status != PaymentStatus.PENDING:
        return payment  # idempotent: already settled
    result = get_provider(payment.provider).verify(reference)  # ask the gateway, never the browser
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if result.status == "pending":
        return payment
    payment.raw = result.raw

    if result.status == "failed":
        payment.status = PaymentStatus.FAILED
        payment.save()
        if order.status == S.PENDING_PAYMENT:
            order.status, order.payment_status = S.CANCELLED, PaymentStatus.FAILED
            order.save()
            _release_stock(order)
            OrderEvent.objects.create(order=order, status=S.CANCELLED, note="Payment failed; order cancelled")
        logger.info("payment_failed order=%s ref=%s", order.number, reference)
        return payment

    if result.amount != payment.amount or result.currency != payment.currency:
        payment.status = PaymentStatus.FAILED
        payment.raw = {**result.raw, "rejected": "amount_or_currency_mismatch"}
        payment.save()
        OrderEvent.objects.create(order=order, status=order.status, is_public=False,
                                  note=f"Payment {reference} rejected: paid {result.amount} {result.currency}, expected {payment.amount} {payment.currency}")
        logger.error("payment_mismatch order=%s ref=%s", order.number, reference)
        return payment

    payment.status, payment.paid_at = PaymentStatus.SUCCESSFUL, timezone.now()
    payment.save()
    order.payment_status, order.paid_at = PaymentStatus.SUCCESSFUL, payment.paid_at
    if order.status == S.PENDING_PAYMENT:
        order.status = S.PAID
        OrderEvent.objects.create(order=order, status=S.PAID, note="Payment confirmed")
        transaction.on_commit(lambda: _send_confirmation(order.pk))
    else:  # money arrived after the order was cancelled/expired: the owner must refund it
        OrderEvent.objects.create(order=order, status=order.status, is_public=False,
                                  note="Payment received after cancellation. Refund this payment on Paystack.")
        logger.error("payment_after_cancel order=%s ref=%s", order.number, reference)
    order.save()
    logger.info("payment_confirmed order=%s ref=%s amount=%s", order.number, reference, payment.amount)
    return payment


@transaction.atomic
def change_status(order_id: int, new_status: str, *, request, note: str = "", tracking_number: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order_id)
    if new_status not in TRANSITIONS[order.status]:
        raise ValidationError(f"An order that is '{order.get_status_display()}' cannot move to '{OrderStatus(new_status).label}'.")
    old = order.status
    if new_status == S.SHIPPED and not order.is_pickup and not (tracking_number or order.tracking_number):
        raise ValidationError({"tracking_number": ["Add a tracking number or rider contact before marking as shipped."]})
    if tracking_number:
        order.tracking_number = tracking_number
    public_note = note
    if new_status == S.CANCELLED:
        _release_stock(order, actor=request.user)
    if new_status == S.REFUNDED or (new_status == S.CANCELLED and order.payment_status == PaymentStatus.SUCCESSFUL):
        refund_note = _refund(order, request)  # last step that can fail: nothing is saved if it does
        note = (note + " " if note else "") + refund_note
    order.status = new_status
    order.save()
    OrderEvent.objects.create(order=order, status=new_status, note=note[:255], actor=request.user)
    audit.record("order.status_changed", request=request, obj=order, changes={"from": old, "to": new_status})
    if new_status in STATUS_EMAILS:
        transaction.on_commit(lambda: _send_status_email(order.pk, new_status, public_note))
    return order


def expire_unpaid(older_than_minutes: int = 60) -> int:
    """Cron job: settle or cancel orders left unpaid, giving their stock back."""
    cutoff = timezone.now() - timezone.timedelta(minutes=older_than_minutes)
    count = 0
    for order in Order.objects.filter(status=S.PENDING_PAYMENT, created_at__lt=cutoff):
        with transaction.atomic():
            for payment in order.payments.filter(status=PaymentStatus.PENDING):
                try:
                    confirm_payment(payment.reference)  # last check: maybe they did pay
                except ProviderError:
                    break
            else:
                fresh = Order.objects.select_for_update().get(pk=order.pk)
                if fresh.status == S.PENDING_PAYMENT:
                    fresh.status = S.CANCELLED
                    fresh.save()
                    # Payments stay 'pending' so a late success is still recorded and flagged for refund.
                    _release_stock(fresh)
                    OrderEvent.objects.create(order=fresh, status=S.CANCELLED, note="Not paid in time; order cancelled")
                    count += 1
    return count
