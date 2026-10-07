from email.utils import parseaddr

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


@shared_task(autoretry_for=(Exception,), retry_backoff=30, retry_backoff_max=600, max_retries=4)
def send_email(subject: str, text: str, html: str, to: str) -> None:
    """With BREVO_API_KEY set, send over HTTPS (works on hosts that block SMTP ports, such as Render's free plan).
    Otherwise use Django's configured email backend (SMTP, or the console in development)."""
    if settings.BREVO_API_KEY:
        name, address = parseaddr(settings.DEFAULT_FROM_EMAIL)
        response = requests.post(
            BREVO_ENDPOINT, timeout=15,
            headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
            json={"sender": {"name": name or settings.SITE_NAME, "email": address}, "to": [{"email": to}],
                  "subject": subject, "htmlContent": html, "textContent": text},
        )
        response.raise_for_status()
        return
    send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [to], html_message=html)


@shared_task
def expire_unpaid_orders() -> int:
    from apps.orders.services import expire_unpaid

    return expire_unpaid(60)
