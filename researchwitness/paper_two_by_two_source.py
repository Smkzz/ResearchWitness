"""Source-mapped detector for a strict unadjusted 2x2 odds-ratio table.

The supported form is one JATS body row with four explicitly labelled event
and non-event counts for exposed/unexposed groups plus an explicitly
unadjusted, oriented odds-ratio column. It does not recover counts from
percentages or compare model-adjusted estimates.
"""
from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from .paper_document import PaperDocument, Table, TableCell
from .paper_statistics import recompute_two_by_two


DETECTOR_ID = 'jats_unadjusted_2x2_odds_ratio'
MAX_FINDINGS = 256
MAX_COUNT = 1_000_000_000
_COUNT = re.compile(r'^(?:0|[1-9][0-9]{0,9})$')
_NUMBER = re.compile(r'^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,8})?$')
_UNADJUSTED_OR = re.compile(
    r'\bunadjusted\s+(?:odds\s+ratio|OR)\b.{0,120}?\bexposed\s+(?:vs\.?|versus)\s+unexposed\b',
    re.IGNORECASE,
)
_TIMEPOINT = re.compile(
    r'\b(?:baseline|follow[ -]?up|day\s+[0-9]{1,4}|[0-9]{1,4}[ -]?day|'
    r'week\s+[0-9]{1,4}|month\s+[0-9]{1,4}|year\s+[0-9]{1,4})\b',
    re.IGNORECASE,
)
_UNSAFE_CONTEXT = re.compile(
    r'\b(?:weighted|adjusted|adjustment|model(?:led|ing)?|regression|cluster(?:ed|ing)?|'
    r'imput(?:ed|ation)|standardiz(?:e|ed|es|ing|ation)|standardis(?:e|ed|es|ing|ation)|propensity|bootstrap|multiple time[ -]?points?|'
    r'repeated[ -]?measures?|missing data|multiple responses?|overlap(?:ping)?)\b',
    re.IGNORECASE,
)
_NON_EVENT = re.compile(r'\b(?:non[ -]?events?|no events?|without events?)\b', re.IGNORECASE)
_EVENT = re.compile(r'\bevents?\b', re.IGNORECASE)


def _anchor(cell: TableCell, document: PaperDocument) -> dict[str, Any] | None:
    source = cell.source_anchor
    if (source.source_format != 'jats_xml' or source.source_sha256 != document.source_sha256
            or not source.element_path or not source.quote):
        return None
    return asdict(source)


def _table_context(table: Table) -> str:
    return ' '.join([
        table.label, table.caption,
        *(note.text for note in table.footnotes),
        *(header for column in table.columns for header in column.header_hierarchy),
        *(cell.raw_text for row in table.rows if row.row_group in ('tbody', 'tfoot') for cell in row.cells),
    ])


def _header_role_text(raw_text: str) -> tuple[str, str] | None:
    text = ' '.join(raw_text.split()).casefold()
    if _UNADJUSTED_OR.search(text):
        return 'statistic', 'unadjusted_odds_ratio_exposed_vs_unexposed'
    has_exposed = re.search(r'\bexposed\b', text) is not None
    has_unexposed = re.search(r'\bunexposed\b', text) is not None
    if has_exposed == has_unexposed:
        return None
    has_non_event = _NON_EVENT.search(text) is not None
    has_event = not has_non_event and _EVENT.search(text) is not None
    if has_non_event == has_event:
        return None
    group = 'unexposed' if has_unexposed else 'exposed'
    return group, 'non_event' if has_non_event else 'event'


def _serialize_check(
    *, status: str, reason: str | None, table: Table, row_index: int,
    row_identity: str, timepoint: str,
    value_cells: dict[tuple[str, str], TableCell], stat_cell: TableCell | None,
    values: dict[tuple[str, str], int], reported: str | None, result: dict[str, Any] | None,
) -> dict[str, Any]:
    ordered_cells = [
        value_cells[('exposed', 'event')], value_cells[('exposed', 'non_event')],
        value_cells[('unexposed', 'event')], value_cells[('unexposed', 'non_event')],
    ]
    anchors = [asdict(cell.source_anchor) for cell in ordered_cells]
    if stat_cell is not None:
        anchors.append(asdict(stat_cell.source_anchor))
    record: dict[str, Any] = {
        'status': status,
        'reason': reason,
        'table_id': table.table_id,
        'row_index': row_index,
        'row_identity': row_identity[:2000],
        'timepoint': timepoint,
        'measure': 'odds_ratio',
        'exposed_events_exact': str(values[('exposed', 'event')]) if ('exposed', 'event') in values else None,
        'exposed_non_events_exact': str(values[('exposed', 'non_event')]) if ('exposed', 'non_event') in values else None,
        'unexposed_events_exact': str(values[('unexposed', 'event')]) if ('unexposed', 'event') in values else None,
        'unexposed_non_events_exact': str(values[('unexposed', 'non_event')]) if ('unexposed', 'non_event') in values else None,
        'reported_odds_ratio': reported,
        'exact_numerator': result.get('exact_numerator') if result else None,
        'exact_denominator': result.get('exact_denominator') if result else None,
        'recomputed_at_display_precision': result.get('recomputed_at_display_precision') if result else None,
        'display_precision': result.get('display_precision') if result else None,
        'source_anchors': anchors,
    }
    return record


def _check_table(document: PaperDocument, table: Table) -> dict[str, Any]:
    table_context = _table_context(table)
    potential_rows = sum(row.row_group == 'tbody' for row in table.rows)
    base = {
        'table_id': table.table_id,
        'status': 'NOT_APPLICABLE',
        'potential_objects': 0,
        'applicable_objects': 0,
        'eligible_objects': 0,
        'checked_objects': 0,
        'skipped_objects': 0,
        'candidate_count': 0,
        'checks': [],
        'candidates': [],
        'skip_reasons': [],
        'scan_complete': True,
    }
    roles = [_header_role_text(' '.join(column.header_hierarchy)) for column in table.columns]
    if not _UNADJUSTED_OR.search(table_context) and '2x2' not in table_context.casefold():
        return base
    base['potential_objects'] = potential_rows
    base['applicable_objects'] = potential_rows
    if document.source_format != 'jats_xml':
        base.update(status='UNSUPPORTED', skipped_objects=potential_rows, scan_complete=False)
        base['skip_reasons'].append({'reason': 'SOURCE_FORMAT_NOT_JATS_XML'})
        return base
    if table.structure_status != 'STRUCTURE_RELIABLE':
        base.update(status='INCOMPLETE', skipped_objects=potential_rows, scan_complete=False)
        base['skip_reasons'].append({'reason': 'TABLE_STRUCTURE_NOT_RELIABLE'})
        return base
    if _UNSAFE_CONTEXT.search(table_context):
        base.update(status='UNSUPPORTED', skipped_objects=potential_rows, scan_complete=False)
        base['skip_reasons'].append({'reason': 'MODEL_ADJUSTED_WEIGHTED_OR_COMPLEX_CONTEXT'})
        return base
    if table.footnotes:
        base.update(status='INCOMPLETE', skipped_objects=potential_rows, scan_complete=False)
        base['skip_reasons'].append({'reason': 'TABLE_FOOTNOTE_SEMANTICS_UNRESOLVED'})
        return base
    if potential_rows != 1:
        base.update(status='INCOMPLETE', skipped_objects=potential_rows, scan_complete=False)
        base['skip_reasons'].append({'reason': 'ONE_OUTCOME_ROW_REQUIRED'})
        return base

    row = next(row for row in table.rows if row.row_group == 'tbody')
    row_label = next((cell for cell in row.cells if cell.column_start == 0), None)
    if row_label is None or not row_label.raw_text.strip():
        base.update(status='INCOMPLETE', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'OUTCOME_ROW_LABEL_MISSING', 'row_index': row.row_index})
        return base
    timepoint_match = _TIMEPOINT.search(row_label.raw_text + ' ' + table.caption)
    if timepoint_match is None:
        base.update(status='UNSUPPORTED', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'TIMEPOINT_UNSPECIFIED', 'row_index': row.row_index})
        return base

    header_role_by_column: dict[int, tuple[str, str]] = {}
    statistic_columns: list[int] = []
    for column in table.columns:
        role = roles[column.index]
        if role is None:
            continue
        if role[0] == 'statistic':
            statistic_columns.append(column.index)
        else:
            header_role_by_column[column.index] = role
    if (len(header_role_by_column) != 4 or len(statistic_columns) != 1
            or set(header_role_by_column.values()) != {
                ('exposed', 'event'), ('exposed', 'non_event'),
                ('unexposed', 'event'), ('unexposed', 'non_event'),
            }):
        base.update(status='UNSUPPORTED', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'EXACT_2X2_AND_ORIENTATION_HEADERS_REQUIRED', 'row_index': row.row_index})
        return base

    if any(cell.footnote_references or cell.cross_references or cell.scope_denominator_cues for cell in row.cells):
        base.update(status='INCOMPLETE', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'FOOTNOTE_OR_SCOPE_CUE_ON_ROW', 'row_index': row.row_index})
        return base
    value_cells: dict[tuple[str, str], TableCell] = {}
    values: dict[tuple[str, str], int] = {}
    for column_index, role in header_role_by_column.items():
        cell = next((item for item in row.cells if item.column_start == column_index), None)
        if cell is None or cell.row_span != 1 or cell.column_span != 1:
            base.update(status='INCOMPLETE', skipped_objects=1, scan_complete=False)
            base['skip_reasons'].append({'reason': '2X2_CELL_MISSING_OR_SPANNED', 'row_index': row.row_index})
            return base
        if not _COUNT.fullmatch(cell.raw_text.strip()):
            base.update(status='INCOMPLETE', skipped_objects=1, scan_complete=False)
            base['skip_reasons'].append({'reason': '2X2_COUNT_NOT_EXPLICIT_INTEGER', 'row_index': row.row_index})
            return base
        value = int(cell.raw_text.strip())
        if value > MAX_COUNT:
            base.update(status='UNSUPPORTED', skipped_objects=1, scan_complete=False)
            base['skip_reasons'].append({'reason': '2X2_COUNT_OUT_OF_BOUNDS', 'row_index': row.row_index})
            return base
        value_cells[role] = cell
        values[role] = value

    if len(statistic_columns) != 1:
        base.update(status='UNSUPPORTED', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'REPORTED_UNADJUSTED_OR_HEADER_REQUIRED', 'row_index': row.row_index})
        return base
    stat_cell = next((item for item in row.cells if item.column_start == statistic_columns[0]), None)
    if (stat_cell is None or stat_cell.row_span != 1 or stat_cell.column_span != 1
            or not _NUMBER.fullmatch(stat_cell.raw_text.strip())):
        base.update(status='INCOMPLETE', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'REPORTED_ODDS_RATIO_NOT_EXPLICIT_DECIMAL', 'row_index': row.row_index})
        return base
    if not _anchor(row_label, document) or any(_anchor(cell, document) is None for cell in value_cells.values()) or _anchor(stat_cell, document) is None:
        base.update(status='INCOMPLETE', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'SOURCE_ANCHOR_MISSING_OR_MISMATCHED', 'row_index': row.row_index})
        return base
    if any(value == 0 for value in values.values()):
        base.update(status='UNSUPPORTED', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': 'ZERO_CELL_POLICY_UNSPECIFIED', 'row_index': row.row_index})
        return base

    arithmetic = recompute_two_by_two(
        exposed_events=values[('exposed', 'event')],
        exposed_non_events=values[('exposed', 'non_event')],
        reference_events=values[('unexposed', 'event')],
        reference_non_events=values[('unexposed', 'non_event')],
        measure='odds_ratio', reported=stat_cell.raw_text.strip(),
        reference_group_explicit=True, timepoint_explicit=True,
        adjustment_status='unadjusted',
    )
    if arithmetic['status'] == 'UNSUPPORTED':
        base.update(status='UNSUPPORTED', skipped_objects=1, scan_complete=False)
        base['skip_reasons'].append({'reason': arithmetic['reason'], 'row_index': row.row_index})
        return base

    status = 'ARITHMETIC_CANDIDATE' if arithmetic['status'] == 'ARITHMETIC_CANDIDATE' else 'CONSISTENT_WITH_ROUNDING'
    check = _serialize_check(
        status=status, reason=None, table=table, row_index=row.row_index,
        row_identity=row_label.raw_text, timepoint=timepoint_match.group(0),
        value_cells=value_cells, stat_cell=stat_cell, values=values,
        reported=stat_cell.raw_text.strip(), result=arithmetic,
    )
    base['checks'] = [check]
    base['checked_objects'] = 1
    base['eligible_objects'] = 1
    if status == 'ARITHMETIC_CANDIDATE':
        candidate = {
            'id': '',
            'type': 'JATS_UNADJUSTED_2X2_ODDS_RATIO_MISMATCH',
            'status': 'CANDIDATE_ANOMALY',
            'table_id': table.table_id,
            'row_identity': row_label.raw_text[:2000],
            'timepoint': timepoint_match.group(0),
            'exposed_events_exact': str(values[('exposed', 'event')]),
            'exposed_non_events_exact': str(values[('exposed', 'non_event')]),
            'unexposed_events_exact': str(values[('unexposed', 'event')]),
            'unexposed_non_events_exact': str(values[('unexposed', 'non_event')]),
            'reported_odds_ratio': stat_cell.raw_text.strip(),
            'exact_numerator': arithmetic['exact_numerator'],
            'exact_denominator': arithmetic['exact_denominator'],
            'recomputed_at_display_precision': arithmetic['recomputed_at_display_precision'],
            'display_precision': arithmetic['display_precision'],
            'source_anchors': [
                asdict(value_cells[role].source_anchor)
                for role in (('exposed', 'event'), ('exposed', 'non_event'),
                             ('unexposed', 'event'), ('unexposed', 'non_event'))
            ] + [asdict(stat_cell.source_anchor)],
            'interpretation': (
                f"The explicit unadjusted odds ratio for exposed versus unexposed is "
                f"{arithmetic['recomputed_at_display_precision']} at the reported precision, "
                f"while the table reports {stat_cell.raw_text.strip()}."
            ),
            'required_review': (
                'Confirm the table outcome, groups, timepoint, crude estimate, and source version. '
                'This arithmetic candidate does not establish a causal effect or which printed value is wrong.'
            ),
        }
        base['candidates'] = [candidate]
        base['candidate_count'] = 1
    base['status'] = 'ELIGIBLE'
    return base


def check_jats_unadjusted_2x2_tables(document: PaperDocument) -> dict[str, Any]:
    """Check exact 2x2 count tables with a same-row, oriented crude odds ratio."""
    findings: list[dict[str, Any]] = []
    tables = []
    limitations = []
    candidate_limit_reached = False
    for table in document.tables:
        result = _check_table(document, table)
        if result['candidate_count']:
            if len(findings) < MAX_FINDINGS:
                for candidate in result['candidates']:
                    candidate['id'] = f'jats-unadjusted-2x2-or-{len(findings) + 1:04d}'
                    findings.append(candidate)
            else:
                # Withhold the entire candidate when the report cap is reached.
                # An omitted arithmetic mismatch must be visible as incomplete
                # coverage rather than looking like a clean, fully checked row.
                result.update(
                    status='INCOMPLETE', eligible_objects=0, checked_objects=0,
                    skipped_objects=max(1, result['skipped_objects']),
                    candidate_count=0, checks=[], candidates=[], scan_complete=False,
                )
                result['skip_reasons'].append({'reason': '2X2_CANDIDATE_LIMIT'})
                candidate_limit_reached = True
                limitations.append('2X2_CANDIDATE_LIMIT')
        tables.append({key: value for key, value in result.items() if key != 'candidates'})
        limitations.extend(item['reason'] for item in result['skip_reasons'])
    return {
        'detector_id': DETECTOR_ID,
        'operand_unit': 'explicit_2x2_row',
        'findings': findings[:MAX_FINDINGS],
        'tables': tables,
        'scan_complete': (not candidate_limit_reached
                          and all(item['status'] not in ('INCOMPLETE', 'UNSUPPORTED') for item in tables)),
        'limitations': list(dict.fromkeys(limitations)),
    }
