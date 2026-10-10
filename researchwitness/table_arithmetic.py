"""Exact arithmetic checks that consume resolved canonical table structure."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import re
from typing import Any

from .paper_contracts import PERCENTAGE_CONTRACT_VERSION
from .paper_document import PaperDocument, SourceAnchor, Table, TableCell
from .paper_relation_telemetry import relation_id, summarize_relations, terminal_relation
from .denominator_provenance import (
    DenominatorTableContext,
    denominator_table_context,
    resolve_denominator,
)

COUNT_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*'
    r'(?P<mark>%?)\s*\)\s*(?:[;,]?\s*\(?\s*[nN]\s*=\s*[0-9][0-9, .\u00a0\u202f]{0,24}\s*\)?)?\s*$'
)
COUNT_PERCENT_SHAPE = re.compile(
    r'^\s*(?P<count>[0-9][0-9, .\u00a0\u202f]{0,24})\s*'
    r'\(\s*(?P<percent>[0-9][0-9, .\u00a0\u202f]{0,24})\s*(?P<mark>%?)\s*\)\s*'
    r'(?:[;,]?\s*\(?\s*[nN]\s*=\s*[0-9][0-9, .\u00a0\u202f]{0,24}\s*\)?)?\s*$'
)
MULTIPLE_RESPONSE_CUE = re.compile(r'\bmultiple responses?\b', re.IGNORECASE)
AMBIGUOUS_RESPONSE_BASE = re.compile(
    r'\b(?:percentage|percentages|proportion|proportions)\s+(?:of|per)\s+(?:all )?responses\b',
    re.IGNORECASE,
)
POPULATION_UNIT = re.compile(r'\b(?:participants?|patients?|respondents?|subjects?|individuals?)\b', re.IGNORECASE)
PERCENT_UNIT_MARKER = re.compile(
    r'\b(?:n|no\.?|number)\s*,?\s*\(\s*%\s*\)'
    r'|(?<!\w)%\s*(?!\w)'
    r'|\bpercent(?:age)?\b',
    re.IGNORECASE,
)
MAX_TABLE_PERCENTAGE_FINDINGS = 256
_MISSINGNESS_ROW = re.compile(
    r'\s*(?:missing|not reported|not available|unrecorded)\s*', re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _TableRowBlockProfile:
    start_index: int
    end_index: int
    has_missingness_row: bool
    category_values_by_column: dict[int, tuple[tuple[int, Decimal, int], ...]]
    invalid_columns: frozenset[int]


def _table_row_block_profiles(table: Table) -> tuple[_TableRowBlockProfile | None, ...]:
    """Precompute label-delimited missingness/category evidence once per table."""
    label_only_rows: list[int] = []
    for index, row in enumerate(table.rows):
        if row.row_group != 'tbody':
            continue
        label = next((cell for cell in row.cells if cell.column_start == 0), None)
        if (label is not None and label.raw_text.strip()
                and all(cell.column_start == 0 or not cell.raw_text.strip() for cell in row.cells)):
            label_only_rows.append(index)

    boundaries = [-1, *label_only_rows, len(table.rows)]
    profiles: list[_TableRowBlockProfile | None] = [None] * len(table.rows)
    for start, end in zip(boundaries, boundaries[1:]):
        has_missingness = False
        category_values: dict[int, list[tuple[int, Decimal, int]]] = {}
        invalid_columns: set[int] = set()
        for row in table.rows[start + 1:end]:
            if row.row_group != 'tbody':
                continue
            label = next((cell for cell in row.cells if cell.column_start == 0), None)
            if label is not None and _MISSINGNESS_ROW.fullmatch(label.raw_text):
                has_missingness = True

            assigned_columns: set[int] = set()
            for data_cell in row.cells:
                cell_match = COUNT_PERCENT.fullmatch(data_cell.raw_text)
                parsed: tuple[int, Decimal, int] | None = None
                invalid = False
                if cell_match is not None:
                    try:
                        count = int(cell_match.group('count'))
                        percent = Decimal(cell_match.group('percent'))
                    except (ValueError, InvalidOperation):
                        invalid = True
                    else:
                        precision = (len(cell_match.group('percent').partition('.')[2])
                                     if '.' in cell_match.group('percent') else 0)
                        parsed = (count, percent, precision)
                column_end = data_cell.column_start + data_cell.column_span
                for column in range(data_cell.column_start, column_end):
                    if column in assigned_columns:
                        continue
                    assigned_columns.add(column)
                    if invalid:
                        invalid_columns.add(column)
                    elif parsed is not None:
                        category_values.setdefault(column, []).append(parsed)

        profile = _TableRowBlockProfile(
            start_index=start,
            end_index=end,
            has_missingness_row=has_missingness,
            category_values_by_column={
                column: tuple(values) for column, values in category_values.items()
            },
            invalid_columns=frozenset(invalid_columns),
        )
        for row_index in range(max(start, 0), end):
            profiles[row_index] = profile
    return tuple(profiles)


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


def _block_has_missingness_row(
    row_index: int,
    profiles: tuple[_TableRowBlockProfile | None, ...],
) -> bool:
    """Read missingness state from the table's precomputed row block."""
    return (0 <= row_index < len(profiles)
            and profiles[row_index] is not None
            and profiles[row_index].has_missingness_row)


def _category_block_has_unresolved_base(
    row_index: int,
    cell: TableCell,
    denominator: int | None,
    profiles: tuple[_TableRowBlockProfile | None, ...],
) -> bool:
    """Fail closed when a source-labelled category block suggests available cases.

    The block totals are used only as evidence that the printed header base may
    not apply. They never become a denominator candidate or an arithmetic base.
    """
    if denominator is None:
        return False
    profile = profiles[row_index] if 0 <= row_index < len(profiles) else None
    if profile is None or profile.start_index < 0:
        return False
    if cell.column_identity in profile.invalid_columns:
        return False
    category_values = list(profile.category_values_by_column.get(cell.column_identity, ()))

    if len(category_values) < 2:
        return False
    count_total = sum(count for count, _percent, _precision in category_values)
    if count_total >= denominator:
        return False
    mismatches = 0
    for count, percent, precision in category_values:
        quantum = Decimal(1).scaleb(-precision)
        recomputed = (Decimal(count) * Decimal(100) / Decimal(denominator)).quantize(
            quantum, rounding=ROUND_HALF_UP,
        )
        mismatches += percent != recomputed
    if mismatches < max(2, len(category_values) // 2 + 1):
        return False
    percent_total = sum((percent for _count, percent, _precision in category_values), Decimal(0))
    rounding_tolerance = sum(
        (Decimal(1).scaleb(-precision) / Decimal(2) for _count, _percent, precision in category_values),
        Decimal(0),
    )
    return abs(percent_total - Decimal(100)) <= rounding_tolerance


def _mark_denominator_scope_unresolved_for_category_base(
    resolved: dict[str, Any],
) -> None:
    """Retain the explicit header as rejected provenance without selecting it."""
    provenance = resolved['denominator_provenance']
    selected = provenance.get('selected_denominator')
    if selected is not None:
        selected = dict(selected)
        selected['eligibility'] = 'INELIGIBLE'
        selected['rejection_reasons'] = ['MISSINGNESS_CHANGES_DENOMINATOR']
        provenance['rejected_competing_denominators'] = [
            *provenance.get('rejected_competing_denominators', []), selected,
        ]
    provenance['selected_denominator'] = None
    provenance['resolution_status'] = 'UNRESOLVED'
    provenance['resolution_reason'] = 'DENOMINATOR_SCOPE_UNRESOLVED'
    resolved['denominator_scope_resolved'] = False
    resolved['denominator_exact'] = None
    resolved['denominator_source_anchor'] = None
    resolved['skip_reasons'] = list(dict.fromkeys([
        *resolved.get('skip_reasons', []), 'MISSINGNESS_CHANGES_DENOMINATOR',
    ]))


def _cell_scope_reasons(
    table: Table,
    row: Any,
    row_index: int,
    cell: TableCell,
    match: re.Match[str],
    table_context: DenominatorTableContext,
    row_block_profiles: tuple[_TableRowBlockProfile | None, ...],
) -> tuple[list[str], int | None, dict[str, Any], dict[str, Any] | None]:
    reasons: list[str] = []
    if table.structure_status != 'STRUCTURE_RELIABLE':
        reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
    row_label_cell = next((candidate for candidate in row.cells if candidate.column_start == 0), None)
    row_label = row_label_cell.raw_text if row_label_cell else ''
    if not row_label.strip():
        reasons.append('SOURCE_SCOPE_AMBIGUOUS')
    if row_label_cell is not None and (
        row_label_cell.footnote_references or row_label_cell.cross_references
        or any('FOOTNOTE' in cue or 'CROSS_REFERENCE' in cue for cue in row_label_cell.scope_denominator_cues)
    ):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    if cell.row_span != 1 or cell.column_span != 1:
        reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
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
    if _block_has_missingness_row(row_index, row_block_profiles):
        reasons.append('MISSINGNESS_CHANGES_DENOMINATOR')
    resolved = resolve_denominator(
        table, row, cell, row_index, table_context,
    )
    denominator = resolved.get('denominator_exact')
    if _category_block_has_unresolved_base(row_index, cell, denominator, row_block_profiles):
        _mark_denominator_scope_unresolved_for_category_base(resolved)
        reasons.append('MISSINGNESS_CHANGES_DENOMINATOR')
    if not resolved['denominator_scope_resolved']:
        reasons.extend(resolved.get('skip_reasons') or ['DENOMINATOR_SCOPE_UNRESOLVED'])
    if MULTIPLE_RESPONSE_CUE.search(cue_text):
        has_population_unit = bool(POPULATION_UNIT.search(cue_text))
        if AMBIGUOUS_RESPONSE_BASE.search(cue_text) or not has_population_unit:
            reasons.append('MULTIPLE_RESPONSE')
    if denominator is not None:
        header_text = ' '.join(cell.effective_headers)
        row_or_header_text = ' '.join((row_label, header_text))
        if not match.group('mark') and not PERCENT_UNIT_MARKER.search(row_or_header_text):
            reasons.append('PERCENT_UNIT_NOT_EXPLICIT')
    numeric_reason = _number_shape_reason(match)
    if numeric_reason:
        reasons.append(numeric_reason)
    return (
        list(dict.fromkeys(reasons)),
        denominator,
        resolved['denominator_provenance'],
        resolved.get('denominator_source_anchor'),
    )


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
        table_context = denominator_table_context(table)
        row_block_profiles = _table_row_block_profiles(table)
        for row_index, row in enumerate(table.rows):
            if row.row_group != 'tbody':
                continue
            for cell in row.cells:
                match = COUNT_PERCENT_SHAPE.fullmatch(cell.raw_text)
                if match is None:
                    continue
                relation_reasons, denominator, denominator_provenance, denominator_anchor = _cell_scope_reasons(
                    table, row, row_index, cell, match, table_context, row_block_profiles,
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
                        table_source_anchor=_as_dict(table.source_anchor),
                        status='UNSUPPORTED' if unsupported else 'INCOMPLETE',
                        reasons=relation_reasons,
                        denominator_source_anchor=denominator_anchor,
                        denominator_scope_resolved=bool(
                            denominator_provenance.get('resolution_status') == 'RESOLVED'
                        ),
                        denominator_provenance=denominator_provenance,
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
                        table_source_anchor=_as_dict(table.source_anchor),
                        status='ELIGIBLE_CHECKED_MATCH' if is_match else 'ELIGIBLE_CHECKED_MISMATCH',
                        numerator_exact=str(count), denominator_exact=str(denominator),
                        denominator_source_anchor=denominator_anchor,
                        denominator_scope_resolved=True,
                        denominator_provenance=denominator_provenance,
                        reported_percent=exact_match.group('percent') if exact_match else '',
                        display_precision=precision,
                        recomputed_at_display_precision=format(rounded, 'f'),
                        finding_emitted=(emitted if not is_match else False),
                        row_identity=cell.row_identity[:2000],
                    )
                    if not is_match:
                        if emitted:
                            tolerance = Decimal(5).scaleb(-(precision + 1))
                            source_anchors = [denominator_anchor] if denominator_anchor else []
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
                                'denominator_provenance': denominator_provenance,
                                'interpretation': (
                                    f'The displayed {exact_match.group("percent")}% differs from {count}/{denominator} '
                                    f'({computed_text}%) using denominator {denominator}, selected from '
                                    f'{denominator_provenance["selected_denominator"]["structural_source"]}.'
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
