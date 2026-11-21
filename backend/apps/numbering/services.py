"""
Gap-free numbering service.

CRITICAL: Call allocate() inside the same database transaction as the document
insert. Allocating outside that transaction will burn numbers on rollback.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.db.models import F

from apps.common.exceptions import AppError
from apps.numbering.models import DocumentType, NumberSequence
from apps.organizations.models import Facility, Organization


def financial_year_label(on_date: date, start_month: int = 4, start_day: int = 1) -> str:
    """Return label like 2026-27 for an Indian FY starting 1 April."""
    if (on_date.month, on_date.day) >= (start_month, start_day):
        start_year = on_date.year
    else:
        start_year = on_date.year - 1
    end_year_short = str(start_year + 1)[-2:]
    return f"{start_year}-{end_year_short}"


def format_number(prefix: str, value: int, padding: int) -> str:
    return f"{prefix}/{str(value).zfill(padding)}"


@transaction.atomic
def allocate(
    *,
    document_type: str,
    organization: Organization | None = None,
    facility: Facility | None = None,
    on_date: date | None = None,
) -> str:
    """
    Allocate the next gap-free number.

    Must be called inside an outer atomic block that also inserts the document.
    Uses SELECT FOR UPDATE on the sequence row.
    """
    on_date = on_date or date.today()

    if document_type == DocumentType.UHID:
        if organization is None:
            raise AppError("UHID allocation requires organization.", code="numbering_error")
        seq = (
            NumberSequence.objects.select_for_update()
            .filter(
                organization=organization,
                document_type=DocumentType.UHID,
            )
            .first()
        )
        if not seq:
            raise AppError("UHID sequence not configured.", code="sequence_missing")
    else:
        if facility is None:
            raise AppError("Document allocation requires facility.", code="numbering_error")
        settings_obj = getattr(facility, "settings", None)
        start_month = settings_obj.financial_year_start_month if settings_obj else 4
        start_day = settings_obj.financial_year_start_day if settings_obj else 1
        fy = financial_year_label(on_date, start_month, start_day)
        seq = (
            NumberSequence.objects.select_for_update()
            .filter(
                facility=facility,
                document_type=document_type,
                financial_year=fy,
            )
            .first()
        )
        if not seq:
            # Auto-create FY series from a template prefix pattern.
            prefix = f"{facility.code}/{document_type}/{fy}"
            seq = NumberSequence.objects.create(
                facility=facility,
                document_type=document_type,
                financial_year=fy,
                prefix=prefix,
                next_value=1,
                padding=6,
            )
            seq = NumberSequence.objects.select_for_update().get(pk=seq.pk)

    value = seq.next_value
    NumberSequence.objects.filter(pk=seq.pk).update(next_value=F("next_value") + 1)
    return format_number(seq.prefix, value, seq.padding)


def ensure_uhid_sequence(organization: Organization) -> NumberSequence:
    seq, _ = NumberSequence.objects.get_or_create(
        organization=organization,
        document_type=DocumentType.UHID,
        defaults={
            "prefix": f"{organization.code}/MR",
            "next_value": 1,
            "padding": 6,
            "financial_year": "",
        },
    )
    return seq


def ensure_facility_sequences(facility: Facility, on_date: date | None = None) -> list[NumberSequence]:
    on_date = on_date or date.today()
    settings_obj = getattr(facility, "settings", None)
    start_month = settings_obj.financial_year_start_month if settings_obj else 4
    start_day = settings_obj.financial_year_start_day if settings_obj else 1
    fy = financial_year_label(on_date, start_month, start_day)
    created = []
    for doc_type in (
        DocumentType.BILL,
        DocumentType.RCPT,
        DocumentType.VISIT,
        DocumentType.IP,
        DocumentType.LAB,
        DocumentType.RAD,
        DocumentType.ADV,
        DocumentType.REF,
        DocumentType.CN,
        DocumentType.PO,
        DocumentType.GRN,
        DocumentType.PHARM,
    ):
        seq, _ = NumberSequence.objects.get_or_create(
            facility=facility,
            document_type=doc_type,
            financial_year=fy,
            defaults={
                "prefix": f"{facility.code}/{doc_type}/{fy}",
                "next_value": 1,
                "padding": 6,
            },
        )
        created.append(seq)
    return created
