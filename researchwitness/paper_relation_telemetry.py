"""Deterministic relation identities and terminal-status accounting."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from typing import Any, Iterable, Mapping


RELATION_STATUSES = (
    'NOT_APPLICABLE',
    'ELIGIBLE_CHECKED_MATCH',
    'ELIGIBLE_CHECKED_MISMATCH',
    'INCOMPLETE',
    'UNSUPPORTED',
)

_REASON_PRECEDENCE = (
    'TABLE_STRUCTURE_UNSUPPORTED',
    'SOURCE_SCOPE_AMBIGUOUS',
    'CONFLICTING_HEADER_DENOMINATORS',
    'LOCAL_ROW_DENOMINATOR',
    'FOOTNOTE_SCOPE_UNRESOLVED',
    'WEIGHTED_RESULT',
    'ADJUSTED_RESULT',
    'MISSINGNESS_CHANGES_DENOMINATOR',
    'MULTIPLE_RESPONSE',
    'CATEGORY_OVERLAP_RELEVANT_TO_RELATION',
    'GROUPED_INTEGER_FORMAT_UNSUPPORTED',
    'DECIMAL_SEPARATOR_UNSUPPORTED',
    'MALFORMED_NUMERIC_TOKEN',
    'OPERANDS_OUTSIDE_PROPORTION_DOMAIN',
    'DENOMINATOR_NOT_EXPLICIT',
    'PERCENT_UNIT_NOT_EXPLICIT',
    'CANDIDATE_LIMIT',
)
_REASON_RANK = {reason: index for index, reason in enumerate(_REASON_PRECEDENCE)}


def relation_id(
    detector_id: str,
    contract_version: str,
    source_sha256: str,
    element_path: str,
    relation_slot: str = '0',
) -> str:
    """Return an ID bound to source bytes and the exact source cell path."""
    fields = (detector_id, contract_version, source_sha256, element_path, relation_slot)
    return sha256('\0'.join(fields).encode('utf-8')).hexdigest()


def ordered_reasons(reasons: Iterable[str]) -> list[str]:
    """Deduplicate reasons and order them by the frozen canonical precedence."""
    unique = set(reasons)
    return sorted(unique, key=lambda reason: (_REASON_RANK.get(reason, len(_REASON_RANK)), reason))


def terminal_relation(
    *,
    relation_id_value: str,
    relation_type: str,
    detector_id: str,
    contract_version: str,
    table_key: str,
    source_anchor: Mapping[str, Any],
    status: str,
    reasons: Iterable[str] = (),
    **details: Any,
) -> dict[str, Any]:
    if status not in RELATION_STATUSES:
        raise ValueError(f'unknown relation terminal status: {status}')
    ordered = ordered_reasons(reasons)
    if status in ('INCOMPLETE', 'UNSUPPORTED') and not ordered:
        raise ValueError('skipped percentage relations require a primary reason')
    if status not in ('INCOMPLETE', 'UNSUPPORTED') and ordered:
        raise ValueError('only skipped percentage relations may have skip reasons')
    record: dict[str, Any] = {
        'relation_id': relation_id_value,
        'relation_type': relation_type,
        'detector_id': detector_id,
        'contract_version': contract_version,
        'table_key': table_key,
        'status': status,
        'primary_skip_reason': ordered[0] if ordered else None,
        'secondary_skip_reasons': ordered[1:],
        'source_anchor': dict(source_anchor),
    }
    record.update(details)
    return record


def summarize_relations(relations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(relations)
    ids = [record.get('relation_id') for record in records]
    if any(not isinstance(item, str) or not item for item in ids):
        raise ValueError('every percentage relation must have a nonempty relation_id')
    if len(ids) != len(set(ids)):
        raise ValueError('percentage relation identities must be unique')
    statuses = Counter(record.get('status') for record in records)
    if any(status not in RELATION_STATUSES for status in statuses):
        raise ValueError('percentage relation contains an unknown terminal status')
    counts = {status: statuses.get(status, 0) for status in RELATION_STATUSES}
    skip_reasons: Counter[str] = Counter()
    secondary_reasons: Counter[str] = Counter()
    for record in records:
        status = record['status']
        primary = record.get('primary_skip_reason')
        secondary = record.get('secondary_skip_reasons')
        if status in ('INCOMPLETE', 'UNSUPPORTED'):
            if not isinstance(primary, str) or not primary:
                raise ValueError('every skipped percentage relation needs exactly one primary reason')
            if not isinstance(secondary, list) or any(not isinstance(reason, str) for reason in secondary):
                raise ValueError('secondary skip reasons must be a list of strings')
            if primary in secondary or len(secondary) != len(set(secondary)):
                raise ValueError('skip reasons must be distinct')
            skip_reasons[primary] += 1
            secondary_reasons.update(secondary)
        elif primary is not None or secondary:
            raise ValueError('checked or not-applicable relations cannot carry skip reasons')
    checked = counts['ELIGIBLE_CHECKED_MATCH'] + counts['ELIGIBLE_CHECKED_MISMATCH']
    skipped = counts['INCOMPLETE'] + counts['UNSUPPORTED']
    if sum(counts.values()) != len(records):
        raise ValueError('percentage relation terminal statuses do not partition potential relations')
    if sum(skip_reasons.values()) != skipped:
        raise ValueError('primary skip reasons do not partition skipped percentage relations')
    return {
        'potential_relations': len(records),
        'applicable_relations': len(records) - counts['NOT_APPLICABLE'],
        'eligible_relations': checked,
        'checked_matches': counts['ELIGIBLE_CHECKED_MATCH'],
        'checked_mismatches': counts['ELIGIBLE_CHECKED_MISMATCH'],
        'checked_relations': checked,
        'incomplete_relations': counts['INCOMPLETE'],
        'unsupported_relations': counts['UNSUPPORTED'],
        'skipped_relations': skipped,
        'status_counts': counts,
        'primary_skip_reason_counts': dict(sorted(skip_reasons.items())),
        'secondary_skip_reason_counts_overlapping': dict(sorted(secondary_reasons.items())),
        'accounting_invariant': (
            len(records) == sum(counts.values())
            and skipped == sum(skip_reasons.values())
            and checked == counts['ELIGIBLE_CHECKED_MATCH'] + counts['ELIGIBLE_CHECKED_MISMATCH']
        ),
    }
