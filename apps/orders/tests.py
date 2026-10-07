import hashlib
import hmac
import json
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Address, Role, User
from apps.catalog.models import Category, InventoryTransaction, Product, ProductVariant
from apps.catalog.services import adjust_stock
from apps.orders import services
from apps.orders.models import Order, OrderStatus, Payment, PaymentStatus, ShippingMethod
from apps.orders.payments.base import InitResult, VerifyResult

PW = "tee-Drop!2026"
SECRET = "sk_test_unit"


def make_user(email: str, role: str = Role.CUSTOMER) -> User:
    return User.objects.create_user(email, PW, first_name="Ada", last_name="Obi", role=role, email_verified_at="2026-01-01T00:00:00Z")


class StoreTestCase(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.category = Category.objects.create(name="Tees")
        self.product = Product.objects.create(name="Oversized Tee", category=self.category, price=1_200_000, is_published=True)
        self.variant = ProductVariant.objects.create(product=self.product, fit="oversized", size="M", color="Black", sku="EW-1")
        adjust_stock(self.variant.pk, 3, InventoryTransaction.Reason.RESTOCK)
        ShippingMethod.objects.create(name="Lagos delivery", zone="lagos", fee=250_000, free_over=5_000_000)
        ShippingMethod.objects.create(name="Pickup", zone="pickup", fee=0)
        self.user = make_user("ada@example.com")
        self.address = Address.objects.create(user=self.user, first_name="Ada", last_name="Obi", phone="0801", state="Lagos", city="Ikeja", line1="2 Close")

    def add(self, quantity: int = 1, client=None):
        return (client or self.client).post("/api/cart/items/", {"variant_id": self.variant.pk, "quantity": quantity}, format="json")

    def checkout(self, **extra):
        return self.client.post("/api/checkout/", {"address_id": self.address.pk, **extra}, format="json")

    def stock(self) -> int:
        return ProductVariant.objects.get(pk=self.variant.pk).stock


class CatalogAndCartTests(StoreTestCase):
    def test_catalog_shows_only_published_and_filters(self) -> None:
        Product.objects.create(name="Hidden Tee", category=self.category, price=900_000, is_published=False)
        listing = self.client.get("/api/products/").json()
        self.assertEqual([p["name"] for p in listing["results"]], ["Oversized Tee"])
        self.assertEqual(self.client.get("/api/products/?color=red").json()["count"], 0)
        self.assertEqual(self.client.get("/api/products/?q=black&fit=oversized&in_stock=1").json()["count"], 1)
        detail = self.client.get(f"/api/products/{self.product.slug}/").json()
        self.assertEqual(detail["variants"][0]["availability"], "low")
        self.assertNotIn("stock", detail["variants"][0])
        self.assertEqual(self.client.get("/api/products/hidden-tee/").status_code, 404)

    def test_guest_cart_limits_and_merges_on_login(self) -> None:
        self.assertEqual(self.add(2).status_code, 201)
        self.assertEqual(self.add(2).status_code, 400)  # 4 > 3 in stock
        self.assertEqual(self.client.get("/api/cart/").json()["subtotal"], 2_400_000)
        self.client.post("/api/auth/login/", {"email": "ada@example.com", "password": PW}, format="json")
        cart = self.client.get("/api/cart/").json()
        self.assertEqual(cart["count"], 2)
        item_id = cart["items"][0]["id"]
        self.assertEqual(self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 9}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/cart/items/{item_id}/").json()["count"], 0)


@override_settings(DEBUG=True, PAYMENT_PROVIDER="sandbox", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CheckoutTests(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.user)

    def pay(self, outcome: str) -> dict:
        self.add(2)
        reference = self.checkout().json()["reference"]
        self.client.post(f"/api/payments/sandbox/{reference}/", {"outcome": outcome}, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post("/api/payments/verify/", {"reference": reference}, format="json").json()
        return {**result, "reference": reference}

    def test_checkout_requires_login_and_ignores_client_prices(self) -> None:
        self.client.force_authenticate(None)
        self.assertEqual(self.checkout().status_code, 403)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.checkout().status_code, 400)  # empty cart
        self.add(2)
        response = self.checkout(total=1, subtotal=1, shipping_fee=0)
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertRegex(order.number, r"^EW-\d{4}-\d{6}$")
        self.assertEqual((order.subtotal, order.shipping_fee, order.total), (2_400_000, 250_000, 2_650_000))
        self.assertEqual(order.status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(self.stock(), 1)  # reserved
        self.assertEqual(self.client.get("/api/cart/").json()["count"], 0)

    def test_cannot_oversell_last_units(self) -> None:
        self.add(2)
        other = make_user("bola@example.com")
        adjust_stock(self.variant.pk, -2, InventoryTransaction.Reason.SALE)  # another buyer got there first
        response = self.checkout()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "insufficient_stock")
        self.assertEqual(Order.objects.count(), 0)  # rolled back completely
        self.assertEqual(self.stock(), 1)
        self.assertFalse(other.orders.exists())

    def test_successful_payment_is_confirmed_once(self) -> None:
        result = self.pay("success")
        self.assertEqual(result["order_status"], "paid")
        self.assertEqual(len(mail.outbox), 1)
        again = self.client.post("/api/payments/verify/", {"reference": result["reference"]}, format="json").json()
        self.assertEqual(again["order_status"], "paid")
        order = Order.objects.get()
        self.assertEqual(order.events.filter(status="paid").count(), 1)
        self.assertEqual(self.stock(), 1)
        detail = self.client.get(f"/api/orders/{order.number}/").json()
        self.assertEqual([e["status"] for e in detail["events"]], ["pending_payment", "paid"])

    def test_browser_cannot_claim_payment(self) -> None:
        self.add(1)
        reference = self.checkout().json()["reference"]
        result = self.client.post("/api/payments/verify/", {"reference": reference, "status": "success"}, format="json").json()
        self.assertEqual(result["payment_status"], "pending")
        self.assertEqual(Order.objects.get().status, OrderStatus.PENDING_PAYMENT)

    def test_failed_payment_cancels_and_returns_stock(self) -> None:
        result = self.pay("failed")
        self.assertEqual(result["order_status"], "cancelled")
        self.assertEqual(self.stock(), 3)

    def test_other_customer_cannot_verify_or_view(self) -> None:
        result = self.pay("success")
        self.client.force_authenticate(make_user("bola@example.com"))
        self.assertEqual(self.client.post("/api/payments/verify/", {"reference": result["reference"]}, format="json").status_code, 404)
        self.assertEqual(self.client.get(f"/api/orders/{result['order_number']}/").status_code, 404)

    def test_unpaid_orders_expire(self) -> None:
        self.add(2)
        self.checkout()
        self.assertEqual(services.expire_unpaid(older_than_minutes=-1), 1)
        self.assertEqual(Order.objects.get().status, OrderStatus.CANCELLED)
        self.assertEqual(self.stock(), 3)


@override_settings(PAYMENT_PROVIDER="paystack", PAYSTACK_SECRET_KEY=SECRET)
class PaystackTests(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.user)
        self.add(1)
        with patch("apps.orders.payments.paystack.PaystackProvider.initialize", return_value=InitResult("https://checkout.paystack.com/x")):
            self.reference = self.checkout(pickup=True).json()["reference"]
        self.payment = Payment.objects.get(reference=self.reference)

    def hook(self, body: dict, signature: str | None = None):
        raw = json.dumps(body).encode()
        signature = signature or hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()
        return self.client.generic("POST", "/api/payments/webhook/", raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)

    def verify_returns(self, **kwargs):
        return patch("apps.orders.payments.paystack.PaystackProvider.verify", return_value=VerifyResult(**kwargs))

    def test_webhook_rejects_bad_signature(self) -> None:
        body = {"event": "charge.success", "data": {"reference": self.reference}}
        self.assertEqual(self.hook(body, signature="forged").status_code, 400)
        self.assertEqual(Order.objects.get().status, OrderStatus.PENDING_PAYMENT)

    def test_webhook_confirms_idempotently(self) -> None:
        self.assertEqual(self.payment.amount, 1_200_000)  # pickup: no delivery fee
        body = {"event": "charge.success", "data": {"reference": self.reference, "amount": 1}}
        with self.verify_returns(status="success", amount=1_200_000, currency="NGN") as verify:
            self.assertEqual(self.hook(body).status_code, 200)
            self.assertEqual(self.hook(body).status_code, 200)
            self.assertEqual(verify.call_count, 1)  # second delivery short-circuits
        order = Order.objects.get()
        self.assertEqual((order.status, order.payment_status), (OrderStatus.PAID, PaymentStatus.SUCCESSFUL))

    def test_underpayment_is_rejected(self) -> None:
        with self.verify_returns(status="success", amount=100, currency="NGN"):
            self.hook({"event": "charge.success", "data": {"reference": self.reference}})
        self.assertEqual(Order.objects.get().status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(Payment.objects.get().status, PaymentStatus.FAILED)

    def test_payment_after_expiry_is_flagged_for_refund(self) -> None:
        with self.verify_returns(status="pending"):
            services.expire_unpaid(older_than_minutes=-1)
        with self.verify_returns(status="success", amount=1_200_000, currency="NGN"):
            self.hook({"event": "charge.success", "data": {"reference": self.reference}})
        order = Order.objects.get()
        self.assertEqual((order.status, order.payment_status), (OrderStatus.CANCELLED, PaymentStatus.SUCCESSFUL))
        self.assertTrue(order.events.filter(is_public=False, note__icontains="refund").exists())


class DashboardTests(StoreTestCase):
    def test_roles_are_enforced(self) -> None:
        self.client.force_authenticate(self.user)
        for path in ["/api/admin/stats/", "/api/admin/orders/", "/api/admin/products/"]:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(self.client.get("/dashboard/").status_code in (302, 404), True)
        self.client.force_authenticate(make_user("staff@example.com", Role.STAFF))
        self.assertEqual(self.client.get("/api/admin/stats/").status_code, 200)
        body = {"name": "New Tee", "category": self.category.pk, "price": 900_000}
        self.assertEqual(self.client.post("/api/admin/products/", body, format="json").status_code, 403)

    def test_admin_manages_products_stock_and_orders(self) -> None:
        admin = make_user("admin@example.com", Role.ADMIN)
        self.client.force_authenticate(admin)
        bad = self.client.post("/api/admin/products/", {"name": "X", "category": self.category.pk, "price": 100, "discount_price": 500}, format="json")
        self.assertEqual(bad.status_code, 400)
        product = self.client.post("/api/admin/products/", {"name": "Regular Tee", "category": self.category.pk, "price": 1_000_000, "is_published": True}, format="json").json()
        variant = self.client.post("/api/admin/variants/", {"product": product["id"], "fit": "regular", "size": "L", "color": "White", "sku": "EW-2", "initial_stock": 5}, format="json").json()
        self.assertEqual(variant["stock"], 5)
        self.client.patch(f"/api/admin/variants/{variant['id']}/", {"stock": 999}, format="json")
        self.assertEqual(ProductVariant.objects.get(pk=variant["id"]).stock, 5)  # not writable directly
        self.assertEqual(self.client.post(f"/api/admin/variants/{variant['id']}/stock/", {"delta": -9}, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"/api/admin/variants/{variant['id']}/stock/", {"delta": -2, "note": "damaged"}, format="json").json()["stock"], 3)
        self.assertEqual(self.client.delete(f"/api/admin/products/{product['id']}/").status_code, 204)
        self.assertIsNotNone(Product.objects.get(pk=product["id"]).archived_at)  # archived, not deleted

        order = Order.objects.create(user=self.user, email=self.user.email, phone="0801", shipping_address={}, shipping_method="Lagos delivery",
                                     number="EW-2026-000099", status=OrderStatus.PAID, payment_status=PaymentStatus.SUCCESSFUL, total=1_000_000)
        url = f"/api/admin/orders/{order.number}/status/"
        self.assertEqual(self.client.post(url, {"status": "delivered"}, format="json").status_code, 400)  # cannot skip steps
        self.assertEqual(self.client.post(url, {"status": "processing"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(url, {"status": "shipped"}, format="json").status_code, 400)  # needs tracking
        shipped = self.client.post(url, {"status": "shipped", "tracking_number": "GIG-123"}, format="json").json()
        self.assertEqual((shipped["status"], shipped["tracking_number"]), ("shipped", "GIG-123"))
        self.assertEqual(self.client.get("/api/admin/stats/").json()["orders"]["total"], 1)
