from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SiteSetting(TimeStampedModel):
    """Owner-editable key/value content (hero text, announcement bar, policies...)."""

    key = models.SlugField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.key


class AuditLog(models.Model):
    """Append-only record of sensitive actions. Never updated or deleted by app code."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}#{self.object_id}"
