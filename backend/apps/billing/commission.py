"""Referral and PRO commission. TDS runs only after an accountant confirms the rate."""

from __future__ import annotations

from decimal import Decimal

from apps.billing.models import Bill, CommissionEntry
from apps.common.money import money


def record_commissions(bill: Bill, referral=None, pro=None) -> str:
    settings_row = bill.facility.settings
    if not settings_row.tds_rate_confirmed:
        return "NOT_CONFIGURED"
    hospital = money(sum((line.hospital_share for line in bill.lines.all()), Decimal("0")))
    base = money(hospital - bill.discount_from_hospital)
    wrote = False
    if referral is not None and money(referral.commission_percent) > 0:
        _write(bill, CommissionEntry.Party.REFERRAL, referral.id, referral.name, base, referral.commission_percent)
        wrote = True
    if pro is not None and money(pro.commission_percent) > 0:
        _write(bill, CommissionEntry.Party.PRO, pro.id, pro.name, base, pro.commission_percent)
        wrote = True
    return "POSTED" if wrote else "NONE"


def _write(bill, kind, party_id, name, base, percent) -> None:
    if bill.commissions.filter(party_kind=kind, party_id=party_id, reversal_of__isnull=True).exists():
        return
    rate = money(bill.facility.settings.tds_commission_rate)
    commission = money(base * money(percent) / Decimal("100"))
    tds = money(commission * rate / Decimal("100"))
    CommissionEntry.objects.create(
        facility=bill.facility,
        bill=bill,
        party_kind=kind,
        party_id=party_id,
        party_name=name,
        base_amount=base,
        commission_amount=commission,
        tds_amount=tds,
        net_payable=money(commission - tds),
    )


def reverse_commissions(bill: Bill) -> None:
    for entry in bill.commissions.filter(reversal_of__isnull=True):
        if entry.reversals.exists():
            continue
        CommissionEntry.objects.create(
            facility=entry.facility,
            bill=bill,
            party_kind=entry.party_kind,
            party_id=entry.party_id,
            party_name=entry.party_name,
            base_amount=money(-entry.base_amount),
            commission_amount=money(-entry.commission_amount),
            tds_amount=money(-entry.tds_amount),
            net_payable=money(-entry.net_payable),
            reversal_of=entry,
        )
