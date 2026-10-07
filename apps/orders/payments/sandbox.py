"""Local test gateway, DEBUG only. It runs the exact same verify path as Paystack; nothing is auto-approved."""
from django.conf import settings

from .base import InitResult, PaymentProvider, VerifyResult


class SandboxProvider(PaymentProvider):
    name = "sandbox"

    def initialize(self, *, reference, amount, currency, email, callback_url, metadata) -> InitResult:
        return InitResult(authorization_url=f"{settings.SITE_URL}/payments/sandbox/{reference}/")

    def verify(self, reference: str) -> VerifyResult:
        from ..models import Payment

        payment = Payment.objects.get(reference=reference)
        outcome = payment.raw.get("sandbox_outcome")
        if outcome == "success":
            return VerifyResult("success", payment.amount, payment.currency, {"sandbox_outcome": "success"})
        if outcome == "failed":
            return VerifyResult("failed", raw={"sandbox_outcome": "failed"})
        return VerifyResult("pending")

    def refund(self, reference: str, amount: int) -> None:
        return None

    def parse_webhook(self, body: bytes, headers) -> str | None:
        return None
