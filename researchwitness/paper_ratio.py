"""Source-mapped arithmetic for self-contained JATS n/N (percent) cells."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from hashlib import sha256
import re
from typing import Any

from .paper_document import PaperDocument, SourceAnchor, Table, TableCell


CELL_RATIO_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*/\s*(?P<denominator>[0-9]{1,9})'
    r'\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*%\s*\)'
    r'\s*(?P<marker>[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰])?\s*$'
)
UNSAFE_CONTEXT = re.compile(
    r'\b(?:weighted|adjusted|standardized|imputed|cluster(?:ed|ing)?|multiple responses?|'
    r'overlap(?:ping)?|missing data|missing responses?|available cases?|denominator varies|'
    r'per row|model-derived|regression-derived)\b',
    re.IGNORECASE,
)
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


def _skip_reason(
    table: Table,
    row_cells: tuple[TableCell, ...],
    cell: TableCell,
    context: str,
) -> str | None:
    if cell.row_span != 1 or cell.column_span != 1:
        return 'CELL_SPAN_UNSUPPORTED'
    if cell.footnote_references or cell.cross_references or cell.scope_denominator_cues:
        return 'CELL_FOOTNOTE_OR_CROSS_REFERENCE_SCOPE'
    label = next((candidate for candidate in row_cells if candidate.column_start == 0), None)
    if label is not None and (label.footnote_references or label.cross_references
                              or label.scope_denominator_cues):
        return 'ROW_LABEL_SCOPE_UNRESOLVED'
    row_label = next((candidate.raw_text for candidate in row_cells if candidate.column_start == 0), '')
    if UNSAFE_CONTEXT.search(context + ' ' + row_label):
        return 'UNSAFE_TABLE_SCOPE_CUE'
    for footnote in table.footnotes:
        if UNSAFE_CONTEXT.search(footnote.text):
            return 'FOOTNOTE_SCOPE_CUE'
        note_text = footnote.text
        if footnote.label and note_text.startswith(footnote.label + ' '):
            note_text = note_text[len(footnote.label):].lstrip()
        if not _known_display_note(note_text):
            return 'FOOTNOTE_SEMANTICS_UNRESOLVED'
    return None


def check_jats_cell_ratio_percentages(document: PaperDocument) -> dict[str, Any]:
    """Check explicit integer ratio and percentage operands in the same cell.

    The exact ``n/N (p%)`` syntax supplies all three arithmetic operands in a
    single source cell, so this narrow check does not depend on a neighboring
    header or on a fully resolved grid. Cells with spans, footnotes, unsafe
    table context, unknown notes, or unsupported numeric domains are skipped.
    Findings are arithmetic candidates and do not establish a paper error.
    """
    findings: list[dict[str, Any]] = []
    table_results: list[dict[str, Any]] = []
    potential_cells = checked_cells = 0
    for table in document.tables:
        result: dict[str, Any] = {
            'table_key': _table_key(table),
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
        before = len(findings)
        context = ' '.join((table.label, table.caption,
                            *(header for column in table.columns for header in column.header_hierarchy)))
        applicable = False
        incomplete = False
        for row in table.rows:
            if row.row_group != 'tbody':
                continue
            for cell in row.cells:
                match = CELL_RATIO_PERCENT.fullmatch(cell.raw_text)
                if match is None:
                    continue
                applicable = True
                potential_cells += 1
                result['potential_objects'] += 1
                result['applicable_objects'] += 1
                if potential_cells > MAX_DIRECT_RATIO_CELLS:
                    result['skip_reasons'].append('DIRECT_RATIO_CELL_LIMIT')
                    incomplete = True
                    break
                reason = _skip_reason(table, row.cells, cell, context)
                if reason is None and match.group('marker'):
                    reason = 'CELL_FOOTNOTE_MARKER_UNRESOLVED'
                if reason:
                    result['skip_reasons'].append(reason)
                    incomplete = True
                    continue
                numerator = int(match.group('count'))
                denominator = int(match.group('denominator'))
                raw_percent = match.group('percent')
                try:
                    reported = Decimal(raw_percent)
                except InvalidOperation:
                    result['skip_reasons'].append('INVALID_PERCENT_OPERAND')
                    incomplete = True
                    continue
                if denominator <= 0 or numerator > denominator or reported > 100:
                    result['skip_reasons'].append('OPERANDS_OUTSIDE_PROPORTION_DOMAIN')
                    incomplete = True
                    continue
                precision = len(raw_percent.partition('.')[2]) if '.' in raw_percent else 0
                quantum = Decimal(1).scaleb(-precision)
                with localcontext() as ctx:
                    ctx.prec = 50
                    computed = Decimal(numerator) * Decimal(100) / Decimal(denominator)
                    rounded = computed.quantize(quantum, rounding=ROUND_HALF_UP)
                if (reported != rounded and len(findings) >= MAX_RATIO_FINDINGS):
                    result['skip_reasons'].append('RATIO_CANDIDATE_LIMIT')
                    incomplete = True
                    continue
                checked_cells += 1
                result['eligible_objects'] += 1
                result['checked_objects'] += 1
                if reported == rounded:
                    continue
                findings.append({
                    'id': f'jats-cell-ratio-percentage-{len(findings) + 1:04d}',
                    'type': 'JATS_CELL_RATIO_PERCENTAGE_MISMATCH',
                    'status': 'CANDIDATE_ANOMALY',
                    'table_key': result['table_key'],
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
            if potential_cells > MAX_DIRECT_RATIO_CELLS:
                break
        result['skipped_objects'] = result['potential_objects'] - result['checked_objects']
        result['candidate_count'] = len(findings) - before
        result['skip_reasons'] = list(dict.fromkeys(result['skip_reasons']))
        if not applicable:
            result['status'] = 'NOT_APPLICABLE'
        elif incomplete:
            result['status'] = 'INCOMPLETE'
        elif result['checked_objects']:
            result['status'] = 'ELIGIBLE'
        else:
            result['status'] = 'UNSUPPORTED'
        table_results.append(result)
    return {
        'detector_id': 'jats_cell_ratio_percentage_recomputation',
        'operand_unit': 'n_over_N_percent_cell',
        'findings': findings,
        'tables': table_results,
        'potential_cells': potential_cells,
        'checked_cells': checked_cells,
        'skipped_cells': potential_cells - checked_cells,
        'scan_complete': all(item['status'] not in ('INCOMPLETE', 'UNSUPPORTED') for item in table_results),
        'limitations': list(dict.fromkeys(
            reason for item in table_results for reason in item['skip_reasons']
        )),
    }
