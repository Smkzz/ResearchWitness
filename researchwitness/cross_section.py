"""Strict identity matching for repeated numeric assertions across sections."""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from itertools import combinations
import re
from typing import Any

from .paper_document import NumericAssertion


def _precision_interval(value: str) -> tuple[Decimal, Decimal] | None:
    if not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value):
        return None
    try:
        number = Decimal(value)
        places = len(value.partition('.')[2]) if '.' in value else 0
        tolerance = Decimal(5).scaleb(-(places + 1))
        return number - tolerance, number + tolerance
    except InvalidOperation:
        return None


def compare_numeric_assertions(assertions: tuple[NumericAssertion, ...] | list[NumericAssertion]) -> dict[str, Any]:
    """Compare only complete identities; incomplete identity yields scope notes."""
    candidates: list[dict[str, Any]] = []
    possible_scope_differences: list[dict[str, Any]] = []
    for left, right in combinations(assertions, 2):
        left_key = left.identity_key
        right_key = right.identity_key
        left_interval = _precision_interval(left.value)
        right_interval = _precision_interval(right.value)
        if left_interval is None or right_interval is None or left.value == right.value:
            continue
        if not (left_interval[1] < right_interval[0] or right_interval[1] < left_interval[0]):
            continue
        if left_key is not None and left_key == right_key:
            if left_interval[1] < right_interval[0] or right_interval[1] < left_interval[0]:
                candidates.append({
                    'status': 'CANDIDATE_ANOMALY',
                    'type': 'CROSS_SECTION_NUMERIC_CONTRADICTION',
                    'identity': list(left_key),
                    'values': [left.value, right.value],
                    'source_anchors': [asdict(left.source_anchor), asdict(right.source_anchor)],
                    'interpretation': (
                        'Values with a complete matching identity differ beyond both displayed precision intervals.'
                    ),
                    'required_review': (
                        'Check source versions, table/prose scope, and the underlying analysis before drawing a conclusion.'
                    ),
                })
            continue
        dimensions = (
            'population', 'group', 'outcome', 'statistic_type', 'timepoint', 'unit', 'adjustment_status',
        )
        left_values = tuple(getattr(left, name) for name in dimensions)
        right_values = tuple(getattr(right, name) for name in dimensions)
        known_equal = [i for i, (a, b) in enumerate(zip(left_values, right_values)) if a and b and a.casefold() == b.casefold()]
        differing_known = [i for i, (a, b) in enumerate(zip(left_values, right_values))
                           if a and b and a.casefold() != b.casefold()]
        missing_dimensions = [i for i, (a, b) in enumerate(zip(left_values, right_values)) if not a or not b]
        if len(known_equal) >= 5 and not differing_known and 1 <= len(missing_dimensions) <= 2:
            possible_scope_differences.append({
                'status': 'POSSIBLE_SCOPE_DIFFERENCE',
                'values': [left.value, right.value],
                'unresolved_dimensions': [dimensions[index] for index in missing_dimensions],
                'source_anchors': [asdict(left.source_anchor), asdict(right.source_anchor)],
                'interpretation': 'The assertions are numerically different but lack enough shared identity to compare as a contradiction.',
            })
    return {
        'candidates': candidates,
        'possible_scope_differences': possible_scope_differences,
        'comparisons': len(candidates) + len(possible_scope_differences),
    }
