"""Pure, bounded coverage accounting for source-aware paper screens.

This module summarizes supplied detector results. It does not infer that a
paper is error-free or that arbitrary error classes were exhaustively checked.
For table screens, the table outcome records supplied by the detector remain
authoritative; operand counts describe only the detector's recognized input
shape.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from .paper_document import PaperDocument, Table
from .table_arithmetic import COUNT_PERCENT


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


def _potential_count_percent_cells(table: Table) -> int:
    """Count only tbody cells matching the active table detector's input shape."""
    return sum(
        1
        for row in table.rows if row.row_group == 'tbody'
        for cell in row.cells
        if COUNT_PERCENT.fullmatch(cell.raw_text)
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
    if extra_count:
        candidate_counts_known = False

    for index, table in enumerate(model_tables):
        potential = _potential_count_percent_cells(table)
        if table.source_anchor.source_sha256 != document.source_sha256:
            raise ValueError('table source anchor hash differs from its PaperDocument source hash')
        if index < matched_count:
            result = raw_rows[index]
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
    status = (
        'UNSUPPORTED' if table_count == 0 and result_count == 0
        else _rollup_status(table_statuses, has_missing_results=bool(missing_count or extra_count))
    )
    return {
        'detector_id': detector_id,
        'scope': 'table',
        'status': status,
        'status_counts': dict(sorted(status_counts.items())),
        'object_counts': {
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
        },
        'operand_counts': {
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
        },
        'reasons': (
            ['NO_JATS_TABLES_FOUND'] if table_count == 0 and result_count == 0 else
            (['DETECTOR_TABLE_RESULT_COUNT_MISMATCH'] if missing_count or extra_count else [])
        ),
        'unmatched_result_count': extra_count,
        'tables': table_results,
    }


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
