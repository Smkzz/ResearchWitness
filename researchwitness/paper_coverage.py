"""Pure, bounded coverage accounting for source-aware paper screens.

This module summarizes supplied detector results. It does not infer that a
paper is error-free or that arbitrary error classes were exhaustively checked.
For table screens, the table outcome records supplied by the detector remain
authoritative; operand counts describe only the detector's recognized input
shape.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
import json
import re
from typing import Any

from .paper_document import PaperDocument, Table
from .paper_contracts import PERCENTAGE_CONTRACT_VERSION
from .paper_ratio import CELL_RATIO_SHAPE, check_jats_cell_ratio_percentages
from .table_arithmetic import (
    COUNT_PERCENT,
    COUNT_PERCENT_SHAPE,
    check_structured_table_percentages,
)
from .paper_relation_telemetry import relation_id, summarize_relations


_TABLE_STATUSES = frozenset({'ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE', 'NOT_APPLICABLE'})
_STRUCTURE_STATUSES = frozenset({'STRUCTURE_RELIABLE', 'TABLE_STRUCTURE_UNSUPPORTED'})
_MAX_TABLES = 1_000
_MAX_DETECTORS = 32
_MAX_REASONS = 16
_MAX_REASON_LENGTH = 200
_MAX_LABEL_LENGTH = 2_000
_MAX_PATH_LENGTH = 4_096
_MAX_CHECKED_CELLS = 100_000
_MAX_CANDIDATES = 256


def _nonnegative_integer(value: Any, name: str, maximum: int) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f'{name} must be an integer from 0 through {maximum}')
    return value


def _bounded_text(value: Any, name: str, maximum: int, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{name} must be text')
    value = value.strip()
    if not allow_empty and not value:
        raise ValueError(f'{name} must not be empty')
    return value[:maximum]


def _reasons(record: Mapping[str, Any]) -> tuple[list[str], bool]:
    raw = record.get('reasons', record.get('limitations', record.get('skip_reasons', [])))
    if raw is None:
        return [], False
    if not isinstance(raw, (list, tuple)):
        raise ValueError('detector reasons must be a list of strings')
    unique: list[str] = []
    truncated = False
    for item in raw:
        if isinstance(item, Mapping):
            reason_value = item.get('reason')
            row_index = item.get('row_index')
            if not isinstance(reason_value, str):
                raise ValueError('detector reason mappings must contain text in reason')
            item = (reason_value if row_index is None else
                    f'{reason_value} (row {row_index})')
        if not isinstance(item, str):
            raise ValueError('detector reasons must contain only strings')
        if len(item.strip()) > _MAX_REASON_LENGTH:
            truncated = True
        reason = _bounded_text(item, 'detector reason', _MAX_REASON_LENGTH, allow_empty=False)
        if reason not in unique:
            if len(unique) == _MAX_REASONS:
                truncated = True
                break
            unique.append(reason)
    return unique, truncated


def _detector_id(record: Mapping[str, Any]) -> str:
    raw = record.get('detector_id')
    if not isinstance(raw, str) or not raw.strip() or len(raw.strip()) > 100:
        raise ValueError('detector_id must be non-empty text of at most 100 characters')
    value = raw.strip()
    return value


def _status(record: Mapping[str, Any]) -> str:
    value = record.get('status', record.get('eligibility'))
    if value not in _TABLE_STATUSES:
        raise ValueError(f'unsupported detector coverage status: {value!r}')
    return value


def _potential_count_percent_cells(table: Table, detector_id: str) -> int:
    """Count the exact broad candidate shape used by a percentage detector."""
    if detector_id == 'jats_cell_ratio_percentage_recomputation':
        pattern = CELL_RATIO_SHAPE
    elif detector_id == 'table_percentage_recomputation':
        pattern = COUNT_PERCENT_SHAPE
    else:
        pattern = COUNT_PERCENT
    return sum(
        1
        for row in table.rows if row.row_group == 'tbody'
        for cell in row.cells
        if pattern.fullmatch(cell.raw_text)
    )


def _table_reference(table: Table) -> dict[str, str]:
    anchor = table.source_anchor
    source_sha256 = anchor.source_sha256
    element_path = anchor.element_path
    if not isinstance(source_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', source_sha256):
        raise ValueError('table source anchor must contain a lowercase SHA-256 hash')
    if (not isinstance(element_path, str) or not element_path
            or len(element_path) > _MAX_PATH_LENGTH):
        raise ValueError('table source element path must be non-empty and within the coverage limit')
    return {'source_sha256': source_sha256, 'element_path': element_path}


def _same_json_value(left: Any, right: Any) -> bool:
    """Compare serialized telemetry with source-derived JSON without bool/int aliasing."""
    try:
        return json.dumps(
            left, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
        ) == json.dumps(
            right, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError):
        return False


def _source_percentage_relations(
    document: PaperDocument,
    detector_id: str,
) -> dict[str, Mapping[str, Any]] | None:
    """Recompute v1.3 relations from the canonical parsed source before accepting telemetry."""
    evaluator = {
        'table_percentage_recomputation': check_structured_table_percentages,
        'jats_cell_ratio_percentage_recomputation': check_jats_cell_ratio_percentages,
    }.get(detector_id)
    if evaluator is None:
        return None
    try:
        record = evaluator(document)
        relations = record.get('relations')
        if not isinstance(relations, (list, tuple)):
            return None
        by_id: dict[str, Mapping[str, Any]] = {}
        for relation in relations:
            if not isinstance(relation, Mapping):
                return None
            relation_identifier = relation.get('relation_id')
            if not isinstance(relation_identifier, str) or relation_identifier in by_id:
                return None
            by_id[relation_identifier] = relation
        return by_id
    except Exception:
        # Invalid or unsupported source models cannot establish telemetry completeness.
        return None


def _table_model_summary(document: PaperDocument) -> dict[str, Any]:
    count = len(document.tables)
    if count > _MAX_TABLES:
        raise ValueError(f'paper document exceeds the {_MAX_TABLES}-table coverage limit')
    status_counts: dict[str, int] = {}
    for table in document.tables:
        status = table.structure_status
        if status not in _STRUCTURE_STATUSES:
            raise ValueError(f'unsupported table parser status: {status!r}')
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        'discovered': count,
        # Every table-wrap represented in PaperDocument has a Table model,
        # including models whose grid could not be made reliable.
        'parsed': count,
        'structure_reliable': status_counts.get('STRUCTURE_RELIABLE', 0),
        'structure_unsupported': status_counts.get('TABLE_STRUCTURE_UNSUPPORTED', 0),
        'parser_status_counts': dict(sorted(status_counts.items())),
    }


def _normalize_detector_results(
    detector_results: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if isinstance(detector_results, Mapping):
        records = [detector_results]
    else:
        try:
            records = []
            for record in detector_results:
                if len(records) == _MAX_DETECTORS:
                    raise ValueError(f'detector_results exceeds the {_MAX_DETECTORS}-detector limit')
                records.append(record)
        except TypeError as exc:
            raise ValueError('detector_results must be a result record or iterable of result records') from exc
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError('each detector result must be a mapping')
    records.sort(key=lambda item: _detector_id(item))
    detector_ids = [_detector_id(item) for item in records]
    if len(set(detector_ids)) != len(detector_ids):
        raise ValueError('detector result records must have unique detector_id values')
    return records


def _rollup_status(statuses: list[str], *, has_missing_results: bool = False) -> str:
    if has_missing_results or 'INCOMPLETE' in statuses:
        return 'INCOMPLETE'
    if 'UNSUPPORTED' in statuses and 'ELIGIBLE' in statuses:
        return 'INCOMPLETE'
    if 'ELIGIBLE' in statuses:
        return 'ELIGIBLE'
    if 'UNSUPPORTED' in statuses:
        return 'UNSUPPORTED'
    if statuses and all(status == 'NOT_APPLICABLE' for status in statuses):
        return 'NOT_APPLICABLE'
    return 'INCOMPLETE'


def _build_table_detector(document: PaperDocument, record: Mapping[str, Any]) -> dict[str, Any]:
    detector_id = _detector_id(record)
    raw_rows = record.get('tables')
    if not isinstance(raw_rows, (list, tuple)):
        raise ValueError(f'{detector_id} result must provide a tables list')
    if len(raw_rows) > _MAX_TABLES:
        raise ValueError(f'{detector_id} result exceeds the {_MAX_TABLES}-table limit')
    if any(not isinstance(item, Mapping) for item in raw_rows):
        raise ValueError(f'{detector_id} table results must be mappings')

    model_tables = list(document.tables)
    table_count = len(model_tables)
    result_count = len(raw_rows)
    matched_count = min(table_count, result_count)
    missing_count = max(0, table_count - result_count)
    extra_count = max(0, result_count - table_count)
    table_results: list[dict[str, Any]] = []
    table_statuses: list[str] = []
    status_counts: dict[str, int] = {}
    potential_operands = checked_operands = skipped_operands = candidate_items = 0
    tables_checked = tables_skipped = tables_with_candidates = 0
    candidate_counts_known = True
    percentage_detector = detector_id in {
        'table_percentage_recomputation', 'jats_cell_ratio_percentage_recomputation',
    }
    relation_records: list[Mapping[str, Any]] = []
    relation_table_results: list[tuple[Table, Mapping[str, Any]]] = []
    source_potentials: list[int] = []
    relation_arrays_complete = percentage_detector and result_count == table_count
    if extra_count:
        candidate_counts_known = False

    for index, table in enumerate(model_tables):
        source_potential = _potential_count_percent_cells(table, detector_id)
        source_potentials.append(source_potential)
        potential = source_potential
        candidate_findings_omitted: int | None = None
        if table.source_anchor.source_sha256 != document.source_sha256:
            raise ValueError('table source anchor hash differs from its PaperDocument source hash')
        if index < matched_count:
            result = raw_rows[index]
            if percentage_detector:
                relation_table_results.append((table, result))
                raw_relations = result.get('relations')
                if not isinstance(raw_relations, (list, tuple)) or any(
                    not isinstance(item, Mapping) for item in raw_relations
                ):
                    relation_arrays_complete = False
                else:
                    relation_records.extend(raw_relations)
                    if len(raw_relations) != result.get('potential_relations', -1):
                        relation_arrays_complete = False
            status = _status(result)
            result_table_id = result.get('table_id')
            if result_table_id is not None and result_table_id != table.table_id:
                raise ValueError(
                    f'{detector_id} result table order/identity differs at document table index {index}'
                )
            checked = _nonnegative_integer(
                result.get('checked_cells', result.get('checked_operands',
                    result.get('checked_objects', result.get('checked_rows', 0)))),
                f'{detector_id} checked cell count', _MAX_CHECKED_CELLS,
            )
            potential = _nonnegative_integer(
                result.get('potential_objects', result.get('potential_cells',
                    result.get('potential_rows', potential))),
                f'{detector_id} potential operand count', _MAX_CHECKED_CELLS,
            )
            candidates = result.get('candidate_count')
            if candidates is None:
                candidates = 0
                candidate_count_known = False
                candidate_counts_known = False
            else:
                candidates = _nonnegative_integer(candidates, f'{detector_id} candidate count', _MAX_CANDIDATES)
                candidate_count_known = True
            raw_omitted = result.get('candidate_findings_omitted')
            if percentage_detector and type(raw_omitted) is int and 0 <= raw_omitted <= _MAX_CHECKED_CELLS:
                candidate_findings_omitted = raw_omitted
            reasons, reasons_truncated = _reasons(result)
            if checked > potential:
                raise ValueError(f'{detector_id} checked more cells than its recognized table operands')
            if candidate_count_known and candidates > checked:
                raise ValueError(f'{detector_id} reports more candidates than checked cells')
            if status == 'NOT_APPLICABLE' and (potential or checked or candidates):
                raise ValueError(f'{detector_id} marks a table not applicable despite detector operands')
            skipped = potential - checked
        else:
            status = 'INCOMPLETE'
            checked = 0
            candidates = 0
            candidate_count_known = False
            candidate_findings_omitted = None
            candidate_counts_known = False
            skipped = potential
            reasons = ['DETECTOR_TABLE_RESULT_MISSING']
            reasons_truncated = False

        table_statuses.append(status)
        status_counts[status] = status_counts.get(status, 0) + 1
        potential_operands += potential
        checked_operands += checked
        skipped_operands += skipped
        candidate_items += candidates
        tables_checked += int(checked > 0)
        tables_skipped += int(status in ('INCOMPLETE', 'UNSUPPORTED'))
        tables_with_candidates += int(candidates > 0)
        table_id = _bounded_text(table.table_id, 'table_id', 500)
        label = _bounded_text(table.label, 'table label', _MAX_LABEL_LENGTH)
        caption = _bounded_text(table.caption, 'table caption', _MAX_LABEL_LENGTH)
        table_results.append({
            'table_ref': _table_reference(table),
            'table_id': table_id,
            'label': label,
            'caption': caption,
            'display_text_truncated': (
                len(table.table_id) > 500 or len(table.label) > _MAX_LABEL_LENGTH
                or len(table.caption) > _MAX_LABEL_LENGTH
            ),
            'parser_status': table.structure_status,
            'status': status,
            'applicability': {
                'ELIGIBLE': 'APPLICABLE',
                'INCOMPLETE': 'UNKNOWN',
                'UNSUPPORTED': 'UNSUPPORTED',
                'NOT_APPLICABLE': 'NOT_APPLICABLE',
            }[status],
            'reasons': reasons,
            'reasons_truncated': reasons_truncated,
            'skip_reasons': reasons if status in ('INCOMPLETE', 'UNSUPPORTED') else [],
            'candidate_findings_omitted': candidate_findings_omitted,
            'counts': {
                'objects': {
                    'unit': 'table',
                    'potential': 1,
                    'applicable': int(status != 'NOT_APPLICABLE'),
                    'applicability_unknown': int(status in ('INCOMPLETE', 'UNSUPPORTED')),
                    'eligible': int(status == 'ELIGIBLE'),
                    'checked': int(checked > 0),
                    'skipped': int(status in ('INCOMPLETE', 'UNSUPPORTED')),
                    'candidates': int(candidates > 0) if candidate_count_known else None,
                },
                'operands': {
                    'unit': _bounded_text(
                        record.get('operand_unit', 'count_percentage_cell'),
                        f'{detector_id} operand unit', 100, allow_empty=False,
                    ),
                    'potential': potential,
                    'applicable': potential if status != 'NOT_APPLICABLE' else 0,
                    'eligible': checked,
                    'checked': checked,
                    'skipped': skipped,
                    'candidates': candidates if candidate_count_known else None,
                    'candidate_count_known': candidate_count_known,
                },
            },
        })

    # Keep extra detector rows visible in the summary rather than attaching
    # them to a table using an ambiguous or duplicated table ID.
    telemetry_complete = (
        _percentage_relation_telemetry_complete(
            document, record, relation_table_results, relation_records, relation_arrays_complete,
        ) if percentage_detector else False
    )
    status = (
        'UNSUPPORTED' if table_count == 0 and result_count == 0
        else _rollup_status(table_statuses, has_missing_results=bool(missing_count or extra_count))
    )
    reasons = (
        ['NO_JATS_TABLES_FOUND'] if table_count == 0 and result_count == 0 else
        (['DETECTOR_TABLE_RESULT_COUNT_MISMATCH'] if missing_count or extra_count else [])
    )
    operand_counts: dict[str, Any] = {
        'unit': _bounded_text(
            record.get('operand_unit', 'count_percentage_cell'),
            f'{detector_id} operand unit', 100, allow_empty=False,
        ),
        'potential': potential_operands,
        'applicable': potential_operands,
        'eligible': checked_operands,
        'checked': checked_operands,
        'skipped': skipped_operands,
        'candidates': candidate_items if candidate_counts_known else None,
    }
    object_counts: dict[str, Any] = {
        'unit': 'table',
        'potential': table_count,
        # Unsupported and incomplete tables are counted as possible
        # applicability; status_counts keeps their uncertainty explicit.
        'applicable': sum(count for key, count in status_counts.items()
                          if key in ('ELIGIBLE', 'UNSUPPORTED', 'INCOMPLETE')),
        'applicability_unknown': status_counts.get('UNSUPPORTED', 0) + status_counts.get('INCOMPLETE', 0),
        'eligible': status_counts.get('ELIGIBLE', 0),
        'checked': tables_checked,
        'skipped': tables_skipped,
        'candidates': tables_with_candidates if candidate_counts_known else None,
    }
    if percentage_detector and not telemetry_complete:
        status = 'INCOMPLETE'
        reasons = list(dict.fromkeys(reasons + ['PERCENTAGE_RELATION_TELEMETRY_INCOMPLETE']))
        status_counts = {'INCOMPLETE': table_count} if table_count else {}
        object_counts = {
            'unit': 'table', 'potential': table_count, 'applicable': table_count,
            'applicability_unknown': table_count, 'eligible': None, 'checked': None,
            'skipped': None, 'candidates': None,
        }
        operand_counts = {
            'unit': operand_counts['unit'], 'potential': sum(source_potentials),
            'applicable': sum(source_potentials),
            'eligible': None, 'checked': None, 'skipped': None, 'candidates': None,
        }
        for index, table_result in enumerate(table_results):
            original_reasons = table_result['reasons']
            table_result['status'] = 'INCOMPLETE'
            table_result['applicability'] = 'UNKNOWN'
            table_result['reasons'] = list(dict.fromkeys(
                original_reasons + ['PERCENTAGE_RELATION_TELEMETRY_INCOMPLETE'],
            ))
            table_result['reasons_truncated'] = False
            table_result['skip_reasons'] = table_result['reasons']
            table_result['candidate_findings_omitted'] = None
            table_result['counts']['objects'].update({
                'applicable': 1, 'applicability_unknown': 1, 'eligible': None,
                'checked': None, 'skipped': None, 'candidates': None,
            })
            table_result['counts']['operands'].update({
                'potential': source_potentials[index], 'applicable': source_potentials[index],
                'eligible': None, 'checked': None,
                'skipped': None, 'candidates': None, 'candidate_count_known': False,
            })

    result_record = {
        'detector_id': detector_id,
        'scope': 'table',
        'status': status,
        'status_counts': dict(sorted(status_counts.items())),
        'object_counts': object_counts,
        'operand_counts': operand_counts,
        'reasons': reasons,
        'unmatched_result_count': extra_count,
        **({
            'percentage_relation_telemetry': (
                summarize_relations(relation_records) if telemetry_complete else None
            ),
            'percentage_relation_telemetry_complete': telemetry_complete,
        } if percentage_detector else {}),
        'tables': table_results,
    }
    return result_record


def _percentage_relation_telemetry_complete(
    document: PaperDocument,
    record: Mapping[str, Any],
    relation_table_results: list[tuple[Table, Mapping[str, Any]]],
    table_relations: list[Mapping[str, Any]],
    table_arrays_complete: bool,
) -> bool:
    supplied = record.get('relations')
    summary = record.get('relation_telemetry')
    if (not table_arrays_complete or len(relation_table_results) != len(document.tables)
            or not isinstance(supplied, (list, tuple))):
        return False
    if any(not isinstance(item, Mapping) for item in supplied):
        return False
    flattened: list[Mapping[str, Any]] = []
    expected_type = (
        'CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE'
        if _detector_id(record) == 'table_percentage_recomputation'
        else 'DIRECT_N_OVER_N_PERCENTAGE'
    )
    detector_id = _detector_id(record)
    # Recompute even when the supplied telemetry is empty. Otherwise a caller
    # can remove every row (or only a mismatch row), adjust the summaries, and
    # avoid source binding because there is no v1.3 relation left to trigger it.
    source_relations = _source_percentage_relations(document, detector_id)
    if source_relations is None:
        return False
    for table, table_result in relation_table_results:
        relations = table_result.get('relations')
        if not isinstance(relations, (list, tuple)) or any(not isinstance(item, Mapping) for item in relations):
            return False
        try:
            computed_table = summarize_relations(relations)
        except (TypeError, ValueError):
            return False
        table_key = sha256(
            (table.source_anchor.source_sha256 + '\0' + table.source_anchor.element_path).encode('utf-8')
        ).hexdigest()
        for relation in relations:
            anchor = relation.get('source_anchor')
            if (relation.get('detector_id') != _detector_id(record)
                    or relation.get('relation_type') != expected_type
                    or relation.get('contract_version') != PERCENTAGE_CONTRACT_VERSION
                    or relation.get('table_key') != table_key
                    or not isinstance(anchor, Mapping)
                    or anchor.get('source_sha256') != document.source_sha256
                    or not isinstance(anchor.get('element_path'), str)
                    or not anchor.get('element_path').startswith(table.source_anchor.element_path + '/')):
                return False
            if relation.get('contract_version') == '1.3':
                provenance = relation.get('denominator_provenance')
                scope_resolved = relation.get('denominator_scope_resolved')
                resolution_status = (
                    provenance.get('resolution_status') if isinstance(provenance, Mapping) else None
                )
                if (not isinstance(provenance, Mapping)
                        or type(scope_resolved) is not bool
                        or resolution_status not in {'RESOLVED', 'UNRESOLVED', 'AMBIGUOUS'}
                        or scope_resolved != (resolution_status == 'RESOLVED')):
                    return False
                selected = provenance.get('selected_denominator')
                checked_status = relation.get('status') in (
                    'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH',
                )
                if checked_status and (not scope_resolved or not isinstance(selected, Mapping)):
                    return False
                if scope_resolved:
                    if not isinstance(selected, Mapping):
                        return False
                    selected_value = selected.get('value_exact')
                    raw_value = selected.get('raw_value')
                    selected_anchor = selected.get('source_anchor')
                    selected_path = (
                        selected_anchor.get('element_path') if isinstance(selected_anchor, Mapping) else None
                    )
                    if (not isinstance(selected_value, str) or not selected_value
                            or not isinstance(raw_value, str)
                            or not re.fullmatch(r'[0-9]{1,9}', raw_value)
                            or selected_value != str(int(raw_value))
                            or not isinstance(selected_anchor, Mapping)
                            or selected_anchor.get('source_sha256') != document.source_sha256
                            or relation.get('denominator_source_anchor') != selected_anchor
                            or not isinstance(selected_path, str)
                            or not selected_path.startswith(table.source_anchor.element_path.rstrip('/') + '/')):
                        return False
                    if (relation.get('status') in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH')
                            and relation.get('denominator_exact') != selected_value):
                        return False
                elif (selected is not None or relation.get('denominator_source_anchor') is not None
                      or relation.get('denominator_exact') is not None):
                    return False
                if source_relations is not None:
                    source_relation_id = relation.get('relation_id')
                    if not isinstance(source_relation_id, str):
                        return False
                    source_relation = source_relations.get(source_relation_id)
                    if source_relation is None or not _same_json_value(relation, source_relation):
                        return False
            if relation.get('relation_id') != relation_id(
                _detector_id(record), PERCENTAGE_CONTRACT_VERSION, document.source_sha256,
                anchor['element_path'],
            ):
                return False
            if relation['status'] in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
                if (not isinstance(relation.get('finding_emitted'), bool)
                        or (relation['status'] == 'ELIGIBLE_CHECKED_MATCH' and relation['finding_emitted'])):
                    return False
            elif 'finding_emitted' in relation:
                return False

        candidate_findings_omitted = sum(
            relation.get('status') == 'ELIGIBLE_CHECKED_MISMATCH'
            and relation.get('finding_emitted') is False
            for relation in relations
        )
        if (type(table_result.get('candidate_findings_omitted')) is not int
                or table_result.get('candidate_findings_omitted') != candidate_findings_omitted):
            return False
        expected_status = (
            'INCOMPLETE' if candidate_findings_omitted or (
                detector_id == 'table_percentage_recomputation'
                and table.structure_status != 'STRUCTURE_RELIABLE'
            ) else
            'NOT_APPLICABLE' if not relations else
            'UNSUPPORTED' if computed_table['skipped_relations']
            and computed_table['unsupported_relations'] == computed_table['skipped_relations'] else
            'INCOMPLETE' if computed_table['skipped_relations'] else 'ELIGIBLE'
        )
        reported_status = table_result.get('status', table_result.get('eligibility'))
        checked_alias = table_result.get(
            'checked_cells', table_result.get('checked_objects', table_result.get('checked_operands')),
        )
        expected_fields = {
            'potential_relations': computed_table['potential_relations'],
            'applicable_relations': computed_table['applicable_relations'],
            'eligible_relations': computed_table['eligible_relations'],
            'checked_matches': computed_table['checked_matches'],
            'checked_mismatches': computed_table['checked_mismatches'],
            'incomplete_relations': computed_table['incomplete_relations'],
            'unsupported_relations': computed_table['unsupported_relations'],
            'skipped_relations': computed_table['skipped_relations'],
            'primary_skip_reason_counts': computed_table['primary_skip_reason_counts'],
        }
        if (reported_status != expected_status or checked_alias != computed_table['checked_relations']
                or table_result.get('candidate_count') != sum(
                    relation.get('finding_emitted') is True for relation in relations
                ) or any(table_result.get(key) != value for key, value in expected_fields.items())):
            return False
        if detector_id in {
            'table_percentage_recomputation', 'jats_cell_ratio_percentage_recomputation',
        }:
            reason_set: list[str] = []
            for relation in relations:
                primary = relation.get('primary_skip_reason')
                if primary:
                    reason_set.append(primary)
                    reason_set.extend(relation.get('secondary_skip_reasons', []))
            expected_reasons = list(dict.fromkeys(reason_set))
            if (detector_id == 'table_percentage_recomputation'
                    and table.structure_status != 'STRUCTURE_RELIABLE'
                    and 'TABLE_STRUCTURE_UNSUPPORTED' not in expected_reasons):
                expected_reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
            if candidate_findings_omitted:
                expected_reasons.append(
                    'STRUCTURED_TABLE_CANDIDATE_LIMIT'
                    if detector_id == 'table_percentage_recomputation'
                    else 'CANDIDATE_FINDINGS_OMITTED'
                )
            if table_result.get('reasons') != expected_reasons:
                return False
        if (detector_id == 'jats_cell_ratio_percentage_recomputation'
                and table_result.get('skip_reasons') != list(computed_table['primary_skip_reason_counts'])):
            return False
        flattened.extend(relations)

    if (list(supplied) != flattened
            or [item.get('relation_id') for item in flattened] != list(source_relations)):
        return False
    try:
        computed = summarize_relations(supplied)
    except (TypeError, ValueError):
        return False
    if summary != computed:
        return False
    if list(supplied) != table_relations:
        return False
    findings = record.get('findings')
    if not isinstance(findings, (list, tuple)):
        return False
    emitted = [
        relation.get('relation_id') for relation in supplied
        if relation.get('status') == 'ELIGIBLE_CHECKED_MISMATCH' and relation.get('finding_emitted') is True
    ]
    omitted = sum(
        relation.get('status') == 'ELIGIBLE_CHECKED_MISMATCH' and relation.get('finding_emitted') is False
        for relation in supplied
    )
    finding_ids = [item.get('relation_id') for item in findings if isinstance(item, Mapping)]
    if (any(not isinstance(item, str) for item in finding_ids)
            or len(finding_ids) != len(findings)
            or sorted(finding_ids) != sorted(emitted)
            or record.get('candidate_findings_omitted') != omitted):
        return False
    checked = computed['checked_relations']
    if record.get('checked_cells') != checked:
        return False
    if 'potential_cells' in record and record.get('potential_cells') != computed['potential_relations']:
        return False
    if 'skipped_cells' in record and record.get('skipped_cells') != computed['skipped_relations']:
        return False
    return True


def _build_paper_detector(record: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize a paper-scoped result when it supplies explicit counts."""
    detector_id = _detector_id(record)
    status = _status(record)
    count_aliases = {
        'potential': ('potential_objects', 'potential_count'),
        'applicable': ('applicable_objects', 'applicable_count'),
        'eligible': ('eligible_objects', 'eligible_count'),
        'checked': ('checked_objects', 'checked_count'),
        'skipped': ('skipped_objects', 'skipped_count'),
        'candidates': ('candidate_objects', 'candidate_count'),
    }
    counts: dict[str, int | None] = {}
    for key, aliases in count_aliases.items():
        raw = next((record[name] for name in aliases if name in record), None)
        counts[key] = (None if raw is None else
                       _nonnegative_integer(raw, f'{detector_id} {key} count', _MAX_CHECKED_CELLS))
    reasons, reasons_truncated = _reasons(record)
    operand_aliases = {
        'potential': ('potential_operands',),
        'applicable': ('applicable_operands',),
        'eligible': ('eligible_operands',),
        'checked': ('checked_operands',),
        'skipped': ('skipped_operands',),
        'candidates': ('candidate_operands',),
    }
    operand_counts = {
        key: (None if (raw := next((record[name] for name in aliases if name in record), None)) is None
              else _nonnegative_integer(raw, f'{detector_id} {key} operand count', _MAX_CHECKED_CELLS))
        for key, aliases in operand_aliases.items()
    }
    return {
        'detector_id': detector_id,
        'scope': 'paper',
        'status': status,
        'reasons': reasons,
        'reasons_truncated': reasons_truncated,
        'object_counts': {
            'unit': _bounded_text(record.get('object_unit', 'detector_object'), 'object_unit', 100,
                                  allow_empty=False),
            **counts,
        },
        'operand_counts': {
            'unit': _bounded_text(record.get('operand_unit', 'operand'), 'operand_unit', 100,
                                  allow_empty=False),
            **operand_counts,
        },
        'tables': [],
    }


def build_paper_coverage(
    document: PaperDocument,
    detector_results: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build deterministic per-paper, per-detector, and (when supplied) per-table coverage.

    ``detector_results`` may be a single detector result or an iterable. A
    table-scoped record uses the current structured JATS shape: ``detector_id``
    plus a ``tables`` list in the same order as ``document.tables``. A paper-
    scoped record uses ``detector_id`` and a supported detector status; counts
    not supplied by that detector remain ``None`` rather than being guessed.

    Table operand counters use detector-supplied potential counts when present.
    Legacy count/percentage screens fall back to the current exact cell shape.
    They are not counts of all numeric content or all possible errors.
    """
    if not isinstance(document, PaperDocument):
        raise TypeError('document must be a PaperDocument')
    if not isinstance(document.source_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', document.source_sha256):
        raise ValueError('PaperDocument must carry a lowercase source SHA-256 hash')
    records = _normalize_detector_results(detector_results)
    paper_tables = _table_model_summary(document)
    detectors = [
        _build_table_detector(document, record) if 'tables' in record
        else _build_paper_detector(record)
        for record in records
    ]
    return {
        'coverage_version': '1',
        'source_sha256': document.source_sha256,
        'scope_note': (
            'Coverage describes only the source objects represented in this document model and the supplied '
            'detector results. Table applicability counts include records not ruled out as inapplicable; '
            'incomplete and unsupported counts remain separately visible. Table checked/skipped object counts '
            'may overlap for a partially checked table; operand counts describe recognized count/percentage cells. '
            'This is not evidence that arbitrary paper errors were exhaustively checked.'
        ),
        'paper': {
            'tables': paper_tables,
            'detectors_reported': len(detectors),
        },
        'detectors': detectors,
    }
