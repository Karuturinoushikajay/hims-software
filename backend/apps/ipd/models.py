from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class FoodPreference(models.TextChoices):
    VEG = "VEG", "Vegetarian"
    NON_VEG = "NON_VEG", "Non-vegetarian"


class AdmissionStatus(models.TextChoices):
    ADMITTED = "ADMITTED", "Admitted"
    DISCHARGED = "DISCHARGED", "Discharged"
    CANCELLED = "CANCELLED", "Cancelled"


class CertificateKind(models.TextChoices):
    FITNESS = "FITNESS", "Fitness"
    REST = "REST", "Rest Advice"
    LEAVE = "LEAVE", "Medical Leave"
    EMERGENCY = "EMERGENCY", "Emergency"
    ESSENTIALITY = "ESSENTIALITY", "Essentiality"
    BIRTH = "BIRTH", "Birth"
    DEATH = "DEATH", "Death"
    GENUINE = "GENUINE", "Genuine"


class IpAdmission(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="ip_admissions"
    )
    ip_no = models.CharField(max_length=64)
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="ip_admissions"
    )
    visit = models.ForeignKey(
        "opd.Visit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_admissions",
    )
    doctor = models.ForeignKey(
        "masters.Doctor", on_delete=models.PROTECT, related_name="ip_admissions"
    )
    secondary_doctor = models.ForeignKey(
        "masters.Doctor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_secondary_admissions",
    )
    department = models.ForeignKey(
        "masters.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_admissions",
    )
    bed = models.ForeignKey(
        "masters.Bed", on_delete=models.PROTECT, related_name="ip_admissions"
    )
    admitted_at = models.DateTimeField()
    discharged_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=AdmissionStatus.choices, default=AdmissionStatus.ADMITTED
    )
    bed_charge_per_day = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    food_preference = models.CharField(
        max_length=16, choices=FoodPreference.choices, default=FoodPreference.VEG
    )
    diet = models.CharField(max_length=255, blank=True, default="")
    is_mlc = models.BooleanField(default=False)
    is_vip = models.BooleanField(default=False)
    is_quarantine = models.BooleanField(default=False)
    insurance_covered = models.BooleanField(default=False)
    icd_code = models.CharField(max_length=16, blank=True, default="")
    attendant_name = models.CharField(max_length=255, blank=True, default="")
    attendant_relation = models.CharField(max_length=64, blank=True, default="")
    attendant_mobile = models.CharField(max_length=20, blank=True, default="")
    admitted_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_admissions_created"
    )
    settlement_bill = models.ForeignKey(
        "billing.Bill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_settlements",
    )
    cancel_reason = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-admitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "ip_no"], name="uniq_ip_admission_no"),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_ip_admission_idempotency",
            ),
        ]


class IpTransfer(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        DOCTOR = "DOCTOR", "Doctor transfer"
        BED = "BED", "Bed transfer"

    admission = models.ForeignKey(IpAdmission, on_delete=models.CASCADE, related_name="transfers")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    from_doctor = models.ForeignKey(
        "masters.Doctor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_transfers_from",
    )
    to_doctor = models.ForeignKey(
        "masters.Doctor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_transfers_to",
    )
    from_bed = models.ForeignKey(
        "masters.Bed",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_transfers_from",
    )
    to_bed = models.ForeignKey(
        "masters.Bed",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_transfers_to",
    )
    reason = models.CharField(max_length=255, blank=True, default="")
    transferred_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_transfers"
    )
    transferred_at = models.DateTimeField()

    class Meta:
        ordering = ["-transferred_at"]


class IpDailyCharge(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        BED = "BED", "Bed / room"
        NURSING = "NURSING", "Nursing"
        OTHER = "OTHER", "Other"

    admission = models.ForeignKey(IpAdmission, on_delete=models.CASCADE, related_name="daily_charges")
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="ip_daily_charges"
    )
    charge_date = models.DateField()
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.BED)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    bill = models.ForeignKey(
        "billing.Bill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_daily_charges",
    )
    posted_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_daily_charges"
    )

    class Meta:
        ordering = ["charge_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["admission", "charge_date", "kind"],
                name="uniq_ip_daily_charge_day_kind",
            )
        ]


class IpNursingNote(UUIDModel, TimeStampedModel):
    admission = models.ForeignKey(IpAdmission, on_delete=models.CASCADE, related_name="nursing_notes")
    note = models.TextField()
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_nursing_notes"
    )
    recorded_at = models.DateTimeField()

    class Meta:
        ordering = ["-recorded_at"]


class IpDoctorOrder(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    admission = models.ForeignKey(IpAdmission, on_delete=models.CASCADE, related_name="doctor_orders")
    order_text = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    ordered_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_doctor_orders"
    )
    ordered_at = models.DateTimeField()

    class Meta:
        ordering = ["-ordered_at"]


class IpMedicationAdmin(UUIDModel, TimeStampedModel):
    admission = models.ForeignKey(IpAdmission, on_delete=models.CASCADE, related_name="mar_entries")
    drug_name = models.CharField(max_length=255)
    dose = models.CharField(max_length=64, blank=True, default="")
    route = models.CharField(max_length=64, blank=True, default="")
    given_at = models.DateTimeField()
    given_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_mar_entries"
    )
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-given_at"]


class IpDischargeSummary(UUIDModel, TimeStampedModel):
    admission = models.OneToOneField(
        IpAdmission, on_delete=models.CASCADE, related_name="discharge_summary"
    )
    template = models.ForeignKey(
        "masters.DocumentTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_discharge_summaries",
    )
    condition_on_admission = models.TextField(blank=True, default="")
    condition_on_discharge = models.TextField(blank=True, default="")
    chief_complaints = models.TextField(blank=True, default="")
    diagnosis = models.TextField(blank=True, default="")
    surgery = models.TextField(blank=True, default="")
    treatment_given = models.TextField(blank=True, default="")
    treatment_advised = models.TextField(blank=True, default="")
    investigations = models.TextField(blank=True, default="")
    icd_code = models.CharField(max_length=16, blank=True, default="")
    next_visit_on = models.DateField(null=True, blank=True)
    discharged_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="ip_discharges"
    )


class MedicalCertificate(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="medical_certificates"
    )
    admission = models.ForeignKey(
        IpAdmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certificates",
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="medical_certificates"
    )
    cert_no = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=CertificateKind.choices)
    disease_name = models.CharField(max_length=255, blank=True, default="")
    occupation = models.CharField(max_length=128, blank=True, default="")
    body = models.TextField(blank=True, default="")
    fit_on = models.DateField(null=True, blank=True)
    rest_from = models.DateField(null=True, blank=True)
    rest_to = models.DateField(null=True, blank=True)
    birth_details = models.TextField(blank=True, default="")
    birth_on = models.DateField(null=True, blank=True)
    death_on = models.DateField(null=True, blank=True)
    death_time = models.CharField(max_length=32, blank=True, default="")
    issued_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="medical_certificates"
    )
    issued_at = models.DateTimeField()

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "cert_no"], name="uniq_med_cert_no")
        ]
