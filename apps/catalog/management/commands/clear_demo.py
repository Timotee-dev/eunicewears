"""Remove the placeholder tees and promo code that earlier versions of seed_demo created."""
from django.core.management.base import BaseCommand
from django.db.models import ProtectedError
from django.utils import timezone

from apps.catalog.models import Product

DEMO_NAMES = ["Oversized Round Neck Tee", "Regular Round Neck Tee"]
DEMO_SKU_PREFIXES = ("EW-OVE-", "EW-REG-")


class Command(BaseCommand):
    help = "Delete the demo products (and the EUNICE10 demo promo code). Real products are never touched."

    def handle(self, *args, **options) -> None:
        from apps.marketing.models import PromoCode

        removed = hidden = 0
        for product in Product.objects.filter(name__in=DEMO_NAMES):
            skus = list(product.variants.values_list("sku", flat=True))
            if skus and not all(sku.startswith(DEMO_SKU_PREFIXES) for sku in skus):
                continue  # same name but edited into a real product: leave it alone
            try:
                product.delete()
                removed += 1
            except ProtectedError:
                # A test order points at it, and order history is never deleted. Take it out of the shop instead.
                product.is_published = False
                product.archived_at = timezone.now()
                product.save(update_fields=["is_published", "archived_at", "updated_at"])
                hidden += 1
        try:
            promos = PromoCode.objects.filter(code="EUNICE10").delete()[0]
        except ProtectedError:
            promos = PromoCode.objects.filter(code="EUNICE10").update(is_active=False)
        self.stdout.write(self.style.SUCCESS(
            f"Demo products deleted: {removed}. Archived because test orders used them: {hidden}. Demo promo codes removed: {promos}."))
