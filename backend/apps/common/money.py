"""Money helpers. Always use Decimal; never float."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTIZE = Decimal("0.01")


def money(value) -> Decimal:
    """Coerce to Decimal quantized to paise (half-up)."""
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    return d.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def zero() -> Decimal:
    return money(0)
