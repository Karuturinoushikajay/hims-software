from __future__ import annotations

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class IdempotencyKey(UUIDModel, TimeStampedModel):
    """Guards double-submit of payments and other mutating financial actions."""

    facility = models.ForeignKey(
        "organizations.Facility",
        on_delete=models.PROTECT,
        related_name="idempotency_keys",
    )
    key = models.CharField(max_length=128)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=512)
    request_hash = models.CharField(max_length=64, blank=True, default="")
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idempotency_keys",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "key"],
                name="uniq_idempotency_facility_key",
            )
        ]
        indexes = [
            models.Index(fields=["facility", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.facility_id}:{self.key}"
