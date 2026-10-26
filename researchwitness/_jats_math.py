"""Exact bounded JATS proportion arithmetic without network or mutable context."""
from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
import re


def percentage_recalculation(numerator: int, denominator: int,
                             reported_percent: str, display_precision: int) -> dict[str, str | bool]:
    """Compute one supplied ratio. Population/rounding applicability stays unresolved."""
    if (type(numerator) is not int or type(denominator) is not int
            or numerator < 0 or denominator <= 0 or numerator > denominator
            or max(numerator, denominator) > 999_999_999):
        raise ValueError("Operands are outside supported proportion domain")
    if type(display_precision) is not int or not 0 <= display_precision <= 6:
        raise ValueError("Display precision outside supported range")
    if type(reported_percent) is not str or re.fullmatch(
            r"[0-9]{1,3}(?:\.[0-9]{1,6})?", reported_percent) is None:
        raise ValueError("Reported percentage must be plain decimal source text")
    try:
        reported = Decimal(reported_percent)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid decimal source text") from exc
    if (not reported.is_finite() or reported < 0 or reported > 100
            or len(reported_percent.partition(".")[2]) != display_precision):
        raise ValueError("Reported percentage or display precision unsupported")
    ctx = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                  capitals=1, clamp=0, traps=[])
    with localcontext(ctx):
        exact = Decimal(numerator) * Decimal(100) / Decimal(denominator)
        rounded = exact.quantize(Decimal(1).scaleb(-display_precision),
                                 rounding=ROUND_HALF_UP)
    return {
        "exact_ratio_percent": f"{numerator * 100}/{denominator}",
        "unrounded_decimal_percent": format(exact, "f"),
        "rounded_percent": format(rounded, "f"),
        "reported_percent": format(reported, "f"),
        "display_precision": str(display_precision),
        "arithmetic_matches": reported == rounded,
    }
