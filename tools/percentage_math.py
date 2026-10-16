"""Exact arithmetic helpers for source-grounded count/percentage review.

These helpers do not infer a table's population scope or source convention.
Callers must supply a denominator justified by separate source evidence.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re
from typing import Any, Iterable

MAX_DISPLAY_PRECISION = 6
MAX_COUNT = 999_999_999
_DECIMAL_TEXT = re.compile(r"^\d+(?:\.\d+)?$")


def _validate_denominator(denominator: int) -> None:
    if (not isinstance(denominator, int) or isinstance(denominator, bool)
            or denominator <= 0 or denominator > MAX_COUNT):
        raise ValueError("Denominator must be a positive supported integer")


def _validate_precision(display_precision: int) -> None:
    if (not isinstance(display_precision, int) or isinstance(display_precision, bool)
            or not 0 <= display_precision <= MAX_DISPLAY_PRECISION):
        raise ValueError("Display precision must be between zero and six")


def _displayed_percentage(value: str, display_precision: int) -> Fraction:
    _validate_precision(display_precision)
    if not isinstance(value, str) or not _DECIMAL_TEXT.fullmatch(value):
        raise ValueError("Reported percentage must be plain nonnegative decimal text")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Reported percentage must be decimal text") from exc
    observed_precision = len(value.partition(".")[2]) if "." in value else 0
    if observed_precision != display_precision:
        raise ValueError("Display precision must match the printed percentage")
    if not decimal.is_finite() or decimal > 100:
        raise ValueError("Reported percentage must be between zero and 100")
    return Fraction(decimal)


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _format_scaled_integer(value: int, precision: int) -> str:
    scale = 10 ** precision
    whole, fractional = divmod(value, scale)
    return str(whole) if precision == 0 else f"{whole}.{fractional:0{precision}d}"


def _round_half_up(value: Fraction, precision: int) -> str:
    """Round a nonnegative exact rational to fixed decimal places, half up."""
    scaled = value * (10 ** precision)
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    if remainder * 2 >= scaled.denominator:
        quotient += 1
    return _format_scaled_integer(quotient, precision)


def compatible_integer_numerator_range(
    denominator: int, reported_percent: str, display_precision: int
) -> dict[str, Any]:
    """Find integer numerators that half-up round to a displayed percentage.

    For nonnegative percentages, the lower half-unit boundary is inclusive
    and the upper boundary is exclusive. The result does not assert that a
    table count is weighted, unweighted, or in the same population scope.
    """
    _validate_denominator(denominator)
    displayed = _displayed_percentage(reported_percent, display_precision)
    half_unit = Fraction(1, 2 * 10 ** display_precision)
    lower_count = (displayed - half_unit) * denominator / 100
    upper_count = (displayed + half_unit) * denominator / 100
    minimum = max(0, _ceil(lower_count))
    maximum = min(denominator, _ceil(upper_count) - 1)
    feasible = minimum <= maximum
    return {
        "denominator": denominator,
        "reported_percent": reported_percent,
        "display_precision": display_precision,
        "rounding_rule": "nonnegative decimal half-up",
        "integer_numerator_feasible": feasible,
        "minimum_compatible_numerator": minimum if feasible else None,
        "maximum_compatible_numerator": maximum if feasible else None,
    }


def compatible_integer_denominator_range(
    numerator: int, reported_percent: str, display_precision: int
) -> dict[str, Any]:
    """Find supported integer denominators compatible with a printed ratio.

    The lower half-unit boundary is inclusive and the upper boundary is
    exclusive under nonnegative half-up rounding. The supported denominator
    range is bounded by ``MAX_COUNT`` to match the existing audit operand cap.
    """
    if (not isinstance(numerator, int) or isinstance(numerator, bool)
            or numerator < 0 or numerator > MAX_COUNT):
        raise ValueError("Numerator must be a supported nonnegative integer")
    displayed = _displayed_percentage(reported_percent, display_precision)
    half_unit = Fraction(1, 2 * 10 ** display_precision)
    lower_percent = displayed - half_unit
    upper_percent = displayed + half_unit

    if numerator == 0:
        feasible = displayed == 0
        minimum = 1 if feasible else None
        maximum = MAX_COUNT if feasible else None
    elif upper_percent <= 0:
        feasible = False
        minimum = maximum = None
    else:
        minimum = (Fraction(100 * numerator, 1) / upper_percent).__floor__() + 1
        minimum = max(numerator, minimum)
        maximum = (
            (Fraction(100 * numerator, 1) / lower_percent).__floor__()
            if lower_percent > 0 else MAX_COUNT
        )
        maximum = min(MAX_COUNT, maximum)
        feasible = minimum <= maximum
        if not feasible:
            minimum = maximum = None
    return {
        "numerator": numerator,
        "reported_percent": reported_percent,
        "display_precision": display_precision,
        "rounding_rule": "nonnegative decimal half-up",
        "integer_denominator_feasible": feasible,
        "minimum_compatible_denominator": minimum,
        "maximum_compatible_denominator": maximum,
        "maximum_supported_denominator": MAX_COUNT,
    }


def independently_rounded_components(
    counts: Iterable[int], denominator: int, display_precision: int
) -> dict[str, Any]:
    """Round component percentages separately and compare their sum.

    Component counts are not assumed to be disjoint or exhaustive. The
    returned count-sum and denominator-equality fields let reviewers decide
    whether an aggregate comparison is meaningful for their source table.
    """
    _validate_denominator(denominator)
    _validate_precision(display_precision)
    values = list(counts)
    if not values:
        raise ValueError("At least one component count is required")
    if any(
        not isinstance(count, int) or isinstance(count, bool)
        or count < 0 or count > MAX_COUNT
        for count in values
    ):
        raise ValueError("Component counts must be supported nonnegative integers")

    component_percentages = [
        _round_half_up(Fraction(count * 100, denominator), display_precision)
        for count in values
    ]
    scale = 10 ** display_precision
    displayed_sum_scaled = sum(
        int(Decimal(value) * scale) for value in component_percentages
    )
    count_sum = sum(values)
    aggregate_rounded = _round_half_up(
        Fraction(count_sum * 100, denominator), display_precision
    )
    return {
        "denominator": denominator,
        "display_precision": display_precision,
        "rounding_rule": "nonnegative decimal half-up",
        "component_counts": values,
        "component_rounded_percentages": component_percentages,
        "component_counts_sum": count_sum,
        "component_counts_sum_equals_denominator": count_sum == denominator,
        "independently_rounded_percentages_sum": _format_scaled_integer(
            displayed_sum_scaled, display_precision
        ),
        "rounded_percentage_of_component_count_sum": aggregate_rounded,
    }
