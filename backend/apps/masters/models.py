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
    address = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
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
    description = models.TextField(blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_doctor_procedure = models.BooleanField(default=False)
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
    city_ref = models.ForeignKey(
        "City", on_delete=models.SET_NULL, null=True, blank=True, related_name="areas"
    )

    class Meta:
        ordering = ["state", "city", "name"]


class Country(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["name"]


class State(UUIDModel, TimeStampedModel):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="states")
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["country", "name"], name="uniq_state_country_name")
        ]


class City(UUIDModel, TimeStampedModel):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="cities")
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["state", "name"], name="uniq_city_state_name")
        ]


class Service(UUIDModel, TimeStampedModel):
    class ServiceType(models.TextChoices):
        DOCTOR = "DOCTOR", "Doctor Service"
        ROOM = "ROOM", "Room Service"
        GENERAL = "GENERAL", "General Service"

    class ChargeUnit(models.TextChoices):
        HOURLY = "HOURLY", "Hourly"
        DAILY = "DAILY", "Daily"
        PACKAGE = "PACKAGE", "Package"
        UNIT = "UNIT", "Unit"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="services"
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    service_type = models.CharField(max_length=16, choices=ServiceType.choices)
    charge_unit = models.CharField(max_length=16, choices=ChargeUnit.choices, default=ChargeUnit.UNIT)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_service_facility_code")
        ]
        ordering = ["name"]


class RoomType(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="room_types"
    )
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_room_type_facility_name")
        ]
        ordering = ["name"]


class Ward(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="wards"
    )
    name = models.CharField(max_length=128)
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="wards")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_ward_facility_name")
        ]
        ordering = ["name"]


class Room(UUIDModel, TimeStampedModel):
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ward", "name"], name="uniq_room_ward_name")
        ]
        ordering = ["name"]


class Bed(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        VACANT = "VACANT", "Vacant"
        OCCUPIED = "OCCUPIED", "Occupied"
        BLOCKED = "BLOCKED", "Blocked"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="beds")
    code = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.VACANT)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["room", "code"], name="uniq_bed_room_code")
        ]
        ordering = ["code"]


class Tariff(UUIDModel, TimeStampedModel):
    """Charge for one procedure or service under one organization. Blank party is hospital cash."""

    class Kind(models.TextChoices):
        PROCEDURE = "PROCEDURE", "Procedure"
        SERVICE = "SERVICE", "Service"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="tariffs"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    procedure = models.ForeignKey(
        Procedure, on_delete=models.CASCADE, null=True, blank=True, related_name="tariffs"
    )
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, null=True, blank=True, related_name="tariffs"
    )
    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, null=True, blank=True, related_name="tariffs"
    )
    party = models.ForeignKey(
        OrganizationParty, on_delete=models.CASCADE, null=True, blank=True, related_name="tariffs"
    )
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "kind", "procedure", "service", "doctor", "party"],
                name="uniq_tariff_scope",
                nulls_distinct=False,
            )
        ]


class DiscountRule(UUIDModel, TimeStampedModel):
    """Facility ceiling. A discount cannot exceed the strictest active rule."""

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="discount_rules"
    )
    name = models.CharField(max_length=128)
    max_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    max_flat = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_discount_rule_facility_name")
        ]
        ordering = ["name"]


class PaymentModeConfig(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="payment_modes"
    )
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "code"], name="uniq_payment_mode_facility_code")
        ]
        ordering = ["name"]


class DocumentTemplate(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        PRESCRIPTION = "PRESCRIPTION", "Prescription"
        DISCHARGE = "DISCHARGE", "Discharge"
        CERTIFICATE = "CERTIFICATE", "Certificate"

    class CertificateType(models.TextChoices):
        NONE = "", "—"
        FITNESS = "FITNESS", "Fitness"
        REST = "REST", "Rest Advice"
        LEAVE = "LEAVE", "Medical Leave"
        EMERGENCY = "EMERGENCY", "Emergency"
        ESSENTIALITY = "ESSENTIALITY", "Essentiality"
        BIRTH = "BIRTH", "Birth"
        DEATH = "DEATH", "Death"
        GENUINE = "GENUINE", "Genuine"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="templates"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    certificate_type = models.CharField(
        max_length=16, choices=CertificateType.choices, blank=True, default=""
    )
    name = models.CharField(max_length=128)
    body = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_template_facility_name")
        ]
        ordering = ["kind", "name"]
