from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import Role
from apps.catalog.models import InventoryTransaction
from apps.catalog.services import adjust_stock
from apps.marketing.models import BackInStockRequest, NewsletterSubscriber, PromoCode, PromoCodeUsage, Review
from apps.orders import services
from apps.orders.models import Order, OrderItem, OrderStatus, Payment, PaymentStatus
from apps.orders.payments.base import ProviderError
from apps.orders.tests import StoreTestCase, make_user

SANDBOX = override_settings(DEBUG=True, PAYMENT_PROVIDER="sandbox", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


def delivered_order(user, variant, number="EW-2026-000050", status=OrderStatus.DELIVERED):
    order = Order.objects.create(user=user, email=user.email, phone="0801", shipping_address={"first_name": "Ada"}, shipping_method="Lagos delivery",
                                 number=number, status=status, payment_status=PaymentStatus.SUCCESSFUL, total=1_200_000,
                                 subtotal=1_200_000, paid_at=timezone.now())
    OrderItem.objects.create(order=order, variant=variant, product_name=variant.product.name, variant_label=variant.label,
                             sku=variant.sku, unit_price=1_200_000, quantity=1, line_total=1_200_000)
    return order


@SANDBOX
class CustomerFeatureTests(StoreTestCase):
    def test_wishlist_is_private_and_idempotent(self) -> None:
        self.assertEqual(self.client.get("/api/wishlist/").status_code, 403)
        self.client.force_authenticate(self.user)
        for _ in range(2):
            self.assertEqual(self.client.post("/api/wishlist/", {"product_id": self.product.pk}, format="json").status_code, 201)
        self.assertEqual([p["slug"] for p in self.client.get("/api/wishlist/").json()], [self.product.slug])
        self.client.force_authenticate(make_user("bola@example.com"))
        self.assertEqual(self.client.get("/api/wishlist/").json(), [])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(f"/api/wishlist/{self.product.pk}/").status_code, 204)
        self.assertEqual(self.client.get("/api/wishlist/").json(), [])

    def test_only_buyers_review_and_reviews_need_approval(self) -> None:
        url = f"/api/products/{self.product.slug}/reviews/"
        body = {"rating": 5, "title": "Holds its shape", "comment": "Washed it six times."}
        self.assertEqual(self.client.post(url, body, format="json").status_code, 403)  # signed out
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(url, body, format="json").status_code, 403)  # has not bought it
        delivered_order(self.user, self.variant)
        self.assertEqual(self.client.post(url, {**body, "rating": 9}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, body, format="json").status_code, 201)
        self.assertEqual(self.client.post(url, {**body, "rating": 4}, format="json").status_code, 201)  # edits, not duplicates
        self.assertEqual(Review.objects.count(), 1)
        self.assertEqual(self.client.get(url).json()["count"], 0)  # hidden until approved

        self.client.force_authenticate(make_user("staff@example.com", Role.STAFF))
        review = Review.objects.get()
        self.assertEqual(self.client.patch(f"/api/admin/reviews/{review.pk}/", {"status": "approved", "rating": 1}, format="json").status_code, 200)
        self.client.force_authenticate(None)
        public = self.client.get(url).json()
        self.assertEqual((public["count"], public["average"], public["results"][0]["author"]), (1, 4.0, "Ada O."))  # staff cannot rewrite the rating
        self.assertNotIn("email", public["results"][0])

    def test_promo_code_rules_are_enforced_by_the_server(self) -> None:
        PromoCode.objects.create(code="eunice10", percent_off=10, max_discount=100_000, per_customer_limit=1)
        PromoCode.objects.create(code="OLD", amount_off=50_000, ends_on=timezone.localdate() - timedelta(days=1))
        PromoCode.objects.create(code="BIG", amount_off=50_000, min_order=9_000_000)
        self.client.force_authenticate(self.user)
        self.add(1)
        quote = lambda code: self.client.post("/api/checkout/quote/", {"address_id": self.address.pk, "promo_code": code}, format="json")  # noqa: E731
        for bad in ["NOPE", "OLD", "BIG"]:
            response = quote(bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn("promo_code", response.json()["error"]["fields"])
        good = quote("eunice10").json()
        self.assertEqual((good["discount"], good["total"]), (100_000, 1_200_000 - 100_000 + 250_000))  # 10% capped at N1,000

        placed = self.checkout(promo_code="EUNICE10", discount=999_999_999, total=1).json()
        order = Order.objects.get(number=placed["order_number"])
        self.assertEqual((order.discount, order.total, order.promo_code), (100_000, 1_350_000, "EUNICE10"))
        self.assertEqual(Payment.objects.get().amount, 1_350_000)  # the gateway is asked for the discounted total
        self.add(1)
        self.assertEqual(quote("EUNICE10").status_code, 400)  # one use per customer

        # The order is never paid: expiring it gives the code back.
        Order.objects.update(created_at=timezone.now() - timedelta(hours=3))
        self.assertEqual(services.expire_unpaid(60), 1)
        self.assertEqual(PromoCodeUsage.objects.count(), 0)
        self.assertEqual(quote("EUNICE10").status_code, 200)

    def test_newsletter_signup_export_and_unsubscribe(self) -> None:
        for email in ["Ada@Example.com", "ada@example.com"]:
            self.assertEqual(self.client.post("/api/newsletter/", {"email": email}, format="json").status_code, 200)
        subscriber = NewsletterSubscriber.objects.get()
        self.assertEqual(self.client.post("/api/newsletter/", {"email": "nope"}, format="json").status_code, 400)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/admin/newsletter/export/").status_code, 403)
        self.client.force_authenticate(make_user("admin@example.com", Role.ADMIN))
        export = self.client.get("/api/admin/newsletter/export/")
        self.assertIn("ada@example.com", export.content.decode())
        self.assertContains(self.client.get(f"/newsletter/unsubscribe/{subscriber.token}/"), "You are unsubscribed")
        subscriber.refresh_from_db()
        self.assertFalse(subscriber.is_active)

    def test_back_in_stock_emails_once_when_stock_returns(self) -> None:
        body = {"variant_id": self.variant.pk, "email": "wait@example.com"}
        self.assertEqual(self.client.post("/api/back-in-stock/", body, format="json").status_code, 400)  # it is in stock
        adjust_stock(self.variant.pk, -3, InventoryTransaction.Reason.ADJUSTMENT)
        for _ in range(2):
            self.assertEqual(self.client.post("/api/back-in-stock/", body, format="json").status_code, 200)
        self.assertEqual(BackInStockRequest.objects.count(), 1)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            adjust_stock(self.variant.pk, 5, InventoryTransaction.Reason.RESTOCK)
        self.assertEqual([m.to for m in mail.outbox], [["wait@example.com"]])
        with self.captureOnCommitCallbacks(execute=True):
            adjust_stock(self.variant.pk, 1, InventoryTransaction.Reason.RESTOCK)
        self.assertEqual(len(mail.outbox), 1)  # not again

    def test_search_suggestions_and_seo_pages(self) -> None:
        self.assertEqual(self.client.get("/api/products/suggest/?q=o").json(), [])
        self.assertEqual([p["slug"] for p in self.client.get("/api/products/suggest/?q=overs").json()], [self.product.slug])
        self.assertEqual(self.client.get("/api/products/suggest/?q=black").json()[0]["price"], 1_200_000)
        page = self.client.get(f"/product/{self.product.slug}/")
        self.assertContains(page, "application/ld+json")
        self.assertContains(page, 'property="og:title"')
        self.assertContains(self.client.get("/sitemap.xml"), f"/product/{self.product.slug}/")
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /dashboard/")
        for slug in ["about", "faq", "shipping", "returns", "privacy", "terms"]:
            self.assertEqual(self.client.get(f"/{slug}/").status_code, 200, slug)
        self.assertEqual(self.client.get("/wishlist/").status_code, 302)


@SANDBOX
class OwnerFeatureTests(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.staff = make_user("staff@example.com", Role.STAFF)

    def test_new_admin_endpoints_enforce_roles(self) -> None:
        admin_only = ["/api/admin/customers/", "/api/admin/promo-codes/", "/api/admin/content/", "/api/admin/newsletter/"]
        staff_ok = ["/api/admin/analytics/", "/api/admin/reviews/", "/api/admin/shipping-methods/", "/api/admin/categories/"]
        self.client.force_authenticate(self.user)
        for path in admin_only + staff_ok:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.client.force_authenticate(self.staff)
        for path in admin_only:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        for path in staff_ok:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.post("/api/admin/shipping-methods/", {"name": "X", "zone": "lagos", "fee": 1}, format="json").status_code, 403)
        self.client.force_login(self.staff)
        for page in ["analytics", "customers", "reviews", "marketing", "content", "settings"]:
            self.assertEqual(self.client.get(f"/dashboard/{page}/").status_code, 200, page)

    def test_analytics_counts_only_confirmed_money(self) -> None:
        delivered_order(self.user, self.variant)
        Order.objects.create(user=self.user, email=self.user.email, phone="1", shipping_address={}, shipping_method="x",
                             number="EW-2026-000051", total=9_000_000)  # unpaid: must not count
        self.client.force_authenticate(self.staff)
        data = self.client.get("/api/admin/analytics/").json()
        self.assertEqual((data["totals"]["revenue"], data["totals"]["orders"], data["totals"]["units"]), (1_200_000, 1, 1))
        self.assertEqual(len(data["series"]), 30)
        self.assertEqual(data["series"][-1]["revenue"], 1_200_000)
        self.assertEqual(data["by_category"][0]["category"], "Tees")
        self.assertEqual(self.client.get("/api/admin/analytics/?from=2020-01-01&to=2020-01-31").json()["totals"]["revenue"], 0)
        self.assertEqual(self.client.get("/api/admin/analytics/?from=rubbish").status_code, 200)

    def test_customers_rates_categories_and_promos_are_managed_from_the_dashboard(self) -> None:
        delivered_order(self.user, self.variant)
        self.client.force_authenticate(self.admin)
        row = self.client.get("/api/admin/customers/?q=ada").json()["results"][0]
        self.assertEqual((row["orders"], row["spent"]), (1, 1_200_000))
        self.assertFalse(self.client.post(f"/api/admin/customers/{row['id']}/active/", {"is_active": False}, format="json").json()["is_active"])
        self.assertEqual(self.client.post(f"/api/admin/customers/{self.staff.pk}/active/", {"is_active": False}, format="json").status_code, 404)

        rate = self.client.get("/api/admin/shipping-methods/").json()[0]
        self.assertEqual(self.client.patch(f"/api/admin/shipping-methods/{rate['id']}/", {"fee": 300_000}, format="json").json()["fee"], 300_000)
        self.assertEqual(self.client.patch(f"/api/admin/shipping-methods/{rate['id']}/", {"fee": -5}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/admin/categories/", {"name": "Caps", "position": 2, "is_active": True}, format="json").json()["slug"], "caps")

        both = {"code": "x", "percent_off": 10, "amount_off": 5000, "min_order": 0}
        self.assertEqual(self.client.post("/api/admin/promo-codes/", both, format="json").status_code, 400)
        made = self.client.post("/api/admin/promo-codes/", {"code": "welcome", "percent_off": 15, "amount_off": None, "min_order": 0}, format="json").json()
        self.assertEqual((made["code"], made["times_used"]), ("WELCOME", 0))

    def test_owner_edits_content_and_customer_text_is_escaped(self) -> None:
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.put("/api/admin/content/nope/", {}, format="json").status_code, 404)
        self.assertEqual(self.client.put("/api/admin/content/home/", {"headline": ""}, format="json").status_code, 400)
        self.client.put("/api/admin/content/home/", {"headline": "Wear it daily", "announcement": "Free Lagos delivery <b>today</b>", "rogue": "x"}, format="json")
        self.client.put("/api/admin/content/page-returns/", {"title": "Returns", "body": "Send it back within 7 days.\n\n<script>alert(1)</script>"}, format="json")
        self.client.put("/api/admin/content/size-guide/", {"oversized": "M, 58, 74\nL, 61, 76", "columns": "Size, Chest, Length"}, format="json")
        home = self.client.get("/")
        self.assertContains(home, "Wear it daily")
        self.assertContains(home, "&lt;b&gt;today&lt;/b&gt;")
        returns = self.client.get("/returns/")
        self.assertContains(returns, "Send it back within 7 days.")
        self.assertNotContains(returns, "<script>alert(1)</script>")
        self.assertContains(self.client.get(f"/product/{self.product.slug}/"), "<td>58</td>")

    def test_status_emails_and_automatic_refund(self) -> None:
        order = delivered_order(self.user, self.variant, status=OrderStatus.PROCESSING)
        Payment.objects.create(order=order, provider="sandbox", reference="REF-1", amount=order.total, status=PaymentStatus.SUCCESSFUL)
        adjust_stock(self.variant.pk, -1, InventoryTransaction.Reason.SALE, order=order)
        url = f"/api/admin/orders/{order.number}/status/"
        self.client.force_authenticate(self.staff)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url, {"status": "shipped", "tracking_number": "GIG-9"}, format="json").status_code, 200)
        self.assertIn("on its way", mail.outbox[0].subject)
        self.assertIn("GIG-9", mail.outbox[0].alternatives[0][0])

        Order.objects.filter(pk=order.pk).update(status=OrderStatus.PROCESSING)
        self.assertEqual(self.client.post(url, {"status": "cancelled"}, format="json").status_code, 403)  # staff cannot refund
        self.client.force_authenticate(self.admin)
        with patch("apps.orders.payments.sandbox.SandboxProvider.refund", side_effect=ProviderError("declined")):
            self.assertEqual(self.client.post(url, {"status": "cancelled"}, format="json").status_code, 400)
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status, self.stock()), ("processing", "successful", 2))  # nothing changed

        with patch("apps.orders.payments.sandbox.SandboxProvider.refund") as refund, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url, {"status": "cancelled"}, format="json").status_code, 200)
        refund.assert_called_once_with("REF-1", 1_200_000)
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status, self.stock()), ("cancelled", "refunded", 3))
        self.assertEqual(Payment.objects.get().status, "refunded")
        self.assertIn("cancelled", mail.outbox[-1].subject)


@SANDBOX
class HomePicksTests(StoreTestCase):
    def test_owner_chooses_up_to_ten_products_per_category(self) -> None:
        from apps.catalog.models import Category, Product

        tees = self.product.category
        others = [Product.objects.create(name=f"Tee {i}", category=tees, price=1_000_000, is_published=True) for i in range(11)]
        draft = Product.objects.create(name="Draft tee", category=tees, price=1_000_000, is_published=False)
        caps = Category.objects.create(name="Caps")
        cap = Product.objects.create(name="Cap", category=caps, price=500_000, is_published=True)

        # Before any choice: the newest ten per category, and never an unpublished product.
        home = self.client.get("/api/home/").json()
        self.assertEqual([s["category"]["name"] for s in home], ["Caps", "Tees"])
        tee_names = [p["name"] for p in home[1]["products"]]
        self.assertEqual(len(tee_names), 10)
        self.assertNotIn("Draft tee", tee_names)

        url = f"/api/admin/home-picks/{tees.pk}/"
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.put(url, {"product_ids": [others[0].pk]}, format="json").status_code, 403)
        self.client.force_authenticate(make_user("staff@example.com", Role.STAFF))
        self.assertEqual(self.client.get("/api/admin/home-picks/").status_code, 200)
        self.assertEqual(self.client.put(url, {"product_ids": [others[0].pk]}, format="json").status_code, 403)

        self.client.force_authenticate(make_user("admin@example.com", Role.ADMIN))
        self.assertEqual(self.client.put(url, {"product_ids": [p.pk for p in others]}, format="json").status_code, 400)  # eleven
        self.assertEqual(self.client.put(url, {"product_ids": [draft.pk]}, format="json").status_code, 400)
        self.assertEqual(self.client.put(url, {"product_ids": [cap.pk]}, format="json").status_code, 400)  # wrong category
        chosen = [others[3].pk, others[1].pk, self.product.pk]
        self.assertEqual(self.client.put(url, {"product_ids": chosen}, format="json").status_code, 200)
        shelf = lambda: [p["id"] for p in next(s for s in self.client.get("/api/home/").json() if s["category"]["name"] == "Tees")["products"]]  # noqa: E731
        self.assertEqual(shelf(), chosen)  # exactly the owner's picks, in the owner's order

        # Replacing one is just choosing another in its place.
        swapped = [others[3].pk, others[7].pk, self.product.pk]
        self.client.put(url, {"product_ids": swapped}, format="json")
        self.assertEqual(shelf(), swapped)
        # A pick that is later unpublished drops off the page by itself.
        Product.objects.filter(pk=others[7].pk).update(is_published=False)
        self.assertEqual(shelf(), [others[3].pk, self.product.pk])
        self.assertEqual(self.client.get("/dashboard/home/").status_code, 302)
