"""Bounded paper-text extraction and conservative numeric-anomaly screening.

This module is an untrusted discovery/ingestion layer. Its output is a screening
report, not a deterministic proof that a research claim is false.
"""
from __future__ import annotations

from bisect import bisect_right
import base64
from dataclasses import asdict
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Protocol

from .jats import parse_jats
from .paper_contracts import contract_registry, eligibility, source_capabilities
from .paper_coverage import build_paper_coverage
from .paper_flow_source import map_jats_sample_flows
from .paper_prisma_flow import map_jats_prisma_relations
from .paper_ratio import check_jats_cell_ratio_percentages
from .paper_relation_telemetry import summarize_relations
from .paper_statistics_source import check_jats_sd_se_n_tables
from .paper_two_by_two_source import check_jats_unadjusted_2x2_tables
from .strict import Bundle, Invalid, byte_hash, canonical, require, text
from .table_arithmetic import check_structured_table_percentages

PAPER_AUDIT_VERSION = '0.4'
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_EXTRACTED_TEXT_BYTES = 16 * 1024 * 1024
MAX_PDF_PAGE_BYTES = 512 * 1024
MAX_PDF_EXTRACTION_SECONDS = 20
MAX_PDF_WORKER_MEMORY_BYTES = 768 * 1024 * 1024
MAX_PDF_WORKER_CPU_SECONDS = 15
MAX_PDF_WORKER_OUTPUT_BYTES = 23 * 1024 * 1024
MAX_COUNT_ASSERTIONS = 512
MAX_SCOPE_DIFFERENCES = 128
MAX_ARITHMETIC_FINDINGS = 256
MAX_FLOW_EXCLUSION_VALUES = 64
MAX_SCAN_LINE_BYTES = 64 * 1024
MAX_SCAN_LINES = 1_000_000
MAX_MARKDOWN_SECTIONS = 512
MAX_TABLE_CELLS_SCANNED = 100_000
MAX_JATS_MODEL_BYTES = 16 * 1024 * 1024
UNAVAILABLE_EXTRACTION_STATUSES = (
    'PARSER_UNAVAILABLE', 'MALFORMED_OR_UNSUPPORTED', 'LIMIT_OR_UNSUPPORTED',
    'NO_EXTRACTABLE_TEXT', 'RESOURCE_LIMIT_OR_TIMEOUT', 'WORKER_FAILED',
    'WORKER_PROTOCOL_ERROR',
)

COUNT_MARKER = re.compile(
    rb'(?<![A-Za-z0-9_])(?P<marker>[nN])[ \t]{0,32}=[ \t]{0,32}'
    rb'(?P<value>[0-9]{1,9})'
    rb'(?![0-9]|[,.]\s*[0-9]|[eE][+-]?[0-9]'
    rb'|(?:[ \t]|\xc2\xa0|\xe2\x80\xaf)+[0-9]'
    rb'|(?:[ \t]|\xc2\xa0|\xe2\x80\xaf)*(?:[/\-]|'
    rb'\xe2(?:\x80[\x90-\x95]|\x88[\x92\x95]|\x81\x84))'
    rb'(?:[ \t]|\xc2\xa0|\xe2\x80\xaf)*[0-9]|\xe2)'
)
COUNT_RANGE_SHAPE = re.compile(
    rb'(?<![A-Za-z0-9_])[nN][ \t]{0,32}=[ \t]{0,32}[0-9]{1,9}'
    rb'(?:[ \t]|\xc2\xa0|\xe2\x80\xaf)*(?:[/\-]|'
    rb'\xe2(?:\x80[\x90-\x95]|\x88[\x92\x95]|\x81\x84))'
    rb'(?:[ \t]|\xc2\xa0|\xe2\x80\xaf)*[0-9]'
)
MARKDOWN_HEADING = re.compile(rb'^ {0,3}(?P<marks>#{1,6})[ \t]+(?P<title>.*?)[ \t]*#*[ \t]*$')
TABLE_ROW = re.compile(r'^\s*\|.*\|\s*$')
TABLE_DENOMINATOR = re.compile(
    r'(?<![A-Za-z0-9_])[nN]\s*=\s*(?P<value>[0-9]{1,9})'
    r'(?P<marker>[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰])?'
    r'(?![A-Za-z0-9_]|[,.]\s*[0-9]|\s+[0-9]'
    r'|\s*[/\u2044\u2215\-\u2010-\u2015\u2212]\s*[0-9])',
    re.IGNORECASE,
)
TABLE_PERCENTAGE_FOOTNOTE_LABEL = re.compile(
    r'\bn\s*\(%\)\s*(?:[([]\s*)?[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰]\s*[)\]]?\s*$', re.IGNORECASE,
)
TABLE_COUNT_PERCENT_WITH_FOOTNOTE = re.compile(
    r'^\s*[0-9]{1,9}\s*\(\s*[0-9]{1,3}(?:\.[0-9]{1,6})?\s*%?\s*\)'
    r'\s*[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰]\s*$', re.IGNORECASE,
)
TABLE_COUNT_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<mark>%?)\s*\)\s*$'
)
FLOW_NUMBER = r'(?P<{name}>[0-9](?:[0-9,\s\u00a0\u202f]*[0-9])?)'
EXCLUSION_FLOW = re.compile(
    r'\bOf\s+the\s+' + FLOW_NUMBER.format(name='total') +
    r'\s+.{0,160}?\bparticipants?\b.{0,180}?\bwe\s+excluded\s+'
    r'(?P<exclusions>[^.\n]{1,1200})\.\s*Finally[, ]+\s*' +
    FLOW_NUMBER.format(name='included') +
    r'\s+participants?\s+were\s+included\b',
    re.IGNORECASE,
)
EXCLUSION_LIST_SPLIT = re.compile(r',\s+(?=(?:and\s+)?[0-9])')
LEADING_FLOW_NUMBER = re.compile(r'^\s*(?:and\s+)?(?P<number>[0-9](?:[0-9,\s\u00a0\u202f]*[0-9])?)')
STAGE_RULES = (
    ('screened', re.compile(r'\bscreen(?:ed|ing)\b', re.IGNORECASE)),
    ('eligible', re.compile(r'\beligib(?:le|ility)\b', re.IGNORECASE)),
    ('enrolled', re.compile(r'\benroll(?:ed|ment)?\b|\brecruit(?:ed|ment)?\b', re.IGNORECASE)),
    ('randomized', re.compile(r'\brandomi[sz](?:ed|ation)\b|\ballocated\b', re.IGNORECASE)),
    ('excluded', re.compile(r'\bexclud(?:ed|ing|es)\b', re.IGNORECASE)),
    ('completed', re.compile(r'\bcomplet(?:ed|ion)\b', re.IGNORECASE)),
    ('analyzed', re.compile(r'\banaly[sz](?:ed|is|ation)\b|\bincluded for analysis\b', re.IGNORECASE)),
    ('follow_up', re.compile(r'\bfollow[ -]?up\b|\bend of study\b', re.IGNORECASE)),
    ('available', re.compile(r'\bavailable\b|\bpaired samples?\b', re.IGNORECASE)),
)


class CandidateDiscoverer(Protocol):
    """Provider-neutral interface for untrusted candidate-generation adapters."""

    name: str

    def discover(
        self, text_bytes: bytes, page_map: list[dict[str, Any]], markdown: bool,
    ) -> dict[str, Any]: ...


class PaperAuditCancelled(Exception):
    """The caller cancelled a bounded paper-audit stage."""


def _check_audit_cancel(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise PaperAuditCancelled()


def _extract_pdf(source_bytes: bytes) -> tuple[bytes, str, str, list[dict[str, Any]], list[str]]:
    worker = Path(__file__).with_name('_pdf_worker.py').absolute()
    try:
        with tempfile.TemporaryDirectory(prefix='researchwitness-pdf-') as temp_name:
            temp_dir = Path(temp_name)
            input_path = temp_dir / 'input.pdf'
            input_path.write_bytes(source_bytes)
            input_path.chmod(0o600)
            command = [
                sys.executable, '-I', str(worker), str(input_path), str(MAX_PDF_PAGES),
                str(MAX_PDF_PAGE_BYTES), str(MAX_EXTRACTED_TEXT_BYTES),
                str(MAX_PDF_WORKER_MEMORY_BYTES), str(MAX_PDF_WORKER_CPU_SECONDS),
            ]
            child = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=MAX_PDF_EXTRACTION_SECONDS,
                check=False,
                shell=False,
                env={'PATH': os.defpath, 'PYTHONIOENCODING': 'utf-8'},
            )
    except subprocess.TimeoutExpired:
        return b'', 'RESOURCE_LIMIT_OR_TIMEOUT', 'pypdf isolated worker', [], [
            f'PDF extraction exceeded the {MAX_PDF_EXTRACTION_SECONDS}-second worker timeout. No detector was run.'
        ]
    except OSError as exc:
        return b'', 'WORKER_FAILED', 'pypdf isolated worker', [], [
            'The PDF extraction worker could not be started (' + type(exc).__name__ + '). No detector was run.'
        ]

    if child.returncode != 0:
        return b'', 'RESOURCE_LIMIT_OR_TIMEOUT', 'pypdf isolated worker', [], [
            'The PDF extraction worker stopped before completing, possibly at an operating-system resource limit. '
            'No detector was run.'
        ]
    if len(child.stdout) > MAX_PDF_WORKER_OUTPUT_BYTES:
        return b'', 'WORKER_PROTOCOL_ERROR', 'pypdf isolated worker', [], [
            'The PDF extraction worker returned more data than the configured output limit. No detector was run.'
        ]
    try:
        payload = json.loads(child.stdout.decode('utf-8'))
        status = payload['status']
        extractor = payload['extractor']
        page_records = payload['page_records']
        warnings = payload['warnings']
        output = base64.b64decode(payload['text_base64'], validate=True)
        require(type(status) is str and type(extractor) is str, 'Invalid PDF worker metadata')
        require(type(page_records) is list and type(warnings) is list, 'Invalid PDF worker result shape')
        require(len(output) <= MAX_EXTRACTED_TEXT_BYTES, 'PDF worker output exceeded the extracted-text limit')
        require(len(page_records) <= MAX_PDF_PAGES, 'PDF worker page count exceeded the configured limit')
        return output, status, extractor, page_records, warnings
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, Invalid):
        return b'', 'WORKER_PROTOCOL_ERROR', 'pypdf isolated worker', [], [
            'The PDF extraction worker returned an invalid bounded result. No detector was run.'
        ]


def _extract_source(source_bytes: bytes, suffix: str) -> tuple[bytes, str, str, list[dict[str, Any]], list[str]]:
    if suffix == '.pdf':
        return _extract_pdf(source_bytes)
    if suffix not in ('.txt', '.md', '.markdown'):
        raise Invalid('Supported paper inputs are UTF-8 .txt/.md/.markdown and optional-parser .pdf files')
    try:
        source_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Invalid('Text and Markdown inputs must be UTF-8') from exc
    status = 'TEXT_AVAILABLE' if source_bytes.strip() else 'NO_EXTRACTABLE_TEXT'
    warnings = [] if status == 'TEXT_AVAILABLE' else ['The text source is empty or contains only whitespace.']
    return source_bytes, status, 'UTF-8 source bytes (no normalization)', [], warnings


def _page_record(page_map: list[dict[str, Any]], offset: int) -> tuple[int | None, int | None]:
    if not page_map:
        return None, None
    starts = [page['text_start_byte'] for page in page_map]
    index = bisect_right(starts, offset) - 1
    if index < 0:
        return None, None
    page = page_map[index]
    if offset >= page['text_end_byte']:
        return None, None
    return page['page_number'], offset - page['text_start_byte']


class ExplicitCountDiscoverer:
    """Find explicit n/N assertions and conservatively screen compatible contexts."""

    name = 'explicit_count_marker_scan'

    def discover(
        self, text_bytes: bytes, page_map: list[dict[str, Any]], markdown: bool,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        assertions: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        overlong_lines = 0
        unsupported_range_markers = 0
        truncated = False
        active_section: str | None = None
        line_start = 0
        line_number = 1
        while line_start < len(text_bytes):
            if line_number % 128 == 1:
                _check_audit_cancel(should_cancel)
            if line_number > MAX_SCAN_LINES:
                truncated = True
                break
            newline = text_bytes.find(b'\n', line_start)
            line_end = len(text_bytes) if newline < 0 else newline
            line = text_bytes[line_start:line_end]
            if markdown:
                heading = MARKDOWN_HEADING.match(line)
                if heading:
                    try:
                        active_section = heading.group('title').decode('utf-8').strip()[:2000]
                    except UnicodeDecodeError:
                        active_section = None
                    if len(sections) < MAX_MARKDOWN_SECTIONS:
                        sections.append({
                            'heading': active_section or '',
                            'level': len(heading.group('marks')),
                            'start_byte': line_start,
                            'line_number': line_number,
                        })
                    else:
                        truncated = True
            if len(line) > MAX_SCAN_LINE_BYTES:
                overlong_lines += 1
            else:
                decoded_line: str | None = None
                unsupported_range_markers += len(COUNT_RANGE_SHAPE.findall(line))
                for match in COUNT_MARKER.finditer(line):
                    if len(assertions) >= MAX_COUNT_ASSERTIONS:
                        truncated = True
                        break
                    marker = match.group('marker').decode('ascii')
                    token_start = line_start + match.start()
                    token_end = line_start + match.end()
                    page_number, page_offset = _page_record(page_map, token_start)
                    if decoded_line is None:
                        decoded_line = line.decode('utf-8')
                    context = decoded_line.strip()
                    if len(context) > 2000:
                        char_start = len(line[:match.start()].decode('utf-8'))
                        char_end = char_start + len(match.group().decode('ascii'))
                        local_start = max(0, char_start - 900)
                        local_end = min(len(decoded_line), char_end + 900)
                        context = ('…' if local_start else '') + decoded_line[local_start:local_end].strip() + (
                            '…' if local_end < len(decoded_line) else ''
                        )
                    anchor = {
                        'text_file': 'extracted-text.txt',
                        'quote': match.group().decode('ascii'),
                        'start_byte': token_start,
                        'end_byte': token_end,
                        'line_number': line_number,
                        'context': context,
                    }
                    if page_number is not None:
                        anchor['page_number'] = page_number
                        anchor['page_offset_start_byte'] = page_offset
                        anchor['page_offset_end_byte'] = page_offset + (token_end - token_start)
                    if active_section is not None:
                        anchor['section'] = active_section
                    char_start = len(line[:match.start()].decode('utf-8'))
                    char_end = char_start + len(match.group().decode('ascii'))
                    is_table_row = markdown and TABLE_ROW.match(decoded_line)
                    if is_table_row:
                        left = decoded_line.rfind('|', 0, char_start) + 1
                        right = decoded_line.find('|', char_end)
                        if right < 0:
                            right = len(decoded_line)
                        cell_context = decoded_line[left:right].strip()
                        scope_context = (decoded_line[:decoded_line.find('|')].strip() + ' | ' + cell_context).strip()
                        region = 'MARKDOWN_TABLE_CELL'
                    else:
                        window_start = max(0, char_start - 180)
                        window_end = min(len(decoded_line), char_end + 180)
                        scope_context = decoded_line[window_start:window_end].strip()
                        region = 'PROSE_CONTEXT'
                    stage_cues = []
                    for stage, rule in STAGE_RULES:
                        stage_cues.extend(
                            {'stage': stage, 'cue': cue.group(0)}
                            for cue in rule.finditer(scope_context)
                        )
                    stage_values = sorted({cue['stage'] for cue in stage_cues})
                    assertions.append({
                        'id': f'count-{len(assertions) + 1:04d}',
                        'kind': 'explicit_count_marker',
                        'marker': marker,
                        'surface_value': match.group('value').decode('ascii'),
                        'value_exact': str(int(match.group('value'))),
                        'anchor': anchor,
                        'scope': {
                            'region': region,
                            'nearby_context': scope_context[:600],
                            'study_stage': stage_values[0] if len(stage_values) == 1 else None,
                            'stage_cues': stage_cues[:8],
                        },
                    })
            if truncated:
                break
            line_start = len(text_bytes) if newline < 0 else newline + 1
            line_number += 1

        groups: dict[str, list[dict[str, Any]]] = {'n': [], 'N': []}
        for assertion in assertions:
            groups[assertion['marker']].append(assertion)
        anomalies: list[dict[str, Any]] = []
        scope_differences: list[dict[str, Any]] = []
        table_assertions_not_compared = sum(
            item['scope']['region'] == 'MARKDOWN_TABLE_CELL' for item in assertions
        )
        scope_truncated = False
        for marker, group in groups.items():
            prose = [item for item in group if item['scope']['region'] == 'PROSE_CONTEXT']
            by_line: dict[int, list[dict[str, Any]]] = {}
            for item in prose:
                by_line.setdefault(item['anchor']['line_number'], []).append(item)
            ambiguous_ids: set[str] = set()
            for line_items in by_line.values():
                ordered = sorted(line_items, key=lambda item: item['anchor']['start_byte'])
                clusters: list[list[dict[str, Any]]] = []
                for item in ordered:
                    if (not clusters or item['anchor']['start_byte'] - clusters[-1][-1]['anchor']['start_byte']
                            > 360):
                        clusters.append([item])
                    else:
                        clusters[-1].append(item)
                for cluster in clusters:
                    distinct_line = sorted({item['value_exact'] for item in cluster}, key=int)
                    if len(distinct_line) < 2:
                        continue
                    ambiguous_ids.update(item['id'] for item in cluster)
                    if len(scope_differences) >= MAX_SCOPE_DIFFERENCES:
                        scope_truncated = True
                        continue
                    scope_differences.append({
                        'id': f'scope-{len(scope_differences) + 1:04d}',
                        'type': 'MULTIPLE_COUNT_SCOPES_IN_ONE_PASSAGE',
                        'status': 'POSSIBLE_SAMPLE_FLOW_DIFFERENCE',
                        'marker': marker,
                        'values_exact': distinct_line,
                        'source_anchors': [item['anchor'] for item in cluster],
                        'interpretation': (
                            'One short passage contains different explicit counts. The local scan cannot determine whether '
                            'the nearby labels describe different causes, groups, stages, or populations.'
                        ),
                        'required_review': (
                            'Compare the population, group, stage, denominator, and outcome labels around each value '
                            'before treating them as inconsistent.'
                        ),
                    })

            remaining = [item for item in prose if item['id'] not in ambiguous_ids]
            value_disagreement: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for index, first in enumerate(remaining):
                for second in remaining[index + 1:]:
                    if first['value_exact'] == second['value_exact']:
                        continue
                    first_stage = first['scope']['study_stage']
                    second_stage = second['scope']['study_stage']
                    if first_stage and second_stage and first_stage != second_stage:
                        if len(scope_differences) >= MAX_SCOPE_DIFFERENCES:
                            scope_truncated = True
                            continue
                        scope_differences.append({
                            'id': f'scope-{len(scope_differences) + 1:04d}',
                            'type': 'DIFFERENT_EXPLICIT_STUDY_STAGES',
                            'status': 'POSSIBLE_SAMPLE_FLOW_DIFFERENCE',
                            'marker': marker,
                            'values_exact': [first['value_exact'], second['value_exact']],
                            'source_anchors': [first['anchor'], second['anchor']],
                            'stage_labels': [first_stage, second_stage],
                            'interpretation': (
                                'The two counts have different nearby stage cues. A change may reflect ordinary '
                                'screening, exclusion, completion, or analysis flow.'
                            ),
                            'required_review': (
                                'Check the paper flow diagram, analysis population, subgroup definitions, and '
                                'supplement before deciding whether the count change is explained.'
                            ),
                        })
                    else:
                        value_disagreement.extend(((first, second),))
            candidate_ids = {item['id'] for pair in value_disagreement for item in pair}
            candidate_items = [item for item in remaining if item['id'] in candidate_ids]
            distinct = sorted({item['value_exact'] for item in candidate_items}, key=int)
            if len(distinct) > 1:
                anomaly_id = f'conflicting-{marker}-values'
                if any(item['marker'] == marker for item in anomalies):
                    anomaly_id += f'-{len(anomalies) + 1:02d}'
                anomalies.append({
                    'id': anomaly_id,
                    'type': 'CONFLICTING_EXPLICIT_COUNT_MARKERS',
                    'status': 'CANDIDATE_ANOMALY',
                    'marker': marker,
                    'values_exact': distinct,
                    'assertion_ids': [item['id'] for item in candidate_items],
                    'source_anchors': [item['anchor'] for item in candidate_items],
                    'scope_stage': sorted({item['scope']['study_stage'] for item in candidate_items
                                           if item['scope']['study_stage']}),
                    'interpretation': (
                        'Different integers follow the same case-sensitive marker in separate prose contexts. '
                        'Nearby stage cues were not enough to establish that the values refer to different scopes.'
                    ),
                    'required_review': (
                        'Compare the surrounding passages, subgroup definitions, exclusions, timepoints, '
                        'supplements, and paper version before treating this as an inconsistency.'
                    ),
                })

        limitations = []
        if overlong_lines:
            limitations.append(
                f'{overlong_lines} line(s) longer than {MAX_SCAN_LINE_BYTES} bytes were not scanned for count markers.'
            )
        if unsupported_range_markers:
            limitations.append(
                f'{unsupported_range_markers} n/N range or fraction marker(s) were not treated as integer count assertions.'
            )
        if truncated:
            limitations.append('A configured assertion or section limit was reached; scanning may be incomplete.')
        if line_number > MAX_SCAN_LINES:
            limitations.append(f'The {MAX_SCAN_LINES}-line scan limit was reached.')
        if scope_truncated:
            limitations.append('A configured scope-difference limit was reached; some count pairs were not classified.')
        limitations.extend([
            'Only explicit n = integer and N = integer patterns were scanned for repeated-count candidates.',
            'Counts in separate Markdown table cells are retained with local context but are not compared globally.',
            'Different values in one paragraph or with different explicit stage cues are described as possible scope differences.',
            'A candidate still requires review of cohort, subgroup, denominator, timepoint, and paper version.',
        ])
        return {
            'discoverer': self.name,
            'assertions': assertions,
            'candidate_anomalies': anomalies,
            'possible_scope_differences': scope_differences,
            'table_count_assertions_not_cross_compared': table_assertions_not_compared,
            'sections': sections,
            'scan_complete': not truncated and overlong_lines == 0 and unsupported_range_markers == 0,
            'limitations': limitations,
        }


def _markdown_cells(line: str) -> list[tuple[str, int, int]]:
    separators = [match.start() for match in re.finditer(r'(?<!\\)\|', line)]
    if len(separators) < 2:
        return []
    output = []
    for left, right in zip(separators, separators[1:]):
        raw_start, raw_end = left + 1, right
        start = raw_start
        end = raw_end
        while start < end and line[start].isspace():
            start += 1
        while end > start and line[end - 1].isspace():
            end -= 1
        output.append((line[start:end].replace('\\|', '|'), start, end))
    return output


def _has_denominator_footnote(cell: str, match: re.Match[str]) -> bool:
    """Detect a footnote marker attached to an explicit table denominator."""
    if match.groupdict().get('marker'):
        return True
    tail = cell[match.end():].lstrip()
    tail = re.sub(r'^[)\]}]+', '', tail).lstrip()
    return re.match(r'[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰](?=$|[\s)\]},.;:])', tail, re.IGNORECASE) is not None


def _bounded_flow_number(raw: str) -> int | None:
    if len(raw) > 75:
        return None
    digits = re.sub(r'[,\s\u00a0\u202f]', '', raw)
    if not digits.isascii() or not digits.isdigit() or len(digits) > 9:
        return None
    return int(digits)


class TablePercentageDiscoverer:
    """Recompute only explicit count/percentage cells against same-column n/N headers."""

    name = 'markdown_table_percentage_recomputation'
    unsafe_scope_cue = re.compile(
        r'(?:(?:\b(?:re)?weight(?:ed|ing|s)?|adjust(?:ed|ment|ments)|standardiz(?:e|ed|es|ing|ation)|standardis(?:e|ed|es|ing|ation)|imput(?:ed|ation|ing)|'
        r'model[- ]derived|regression[- ]derived|multiple responses?|overlap(?:ping)?|'
        r'missing data|available cases?|complete cases?|nonresponse|denominator varies)\b'
        r'|(?<![A-Za-z0-9_])[nN]\s*=\s*[0-9]{1,9}\s*[/\u2044\u2215\-\u2010-\u2015\u2212]\s*[0-9])',
        re.IGNORECASE,
    )

    def discover(
        self, text_bytes: bytes, page_map: list[dict[str, Any]], markdown: bool,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        scope_differences: list[dict[str, Any]] = []
        checked = 0
        limitations = []
        if not markdown:
            return {
                'discoverer': self.name,
                'findings': findings,
                'possible_scope_differences': scope_differences,
                'checked_cells': checked,
                'cells_scanned': 0,
                'supported': False,
                'scan_complete': True,
                'limitations': ['Structured table percentage checks run only on Markdown pipe tables.'],
            }
        line_start = 0
        line_number = 1
        section: str | None = None
        table_active = False
        caption = ''
        column_labels: list[str] = []
        denominators: dict[int, dict[str, Any]] = {}
        truncated = False
        coverage_incomplete = False
        cells_scanned = 0
        tables_seen = 0
        table_width: int | None = None
        table_finding_start = 0
        table_checked_start = 0
        table_shape_mismatch = False
        table_unsafe_context = False
        table_awaiting_note = False

        def mark_unsafe_scope() -> None:
            nonlocal table_unsafe_context, checked, coverage_incomplete
            if table_unsafe_context:
                return
            table_unsafe_context = True
            del findings[table_finding_start:]
            checked = table_checked_start
            coverage_incomplete = True
            limitations.append(
                'A pipe table with weighting, adjustment, missingness, multiple-response, overlap, or range/fraction denominator cues was skipped because the stated values or scope may not support a simple unweighted proportion.'
            )

        while line_start < len(text_bytes):
            if line_number % 128 == 1:
                _check_audit_cancel(should_cancel)
            newline = text_bytes.find(b'\n', line_start)
            line_end = len(text_bytes) if newline < 0 else newline
            raw = text_bytes[line_start:line_end]
            if len(raw) > MAX_SCAN_LINE_BYTES:
                truncated = True
                break
            decoded = raw.decode('utf-8')
            if markdown:
                heading = MARKDOWN_HEADING.match(raw)
                if heading:
                    section = heading.group('title').decode('utf-8').strip()[:2000]
                    table_active = False
                    table_width = None
                    table_shape_mismatch = False
                    table_unsafe_context = False
                    table_awaiting_note = False
                    caption = section if section.lower().startswith('table ') else ''
                    column_labels = []
                    denominators = {}
            if table_awaiting_note and decoded.strip():
                is_table_note = (
                    decoded.lstrip().lower().startswith(('note:', 'notes:'))
                    or re.match(r'^\s*[*†‡§]\s', decoded)
                )
                if is_table_note and self.unsafe_scope_cue.search(decoded):
                    mark_unsafe_scope()
                table_awaiting_note = False
                table_active = False
                table_width = None
                table_shape_mismatch = False
                table_unsafe_context = False
                caption = ''
                column_labels = []
                denominators = {}
            if TABLE_ROW.match(decoded):
                if not table_active:
                    tables_seen += 1
                    table_width = None
                    table_shape_mismatch = False
                    table_unsafe_context = False
                    table_finding_start = len(findings)
                    table_checked_start = checked
                    table_awaiting_note = False
                    if self.unsafe_scope_cue.search(caption):
                        mark_unsafe_scope()
                table_active = True
                if self.unsafe_scope_cue.search(decoded):
                    mark_unsafe_scope()
                cells = _markdown_cells(decoded)
                cells_scanned += len(cells)
                if cells_scanned > MAX_TABLE_CELLS_SCANNED:
                    truncated = True
                    break
                if table_width is None:
                    table_width = len(cells)
                elif len(cells) != table_width and not table_shape_mismatch:
                    table_shape_mismatch = True
                    del findings[table_finding_start:]
                    checked = table_checked_start
                    denominators = {}
                    column_labels = []
                    coverage_incomplete = True
                    limitations.append(
                        'A pipe table with inconsistent row widths was skipped because its columns could not be aligned safely.'
                    )
                if not re.fullmatch(r'[\s:|\-]+', decoded) and not table_shape_mismatch and not table_unsafe_context:
                    current: dict[int, dict[str, Any]] = {}
                    denominator_row = False
                    for column, (cell, cell_start, cell_end) in enumerate(cells):
                        match = TABLE_DENOMINATOR.search(cell)
                        if match and column > 0:
                            denominator_row = True
                            if _has_denominator_footnote(cell, match):
                                coverage_incomplete = True
                                limitations.append(
                                    'A denominator with an attached footnote marker was omitted because its scope may be row-specific.'
                                )
                                continue
                            number = int(match.group('value'))
                            match_start = cell_start + match.start()
                            match_end = cell_start + match.end()
                            page_number, page_offset = _page_record(page_map, line_start + len(decoded[:match_start].encode('utf-8')))
                            quote = decoded[match_start:match_end]
                            anchor = {
                                'text_file': 'extracted-text.txt', 'quote': quote,
                                'start_byte': line_start + len(decoded[:match_start].encode('utf-8')),
                                'end_byte': line_start + len(decoded[:match_end].encode('utf-8')),
                                'line_number': line_number, 'context': decoded.strip()[:2000],
                            }
                            if section:
                                anchor['section'] = section
                            if page_number is not None:
                                anchor.update({'page_number': page_number, 'page_offset_start_byte': page_offset,
                                               'page_offset_end_byte': page_offset + anchor['end_byte'] - anchor['start_byte']})
                            cell_label = TABLE_DENOMINATOR.sub('', cell).strip(' ()')
                            header_label = column_labels[column] if column < len(column_labels) else ''
                            row_group = cells[0][0].strip() if cells else ''
                            labels = [label for label in (row_group, header_label or cell_label) if label]
                            current[column] = {
                                'value': number,
                                'anchor': anchor,
                                'group_label': ' / '.join(labels)[:200],
                            }
                    if denominator_row:
                        denominators = current
                    elif denominators:
                        row_label = cells[0][0] if cells else ''
                        row_has_local_denominator = (
                            TABLE_DENOMINATOR.search(row_label) is not None
                            or TABLE_PERCENTAGE_FOOTNOTE_LABEL.search(row_label) is not None
                        )
                        if row_has_local_denominator:
                            coverage_incomplete = True
                            limitations.append(
                                'A table row with a local denominator or footnoted n (%) label was omitted from percentage checks.'
                            )
                        for column, (cell, cell_start, _cell_end) in enumerate(cells[1:], start=1):
                            if row_has_local_denominator:
                                continue
                            parsed = TABLE_COUNT_PERCENT.fullmatch(cell)
                            if parsed is None or column not in denominators:
                                if (column in denominators
                                        and TABLE_COUNT_PERCENT_WITH_FOOTNOTE.fullmatch(cell)):
                                    coverage_incomplete = True
                                    limitations.append(
                                        'A count/percentage cell with an attached footnote marker was omitted from arithmetic checks.'
                                    )
                                continue
                            if not parsed.group('mark') and not re.search(r'\bn\s*\(%\)', row_label, re.IGNORECASE):
                                continue
                            count = int(parsed.group('count'))
                            denominator = denominators[column]['value']
                            reported = parsed.group('percent')
                            percent = Decimal(reported)
                            if denominator <= 0 or count > denominator or percent > 100:
                                continue
                            computed = Decimal(count) * Decimal(100) / Decimal(denominator)
                            displayed_digits = len(reported.split('.', 1)[1]) if '.' in reported else 0
                            tolerance = Decimal(5).scaleb(-(displayed_digits + 1))
                            display_quantum = Decimal(1).scaleb(-displayed_digits)
                            rounded = computed.quantize(display_quantum, rounding=ROUND_HALF_UP)
                            checked += 1
                            if percent == rounded:
                                continue
                            alternate_tolerance = Decimal(1).scaleb(-displayed_digits)
                            estimated_denominator = int(
                                (Decimal(count) * Decimal(100) / percent).quantize(
                                    Decimal('1'), rounding=ROUND_HALF_UP,
                                )
                            ) if percent > 0 else denominator
                            alternate_denominators = [
                                possible for possible in range(max(count, estimated_denominator - 1),
                                                               min(denominator, estimated_denominator + 2))
                                if possible < denominator
                                and abs(percent - Decimal(count) * Decimal(100) / Decimal(possible))
                                <= alternate_tolerance
                            ]
                            if len(findings) >= MAX_ARITHMETIC_FINDINGS:
                                truncated = True
                                continue
                            cell_start_abs = line_start + len(decoded[:cell_start].encode('utf-8'))
                            page_number, page_offset = _page_record(page_map, cell_start_abs)
                            data_anchor = {
                                'text_file': 'extracted-text.txt', 'quote': cell[:75],
                                'start_byte': cell_start_abs,
                                'end_byte': cell_start_abs + len(cell[:75].encode('utf-8')),
                                'line_number': line_number, 'context': decoded.strip()[:2000],
                            }
                            row_context_start = cells[0][1]
                            label_start = line_start + len(decoded[:row_context_start].encode('utf-8'))
                            label_quote = row_label[:75]
                            label_anchor = {
                                'text_file': 'extracted-text.txt', 'quote': label_quote,
                                'start_byte': label_start,
                                'end_byte': label_start + len(label_quote.encode('utf-8')),
                                'line_number': line_number, 'context': decoded.strip()[:2000],
                            }
                            for anchor in (data_anchor, label_anchor):
                                if section:
                                    anchor['section'] = section
                            if page_number is not None:
                                data_anchor.update({'page_number': page_number, 'page_offset_start_byte': page_offset,
                                                    'page_offset_end_byte': page_offset + len(data_anchor['quote'].encode('utf-8'))})
                            if section:
                                denominators[column]['anchor']['section'] = section
                            computed_str = format(computed, '.6f').rstrip('0').rstrip('.')
                            findings.append({
                                'id': f'table-percentage-{len(findings) + 1:04d}',
                                'type': 'TABLE_PERCENTAGE_ARITHMETIC_MISMATCH',
                                'status': 'CANDIDATE_ANOMALY',
                                'numerator_exact': str(count),
                                'denominator_exact': str(denominator),
                                'reported_percent': reported,
                                'recomputed_percent': computed_str,
                                'rounding_tolerance_percentage_points': format(tolerance, 'f'),
                                'scope_label': denominators[column]['group_label'],
                                'table': caption,
                                'source_anchors': [denominators[column]['anchor'], label_anchor, data_anchor],
                                '_possible_alternate_denominators': [str(item) for item in alternate_denominators],
                                'adversarial_review': {
                                    'status': 'ARITHMETIC_RECOMPUTED_WITH_SCOPE_OBJECTIONS',
                                    'objections_considered': [
                                        'The reported percentage must equal ROUND_HALF_UP at its displayed precision; ties round away from zero.',
                                        'The numerator and reported percentage share one table cell.',
                                        'The denominator comes from an explicit n/N header in the same table column.',
                                        'Column order must be preserved by the supplied Markdown table; raw PDF layout is not inferred.',
                                    ],
                                    'limitations': [
                                        'The mismatch applies only if the explicit column denominator is intended for this row; source authenticity and paper version were not authenticated.',
                                        'A row-specific denominator, missing-data subset, or table-layout change could alter the interpretation.',
                                    ],
                                },
                                'interpretation': (
                                    f'The displayed {reported}% differs from {count}/{denominator} '
                                    f'({computed_str}%) using the explicit column denominator.'
                                ),
                                'required_review': (
                                    'Check table footnotes, row-specific denominators, missing-data rules, and the publisher '
                                    'version before treating this arithmetic difference as an error.'
                                ),
                            })
                if not table_shape_mismatch and not table_unsafe_context and not column_labels:
                    column_labels = [TABLE_DENOMINATOR.sub('', cell).strip(' ()') for cell, _, _ in cells]
                elif not table_shape_mismatch and not table_unsafe_context:
                    for column, (cell, _, _) in enumerate(cells):
                        if column >= len(column_labels):
                            column_labels.append('')
                        if TABLE_DENOMINATOR.search(cell):
                            label = TABLE_DENOMINATOR.sub('', cell).strip(' ()')
                            if label:
                                column_labels[column] = label
            elif not decoded.strip():
                if table_active:
                    table_awaiting_note = True
            elif table_active and (
                decoded.lstrip().lower().startswith(('note:', 'notes:'))
                or re.match(r'^\s*[*†‡§]\s', decoded)
            ):
                if self.unsafe_scope_cue.search(decoded):
                    mark_unsafe_scope()
            elif not decoded.lstrip().startswith('#') and table_active:
                table_active = False
                table_width = None
                table_shape_mismatch = False
                table_unsafe_context = False
                caption = ''
                column_labels = []
                denominators = {}
            if line_number > MAX_SCAN_LINES:
                truncated = True
                break
            line_start = len(text_bytes) if newline < 0 else newline + 1
            line_number += 1
        supported_alternates: dict[tuple[str, str], int] = {}
        for finding in findings:
            alternatives = finding['_possible_alternate_denominators']
            if len(alternatives) == 1:
                key = (finding['scope_label'], alternatives[0])
                supported_alternates[key] = supported_alternates.get(key, 0) + 1
        retained_findings = []
        for finding in findings:
            alternatives = finding.pop('_possible_alternate_denominators')
            supported = [
                alternate for alternate in alternatives
                if supported_alternates.get((finding['scope_label'], alternate), 0) >= 2
            ]
            alternate = supported[0] if len(supported) == 1 else None
            if alternate is not None:
                if len(scope_differences) >= MAX_SCOPE_DIFFERENCES:
                    truncated = True
                    retained_findings.append(finding)
                    continue
                scope_differences.append({
                    'id': f'table-scope-{len(scope_differences) + 1:04d}',
                    'type': 'POSSIBLE_ROW_SPECIFIC_DENOMINATOR',
                    'status': 'POSSIBLE_SAMPLE_FLOW_DIFFERENCE',
                    'reported_percent': finding['reported_percent'],
                    'numerator_exact': finding['numerator_exact'],
                    'column_denominator_exact': finding['denominator_exact'],
                    'compatible_alternate_denominators_exact': [alternate],
                    'scope_label': finding['scope_label'],
                    'table': finding['table'],
                    'source_anchors': finding['source_anchors'],
                    'interpretation': (
                        'Several percentages in this table column are compatible with one smaller row-specific '
                        'denominator, suggesting missing values or a subset.'
                    ),
                    'required_review': (
                        'Check item nonresponse and table footnotes to determine whether the smaller denominator is '
                        'the reported population for these rows.'
                    ),
                })
            else:
                retained_findings.append(finding)
        findings = retained_findings
        if truncated:
            limitations.append('A configured table scan or finding limit was reached; percentage checks may be incomplete.')
        return {
            'discoverer': self.name,
            'findings': findings,
            'possible_scope_differences': scope_differences,
            'checked_cells': checked,
            'tables_seen': tables_seen,
            'cells_scanned': cells_scanned,
            'supported': True,
            'scan_complete': not truncated and not coverage_incomplete,
            'limitations': list(dict.fromkeys(limitations)),
        }


class ExplicitExclusionFlowDiscoverer:
    """Locate a narrow flow sentence but refuse subtraction when overlap is unknown."""

    name = 'explicit_exclusion_flow_arithmetic_screen'

    def discover(
        self, text_bytes: bytes, page_map: list[dict[str, Any]],
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        ambiguous_relations: list[dict[str, Any]] = []
        line_start = 0
        line_number = 1
        line_limit = False
        incomplete = False
        while line_start < len(text_bytes):
            if line_number % 128 == 1:
                _check_audit_cancel(should_cancel)
            newline = text_bytes.find(b'\n', line_start)
            line_end = len(text_bytes) if newline < 0 else newline
            raw = text_bytes[line_start:line_end]
            if len(raw) <= MAX_SCAN_LINE_BYTES:
                decoded = raw.decode('utf-8')
                for match in EXCLUSION_FLOW.finditer(decoded):
                    excluded_text = match.group('exclusions')
                    parts = EXCLUSION_LIST_SPLIT.split(excluded_text)
                    exclusion_values = []
                    spans = []
                    cursor = 0
                    valid = 1 <= len(parts) <= MAX_FLOW_EXCLUSION_VALUES
                    for part in parts:
                        leading = LEADING_FLOW_NUMBER.match(part)
                        if leading is None:
                            valid = False
                            break
                        raw_number = leading.group('number')
                        value = _bounded_flow_number(raw_number)
                        if value is None:
                            valid = False
                            break
                        part_start = excluded_text.find(part, cursor)
                        cursor = part_start + len(part)
                        leading_offset = len(part) - len(part.lstrip())
                        number_start = match.start('exclusions') + part_start + leading_offset
                        spans.append((number_start, number_start + len(raw_number)))
                        exclusion_values.append(value)
                    if not valid:
                        continue
                    total = _bounded_flow_number(match.group('total'))
                    included = _bounded_flow_number(match.group('included'))
                    if total is None or included is None:
                        continue
                    if len(ambiguous_relations) >= 64:
                        line_limit = True
                        break
                    token_spans = [(match.start('total'), match.end('total'))]
                    token_spans.extend(spans)
                    token_spans.append((match.start('included'), match.end('included')))
                    anchors = []
                    for char_start, char_end in token_spans:
                        start_byte = line_start + len(decoded[:char_start].encode('utf-8'))
                        end_byte = line_start + len(decoded[:char_end].encode('utf-8'))
                        page_number, page_offset = _page_record(page_map, start_byte)
                        anchor = {
                            'text_file': 'extracted-text.txt',
                            'quote': decoded[char_start:char_end],
                            'start_byte': start_byte,
                            'end_byte': end_byte,
                            'line_number': line_number,
                            'context': decoded.strip()[:2000],
                        }
                        if page_number is not None:
                            anchor.update({'page_number': page_number,
                                           'page_offset_start_byte': page_offset,
                                           'page_offset_end_byte': page_offset + end_byte - start_byte})
                        anchors.append(anchor)
                    ambiguous_relations.append({
                        'id': f'ambiguous-flow-{len(ambiguous_relations) + 1:04d}',
                        'status': 'FLOW_RELATION_AMBIGUOUS',
                        'source_total_exact': str(total),
                        'excluded_values_exact': [str(value) for value in exclusion_values],
                        'reported_included_exact': str(included),
                        'source_anchors': anchors,
                        'interpretation': (
                            'A starting count, listed exclusions, and an included count were found, but the source text '
                            'does not establish that exclusions are disjoint, exhaustive, or from one analysis population.'
                        ),
                        'required_review': (
                            'Check overlap, sequence, population, attrition, and missing-data scope. No subtraction was performed.'
                        ),
                    })
            else:
                incomplete = True
            if line_limit or line_number >= MAX_SCAN_LINES:
                line_limit = True
                break
            line_start = len(text_bytes) if newline < 0 else newline + 1
            line_number += 1
        return {
            'discoverer': self.name,
            'candidate_anomalies': [],
            'ambiguous_relations': ambiguous_relations,
            'scan_complete': not line_limit and not incomplete and not ambiguous_relations,
            'limitations': (
                (['A configured explicit-flow scan limit was reached; flow scanning may be incomplete.'] if line_limit else [])
                + (['One or more lines exceeded the configured scan limit and were skipped.'] if incomplete else [])
                + (['A flow-shaped sentence had unresolved overlap or population scope; arithmetic was not performed.']
                   if ambiguous_relations else [])
            ),
        }


def capabilities() -> list[dict[str, Any]]:
    """List bounded paper checks and keep their interpretation limits explicit."""
    prose_formats = [
        'UTF-8 .txt', 'UTF-8 .md', 'UTF-8 .markdown',
        'born-digital .pdf with optional pypdf when OS worker limits are available',
    ]
    return [
        {
            'kind': 'explicit_count_marker_conflict_screen',
            'role': 'candidate_discovery_only',
            'formats': prose_formats,
            'patterns': ['n = integer', 'N = integer'],
            'limits': (
                '32 MiB source; PDF 500 pages, 16 MiB extracted text and 512 KiB/page; '
                'PDF worker 20-second wall timeout; pypdf is imported only when the OS applies both a 15-second CPU '
                'limit and 768 MiB address-space limit, otherwise PDF extraction is unavailable and no detector runs; '
                '512 count markers; 128 scope differences; 1,000,000 lines; 64 KiB per scanned line; 512 Markdown headings. '
                'JATS narrative assertions are not scanned until native source anchors are available.'
            ),
            'output_schema': 'schemas/paper-audit.schema.json',
            'example_input': 'examples/paper-audit/paper.md',
            'example_command': 'python -m researchwitness paper-audit examples/paper-audit/paper.md --output work/paper-audit',
            'does_not_prove': (
                'That differing counts refer to the same cohort or scope, that a count candidate is an error, '
                'or that a no-candidate scan establishes paper correctness. Markdown table count markers '
                'are recorded but not compared globally.'
            ),
        },
        {
            'kind': 'markdown_table_percentage_recomputation',
            'role': 'candidate_discovery_only',
            'formats': ['UTF-8 .md', 'UTF-8 .markdown'],
            'patterns': ['count (percentage) in one cell with an explicit n/N header in the same column'],
            'limits': (
                'Checks only rectangular pipe tables with an explicit same-column denominator; inconsistent row widths '
                'are skipped. Rows or denominators with local denominator/footnote cues are omitted and mark coverage '
                'incomplete. Uses ROUND_HALF_UP at the displayed precision; scans at most '
                '100,000 Markdown table cells. Repeated compatible smaller denominators are surfaced as scope '
                'differences, not arithmetic candidates.'
            ),
            'output_schema': 'schemas/paper-audit.schema.json',
            'does_not_prove': (
                'That the supplied table extraction preserves the publisher layout, that the denominator is the right '
                'analysis population when the paper states otherwise, or that any broader research conclusion is wrong.'
            ),
        },
        {
            'kind': 'jats_table_percentage_recomputation',
            'role': 'exact_arithmetic_candidate',
            'formats': ['JATS XML (.xml or .nxml)'],
            'patterns': ['count (percentage) cell with explicit applicable n/N column header'],
            'limits': (
                'Directly parses JATS table grids, nested headers, spans, captions, xrefs and footnotes. Uses '
                'ROUND_HALF_UP at the displayed precision. Skips malformed/ragged tables, spans affecting data cells, '
                'local/footnoted denominators, weighted/adjusted values, missing-data and overlap cues. Limits: '
                '32 MiB source, 250,000 elements, depth 64, 1,000 tables, 10,000 rows/table, '
                '256 columns/table, 50,000 table cells, and 16 MiB serialized model.'
            ),
            'output_schema': 'schemas/paper-audit.schema.json',
            'does_not_prove': (
                'That the source layout or table semantics were represented faithfully in the publisher article, '
                'or that a candidate affects any conclusion.'
            ),
        },
        {
            'kind': 'explicit_exclusion_flow_locator',
            'role': 'unresolved_question_locator',
            'formats': prose_formats,
            'patterns': ['one bounded sentence shape with a starting count, exclusions, and included count'],
            'limits': (
                'At most 1,000,000 lines of at most 64 KiB each and 64 listed exclusions per match. '
                'It never subtracts or emits an arithmetic candidate because overlap, exhaustiveness, and scope '
                'are not established by this sentence pattern.'
            ),
            'output_schema': 'schemas/paper-audit.schema.json',
            'does_not_prove': 'That exclusion counts are mutually exclusive, exhaustive, or from the same analysis population.',
        },
    ]


def _mapped_sample_flow_screen(document) -> tuple[dict[str, Any], dict[str, Any]]:
    mapped_results = map_jats_sample_flows(document, limit=MAX_ARITHMETIC_FINDINGS + 1)
    flow_results_truncated = len(mapped_results) > MAX_ARITHMETIC_FINDINGS
    mapped = mapped_results[:MAX_ARITHMETIC_FINDINGS]
    flows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for index, flow in enumerate(mapped, start=1):
        arithmetic = flow.arithmetic or {'status': flow.status, 'reason': flow.reason}
        flow_item = {
            'id': f'source-flow-{index:04d}',
            'status': flow.status,
            'reason': flow.reason,
            'source_anchor': asdict(flow.relation_anchor),
            'operands': [asdict(operand) for operand in flow.operands],
            'population': asdict(flow.population) if flow.population else None,
            'stages': [asdict(stage) for stage in flow.stages],
            'transitions': [asdict(transition) for transition in flow.transitions],
            'exclusions': [asdict(exclusion) for exclusion in flow.exclusions],
            'arithmetic_relation': (
                asdict(flow.arithmetic_relation) if flow.arithmetic_relation else None
            ),
            'arithmetic_status': arithmetic.get('status', flow.status),
        }
        flows.append(flow_item)
        candidate = arithmetic.get('candidate')
        if flow.status != 'FLOW_ARITHMETIC_CANDIDATE' or not isinstance(candidate, dict):
            continue
        total = next((operand for operand in flow.operands if operand.role == 'total'), None)
        included = next((operand for operand in flow.operands if operand.role == 'included'), None)
        exclusions = [operand for operand in flow.operands if operand.role == 'exclusion']
        if total is None or included is None or not exclusions:
            continue
        anchor_list = [asdict(operand.source_anchor) for operand in flow.operands]
        anchor_list.append(asdict(flow.relation_anchor))
        findings.append({
            'id': f'jats-sample-flow-{len(findings) + 1:04d}',
            'type': 'JATS_SAMPLE_FLOW_ARITHMETIC_MISMATCH',
            'status': 'CANDIDATE_ANOMALY',
            'source_total_exact': str(total.count),
            'excluded_values_exact': [str(operand.count) for operand in exclusions],
            'reported_included_exact': str(included.count),
            'expected_included_exact': str(candidate['expected_count']),
            'difference_exact': str(candidate['difference']),
            'source_anchors': anchor_list,
            'interpretation': (
                f"The explicit flow relation gives {candidate['expected_count']} included "
                f"{total.unit} after the listed exclusions, while the paragraph reports {included.count}."
            ),
            'required_review': (
                'Confirm the source anchors, count units, population, and explicit flow relation. '
                'This arithmetic candidate does not establish which count is wrong or whether any conclusion changes.'
            ),
        })

    statuses = [flow.status for flow in mapped]
    checked_statuses = {'FLOW_BALANCED', 'FLOW_ARITHMETIC_CANDIDATE'}
    has_checked = any(status in checked_statuses for status in statuses)
    has_unresolved = any(status not in checked_statuses for status in statuses) or flow_results_truncated
    if flow_results_truncated:
        status = 'INCOMPLETE'
    elif not mapped:
        status = 'NOT_APPLICABLE'
    elif has_checked and not has_unresolved:
        status = 'ELIGIBLE'
    elif any(item == 'FLOW_RELATION_AMBIGUOUS' for item in statuses) or has_checked:
        status = 'INCOMPLETE'
    else:
        status = 'UNSUPPORTED'
    reasons = list(dict.fromkeys(flow.reason for flow in mapped if flow.reason))
    if flow_results_truncated:
        reasons.append('FLOW_RESULT_LIMIT_REACHED')
    screen = {
        'detector_id': 'jats_sample_flow_arithmetic',
        'flows': flows,
        'findings': findings,
        'status': status,
        'potential_objects': len(mapped) + int(flow_results_truncated),
        'applicable_objects': len(mapped) + int(flow_results_truncated),
        'eligible_objects': sum(item in checked_statuses for item in statuses),
        'checked_objects': sum(item in checked_statuses for item in statuses),
        'skipped_objects': sum(item not in checked_statuses for item in statuses) + int(flow_results_truncated),
        'candidate_count': len(findings),
        'scan_complete': not has_unresolved and not flow_results_truncated,
        'limitations': reasons,
    }
    coverage_record = {
        **screen,
        'object_unit': 'source_mapped_flow_relation',
        'operand_unit': 'flow_count_operand',
        'potential_operands': (None if flow_results_truncated else
                               sum(len(flow.operands) for flow in mapped)),
        'checked_operands': sum(len(flow.operands) for flow in mapped if flow.status in checked_statuses),
        'skipped_operands': (None if flow_results_truncated else
                             sum(len(flow.operands) for flow in mapped if flow.status not in checked_statuses)),
    }
    return screen, coverage_record


_PRISMA_SINGLE_CUE = re.compile(
    r'\b(?:prisma|flow diagram|study selection flow|records identified)\b', re.IGNORECASE,
)
_PRISMA_STAGE_CUE = re.compile(
    r'\b(?:duplicates? removed|records? screened|full[- ]texts? assessed|'
    r'studies? included|qualitative synthesis|quantitative synthesis)\b', re.IGNORECASE,
)


def _prisma_synthesis_screen(document) -> tuple[dict[str, Any], dict[str, Any]]:
    """Check one explicitly labelled review-flow relation and locate the rest."""
    objects: list[dict[str, Any]] = []
    image_flow = False
    object_limit_reached = False

    def append_object(item: dict[str, Any]) -> bool:
        nonlocal object_limit_reached
        if len(objects) >= 256:
            object_limit_reached = True
            return False
        objects.append(item)
        return True

    for figure in document.figures:
        label_caption = figure.label + ' ' + figure.caption
        if not _PRISMA_SINGLE_CUE.search(label_caption):
            continue
        image_flow = image_flow or figure.graphic_present
        if not append_object({
            'kind': 'figure',
            'label': figure.label[:500],
            'caption': figure.caption[:2000],
            'graphic_present': figure.graphic_present,
            'source_anchor': asdict(figure.source_anchor),
        }):
            break
    for table in document.tables:
        if object_limit_reached:
            break
        label_caption = table.label + ' ' + table.caption
        stage_count = len(list(_PRISMA_STAGE_CUE.finditer(label_caption)))
        if _PRISMA_SINGLE_CUE.search(label_caption) or stage_count >= 2:
            if not append_object({
                'kind': 'table',
                'label': table.label[:500],
                'caption': table.caption[:2000],
                'source_anchor': asdict(table.source_anchor),
            }):
                break
    for paragraph in document.paragraphs:
        if object_limit_reached:
            break
        stage_count = len(list(_PRISMA_STAGE_CUE.finditer(paragraph.text)))
        if _PRISMA_SINGLE_CUE.search(paragraph.text) or stage_count >= 2:
            if not append_object({
                'kind': 'prose',
                'text': paragraph.text[:4000],
                'source_anchor': asdict(paragraph.source_anchor),
            }):
                break
    mapped_results = map_jats_prisma_relations(document, limit=257)
    relations_truncated = len(mapped_results) > 256
    mapped = mapped_results[:256]
    relation_dicts = [relation.to_dict() for relation in mapped]
    supported_statuses = {'PRISMA_FLOW_BALANCED', 'PRISMA_FLOW_ARITHMETIC_CANDIDATE'}
    checked_relations = [relation for relation in mapped if relation.status in supported_statuses]
    mapped_paths = {
        item['source_anchor']['element_path']
        for relation in relation_dicts for item in relation['source_anchors']
    }
    unsupported_image_objects = [
        item for item in objects
        if item['kind'] == 'figure' and item.get('graphic_present') is True
        and item['source_anchor']['element_path'] not in mapped_paths
    ]
    unhandled_objects = [
        item for item in objects
        if item['source_anchor']['element_path'] not in mapped_paths
        and item not in unsupported_image_objects
    ]
    reasons: list[str] = []
    if image_flow:
        reasons.append('UNSUPPORTED_IMAGE_FLOW')
    if relations_truncated or object_limit_reached:
        reasons.append('PRISMA_SOURCE_OBJECT_LIMIT')
    reasons.extend(
        relation.reason for relation in mapped if relation.reason is not None
    )
    if unhandled_objects:
        reasons.append('PRISMA_FLOW_RELATION_NOT_IMPLEMENTED')
    if not objects and not mapped:
        reasons.append('NO_PRISMA_OR_SYNTHESIS_FLOW_CUE')
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        status = 'ELIGIBLE' if checked_relations else 'NOT_APPLICABLE'
    elif checked_relations:
        status = 'INCOMPLETE'
    elif reasons == ['NO_PRISMA_OR_SYNTHESIS_FLOW_CUE']:
        status = 'NOT_APPLICABLE'
    else:
        status = 'UNSUPPORTED'
    scan_complete = not reasons or reasons == ['NO_PRISMA_OR_SYNTHESIS_FLOW_CUE']
    findings = []
    for relation in mapped:
        if relation.status != 'PRISMA_FLOW_ARITHMETIC_CANDIDATE':
            continue
        raw = relation.to_dict()
        anchors = [item['source_anchor'] for item in raw['source_anchors']]
        findings.append({
            'id': f'jats-prisma-flow-{len(findings) + 1:04d}',
            'type': 'JATS_PRISMA_FLOW_ARITHMETIC_MISMATCH',
            'status': 'CANDIDATE_ANOMALY',
            'records_identified_exact': raw['records_identified_exact'],
            'duplicates_removed_exact': raw['duplicates_removed_exact'],
            'reported_screened_exact': raw['records_screened_exact'],
            'expected_screened_exact': raw['expected_screened_exact'],
            'difference_exact': raw['difference_exact'],
            'source_anchors': anchors,
            'interpretation': (
                f"The labelled review sequence gives {relation.expected_screened} screened records after "
                f"removing {relation.duplicates_removed} duplicates from {relation.records_identified}, "
                f"while the source reports {relation.records_screened}."
            ),
            'required_review': (
                'Confirm that these are the same record set and source version. This arithmetic candidate '
                'does not verify downstream screening, study inclusion, or the review conclusions.'
            ),
        })
    known_operand_relations = [
        relation for relation in mapped
        if relation.records_identified is not None and relation.duplicates_removed is not None
        and relation.records_screened is not None
    ]
    skipped_relations = len(mapped) - len(checked_relations)
    extra_unchecked = (len(unhandled_objects) + len(unsupported_image_objects)
                       + int(relations_truncated or object_limit_reached))
    potential_objects = len(mapped) + extra_unchecked
    operand_potential = (None if len(known_operand_relations) != len(mapped)
                         else 3 * len(known_operand_relations))
    operand_checked = 3 * len(checked_relations)
    operand_skipped = (None if operand_potential is None else operand_potential - operand_checked)
    screen = {
        'detector_id': 'prisma_synthesis_flow',
        'status': status,
        'objects': objects[:256],
        'relations': relation_dicts,
        'findings': findings,
        'scan_complete': scan_complete,
        'limitations': reasons,
        'image_contents_read': False,
        'ocr_performed': False,
    }
    coverage_record = {
        'detector_id': 'prisma_synthesis_flow',
        'status': status,
        'reasons': reasons,
        'potential_objects': potential_objects,
        'applicable_objects': potential_objects,
        'eligible_objects': len(checked_relations),
        'checked_objects': len(checked_relations),
        'skipped_objects': skipped_relations + extra_unchecked,
        'candidate_count': len(findings),
        'object_unit': 'review_flow_source_object',
        'potential_operands': operand_potential,
        'checked_operands': operand_checked,
        'skipped_operands': operand_skipped,
        'candidate_operands': len(findings),
        'operand_unit': 'review_flow_count',
    }
    return screen, coverage_record


def _coverage_html(coverage: dict[str, Any] | None) -> str:
    if coverage is None:
        return (
            '<p>Granular table counts are available for source-mapped JATS input. '
            'This source format does not provide a structured table model.</p>'
        )
    paper_tables = coverage['paper']['tables']
    table_summary = (
        f"ResearchWitness found {paper_tables['discovered']} structured tables: "
        f"{paper_tables['structure_reliable']} with reliable grids and "
        f"{paper_tables['structure_unsupported']} with unsupported grids."
    )
    rows: list[str] = []
    for detector in coverage['detectors']:
        object_counts = detector['object_counts']
        if detector['scope'] == 'table':
            counts = detector['status_counts']
            checked = object_counts['checked']
            potential = object_counts['potential']
            description = (
                f"{checked}/{potential} tables checked; "
                f"{counts.get('ELIGIBLE', 0)} eligible, "
                f"{counts.get('INCOMPLETE', 0)} incomplete, "
                f"{counts.get('UNSUPPORTED', 0)} unsupported, "
                f"{counts.get('NOT_APPLICABLE', 0)} not applicable."
            )
            operand = detector['operand_counts']
            description += (
                f" Operands: {operand['checked']}/{operand['potential']} "
                f"{operand['unit'].replace('_', ' ')} checked."
            )
            table_items = []
            for table in detector['tables'][:100]:
                label = table['label'] or table['table_id'] or '(unlabelled table)'
                reason = '; '.join(table['skip_reasons'])
                suffix = f" — {reason}" if reason else ''
                table_items.append(
                    '<li>' + escape(label) + ': ' + escape(table['parser_status']) + ' / '
                    + escape(table['status']) + escape(suffix) + '</li>'
                )
            extra = (
                '<details><summary>Per-table status</summary><ul>' + ''.join(table_items) + '</ul></details>'
                if table_items else ''
            )
        else:
            description = f"{detector['status']}"
            if object_counts['potential'] is not None:
                description += f"; {object_counts['checked']}/{object_counts['potential']} objects checked"
            if detector['reasons']:
                description += '; ' + ', '.join(detector['reasons'])
            extra = ''
        rows.append(
            '<li><strong>' + escape(detector['detector_id']) + '</strong>: '
            + escape(description) + extra + '</li>'
        )
    return (
        '<p>' + escape(table_summary) + '</p><ul>' + ''.join(rows) + '</ul>'
        '<p>Counts describe only represented source objects and detector inputs. They do not establish exhaustive paper checking.</p>'
    )


def _html_report(report: dict[str, Any]) -> str:
    candidates = []
    for anomaly in report['candidate_anomalies']:
        assertions = []
        denominator_details = ''
        for anchor in anomaly['source_anchors']:
            role = anchor.get('role') if isinstance(anchor, dict) else None
            if isinstance(anchor, dict) and 'source_anchor' in anchor:
                anchor = anchor['source_anchor']
            if 'element_path' in anchor:
                location = anchor['source_file'] + ' · ' + anchor['element_path']
                if role:
                    location = role + ' · ' + location
                assertions.append(
                    '<li><p><strong>' + escape(location) + '</strong>: <code>'
                    + escape(anchor['quote']) + '</code></p></li>'
                )
            else:
                location = f"line {anchor['line_number']}"
                if 'page_number' in anchor:
                    location = f"PDF page {anchor['page_number']}, {location}"
                if 'section' in anchor:
                    location += ' · ' + anchor['section']
                assertions.append(
                    '<li><p><strong>' + escape(location) + '</strong>: <code>' +
                    escape(anchor['quote']) + '</code></p><blockquote>' +
                    escape(anchor['context']) + '</blockquote></li>'
                )
        if anomaly['type'] == 'CONFLICTING_EXPLICIT_COUNT_MARKERS':
            title = f"Different {anomaly['marker']} counts appear in separate passages"
            summary = 'Values found: ' + ', '.join(anomaly['values_exact']) + '.'
        elif anomaly['type'] == 'TABLE_PERCENTAGE_ARITHMETIC_MISMATCH':
            title = 'Possible table percentage arithmetic mismatch'
            summary = (
                f"The cell reports {anomaly['reported_percent']}%, while "
                f"{anomaly['numerator_exact']}/{anomaly['denominator_exact']} is "
                f"{anomaly['recomputed_percent']}% for {anomaly['scope_label'] or 'this column'}."
            )
        elif anomaly['type'] == 'EXPLICIT_EXCLUSION_FLOW_ARITHMETIC_MISMATCH':
            excluded = ' + '.join(anomaly['excluded_values_exact'])
            summary = (
                f"{anomaly['source_total_exact']} minus listed exclusions ({excluded}) is "
                f"{anomaly['expected_included_exact']}, but the passage says "
                f"{anomaly['reported_included_exact']} were included."
            )
            title = 'The listed sample exclusions do not add up to the included count'
        elif anomaly['type'] == 'STRUCTURED_TABLE_PERCENTAGE_ARITHMETIC_MISMATCH':
            title = 'Possible JATS table percentage arithmetic mismatch'
            summary = (
                f"Table {anomaly['table_id']} reports {anomaly['reported_percent']}%, while "
                f"{anomaly['numerator_exact']}/{anomaly['denominator_exact']} is "
                f"{anomaly['recomputed_percent']}% at the displayed precision."
            )
        else:
            title = 'A numeric passage needs review'
            summary = anomaly.get('interpretation', 'A supported screen found a numeric discrepancy candidate.')
        provenance = anomaly.get('denominator_provenance')
        if isinstance(provenance, dict):
            selected = provenance.get('selected_denominator')
            provenance_rows = []
            if isinstance(selected, dict):
                selected_anchor = selected.get('source_anchor', {})
                provenance_rows.append(
                    '<li><strong>Selected denominator:</strong> <code>'
                    + escape(str(selected.get('value_exact') or 'unresolved'))
                    + '</code> — ' + escape(selected.get('structural_source', 'explicit source'))
                    + (': <code>' + escape(selected_anchor.get('quote', '')) + '</code>'
                       if selected_anchor.get('quote') else '')
                    + '</li>'
                )
            for competing in provenance.get('rejected_competing_denominators', [])[:4]:
                anchor = competing.get('source_anchor', {})
                reasons = ', '.join(competing.get('rejection_reasons', [])) or 'lower semantic scope'
                provenance_rows.append(
                    '<li><strong>Competing denominator rejected:</strong> <code>'
                    + escape(str(competing.get('value_exact') or competing.get('raw_value') or 'unknown'))
                    + '</code> — ' + escape(reasons)
                    + (': <code>' + escape(anchor.get('quote', '')) + '</code>' if anchor.get('quote') else '')
                    + '</li>'
                )
            if provenance_rows:
                denominator_details = '<p><strong>Denominator provenance</strong></p><ul>' + ''.join(provenance_rows) + '</ul>'
        candidates.append(
            '<article><h3>' + escape(title) + '</h3><p><strong>Status:</strong> Candidate anomaly · requires review.</p><p>'
            + escape(summary) + '</p>' + denominator_details +
            '<p>This is a review candidate; the paper may give a different row denominator or an additional flow step.</p>'
            '<p>ResearchWitness has not determined whether this affects the paper\'s conclusions.</p>'
            '<ul>' + ''.join(assertions) + '</ul><p>' + escape(anomaly['required_review']) + '</p></article>'
        )
    if candidates:
        candidate_html = ''.join(candidates)
    elif report['discovery']['scan_complete'] and report['extraction']['status'] == 'TEXT_AVAILABLE':
        candidate_html = '<p>No candidate was found by the supported numeric screens.</p>'
    else:
        candidate_html = '<p>No candidate was identified, but extraction or scan coverage was incomplete.</p>'
    skipped_percentage_relations = []
    arithmetic_screens = report.get('arithmetic_screens', {})
    for detector_key in ('structured_table_percentages', 'cell_ratio_percentages'):
        screen = arithmetic_screens.get(detector_key, {})
        for relation in screen.get('relations', []):
            if relation.get('status') not in ('INCOMPLETE', 'UNSUPPORTED'):
                continue
            provenance = relation.get('denominator_provenance', {})
            if relation.get('denominator_scope_resolved') is False:
                explanation = 'Check not performed because denominator scope was not resolved.'
            else:
                explanation = 'Check not performed because this relationship is outside the supported scope.'
            reason = relation.get('primary_skip_reason')
            if reason:
                explanation += ' Reason: ' + reason + '.'
            competitors = provenance.get('rejected_competing_denominators', [])
            if reason == 'DENOMINATOR_AMBIGUOUS' and competitors:
                examples = [
                    str(item.get('value_exact') or item.get('raw_value') or 'unknown')
                    for item in competitors[:3]
                ]
                explanation += ' Competing explicit denominators: ' + ', '.join(examples) + '.'
            anchor = relation.get('source_anchor', {})
            location = anchor.get('element_path', '')
            quote = anchor.get('quote', '')
            skipped_percentage_relations.append(
                '<li><strong>' + escape(location) + '</strong>'
                + (': <code>' + escape(quote) + '</code>' if quote else '')
                + ' — ' + escape(explanation) + '</li>'
            )
            if len(skipped_percentage_relations) >= 64:
                break
        if len(skipped_percentage_relations) >= 64:
            break
    skipped_percentage_html = (
        '<ul>' + ''.join(skipped_percentage_relations) + '</ul>'
        if skipped_percentage_relations else '<p>No percentage relations were skipped.</p>'
    )
    scope_items = []
    for item in report['possible_scope_differences']:
        anchor_items = []
        for anchor in item['source_anchors']:
            location = f"line {anchor['line_number']}"
            if 'page_number' in anchor:
                location = f"PDF page {anchor['page_number']}, {location}"
            if 'section' in anchor:
                location += ' · ' + anchor['section']
            anchor_items.append(
                '<li><strong>' + escape(location) + ':</strong> <code>' + escape(anchor['quote'])
                + '</code> ' + escape(anchor['context']) + '</li>'
            )
        anchors = ''.join(anchor_items)
        if item['type'] == 'POSSIBLE_ROW_SPECIFIC_DENOMINATOR':
            description = (
                'Several values in one column fit a smaller denominator, which may reflect missing responses. '
                + item['interpretation']
            )
        else:
            description = item.get('interpretation', 'Counts may refer to different populations or study stages.')
        scope_items.append(
            '<article><h3>Possible difference in population or denominator</h3><p>'
            + escape(description) + '</p><ul>' + anchors + '</ul><p>'
            + escape(item['required_review']) + '</p></article>'
        )
    limitations = ''.join('<li>' + escape(item) + '</li>' for item in report['unsupported_checks'])
    warnings = ''.join('<li>' + escape(item) + '</li>' for item in report['extraction']['warnings'])
    source = report['source']
    eligibility_items = ''.join(
        '<li><strong>' + escape(item['detector_id']) + '</strong>: ' + escape(item['status'])
        + ((' — ' + escape(', '.join(item['reasons']))) if item['reasons'] else '')
        + ((' · table ' + escape(item['table_id'])) if item.get('table_id') else '')
        + '</li>' for item in report['detector_eligibility']
    )
    flow_items = ''.join(
        '<li><strong>' + escape(item['status']) + '</strong>: ' + escape(item['interpretation']) + '</li>'
        for item in report['arithmetic_screens']['sample_exclusion_flow'].get('ambiguous_relations', [])
    )
    structured_tables = report['arithmetic_screens']['structured_table_percentages']['tables']
    incomplete_tables = ''.join(
        '<li>Table ' + escape(item['table_id'] or '(unlabelled)') + ': '
        + escape(item['status']) + ((' — ' + escape(', '.join(item['reasons']))) if item['reasons'] else '')
        + '</li>' for item in structured_tables if item['status'] in ('INCOMPLETE', 'UNSUPPORTED')
    )
    markdown_table_screen = report['arithmetic_screens']['table_percentages']
    if markdown_table_screen.get('supported') and not markdown_table_screen.get('scan_complete'):
        incomplete_tables += ''.join('<li>' + escape(item) + '</li>'
                                     for item in markdown_table_screen.get('limitations', []))
    table_checking_incomplete = (
        report['source_capabilities']['tables'] == 'TABLE_STRUCTURE_UNSUPPORTED'
        or bool(incomplete_tables)
    )
    if report['extraction']['original_format'] == 'pdf':
        table_coverage_explanation = (
            'ResearchWitness could not reliably reconstruct PDF table headers, columns, and denominator scopes, '
            'so table arithmetic checks were not performed.'
        )
    elif report['extraction']['original_format'] == 'jats_xml':
        table_coverage_explanation = (
            'ResearchWitness could not reliably reconstruct the listed table structure or denominator scope, '
            'so arithmetic checks were skipped for those tables.'
        )
    elif report['extraction']['original_format'] in ('md', 'markdown'):
        table_coverage_explanation = (
            'One or more Markdown tables did not meet the strict rectangularity, denominator, or footnote rules; '
            'affected arithmetic checks were skipped.'
        )
    else:
        table_coverage_explanation = (
            'Plain-text input does not preserve table structure, so table arithmetic checks were not performed.'
        )
    model_file = report['paper_structure']['document_model']
    model_summary = (
        f"Structured document model: {model_file['section_count']} sections, "
        f"{model_file['paragraph_count']} narrative paragraphs, {model_file['table_count']} tables, "
        f"{model_file['figure_count']} figures. "
        f"Machine-readable structure: {escape(model_file['file'])}."
        if model_file else 'No canonical structured document artifact was created for this source format.'
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ResearchWitness paper screening — {escape(source['identifier'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:3rem auto;padding:0 1rem;line-height:1.55;color:#1c2430}}
article{{border-top:1px solid #aaa;padding:1rem 0}}blockquote,code{{background:#f2f4f6;padding:.3rem .5rem;overflow-wrap:anywhere}}
.notice{{border-left:4px solid #b66;padding:.7rem 1rem;background:#fff8ea}}dt{{font-weight:700}}dd{{margin-bottom:.6rem}}</style></head><body>
<h1>ResearchWitness paper screening report</h1>
<p>This run reports which detector contracts were eligible for the supplied source and which were not.</p>
<p class="notice">A review candidate is a lead for human review. Different values may describe different cohorts, denominators, timepoints, or analyses. This report does not establish that the paper is wrong or correct.</p>
<dl><dt>Source</dt><dd>{escape(source['identifier'])} · version {escape(source['version'])} · capture status: unverified</dd>
<dt>Extraction status</dt><dd>{escape(report['extraction']['status'])} · {escape(report['extraction']['extractor'])}</dd>
<dt>Screening result</dt><dd>{escape(report['decision'])}</dd>
<dt>Count assertions scanned</dt><dd>{len(report['discovery']['assertions'])}</dd>
<dt>Review candidates</dt><dd>{len(report['candidate_anomalies'])}</dd>
<dt>Possible scope or denominator differences</dt><dd>{len(report['possible_scope_differences'])}</dd></dl>
<h2>What this source could support</h2><p>{model_summary}</p>
<p>Prose capability: <strong>{escape(report['source_capabilities']['prose'])}</strong> · Table capability: <strong>{escape(report['source_capabilities']['tables'])}</strong></p>
<h2>Capability coverage</h2>{_coverage_html(report.get('coverage'))}
{('<p><strong>Table checking incomplete.</strong> ' + escape(table_coverage_explanation)
  + (' Details: <ul>' + incomplete_tables + '</ul>' if incomplete_tables else '') + '</p>')
  if table_checking_incomplete else ''}
<ul>{eligibility_items}</ul>
<h2>Review candidates</h2>{candidate_html}
<h2>Percentage checks not performed</h2>{skipped_percentage_html}
<h2>Flow questions left unresolved</h2>{'<ul>' + flow_items + '</ul>' if flow_items else '<p>None recorded.</p>'}
<h2>Possible scope or denominator differences</h2>{''.join(scope_items) if scope_items else '<p>None recorded.</p>'}
<h2>Extraction warnings</h2>{'<ul>' + warnings + '</ul>' if warnings else '<p>None recorded.</p>'}
<h2>Checks not supported in this run</h2><ul>{limitations}</ul>
<h2>Integrity and limits</h2><p>Source SHA-256: <code>{escape(source['sha256'])}</code><br>
Extracted-text SHA-256: <code>{escape(report['extraction']['text_sha256'])}</code></p>
<p>No candidate was promoted to a verified paper error. Source authenticity, claim meaning, subgroup identity, corrections, and the paper's overall correctness were not verified.</p>
</body></html>'''


def run_paper_audit(
    input_path: Path | str,
    output_dir: Path | str,
    identifier: str | None = None,
    version: str | None = None,
    *,
    progress_callback: Callable[[str], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Create a source-pinned report with per-detector eligibility and limits."""
    def stage(label: str) -> None:
        _check_audit_cancel(cancellation_check)
        if progress_callback is not None:
            progress_callback(label)

    stage('Reading source bytes')
    path = Path(input_path).absolute()
    source_bytes = Bundle(path.parent).read(path.name, MAX_SOURCE_BYTES)
    suffix = path.suffix.lower()
    source_name = 'source.pdf' if suffix == '.pdf' else 'source' + suffix
    jats_document = None
    jats_model_bytes = None
    stage('Extracting text and source structure')
    if suffix in ('.xml', '.nxml'):
        try:
            jats_document = parse_jats(source_bytes, source_name)
            jats_model_bytes = canonical(jats_document.to_dict()) + b'\n'
            if len(jats_model_bytes) > MAX_JATS_MODEL_BYTES:
                raise Invalid('Canonical JATS document model exceeded the configured 16 MiB limit')
            extracted = jats_document.text_projection()
            extraction_status = (
                'TEXT_AVAILABLE' if extracted.strip() or jats_document.tables else 'NO_EXTRACTABLE_TEXT'
            )
            extractor = 'bounded JATS/XML structure parser'
            page_map = []
            warnings = list(jats_document.extraction_warnings)
        except Invalid as exc:
            jats_document = None
            jats_model_bytes = None
            extracted = b''
            extraction_status = 'MALFORMED_OR_UNSUPPORTED'
            extractor = 'bounded JATS/XML structure parser'
            page_map = []
            warnings = [str(exc)]
    else:
        extracted, extraction_status, extractor, page_map, warnings = _extract_source(source_bytes, suffix)
    try:
        extracted.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Invalid('Extracted paper text is not valid UTF-8') from exc

    can_scan = extraction_status in ('TEXT_AVAILABLE', 'PARTIAL_TEXT') and jats_document is None
    discoverer: CandidateDiscoverer = ExplicitCountDiscoverer()
    if can_scan:
        stage('Scanning explicit count statements')
        discovery = discoverer.discover(
            extracted, page_map, suffix in ('.md', '.markdown'), cancellation_check,
        )
        stage('Checking Markdown table percentages')
        table_screen = TablePercentageDiscoverer().discover(
            extracted, page_map, suffix in ('.md', '.markdown'), cancellation_check,
        )
        stage('Locating explicit exclusion-flow questions')
        flow_screen = ExplicitExclusionFlowDiscoverer().discover(
            extracted, page_map, cancellation_check,
        )
    else:
        discovery = {
            'discoverer': discoverer.name, 'assertions': [], 'candidate_anomalies': [],
            'possible_scope_differences': [], 'table_count_assertions_not_cross_compared': 0,
            'sections': [], 'scan_complete': False,
            'limitations': [
                'Narrative count screening was not run because source-native JATS text anchors are not yet mapped.'
                if jats_document is not None else 'No supported text was available for numeric screening.'
            ],
        }
        table_screen = {
            'discoverer': TablePercentageDiscoverer.name, 'findings': [],
            'possible_scope_differences': [], 'checked_cells': 0, 'cells_scanned': 0,
            'supported': suffix in ('.md', '.markdown') and extraction_status not in UNAVAILABLE_EXTRACTION_STATUSES,
            'scan_complete': False,
            'limitations': ['No supported text was available for table screening.'],
        }
        flow_screen = {
            'discoverer': ExplicitExclusionFlowDiscoverer.name, 'candidate_anomalies': [],
            'ambiguous_relations': [], 'scan_complete': False,
            'limitations': [
                'Narrative flow screening was not run because source-native JATS text anchors are not yet mapped.'
                if jats_document is not None else 'No supported text was available for flow screening.'
            ],
        }

    stage('Checking structured JATS table percentages')
    structured_table_screen = (
        check_structured_table_percentages(jats_document)
        if jats_document is not None else {
            'detector_id': 'table_percentage_recomputation', 'findings': [], 'tables': [],
            'checked_cells': 0, 'relations': [], 'relation_telemetry': summarize_relations([]),
            'candidate_findings_omitted': 0,
            'scan_complete': True, 'limitations': [],
        }
    )
    if jats_document is not None:
        stage('Checking structured JATS ratios and summaries')
        ratio_screen = check_jats_cell_ratio_percentages(jats_document)
        statistics_screen = check_jats_sd_se_n_tables(jats_document)
        two_by_two_screen = check_jats_unadjusted_2x2_tables(jats_document)
        stage('Checking source-mapped flow relationships')
        source_flow_screen, source_flow_coverage = _mapped_sample_flow_screen(jats_document)
        prisma_screen, prisma_coverage = _prisma_synthesis_screen(jats_document)
        paper_coverage = build_paper_coverage(jats_document, [
            structured_table_screen, ratio_screen, statistics_screen,
            two_by_two_screen, source_flow_coverage, prisma_coverage,
        ])
    else:
        ratio_screen = {
            'detector_id': 'jats_cell_ratio_percentage_recomputation',
            'operand_unit': 'n_over_N_percent_cell', 'findings': [], 'tables': [],
            'potential_cells': 0, 'checked_cells': 0, 'skipped_cells': 0,
            'relations': [], 'relation_telemetry': summarize_relations([]), 'candidate_findings_omitted': 0,
            'scan_complete': False, 'limitations': ['SOURCE_FORMAT_NOT_JATS_XML'],
        }
        statistics_screen = {
            'detector_id': 'jats_sd_se_n_recomputation',
            'operand_unit': 'eligible_sd_se_n_row',
            'rounding_policy': 'not_applicable because source format is unsupported',
            'findings': [], 'tables': [],
            'scan_complete': False, 'limitations': ['SOURCE_FORMAT_NOT_JATS_XML'],
        }
        two_by_two_screen = {
            'detector_id': 'jats_unadjusted_2x2_odds_ratio',
            'operand_unit': 'explicit_2x2_row', 'findings': [], 'tables': [],
            'scan_complete': False, 'limitations': ['SOURCE_FORMAT_NOT_JATS_XML'],
        }
        source_flow_screen = {
            'detector_id': 'jats_sample_flow_arithmetic', 'flows': [], 'findings': [],
            'status': 'UNSUPPORTED', 'potential_objects': 0, 'applicable_objects': 0,
            'eligible_objects': 0, 'checked_objects': 0, 'skipped_objects': 0,
            'candidate_count': 0, 'scan_complete': False,
            'limitations': ['SOURCE_FORMAT_NOT_JATS_XML'],
        }
        prisma_screen = {
            'detector_id': 'prisma_synthesis_flow', 'status': 'UNSUPPORTED',
            'objects': [], 'relations': [], 'findings': [], 'scan_complete': False,
            'limitations': ['SOURCE_FORMAT_NOT_JATS_XML'],
            'image_contents_read': False, 'ocr_performed': False,
        }
        paper_coverage = None
    percentage_relation_telemetry = summarize_relations(
        structured_table_screen.get('relations', []) + ratio_screen.get('relations', [])
    )
    source_id = text(identifier or ('local:' + path.name), 2000)
    source_version = text(version or 'unspecified', 100)
    table_candidates = table_screen['findings']
    flow_candidates = flow_screen['candidate_anomalies']
    statistics_candidates = [
        {
            **finding,
            'id': f'jats-sd-se-n-{index:04d}',
            'status': 'CANDIDATE_ANOMALY',
            'type': 'JATS_SD_SE_N_ARITHMETIC_MISMATCH',
            'interpretation': (
                f"For {finding['row_identity']}, SE={finding['reported_se']} while "
                f"SD/sqrt(n) rounds to {finding['recomputed_se_at_display_precision']}."
            ),
            'required_review': (
                'Confirm that n, SD, and SE describe the same unweighted summary quantity and that the '
                'reported SE uses SD/sqrt(n). This arithmetic candidate does not establish which value is wrong.'
            ),
        }
        for index, finding in enumerate(statistics_screen['findings'], start=1)
    ]
    candidates = (
        discovery['candidate_anomalies'] + table_candidates + flow_candidates
        + structured_table_screen['findings'] + ratio_screen['findings']
        + statistics_candidates + two_by_two_screen['findings']
        + source_flow_screen['findings'] + prisma_screen['findings']
    )
    possible_scope_differences = (
        discovery['possible_scope_differences'] + table_screen.get('possible_scope_differences', [])
    )
    if jats_document is not None:
        scan_complete = all((
            structured_table_screen['scan_complete'],
            ratio_screen['scan_complete'],
            statistics_screen['scan_complete'],
            two_by_two_screen['scan_complete'],
            source_flow_screen['scan_complete'],
            prisma_screen['scan_complete'],
        ))
    else:
        scan_complete = (
            discovery['scan_complete'] and flow_screen['scan_complete']
            and (not table_screen['supported'] or table_screen['scan_complete'])
        )
    if extraction_status in UNAVAILABLE_EXTRACTION_STATUSES:
        decision = 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    elif candidates and scan_complete and extraction_status == 'TEXT_AVAILABLE':
        decision = 'CANDIDATES_FOUND'
    elif candidates:
        decision = 'CANDIDATES_FOUND_IN_INCOMPLETE_SCAN'
    elif scan_complete and extraction_status == 'TEXT_AVAILABLE':
        decision = 'NO_CANDIDATES_IN_SUPPORTED_SCAN'
    else:
        decision = 'SCAN_INCOMPLETE_NO_CANDIDATES'
    checks_attempted = []
    if can_scan:
        checks_attempted.extend([discoverer.name, ExplicitExclusionFlowDiscoverer.name])
        if table_screen['supported']:
            checks_attempted.append(TablePercentageDiscoverer.name)
    if jats_document is not None and jats_document.tables:
        checks_attempted.append('jats_table_percentage_recomputation')
    if jats_document is not None:
        checks_attempted.extend([
            'jats_cell_ratio_percentage_recomputation',
            'jats_sd_se_n_recomputation',
            'jats_sample_flow_arithmetic',
            'prisma_synthesis_flow',
            'jats_unadjusted_2x2_odds_ratio',
        ])

    source_format = 'jats_xml' if suffix in ('.xml', '.nxml') else suffix.lstrip('.')
    source_caps = source_capabilities(source_format, extraction_status)
    detector_eligibility = []
    if jats_document is not None:
        detector_eligibility.append(eligibility(
            'explicit_count_marker_scan', 'UNSUPPORTED', source_format,
            ['SOURCE_NATIVE_ANCHOR_UNAVAILABLE'],
        ))
    else:
        count_status = 'ELIGIBLE' if extraction_status == 'TEXT_AVAILABLE' else 'INCOMPLETE'
        detector_eligibility.append(eligibility(
            'explicit_count_marker_scan', count_status, source_format,
            [] if count_status == 'ELIGIBLE' else ['PROSE_TEXT_UNAVAILABLE_OR_PARTIAL'],
            checked_operands=len(discovery['assertions']),
        ))
    if jats_document is not None:
        for table_result in structured_table_screen['tables']:
            detector_eligibility.append(eligibility(
                'table_percentage_recomputation', table_result['status'], source_format,
                table_result['reasons'], table_result['table_id'], table_result['checked_cells'],
            ))
        if not structured_table_screen['tables']:
            detector_eligibility.append(eligibility(
                'table_percentage_recomputation', 'UNSUPPORTED', source_format,
                ['NO_JATS_TABLES_FOUND'],
            ))
        detector_eligibility.append(eligibility(
            'markdown_table_percentage_recomputation', 'UNSUPPORTED', source_format,
            ['SOURCE_FORMAT_NOT_MARKDOWN'],
        ))
    elif suffix in ('.md', '.markdown') and table_screen['supported']:
        detector_eligibility.append(eligibility(
            'table_percentage_recomputation', 'UNSUPPORTED', source_format,
            ['SOURCE_FORMAT_NOT_JATS_XML'],
        ))
        status = ('INCOMPLETE' if not table_screen['scan_complete'] else
                  ('ELIGIBLE' if table_screen.get('checked_cells', 0) else 'NOT_APPLICABLE'))
        detector_eligibility.append(eligibility(
            'markdown_table_percentage_recomputation', status, source_format,
            table_screen['limitations'] or (['NO_APPLICABLE_COUNT_PERCENT_CELLS'] if status == 'NOT_APPLICABLE' else []),
            checked_operands=table_screen['checked_cells'],
        ))
    else:
        table_reason = ('TABLE_STRUCTURE_UNSUPPORTED' if suffix == '.pdf'
                        else 'NO_STRUCTURED_TABLE_ADAPTER_FOR_SOURCE')
        detector_eligibility.append(eligibility(
            'table_percentage_recomputation', 'UNSUPPORTED', source_format, [table_reason],
        ))
        detector_eligibility.append(eligibility(
            'markdown_table_percentage_recomputation', 'UNSUPPORTED', source_format,
            ['SOURCE_FORMAT_NOT_MARKDOWN'],
        ))
    if jats_document is not None:
        flow_locator_status = 'UNSUPPORTED'
        flow_locator_reasons = ['SOURCE_NATIVE_ANCHOR_UNAVAILABLE']
    elif can_scan and flow_screen.get('ambiguous_relations'):
        flow_locator_status = 'INCOMPLETE'
        flow_locator_reasons = ['FLOW_RELATION_AMBIGUOUS']
    elif can_scan:
        flow_locator_status = 'NOT_APPLICABLE'
        flow_locator_reasons = ['NO_FLOW_SHAPED_SENTENCE_FOUND']
    else:
        flow_locator_status = 'INCOMPLETE'
        flow_locator_reasons = ['PROSE_TEXT_UNAVAILABLE_OR_PARTIAL']
    detector_eligibility.append(eligibility(
        'explicit_exclusion_flow_locator', flow_locator_status, source_format, flow_locator_reasons,
        checked_operands=len(flow_screen.get('ambiguous_relations', [])) * 2,
    ))
    detector_eligibility.append(eligibility(
        'explicit_sample_flow_arithmetic', 'UNSUPPORTED', source_format,
        ['EXPLICIT_FLOW_GRAPH_NOT_EXTRACTED'],
    ))
    detector_eligibility.append(eligibility(
        'two_by_two_effect_size_recomputation', 'UNSUPPORTED', source_format,
        ['SOURCE_RESULT_MAPPING_NOT_IMPLEMENTED'],
    ))
    detector_eligibility.append(eligibility(
        'cross_section_numeric_identity', 'UNSUPPORTED', source_format,
        ['IDENTITY_ASSERTION_EXTRACTION_NOT_IMPLEMENTED'],
    ))
    if jats_document is not None:
        for table_result in ratio_screen['tables']:
            detector_eligibility.append(eligibility(
                'jats_cell_ratio_percentage_recomputation', table_result['status'], source_format,
                table_result['skip_reasons'], table_result['table_id'], table_result['checked_objects'],
            ))
        if not ratio_screen['tables']:
            detector_eligibility.append(eligibility(
                'jats_cell_ratio_percentage_recomputation', 'NOT_APPLICABLE', source_format,
                ['NO_JATS_TABLES_FOUND'],
            ))
        for table_result in statistics_screen['tables']:
            detector_eligibility.append(eligibility(
                'jats_sd_se_n_recomputation', table_result['status'], source_format,
                [item['reason'] for item in table_result['skip_reasons']],
                table_result['table_id'], table_result['checked_rows'],
            ))
        if not statistics_screen['tables']:
            detector_eligibility.append(eligibility(
                'jats_sd_se_n_recomputation', 'NOT_APPLICABLE', source_format,
                ['NO_JATS_TABLES_FOUND'],
            ))
        checked_flow_operands = sum(
            len(item['operands']) for item in source_flow_screen['flows']
            if item['status'] in ('FLOW_BALANCED', 'FLOW_ARITHMETIC_CANDIDATE')
        )
        detector_eligibility.append(eligibility(
            'jats_sample_flow_arithmetic', source_flow_screen['status'], source_format,
            source_flow_screen['limitations'], checked_operands=checked_flow_operands,
        ))
        for table_result in two_by_two_screen['tables']:
            detector_eligibility.append(eligibility(
                'jats_unadjusted_2x2_odds_ratio', table_result['status'], source_format,
                [item['reason'] for item in table_result['skip_reasons']],
                table_result['table_id'], table_result['checked_objects'],
            ))
        if not two_by_two_screen['tables']:
            detector_eligibility.append(eligibility(
                'jats_unadjusted_2x2_odds_ratio', 'NOT_APPLICABLE', source_format,
                ['NO_JATS_TABLES_FOUND'],
            ))
        detector_eligibility.append(eligibility(
            'prisma_synthesis_flow', prisma_screen['status'], source_format,
            prisma_screen['limitations'],
            checked_operands=prisma_coverage['checked_operands'],
        ))
    else:
        for detector_id in (
            'jats_cell_ratio_percentage_recomputation',
            'jats_sd_se_n_recomputation',
            'jats_sample_flow_arithmetic',
            'jats_unadjusted_2x2_odds_ratio',
            'prisma_synthesis_flow',
        ):
            detector_eligibility.append(eligibility(
                detector_id, 'UNSUPPORTED', source_format, ['SOURCE_FORMAT_NOT_JATS_XML'],
            ))
    detector_eligibility.append(eligibility(
        'simple_rate_recomputation', 'UNSUPPORTED', source_format,
        ['EXPLICIT_RATE_OPERAND_MAPPING_NOT_IMPLEMENTED'],
    ))
    unsupported_checks = [
        'The count scan does not determine whether separate values refer to the same cohort, subgroup, or timepoint.',
        'Structured JATS count/percentage checks do not infer local denominators, row totals, column totals, or additive category semantics.',
        'The same-cell n/N (%) check accepts only bounded explicit ratios; category overlap is irrelevant to a cell-local quotient when its denominator and percentage base are explicit.',
        'Source-mapped sample-flow arithmetic is limited to one paragraph with explicit disjoint/exhaustive or sequential relation cues and common scope.',
        'PRISMA arithmetic checks only one explicitly labelled JATS record/duplicate/screened sequence; later review stages and figure contents remain unsupported.',
        'The source-mapped 2x2 odds-ratio check requires a one-row JATS table with four explicit event cells, timepoint, and a crude exposed-versus-unexposed estimate; other effect measures remain unsupported.',
        'The SD/SE/n screen is experimental and limited to simple unweighted JATS rows. CI methods, rate arithmetic, and cross-section identity extraction remain unsupported.',
        'PDF table arithmetic is unsupported because pypdf text extraction does not preserve a validated table grid.',
    ]
    if jats_document is not None:
        unsupported_checks.append(
            'JATS narrative count-marker comparison remains unsupported; source-mapped sample-flow checking is separately bounded.'
        )
    unsupported_checks = list(dict.fromkeys(
        unsupported_checks + table_screen.get('limitations', []) + flow_screen.get('limitations', [])
        + structured_table_screen.get('limitations', []) + ratio_screen.get('limitations', [])
        + statistics_screen.get('limitations', []) + source_flow_screen.get('limitations', [])
        + prisma_screen.get('limitations', [])
    ))[:16]

    document_artifact = None
    document_bytes = None
    if jats_document is not None:
        document_bytes = jats_model_bytes
        document_artifact = {
            'file': 'paper-document.json',
            'sha256': byte_hash(document_bytes),
            'model_version': jats_document.model_version,
            'section_count': len(jats_document.sections),
            'paragraph_count': len(jats_document.paragraphs),
            'table_count': len(jats_document.tables),
            'figure_count': len(jats_document.figures),
            'numeric_assertion_count': len(jats_document.numeric_assertions),
        }

    report = {
        'paper_audit_version': PAPER_AUDIT_VERSION,
        'decision': decision,
        'source': {
            'identifier': source_id,
            'version': source_version,
            'capture_status': 'unverified',
            'source_file': source_name,
            'sha256': byte_hash(source_bytes),
        },
        'extraction': {
            'status': extraction_status,
            'extractor': extractor,
            'original_format': source_format,
            'source_bytes': len(source_bytes),
            'text_file': 'extracted-text.txt',
            'text_sha256': byte_hash(extracted),
            'text_bytes': len(extracted),
            'page_count': len(page_map) if suffix == '.pdf' else None,
            'page_map': page_map,
            'warnings': warnings,
            'ocr_performed': False,
        },
        'paper_structure': {
            'sections': discovery['sections'] if jats_document is None else [],
            'layout_status': (
                'JATS_ELEMENT_PATHS_AND_TABLE_GRIDS' if jats_document is not None
                else ('JATS_STRUCTURE_UNAVAILABLE' if suffix in ('.xml', '.nxml')
                      else ('TEXT_OR_MARKDOWN_OFFSETS' if suffix != '.pdf'
                            else 'PDF_PAGE_AND_EXTRACTED_TEXT_OFFSETS_ONLY'))
            ),
            'document_model': document_artifact,
        },
        'source_capabilities': source_caps,
        'detector_eligibility': detector_eligibility,
        'detector_contracts': contract_registry(),
        'coverage': paper_coverage,
        'discovery': {
            'provider': 'deterministic_local_heuristic',
            'discoverer': discovery['discoverer'],
            'scan_complete': scan_complete,
            'assertions': discovery['assertions'],
            'candidate_anomalies': discovery['candidate_anomalies'],
            'possible_scope_differences': discovery['possible_scope_differences'],
            'table_count_assertions_not_cross_compared': discovery['table_count_assertions_not_cross_compared'],
            'limitations': discovery['limitations'],
        },
        'arithmetic_screens': {
            'table_percentages': table_screen,
            'structured_table_percentages': structured_table_screen,
            'cell_ratio_percentages': ratio_screen,
            'percentage_relation_telemetry': percentage_relation_telemetry,
            'sd_se_n_statistics': statistics_screen,
            'source_mapped_sample_flow': source_flow_screen,
            'prisma_synthesis_flow': prisma_screen,
            'jats_unadjusted_2x2_odds_ratio': two_by_two_screen,
            'sample_exclusion_flow': flow_screen,
        },
        'candidate_anomalies': candidates,
        'possible_scope_differences': possible_scope_differences,
        'checks_attempted': checks_attempted,
        'verified_findings': [],
        'unresolved_questions': [item['required_review'] for item in candidates],
        'unsupported_checks': unsupported_checks,
        'known_corrections': {'status': 'NOT_CHECKED'},
        'paper_error_established': False,
        'meaning': (
            'This is a bounded screening report. Numeric candidates require human review and may reflect different '
            'scopes, denominators, missing data, or extraction structure. No candidate establishes a paper error, '
            'and no-candidate results do not establish paper correctness.'
        ),
    }

    stage('Writing source copy and reproducible report')
    output = Path(output_dir).absolute()
    require(not output.exists(), 'Paper-audit output directory already exists')
    output.mkdir(parents=True)
    (output / source_name).write_bytes(source_bytes)
    (output / 'extracted-text.txt').write_bytes(extracted)
    if document_bytes is not None:
        (output / 'paper-document.json').write_bytes(document_bytes)
    (output / 'report.json').write_bytes(canonical(report) + b'\n')
    (output / 'report.html').write_text(_html_report(report), encoding='utf-8')
    return {
        'decision': report['decision'],
        'paper_audit': str(output / 'report.json'),
        'html_report': str(output / 'report.html'),
        'source_copy': str(output / source_name),
        'extracted_text': str(output / 'extracted-text.txt'),
        'paper_document': str(output / document_artifact['file']) if document_artifact else None,
        'candidate_anomalies': len(candidates),
        'possible_scope_differences': len(possible_scope_differences),
        'checks_attempted': checks_attempted,
        'paper_error_established': False,
    }
