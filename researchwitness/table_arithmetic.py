"""Exact arithmetic checks that consume resolved canonical table structure."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any

from .paper_document import PaperDocument, SourceAnchor, Table, TableCell

COUNT_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<mark>%?)\s*\)\s*$'
)
DENOMINATOR = re.compile(r'(?<![A-Za-z0-9_])[nN]\s*=\s*(?P<value>[0-9]{1,9})(?![0-9])')
UNSAFE_TABLE_CUE = re.compile(
    r'\b(?:weighted|adjusted|multiple responses?|overlap(?:ping)?|missing data|available cases?)\b',
    re.IGNORECASE,
)
ROW_LOCAL_DENOMINATOR = re.compile(
    r'\bn\s*=\s*[0-9]+|\bn\s*\(%\)\s*(?:[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰])?',
    re.IGNORECASE,
)
MAX_TABLE_PERCENTAGE_FINDINGS = 256


def _as_dict(anchor: SourceAnchor) -> dict[str, Any]:
    return {
        'source_file': anchor.source_file,
        'source_sha256': anchor.source_sha256,
        'source_format': anchor.source_format,
        'element_path': anchor.element_path,
        'quote': anchor.quote,
        'start_byte': anchor.start_byte,
        'end_byte': anchor.end_byte,
    }


def _denominator_header(table: Table, column: int) -> tuple[int | None, TableCell | None, str | None]:
    values: set[int] = set()
    matched: TableCell | None = None
    for row in table.rows:
        if row.row_group != 'thead':
            continue
        for cell in row.cells:
            if cell.column_start <= column < cell.column_start + cell.column_span:
                for match in DENOMINATOR.finditer(cell.raw_text):
                    values.add(int(match.group('value')))
                    matched = cell
    if len(values) == 1:
        return next(iter(values)), matched, None
    if not values:
        return None, None, 'NO_EXPLICIT_COLUMN_DENOMINATOR'
    return None, None, 'CONFLICTING_HEADER_DENOMINATORS'


def _table_context(table: Table) -> str:
    parts = [table.label, table.caption]
    parts.extend(footnote.text for footnote in table.footnotes)
    parts.extend(cell.raw_text for row in table.rows if row.row_group == 'thead' for cell in row.cells)
    return ' '.join(parts)


def _local_group_denominator_cells(table: Table) -> set[tuple[str, int]]:
    """Identify category blocks whose percentages use their summed count total.

    This is a fail-closed scope guard, not a row-total finding. A block is
    suppressed only when its explicit row structure separates it from adjacent
    variables, all cells in one column have count/percentage pairs, their
    counts sum to less than the column header, and every percentage rounds
    exactly from that smaller sum while at least one differs at the header N.
    """
    header_denominators = {
        column: denominator for column in range(len(table.columns))
        if (denominator := _denominator_header(table, column)[0]) is not None
    }
    body_rows = [row for row in table.rows if row.row_group == 'tbody']
    blocks: list[list[Any]] = []
    current: list[Any] = []
    for row in body_rows:
        if len(row.cells) > 1 and all(not cell.raw_text.strip() for cell in row.cells[1:]):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(row)
    if current:
        blocks.append(current)

    suppressed: set[tuple[str, int]] = set()
    for block in blocks:
        if len(block) < 2:
            continue
        for column, header_denominator in header_denominators.items():
            parsed_cells: list[tuple[Any, Any, int, Decimal, int]] = []
            for row in block:
                cell = next((item for item in row.cells if item.column_start == column), None)
                if cell is None or cell.footnote_references or cell.scope_denominator_cues:
                    parsed_cells = []
                    break
                match = COUNT_PERCENT.fullmatch(cell.raw_text)
                if match is None:
                    parsed_cells = []
                    break
                count = int(match.group('count'))
                reported = Decimal(match.group('percent'))
                precision = len(match.group('percent').partition('.')[2]) if '.' in match.group('percent') else 0
                parsed_cells.append((row, cell, count, reported, precision))
            if len(parsed_cells) != len(block):
                continue
            local_denominator = sum(item[2] for item in parsed_cells)
            if not 0 < local_denominator < header_denominator:
                continue
            local_matches = True
            header_differs = False
            for _row, _cell, count, reported, precision in parsed_cells:
                quantum = Decimal(1).scaleb(-precision)
                local = (Decimal(count) * Decimal(100) / Decimal(local_denominator)).quantize(
                    quantum, rounding=ROUND_HALF_UP,
                )
                header = (Decimal(count) * Decimal(100) / Decimal(header_denominator)).quantize(
                    quantum, rounding=ROUND_HALF_UP,
                )
                local_matches = local_matches and reported == local
                header_differs = header_differs or reported != header
            if local_matches and header_differs:
                suppressed.update((cell.source_anchor.element_path, column) for _row, cell, *_ in parsed_cells)
    return suppressed


def check_structured_table_percentages(document: PaperDocument) -> dict[str, Any]:
    """Recompute only explicitly scoped, unadjusted count/percentage table cells.

    Any unresolved layout, denominator, scope, weight, adjustment, or attached
    footnote condition suppresses that cell. Findings remain arithmetic
    candidates and do not establish a paper error.
    """
    findings: list[dict[str, Any]] = []
    table_results: list[dict[str, Any]] = []
    checked_cells = 0
    incomplete = False

    for table in document.tables:
        reasons: list[str] = []
        table_findings_before = len(findings)
        checked_before = checked_cells
        if table.structure_status != 'STRUCTURE_RELIABLE':
            reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
            table_results.append({
                'table_id': table.table_id,
                'status': 'INCOMPLETE',
                'reasons': reasons + list(table.limitations),
                'checked_cells': 0,
                'candidate_count': 0,
            })
            incomplete = True
            continue

        context = _table_context(table)
        if UNSAFE_TABLE_CUE.search(context):
            reasons.append('WEIGHTED_ADJUSTED_MISSING_OR_OVERLAPPING_SCOPE')
            incomplete = True
            table_results.append({
                'table_id': table.table_id,
                'status': 'UNSUPPORTED',
                'reasons': reasons,
                'checked_cells': 0,
                'candidate_count': 0,
            })
            continue

        found_count_pair = False
        local_group_cells = _local_group_denominator_cells(table)
        for row in table.rows:
            if row.row_group != 'tbody':
                continue
            row_pairs = [item for item in row.cells if COUNT_PERCENT.fullmatch(item.raw_text)]
            if row_pairs:
                found_count_pair = True
            row_label_cell = next((item for item in row.cells if item.column_start == 0), None)
            row_label = row_label_cell.raw_text if row_label_cell else ''
            if ROW_LOCAL_DENOMINATOR.search(row_label):
                reasons.append('LOCAL_ROW_DENOMINATOR')
                incomplete = True
                continue
            if row_label_cell is not None and (
                row_label_cell.footnote_references or row_label_cell.scope_denominator_cues
            ):
                reasons.append('FOOTNOTED_OR_SCOPED_ROW_LABEL')
                incomplete = True
                continue
            for cell in row.cells:
                match = COUNT_PERCENT.fullmatch(cell.raw_text)
                if match is None:
                    continue
                if (cell.source_anchor.element_path, cell.column_identity) in local_group_cells:
                    reasons.append('LOCAL_GROUP_DENOMINATOR_INDICATED')
                    incomplete = True
                    continue
                if cell.column_span != 1 or cell.row_span != 1:
                    reasons.append('DATA_CELL_SPANS_MULTIPLE_ROWS_OR_COLUMNS')
                    incomplete = True
                    continue
                if cell.scope_denominator_cues:
                    reasons.append('CELL_OR_HEADER_FOOTNOTE_OR_LOCAL_SCOPE_CUE')
                    incomplete = True
                    continue
                denominator, denominator_cell, denominator_reason = _denominator_header(
                    table, cell.column_identity,
                )
                if denominator_reason:
                    reasons.append(denominator_reason)
                    incomplete = True
                    continue
                assert denominator is not None and denominator_cell is not None
                if denominator_cell.footnote_references or denominator_cell.scope_denominator_cues:
                    reasons.append('FOOTNOTED_OR_CROSS_REFERENCED_DENOMINATOR')
                    incomplete = True
                    continue
                header_text = ' '.join(cell.effective_headers)
                if not match.group('mark') and not re.search(r'\bn\s*\(%\)', header_text, re.IGNORECASE):
                    reasons.append('PERCENT_UNIT_NOT_EXPLICIT')
                    incomplete = True
                    continue
                count = int(match.group('count'))
                reported_raw = match.group('percent')
                try:
                    reported = Decimal(reported_raw)
                except InvalidOperation:
                    reasons.append('INVALID_REPORTED_PERCENTAGE')
                    incomplete = True
                    continue
                if denominator <= 0 or count > denominator or reported > 100:
                    reasons.append('OPERANDS_OUTSIDE_PROPORTION_DOMAIN')
                    incomplete = True
                    continue
                computed = Decimal(count) * Decimal(100) / Decimal(denominator)
                precision = len(reported_raw.partition('.')[2]) if '.' in reported_raw else 0
                tolerance = Decimal(5).scaleb(-(precision + 1))
                quantum = Decimal(1).scaleb(-precision)
                rounded = computed.quantize(quantum, rounding=ROUND_HALF_UP)
                checked_cells += 1
                if reported == rounded:
                    continue
                if len(findings) >= MAX_TABLE_PERCENTAGE_FINDINGS:
                    reasons.append('STRUCTURED_TABLE_CANDIDATE_LIMIT')
                    incomplete = True
                    continue
                label_cell = next((item for item in row.cells if item.column_start == 0), None)
                source_anchors = [_as_dict(denominator_cell.source_anchor)]
                if label_cell is not None:
                    source_anchors.append(_as_dict(label_cell.source_anchor))
                source_anchors.append(_as_dict(cell.source_anchor))
                computed_text = format(computed, '.8f').rstrip('0').rstrip('.')
                findings.append({
                    'id': f'structured-table-percentage-{len(findings) + 1:04d}',
                    'type': 'STRUCTURED_TABLE_PERCENTAGE_ARITHMETIC_MISMATCH',
                    'status': 'CANDIDATE_ANOMALY',
                    'table_id': table.table_id,
                    'table_caption': ' '.join(item for item in (table.label, table.caption) if item)[:2000],
                    'numerator_exact': str(count),
                    'denominator_exact': str(denominator),
                    'reported_percent': reported_raw,
                    'recomputed_percent': computed_text,
                    'recomputed_at_display_precision': format(rounded, 'f'),
                    'display_precision': precision,
                    'rounding_tolerance_percentage_points': format(tolerance, 'f'),
                    'row_identity': cell.row_identity[:2000],
                    'effective_headers': list(cell.effective_headers),
                    'source_anchors': source_anchors,
                    'interpretation': (
                        f'The displayed {reported_raw}% differs from {count}/{denominator} '
                        f'({computed_text}%) using the unambiguous JATS table header.'
                    ),
                    'required_review': (
                        'Confirm table scope, source version, denominator applicability, and display rounding. '
                        'This arithmetic candidate alone does not establish a paper error.'
                    ),
                })

        if not found_count_pair:
            reasons.append('NO_COUNT_PERCENT_CELLS')
        elif checked_cells == checked_before and not reasons:
            reasons.append('NO_CELLS_MET_THE_ELIGIBILITY_CONTRACT')
        incomplete_reasons = {
            'CELL_OR_HEADER_FOOTNOTE_OR_LOCAL_SCOPE_CUE', 'NO_EXPLICIT_COLUMN_DENOMINATOR',
            'LOCAL_ROW_DENOMINATOR', 'DATA_CELL_SPANS_MULTIPLE_ROWS_OR_COLUMNS',
            'CONFLICTING_HEADER_DENOMINATORS', 'FOOTNOTED_OR_CROSS_REFERENCED_DENOMINATOR',
            'FOOTNOTED_OR_SCOPED_ROW_LABEL', 'LOCAL_GROUP_DENOMINATOR_INDICATED',
            'PERCENT_UNIT_NOT_EXPLICIT', 'INVALID_REPORTED_PERCENTAGE',
            'OPERANDS_OUTSIDE_PROPORTION_DOMAIN',
            'STRUCTURED_TABLE_CANDIDATE_LIMIT',
        }
        if not found_count_pair:
            result_status = 'NOT_APPLICABLE'
        elif any(reason in incomplete_reasons for reason in reasons):
            result_status = 'INCOMPLETE'
        elif checked_cells > checked_before:
            result_status = 'ELIGIBLE'
        else:
            result_status = 'UNSUPPORTED'
        if result_status == 'INCOMPLETE':
            incomplete = True
        table_results.append({
            'table_id': table.table_id,
            'status': result_status,
            'reasons': list(dict.fromkeys(reasons)),
            'checked_cells': checked_cells - checked_before,
            'candidate_count': len(findings) - table_findings_before,
        })

    return {
        'detector_id': 'table_percentage_recomputation',
        'findings': findings,
        'tables': table_results,
        'checked_cells': checked_cells,
        'scan_complete': not incomplete,
        'limitations': list(dict.fromkeys(
            reason for result in table_results if result['status'] in ('INCOMPLETE', 'UNSUPPORTED')
            for reason in result['reasons']
        )),
    }
