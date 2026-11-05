"""Emails the owner the moment an order is paid, so a sale never sits unnoticed in the dashboard."""
import logging

from django.conf import settings

from apps.accounts.models import Role, User
from apps.core.mail import deliver_template
from apps.core.models import SiteSetting

from .models import Order

logger = logging.getLogger("eunice.orders")
KEY = "order-alerts"
MAX_RECIPIENTS = 5


def chosen_emails() -> list[str]:
    stored = SiteSetting.objects.filter(key=KEY).values_list("value", flat=True).first() or {}
    return [e for e in stored.get("emails", []) if e]


def recipients() -> list[str]:
    """The addresses set in Settings, or every admin account when none are set."""
    chosen = chosen_emails()
    if chosen:
        return chosen
    admins = User.objects.filter(role__in=[Role.ADMIN, Role.SUPER_ADMIN], is_active=True).order_by("pk")
    return list(dict.fromkeys(admins.values_list("email", flat=True)))[:MAX_RECIPIENTS]


def send_new_order_alert(order_id: int) -> None:
    try:
        order = Order.objects.prefetch_related("items").get(pk=order_id)
        count = sum(item.quantity for item in order.items.all())
        address = order.shipping_address or {}
        name = f"{address.get('first_name', '')} {address.get('last_name', '')}".strip() or order.email
        subject = f"New order {order.number}: {count} item{'s' if count != 1 else ''} from {name}"
        text = (f"{name} just paid for order {order.number}. "
                f"Open it in your dashboard: {settings.SITE_URL}/dashboard/orders/{order.number}/")
        for to in recipients():
            deliver_template(to, subject, "new_order", text, {"order": order, "name": name, "address": address, "count": count})
    except Exception:  # an alert must never get in the way of confirming the payment
        logger.exception("new_order_alert_failed order_id=%s", order_id)
