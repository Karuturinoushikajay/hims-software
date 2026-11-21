from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class DocumentType(models.TextChoices):
    UHID = "UHID", "UHID / MR"
    BILL = "BILL", "Bill"
    RCPT = "RCPT", "Receipt"
    VISIT = "VISIT", "Visit"
    IP = "IP", "IP Admission"
    LAB = "LAB", "Lab"
    RAD = "RAD", "Radiology"
    ADV = "ADV", "Advance"
    REF = "REF", "Refund"
    CN = "CN", "Credit Note"
    PO = "PO", "Purchase Order"
    GRN = "GRN", "Goods Receipt"
    PHARM = "PHARM", "Pharmacy sale"


class NumberSequence(UUIDModel, TimeStampedModel):
    """
    Gap-free sequence. Exactly one owner:
    - organization for UHID
    - facility for every other document type
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="number_sequences",
    )
    facility = models.ForeignKey(
        "organizations.Facility",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="number_sequences",
    )
    document_type = models.CharField(max_length=16, choices=DocumentType.choices)
    financial_year = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="e.g. 2026-27. Empty for UHID (never resets).",
    )
    prefix = models.CharField(max_length=64)
    next_value = models.PositiveBigIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=6)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(organization__isnull=False, facility__isnull=True)
                    | models.Q(organization__isnull=True, facility__isnull=False)
                ),
                name="number_sequence_exactly_one_owner",
            ),
            models.UniqueConstraint(
                fields=["organization", "document_type"],
                condition=models.Q(organization__isnull=False),
                name="uniq_org_uhid_sequence",
            ),
            models.UniqueConstraint(
                fields=["facility", "document_type", "financial_year"],
                condition=models.Q(facility__isnull=False),
                name="uniq_facility_doc_fy_sequence",
            ),
        ]

    def clean(self):
        if self.document_type == DocumentType.UHID:
            if not self.organization_id or self.facility_id:
                raise ValidationError("UHID sequences must be owned by organization only.")
            if self.financial_year:
                raise ValidationError("UHID sequences must not have a financial year.")
        else:
            if not self.facility_id or self.organization_id:
                raise ValidationError("Document sequences must be owned by facility only.")
            if not self.financial_year:
                raise ValidationError("Facility document sequences require a financial year.")

    def __str__(self) -> str:
        owner = self.organization_id or self.facility_id
        return f"{owner}:{self.document_type}:{self.financial_year or 'lifetime'}"
