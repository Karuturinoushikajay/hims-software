from __future__ import annotations

from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel, UUIDModel


class Patient(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """Lifelong record owned by the organization, not a single facility."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="patients"
    )
    uhid = models.CharField(max_length=64)
    title = models.CharField(max_length=16, blank=True, default="")
    first_name = models.CharField(max_length=128)
    middle_name = models.CharField(max_length=128, blank=True, default="")
    last_name = models.CharField(max_length=128, blank=True, default="")
    gender = models.CharField(max_length=16)
    date_of_birth = models.DateField(null=True, blank=True)
    age_years = models.PositiveSmallIntegerField(default=0)
    age_months = models.PositiveSmallIntegerField(default=0)
    age_days = models.PositiveSmallIntegerField(default=0)
    blood_group = models.CharField(max_length=8, blank=True, default="")
    mobile = models.CharField(max_length=20, blank=True, default="", db_index=True)
    landline = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    marital_status = models.CharField(max_length=32, blank=True, default="")
    religion = models.CharField(max_length=64, blank=True, default="")
    address = models.TextField(blank=True, default="")
    country = models.CharField(max_length=64, blank=True, default="India")
    state = models.CharField(max_length=64, blank=True, default="")
    city = models.CharField(max_length=64, blank=True, default="")
    area = models.CharField(max_length=128, blank=True, default="")
    zip_code = models.CharField(max_length=16, blank=True, default="")
    education = models.CharField(max_length=64, blank=True, default="")
    occupation = models.CharField(max_length=64, blank=True, default="")
    birth_mark = models.CharField(max_length=255, blank=True, default="")
    medical_history = models.TextField(blank=True, default="")
    comments = models.TextField(blank=True, default="")
    photo = models.ImageField(upload_to="patient_photos/", blank=True, null=True)
    registered_at = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="registered_patients"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "uhid"], name="uniq_patient_uhid")
        ]
        ordering = ["first_name", "last_name"]

    @property
    def full_name(self) -> str:
        parts = [self.title, self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()


class PatientIdentifier(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        ABHA = "ABHA", "ABHA"
        AADHAAR = "AADHAAR", "Aadhaar"
        OTHER = "OTHER", "Other"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="identifiers")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    value = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["patient", "kind"], name="uniq_patient_identifier_kind")
        ]


class Registration(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="registrations"
    )
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="registrations")
    registered_on = models.DateField()
    expires_on = models.DateField()
    bill = models.ForeignKey(
        "billing.Bill", on_delete=models.PROTECT, null=True, blank=True, related_name="registrations"
    )
