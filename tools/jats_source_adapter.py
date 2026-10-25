"""Bridge the current bounded JATS detector to the preserved canonical source model.

XML element spans are NOT literal-quote byte offsets. Detector scope decisions
remain proposals; exact arithmetic replay does not establish scientific truth.
This module is a checkout tool, outside the trusted certificate allowlist.
"""
from __future__ import annotations

from dataclasses import asdict
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any

from researchwitness.paper_document import NumericAssertion, SourceAnchor

ADAPTER_VERSION = 'rw-jats-source-adapter.v1'
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_EXCERPT_CHARS = 4096
RESOLVED = frozenset({'arithmetic_match', 'arithmetic_mismatch_candidate'})
STATUSES = RESOLVED | {'scope_ambiguous', 'rounding_ambiguous'}
INTERPRETATION = {
    'schema_version': 'rw-jats-interpretation.v1',
    'mechanism': 'explicit_count_denominator_percentage',
    'source': 'original_utf8_jats_no_declarations',
    'anchor': 'original_xml_element_span_with_normalized_text',
    'rounding': 'half_up_only_when_detector_scope_is_resolved',
    'uncertainty': 'preserve_scope_rounding_and_conditional_abstentions',
    'scope': 'arithmetic_candidate_not_scientific_error',
}


class SourceAdapterError(ValueError):
    """A fixed diagnostic, without source content or local path disclosure."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SourceAdapterError(code)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def commitment(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def interpretation_sha256() -> str:
    return commitment(INTERPRETATION)


def component_id(source_sha256: str, start: int, end: int,
                character_start: int, character_end: int) -> str:
    return 'src-' + commitment({
        'source_sha256': source_sha256, 'byte_start': start, 'byte_end': end,
        'normalized_character_start': character_start,
        'normalized_character_end': character_end,
    })


def replay_percentage(numerator: int, denominator: int, reported: str,
                      precision: int) -> dict[str, Any]:
    """Independent Fraction/integer replay, unaffected by Decimal contexts."""
    _require(type(numerator) is int and type(denominator) is int and
             0 <= numerator <= denominator <= 10**12 and denominator > 0,
             'RATIO_OPERANDS')
    _require(type(precision) is int and 0 <= precision <= 6, 'DISPLAY_PRECISION')
    _require(type(reported) is str and len(reported) <= 12 and
             re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,6})?', reported) is not None,
             'REPORTED_PERCENT')
    _require(len(reported.partition('.')[2]) == precision and Fraction(reported) <= 100,
             'REPORTED_PRECISION_OR_RANGE')
    scale = 10**precision
    whole, remainder = divmod(100 * numerator * scale, denominator)
    rounded = whole + (2 * remainder >= denominator)
    text = str(rounded) if precision == 0 else f'{rounded // scale}.{rounded % scale:0{precision}d}'
    exact = Fraction(100 * numerator, denominator)
    return {
        'numerator': numerator, 'denominator': denominator,
        'reported_percent': reported, 'display_precision': precision,
        'rounded_percent': text,
        'exact_numerator': str(exact.numerator), 'exact_denominator': str(exact.denominator),
        'arithmetic_matches': Fraction(reported) == Fraction(rounded, scale),
    }


def bounded_report_bytes(report: dict[str, Any]) -> bytes:
    """Bound serialization while iterating, rather than after a giant byte string."""
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    parts: list[bytes] = []
    size = 1
    for part in encoder.iterencode(report):
        encoded = part.encode('ascii')
        size += len(encoded)
        _require(size <= MAX_REPORT_BYTES, 'ADAPTER_OUTPUT_LIMIT')
        parts.append(encoded)
    return b''.join(parts) + b'\n'


def _index_nodes(root: Any, detector: Any) -> dict[tuple[int, int], tuple[Any, str]]:
    index: dict[tuple[int, int], tuple[Any, str]] = {}
    stack = [(root, '/article[1]')]
    while stack:
        node, path = stack.pop()
        _require(len(path) <= MAX_EXCERPT_CHARS, 'ELEMENT_PATH_LIMIT')
        key = (node.byte_start, node.byte_end)
        _require(key not in index, 'DUPLICATE_ELEMENT_SPAN')
        index[key] = (node, path)
        counts: dict[str, int] = {}
        children = []
        for child in node.children:
            name = detector._local_name(child.tag)
            counts[name] = counts.get(name, 0) + 1
            children.append((child, f'{path}/{name}[{counts[name]}]'))
        stack.extend(reversed(children))
    return index


def _check_evidence(value: Any, index: dict, detector: Any) -> None:
    """Check every emitted element/excerpt binding, including denominator notes."""
    if isinstance(value, dict):
        if 'byte_start' in value or 'byte_end' in value:
            start, end = value.get('byte_start'), value.get('byte_end')
            _require(type(start) is int and type(end) is int and (start, end) in index,
                     'EVIDENCE_ELEMENT_SPAN')
            node = index[(start, end)][0]
            text = detector._text(node)
            if 'quote' in value:
                quote = value['quote']
                _require(type(quote) is str and quote in text, 'EVIDENCE_EXCERPT_MISMATCH')
            if 'cell_quote' in value:
                quote = value['cell_quote']
                _require(type(quote) is str and
                         (text.startswith(quote) if value.get('cell_quote_truncated') is True else text == quote),
                         'CELL_EXCERPT_MISMATCH')
        for item in value.values():
            _check_evidence(item, index, detector)
    elif isinstance(value, list):
        for item in value:
            _check_evidence(item, index, detector)


def _check_operands(result: dict, text: str, lo: int, hi: int,
                    index: dict, detector: Any) -> None:
    """Bind stated operands to actual cell text; never resolve denominator scope."""
    fragment = next((f for f in detector._fragments(text) if f is not None and
                     (f['character_start'], f['character_end']) == (lo, hi)), None)
    _require(fragment is not None or (lo == 0 and hi == len(text)), 'COMPONENT_IDENTITY')
    numeric = fragment['numeric_quote'] if fragment else text
    match = (detector._COUNT_RATIO_PERCENT_RE.fullmatch(numeric) or
             detector._COUNT_PERCENT_RE.fullmatch(numeric))
    if match:
        _require(int(match.group('count').replace(',', '')) == result['numerator'] and
                 match.group('percent') == result['reported_percent'], 'CELL_OPERAND_MISMATCH')
    else:
        percent = detector._PERCENT_ONLY_RE.fullmatch(text)
        evidence = result['evidence'].get('count_evidence')
        _require(percent is not None and evidence is not None, 'COUNT_EVIDENCE_MISSING')
        node = index[(evidence['byte_start'], evidence['byte_end'])][0]
        count = detector._COUNT_ONLY_RE.fullmatch(detector._text(node))
        _require(count is not None and int(count.group('count').replace(',', '')) == result['numerator']
                 and percent.group('percent') == result['reported_percent'], 'COLUMN_OPERAND_MISMATCH')
    if result['status'] not in RESOLVED:
        return
    supported = False
    for fact in result['evidence']['denominator_sources']:
        if fact['value'] != result['denominator']:
            continue
        evidence = fact['evidence']
        node = index[(evidence['byte_start'], evidence['byte_end'])][0]
        quote = detector._text(node)
        values = {int(m.group('value').replace(',', ''))
                  for m in detector._DENOMINATOR_RE.finditer(quote)}
        role = evidence['role']
        if role == 'cell_ratio_denominator':
            ratio = detector._COUNT_RATIO_PERCENT_RE.fullmatch(numeric)
            if ratio:
                values.add(int(ratio.group('denominator').replace(',', '')))
        elif role == 'row_denominator_cell':
            count = detector._COUNT_ONLY_RE.fullmatch(quote)
            if count:
                values.add(int(count.group('count').replace(',', '')))
        elif role == 'table_total_row':
            total = detector._FULL_WIDTH_TOTAL_ROW_RE.fullmatch(quote)
            if total:
                values.add(int(total.group('count').replace(',', '')))
        supported |= result['denominator'] in values
    _require(supported, 'DENOMINATOR_TOKEN_MISMATCH')


def _map_result(result: dict, index: dict, detector: Any, source: bytes,
                source_hash: str, position: int) -> dict[str, Any]:
    evidence = result['evidence']
    _require(evidence['source_sha256'] == source_hash, 'SOURCE_HASH_MISMATCH')
    start, end = evidence['byte_start'], evidence['byte_end']
    _require(type(start) is int and type(end) is int and (start, end) in index,
             'CELL_ELEMENT_SPAN')
    node, path = index[(start, end)]
    text = detector._text(node)
    lo, hi = evidence['normalized_character_start'], evidence['normalized_character_end']
    _require(type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(text), 'COMPONENT_SPAN')
    _require(len(text) <= MAX_EXCERPT_CHARS, 'CELL_TEXT_LIMIT')
    if 'relationship_quote' in evidence:
        _require(evidence['relationship_quote'] == text[lo:hi], 'COMPONENT_EXCERPT_MISMATCH')
    _check_evidence(result, index, detector)
    target = component_id(source_hash, start, end, lo, hi)
    identifier = 'rel-' + commitment({
        'version': 'rw-percentage-relation.v1', 'kind': 'count_percentage',
        'component_id': target, 'numerator': result['numerator'],
        'denominator': result['denominator'], 'scope': result['denominator_scope'],
        'denominator_sources': evidence['denominator_sources'],
        'conditional': result.get('conditional_calculation'),
    })
    _check_operands(result, text, lo, hi, index, detector)
    status = result['status']
    _require(status in STATUSES, 'DETECTOR_STATUS')
    anchor = SourceAnchor('source.xml', source_hash, 'jats_xml', path, text, start, end)
    assertion = NumericAssertion(
        value=result['reported_percent'], unit='percent', statistic_type='count_percentage',
        numerator=str(result['numerator']),
        denominator=None if result['denominator'] is None else str(result['denominator']),
        population=None, group=None, outcome=None, timepoint=None, adjustment_status=None,
        source_anchor=anchor,
        structural_provenance=(f'denominator_scope:{result["denominator_scope"]}',
                               f'legacy_result_sha256:{commitment(result)}'),
    )
    conditional_replay = None
    conditional = result.get('conditional_calculation')
    if conditional is not None:
        try:
            conditional_replay = {
                'unconditional': False, 'assumption': conditional.get('assumption'),
                'arithmetic': replay_percentage(result['numerator'], conditional['denominator'],
                                                result['reported_percent'], result['display_precision']),
            }
        except (ValueError, TypeError, KeyError):
            conditional_replay = {'unconditional': False, 'status': 'unsupported'}
    certificate = None
    certificate_status = 'not_checked'
    diagnostic = result['reason']
    if status in RESOLVED:
        try:
            arithmetic = replay_percentage(result['numerator'], result['denominator'],
                                           result['reported_percent'], result['display_precision'])
            _require(arithmetic['rounded_percent'] == result['contract_expected_percent'] and
                     arithmetic['arithmetic_matches'] == (status == 'arithmetic_match'),
                     'ARITHMETIC_REPLAY_DISAGREEMENT')
            certificate_status = 'accepted'
            certificate = {
                'schema_version': 'rw-jats-arithmetic-replay.v1',
                'relation_id': identifier, 'source_sha256': source_hash,
                'legacy_result_sha256': commitment(result),
                'element_sha256': sha256(source[start:end]).hexdigest(),
                'arithmetic': arithmetic,
                'scope': 'supplied_source_mapped_operands_only',
            }
        except (SourceAdapterError, ValueError, TypeError):
            certificate_status = 'rejected'
            diagnostic = 'ARITHMETIC_REPLAY_REJECTED'
            certificate = {'schema_version': 'rw-jats-arithmetic-replay.v1',
                           'relation_id': identifier, 'source_sha256': source_hash,
                           'legacy_result_sha256': commitment(result), 'rejected': True}
    return {
        'relation_id': identifier, 'target_id': target, 'legacy_result_index': position,
        'assertion': asdict(assertion), 'detector_status': status, 'reason': diagnostic,
        'alarm_emitted': status == 'arithmetic_mismatch_candidate',
        'normalized_character_start': lo, 'normalized_character_end': hi,
        'element_sha256': sha256(source[start:end]).hexdigest(),
        'conditional_replay': conditional_replay,
        'certificate_status': certificate_status, 'certificate': certificate,
        'certificate_sha256': None if certificate is None else commitment(certificate),
        'source_correspondence': 'detector_element_mapping_not_independent_adjudication',
    }


def audit_jats_source(source: bytes) -> dict[str, Any]:
    # Lazy import keeps pure replay/model use independent of checkout source tools.
    from tools import jats_percentage_audit as detector

    report = detector.audit_jats_percentage_tables(source)
    source_hash = sha256(source).hexdigest()
    _require(report['source_sha256'] == source_hash, 'SOURCE_HASH_MISMATCH')
    # Same bounded original-byte parser, not the legacy normalizing parser. A second
    # pass reconstructs exact element identity without modifying detector semantics.
    index = _index_nodes(detector._parse_jats(source), detector)
    relations = [_map_result(item, index, detector, source, source_hash, i)
                 for i, item in enumerate(report['results'])]
    _require(len({r['relation_id'] for r in relations}) == len(relations), 'DUPLICATE_RELATION_ID')
    return {
        'schema_version': ADAPTER_VERSION, 'source_sha256': source_hash,
        'interpretation_sha256': interpretation_sha256(),
        'anchor_semantics': 'original_xml_element_span_not_literal_quote_byte_offset',
        'unknown_context_fields': 'left_null_not_inferred',
        'detector_report': report, 'relations': relations,
        'scientific_error_established': False,
        'scope': 'canonical_source_mapping_and_arithmetic_replay_only',
    }
