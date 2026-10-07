import logging
from email.utils import parseaddr

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("eunice.email")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
PLACEHOLDER_SENDER = "eunicewears.example"


class EmailError(Exception):
    """An email could not be sent. The message is written for the store owner, not a developer."""


def email_setup() -> dict:
    """What the store will use to send email, and anything obviously wrong with it."""
    sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    console = settings.EMAIL_BACKEND.endswith("console.EmailBackend")
    provider = "brevo" if settings.BREVO_API_KEY else "smtp" if settings.EMAIL_HOST else "none" if console else "other"
    problem = ""
    if provider == "none" and not settings.DEBUG:
        problem = "No email service is connected, so nothing is being sent. Add BREVO_API_KEY in Render > Environment."
    elif provider == "brevo" and PLACEHOLDER_SENDER in sender:
        problem = ("DEFAULT_FROM_EMAIL is not set, so emails claim to come from a placeholder address and get rejected. "
                   "In Render > Environment set it to: Eunice Wears <an address you verified in Brevo>")
    return {"provider": provider, "sender": sender, "problem": problem}


def send_now(subject: str, text: str, html: str, to: str) -> None:
    """Send one email immediately. Raises EmailError with a plain-language reason if it does not go out."""
    setup = email_setup()
    if setup["problem"]:
        raise EmailError(setup["problem"])
    if settings.BREVO_API_KEY:
        name, address = parseaddr(settings.DEFAULT_FROM_EMAIL)
        try:
            response = requests.post(
                BREVO_ENDPOINT, timeout=15,
                headers={"api-key": settings.BREVO_API_KEY.strip(), "accept": "application/json"},
                json={"sender": {"name": name or settings.SITE_NAME, "email": address}, "to": [{"email": to}],
                      "subject": subject, "htmlContent": html, "textContent": text},
            )
        except requests.RequestException as exc:
            raise EmailError(f"Could not reach Brevo ({exc.__class__.__name__}). Try again in a minute.") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", "")
            except ValueError:
                detail = response.text[:200]
            hint = ""
            if response.status_code == 401:
                hint = (" The BREVO_API_KEY on Render is wrong, or Brevo is blocking this server's IP address: in Brevo open "
                        "Security > Authorized IPs and turn off blocking for API keys.")
            elif "sender" in detail.lower():
                hint = f" Brevo does not accept {address} as a sender: verify it under Senders, domains, IPs > Senders, then set DEFAULT_FROM_EMAIL to it."
            elif response.status_code == 403:
                hint = " Your Brevo account may not be activated for transactional email yet: open Transactional in Brevo and finish the activation."
            raise EmailError(f"Brevo refused the email ({response.status_code}: {detail or 'no reason given'}).{hint}")
        return
    try:
        send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [to], html_message=html)
    except Exception as exc:
        raise EmailError(f"The mail server refused the email ({exc}).") from exc


@shared_task
def send_email(subject: str, text: str, html: str, to: str) -> None:
    """Background send. A failure is logged with its reason and never breaks the customer's request."""
    try:
        send_now(subject, text, html, to)
        logger.info("email_sent subject=%r", subject)
    except EmailError as exc:
        logger.error("email_failed subject=%r reason=%s", subject, exc)


@shared_task
def expire_unpaid_orders() -> int:
    from apps.orders.services import expire_unpaid

    return expire_unpaid(60)
