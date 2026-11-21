from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class IcdCode(UUIDModel, TimeStampedModel):
    """ICD-10 code. Seed only clinically reviewed codes; do not invent ranges."""

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]


class Drug(UUIDModel, TimeStampedModel):
    """Drug / brand master used by prescriptions and pharmacy stock."""

    class Schedule(models.TextChoices):
        NONE = "NONE", "Unscheduled"
        H = "H", "Schedule H"
        H1 = "H1", "Schedule H1"
        NARCOTIC = "NARCOTIC", "Narcotic"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="drugs"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    brand_name = models.CharField(max_length=255, blank=True, default="")
    generic_name = models.CharField(max_length=255, blank=True, default="")
    schedule = models.CharField(max_length=16, choices=Schedule.choices, default=Schedule.NONE)
    unit = models.CharField(max_length=32, blank=True, default="TAB")
    reorder_level = models.PositiveIntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    hsn_sac = models.CharField(max_length=16, blank=True, default="")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_drug_facility_code")
        ]
        ordering = ["name"]


class DrugInteraction(UUIDModel, TimeStampedModel):
    class Severity(models.TextChoices):
        MINOR = "MINOR", "Minor"
        MODERATE = "MODERATE", "Moderate"
        MAJOR = "MAJOR", "Major"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="drug_interactions"
    )
    drug_a = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="interactions_as_a")
    drug_b = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="interactions_as_b")
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MODERATE)
    message = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "drug_a", "drug_b"], name="uniq_drug_interaction_pair"
            )
        ]


class Allergy(UUIDModel, TimeStampedModel):
    class Severity(models.TextChoices):
        MILD = "MILD", "Mild"
        MODERATE = "MODERATE", "Moderate"
        SEVERE = "SEVERE", "Severe"

    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="allergies")
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="recorded_allergies"
    )
    drug = models.ForeignKey(Drug, on_delete=models.SET_NULL, null=True, blank=True, related_name="allergies")
    substance = models.CharField(max_length=255)
    reaction = models.CharField(max_length=255, blank=True, default="")
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.MODERATE)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="recorded_allergies"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]


class ClinicalNote(UUIDModel, TimeStampedModel):
    visit = models.OneToOneField("opd.Visit", on_delete=models.CASCADE, related_name="clinical_note")
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="clinical_notes"
    )
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.PROTECT, related_name="clinical_notes")
    author = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="authored_clinical_notes"
    )
    complaints = models.TextField(blank=True, default="")
    history = models.TextField(blank=True, default="")
    examination = models.TextField(blank=True, default="")
    advice = models.TextField(blank=True, default="")


class Diagnosis(UUIDModel, TimeStampedModel):
    visit = models.ForeignKey("opd.Visit", on_delete=models.CASCADE, related_name="diagnoses")
    icd_code = models.ForeignKey(
        IcdCode, on_delete=models.PROTECT, null=True, blank=True, related_name="diagnoses"
    )
    name = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]


class Prescription(UUIDModel, TimeStampedModel):
    visit = models.ForeignKey("opd.Visit", on_delete=models.CASCADE, related_name="prescriptions")
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="prescriptions"
    )
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.PROTECT, related_name="prescriptions")
    author = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="authored_prescriptions"
    )
    template = models.ForeignKey(
        "masters.DocumentTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    notes = models.TextField(blank=True, default="")
    allergy_alerts = models.JSONField(default=list, blank=True)
    interaction_alerts = models.JSONField(default=list, blank=True)


class PrescriptionItem(UUIDModel, TimeStampedModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    drug = models.ForeignKey(
        Drug, on_delete=models.SET_NULL, null=True, blank=True, related_name="prescription_items"
    )
    name = models.CharField(max_length=255)
    dose = models.CharField(max_length=64, blank=True, default="")
    frequency = models.CharField(max_length=64, blank=True, default="")
    duration_days = models.PositiveSmallIntegerField(null=True, blank=True)
    instructions = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]


class ClinicalOrder(UUIDModel, TimeStampedModel):
    """Lab or radiology order. Fulfillment is Phases 6 and 7."""

    class Kind(models.TextChoices):
        LAB = "LAB", "Laboratory"
        RADIOLOGY = "RADIOLOGY", "Radiology"

    class Status(models.TextChoices):
        ORDERED = "ORDERED", "Ordered"
        CANCELLED = "CANCELLED", "Cancelled"

    visit = models.ForeignKey("opd.Visit", on_delete=models.CASCADE, related_name="clinical_orders")
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="clinical_orders"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="clinical_orders"
    )
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.PROTECT, related_name="clinical_orders")
    ordered_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="clinical_orders"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    code = models.CharField(max_length=32, blank=True, default="")
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ORDERED)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]


class FollowUp(UUIDModel, TimeStampedModel):
    visit = models.ForeignKey("opd.Visit", on_delete=models.CASCADE, related_name="follow_ups")
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="follow_ups"
    )
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="follow_ups")
    doctor = models.ForeignKey("masters.Doctor", on_delete=models.PROTECT, related_name="follow_ups")
    follow_up_on = models.DateField()
    reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="scheduled_follow_ups"
    )

    class Meta:
        ordering = ["follow_up_on"]


class ClinicalAttachment(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="clinical_attachments"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="clinical_attachments"
    )
    visit = models.ForeignKey(
        "opd.Visit",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
    )
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="clinical_attachments"
    )
    file = models.FileField(upload_to="clinical_attachments/")
    description = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
