from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Single-use: the hash includes email_verified_at, so verifying invalidates the link."""

    key_salt = "apps.accounts.tokens.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user: User, timestamp: int) -> str:
        return f"{user.pk}{user.email}{user.email_verified_at}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
password_reset_token = default_token_generator


def encode_uid(user: User) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def user_from_uid(uid: str) -> User | None:
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
