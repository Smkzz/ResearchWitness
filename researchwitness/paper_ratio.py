"""Source-mapped arithmetic for self-contained JATS n/N (percent) cells."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from hashlib import sha256
import re
from typing import Any

from .paper_contracts import PERCENTAGE_CONTRACT_VERSION
from .paper_document import PaperDocument, SourceAnchor, Table, TableCell
from .paper_relation_telemetry import relation_id, summarize_relations, terminal_relation


CELL_RATIO_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*/\s*(?P<denominator>[0-9]{1,9})'
    r'\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*%\s*\)'
    r'\s*(?P<marker>[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰])?\s*$'
)
CELL_RATIO_SHAPE = re.compile(
    r'^\s*(?P<count>[0-9][0-9, .\u00a0\u202f]{0,24})\s*/\s*'
    r'(?P<denominator>[0-9][0-9, .\u00a0\u202f]{0,24})\s*'
    r'\(\s*(?P<percent>[0-9][0-9, .\u00a0\u202f]{0,24})\s*%\s*\)'
    r'\s*(?P<marker>[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰])?\s*$'
)
_WEIGHTED_CUE = re.compile(r'\bweighted\b', re.IGNORECASE)
_ADJUSTED_CUE = re.compile(r'\b(?:adjusted|standardized|imputed|model-derived|regression-derived)\b', re.IGNORECASE)
_MISSINGNESS_CUE = re.compile(
    r'\b(?:missing data|missing responses?|available cases?|denominator varies|per row|complete cases?)\b',
    re.IGNORECASE,
)
_MULTIPLE_RESPONSE_CUE = re.compile(r'\bmultiple responses?\b', re.IGNORECASE)
_AMBIGUOUS_RESPONSE_BASE = re.compile(
    r'\b(?:percentage|percentages|proportion|proportions)\s+(?:of|per)\s+(?:all )?responses\b',
    re.IGNORECASE,
)
_POPULATION_UNIT = re.compile(r'\b(?:participants?|patients?|respondents?|subjects?|individuals?)\b', re.IGNORECASE)
_DISPLAY_NOTE = re.compile(
    r'^(?:(?:all )?categorical variables? are shown as n\s*\(%\)|'
    r'the variables are shown as n\s*\(%\))',
    re.IGNORECASE,
)
_CONTINUOUS_NOTE = re.compile(
    r'^;\s*continuous variables are shown as (?:mean\s*±\s*standard deviation'
    r'(?:\s+or\s+median\s*\([^)]{1,80}\))?|median\s*\([^)]{1,80}\))',
    re.IGNORECASE,
)
_GLOSSARY_ITEM = re.compile(
    r'^[*†‡§]?\s*(?P<abbr>[A-Z][A-Z0-9-]{1,11})\s+'
    r'(?P<definition>[A-Za-z][A-Za-z0-9 ()/.,–-]{1,180})$'
)
_TEST_NOTE = re.compile(
    r'^[*†‡§]?\s*(?:chi[- ]square|fisher(?:\x27s)? exact|student\x27s? t|'
    r'analysis of variance) test(?:\s+was used)?$', re.IGNORECASE,
)
_TRAILING_TEST_NOTE = re.compile(
    r'\s+([*†‡§]\s*(?:chi[- ]square|fisher(?:\x27s)? exact|student\x27s? t|'
    r'analysis of variance) test(?:\s+was used)?)$', re.IGNORECASE,
)
MAX_DIRECT_RATIO_CELLS = 50_000
MAX_RATIO_FINDINGS = 256


def _anchor_dict(anchor: SourceAnchor) -> dict[str, Any]:
    return {
        'source_file': anchor.source_file,
        'source_sha256': anchor.source_sha256,
        'source_format': anchor.source_format,
        'element_path': anchor.element_path,
        'quote': anchor.quote,
        'start_byte': anchor.start_byte,
        'end_byte': anchor.end_byte,
    }


def _known_display_note(note: str) -> bool:
    """Recognize narrowly bounded table-format and abbreviation footnotes.

    An unknown note can change scope, so it remains unsupported. Hazard cues
    are checked separately by the caller before this display-only classifier.
    """
    text = re.sub(r'\s+', ' ', note).strip()
    trailing_test = _TRAILING_TEST_NOTE.search(text)
    if trailing_test is not None:
        text = text[:trailing_test.start()].rstrip()
    first = _DISPLAY_NOTE.match(text)
    if first is None:
        return False
    remainder = text[first.end():].strip()
    if remainder.startswith(';'):
        continuous = _CONTINUOUS_NOTE.match(remainder)
        if continuous is None:
            return False
        remainder = remainder[continuous.end():].strip()
    if not remainder:
        return True
    for item in remainder.split(','):
        phrase = item.strip()
        if not phrase:
            return False
        if _TEST_NOTE.fullmatch(phrase):
            continue
        if _GLOSSARY_ITEM.fullmatch(phrase):
            continue
        return False
    return True


def _table_key(table: Table) -> str:
    bound = table.source_anchor.source_sha256 + '\0' + table.source_anchor.element_path
    return sha256(bound.encode('utf-8')).hexdigest()


def _skip_reasons(
    table: Table,
    row_cells: tuple[TableCell, ...],
    cell: TableCell,
    match: re.Match[str],
) -> list[str]:
    reasons: list[str] = []
    if cell.row_span != 1 or cell.column_span != 1:
        reasons.append('TABLE_STRUCTURE_UNSUPPORTED')
    if cell.footnote_references or cell.cross_references or any(
        'FOOTNOTE' in cue or 'CROSS_REFERENCE' in cue for cue in cell.scope_denominator_cues
    ):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    label = next((candidate for candidate in row_cells if candidate.column_start == 0), None)
    if label is not None and (label.footnote_references or label.cross_references
                              or any('FOOTNOTE' in cue or 'CROSS_REFERENCE' in cue
                                     for cue in label.scope_denominator_cues)):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    row_label = next((candidate.raw_text for candidate in row_cells if candidate.column_start == 0), '')
    if not row_label.strip():
        reasons.append('SOURCE_SCOPE_AMBIGUOUS')
    context = ' '.join((table.label, table.caption, row_label, cell.raw_text, *cell.effective_headers))
    if _WEIGHTED_CUE.search(context):
        reasons.append('WEIGHTED_RESULT')
    if _ADJUSTED_CUE.search(context):
        reasons.append('ADJUSTED_RESULT')
    if _MISSINGNESS_CUE.search(context):
        reasons.append('MISSINGNESS_CHANGES_DENOMINATOR')
    if _MULTIPLE_RESPONSE_CUE.search(context) and (
        _AMBIGUOUS_RESPONSE_BASE.search(context) or not _POPULATION_UNIT.search(context)
    ):
        reasons.append('MULTIPLE_RESPONSE')
    for footnote in table.footnotes:
        if _WEIGHTED_CUE.search(footnote.text):
            reasons.append('WEIGHTED_RESULT')
        if _ADJUSTED_CUE.search(footnote.text):
            reasons.append('ADJUSTED_RESULT')
        if _MISSINGNESS_CUE.search(footnote.text):
            reasons.append('MISSINGNESS_CHANGES_DENOMINATOR')
        if _MULTIPLE_RESPONSE_CUE.search(footnote.text) and (
            _AMBIGUOUS_RESPONSE_BASE.search(footnote.text) or not _POPULATION_UNIT.search(context + ' ' + footnote.text)
        ):
            reasons.append('MULTIPLE_RESPONSE')
        note_text = footnote.text
        if footnote.label and note_text.startswith(footnote.label + ' '):
            note_text = note_text[len(footnote.label):].lstrip()
        if not _known_display_note(note_text):
            reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    if match.group('marker'):
        reasons.append('FOOTNOTE_SCOPE_UNRESOLVED')
    return list(dict.fromkeys(reasons))


def _numeric_shape_reason(match: re.Match[str]) -> str | None:
    tokens = (match.group('count').strip(), match.group('denominator').strip(), match.group('percent').strip())
    grouped = re.compile(r'^[0-9]{1,3}(?:(?:,[0-9]{3})|(?:[ \u00a0\u202f][0-9]{3}))+?$')
    if any(grouped.fullmatch(token) for token in tokens):
        return 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'
    if ',' in ''.join(tokens):
        return 'DECIMAL_SEPARATOR_UNSUPPORTED'
    if not CELL_RATIO_PERCENT.fullmatch(
        f'{tokens[0]}/{tokens[1]} ({tokens[2]}%)'
    ):
        return 'MALFORMED_NUMERIC_TOKEN'
    return None


def check_jats_cell_ratio_percentages(document: PaperDocument) -> dict[str, Any]:
    """Check explicit cell-local integer ratios and retain every relation outcome."""
    findings: list[dict[str, Any]] = []
    table_results: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []
    potential_cells = checked_cells = finding_omissions = 0
    for table in document.tables:
        table_relations: list[dict[str, Any]] = []
        before = len(findings)
        table_omissions_before = finding_omissions
        table_key = _table_key(table)
        result: dict[str, Any] = {
            'table_key': table_key,
            'table_id': table.table_id,
            'label': table.label[:500],
            'caption': table.caption[:2000],
            'source_anchor': _anchor_dict(table.source_anchor),
            'parser_status': table.structure_status,
            'potential_objects': 0,
            'applicable_objects': 0,
            'eligible_objects': 0,
            'checked_objects': 0,
            'skipped_objects': 0,
            'candidate_count': 0,
            'status': 'NOT_APPLICABLE',
            'skip_reasons': [],
        }
        for row in table.rows:
            if row.row_group != 'tbody':
                continue
            for cell in row.cells:
                match = CELL_RATIO_SHAPE.fullmatch(cell.raw_text)
                if match is None:
                    continue
                potential_cells += 1
                result['potential_objects'] += 1
                result['applicable_objects'] += 1
                relation_reasons = _skip_reasons(table, row.cells, cell, match)
                if potential_cells > MAX_DIRECT_RATIO_CELLS:
                    relation_reasons.append('CANDIDATE_LIMIT')
                numeric_reason = _numeric_shape_reason(match)
                exact_match = CELL_RATIO_PERCENT.fullmatch(cell.raw_text)
                if numeric_reason:
                    relation_reasons.append(numeric_reason)
                elif exact_match is None:
                    relation_reasons.append('MALFORMED_NUMERIC_TOKEN')

                numerator: int | None = None
                denominator: int | None = None
                reported: Decimal | None = None
                raw_percent = match.group('percent').strip()
                if exact_match is not None and numeric_reason is None:
                    numerator = int(exact_match.group('count'))
                    denominator = int(exact_match.group('denominator'))
                    raw_percent = exact_match.group('percent')
                    try:
                        reported = Decimal(raw_percent)
                    except InvalidOperation:
                        relation_reasons.append('MALFORMED_NUMERIC_TOKEN')
                if numerator is not None and denominator is not None and reported is not None:
                    if denominator <= 0 or numerator > denominator or reported > 100:
                        relation_reasons.append('OPERANDS_OUTSIDE_PROPORTION_DOMAIN')
                rid = relation_id(
                    'jats_cell_ratio_percentage_recomputation', PERCENTAGE_CONTRACT_VERSION,
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
                        relation_type='DIRECT_N_OVER_N_PERCENTAGE',
                        detector_id='jats_cell_ratio_percentage_recomputation', table_key=table_key,
                        contract_version=PERCENTAGE_CONTRACT_VERSION,
                        source_anchor=_anchor_dict(cell.source_anchor),
                        status='UNSUPPORTED' if unsupported else 'INCOMPLETE',
                        reasons=relation_reasons,
                        denominator_source_anchor=_anchor_dict(cell.source_anchor),
                        row_identity=cell.row_identity[:2000],
                    )
                    table_relations.append(relation)
                    all_relations.append(relation)
                    continue

                assert numerator is not None and denominator is not None and reported is not None
                precision = len(raw_percent.partition('.')[2]) if '.' in raw_percent else 0
                quantum = Decimal(1).scaleb(-precision)
                with localcontext() as ctx:
                    ctx.prec = 50
                    computed = Decimal(numerator) * Decimal(100) / Decimal(denominator)
                    rounded = computed.quantize(quantum, rounding=ROUND_HALF_UP)
                matched = reported == rounded
                checked_cells += 1
                result['eligible_objects'] += 1
                result['checked_objects'] += 1
                finding_emitted = False
                if not matched and len(findings) < MAX_RATIO_FINDINGS:
                    finding_emitted = True
                    findings.append({
                        'id': f'jats-cell-ratio-percentage-{len(findings) + 1:04d}',
                        'type': 'JATS_CELL_RATIO_PERCENTAGE_MISMATCH',
                        'status': 'CANDIDATE_ANOMALY',
                        'relation_id': rid,
                        'table_key': table_key,
                        'table_id': table.table_id,
                        'table_label': table.label[:500],
                        'table_caption': table.caption[:2000],
                        'row_identity': cell.row_identity[:2000],
                        'numerator_exact': str(numerator),
                        'denominator_exact': str(denominator),
                        'reported_percent': raw_percent,
                        'recomputed_percent': format(computed, '.8f').rstrip('0').rstrip('.'),
                        'recomputed_at_display_precision': format(rounded, 'f'),
                        'display_precision': precision,
                        'source_anchors': [_anchor_dict(cell.source_anchor)],
                        'interpretation': (
                            f'The same source cell states {numerator}/{denominator} and {raw_percent}%; '
                            f'the ratio rounds to {format(rounded, "f")}% under ROUND_HALF_UP at the displayed precision.'
                        ),
                        'required_review': (
                            'Confirm the source cell, units, and display convention. This single-cell arithmetic '
                            'candidate does not establish which printed operand is wrong or whether any conclusion changes.'
                        ),
                    })
                elif not matched:
                    finding_omissions += 1
                relation = terminal_relation(
                    relation_id_value=rid,
                    relation_type='DIRECT_N_OVER_N_PERCENTAGE',
                    detector_id='jats_cell_ratio_percentage_recomputation', table_key=table_key,
                    contract_version=PERCENTAGE_CONTRACT_VERSION,
                    source_anchor=_anchor_dict(cell.source_anchor),
                    status='ELIGIBLE_CHECKED_MATCH' if matched else 'ELIGIBLE_CHECKED_MISMATCH',
                    numerator_exact=str(numerator), denominator_exact=str(denominator),
                    denominator_source_anchor=_anchor_dict(cell.source_anchor),
                    reported_percent=raw_percent, display_precision=precision,
                    recomputed_at_display_precision=format(rounded, 'f'),
                    finding_emitted=finding_emitted,
                    row_identity=cell.row_identity[:2000],
                )
                table_relations.append(relation)
                all_relations.append(relation)
        table_summary = summarize_relations(table_relations)
        table_omissions = finding_omissions - table_omissions_before
        table_reasons: list[str] = []
        for relation in table_relations:
            primary = relation.get('primary_skip_reason')
            if primary:
                table_reasons.append(primary)
                table_reasons.extend(relation.get('secondary_skip_reasons', []))
        table_reasons = list(dict.fromkeys(table_reasons))
        table_status = (
            'NOT_APPLICABLE' if not table_relations else
            'UNSUPPORTED' if table_summary['skipped_relations'] and
            table_summary['unsupported_relations'] == table_summary['skipped_relations'] else
            'INCOMPLETE' if table_summary['skipped_relations'] else 'ELIGIBLE'
        )
        if table_omissions:
            table_status = 'INCOMPLETE'
            table_reasons.append('CANDIDATE_FINDINGS_OMITTED')
        result.update({
            'potential_objects': table_summary['potential_relations'],
            'applicable_objects': table_summary['applicable_relations'],
            'eligible_objects': table_summary['eligible_relations'],
            'checked_objects': table_summary['checked_relations'],
            'skipped_objects': table_summary['skipped_relations'],
            'status': table_status,
            'reasons': table_reasons,
            'skip_reasons': list(table_summary['primary_skip_reason_counts']),
            'candidate_findings_omitted': table_omissions,
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
        result['candidate_count'] = len(findings) - before
        table_results.append(result)
    summary = summarize_relations(all_relations)
    return {
        'detector_id': 'jats_cell_ratio_percentage_recomputation',
        'operand_unit': 'n_over_N_percent_cell',
        'findings': findings,
        'tables': table_results,
        'potential_cells': potential_cells,
        'checked_cells': checked_cells,
        'skipped_cells': summary['skipped_relations'],
        'relations': all_relations,
        'relation_telemetry': summary,
        'candidate_findings_omitted': finding_omissions,
        'scan_complete': summary['skipped_relations'] == 0 and finding_omissions == 0,
        'limitations': list(summary['primary_skip_reason_counts']),
    }
