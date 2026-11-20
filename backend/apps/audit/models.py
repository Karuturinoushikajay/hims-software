from __future__ import annotations

from django.db import models

from apps.common.models import UUIDModel


class AuditLog(UUIDModel):
    """Append-only audit trail. DB trigger blocks UPDATE/DELETE."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    facility = models.ForeignKey(
        "organizations.Facility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=128, db_index=True)
    entity_type = models.CharField(max_length=128, blank=True, default="")
    entity_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["facility", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at} {self.action}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            return super().save(*args, **kwargs)
        raise RuntimeError("AuditLog rows are immutable and cannot be updated.")

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog rows are immutable and cannot be deleted.")
