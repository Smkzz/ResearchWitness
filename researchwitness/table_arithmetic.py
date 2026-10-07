"""Exact arithmetic checks that consume resolved canonical table structure."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import re
from typing import Any

from .paper_contracts import PERCENTAGE_CONTRACT_VERSION
from .paper_document import PaperDocument, SourceAnchor, Table, TableCell
from .paper_relation_telemetry import relation_id, summarize_relations, terminal_relation

COUNT_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<mark>%?)\s*\)\s*$'
)
COUNT_PERCENT_SHAPE = re.compile(
    r'^\s*(?P<count>[0-9][0-9, .\u00a0\u202f]{0,24})\s*'
    r'\(\s*(?P<percent>[0-9][0-9, .\u00a0\u202f]{0,24})\s*(?P<mark>%?)\s*\)\s*$'
)
DENOMINATOR = re.compile(
    r'(?<![A-Za-z0-9_])[nN]\s*=\s*(?P<value>[0-9]{1,9})'
    r'(?![0-9]|[,.]\s*[0-9]|\s+[0-9])'
)
DENOMINATOR_SHAPE = re.compile(r'(?<![A-Za-z0-9_])[nN]\s*=\s*(?P<value>[0-9][0-9, .\u00a0\u202f]{0,24})')
BODY_DENOMINATOR_SHAPE = re.compile(
    r'^\s*[nN]\s*=\s*(?P<value>[0-9][0-9, .\u00a0\u202f]{0,24})\s*$'
)
UNSAFE_TABLE_CUE = re.compile(
    r'\b(?:weighted|adjusted|standardized|missing data|available cases?|denominator varies|'
    r'per row|complete cases?)\b',
    re.IGNORECASE,
)
MULTIPLE_RESPONSE_CUE = re.compile(r'\bmultiple responses?\b', re.IGNORECASE)
AMBIGUOUS_RESPONSE_BASE = re.compile(
    r'\b(?:percentage|percentages|proportion|proportions)\s+(?:of|per)\s+(?:all )?responses\b',
    re.IGNORECASE,
)
POPULATION_UNIT = re.compile(r'\b(?:participants?|patients?|respondents?|subjects?|individuals?)\b', re.IGNORECASE)
OVERLAPPING_LABEL = re.compile(
    r'(?:[<>]=?|[≤≥])|\b(?:at least|at most|or more|or less|greater than|less than|above|below)\b',
    re.IGNORECASE,
)
THRESHOLD_LABEL = re.compile(
    r'(?P<operator>>=|<=|≥|≤|>|<|at least|at most|greater than|less than|above|below)\s*'
    r'(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%?',
    re.IGNORECASE,
)
ROW_LOCAL_DENOMINATOR = re.compile(
    r'\bn\s*=\s*[0-9]+',
    re.IGNORECASE,
)
PERCENT_UNIT_MARKER = re.compile(r'\bn\s*\(%\)', re.IGNORECASE)
MAX_TABLE_PERCENTAGE_FINDINGS = 256


def _number_shape_reason(match: re.Match[str]) -> str | None:
    count_raw = match.group('count').strip()
    percent_raw = match.group('percent').strip()
    grouped = re.compile(r'^[0-9]{1,3}(?:(?:,[0-9]{3})|(?:[ \u00a0\u202f][0-9]{3}))+?$')
    if grouped.fullmatch(count_raw) or grouped.fullmatch(percent_raw):
        return 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'
    if ',' in count_raw or ',' in percent_raw:
        return 'DECIMAL_SEPARATOR_UNSUPPORTED'
    if not COUNT_PERCENT.fullmatch(
        f"{count_raw} ({percent_raw}{match.group('mark')})"
    ):
        return 'MALFORMED_NUMERIC_TOKEN'
    return None


def _explicit_grouped_header_denominator(table: Table, column: int) -> bool:
    for row in table.rows:
        if row.row_group != 'thead':
            continue
        for cell in row.cells:
            if cell.column_start <= column < cell.column_start + cell.column_span:
                for match in DENOMINATOR_SHAPE.finditer(cell.raw_text):
                    raw = match.group('value').strip()
                    if ',' in raw or re.search(r'[ \u00a0\u202f]', raw):
                        return True
    return False


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


def _body_subgroup_denominators(
    table: Table,
) -> dict[int, dict[int, tuple[int | None, TableCell | None, str | None]] | None]:
    """Resolve explicit denominator rows that scope following body rows.

    Some JATS tables put subgroup Ns in the body rather than in the thead. A
    row is treated as a subgroup boundary only when its row label is present
    and every other nonempty cell is either an explicit N value or a dash.
    The latest such row applies until another subgroup row or a blank/label-
    only separator. Missing, malformed, or footnoted values stay incomplete;
    they never fall back to a broader thead denominator.
    """
    dash_values = {'-', '–', '—', '−'}
    subgroup_rows: dict[int, dict[int, tuple[int | None, TableCell | None, str | None]]] = {}
    for row_index, row in enumerate(table.rows):
        if row.row_group != 'tbody':
            continue
        label = next((cell for cell in row.cells if cell.column_start == 0), None)
        if label is None or not label.raw_text.strip():
            continue
        values: dict[int, tuple[int | None, TableCell | None, str | None]] = {}
        has_denominator = False
        valid_boundary = True
        for cell in row.cells:
            if cell.column_start == 0:
                continue
            raw = cell.raw_text.strip()
            if not raw or raw in dash_values:
                continue
            match = BODY_DENOMINATOR_SHAPE.fullmatch(raw)
            if match is None:
                # A malformed N value still marks a denominator boundary, so
                # subsequent cells cannot inherit the broader header N.
                if re.match(r'^\s*[nN]\s*=', raw):
                    has_denominator = True
                    reason = (
                        'FOOTNOTE_SCOPE_UNRESOLVED'
                        if cell.footnote_references or cell.cross_references
                        else 'MALFORMED_NUMERIC_TOKEN'
                    )
                    values[cell.column_start] = (None, cell, reason)
                    continue
                valid_boundary = False
                break
            has_denominator = True
            value = match.group('value').strip()
            reason: str | None = None
            denominator: int | None = None
            if ',' in value or re.search(r'[ \u00a0\u202f]', value):
                reason = 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'
            elif not re.fullmatch(r'[0-9]{1,9}', value):
                reason = 'MALFORMED_NUMERIC_TOKEN'
            else:
                denominator = int(value)
            if cell.footnote_references or cell.cross_references:
                reason = 'FOOTNOTE_SCOPE_UNRESOLVED'
                denominator = None
            prior = values.get(cell.column_start)
            if prior is not None:
                values[cell.column_start] = (None, cell, 'CONFLICTING_HEADER_DENOMINATORS')
            else:
                values[cell.column_start] = (denominator, cell, reason)
        if valid_boundary and has_denominator:
            subgroup_rows[row_index] = values

    states: dict[int, dict[int, tuple[int | None, TableCell | None, str | None]] | None] = {}
    active: dict[int, tuple[int | None, TableCell | None, str | None]] | None = None
    for row_index, row in enumerate(table.rows):
        if row_index in subgroup_rows:
            active = subgroup_rows[row_index]
        elif row.row_group == 'tbody':
            label = next((cell for cell in row.cells if cell.column_start == 0), None)
            other_text = [cell.raw_text.strip() for cell in row.cells if cell.column_start > 0]
            if (not any(cell.raw_text.strip() for cell in row.cells)
                    or (label is not None and label.raw_text.strip()
                        and not any(value for value in other_text))):
                active = None
        states[row_index] = active
    return states


def _table_context(table: Table) -> str:
    parts = [table.label, table.caption]
    parts.extend(footnote.text for footnote in table.footnotes)
    parts.extend(cell.raw_text for row in table.rows if row.row_group == 'thead' for cell in row.cells)
    return ' '.join(parts)


def _threshold_interval(label: str) -> tuple[Decimal | None, bool, Decimal | None, bool] | None:
    """Parse one simple threshold into an open/closed numeric interval."""
    match = THRESHOLD_LABEL.search(label)
    if match is None:
        return None
    operator = match.group('operator').lower()
    value = Decimal(match.group('value'))
    if operator in ('>=', '≥', 'at least'):
        return value, True, None, False
    if operator in ('>', 'greater than', 'above'):
        return value, False, None, False
    if operator in ('<=', '≤', 'at most'):
        return None, False, value, True
    return None, False, value, False


def _intervals_overlap(
    left: tuple[Decimal | None, bool, Decimal | None, bool],
    right: tuple[Decimal | None, bool, Decimal | None, bool],
) -> bool:
    lower_bounds = [(left[0], left[1]), (right[0], right[1])]
    upper_bounds = [(left[2], left[3]), (right[2], right[3])]
    finite_lowers = [item for item in lower_bounds if item[0] is not None]
    finite_uppers = [item for item in upper_bounds if item[0] is not None]
    lower = max(finite_lowers, key=lambda item: item[0]) if finite_lowers else (None, False)
    upper = min(finite_uppers, key=lambda item: item[0]) if finite_uppers else (None, False)
    if lower[0] is None or upper[0] is None:
        return True
    if lower[0] < upper[0]:
        return True
    return lower[0] == upper[0] and lower[1] and upper[1]


def _contains_overlapping_thresholds(labels: list[str]) -> bool:
    threshold_labels = [label for label in labels if OVERLAPPING_LABEL.search(label)]
    if len(threshold_labels) < 2:
        return False
    intervals = [_threshold_interval(label) for label in threshold_labels]
    for index, left in enumerate(intervals):
        for right in intervals[index + 1:]:
            # If a threshold cue cannot be interpreted safely, do not infer a
            # shared denominator from sibling category sums.
            if left is None or right is None or _intervals_overlap(left, right):
                return True
    return False


def _local_group_denominator_cells(table: Table) -> set[tuple[str, int]]:
    """Identify category blocks whose percentages use their summed count total.

    This is a fail-closed scope guard, not a row-total finding. A block is
    suppressed only when its explicit row structure separates it from adjacent
    variables, all cells in one column have count/percentage pairs, their
    counts sum to less than the column header, and every percentage rounds
    exactly from that smaller sum while at least one differs at the header N.
    """
    if MULTIPLE_RESPONSE_CUE.search(_table_context(table)):
        return set()

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
        labels = [
            next((cell.raw_text for cell in row.cells if cell.column_start == 0), '')
            for row in block
        ]
        if _contains_overlapping_thresholds(labels):
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


def _cell_scope_reasons(
    table: Table,
    row: Any,
    row_index: int,
    cell: TableCell,
    match: re.Match[str],
    local_group_cells: set[tuple[str, int]],
    body_subgroup_states: dict[int, dict[int, tuple[int | None, TableCell | None, str | None]] | None],
) -> tuple[list[str], int | None, TableCell | None]:
    reasons: list[str] = []
    if table.structure_status != 'STRUCTURE_RELIABLE':
        reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
    row_label_cell = next((candidate for candidate in row.cells if candidate.column_start == 0), None)
    row_label = row_label_cell.raw_text if row_label_cell else ''
    if not row_label.strip():
        reasons.append('SOURCE_SCOPE_AMBIGUOUS')
    if ROW_LOCAL_DENOMINATOR.search(row_label):
        reasons.append('LOCAL_ROW_DENOMINATOR')
    if row_label_cell is not None and (
        row_label_cell.footnote_references or row_label_cell.cross_references
        or any('FOOTNOTE' in cue or 'CROSS_REFERENCE' in cue for cue in row_label_cell.scope_denominator_cues)
    ):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    if row_label_cell is not None and 'CELL_LOCAL_DENOMINATOR' in row_label_cell.scope_denominator_cues:
        reasons.append('LOCAL_ROW_DENOMINATOR')
    if cell.row_span != 1 or cell.column_span != 1:
        reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
    if (cell.source_anchor.element_path, cell.column_identity) in local_group_cells:
        reasons.append('LOCAL_ROW_DENOMINATOR')
    if cell.footnote_references or cell.cross_references or any(
        'FOOTNOTE' in cue or 'CROSS_REFERENCE' in cue for cue in cell.scope_denominator_cues
    ):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    cue_text = ' '.join((table.label, table.caption, row_label,
                         ' '.join(cell.effective_headers), cell.raw_text))
    for note in table.footnotes:
        cue_text += ' ' + note.text
    if re.search(r'\bweighted\b', cue_text, re.IGNORECASE):
        reasons.append('WEIGHTED_RESULT')
    if re.search(r'\b(?:adjusted|standardized|model-derived|regression-derived)\b', cue_text, re.IGNORECASE):
        reasons.append('ADJUSTED_RESULT')
    if re.search(r'\b(?:missing data|available cases?|complete cases?|nonresponse|denominator varies)\b', cue_text, re.IGNORECASE):
        reasons.append('MISSINGNESS_CHANGES_DENOMINATOR')
    subgroup_state = body_subgroup_states.get(row_index)
    if subgroup_state is not None:
        denominator, denominator_cell, denominator_reason = subgroup_state.get(
            cell.column_identity, (None, None, 'DENOMINATOR_NOT_EXPLICIT'),
        )
        if denominator_reason:
            reasons.append(denominator_reason)
    else:
        denominator, denominator_cell, denominator_reason = _denominator_header(table, cell.column_identity)
        if _explicit_grouped_header_denominator(table, cell.column_identity):
            reasons.append('GROUPED_INTEGER_FORMAT_UNSUPPORTED')
            if denominator_reason == 'CONFLICTING_HEADER_DENOMINATORS':
                reasons.append('CONFLICTING_HEADER_DENOMINATORS')
            elif denominator_reason:
                reasons.append('DENOMINATOR_NOT_EXPLICIT')
        elif denominator_reason == 'CONFLICTING_HEADER_DENOMINATORS':
            reasons.append('CONFLICTING_HEADER_DENOMINATORS')
        elif denominator_reason:
            reasons.append('DENOMINATOR_NOT_EXPLICIT')
    if denominator_cell is not None and (denominator_cell.footnote_references or denominator_cell.cross_references):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    if MULTIPLE_RESPONSE_CUE.search(cue_text):
        has_population_unit = bool(POPULATION_UNIT.search(cue_text))
        if AMBIGUOUS_RESPONSE_BASE.search(cue_text) or not has_population_unit:
            reasons.append('MULTIPLE_RESPONSE')
    if denominator is not None and denominator_cell is not None:
        header_text = ' '.join(cell.effective_headers)
        row_or_header_text = ' '.join((row_label, header_text))
        if not match.group('mark') and not PERCENT_UNIT_MARKER.search(row_or_header_text):
            reasons.append('PERCENT_UNIT_NOT_EXPLICIT')
    numeric_reason = _number_shape_reason(match)
    if numeric_reason:
        reasons.append(numeric_reason)
    return list(dict.fromkeys(reasons)), denominator, denominator_cell


def check_structured_table_percentages(document: PaperDocument) -> dict[str, Any]:
    """Recompute source-scoped cell-local count/percentage relations."""
    findings: list[dict[str, Any]] = []
    table_results: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []
    checked_cells = 0
    finding_omissions = 0

    for table in document.tables:
        table_findings_before = len(findings)
        table_omissions_before = finding_omissions
        table_relations: list[dict[str, Any]] = []
        local_group_cells = _local_group_denominator_cells(table)
        body_subgroup_states = _body_subgroup_denominators(table)
        for row_index, row in enumerate(table.rows):
            if row.row_group != 'tbody':
                continue
            for cell in row.cells:
                match = COUNT_PERCENT_SHAPE.fullmatch(cell.raw_text)
                if match is None:
                    continue
                relation_reasons, denominator, denominator_cell = _cell_scope_reasons(
                    table, row, row_index, cell, match, local_group_cells, body_subgroup_states,
                )
                exact_match = COUNT_PERCENT.fullmatch(cell.raw_text)
                count: int | None = None
                reported: Decimal | None = None
                if exact_match is not None and not _number_shape_reason(match):
                    count = int(exact_match.group('count'))
                    try:
                        reported = Decimal(exact_match.group('percent'))
                    except InvalidOperation:
                        relation_reasons.append('MALFORMED_NUMERIC_TOKEN')
                elif not relation_reasons:
                    relation_reasons.append(_number_shape_reason(match) or 'MALFORMED_NUMERIC_TOKEN')
                if count is not None and reported is not None and denominator is not None:
                    if denominator <= 0 or count > denominator or reported > 100:
                        relation_reasons.append('OPERANDS_OUTSIDE_PROPORTION_DOMAIN')

                table_key = sha256(
                    (table.source_anchor.source_sha256 + '\0' + table.source_anchor.element_path).encode('utf-8')
                ).hexdigest()
                rid = relation_id(
                    'table_percentage_recomputation', PERCENTAGE_CONTRACT_VERSION,
                    cell.source_anchor.source_sha256, cell.source_anchor.element_path,
                )
                if relation_reasons:
                    unsupported = any(reason in {
                        'TABLE_STRUCTURE_UNSUPPORTED', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED',
                        'DECIMAL_SEPARATOR_UNSUPPORTED', 'MALFORMED_NUMERIC_TOKEN',
                        'OPERANDS_OUTSIDE_PROPORTION_DOMAIN', 'WEIGHTED_RESULT', 'ADJUSTED_RESULT',
                    } for reason in relation_reasons)
                    relation = terminal_relation(
                        relation_id_value=rid,
                        relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
                        detector_id='table_percentage_recomputation', table_key=table_key,
                        contract_version=PERCENTAGE_CONTRACT_VERSION,
                        source_anchor=_as_dict(cell.source_anchor),
                        status='UNSUPPORTED' if unsupported else 'INCOMPLETE',
                        reasons=relation_reasons,
                        denominator_source_anchor=(
                            _as_dict(denominator_cell.source_anchor) if denominator_cell else None
                        ),
                        row_identity=cell.row_identity[:2000],
                    )
                else:
                    assert count is not None and reported is not None and denominator is not None
                    precision = len(exact_match.group('percent').partition('.')[2]) if exact_match and '.' in exact_match.group('percent') else 0
                    computed = Decimal(count) * Decimal(100) / Decimal(denominator)
                    quantum = Decimal(1).scaleb(-precision)
                    rounded = computed.quantize(quantum, rounding=ROUND_HALF_UP)
                    is_match = reported == rounded
                    checked_cells += 1
                    emitted = True
                    if not is_match and len(findings) >= MAX_TABLE_PERCENTAGE_FINDINGS:
                        emitted = False
                    relation = terminal_relation(
                        relation_id_value=rid,
                        relation_type='CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
                        detector_id='table_percentage_recomputation', table_key=table_key,
                        contract_version=PERCENTAGE_CONTRACT_VERSION,
                        source_anchor=_as_dict(cell.source_anchor),
                        status='ELIGIBLE_CHECKED_MATCH' if is_match else 'ELIGIBLE_CHECKED_MISMATCH',
                        numerator_exact=str(count), denominator_exact=str(denominator),
                        denominator_source_anchor=(
                            _as_dict(denominator_cell.source_anchor) if denominator_cell else None
                        ),
                        reported_percent=exact_match.group('percent') if exact_match else '',
                        display_precision=precision,
                        recomputed_at_display_precision=format(rounded, 'f'),
                        finding_emitted=(emitted if not is_match else False),
                        row_identity=cell.row_identity[:2000],
                    )
                    if not is_match:
                        if emitted:
                            tolerance = Decimal(5).scaleb(-(precision + 1))
                            source_anchors = [_as_dict(denominator_cell.source_anchor)] if denominator_cell else []
                            label_cell = next((item for item in row.cells if item.column_start == 0), None)
                            if label_cell is not None:
                                source_anchors.append(_as_dict(label_cell.source_anchor))
                            source_anchors.append(_as_dict(cell.source_anchor))
                            computed_text = format(computed, '.8f').rstrip('0').rstrip('.')
                            findings.append({
                                'id': f'structured-table-percentage-{len(findings) + 1:04d}',
                                'type': 'STRUCTURED_TABLE_PERCENTAGE_ARITHMETIC_MISMATCH',
                                'status': 'CANDIDATE_ANOMALY',
                                'relation_id': rid,
                                'table_id': table.table_id,
                                'table_caption': ' '.join(item for item in (table.label, table.caption) if item)[:2000],
                                'numerator_exact': str(count),
                                'denominator_exact': str(denominator),
                                'reported_percent': exact_match.group('percent') if exact_match else '',
                                'recomputed_percent': computed_text,
                                'recomputed_at_display_precision': format(rounded, 'f'),
                                'display_precision': precision,
                                'rounding_tolerance_percentage_points': format(tolerance, 'f'),
                                'row_identity': cell.row_identity[:2000],
                                'effective_headers': list(cell.effective_headers),
                                'source_anchors': source_anchors,
                                'interpretation': (
                                    f'The displayed {exact_match.group("percent")}% differs from {count}/{denominator} '
                                    f'({computed_text}%) using the explicit JATS denominator applicable to this table section.'
                                ),
                                'required_review': (
                                    'Confirm the source relation, denominator applicability, and display rounding. '
                                    'This arithmetic candidate alone does not establish a paper error.'
                                ),
                            })
                        else:
                            finding_omissions += 1
                table_relations.append(relation)
                all_relations.append(relation)
        table_summary = summarize_relations(table_relations)
        table_reasons = []
        for relation in table_relations:
            if relation['primary_skip_reason']:
                table_reasons.append(relation['primary_skip_reason'])
                table_reasons.extend(relation['secondary_skip_reasons'])
        table_reasons = list(dict.fromkeys(table_reasons))
        if not table_relations:
            result_status = 'NOT_APPLICABLE'
        elif table_summary['skipped_relations']:
            result_status = (
                'UNSUPPORTED' if table_summary['unsupported_relations'] == table_summary['skipped_relations']
                else 'INCOMPLETE'
            )
        else:
            result_status = 'ELIGIBLE'
        if table.structure_status != 'STRUCTURE_RELIABLE':
            result_status = 'INCOMPLETE'
            if 'TABLE_STRUCTURE_UNSUPPORTED' not in table_reasons:
                table_reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
        if finding_omissions > table_omissions_before:
            result_status = 'INCOMPLETE'
            if 'STRUCTURED_TABLE_CANDIDATE_LIMIT' not in table_reasons:
                table_reasons.append('STRUCTURED_TABLE_CANDIDATE_LIMIT')
        table_candidate_findings_omitted = finding_omissions - table_omissions_before
        table_results.append({
            'table_id': table.table_id,
            'status': result_status,
            'reasons': table_reasons,
            'candidate_findings_omitted': table_candidate_findings_omitted,
            'checked_cells': table_summary['checked_relations'],
            'potential_objects': table_summary['potential_relations'],
            'potential_cells': table_summary['potential_relations'],
            'candidate_count': len(findings) - table_findings_before,
            'potential_relations': table_summary['potential_relations'],
            'applicable_relations': table_summary['applicable_relations'],
            'eligible_relations': table_summary['eligible_relations'],
            'checked_matches': table_summary['checked_matches'],
            'checked_mismatches': table_summary['checked_mismatches'],
            'incomplete_relations': table_summary['incomplete_relations'],
            'unsupported_relations': table_summary['unsupported_relations'],
            'skipped_relations': table_summary['skipped_relations'],
            'primary_skip_reason_counts': table_summary['primary_skip_reason_counts'],
            'relations': table_relations,
        })

    summary = summarize_relations(all_relations)
    return {
        'detector_id': 'table_percentage_recomputation',
        'findings': findings,
        'tables': table_results,
        'checked_cells': checked_cells,
        'relations': all_relations,
        'relation_telemetry': summary,
        'candidate_findings_omitted': finding_omissions,
        'scan_complete': summary['skipped_relations'] == 0 and finding_omissions == 0,
        'limitations': list(summary['primary_skip_reason_counts']),
    }
