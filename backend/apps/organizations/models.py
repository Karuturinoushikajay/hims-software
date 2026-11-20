from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel, UUIDModel


class Organization(UUIDModel, TimeStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Facility(UUIDModel, TimeStampedModel, SoftDeleteModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="facilities",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32)
    legal_name = models.CharField(max_length=255, blank=True, default="")
    address_line1 = models.CharField(max_length=255, blank=True, default="")
    address_line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=128, blank=True, default="")
    state_code = models.CharField(max_length=2, blank=True, default="")  # GST state code
    pincode = models.CharField(max_length=16, blank=True, default="")
    country = models.CharField(max_length=64, default="India")
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    bed_capacity = models.PositiveIntegerField(default=0)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    currency = models.CharField(max_length=8, default="INR")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "facilities"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uniq_facility_org_code",
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class FacilitySettings(UUIDModel, TimeStampedModel):
    facility = models.OneToOneField(
        Facility,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    gstin = models.CharField(max_length=15, blank=True, default="")
    gstin_confirmed = models.BooleanField(default=False)
    financial_year_start_month = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    financial_year_start_day = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(28)],
    )
    session_timeout_minutes = models.PositiveIntegerField(default=30)
    refund_auth_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tds_commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percent. Must be confirmed by accountant before commission math runs.",
    )
    tds_rate_confirmed = models.BooleanField(default=False)
    require_2fa_roles = models.JSONField(
        default=list,
        help_text='Role codes that require TOTP, e.g. ["SUPER_ADMIN", "DOCTOR"].',
    )
    logo = models.ImageField(upload_to="facility_logos/", blank=True, null=True)
    letterhead_text = models.TextField(blank=True, default="")
    registration_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    registration_validity_days = models.PositiveIntegerField(default=365)

    def __str__(self) -> str:
        return f"Settings for {self.facility.code}"
