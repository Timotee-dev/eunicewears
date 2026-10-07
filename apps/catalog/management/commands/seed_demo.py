"""Local setup helper: an owner login, the Tees category and starter delivery rates. Creates NO products.
Refuses to run unless DEBUG is on."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.catalog.models import Category
from apps.orders.models import ShippingMethod

SHIPPING = [
    ("Lagos delivery", "lagos", 250000, None, "1 to 2 working days"),
    ("Delivery outside Lagos", "other_states", 450000, None, "3 to 5 working days"),
    ("Pickup", "pickup", 0, None, "Ready within 24 hours"),
]


class Command(BaseCommand):
    help = "Create an owner login, the Tees category and starter delivery rates for development. No products."

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True. It must never touch production data.")
        Category.objects.get_or_create(slug="tees", defaults={"name": "Tees"})
        for name, zone, fee, free_over, estimate in SHIPPING:
            ShippingMethod.objects.get_or_create(zone=zone, defaults={"name": name, "fee": fee, "free_over": free_over, "estimate": estimate})
        if not User.objects.filter(email="owner@eunicewears.test").exists():
            User.objects.create_superuser("owner@eunicewears.test", "demo-owner-2026", first_name="Demo", last_name="Owner")
        assert User.objects.get(email="owner@eunicewears.test").role == Role.SUPER_ADMIN
        self.stdout.write(self.style.SUCCESS(
            "Ready. Owner login (DEVELOPMENT ONLY): owner@eunicewears.test / demo-owner-2026\n"
            "Add your real tees at /dashboard/products/ and set your real delivery fees at /dashboard/settings/."))
