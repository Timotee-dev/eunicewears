from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import PromoCode, PromoCodeUsage


def _reject(message: str):
    raise ValidationError({"promo_code": [message]})


def apply_promo(code: str, user, subtotal: int, *, lock: bool = False) -> tuple[PromoCode, int]:
    """Validate a code against live data and return (promo, discount in kobo). Server-side only."""
    promos = PromoCode.objects.select_for_update() if lock else PromoCode.objects
    promo = promos.filter(code=code.strip().upper()).first()
    today = timezone.localdate()
    if promo is None or not promo.is_active:
        _reject("That code is not valid.")
    if promo.starts_on and today < promo.starts_on:
        _reject("That code is not active yet.")
    if promo.ends_on and today > promo.ends_on:
        _reject("That code has expired.")
    if subtotal < promo.min_order:
        _reject(f"This code needs an order of at least \u20a6{promo.min_order // 100:,}.")
    used = PromoCodeUsage.objects.filter(promo=promo)
    if promo.usage_limit is not None and used.count() >= promo.usage_limit:
        _reject("That code has been fully used.")
    if promo.per_customer_limit is not None and used.filter(user=user).count() >= promo.per_customer_limit:
        _reject("You have already used that code.")
    return promo, promo.discount_for(subtotal)
