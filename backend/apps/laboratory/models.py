from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class LabDepartment(models.TextChoices):
    BIOCHEMISTRY = "BIOCHEMISTRY", "Biochemistry"
    CARDIOLOGY = "CARDIOLOGY", "Cardiology"
    CYTOLOGY = "CYTOLOGY", "Cytology"
    HEMATOLOGY = "HEMATOLOGY", "Hematology"
    HISTOPATHOLOGY = "HISTOPATHOLOGY", "Histopathology"
    IMMUNOASSAYS = "IMMUNOASSAYS", "Immunoassays"
    MICROBIOLOGY = "MICROBIOLOGY", "Microbiology"
    PATHOLOGY = "PATHOLOGY", "Pathology"
    SEROLOGY = "SEROLOGY", "Serology"


class FieldType(models.TextChoices):
    QUALITATIVE = "QUALITATIVE", "Qualitative"
    QUANTITATIVE = "QUANTITATIVE", "Quantitative"
    DESCRIPTIVE = "DESCRIPTIVE", "Descriptive"
    SUB_HEADER = "SUB_HEADER", "Sub Header"


class GenderScope(models.TextChoices):
    ANY = "ANY", "Any"
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"


class SampleStatus(models.TextChoices):
    REGISTERED = "REGISTERED", "Registered"
    COLLECTED = "COLLECTED", "Sample collected"
    RECEIVED = "RECEIVED", "Received"
    RESULTED = "RESULTED", "Resulted"
    VERIFIED = "VERIFIED", "Verified"
    AUTHORIZED = "AUTHORIZED", "Authorized"
    DISPATCHED = "DISPATCHED", "Dispatched"
    CANCELLED = "CANCELLED", "Cancelled"


class ResultFlag(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    LOW = "LOW", "Low"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"
    ABNORMAL = "ABNORMAL", "Abnormal"
    DELTA = "DELTA", "Delta check"


class LabTest(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="lab_tests"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=32, choices=LabDepartment.choices)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_outsourced = models.BooleanField(default=False)
    outsource_lab = models.CharField(max_length=255, blank=True, default="")
    turnaround_hours = models.PositiveSmallIntegerField(default=24)
    delta_absolute = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, help_text="Delta check absolute threshold"
    )
    delta_percent = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, help_text="Delta check percent threshold"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["department", "name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_lab_test_facility_code")
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class LabTestField(UUIDModel, TimeStampedModel):
    test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=128)
    field_type = models.CharField(max_length=16, choices=FieldType.choices)
    unit = models.CharField(max_length=32, blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]


class LabReferenceRange(UUIDModel, TimeStampedModel):
    field = models.ForeignKey(LabTestField, on_delete=models.CASCADE, related_name="ranges")
    gender = models.CharField(max_length=8, choices=GenderScope.choices, default=GenderScope.ANY)
    age_min_days = models.PositiveIntegerField(default=0)
    age_max_days = models.PositiveIntegerField(default=36500)
    low = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    high = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    critical_low = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    critical_high = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    qualitative_normal = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["age_min_days", "gender"]


class LabPackage(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="lab_packages"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    tests = models.ManyToManyField(LabTest, related_name="packages", blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_lab_package_facility_code")
        ]


class LabReagent(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="lab_reagents"
    )
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=32, blank=True, default="ML")
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_lab_reagent_facility_name")
        ]


class LabTestReagent(UUIDModel, TimeStampedModel):
    test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name="reagent_links")
    reagent = models.ForeignKey(LabReagent, on_delete=models.PROTECT, related_name="test_links")
    quantity_per_test = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["test", "reagent"], name="uniq_lab_test_reagent")
        ]


class LabOrder(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="lab_orders"
    )
    lab_no = models.CharField(max_length=64)
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="lab_orders"
    )
    visit = models.ForeignKey(
        "opd.Visit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_orders",
    )
    clinical_order = models.ForeignKey(
        "clinical.ClinicalOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_orders",
    )
    doctor = models.ForeignKey(
        "masters.Doctor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_orders",
    )
    registered_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="lab_orders_registered"
    )
    bill = models.ForeignKey(
        "billing.Bill",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lab_orders",
    )
    remarks = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "lab_no"], name="uniq_lab_order_no"),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_lab_order_idempotency",
            ),
        ]


class LabOrderItem(UUIDModel, TimeStampedModel):
    order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name="items")
    test = models.ForeignKey(LabTest, on_delete=models.PROTECT, related_name="order_items")
    package = models.ForeignKey(
        LabPackage, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items"
    )
    status = models.CharField(
        max_length=16, choices=SampleStatus.choices, default=SampleStatus.REGISTERED
    )
    barcode = models.CharField(max_length=64, blank=True, default="")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_outsourced = models.BooleanField(default=False)
    outsource_lab = models.CharField(max_length=255, blank=True, default="")
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_samples_collected",
    )
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_samples_received",
    )
    resulted_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_items_verified",
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    authorized_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_items_authorized",
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True, default="")
    has_critical = models.BooleanField(default=False)
    has_delta = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "barcode"],
                condition=~models.Q(barcode=""),
                name="uniq_lab_item_barcode",
            )
        ]


class LabResult(UUIDModel, TimeStampedModel):
    item = models.ForeignKey(LabOrderItem, on_delete=models.CASCADE, related_name="results")
    field = models.ForeignKey(LabTestField, on_delete=models.PROTECT, related_name="results")
    value_text = models.TextField(blank=True, default="")
    value_numeric = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    flag = models.CharField(max_length=16, choices=ResultFlag.choices, default=ResultFlag.NORMAL)
    reference_text = models.CharField(max_length=128, blank=True, default="")
    entered_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="lab_results_entered"
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
        ordering = ["field__sort_order", "created_at"]


class LabReagentMovement(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        CONSUME = "CONSUME", "Consumed for test"
        BREAKAGE = "BREAKAGE", "Breakage / loss"
        ADJUST = "ADJUST", "Manual adjust"
        RECEIVE = "RECEIVE", "Stock receive"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="lab_reagent_movements"
    )
    reagent = models.ForeignKey(LabReagent, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    delta = models.DecimalField(max_digits=14, decimal_places=3)
    quantity_after = models.DecimalField(max_digits=14, decimal_places=3)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="lab_reagent_movements"
    )
    order_item = models.ForeignKey(
        LabOrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reagent_movements",
    )
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
