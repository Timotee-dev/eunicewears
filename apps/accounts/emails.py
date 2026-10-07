"""Transactional account emails. Queued through apps.core.mail."""
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.template.loader import render_to_string

from apps.core.mail import deliver

from .models import User
from .tokens import email_verification_token, encode_uid, password_reset_token

logger = logging.getLogger("eunice.email")


def _send(user: User, subject: str, template: str, text: str, context: dict) -> None:
    html = render_to_string(f"emails/{template}.html", {"user": user, "SITE_NAME": settings.SITE_NAME, **context})
    deliver(subject, text, html, user.email)
    logger.info("email_sent template=%s user_id=%s", template, user.pk)


def send_verification_email(user: User) -> None:
    query = urlencode({"uid": encode_uid(user), "token": email_verification_token.make_token(user)})
    link = f"{settings.SITE_URL}/account/verify-email/?{query}"
    _send(
        user,
        "Confirm your email for Eunice Wears",
        "verify_email",
        f"Hi {user.first_name},\n\nConfirm your email to finish setting up your account:\n{link}\n\n"
        "This link works for 24 hours. If you did not create an account, ignore this email.",
        {"link": link},
    )


def send_password_reset_email(user: User) -> None:
    query = urlencode({"uid": encode_uid(user), "token": password_reset_token.make_token(user)})
    link = f"{settings.SITE_URL}/account/reset-password/?{query}"
    _send(
        user,
        "Reset your Eunice Wears password",
        "password_reset",
        f"Hi {user.first_name},\n\nSet a new password here:\n{link}\n\n"
        "This link works for 24 hours. If you did not ask for this, ignore this email; your password stays the same.",
        {"link": link},
    )
