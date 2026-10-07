import hashlib
import hmac
import json

import requests
from django.conf import settings

from .base import InitResult, InvalidWebhook, PaymentProvider, ProviderError, VerifyResult

API = "https://api.paystack.co"


class PaystackProvider(PaymentProvider):
    name = "paystack"

    def __init__(self) -> None:
        self.secret = settings.PAYSTACK_SECRET_KEY
        if not self.secret:
            raise ProviderError("PAYSTACK_SECRET_KEY is not set.")

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = requests.request(
                method, API + path, headers={"Authorization": f"Bearer {self.secret}"}, timeout=15, **kwargs
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("Paystack could not be reached.") from exc
        if not payload.get("status"):
            raise ProviderError(payload.get("message", "Paystack rejected the request."))
        return payload["data"]

    def initialize(self, *, reference, amount, currency, email, callback_url, metadata) -> InitResult:
        data = self._call("POST", "/transaction/initialize", json={
            "reference": reference, "amount": amount, "currency": currency, "email": email,
            "callback_url": callback_url, "metadata": metadata,
        })
        return InitResult(authorization_url=data["authorization_url"])

    def verify(self, reference: str) -> VerifyResult:
        data = self._call("GET", f"/transaction/verify/{reference}")
        state = data.get("status")
        status = "success" if state == "success" else "failed" if state in ("failed", "reversed") else "pending"
        return VerifyResult(status=status, amount=int(data.get("amount") or 0), currency=data.get("currency", ""), raw=data)

    def refund(self, reference: str, amount: int) -> None:
        self._call("POST", "/refund", json={"transaction": reference, "amount": amount})

    def parse_webhook(self, body: bytes, headers) -> str | None:
        expected = hmac.new(self.secret.encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, headers.get("x-paystack-signature", "")):
            raise InvalidWebhook()
        try:
            event = json.loads(body)
        except ValueError as exc:
            raise InvalidWebhook() from exc
        if event.get("event") != "charge.success":
            return None
        # The event body is only a hint: the caller re-verifies this reference with Paystack.
        return (event.get("data") or {}).get("reference")
