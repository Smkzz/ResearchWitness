"""Bounded paper-text extraction and conservative numeric-anomaly screening.

This module is an untrusted discovery/ingestion layer. Its output is a screening
report, not a deterministic proof that a research claim is false.
"""
from __future__ import annotations

from bisect import bisect_right
from html import escape
import io
import json
from pathlib import Path
import re
from typing import Any, Protocol

from .strict import Bundle, Invalid, byte_hash, canonical, require, text

PAPER_AUDIT_VERSION = '0.1'
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_EXTRACTED_TEXT_BYTES = 16 * 1024 * 1024
MAX_PDF_PAGE_BYTES = 512 * 1024
MAX_COUNT_ASSERTIONS = 512
MAX_SCAN_LINE_BYTES = 64 * 1024
MAX_SCAN_LINES = 1_000_000
MAX_MARKDOWN_SECTIONS = 512

COUNT_MARKER = re.compile(
    rb'(?<![A-Za-z0-9_])(?P<marker>[nN])[ \t]{0,32}=[ \t]{0,32}'
    rb'(?P<value>[0-9]{1,9})(?![0-9]|[,.][0-9]|/[0-9]|[eE][+-]?[0-9])'
)
MARKDOWN_HEADING = re.compile(rb'^ {0,3}(?P<marks>#{1,6})[ \t]+(?P<title>.*?)[ \t]*#*[ \t]*$')


class CandidateDiscoverer(Protocol):
    """Provider-neutral interface for untrusted candidate-generation adapters."""

    name: str

    def discover(
        self, text_bytes: bytes, page_map: list[dict[str, Any]], markdown: bool,
    ) -> dict[str, Any]: ...


def _extract_pdf(source_bytes: bytes) -> tuple[bytes, str, str, list[dict[str, Any]], list[str]]:
    try:
        import pypdf
        from pypdf import PdfReader
    except ImportError:
        return b'', 'PARSER_UNAVAILABLE', 'pypdf (optional paper extra)', [], [
            'Install researchwitness[paper] to extract PDF text. No OCR was attempted.'
        ]

    try:
        reader = PdfReader(io.BytesIO(source_bytes), strict=True)
        require(not reader.is_encrypted, 'Encrypted PDFs are not supported')
        page_count = len(reader.pages)
        require(1 <= page_count <= MAX_PDF_PAGES,
                f'PDF must have 1 to {MAX_PDF_PAGES} pages')
        page_texts: list[bytes] = []
        page_records: list[dict[str, Any]] = []
        total = 0
        warnings: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ''
            require(type(extracted) is str, 'PDF parser returned non-text page content')
            page_bytes = extracted.encode('utf-8')
            require(len(page_bytes) <= MAX_PDF_PAGE_BYTES,
                    f'PDF page {page_number} exceeds the extracted-text limit')
            total += len(page_bytes)
            require(total <= MAX_EXTRACTED_TEXT_BYTES,
                    'PDF extracted-text size limit exceeded')
            page_texts.append(page_bytes)
            page_records.append({
                'page_number': page_number,
                'character_count': len(extracted),
                'status': 'TEXT_EXTRACTED' if extracted.strip() else 'NO_EXTRACTABLE_TEXT',
            })

        separator = b'\n\f\n'
        chunks: list[bytes] = []
        offset = 0
        for index, page_bytes in enumerate(page_texts):
            record = page_records[index]
            record['text_start_byte'] = offset
            record['text_end_byte'] = offset + len(page_bytes)
            chunks.append(page_bytes)
            offset += len(page_bytes)
            if index + 1 < len(page_texts):
                chunks.append(separator)
                offset += len(separator)
        require(offset <= MAX_EXTRACTED_TEXT_BYTES,
                'PDF extracted-text size limit exceeded')
        output = b''.join(chunks)
        empty_pages = [record['page_number'] for record in page_records
                       if record['status'] == 'NO_EXTRACTABLE_TEXT']
        if len(empty_pages) == page_count:
            status = 'NO_EXTRACTABLE_TEXT'
            warnings.append(
                'No text was extracted. Pages may be image-only or use unsupported encodings; no OCR was attempted.'
            )
        elif empty_pages:
            status = 'PARTIAL_TEXT'
            warnings.append('No extractable text on physical PDF pages: ' + ', '.join(map(str, empty_pages)))
        else:
            status = 'TEXT_AVAILABLE'
        return output, status, f'pypdf {pypdf.__version__}', page_records, warnings
    except Invalid:
        # A configured extraction bound or unsupported encrypted document is a
        # reportable ingestion outcome. Preserve the original input, but do not
        # run a detector over incomplete output.
        return b'', 'LIMIT_OR_UNSUPPORTED', f'pypdf {pypdf.__version__}', [], [
            'PDF extraction stopped at a configured limit or unsupported document feature. '
            'The original PDF was preserved; extracted text is incomplete and no OCR was attempted.'
        ]
    except Exception as exc:
        # Parser diagnostics may include attacker-controlled document strings.
        return b'', 'MALFORMED_OR_UNSUPPORTED', f'pypdf {pypdf.__version__}', [], [
            'PDF extraction failed (' + type(exc).__name__ + '). No OCR or repair was attempted.'
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
    """Find conflicting explicit n=/N= integers; leave cohort identity unresolved."""

    name = 'explicit_count_marker_scan'

    def discover(
        self, text_bytes: bytes, page_map: list[dict[str, Any]], markdown: bool,
    ) -> dict[str, Any]:
        assertions: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        overlong_lines = 0
        truncated = False
        line_start = 0
        line_number = 1
        active_section: str | None = None
        while line_start < len(text_bytes):
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
                    assertions.append({
                        'id': f'count-{len(assertions) + 1:04d}',
                        'kind': 'explicit_count_marker',
                        'marker': marker,
                        'surface_value': match.group('value').decode('ascii'),
                        'value_exact': str(int(match.group('value'))),
                        'anchor': anchor,
                    })
            if truncated:
                break
            line_start = len(text_bytes) if newline < 0 else newline + 1
            line_number += 1

        groups: dict[str, list[dict[str, Any]]] = {'n': [], 'N': []}
        for assertion in assertions:
            groups[assertion['marker']].append(assertion)
        anomalies = []
        for marker, group in groups.items():
            distinct = sorted({item['value_exact'] for item in group}, key=int)
            if len(distinct) > 1:
                anomalies.append({
                    'id': f'conflicting-{marker}-values',
                    'type': 'CONFLICTING_EXPLICIT_COUNT_MARKERS',
                    'status': 'CANDIDATE_ANOMALY',
                    'marker': marker,
                    'values_exact': distinct,
                    'assertion_ids': [item['id'] for item in group],
                    'source_anchors': [item['anchor'] for item in group],
                    'interpretation': (
                        'Different integers follow the same case-sensitive marker. This scan cannot tell whether '
                        'they refer to the same population, subgroup, timepoint, analysis, or definition.'
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
        if truncated:
            limitations.append('A configured assertion or section limit was reached; scanning may be incomplete.')
        if line_number > MAX_SCAN_LINES:
            limitations.append(f'The {MAX_SCAN_LINES}-line scan limit was reached.')
        limitations.extend([
            'Only explicit n = integer and N = integer patterns were scanned.',
            'Marker identity does not establish that assertions describe the same cohort or quantity.',
            'No p-values, confidence intervals, tables, equations, citations, methods, or conclusions were checked.',
        ])
        return {
            'discoverer': self.name,
            'assertions': assertions,
            'candidate_anomalies': anomalies,
            'sections': sections,
            'scan_complete': not truncated and overlong_lines == 0,
            'limitations': limitations,
        }


def capabilities() -> list[dict[str, Any]]:
    """Describe the supported paper-screening mechanism without implying proof coverage."""
    return [{
        'kind': 'explicit_count_marker_conflict_screen',
        'role': 'candidate_discovery_only',
        'formats': ['UTF-8 .txt', 'UTF-8 .md', 'UTF-8 .markdown', 'born-digital .pdf with optional pypdf'],
        'patterns': ['n = integer', 'N = integer'],
        'limits': (
            '32 MiB source; PDF 500 pages, 16 MiB extracted text and 512 KiB/page; '
            '512 count markers; 1,000,000 lines; 64 KiB per scanned line; 512 Markdown headings.'
        ),
        'output_schema': 'schemas/paper-audit.schema.json',
        'example_input': 'examples/paper-audit/paper.md',
        'example_command': (
            'python -m researchwitness paper-audit examples/paper-audit/paper.md '
            '--output work/paper-audit'
        ),
        'does_not_prove': (
            'That conflicting values refer to the same cohort or scope, that any candidate is an error, '
            'or that a no-candidate scan establishes paper correctness. Tables, citations, equations, '
            'statistics, methods, code, figures, conclusions, and corrections are not checked.'
        ),
    }]


def _html_report(report: dict[str, Any]) -> str:
    candidates = []
    for anomaly in report['candidate_anomalies']:
        assertions = []
        for anchor in anomaly['source_anchors']:
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
        candidates.append(
            '<article><h3>Different values follow the ' + escape(anomaly['marker']) + '= marker</h3>'
            '<p>Values found: ' + escape(', '.join(anomaly['values_exact'])) +
            '. This is a candidate for review; the passages may describe different groups or analyses.</p>'
            '<ul>' + ''.join(assertions) + '</ul><p>' + escape(anomaly['required_review']) + '</p></article>'
        )
    if candidates:
        candidate_html = ''.join(candidates)
    elif report['discovery']['scan_complete'] and report['extraction']['status'] == 'TEXT_AVAILABLE':
        candidate_html = '<p>No conflict was found in the supported marker scan.</p>'
    else:
        candidate_html = '<p>No candidate was identified, but extraction or scan coverage was incomplete.</p>'
    limitations = ''.join('<li>' + escape(item) + '</li>' for item in report['discovery']['limitations'])
    warnings = ''.join('<li>' + escape(item) + '</li>' for item in report['extraction']['warnings'])
    source = report['source']
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ResearchWitness paper screening — {escape(source['identifier'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:3rem auto;padding:0 1rem;line-height:1.55;color:#1c2430}}
article{{border-top:1px solid #aaa;padding:1rem 0}}blockquote,code{{background:#f2f4f6;padding:.3rem .5rem;overflow-wrap:anywhere}}
.notice{{border-left:4px solid #b66;padding:.7rem 1rem;background:#fff8ea}}dt{{font-weight:700}}dd{{margin-bottom:.6rem}}</style></head><body>
<h1>ResearchWitness paper screening report</h1>
<p>This run searched extracted paper text for explicit <code>n = integer</code> and <code>N = integer</code> markers.</p>
<p class="notice">A candidate anomaly is a lead for human review. Different values may describe different cohorts, subgroups, timepoints, or analyses. This report does not establish that the paper is wrong or correct.</p>
<dl><dt>Source</dt><dd>{escape(source['identifier'])} · version {escape(source['version'])} · capture status: unverified</dd>
<dt>Extraction status</dt><dd>{escape(report['extraction']['status'])} · {escape(report['extraction']['extractor'])}</dd>
<dt>Screening result</dt><dd>{escape(report['decision'])}</dd>
<dt>Count assertions scanned</dt><dd>{len(report['discovery']['assertions'])}</dd>
<dt>Candidate anomalies</dt><dd>{len(report['candidate_anomalies'])}</dd></dl>
<h2>Candidate anomalies</h2>{candidate_html}
<h2>Extraction warnings</h2>{'<ul>' + warnings + '</ul>' if warnings else '<p>None recorded.</p>'}
<h2>Checks not run</h2><ul>{limitations}</ul>
<h2>Integrity and limits</h2><p>Source SHA-256: <code>{escape(source['sha256'])}</code><br>
Extracted-text SHA-256: <code>{escape(report['extraction']['text_sha256'])}</code></p>
<p>Source authenticity, PDF text accuracy, claim meaning, subgroup identity, corrections, and the paper's overall correctness were not verified.</p>
</body></html>'''


def run_paper_audit(
    input_path: Path | str,
    output_dir: Path | str,
    identifier: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Create a reproducible screening report for UTF-8 text or a born-digital PDF."""
    path = Path(input_path).absolute()
    source_bytes = Bundle(path.parent).read(path.name, MAX_SOURCE_BYTES)
    suffix = path.suffix.lower()
    extracted, extraction_status, extractor, page_map, warnings = _extract_source(source_bytes, suffix)
    try:
        extracted.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Invalid('Extracted paper text is not valid UTF-8') from exc

    discoverer: CandidateDiscoverer = ExplicitCountDiscoverer()
    discovery = discoverer.discover(extracted, page_map, suffix in ('.md', '.markdown'))
    if extraction_status in (
        'PARSER_UNAVAILABLE', 'MALFORMED_OR_UNSUPPORTED', 'LIMIT_OR_UNSUPPORTED', 'NO_EXTRACTABLE_TEXT'
    ):
        discovery = {
            'discoverer': discoverer.name,
            'assertions': [],
            'candidate_anomalies': [],
            'sections': [],
            'scan_complete': False,
            'limitations': discovery['limitations'],
        }

    source_name = 'source.pdf' if suffix == '.pdf' else 'source' + suffix
    source_id = text(identifier or ('local:' + path.name), 2000)
    source_version = text(version or 'unspecified', 100)
    candidates = discovery['candidate_anomalies']
    if extraction_status in (
        'PARSER_UNAVAILABLE', 'MALFORMED_OR_UNSUPPORTED', 'LIMIT_OR_UNSUPPORTED', 'NO_EXTRACTABLE_TEXT'
    ):
        decision = 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    elif candidates and discovery['scan_complete'] and extraction_status == 'TEXT_AVAILABLE':
        decision = 'CANDIDATES_FOUND'
    elif candidates:
        decision = 'CANDIDATES_FOUND_IN_INCOMPLETE_SCAN'
    elif discovery['scan_complete'] and extraction_status == 'TEXT_AVAILABLE':
        decision = 'NO_CANDIDATES_IN_SUPPORTED_SCAN'
    else:
        decision = 'SCAN_INCOMPLETE_NO_CANDIDATES'

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
            'original_format': suffix.lstrip('.'),
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
            'sections': discovery['sections'],
            'layout_status': ('TEXT_OR_MARKDOWN_OFFSETS' if suffix != '.pdf'
                              else 'PDF_PAGE_AND_EXTRACTED_TEXT_OFFSETS_ONLY'),
        },
        'discovery': {
            'provider': 'deterministic_local_heuristic',
            'discoverer': discovery['discoverer'],
            'scan_complete': discovery['scan_complete'],
            'assertions': discovery['assertions'],
            'limitations': discovery['limitations'],
        },
        'candidate_anomalies': candidates,
        'checks_attempted': [discoverer.name] if extraction_status in ('TEXT_AVAILABLE', 'PARTIAL_TEXT') else [],
        'verified_findings': [],
        'unresolved_questions': [item['required_review'] for item in candidates],
        'unsupported_checks': [
            'All claim semantics beyond explicit n/N count markers.',
            'Arithmetic and percentage checks across tables and prose.',
            'Statistical recomputation, citations, equations, units, methods, code, figures, and corrections.',
        ],
        'known_corrections': {'status': 'NOT_CHECKED'},
        'paper_error_established': False,
        'meaning': (
            'This is a bounded screening report. The count-marker scan proposes candidates only and may miss errors; '
            'different n/N values can be correct when they refer to different scopes. No candidate proves a paper error.'
        ),
    }

    output = Path(output_dir).absolute()
    require(not output.exists(), 'Paper-audit output directory already exists')
    output.mkdir(parents=True)
    (output / source_name).write_bytes(source_bytes)
    (output / 'extracted-text.txt').write_bytes(extracted)
    (output / 'report.json').write_bytes(canonical(report) + b'\n')
    (output / 'report.html').write_text(_html_report(report), encoding='utf-8')
    return {
        'decision': report['decision'],
        'paper_audit': str(output / 'report.json'),
        'html_report': str(output / 'report.html'),
        'source_copy': str(output / source_name),
        'extracted_text': str(output / 'extracted-text.txt'),
        'candidate_anomalies': len(candidates),
        'paper_error_established': False,
    }
