from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class TokenCounter(UUIDModel, TimeStampedModel):
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.CASCADE, related_name="token_counters")
    service_date = models.DateField()
    next_token = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "service_date"], name="uniq_token_doctor_date")
        ]


class Appointment(UUIDModel, TimeStampedModel):
    class Source(models.TextChoices):
        WALKIN = "WALKIN", "Walk-in"
        ONLINE = "ONLINE", "Online"

    class Status(models.TextChoices):
        BOOKED = "BOOKED", "Booked"
        CHECKED_IN = "CHECKED_IN", "Checked in"
        DONE = "DONE", "Done"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No show"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="appointments"
    )
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="appointments")
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.PROTECT, related_name="appointments")
    service_date = models.DateField()
    token = models.PositiveIntegerField()
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.WALKIN)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CHECKED_IN)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["doctor", "service_date", "token"], name="uniq_token")
        ]
        ordering = ["token"]


class Visit(UUIDModel, TimeStampedModel):
    class PatientType(models.TextChoices):
        DIRECT = "DIRECT", "Direct"
        ORGANIZATION = "ORGANIZATION", "Organization"
        TPA = "TPA", "TPA"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="visits"
    )
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="visits")
    appointment = models.ForeignKey(
        Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="visits"
    )
    visit_no = models.CharField(max_length=64)
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.PROTECT, related_name="visits")
    patient_type = models.CharField(max_length=16, choices=PatientType.choices, default=PatientType.DIRECT)
    party = models.ForeignKey(
        "masters.OrganizationParty", on_delete=models.PROTECT, null=True, blank=True, related_name="visits"
    )
    referral_doctor = models.ForeignKey(
        "masters.ReferralDoctor", on_delete=models.PROTECT, null=True, blank=True, related_name="visits"
    )
    pro = models.ForeignKey(
        "masters.PRO", on_delete=models.PROTECT, null=True, blank=True, related_name="visits"
    )
    attendant_relation = models.CharField(max_length=64, blank=True, default="")
    attendant_name = models.CharField(max_length=128, blank=True, default="")
    attendant_mobile = models.CharField(max_length=20, blank=True, default="")
    insurance_covered = models.BooleanField(default=False)
    remarks = models.TextField(blank=True, default="")
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    temperature_f = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    fee_waived_reason = models.CharField(max_length=64, blank=True, default="")
    bill = models.ForeignKey(
        "billing.Bill", on_delete=models.PROTECT, null=True, blank=True, related_name="visits"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "visit_no"], name="uniq_visit_no")
        ]


class ProcedureOrder(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="procedure_orders"
    )
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="procedure_orders")
    procedure = models.ForeignKey("masters.Procedure", on_delete=models.PROTECT, related_name="orders")
    doctor = models.ForeignKey(
        "masters.Doctor", on_delete=models.PROTECT, null=True, blank=True, related_name="procedure_orders"
    )
    bill = models.ForeignKey("billing.Bill", on_delete=models.PROTECT, related_name="procedure_orders")


class Reminder(UUIDModel, TimeStampedModel):
    """Queued reminder. No SMS or WhatsApp provider is configured in Phase 2."""

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="reminders")
    channel = models.CharField(max_length=16, default="SMS")
    status = models.CharField(max_length=32, default="NOT_CONFIGURED")
    detail = models.CharField(max_length=255, default="No SMS or WhatsApp provider is configured.")
