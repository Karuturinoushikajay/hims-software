"""Seed demo organization, facility, roles, users, screens, and number sequences."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import (
    Membership,
    Permission,
    Role,
    RolePermission,
    RoleScreen,
    Screen,
    User,
)
from apps.numbering.services import ensure_facility_sequences, ensure_uhid_sequence
from apps.organizations.models import Facility, FacilitySettings, Organization

PERMISSIONS = [
    ("accounts.user.read", "accounts", "user.read", "View users"),
    ("accounts.user.create", "accounts", "user.create", "Create users"),
    ("accounts.user.update", "accounts", "user.update", "Update users"),
    ("accounts.user.deactivate", "accounts", "user.deactivate", "Deactivate users"),
    ("accounts.role.read", "accounts", "role.read", "View roles"),
    ("accounts.role.create", "accounts", "role.create", "Create roles"),
    ("accounts.role.update", "accounts", "role.update", "Update role permissions/screens"),
    ("organizations.settings.read", "organizations", "settings.read", "View facility settings"),
    ("organizations.settings.update", "organizations", "settings.update", "Update facility settings"),
    ("audit.read", "audit", "read", "View audit logs"),
    ("numbering.read", "numbering", "read", "View number sequences"),
    ("home.view", "home", "view", "View home dashboard"),
    ("patients.read", "patients", "read", "Search and view patients"),
    ("patients.create", "patients", "create", "Register patients"),
    ("opd.appointment.manage", "opd", "appointment.manage", "Book appointments and view the queue"),
    ("opd.consult.create", "opd", "consult.create", "Record a consultation"),
    ("opd.procedure.create", "opd", "procedure.create", "Book a procedure"),
    ("billing.collect", "billing", "collect", "Collect a payment"),
    ("billing.read", "billing", "read", "View bills, advances, and printouts"),
    ("billing.refund", "billing", "refund", "Refund, credit, or cancel a bill"),
    ("billing.authorize_refund", "billing", "authorize_refund", "Authorize a refund above the threshold"),
    ("billing.day_close", "billing", "day_close", "Close or reopen the business day"),
    ("billing.discount_authorize", "billing", "discount_authorize", "Approve a discount above the requester limit"),
    ("masters.read", "masters", "read", "View hospital masters"),
    ("masters.write", "masters", "write", "Create and update hospital masters"),
    ("clinical.read", "clinical", "read", "View clinical notes, timeline, and printouts"),
    ("clinical.write", "clinical", "write", "Record notes, allergies, prescriptions, and follow-ups"),
    ("clinical.order", "clinical", "order", "Order laboratory or radiology tests"),
    ("pharmacy.read", "pharmacy", "read", "View pharmacy stock and sales"),
    ("pharmacy.write", "pharmacy", "write", "Maintain drug master and suppliers"),
    ("pharmacy.purchase", "pharmacy", "purchase", "Create purchase orders and receive goods"),
    ("pharmacy.dispense", "pharmacy", "dispense", "Dispense, sell, and accept returns"),
    ("pharmacy.adjust", "pharmacy", "adjust", "Adjust or dump stock"),
]

SCREENS = [
    ("home", "home", "Home", "/", 0),
    ("facility_settings", "admin", "Facility Settings", "/settings", 10),
    ("users", "admin", "Users", "/users", 20),
    ("roles", "admin", "Roles", "/roles", 30),
    ("number_sequences", "admin", "Number Sequences", "/sequences", 40),
    ("audit_logs", "admin", "Audit Logs", "/audit", 50),
    ("register", "opd", "Register", "/register", 60),
    ("queue", "opd", "Queue", "/queue", 70),
    ("consult", "opd", "Consultation", "/consult", 80),
    ("procedures", "opd", "Procedures", "/procedures", 90),
    ("billing", "billing", "Billing", "/billing", 100),
    ("masters", "admin", "Masters", "/masters", 55),
    ("emr", "clinical", "Clinical record", "/emr", 85),
    ("pharmacy", "pharmacy", "Pharmacy", "/pharmacy", 95),
]

ROLE_DEFS = [
    ("SUPER_ADMIN", "Super Admin", True, True),
    ("FACILITY_ADMIN", "Facility Admin", True, False),
    ("RECEPTIONIST", "Receptionist", False, False),
    ("CASHIER", "Cashier/Billing", False, False),
    ("DOCTOR", "Doctor", False, False),
    ("NURSE", "Nurse", False, False),
    ("LAB_TECH", "Lab Technician", False, False),
    ("LAB_AUTHORIZER", "Lab Pathologist/Authorizer", False, False),
    ("RAD_TECH", "Radiology Technician", False, False),
    ("RADIOLOGIST", "Radiologist", False, False),
    ("PHARMACIST", "Pharmacist", False, False),
    ("STORE_KEEPER", "Store Keeper", False, False),
    ("ACCOUNTANT", "Accountant", False, False),
    ("MANAGER", "Manager", False, False),
]

# Role code -> permission codes
ROLE_PERMS = {
    "SUPER_ADMIN": [p[0] for p in PERMISSIONS],
    "FACILITY_ADMIN": [
        "home.view",
        "accounts.user.read",
        "accounts.user.create",
        "accounts.user.update",
        "accounts.user.deactivate",
        "accounts.role.read",
        "accounts.role.create",
        "accounts.role.update",
        "organizations.settings.read",
        "organizations.settings.update",
        "audit.read",
        "numbering.read",
        "patients.read",
        "patients.create",
        "opd.appointment.manage",
        "opd.consult.create",
        "opd.procedure.create",
        "billing.collect",
        "billing.read",
        "billing.refund",
        "billing.authorize_refund",
        "billing.day_close",
        "billing.discount_authorize",
        "masters.read",
        "masters.write",
        "clinical.read",
        "clinical.write",
        "clinical.order",
        "pharmacy.read",
        "pharmacy.write",
        "pharmacy.purchase",
        "pharmacy.dispense",
        "pharmacy.adjust",
    ],
    "RECEPTIONIST": [
        "home.view",
        "patients.read",
        "patients.create",
        "opd.appointment.manage",
        "opd.consult.create",
        "opd.procedure.create",
        "billing.collect",
        "billing.read",
        "billing.refund",
        "clinical.read",
    ],
    "CASHIER": [
        "home.view",
        "patients.read",
        "opd.appointment.manage",
        "opd.consult.create",
        "opd.procedure.create",
        "billing.collect",
        "billing.read",
        "billing.refund",
        "billing.day_close",
    ],
    "DOCTOR": [
        "home.view",
        "patients.read",
        "opd.appointment.manage",
        "opd.consult.create",
        "clinical.read",
        "clinical.write",
        "clinical.order",
    ],
    "NURSE": ["home.view", "patients.read", "clinical.read"],
    "LAB_TECH": ["home.view"],
    "LAB_AUTHORIZER": ["home.view"],
    "RAD_TECH": ["home.view"],
    "RADIOLOGIST": ["home.view"],
    "PHARMACIST": [
        "home.view",
        "patients.read",
        "pharmacy.read",
        "pharmacy.write",
        "pharmacy.purchase",
        "pharmacy.dispense",
        "pharmacy.adjust",
        "billing.collect",
        "billing.read",
        "billing.refund",
        "clinical.read",
    ],
    "STORE_KEEPER": [
        "home.view",
        "pharmacy.read",
        "pharmacy.write",
        "pharmacy.purchase",
        "pharmacy.adjust",
    ],
    "ACCOUNTANT": [
        "home.view",
        "numbering.read",
        "billing.read",
        "billing.authorize_refund",
        "billing.day_close",
        "billing.discount_authorize",
        "opd.consult.create",
    ],
    "MANAGER": [
        "home.view",
        "audit.read",
        "numbering.read",
        "organizations.settings.read",
        "masters.read",
    ],
}

ROLE_SCREENS = {
    "SUPER_ADMIN": [s[0] for s in SCREENS],
    "FACILITY_ADMIN": [s[0] for s in SCREENS],
    "RECEPTIONIST": ["home", "register", "queue", "consult", "procedures", "billing", "emr"],
    "CASHIER": ["home", "queue", "consult", "procedures", "billing"],
    "DOCTOR": ["home", "queue", "consult", "emr"],
    "PHARMACIST": ["home", "pharmacy", "billing"],
    "STORE_KEEPER": ["home", "pharmacy"],
    "ACCOUNTANT": ["home", "billing"],
}

DEMO_USERS = [
    ("superadmin", "SUPER_ADMIN", "Super", "Admin", True),
    ("facadmin", "FACILITY_ADMIN", "Facility", "Admin", False),
    ("receptionist", "RECEPTIONIST", "Rita", "Reception", False),
    ("cashier", "CASHIER", "Carl", "Cashier", False),
    ("doctor", "DOCTOR", "Dr. Divya", "Sharma", False),
    ("pharmacist", "PHARMACIST", "Priya", "Pharmacist", False),
]


class Command(BaseCommand):
    help = "Seed demo hospital data for Phase 0. Refused when DEBUG is false (unless --force)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding when DEBUG is false (tests / controlled environments only).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options.get("force"):
            raise CommandError("seed_demo refuses to run when DEBUG is false.")
        password = settings.DEMO_SEED_PASSWORD
        if not password:
            raise CommandError("DEMO_SEED_PASSWORD is not set.")


        for code, module, action, desc in PERMISSIONS:
            Permission.objects.update_or_create(
                code=code,
                defaults={"module": module, "action": action, "description": desc},
            )

        for code, module, name, route, sort in SCREENS:
            Screen.objects.update_or_create(
                code=code,
                defaults={
                    "module": module,
                    "name": name,
                    "route": route,
                    "sort_order": sort,
                    "is_active": True,
                },
            )

        org, _ = Organization.objects.update_or_create(
            code="DHG",
            defaults={"name": "Demo Hospital Group", "is_active": True},
        )
        facility, created = Facility.objects.update_or_create(
            organization=org,
            code="DMSH",
            defaults={
                "name": "Demo Multi-Speciality Hospital",
                "legal_name": "Demo Multi-Speciality Hospital Pvt Ltd",
                "address_line1": "1 Hospital Road",
                "city": "Hyderabad",
                "state": "Telangana",
                "state_code": "36",
                "pincode": "500001",
                "country": "India",
                "phone": "+91-40-00000000",
                "email": "admin@demo-hospital.example",
                "bed_capacity": 180,
                "timezone": "Asia/Kolkata",
                "currency": "INR",
                "is_active": True,
            },
        )
        FacilitySettings.objects.update_or_create(
            facility=facility,
            defaults={
                "gstin": "36AAAAA0000A1Z5",
                "gstin_confirmed": False,
                "financial_year_start_month": 4,
                "financial_year_start_day": 1,
                "session_timeout_minutes": 30,
                "refund_auth_threshold": Decimal("5000.00"),
                "tds_commission_rate": Decimal("10.00"),
                "tds_rate_confirmed": False,
                "require_2fa_roles": ["SUPER_ADMIN", "DOCTOR"],
                "letterhead_text": "Demo Multi-Speciality Hospital",
                "registration_fee": Decimal("100.00"),
                "registration_validity_days": 365,
            },
        )

        perm_map = {p.code: p for p in Permission.objects.all()}
        screen_map = {s.code: s for s in Screen.objects.all()}

        roles = {}
        for code, name, is_system, _ in ROLE_DEFS:
            role, _ = Role.objects.update_or_create(
                facility=facility,
                code=code,
                defaults={
                    "name": name,
                    "is_system": is_system,
                    "description": f"{name} role",
                    "own_collection_only": code == "CASHIER",
                    "max_discount_percent": Decimal("10.00")
                    if code in ("FACILITY_ADMIN", "SUPER_ADMIN", "MANAGER", "ACCOUNTANT")
                    else Decimal("5.00"),
                    "max_discount_amount": Decimal("5000.00")
                    if code in ("FACILITY_ADMIN", "SUPER_ADMIN", "MANAGER", "ACCOUNTANT")
                    else Decimal("200.00"),
                },
            )
            roles[code] = role
            RolePermission.objects.filter(role=role).delete()
            for pcode in ROLE_PERMS.get(code, ["home.view"]):
                if pcode in perm_map:
                    RolePermission.objects.create(role=role, permission=perm_map[pcode])
            RoleScreen.objects.filter(role=role).delete()
            for i, scode in enumerate(ROLE_SCREENS.get(code, ["home"])):
                if scode in screen_map:
                    RoleScreen.objects.create(
                        role=role, screen=screen_map[scode], sort_order=i
                    )

        for username, role_code, first, last, is_super in DEMO_USERS:
            user, created_user = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@demo-hospital.example",
                    "is_staff": is_super,
                    "is_superuser": is_super,
                    "is_active": True,
                },
            )
            if created_user or True:
                user.set_password(password)
                user.first_name = first
                user.last_name = last
                user.is_staff = is_super
                user.is_superuser = is_super
                user.is_active = True
                # Leave totp_enabled False so demos can enroll; policy still requires setup.
                user.save()
            Membership.objects.update_or_create(
                user=user,
                facility=facility,
                role=roles[role_code],
                defaults={"is_active": True},
            )

        ensure_uhid_sequence(org)
        ensure_facility_sequences(facility)
        _seed_opd_masters(facility)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded org={org.code} facility={facility.code} users={len(DEMO_USERS)}"
        ))


def _seed_opd_masters(facility):
    from datetime import time

    from apps.accounts.models import User
    from apps.masters.models import (
        PRO,
        Area,
        Department,
        Doctor,
        DoctorSchedule,
        OrganizationParty,
        Procedure,
        ReferralDoctor,
        Specialization,
    )

    medicine, _ = Department.objects.update_or_create(
        facility=facility, name="General Medicine", defaults={"is_active": True}
    )
    cardio, _ = Department.objects.update_or_create(
        facility=facility, name="Cardiology", defaults={"is_active": True}
    )
    gen, _ = Specialization.objects.update_or_create(
        facility=facility, name="General Physician", defaults={"department": medicine, "is_active": True}
    )
    card_spec, _ = Specialization.objects.update_or_create(
        facility=facility, name="Cardiology", defaults={"department": cardio, "is_active": True}
    )
    doctor_user = User.objects.filter(username="doctor").first()
    doctor, _ = Doctor.objects.update_or_create(
        facility=facility,
        code="DIVYA",
        defaults={
            "user": doctor_user,
            "name": "Dr. Divya Sharma",
            "department": medicine,
            "specialization": gen,
            "consultation_fee": Decimal("500.00"),
            "hospital_share": Decimal("300.00"),
            "doctor_share": Decimal("200.00"),
            "review_days": 7,
            "is_active": True,
        },
    )
    for weekday in range(0, 6):
        DoctorSchedule.objects.update_or_create(
            doctor=doctor,
            weekday=weekday,
            defaults={"start_time": time(9, 0), "end_time": time(13, 0), "slot_minutes": 15},
        )
    Doctor.objects.update_or_create(
        facility=facility,
        code="ARUN",
        defaults={
            "name": "Dr. Arun Rao",
            "department": cardio,
            "specialization": card_spec,
            "consultation_fee": Decimal("800.00"),
            "hospital_share": Decimal("500.00"),
            "doctor_share": Decimal("300.00"),
            "review_days": 7,
            "is_active": True,
        },
    )
    ReferralDoctor.objects.update_or_create(
        facility=facility, name="Self", defaults={"is_active": True, "hospital": "", "commission_percent": Decimal("0.00")}
    )
    ReferralDoctor.objects.update_or_create(
        facility=facility,
        name="City Clinic",
        defaults={"is_active": True, "hospital": "City Clinic", "commission_percent": Decimal("10.00")},
    )
    PRO.objects.update_or_create(
        facility=facility,
        name="Front Desk PRO",
        defaults={"mobile": "9000000000", "is_active": True, "commission_percent": Decimal("5.00")},
    )
    OrganizationParty.objects.update_or_create(
        facility=facility, name="Demo TPA", defaults={"kind": "TPA", "is_active": True}
    )
    Procedure.objects.update_or_create(
        facility=facility,
        code="DRESS",
        defaults={
            "name": "Dressing",
            "amount": Decimal("200.00"),
            "hospital_share": Decimal("200.00"),
            "doctor_share": Decimal("0.00"),
            "is_active": True,
        },
    )
    from apps.masters.models import (
        Bed,
        City,
        Country,
        DiscountRule,
        DocumentTemplate,
        PaymentModeConfig,
        Room,
        RoomType,
        Service,
        State,
        Ward,
    )

    india, _ = Country.objects.get_or_create(name="India")
    telangana, _ = State.objects.get_or_create(country=india, name="Telangana")
    hyderabad, _ = City.objects.get_or_create(state=telangana, name="Hyderabad")
    Area.objects.get_or_create(
        country="India",
        state="Telangana",
        city="Hyderabad",
        name="Ameerpet",
        defaults={"city_ref": hyderabad},
    )
    for code, label in (
        ("CASH", "Cash"),
        ("CARD", "Card"),
        ("UPI", "UPI"),
        ("CHEQUE", "Cheque"),
        ("TRANSFER", "Bank Transfer"),
    ):
        PaymentModeConfig.objects.update_or_create(
            facility=facility, code=code, defaults={"name": label, "is_active": True}
        )
    DiscountRule.objects.update_or_create(
        facility=facility,
        name="Facility ceiling",
        defaults={"max_percent": Decimal("100.00"), "max_flat": Decimal("999999999.99"), "is_active": True},
    )
    for name in ("ER Ward", "General Ward", "ICU", "Step Down ICU", "Special Rooms"):
        RoomType.objects.update_or_create(facility=facility, name=name, defaults={"is_active": True})
    general = RoomType.objects.get(facility=facility, name="General Ward")
    ward, _ = Ward.objects.update_or_create(
        facility=facility, name="General Ward A", defaults={"room_type": general, "is_active": True}
    )
    room, _ = Room.objects.update_or_create(ward=ward, name="101", defaults={"is_active": True})
    for code in ("101-A", "101-B"):
        Bed.objects.update_or_create(room=room, code=code, defaults={"status": "VACANT", "is_active": True})
    Service.objects.update_or_create(
        facility=facility,
        code="NURSING",
        defaults={
            "name": "Nursing charges",
            "service_type": "ROOM",
            "charge_unit": "DAILY",
            "amount": Decimal("500.00"),
            "hospital_share": Decimal("500.00"),
            "doctor_share": Decimal("0.00"),
            "is_active": True,
        },
    )
    Service.objects.update_or_create(
        facility=facility,
        code="OXYGEN",
        defaults={
            "name": "Oxygen per day",
            "service_type": "GENERAL",
            "charge_unit": "DAILY",
            "amount": Decimal("800.00"),
            "hospital_share": Decimal("800.00"),
            "doctor_share": Decimal("0.00"),
            "is_active": True,
        },
    )
    DocumentTemplate.objects.update_or_create(
        facility=facility,
        name="OPD prescription",
        defaults={
            "kind": "PRESCRIPTION",
            "body": "Rx\n1. \nAdvice: \nReview: ",
            "is_active": True,
        },
    )
    DocumentTemplate.objects.update_or_create(
        facility=facility,
        name="Discharge summary",
        defaults={
            "kind": "DISCHARGE",
            "body": "Diagnosis:\nTreatment given:\nAdvice on discharge:\n",
            "is_active": True,
        },
    )
    from apps.billing.models import TaxCategory

    TaxCategory.objects.update_or_create(
        facility=facility,
        name="Outpatient services",
        defaults={"hsn_sac": "9993", "rate_percent": Decimal("18.00"), "is_active": True},
    )
    _seed_clinical(facility)


def _seed_clinical(facility):
    from apps.clinical.models import Drug, DrugInteraction, IcdCode

    # Small reviewed starter set only — not a full ICD or formulary catalog.
    for code, name in (
        ("J06.9", "Acute upper respiratory infection, unspecified"),
        ("I10", "Essential (primary) hypertension"),
        ("E11.9", "Type 2 diabetes mellitus without complications"),
        ("K21.0", "Gastro-oesophageal reflux disease with oesophagitis"),
        ("M54.5", "Low back pain"),
    ):
        IcdCode.objects.update_or_create(code=code, defaults={"name": name, "is_active": True})

    para, _ = Drug.objects.update_or_create(
        facility=facility,
        code="PARA500",
        defaults={
            "name": "Paracetamol 500 mg",
            "brand_name": "Calpol 500",
            "generic_name": "Paracetamol",
            "schedule": "NONE",
            "unit": "TAB",
            "reorder_level": 50,
            "purchase_price": Decimal("1.00"),
            "selling_price": Decimal("2.00"),
            "hsn_sac": "3004",
            "tax_rate": Decimal("12.00"),
            "is_active": True,
        },
    )
    ibuprofen, _ = Drug.objects.update_or_create(
        facility=facility,
        code="IBU400",
        defaults={
            "name": "Ibuprofen 400 mg",
            "brand_name": "Brufen 400",
            "generic_name": "Ibuprofen",
            "schedule": "H",
            "unit": "TAB",
            "reorder_level": 40,
            "purchase_price": Decimal("1.50"),
            "selling_price": Decimal("3.00"),
            "hsn_sac": "3004",
            "tax_rate": Decimal("12.00"),
            "is_active": True,
        },
    )
    amox, _ = Drug.objects.update_or_create(
        facility=facility,
        code="AMOX500",
        defaults={
            "name": "Amoxicillin 500 mg",
            "brand_name": "Mox 500",
            "generic_name": "Amoxicillin",
            "schedule": "H",
            "unit": "CAP",
            "reorder_level": 30,
            "purchase_price": Decimal("4.00"),
            "selling_price": Decimal("8.00"),
            "hsn_sac": "3004",
            "tax_rate": Decimal("12.00"),
            "is_active": True,
        },
    )
    Drug.objects.update_or_create(
        facility=facility,
        code="OMEP20",
        defaults={
            "name": "Omeprazole 20 mg",
            "brand_name": "Omez 20",
            "generic_name": "Omeprazole",
            "schedule": "H",
            "unit": "CAP",
            "reorder_level": 20,
            "purchase_price": Decimal("3.00"),
            "selling_price": Decimal("6.00"),
            "hsn_sac": "3004",
            "tax_rate": Decimal("12.00"),
            "is_active": True,
        },
    )
    Drug.objects.update_or_create(
        facility=facility,
        code="TRAM50",
        defaults={
            "name": "Tramadol 50 mg",
            "brand_name": "Tramazac 50",
            "generic_name": "Tramadol",
            "schedule": "H1",
            "unit": "CAP",
            "reorder_level": 10,
            "purchase_price": Decimal("5.00"),
            "selling_price": Decimal("10.00"),
            "hsn_sac": "3004",
            "tax_rate": Decimal("12.00"),
            "is_active": True,
        },
    )
    DrugInteraction.objects.update_or_create(
        facility=facility,
        drug_a=para,
        drug_b=ibuprofen,
        defaults={
            "severity": "MODERATE",
            "message": "Paracetamol with ibuprofen: confirm the combined regimen and monitor for adverse effects.",
        },
    )
    from apps.pharmacy.models import Supplier

    Supplier.objects.update_or_create(
        facility=facility,
        name="MedSupply India",
        defaults={"mobile": "9000000011", "gstin": "36AABCU9603R1ZM", "is_active": True},
    )
    _ = amox
