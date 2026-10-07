"""One door for outgoing email. Sending happens on a worker; a mail outage never breaks a request."""
import logging

from django.conf import settings
from django.template.loader import render_to_string

from .tasks import send_email

logger = logging.getLogger("eunice.email")


def deliver(subject: str, text: str, html: str, to: str) -> None:
    try:
        send_email.delay(subject, text, html, to)
    except Exception:  # broker down: log it, keep serving the customer
        logger.exception("email_queue_failed subject=%s", subject)


def deliver_template(to: str, subject: str, template: str, text: str, context: dict) -> None:
    html = render_to_string(f"emails/{template}.html", {"SITE_NAME": settings.SITE_NAME, "SITE_URL": settings.SITE_URL, **context})
    deliver(subject, text, html, to)
