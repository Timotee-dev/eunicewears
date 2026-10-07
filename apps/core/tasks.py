from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(autoretry_for=(Exception,), retry_backoff=30, retry_backoff_max=600, max_retries=4)
def send_email(subject: str, text: str, html: str, to: str) -> None:
    send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [to], html_message=html)


@shared_task
def expire_unpaid_orders() -> int:
    from apps.orders.services import expire_unpaid

    return expire_unpaid(60)
