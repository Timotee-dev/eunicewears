"""Browser test of the whole purchase: sign in -> product -> cart -> checkout -> pay -> confirmation.

Not part of the normal suite because it needs a real browser:

    pip install playwright && playwright install chromium
    python manage.py test e2e

It uses the DEBUG-only sandbox gateway, so it never touches Paystack. Run it with DEBUG=True in .env.
"""
import os

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from apps.accounts.models import Address, User
from apps.catalog.models import Category, InventoryTransaction, Product, ProductVariant
from apps.catalog.services import adjust_stock
from apps.orders.models import Order, ShippingMethod

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # Playwright's sync API runs an event loop
PASSWORD = "tee-Drop!2026"


@override_settings(DEBUG=True, PAYMENT_PROVIDER="sandbox", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BuyingJourneyTest(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        tees = Category.objects.create(name="Tees")
        self.product = Product.objects.create(name="Oversized Tee", category=tees, price=1_200_000, is_published=True)
        self.variant = ProductVariant.objects.create(product=self.product, fit="oversized", size="M", color="Black", sku="E2E-1")
        ProductVariant.objects.create(product=self.product, fit="oversized", size="L", color="Black", sku="E2E-2")
        adjust_stock(self.variant.pk, 2, InventoryTransaction.Reason.RESTOCK)
        ShippingMethod.objects.create(name="Lagos delivery", zone="lagos", fee=250_000)
        self.user = User.objects.create_user("ada@example.com", PASSWORD, first_name="Ada", last_name="Obi", email_verified_at="2026-01-01T00:00:00Z")
        Address.objects.create(user=self.user, first_name="Ada", last_name="Obi", phone="0801", state="Lagos", city="Ikeja", line1="2 Close")

    def test_customer_can_buy_a_tee(self) -> None:
        page = self.browser.new_page()
        with self.settings(SITE_URL=self.live_server_url):
            page.goto(f"{self.live_server_url}/account/login/?next=/product/{self.product.slug}/")
            page.fill("#email", "ada@example.com")
            page.fill("#password", PASSWORD)
            page.click('[data-form="login"] button[type="submit"]')
            page.wait_for_url(f"**/product/{self.product.slug}/")

            page.click(".option:text-is('M')")
            page.wait_for_selector("[data-add]:not([disabled])")
            page.click("[data-add]")
            page.wait_for_selector("[data-cart-drawer][open]")

            page.goto(f"{self.live_server_url}/checkout/")
            page.wait_for_selector("[data-pay]:not([disabled])")
            self.assertIn("14,500", page.inner_text("[data-total]"))  # 12,000 + 2,500 delivery, computed by the server
            page.click("[data-pay]")

            page.wait_for_url("**/payments/sandbox/**")
            page.click('[data-outcome="success"]')
            page.wait_for_selector("text=Your order is confirmed")

        order = Order.objects.get()
        self.assertEqual((order.status, order.payment_status, order.total), ("paid", "successful", 1_450_000))
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        page.close()
