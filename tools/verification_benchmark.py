"""Offline DEVELOPMENT receipt scorer, not a verifier or sealed-evaluation runner.

Registry, protocol and run are separately supplied, externally pinned inputs.
Hashes bind declarations; they do not authenticate labels, scientific truth,
source correspondence, certificates, actual resource use or family independence.
No supplied code, URL, command or model is executed. Initial scope: one terminal
receipt per scheduled work, without retries or protected/confirmatory material.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from tools.offline_files import read_regular

MAX_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 16
MAX_NODES = 200_000
MAX_WORKS = 10_000
MAX_INTEGER = 2**53 - 1
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z', re.ASCII)
HASH = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
STATES = frozenset({
    'completed', 'abstained', 'failed', 'timeout', 'unsupported',
    'source_unavailable', 'budget_exceeded', 'not_attempted',
})
REGISTRY_VERSION = 'rw-development-registry.v1'
PROTOCOL_VERSION = 'rw-development-protocol.v1'
RUN_VERSION = 'rw-development-run.v1'
REPORT_VERSION = 'rw-development-score.v1'


class BenchmarkError(ValueError):
    """Stable diagnostic code; never interpolate source or private input text."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise BenchmarkError(code)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def commitment(value: Any) -> str:
    """SHA-256 of canonical JSON, including LF. Array order is significant."""
    return sha256(canonical_bytes(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _integer(text: str) -> int:
    require(len(text) <= 17, 'INTEGER_OUT_OF_BOUNDS')
    value = int(text)
    require(abs(value) <= MAX_INTEGER, 'INTEGER_OUT_OF_BOUNDS')
    return value


def _reject_number(_text: str) -> None:
    raise BenchmarkError('NON_INTEGER_JSON_NUMBER')


def parse_document(data: bytes) -> dict[str, Any]:
    require(type(data) is bytes and len(data) <= MAX_BYTES, 'INPUT_BYTE_LIMIT')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise BenchmarkError('INVALID_UTF8') from exc
    depth = 0
    in_string = escaped = False
    # Bound depth before json.loads allocates its nested result. Brackets within
    # strings are data, not nesting. JSON syntax itself is validated below.
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in '[{':
            depth += 1
            require(depth <= MAX_DEPTH, 'INPUT_DEPTH_LIMIT')
        elif character in ']}':
            depth -= 1
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                              parse_float=_reject_number, parse_constant=_reject_number)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise BenchmarkError('INVALID_JSON') from exc
    require(type(document) is dict, 'ROOT_MUST_BE_OBJECT')
    stack = [document]
    count = 0
    while stack:
        value = stack.pop()
        count += 1
        require(count <= MAX_NODES, 'INPUT_NODE_LIMIT')
        if isinstance(value, dict):
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str):
            require(len(value) <= 4096, 'INPUT_STRING_LIMIT')
    return document


def _object(value: Any, keys: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == set(keys.split()), 'OBJECT_FIELDS')
    return value


def _enum(value: Any, options: set[str] | frozenset[str]) -> str:
    require(type(value) is str and value in options, 'ENUM_VALUE')
    return value


def _id(value: Any) -> str:
    require(type(value) is str and ID.fullmatch(value) is not None, 'INVALID_ID')
    return value


def _hash(value: Any) -> str:
    require(type(value) is str and HASH.fullmatch(value) is not None, 'INVALID_HASH')
    return value


def _count(value: Any) -> int:
    require(type(value) is int and 0 <= value <= MAX_INTEGER, 'COUNTER_OUT_OF_BOUNDS')
    return value


def _bool(value: Any) -> bool:
    require(type(value) is bool, 'BOOL_REQUIRED')
    return value


def _array(value: Any) -> list[Any]:
    require(type(value) is list and len(value) <= MAX_WORKS, 'ARRAY_LIMIT')
    return value


def _fraction(numerator: int, denominator: int) -> dict[str, int] | None:
    return {'numerator': numerator, 'denominator': denominator} if denominator else None


def _registry(value: Any) -> dict[str, dict[str, Any]]:
    registry = _object(value, 'schema_version exposure label_basis works')
    require(registry['schema_version'] == REGISTRY_VERSION, 'REGISTRY_VERSION')
    exposure = _enum(registry['exposure'], {'synthetic', 'developer_exposed'})
    basis = _enum(registry['label_basis'], {'synthetic_construction', 'source_review'})
    require((exposure == 'synthetic') == (basis == 'synthetic_construction'), 'LABEL_BASIS')
    works: dict[str, dict[str, Any]] = {}
    families: dict[str, tuple[str, bool]] = {}
    sources: dict[str, str] = {}
    for work in _array(registry['works']):
        _object(work, 'work_id family_id source_sha256 interpretation_sha256 label eligible exclusion_reason target_id')
        work_id, family_id = _id(work['work_id']), _id(work['family_id'])
        require(work_id not in works, 'DUPLICATE_WORK')
        source = _hash(work['source_sha256'])
        _hash(work['interpretation_sha256'])
        label = _enum(work['label'], {'positive', 'negative', 'unresolved'})
        eligible = _bool(work['eligible'])
        reason = work['exclusion_reason']
        require(reason is None if eligible else type(reason) is str and ID.fullmatch(reason) is not None,
                'EXCLUSION_REASON')
        if label == 'positive':
            _id(work['target_id'])
        else:
            require(work['target_id'] is None, 'UNEXPECTED_TARGET')
        require(family_id not in families or families[family_id] == (label, eligible),
                'MIXED_FAMILY_CLASSIFICATION')
        require(source not in sources or sources[source] == family_id, 'SOURCE_CROSSES_FAMILIES')
        families[family_id] = (label, eligible)
        sources[source] = family_id
        works[work_id] = work
    require(bool(works), 'EMPTY_REGISTRY')
    return works


def score(registry: dict[str, Any], protocol: dict[str, Any], run: dict[str, Any], *,
          expected_registry_sha256: str, expected_protocol_sha256: str) -> dict[str, Any]:
    """Score supplied development receipts. The external pins must predate results.

    The caller must validate inputs via parse_document (the CLI does so). This
    function also revalidates canonical bytes to bound direct Python API inputs.
    """
    for document in (registry, protocol, run):
        try:
            parse_document(canonical_bytes(document))
        except (TypeError, OverflowError, RecursionError, ValueError) as exc:
            if isinstance(exc, BenchmarkError):
                raise
            raise BenchmarkError('INVALID_DOCUMENT') from exc
    _hash(expected_registry_sha256)
    _hash(expected_protocol_sha256)
    registry_hash, protocol_hash = commitment(registry), commitment(protocol)
    require(registry_hash == expected_registry_sha256, 'REGISTRY_PIN_MISMATCH')
    require(protocol_hash == expected_protocol_sha256, 'PROTOCOL_PIN_MISMATCH')
    works = _registry(registry)
    _object(protocol, 'schema_version registry_sha256 implementation_sha256 schedule max_elapsed_ms max_calls max_cost_micro_eur')
    require(protocol['schema_version'] == PROTOCOL_VERSION, 'PROTOCOL_VERSION')
    require(_hash(protocol['registry_sha256']) == registry_hash, 'REGISTRY_BINDING')
    _hash(protocol['implementation_sha256'])
    schedule = _array(protocol['schedule'])
    for work_id in schedule:
        _id(work_id)
    require(len(schedule) == len(set(schedule)) and set(schedule) == set(works), 'SCHEDULE_COVERAGE')
    limits = {name: _count(protocol[f'max_{name}']) for name in ('elapsed_ms', 'calls', 'cost_micro_eur')}
    require(limits['elapsed_ms'] > 0, 'ZERO_TIME_BUDGET')
    # This development slice must not normalize unauthorized chargeable runs.
    require(limits['cost_micro_eur'] == 0, 'PAID_RUN_NOT_SUPPORTED')
    _object(run, 'schema_version registry_sha256 protocol_sha256 implementation_sha256 results')
    require(run['schema_version'] == RUN_VERSION, 'RUN_VERSION')
    require(run['registry_sha256'] == registry_hash and run['protocol_sha256'] == protocol_hash,
            'RUN_BINDING')
    require(run['implementation_sha256'] == protocol['implementation_sha256'], 'IMPLEMENTATION_BINDING')
    results: dict[str, dict[str, Any]] = {}
    totals = dict.fromkeys(limits, 0)
    for record in _array(run['results']):
        _object(record, 'work_id source_sha256 interpretation_sha256 status alarm_emitted candidate_sha256 certificate_sha256 certificate_status source_correspondence target_id elapsed_ms calls cost_micro_eur')
        work_id = _id(record['work_id'])
        require(work_id in works and work_id not in results, 'UNKNOWN_OR_DUPLICATE_RESULT')
        work = works[work_id]
        require(record['source_sha256'] == work['source_sha256'] and
                record['interpretation_sha256'] == work['interpretation_sha256'], 'SOURCE_BINDING')
        status = _enum(record['status'], STATES)
        alarm = _bool(record['alarm_emitted'])
        certificate = _enum(record['certificate_status'], {'accepted', 'rejected', 'not_checked'})
        correspondence = _enum(record['source_correspondence'], {'supported', 'contradicted', 'unresolved'})
        if alarm:
            _hash(record['candidate_sha256'])
        else:
            require(record['candidate_sha256'] is None and record['target_id'] is None and
                    certificate == 'not_checked' and correspondence == 'unresolved', 'NO_ALARM_EVIDENCE')
        if certificate == 'not_checked':
            require(record['certificate_sha256'] is None, 'UNEXPECTED_CERTIFICATE')
        else:
            _hash(record['certificate_sha256'])
        if record['target_id'] is not None:
            _id(record['target_id'])
        over_budget = False
        for name, limit in limits.items():
            count = _count(record[name])
            totals[name] += count
            require(totals[name] <= MAX_INTEGER, 'TOTAL_OUT_OF_BOUNDS')
            over_budget |= count > limit
        require(record['cost_micro_eur'] == 0, 'PAID_RUN_NOT_SUPPORTED')
        require(not over_budget or status == 'budget_exceeded', 'BUDGET_STATE_MISMATCH')
        if status in {'not_attempted', 'source_unavailable'}:
            require(not alarm and all(record[name] == 0 for name in ('calls',)), 'UNATTEMPTED_ALARM')
        results[work_id] = record

    states: Counter[str] = Counter()
    families: dict[str, dict[str, Any]] = {}
    for work_id in sorted(works):
        work = works[work_id]
        record = results.get(work_id)
        state = record['status'] if record else 'missing'
        states[state] += 1
        family = families.setdefault(work['family_id'], {
            'label': work['label'], 'eligible': work['eligible'],
            'work_count': 0, 'alarm': False, 'recorded_detection': False,
            'coverage_complete': True,
        })
        family['work_count'] += 1
        family['coverage_complete'] &= state == 'completed'
        if record:
            family['alarm'] |= record['alarm_emitted']
            family['recorded_detection'] |= (
                state == 'completed' and record['alarm_emitted'] and
                record['certificate_status'] == 'accepted' and
                record['source_correspondence'] == 'supported' and
                work['label'] == 'positive' and record['target_id'] == work['target_id']
            )
    eligible = [family for family in families.values() if family['eligible']]
    positives = [family for family in eligible if family['label'] == 'positive']
    negatives = [family for family in eligible if family['label'] == 'negative']
    detections = sum(family['recorded_detection'] for family in positives)
    false_alarms = sum(family['alarm'] for family in negatives)
    unknown_negatives = sum(not family['alarm'] and not family['coverage_complete'] for family in negatives)
    unknown_positives = sum(not family['recorded_detection'] and not family['coverage_complete'] for family in positives)
    coverage_complete = all(family['coverage_complete'] for family in eligible)
    return {
        'schema_version': REPORT_VERSION,
        'classification': 'DEVELOPMENT_RECEIPT_ACCOUNTING_NOT_SCIENTIFIC_VALIDATION',
        'status': 'complete' if coverage_complete and len(results) == len(works) else 'incomplete',
        'source_and_certificate_validation': 'SUPPLIED_DECLARATIONS_NOT_REPLAYED',
        'independence': 'DECLARED_FAMILIES_NOT_AUTHENTICATED',
        'protected_evaluation_performed': False,
        'scientific_performance_established': False,
        'exposure': registry['exposure'],
        'commitments': {'registry': registry_hash, 'protocol': protocol_hash,
                        'run': commitment(run), 'implementation': protocol['implementation_sha256']},
        'ledger_complete': len(results) == len(works),
        'coverage_complete': coverage_complete,
        'work_counts': {'registered': len(works), 'receipts': len(results),
                        'missing': len(works) - len(results), 'states': dict(sorted(states.items()))},
        'family_counts': {'registered': len(families), 'eligible': len(eligible),
                          'positive': len(positives), 'negative': len(negatives),
                          'unresolved': sum(f['label'] == 'unresolved' for f in eligible),
                          'ineligible': len(families) - len(eligible),
                          'negative_incomplete_without_alarm': unknown_negatives},
        'rates': {
            'recorded_detection': _fraction(detections, len(positives)),
            'recorded_detection_completion_upper_bound': _fraction(detections + unknown_positives, len(positives)),
            'observed_false_alarm': _fraction(false_alarms, len(negatives)),
            'false_alarm_completion_upper_bound': _fraction(false_alarms + unknown_negatives, len(negatives)),
        },
        'resources_reported': totals,
        'limitations': [
            'Pins must be held separately before outcomes; no chronology is authenticated.',
            'No supplied certificate, source interpretation or label is independently verified here.',
            'Missing/failed/abstained works remain in registered family denominators.',
            'Completion bounds describe missing outcomes; they are not confidence intervals.',
            'No omitted or hidden retry can be detected without a trusted recording boundary.',
            'No statistical superiority test, sealed custody, live execution or provider call is performed.',
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('registry', 'protocol', 'run'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--expected-registry-sha256', required=True)
    parser.add_argument('--expected-protocol-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        documents = [parse_document(read_regular(getattr(args, name), MAX_BYTES))
                     for name in ('registry', 'protocol', 'run')]
        report = score(*documents, expected_registry_sha256=args.expected_registry_sha256,
                       expected_protocol_sha256=args.expected_protocol_sha256)
        sys.stdout.buffer.write(canonical_bytes(report))
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, BenchmarkError) else 'INPUT_IO_OR_FORMAT_ERROR'
        sys.stderr.buffer.write(canonical_bytes({'status': 'invalid', 'code': code}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
