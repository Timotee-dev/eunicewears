import re

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Address, Role, User
from apps.core.permissions import has_role

PASSWORD = "tee-Drop!2026"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthFlowTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()  # reset throttles

    def register(self, email: str = "ada@example.com"):
        return self.client.post(
            "/api/auth/register/",
            {"email": email, "password": PASSWORD, "first_name": "Ada", "last_name": "Obi"},
            format="json",
        )

    def link_params(self) -> dict:
        match = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[-1].body)
        return {"uid": match.group(1), "token": match.group(2)}

    def login(self, password: str = PASSWORD):
        return self.client.post("/api/auth/login/", {"email": "ADA@example.com", "password": password}, format="json")

    def test_register_verify_login_me(self) -> None:
        self.assertEqual(self.register().status_code, 201)
        user = User.objects.get(email="ada@example.com")
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertTrue(hasattr(user, "profile"))

        blocked = self.login()
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["error"]["code"], "email_not_verified")

        params = self.link_params()
        self.assertEqual(self.client.post("/api/auth/verify-email/", params, format="json").status_code, 200)
        # single use
        self.assertEqual(self.client.post("/api/auth/verify-email/", params, format="json").status_code, 400)

        self.assertEqual(self.login().status_code, 200)
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.json()["email"], "ada@example.com")
        self.assertNotIn("password", me.json())

        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_register_rejects_duplicates_weak_passwords_and_role_injection(self) -> None:
        self.register()
        self.assertEqual(self.register().status_code, 400)
        weak = self.client.post(
            "/api/auth/register/",
            {"email": "b@example.com", "password": "12345678", "first_name": "B", "last_name": "C"},
            format="json",
        )
        self.assertIn("password", weak.json()["error"]["fields"])
        self.client.post(
            "/api/auth/register/",
            {"email": "c@example.com", "password": PASSWORD, "first_name": "C", "last_name": "D", "role": "super_admin", "is_staff": True},
            format="json",
        )
        self.assertEqual(User.objects.get(email="c@example.com").role, Role.CUSTOMER)

    def test_wrong_password_and_unknown_email_look_the_same(self) -> None:
        self.register()
        User.objects.update(email_verified_at="2026-01-01T00:00:00Z")
        wrong = self.login("nope-nope-nope")
        unknown = self.client.post("/api/auth/login/", {"email": "x@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_login_is_rate_limited(self) -> None:
        codes = [self.login("bad-password-x").status_code for _ in range(12)]
        self.assertIn(429, codes)

    def test_password_reset_flow(self) -> None:
        self.register()
        mail.outbox.clear()
        known = self.client.post("/api/auth/password/reset/", {"email": "ada@example.com"}, format="json")
        unknown = self.client.post("/api/auth/password/reset/", {"email": "ghost@example.com"}, format="json")
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 1)

        params = self.link_params()
        new = "another-Tee#77"
        ok = self.client.post("/api/auth/password/reset/confirm/", {**params, "new_password": new}, format="json")
        self.assertEqual(ok.status_code, 200)
        reused = self.client.post("/api/auth/password/reset/confirm/", {**params, "new_password": new}, format="json")
        self.assertEqual(reused.status_code, 400)
        self.assertEqual(self.login(new).status_code, 200)

    def test_addresses_are_private_and_have_one_default(self) -> None:
        ada = User.objects.create_user("ada@example.com", PASSWORD, first_name="Ada", last_name="Obi")
        bola = User.objects.create_user("bola@example.com", PASSWORD, first_name="Bola", last_name="Ade")
        theirs = Address.objects.create(
            user=bola, first_name="Bola", last_name="Ade", phone="0800", state="Ondo", city="Ondo", line1="1 Road"
        )
        self.client.force_authenticate(ada)
        body = {"first_name": "Ada", "last_name": "Obi", "phone": "0801", "state": "Lagos", "city": "Ikeja", "line1": "2 Close"}
        first = self.client.post("/api/account/addresses/", body, format="json")
        self.assertTrue(first.json()["is_default"])
        second = self.client.post("/api/account/addresses/", {**body, "line1": "3 Ave", "is_default": True}, format="json")
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Address.objects.filter(user=ada, is_default=True).count(), 1)
        self.assertEqual(self.client.get(f"/api/account/addresses/{theirs.pk}/").status_code, 404)
        self.assertEqual(len(self.client.get("/api/account/addresses/").json()), 2)

    def test_roles_and_health(self) -> None:
        staff = User.objects.create_user("s@example.com", PASSWORD, first_name="S", last_name="T", role=Role.STAFF)
        self.assertTrue(staff.is_staff)
        self.assertTrue(has_role(staff, "staff"))
        self.assertFalse(has_role(staff, "admin"))
        self.assertEqual(self.client.get("/api/health/").json()["status"], "ok")

    def test_pages_render_and_account_requires_sign_in(self) -> None:
        for path in ["/", "/account/login/", "/account/register/", "/account/forgot-password/", "/account/verify-email/", "/account/reset-password/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("Content-Security-Policy", response.headers)
        self.assertEqual(self.client.get("/account/").status_code, 302)
        self.assertEqual(self.client.get("/nope/").status_code, 404)
        user = User.objects.create_user("ada@example.com", PASSWORD, first_name="Ada", last_name="Obi")
        self.client.force_login(user)
        self.assertContains(self.client.get("/account/"), "Hello, Ada")
