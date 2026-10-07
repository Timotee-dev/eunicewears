from typing import Any

from django.db import models
from django.http import HttpRequest

from .models import AuditLog


def client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def record(
    action: str,
    *,
    request: HttpRequest | None = None,
    actor: Any = None,
    obj: models.Model | None = None,
    changes: dict | None = None,
) -> AuditLog:
    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        object_repr=str(obj)[:255] if obj is not None else "",
        changes=changes or {},
        ip_address=client_ip(request),
    )
