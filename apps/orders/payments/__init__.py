from django.conf import settings

from .base import InvalidWebhook, PaymentProvider, ProviderError, VerifyResult  # noqa: F401


def get_provider(name: str | None = None) -> PaymentProvider:
    name = name or settings.PAYMENT_PROVIDER
    if name == "paystack":
        from .paystack import PaystackProvider

        return PaystackProvider()
    if name == "sandbox" and settings.DEBUG:
        from .sandbox import SandboxProvider

        return SandboxProvider()
    raise ProviderError(f"Payment provider '{name}' is not available.")
