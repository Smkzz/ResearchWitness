"""Source-mapped, narrow JATS table check for SD, SE, and sample size.

This module is deliberately independent of the paper-audit dispatcher. It
checks only rows whose exact JATS header paths identify one sample-size cell,
one standard-deviation cell, and one standard-error cell in the same scope.
Every positive result remains an arithmetic candidate for human review.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
from typing import Any

from .paper_document import PaperDocument, Table, TableCell, TableRow


DETECTOR_ID = 'jats_sd_se_n_recomputation'
MAX_N = 1_000_000_000
MAX_MAGNITUDE = Decimal('1000000000')
MAX_DISPLAY_PRECISION = 8
CALCULATION_PRECISION = 60
MAX_STATISTICS_FINDINGS = 256

_INTEGER = re.compile(r'^(?:0|[1-9][0-9]{0,9})$')
_DECIMAL = re.compile(r'^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,8})?$')
_HEADER_ROLES = {
    'n': 'n',
    'sd': 'sd',
    'standard deviation': 'sd',
    'se': 'se',
    'standard error': 'se',
    # SEM is intentionally recognizable only as a disallowed near-match. It
    # is not silently treated as the contract's exact SE column label.
    'sem': 'sem',
    'standard error of the mean': 'sem',
}
_TABLE_SCOPE_AMBIGUITY = re.compile(
    r'\b(?:weighted|weighting|adjusted|adjustment|covariate|multivariable|'
    r'multivariate|clustered|cluster\s+robust|imput(?:ed|ation)|'
    r'repeated[ -]?measures?|repeated observations?|longitudinal|'
    r'multiple time[ -]?points?|across visits?|between visits?|'
    r'baseline and follow[ -]?up|follow[ -]?up and baseline|'
    r'transform(?:ed|ation)?|log[ -]?scale|logarithm(?:ic)?|'
    r'square[ -]?root|standardized score|z[ -]?score)\b',
    re.IGNORECASE,
)


def _header_path(cell: TableCell) -> tuple[str, ...]:
    return tuple(' '.join(value.split()).casefold() for value in cell.effective_headers)


def _cell_role(cell: TableCell) -> str | None:
    path = _header_path(cell)
    if not path:
        return None
    return _HEADER_ROLES.get(path[-1])


def _has_role_header(table: Table) -> bool:
    return any(_cell_role(cell) is not None for row in table.rows for cell in row.cells)


def _table_context(table: Table) -> str:
    parts = [table.label, table.caption]
    parts.extend(note.text for note in table.footnotes)
    parts.extend('/'.join(column.header_hierarchy) for column in table.columns)
    parts.extend(
        cell.raw_text for row in table.rows for cell in row.cells
        if row.row_group in ('tbody', 'tfoot')
    )
    return ' '.join(parts)


def _skip(reason: str, row_index: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {'reason': reason}
    if row_index is not None:
        result['row_index'] = row_index
    return result


def _numeric_value(raw: str, *, integer: bool) -> tuple[Decimal | int | None, int | None, str | None]:
    value = raw.strip()
    if len(value) > 20:
        return None, None, 'NUMERIC_TOKEN_TOO_LONG'
    if integer:
        if not _INTEGER.fullmatch(value):
            return None, None, 'N_NOT_A_BOUNDED_EXPLICIT_INTEGER'
        parsed = int(value)
        if parsed < 1 or parsed > MAX_N:
            return None, None, 'N_OUTSIDE_SUPPORTED_RANGE'
        return parsed, 0, None
    if not _DECIMAL.fullmatch(value):
        return None, None, 'SD_OR_SE_NOT_A_BOUNDED_DECIMAL'
    precision = len(value.partition('.')[2]) if '.' in value else 0
    if precision > MAX_DISPLAY_PRECISION:
        return None, None, 'DISPLAY_PRECISION_EXCEEDS_LIMIT'
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None, None, 'SD_OR_SE_NOT_A_BOUNDED_DECIMAL'
    if parsed < 0 or parsed > MAX_MAGNITUDE:
        return None, None, 'SD_OR_SE_OUTSIDE_SUPPORTED_RANGE'
    return parsed, precision, None


def _source_anchor(cell: TableCell, document: PaperDocument) -> dict[str, Any] | None:
    anchor = cell.source_anchor
    if (not anchor.element_path or anchor.source_format != 'jats_xml'
            or anchor.source_sha256 != document.source_sha256):
        return None
    return asdict(anchor)


def _row_header_cells(row: TableRow) -> dict[str, list[TableCell]]:
    role_cells: dict[str, list[TableCell]] = {'n': [], 'sd': [], 'se': [], 'sem': []}
    for cell in row.cells:
        role = _cell_role(cell)
        if role is not None:
            role_cells[role].append(cell)
    return role_cells


def _check_row(document: PaperDocument, table: Table, row: TableRow) -> tuple[dict[str, Any] | None, str | None]:
    roles = _row_header_cells(row)
    row_index = row.row_index
    if roles['sem']:
        return None, 'SEM_HEADER_NOT_ACCEPTED_AS_SE'
    if any(len(roles[role]) > 1 for role in ('n', 'sd', 'se')):
        return None, 'DUPLICATE_OPERAND_COLUMNS'
    if any(len(roles[role]) != 1 for role in ('n', 'sd', 'se')):
        return None, 'MISSING_REQUIRED_OPERAND_COLUMN'

    n_cell, sd_cell, se_cell = roles['n'][0], roles['sd'][0], roles['se'][0]
    operand_cells = (n_cell, sd_cell, se_cell)
    if any(cell.row_span != 1 or cell.column_span != 1 for cell in operand_cells):
        return None, 'OPERAND_CELL_SPANS_MULTIPLE_ROWS_OR_COLUMNS'
    if any(cell.footnote_references or cell.cross_references or cell.scope_denominator_cues
           for cell in row.cells):
        return None, 'FOOTNOTE_CROSS_REFERENCE_OR_SCOPE_CUE_ON_ROW'

    row_label = next((cell for cell in row.cells if cell.column_start == 0), None)
    if row_label is None or not row_label.raw_text.strip():
        return None, 'ROW_SCOPE_UNSPECIFIED'
    if (row_label.footnote_references or row_label.cross_references
            or row_label.scope_denominator_cues):
        return None, 'FOOTNOTE_CROSS_REFERENCE_OR_SCOPE_CUE_ON_ROW_LABEL'
    if len({cell.row_identity for cell in operand_cells}) != 1:
        return None, 'OPERAND_ROW_IDENTITY_MISMATCH'

    paths = tuple(_header_path(cell) for cell in operand_cells)
    if any(not path for path in paths):
        return None, 'OPERAND_HEADER_PATH_MISSING'
    if paths[0][:-1] != paths[1][:-1] or paths[0][:-1] != paths[2][:-1]:
        return None, 'OPERAND_SCOPE_OR_UNIT_HEADER_MISMATCH'

    anchors = [_source_anchor(cell, document) for cell in operand_cells]
    if any(anchor is None for anchor in anchors):
        return None, 'SOURCE_ANCHOR_MISSING_OR_MISMATCHED'

    n, _n_precision, n_error = _numeric_value(n_cell.raw_text, integer=True)
    sd, _sd_precision, sd_error = _numeric_value(sd_cell.raw_text, integer=False)
    se, se_precision, se_error = _numeric_value(se_cell.raw_text, integer=False)
    if n_error:
        return None, n_error
    if sd_error:
        return None, sd_error
    if se_error:
        return None, se_error
    assert isinstance(n, int) and isinstance(sd, Decimal) and isinstance(se, Decimal)
    assert se_precision is not None

    try:
        with localcontext() as context:
            context.prec = CALCULATION_PRECISION
            context.rounding = ROUND_HALF_UP
            expected = sd / Decimal(n).sqrt()
            quantum = Decimal(1).scaleb(-se_precision)
            rounded = expected.quantize(quantum, rounding=ROUND_HALF_UP)
            expected_text = format(rounded, 'f')
            difference = abs(se - rounded)
            difference_text = format(difference, 'f')
    except (InvalidOperation, ArithmeticError):
        return None, 'DECIMAL_ARITHMETIC_UNSUPPORTED'

    status = 'CONSISTENT_WITH_ROUNDING' if se == rounded else 'ARITHMETIC_CANDIDATE'
    finding = {
        'status': status,
        'type': 'JATS_SD_SE_N_ARITHMETIC_MISMATCH' if status == 'ARITHMETIC_CANDIDATE' else None,
        'table_id': table.table_id,
        'row_index': row_index,
        'row_identity': row_label.raw_text[:2000],
        'n_exact': str(n),
        'sd_exact': format(sd, 'f'),
        'reported_se': format(se, 'f'),
        'recomputed_se_at_display_precision': expected_text,
        'display_precision': se_precision,
        'difference_at_display_precision': difference_text,
        'source_anchors': [
            {'role': role, 'source_anchor': anchor}
            for role, anchor in zip(('n', 'sd', 'se'), anchors, strict=True)
        ],
    }
    return finding, None


def check_jats_sd_se_n_tables(document: PaperDocument) -> dict[str, Any]:
    """Check eligible JATS rows for ``SE = SD / sqrt(n)``.

    Applicability is identified by exact terminal header labels. The checker
    requires one n/SD/SE cell per row, common header scope, an explicit row
    label, bounded numeric cells, and source anchors tied to the document hash.
    It does not infer transformations, repeated-measure semantics, units, or
    publication fidelity. A mismatch is only an arithmetic candidate.
    """
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for table in document.tables:
        applicable = _has_role_header(table)
        potential_rows = sum(
            1 for row in table.rows if row.row_group == 'tbody' and any(_row_header_cells(row).values())
        )
        result: dict[str, Any] = {
            'table_id': table.table_id,
            'applicability': 'APPLICABLE' if applicable else 'NOT_APPLICABLE',
            'eligibility': 'NOT_APPLICABLE' if not applicable else 'INCOMPLETE',
            'status': 'NOT_APPLICABLE' if not applicable else 'INCOMPLETE',
            'potential_objects': potential_rows,
            'checked_objects': 0,
            'skipped_objects': potential_rows,
            'checked_rows': 0,
            'checks': [],
            'candidate_count': 0,
            'candidates': [],
            'skip_reasons': [],
            'scan_complete': True,
        }
        if not applicable:
            result['skip_reasons'].append(_skip('NO_RECOGNIZED_OPERAND_HEADER'))
            results.append(result)
            continue

        table_failure: str | None = None
        if document.source_format != 'jats_xml':
            table_failure = 'SOURCE_FORMAT_NOT_JATS_XML'
        elif table.structure_status != 'STRUCTURE_RELIABLE':
            table_failure = 'TABLE_STRUCTURE_NOT_RELIABLE'
        elif _TABLE_SCOPE_AMBIGUITY.search(_table_context(table)):
            table_failure = 'TABLE_HAS_SCOPE_OR_TRANSFORM_AMBIGUITY'
        if table_failure:
            result['eligibility'] = 'UNSUPPORTED'
            result['status'] = 'UNSUPPORTED'
            result['scan_complete'] = False
            result['skip_reasons'].append(_skip(table_failure))
            results.append(result)
            continue

        relevant_rows = [row for row in table.rows if row.row_group == 'tbody']
        checked_rows = 0
        for row in relevant_rows:
            roles = _row_header_cells(row)
            if not any(roles.values()):
                continue
            finding, reason = _check_row(document, table, row)
            if reason is not None:
                result['scan_complete'] = False
                result['skip_reasons'].append(_skip(reason, row.row_index))
                continue
            assert finding is not None
            if (finding['status'] == 'ARITHMETIC_CANDIDATE'
                    and len(findings) >= MAX_STATISTICS_FINDINGS):
                result['scan_complete'] = False
                result['skip_reasons'].append(_skip('STATISTICS_CANDIDATE_LIMIT', row.row_index))
                continue
            checked_rows += 1
            result['checks'].append(finding)
            if finding['status'] == 'ARITHMETIC_CANDIDATE':
                result['candidates'].append(finding)
                findings.append(finding)

        result['checked_rows'] = checked_rows
        result['checked_objects'] = checked_rows
        result['skipped_objects'] = max(0, potential_rows - checked_rows)
        result['candidate_count'] = len(result['candidates'])
        if checked_rows and result['skipped_objects'] == 0 and result['scan_complete']:
            result['eligibility'] = 'ELIGIBLE'
            result['status'] = 'ELIGIBLE'
        elif checked_rows:
            result['eligibility'] = 'INCOMPLETE'
            result['status'] = 'INCOMPLETE'
        else:
            result['eligibility'] = 'INCOMPLETE'
            result['status'] = 'INCOMPLETE'
            if not result['skip_reasons']:
                result['skip_reasons'].append(_skip('NO_ROWS_WITH_OPERAND_HEADERS'))
                result['scan_complete'] = False
        results.append(result)

    return {
        'detector_id': DETECTOR_ID,
        'operand_unit': 'eligible_sd_se_n_row',
        'rounding_policy': 'Decimal square root and division at 60-digit precision; ROUND_HALF_UP at reported SE precision',
        'findings': findings,
        'tables': results,
        'scan_complete': all(
            item['eligibility'] not in ('INCOMPLETE', 'UNSUPPORTED') for item in results
        ),
        'limitations': list(dict.fromkeys(
            item['reason'] for table in results for item in table['skip_reasons']
        )),
    }
