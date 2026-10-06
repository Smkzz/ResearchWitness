"""Strict arithmetic for source-mapped unadjusted 2x2 results."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from fractions import Fraction
import re
from typing import Any


DISPLAYED_NUMBER = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,8})?$')
MAX_COUNT = 1_000_000_000


def recompute_two_by_two(
    *,
    exposed_events: int,
    exposed_non_events: int,
    reference_events: int,
    reference_non_events: int,
    measure: str,
    reported: str,
    reference_group_explicit: bool,
    timepoint_explicit: bool,
    adjustment_status: str,
) -> dict[str, Any]:
    """Recompute a crude RR, OR, or risk difference from four explicit counts.

    This is an operand-level calculator. It does not extract or map numbers from
    paper prose/tables. Missing model context or an unsupported zero-cell case
    returns UNSUPPORTED without producing a candidate.
    """
    cells = (exposed_events, exposed_non_events, reference_events, reference_non_events)
    if any(type(value) is not int or value < 0 for value in cells):
        return {'status': 'UNSUPPORTED', 'reason': 'OPERANDS_MISSING_OR_INVALID', 'candidate': None}
    if any(value > MAX_COUNT for value in cells) or len(reported) > 32:
        return {'status': 'UNSUPPORTED', 'reason': 'RESOURCE_LIMIT_EXCEEDED', 'candidate': None}
    if not reference_group_explicit or not timepoint_explicit:
        return {'status': 'UNSUPPORTED', 'reason': 'REFERENCE_GROUP_OR_TIMEPOINT_UNSPECIFIED', 'candidate': None}
    if adjustment_status != 'unadjusted':
        return {'status': 'UNSUPPORTED', 'reason': 'MODEL_ADJUSTED_OR_ADJUSTMENT_STATUS_UNKNOWN', 'candidate': None}
    if not DISPLAYED_NUMBER.fullmatch(reported):
        return {'status': 'UNSUPPORTED', 'reason': 'REPORTED_VALUE_OR_PRECISION_UNSUPPORTED', 'candidate': None}
    if measure not in ('risk_ratio', 'odds_ratio', 'difference_in_proportions'):
        return {'status': 'UNSUPPORTED', 'reason': 'STATISTIC_TYPE_UNSUPPORTED', 'candidate': None}

    exposed_total = exposed_events + exposed_non_events
    reference_total = reference_events + reference_non_events
    if exposed_total == 0 or reference_total == 0:
        return {'status': 'UNSUPPORTED', 'reason': 'ZERO_GROUP_TOTAL', 'candidate': None}
    if measure == 'risk_ratio':
        if reference_events == 0:
            return {'status': 'UNSUPPORTED', 'reason': 'ZERO_REFERENCE_RISK', 'candidate': None}
        exact = Fraction(exposed_events, exposed_total) / Fraction(reference_events, reference_total)
    elif measure == 'odds_ratio':
        if exposed_non_events == 0 or reference_events == 0:
            return {'status': 'UNSUPPORTED', 'reason': 'ZERO_CELL_POLICY_UNSPECIFIED', 'candidate': None}
        exact = Fraction(exposed_events * reference_non_events, exposed_non_events * reference_events)
    else:
        exact = Fraction(exposed_events, exposed_total) - Fraction(reference_events, reference_total)

    precision = len(reported.partition('.')[2]) if '.' in reported else 0
    quantum = Decimal(1).scaleb(-precision)
    tolerance = quantum / Decimal(2)
    try:
        reported_decimal = Decimal(reported)
        with localcontext() as ctx:
            ctx.prec = 50
            exact_decimal = Decimal(exact.numerator) / Decimal(exact.denominator)
            rounded = exact_decimal.quantize(quantum, rounding=ROUND_HALF_UP)
            rounded_text = format(rounded, 'f')
    except (InvalidOperation, ZeroDivisionError):
        return {'status': 'UNSUPPORTED', 'reason': 'ARITHMETIC_DOMAIN_ERROR', 'candidate': None}
    # Match the declared ROUND_HALF_UP policy exactly. A value on a half-unit
    # boundary rounds away from zero and is not accepted on both sides.
    if reported_decimal == rounded:
        return {
            'status': 'CONSISTENT_WITH_ROUNDING',
            'reason': None,
            'measure': measure,
            'exact_numerator': str(exact.numerator),
            'exact_denominator': str(exact.denominator),
            'recomputed_at_display_precision': rounded_text,
            'display_precision': precision,
            'tolerance': format(tolerance, 'f'),
            'candidate': None,
        }
    return {
        'status': 'ARITHMETIC_CANDIDATE',
        'reason': None,
        'measure': measure,
        'exact_numerator': str(exact.numerator),
        'exact_denominator': str(exact.denominator),
        'recomputed_at_display_precision': rounded_text,
        'display_precision': precision,
        'tolerance': format(tolerance, 'f'),
        'candidate': {
            'reported': reported,
            'difference': format(abs(reported_decimal - exact_decimal), '.12f').rstrip('0').rstrip('.'),
        },
    }
