"""Checkout talks to this interface only. A new gateway is a new subclass, not a checkout rewrite."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    """The gateway could not be reached or answered unexpectedly."""


class InvalidWebhook(Exception):
    """Signature missing or wrong. The request did not come from the gateway."""


@dataclass
class InitResult:
    authorization_url: str


@dataclass
class VerifyResult:
    status: str  # "success" | "failed" | "pending"
    amount: int = 0
    currency: str = ""
    raw: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def initialize(self, *, reference: str, amount: int, currency: str, email: str, callback_url: str, metadata: dict) -> InitResult: ...

    @abstractmethod
    def verify(self, reference: str) -> VerifyResult: ...

    @abstractmethod
    def parse_webhook(self, body: bytes, headers) -> str | None:
        """Validate the signature; return the payment reference to re-verify, or None to ignore the event."""

    def refund(self, reference: str, amount: int) -> None:
        """Send the money back for a settled payment. Raise ProviderError if the gateway refuses."""
        raise ProviderError(f"{self.name} cannot refund automatically.")
