from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class Department(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="departments"
    )
    name = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_dept_facility_name")
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Specialization(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="specializations"
    )
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="specializations")
    name = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "name"], name="uniq_spec_facility_name"
            )
        ]
        ordering = ["name"]


class Doctor(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="doctors"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="doctor_profiles"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="doctors")
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name="doctors"
    )
    consultation_fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    review_days = models.PositiveIntegerField(default=7)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_doctor_facility_code")
        ]
        ordering = ["name"]


class DoctorSchedule(UUIDModel, TimeStampedModel):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="schedules")
    weekday = models.PositiveSmallIntegerField()  # 0 Monday
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveSmallIntegerField(default=15)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "weekday"], name="uniq_doctor_weekday")
        ]


class ReferralDoctor(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="referral_doctors"
    )
    name = models.CharField(max_length=255)
    hospital = models.CharField(max_length=255, blank=True, default="")
    mobile = models.CharField(max_length=20, blank=True, default="")
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class PRO(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="pros"
    )
    name = models.CharField(max_length=255)
    mobile = models.CharField(max_length=20, blank=True, default="")
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)


class OrganizationParty(UUIDModel, TimeStampedModel):
    """Corporate or TPA/insurer the patient is billed under. Direct patients have none."""

    class Kind(models.TextChoices):
        CORPORATE = "CORPORATE", "Corporate"
        TPA = "TPA", "TPA/Insurer"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="parties"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class Procedure(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="procedures"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_procedure_facility_code")
        ]


class Area(UUIDModel, TimeStampedModel):
    country = models.CharField(max_length=64, default="India")
    state = models.CharField(max_length=64)
    city = models.CharField(max_length=64)
    name = models.CharField(max_length=128)

    class Meta:
        ordering = ["state", "city", "name"]
