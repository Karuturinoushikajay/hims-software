from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class RadiologyDepartment(models.TextChoices):
    AUDIOLOGY = "AUDIOLOGY", "Audiology"
    CT = "CT", "CT Scan"
    MRI = "MRI", "MRI"
    NEUROLOGY = "NEUROLOGY", "Neurology"
    RADIOLOGY = "RADIOLOGY", "Radiology (X-ray)"
    ULTRASONOGRAPHY = "ULTRASONOGRAPHY", "Ultrasonography"
    ULTRASOUND = "ULTRASOUND", "Ultrasound"


class StudyStatus(models.TextChoices):
    REGISTERED = "REGISTERED", "Registered"
    SCHEDULED = "SCHEDULED", "Scheduled"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Acquisition complete"
    REPORTED = "REPORTED", "Reported"
    AUTHORIZED = "AUTHORIZED", "Authorized"
    DISPATCHED = "DISPATCHED", "Dispatched"
    CANCELLED = "CANCELLED", "Cancelled"


class RadiologyTest(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="radiology_tests"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    instruction = models.TextField(blank=True, default="")
    department = models.CharField(max_length=32, choices=RadiologyDepartment.choices)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["department", "name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_rad_test_facility_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class RadiologyConsumable(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="radiology_consumables"
    )
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=32, blank=True, default="UNIT")
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "name"], name="uniq_rad_consumable_facility_name"
            )
        ]


class RadiologyTestConsumable(UUIDModel, TimeStampedModel):
    test = models.ForeignKey(RadiologyTest, on_delete=models.CASCADE, related_name="consumable_links")
    consumable = models.ForeignKey(
        RadiologyConsumable, on_delete=models.PROTECT, related_name="test_links"
    )
    quantity_per_study = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["test", "consumable"], name="uniq_rad_test_consumable")
        ]


class RadiologyReportTemplate(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="radiology_templates"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    department = models.CharField(
        max_length=32, choices=RadiologyDepartment.choices, blank=True, default=""
    )
    test = models.ForeignKey(
        RadiologyTest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="templates",
    )
    findings_template = models.TextField(blank=True, default="")
    impression_template = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "code"], name="uniq_rad_template_facility_code"
            )
        ]


class RadiologyOrder(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="radiology_orders"
    )
    rad_no = models.CharField(max_length=64)
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="radiology_orders"
    )
    visit = models.ForeignKey(
        "opd.Visit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radiology_orders",
    )
    clinical_order = models.ForeignKey(
        "clinical.ClinicalOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radiology_orders",
    )
    doctor = models.ForeignKey(
        "masters.Doctor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radiology_orders",
    )
    registered_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="radiology_orders_registered"
    )
    bill = models.ForeignKey(
        "billing.Bill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="radiology_orders",
    )
    remarks = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "rad_no"], name="uniq_rad_order_no"),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_rad_order_idempotency",
            ),
        ]


class RadiologyOrderItem(UUIDModel, TimeStampedModel):
    order = models.ForeignKey(RadiologyOrder, on_delete=models.CASCADE, related_name="items")
    test = models.ForeignKey(RadiologyTest, on_delete=models.PROTECT, related_name="order_items")
    status = models.CharField(
        max_length=16, choices=StudyStatus.choices, default=StudyStatus.REGISTERED
    )
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    scheduled_at = models.DateTimeField(null=True, blank=True)
    slot_label = models.CharField(max_length=64, blank=True, default="")
    performed_at = models.DateTimeField(null=True, blank=True)
    performed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radiology_studies_performed",
    )
    reported_at = models.DateTimeField(null=True, blank=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    authorized_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="radiology_items_authorized",
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default="")
    pacs_url = models.URLField(blank=True, default="")

    class Meta:
        ordering = ["created_at"]


class RadiologyReport(UUIDModel, TimeStampedModel):
    item = models.ForeignKey(RadiologyOrderItem, on_delete=models.CASCADE, related_name="reports")
    template = models.ForeignKey(
        RadiologyReportTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    findings = models.TextField(blank=True, default="")
    impression = models.TextField(blank=True, default="")
    reported_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="radiology_reports"
    )
    is_current = models.BooleanField(default=True)
    version = models.PositiveSmallIntegerField(default=1)
    amended_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="amendments",
    )
    amendment_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]


class RadiologyConsumableMovement(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        CONSUME = "CONSUME", "Consumed for study"
        BREAKAGE = "BREAKAGE", "Breakage / loss"
        ADJUST = "ADJUST", "Manual adjust"
        RECEIVE = "RECEIVE", "Stock receive"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="radiology_consumable_movements"
    )
    consumable = models.ForeignKey(
        RadiologyConsumable, on_delete=models.PROTECT, related_name="movements"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    delta = models.DecimalField(max_digits=14, decimal_places=3)
    quantity_after = models.DecimalField(max_digits=14, decimal_places=3)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="radiology_consumable_movements"
    )
    order_item = models.ForeignKey(
        RadiologyOrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consumable_movements",
    )
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
