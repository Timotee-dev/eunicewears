from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.mail import deliver_template


@shared_task
def notify_back_in_stock(variant_id: int) -> int:
    from apps.catalog.models import ProductVariant

    from .models import BackInStockRequest

    variant = ProductVariant.objects.select_related("product").get(pk=variant_id)
    if variant.stock < 1 or not variant.is_active or not variant.product.is_published:
        return 0
    sent = 0
    for request in BackInStockRequest.objects.filter(variant=variant, notified_at__isnull=True):
        link = f"{settings.SITE_URL}/product/{variant.product.slug}/"
        deliver_template(
            request.email, f"{variant.product.name} is back in stock", "back_in_stock",
            f"{variant.product.name} ({variant.label}) is back in stock: {link}",
            {"product": variant.product, "variant": variant, "link": link},
        )
        request.notified_at = timezone.now()
        request.save(update_fields=["notified_at"])
        sent += 1
    return sent
