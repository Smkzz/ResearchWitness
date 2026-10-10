"""Paper-screening tests assert narrow candidate behavior and its limits."""
from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from researchwitness.paper_audit import capabilities, run_paper_audit
from researchwitness.strict import Invalid
from researchwitness import _pdf_worker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/paper-audit.schema.json').read_text(encoding='utf-8'))
SCHEMA_VALIDATOR = Draft202012Validator(SCHEMA)
requires_posix_pdf_limits = pytest.mark.skipif(
    os.name == 'nt',
    reason='native Windows PDF parsing is fail-closed without qualified worker memory limits',
)


def test_capability_registry_labels_paper_scan_as_candidate_discovery_only():
    screens = capabilities()

    assert len(screens) == 4
    assert screens[0]['role'] == 'candidate_discovery_only'
    assert 'when OS worker limits are available' in screens[0]['formats'][-1]
    assert 'otherwise PDF extraction is unavailable and no detector runs' in screens[0]['limits']
    assert screens[2]['kind'] == 'jats_table_percentage_recomputation'
    assert screens[3]['role'] == 'unresolved_question_locator'
    assert 'same cohort or scope' in screens[0]['does_not_prove']


@pytest.mark.parametrize('token', [
    b'n=20/30', b'n=20-30', b'n=20\xe2\x80\x9030', b'n=20\xe2\x80\x9330',
    b'n=20 \xe2\x80\x93 30', b'n=20 \xe2\x88\x92 30',
    b'n=20 \xe2\x81\x84 30', b'n=20 \xe2\x88\x95 30',
    'n=20\u00a0–\u00a030'.encode(), 'n=20\u202f–\u202f30'.encode(),
    'n=20\u00a0⁄\u00a030'.encode(), 'n=20\u202f∕\u202f30'.encode(),
])
def test_pdf_count_marker_does_not_take_the_left_number_from_a_range(token):
    from researchwitness.paper_audit import COUNT_MARKER

    match = COUNT_MARKER.search(token)
    assert match is None or match.group('value') != b'20'


@pytest.mark.parametrize('token', [
    'N=20 – 30', 'N=20 − 30', 'N=20 ⁄ 30', 'N=20 ∕ 30',
    'N=20\u00a0–\u00a030', 'N=20\u202f–\u202f30',
    'N=20\u00a0⁄\u00a030', 'N=20\u202f∕\u202f30',
])
def test_unicode_count_ranges_are_skipped_and_mark_scan_incomplete(tmp_path, token):
    _, report, _ = _run(tmp_path, f'{token}\nN=18\n'.encode('utf-8'))

    assert [item['value_exact'] for item in report['discovery']['assertions']] == ['18']
    assert report['discovery']['candidate_anomalies'] == []
    assert report['discovery']['scan_complete'] is False
    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert any('range or fraction marker' in item for item in report['discovery']['limitations'])


def _run(tmp_path: Path, content: bytes, suffix: str = '.txt', **kwargs):
    source = tmp_path / ('paper' + suffix)
    source.write_bytes(content)
    output = tmp_path / 'screening'
    result = run_paper_audit(source, output, **kwargs)
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert not list(SCHEMA_VALIDATOR.iter_errors(report))
    return result, report, output


def _skip_if_worker_limits_unavailable(report: dict) -> None:
    warnings = report.get('extraction', {}).get('warnings', [])
    if any(
        'could not apply the required worker CPU and memory limits' in warning
        for warning in warnings if isinstance(warning, str)
    ):
        pytest.skip('this OS did not allow the isolated PDF worker limits')


def test_text_conflict_is_candidate_with_byte_exact_source_anchors(tmp_path):
    content = 'Résumé. Group A: n = 20.\nGroup B: n = 18.\n'.encode('utf-8')

    result, report, output = _run(tmp_path, content, identifier='doi:10.example/test', version='v2')

    assert result['decision'] == 'CANDIDATES_FOUND'
    assert result['candidate_anomalies'] == 1
    assert report['paper_error_established'] is False
    assert report['verified_findings'] == []
    assert (output / 'source.txt').read_bytes() == content
    assert (output / 'extracted-text.txt').read_bytes() == content
    anomaly = report['candidate_anomalies'][0]
    assert anomaly['status'] == 'CANDIDATE_ANOMALY'
    assert anomaly['values_exact'] == ['18', '20']
    for anchor in anomaly['source_anchors']:
        start = anchor['start_byte']
        end = anchor['end_byte']
        assert content[start:end].decode('utf-8') == anchor['quote']


def test_same_values_and_other_numeric_forms_do_not_create_conflict(tmp_path):
    content = (
        'Group A n=20. Group B n = 020. Total N = 1,200. A ratio n = 0.5. '
        'Scientific n=1e3. Fraction n=1/2.\n'
    ).encode('utf-8')

    _, report, _ = _run(tmp_path, content)

    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert report['candidate_anomalies'] == []
    assert [item['value_exact'] for item in report['discovery']['assertions']] == ['20', '20']
    assert report['discovery']['scan_complete'] is False
    assert any('range or fraction marker' in item for item in report['discovery']['limitations'])


def test_spaced_thousands_counts_are_not_partially_read_as_distinct_values(tmp_path):
    content = 'Group A n=10 000. Group B n=9 000.\n'.encode('utf-8')

    _, report, _ = _run(tmp_path, content)

    assert report['candidate_anomalies'] == []
    assert report['discovery']['assertions'] == []


def test_spaced_thousands_table_denominator_does_not_create_false_mismatch(tmp_path):
    source_text = (
        '| Outcome | All (n=10 000) |\n'
        '| --- | ---: |\n'
        '| Event, n (%) | 1 (0.01%) |\n'
    )

    _, report, _ = _run(tmp_path, source_text.encode('utf-8'), '.md')

    assert report['arithmetic_screens']['table_percentages']['findings'] == []


def test_long_utf8_line_context_keeps_valid_text_and_byte_anchors(tmp_path):
    line = 'é' * 1200 + ' n=20 ' + 'x' * 1000 + ' n=18\n'
    source_bytes = line.encode('utf-8')

    _, report, _ = _run(tmp_path, source_bytes)

    assert report['decision'] == 'CANDIDATES_FOUND'
    for anchor in report['candidate_anomalies'][0]['source_anchors']:
        assert source_bytes[anchor['start_byte']:anchor['end_byte']].decode('utf-8') == anchor['quote']
        assert '�' not in anchor['context']


def test_marker_quote_accepts_maximum_bounded_horizontal_spacing(tmp_path):
    content = ('n' + ' ' * 32 + '=' + '\t' * 32 + '123456789\nN=2\nN=3\n').encode('utf-8')

    _, report, _ = _run(tmp_path, content)

    assert report['candidate_anomalies'][0]['marker'] == 'N'
    assert len(report['discovery']['assertions'][0]['anchor']['quote']) == 75


def test_markdown_section_is_attached_as_navigation_context_only(tmp_path):
    _, report, _ = _run(
        tmp_path,
        b'# Methods\nSample size n = 30.\n\n## Results\nAnalysed n=28.\n',
        '.md',
    )

    candidate = report['candidate_anomalies'][0]
    assert {anchor['section'] for anchor in candidate['source_anchors']} == {'Methods', 'Results'}
    assert report['paper_structure']['sections'][1]['level'] == 2


def test_same_passage_counts_are_scope_notes_but_separate_distant_counts_are_candidates(tmp_path):
    _, report, _ = _run(
        tmp_path,
        b'In all, n = 20 were enrolled and n = 18 were analyzed.\n',
    )
    assert report['candidate_anomalies'] == []
    assert report['possible_scope_differences'][0]['type'] == 'MULTIPLE_COUNT_SCOPES_IN_ONE_PASSAGE'

    distant_dir = tmp_path / 'distant'
    distant_dir.mkdir()
    _, distant, _ = _run(
        distant_dir,
        ('Group A n=20. ' + 'x' * 800 + ' Group B n=18.\n').encode(),
        identifier='synthetic:distant-counts',
    )
    assert distant['candidate_anomalies'][0]['values_exact'] == ['18', '20']


def test_untrusted_source_text_and_identifiers_are_escaped_in_html(tmp_path):
    _, report, output = _run(
        tmp_path,
        b'<script> alert(1) </script> n=20\n<svg onload=x> n=18\n',
        identifier='<img src=x onerror=alert(1)>',
    )

    html = (output / 'report.html').read_text(encoding='utf-8')
    assert report['decision'] == 'CANDIDATES_FOUND'
    assert '<script>' not in html
    assert '<img src=x' not in html
    assert '&lt;script&gt;' in html
    assert '&lt;img src=x' in html


def test_overlong_line_is_reported_as_incomplete_instead_of_no_candidate(tmp_path):
    _, report, _ = _run(tmp_path, b'x' * (64 * 1024 + 1) + b' n=20 n=10\n')

    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert report['discovery']['scan_complete'] is False
    assert report['candidate_anomalies'] == []
    assert report['checks_attempted'] == [
        'explicit_count_marker_scan', 'explicit_exclusion_flow_arithmetic_screen',
    ]
    assert any('line(s) longer' in item for item in report['discovery']['limitations'])
    html = (tmp_path / 'screening' / 'report.html').read_text(encoding='utf-8')
    assert 'coverage was incomplete' in html


def test_line_limit_is_reported_as_incomplete_not_a_clean_scan(tmp_path, monkeypatch):
    import researchwitness.paper_audit as paper_audit

    monkeypatch.setattr(paper_audit, 'MAX_SCAN_LINES', 2)
    _, report, _ = _run(tmp_path, b'Line one.\nLine two.\nLine three n=2.\n')

    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert report['discovery']['scan_complete'] is False
    assert report['discovery']['assertions'] == []
    assert any('2-line scan limit' in item for item in report['discovery']['limitations'])


def _pdf_with_text(pypdf, pages: list[str]) -> bytes:
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = pypdf.PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'),
            NameObject('/BaseFont'): NameObject('/Helvetica'),
        })
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    import io
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _pdf_with_positioned_unicode_text(pypdf) -> bytes:
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
        NameObject('/Encoding'): NameObject('/WinAnsiEncoding'),
    })
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): font}),
    })
    entries = [
        (72, 760, 'Cohort – naïve participants'),
        (72, 720, 'Left column: Group A n=20'),
        (320, 720, 'Right column: Group B n=18'),
        (72, 36, 'Footer · page 1'),
    ]
    operations = []
    for x, y, text in entries:
        encoded = text.encode('cp1252').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
        operations.append(f'BT /F1 10 Tf {x} {y} Td '.encode('ascii') + b'(' + encoded + b') Tj ET')
    stream = DecodedStreamObject()
    stream.set_data(b'\n'.join(operations))
    page[NameObject('/Contents')] = writer._add_object(stream)
    import io
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _image_only_pdf(pypdf) -> bytes:
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    image = DecodedStreamObject()
    image.set_data(b'\x7f')
    image.update({
        NameObject('/Type'): NameObject('/XObject'),
        NameObject('/Subtype'): NameObject('/Image'),
        NameObject('/Width'): NumberObject(1),
        NameObject('/Height'): NumberObject(1),
        NameObject('/ColorSpace'): NameObject('/DeviceGray'),
        NameObject('/BitsPerComponent'): NumberObject(8),
    })
    image_ref = writer._add_object(image)
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/XObject'): DictionaryObject({NameObject('/Im0'): image_ref}),
    })
    content = DecodedStreamObject()
    content.set_data(b'q 100 0 0 100 72 600 cm /Im0 Do Q')
    page[NameObject('/Contents')] = writer._add_object(content)
    import io
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@requires_posix_pdf_limits
def test_born_digital_pdf_maps_count_markers_back_to_physical_pages(tmp_path):
    import pypdf

    pdf = _pdf_with_text(pypdf, ['Group A n=20', 'Group B n=18'])
    _, report, output = _run(tmp_path, pdf, '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['decision'] == 'CANDIDATES_FOUND'
    assert report['extraction']['status'] == 'TEXT_AVAILABLE'
    assert report['extraction']['page_count'] == 2
    assert report['source_capabilities']['prose'] == 'PROSE_TEXT_RELIABLE'
    assert report['source_capabilities']['tables'] == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert 'Table checking incomplete' in (output / 'report.html').read_text(encoding='utf-8')
    assert {anchor['page_number'] for anchor in report['candidate_anomalies'][0]['source_anchors']} == {1, 2}
    assert (output / 'source.pdf').read_bytes() == pdf


@requires_posix_pdf_limits
def test_two_column_unicode_pdf_preserves_extracted_text_and_page_anchors(tmp_path):
    import pypdf

    pdf = _pdf_with_positioned_unicode_text(pypdf)
    _, report, output = _run(tmp_path, pdf, '.pdf')
    _skip_if_worker_limits_unavailable(report)

    extracted = (output / 'extracted-text.txt').read_text(encoding='utf-8')
    assert report['extraction']['status'] == 'TEXT_AVAILABLE'
    assert 'Cohort – naïve participants' in extracted
    assert 'Left column: Group A n=20' in extracted
    assert 'Right column: Group B n=18' in extracted
    assertion_pages = {
        item['anchor']['page_number'] for item in report['discovery']['assertions']
    }
    assert assertion_pages == {1}
    assert report['extraction']['page_count'] == 1


@requires_posix_pdf_limits
def test_repeated_pdf_headers_and_footers_do_not_enable_table_arithmetic(tmp_path):
    import pypdf

    repeated_matter = 'Journal Table 1 Group A n=20 Footer'
    pdf = _pdf_with_text(pypdf, [repeated_matter, repeated_matter])
    _, report, _ = _run(tmp_path, pdf, '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'TEXT_AVAILABLE'
    assert report['candidate_anomalies'] == []
    assert report['source_capabilities']['tables'] == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert report['arithmetic_screens']['table_percentages']['findings'] == []


@requires_posix_pdf_limits
def test_image_only_pdf_reports_no_extractable_text_and_no_ocr(tmp_path):
    import pypdf

    pdf = _image_only_pdf(pypdf)
    _, report, _ = _run(tmp_path, pdf, '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'NO_EXTRACTABLE_TEXT'
    assert report['extraction']['ocr_performed'] is False
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['source_capabilities']['prose'] == 'IMAGE_ONLY'
    assert report['source_capabilities']['tables'] == 'TABLE_STRUCTURE_UNSUPPORTED'
    assert report['candidate_anomalies'] == []
    assert report['discovery']['scan_complete'] is False
    assert any('no OCR was attempted' in item for item in report['extraction']['warnings'])


@requires_posix_pdf_limits
def test_partial_pdf_extraction_never_returns_a_clean_scan(tmp_path):
    import pypdf

    pdf = _pdf_with_text(pypdf, ['Group A n=20', '', 'Group B n=18'])
    _, report, _ = _run(tmp_path, pdf, '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'PARTIAL_TEXT'
    assert report['decision'] == 'CANDIDATES_FOUND_IN_INCOMPLETE_SCAN'
    assert report['candidate_anomalies'][0]['values_exact'] == ['18', '20']
    assert report['discovery']['scan_complete'] is True


def test_missing_optional_pdf_parser_is_an_explicit_non_scan(monkeypatch, tmp_path):
    import researchwitness.paper_audit as paper_audit

    def unavailable_worker(*args, **kwargs):
        return type('WorkerResult', (), {
            'returncode': 0,
            'stdout': json.dumps({
                'status': 'PARSER_UNAVAILABLE',
                'extractor': 'pypdf (optional paper extra)',
                'page_records': [],
                'warnings': ['Install researchwitness[paper] to extract PDF text. No OCR was attempted.'],
                'text_base64': '',
            }).encode(),
        })()

    monkeypatch.setattr(paper_audit.subprocess, 'run', unavailable_worker)
    _, report, _ = _run(tmp_path, b'%PDF-1.4\n%%EOF\n', '.pdf')

    assert report['extraction']['status'] == 'PARSER_UNAVAILABLE'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['discovery']['scan_complete'] is False
    assert report['discovery']['assertions'] == []


def test_worker_timeout_is_a_bounded_non_scan(monkeypatch, tmp_path):
    import subprocess
    import researchwitness.paper_audit as paper_audit

    def time_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])

    monkeypatch.setattr(paper_audit.subprocess, 'run', time_out)
    _, report, _ = _run(tmp_path, b'%PDF-1.4\n%%EOF\n', '.pdf')

    assert report['extraction']['status'] == 'RESOURCE_LIMIT_OR_TIMEOUT'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []
    assert report['extraction']['warnings']


def test_pdf_worker_requires_resource_module(monkeypatch):
    monkeypatch.setitem(sys.modules, 'resource', None)

    assert _pdf_worker._limits(768 * 1024 * 1024, 15) is False


def test_pdf_worker_requires_both_setrlimit_calls(monkeypatch):
    calls = []

    def setrlimit(limit, bounds):
        calls.append((limit, bounds))
        if limit == 2:
            raise OSError('synthetic resource-limit denial')

    resource_module = SimpleNamespace(RLIMIT_CPU=1, RLIMIT_AS=2, setrlimit=setrlimit)
    monkeypatch.setitem(sys.modules, 'resource', resource_module)

    assert _pdf_worker._limits(768 * 1024 * 1024, 15) is False
    assert calls == [(1, (15, 15)), (2, (768 * 1024 * 1024, 768 * 1024 * 1024))]


def test_pdf_worker_does_not_import_pypdf_without_limits(monkeypatch, tmp_path):
    import researchwitness._pdf_worker as pdf_worker

    source = tmp_path / 'synthetic.pdf'
    source.write_bytes(b'%PDF-1.4\n%%EOF\n')
    output = io.StringIO()
    original_import = builtins.__import__

    def forbid_pypdf_import(name, *args, **kwargs):
        if name == 'pypdf':
            raise AssertionError('pypdf must not be imported when OS limits are unavailable')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(pdf_worker, '_limits', lambda _memory, _cpu: False)
    monkeypatch.setattr(builtins, '__import__', forbid_pypdf_import)
    monkeypatch.setattr(sys, 'stdout', output)

    result = pdf_worker.main([
        str(Path(__file__).parents[1] / 'researchwitness' / '_pdf_worker.py'),
        str(source), '500', '524288', '16777216', str(768 * 1024 * 1024), '15',
    ])

    payload = json.loads(output.getvalue())
    assert result == 0
    assert payload['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert payload['page_records'] == []
    assert payload['text_base64'] == ''
    assert any('No detector was run' in warning for warning in payload['warnings'])


def test_resource_limit_unavailable_pdf_report_is_an_incomplete_non_scan(monkeypatch, tmp_path):
    import researchwitness.paper_audit as paper_audit

    worker_payload = {
        'status': 'LIMIT_OR_UNSUPPORTED',
        'extractor': 'pypdf isolated worker (not run)',
        'page_records': [],
        'warnings': [
            'PDF extraction was skipped because the operating system could not apply the required worker CPU and memory limits. '
            'No detector was run.'
        ],
        'text_base64': '',
    }
    completed = SimpleNamespace(returncode=0, stdout=json.dumps(worker_payload).encode('utf-8'))
    monkeypatch.setattr(paper_audit.subprocess, 'run', lambda *args, **kwargs: completed)

    _, report, _ = _run(tmp_path, b'%PDF-1.4\nsynthetic fixture\n%%EOF\n', '.pdf')

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['extraction']['text_bytes'] == 0
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []
    assert report['discovery']['assertions'] == []
    assert report['discovery']['scan_complete'] is False
    assert any('No detector was run' in warning for warning in report['extraction']['warnings'])


@pytest.mark.skipif(os.name != 'nt', reason='native Windows-only PDF fail-closed integration check')
def test_native_windows_pdf_is_explicitly_unavailable(tmp_path):
    _, report, _ = _run(tmp_path, b'%PDF-1.4\n%%EOF\n', '.pdf')

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['extraction']['text_bytes'] == 0
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []
    assert report['discovery']['scan_complete'] is False
    assert any('operating system could not apply' in warning for warning in report['extraction']['warnings'])


@requires_posix_pdf_limits
def test_malformed_pdf_is_not_treated_as_paper_text(tmp_path):
    _, report, _ = _run(tmp_path, b'%PDF-1.4\n%%EOF\n', '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'MALFORMED_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []


@requires_posix_pdf_limits
def test_encrypted_pdf_fails_closed_without_running_detectors(tmp_path):
    import io
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(_pdf_with_text(pypdf, ['Group A n=20'])))
    writer = pypdf.PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt('paper-password')
    encrypted = io.BytesIO()
    writer.write(encrypted)

    _, report, _ = _run(tmp_path, encrypted.getvalue(), '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []


@requires_posix_pdf_limits
def test_pdf_extraction_cap_is_degraded_to_a_clear_report(tmp_path, monkeypatch):
    import pypdf
    import researchwitness.paper_audit as paper_audit

    monkeypatch.setattr(paper_audit, 'MAX_PDF_PAGES', 1)
    pdf = _pdf_with_text(pypdf, ['Group A n=20', 'Group B n=18'])

    _, report, _ = _run(tmp_path, pdf, '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['extraction']['text_bytes'] == 0
    assert report['candidate_anomalies'] == []


@requires_posix_pdf_limits
def test_oversized_pdf_page_text_stops_before_numeric_screening(tmp_path):
    import io
    import pypdf
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): font}),
    })
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 72 720 Td (' + 'A' * (4 * 1024 * 1024) + ' n=20) Tj ET').encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    pdf = io.BytesIO()
    writer.write(pdf)

    _, report, _ = _run(tmp_path, pdf.getvalue(), '.pdf')
    _skip_if_worker_limits_unavailable(report)

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []


def test_table_percentages_recompute_with_rounding_and_exact_byte_anchors(tmp_path):
    source_text = (
        '# Table 1 Repigmentation\n\n'
        '| Outcome | Group 1 (n=30) | Group 2 (n=30) |\n'
        '| --- | ---: | ---: |\n'
        '| At least 75%, n (%) | 23 (73.3) | 23 (70) |\n'
    )
    content = source_text.encode('utf-8')
    _, report, output = _run(tmp_path, content, '.md')

    assert report['decision'] == 'CANDIDATES_FOUND'
    findings = report['arithmetic_screens']['table_percentages']['findings']
    assert [(item['reported_percent'], item['recomputed_percent']) for item in findings] == [
        ('73.3', '76.666667'), ('70', '76.666667'),
    ]
    assert all(item['status'] == 'CANDIDATE_ANOMALY' for item in findings)
    assert report['verified_findings'] == []
    html = (output / 'report.html').read_text(encoding='utf-8')
    assert 'Possible table percentage arithmetic mismatch' in html
    assert 'Candidate anomaly · requires review.' in html
    assert "has not determined whether this affects the paper's conclusions" in html
    for finding in findings:
        for anchor in finding['source_anchors']:
            assert content[anchor['start_byte']:anchor['end_byte']].decode('utf-8') == anchor['quote']


@pytest.mark.parametrize('denominator', ['20/30', '20-30', '20–30', '20−30'])
def test_markdown_percentage_tables_do_not_use_the_left_value_of_a_denominator_range(
    tmp_path, denominator,
):
    source_text = (
        '| Outcome | All participants (N=' + denominator + ') |\n'
        '| --- | ---: |\n'
        '| Event, n (%) | 2 (10) |\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode('utf-8'), '.md')
    percentages = report['arithmetic_screens']['table_percentages']

    assert percentages['findings'] == []
    assert percentages['checked_cells'] == 0
    assert percentages['scan_complete'] is False


@pytest.mark.parametrize('context', [
    '# Table 1 Inverse probability weighting\n',
    '| Inverse probability weighting |  |  |\n',
    'Note: Percentages use post-stratification weights.\n',
    '# Table 1 Reweighted estimate\n',
    'Note: Percentages include adjustment for age.\n',
    '| Outcome | Group 1 (n=30) standardised estimate | Group 2 (n=30) |\n',
    '# Table 1 Standardising estimates\n',
    'Note: Percentages use standardizing.\n',
    '| Outcome | Group 1 (n=30) standardise estimate | Group 2 (n=30) |\n',
])
def test_markdown_percentage_tables_with_weighting_context_abstain_and_rollback(tmp_path, context):
    source_text = (
        '# Table 1 Outcomes\n'
        '| Outcome | Group 1 (n=30) | Group 2 (n=30) |\n'
        '| --- | ---: | ---: |\n'
        '| Event, n (%) | 23 (70) | 20 (66.7) |\n'
    )
    if context.startswith('#'):
        source_text = context + source_text.split('\n', 1)[1]
    elif context.startswith('|'):
        source_text += context
    else:
        source_text += context

    _, report, _ = _run(tmp_path, source_text.encode('utf-8'), '.md')
    percentages = report['arithmetic_screens']['table_percentages']
    assert percentages['findings'] == []
    assert percentages['checked_cells'] == 0
    assert percentages['scan_complete'] is False
    assert percentages['limitations']


def test_markdown_weighted_note_after_blank_line_rolls_back_table_results(tmp_path):
    source_text = (
        '| Outcome | Group 1 (n=30) | Group 2 (n=30) |\n'
        '| --- | ---: | ---: |\n'
        '| Event, n (%) | 23 (70) | 20 (60) |\n\n'
        'Note: Percentages use inverse probability weighting.\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode('utf-8'), '.md')
    percentages = report['arithmetic_screens']['table_percentages']

    assert percentages['findings'] == []
    assert percentages['checked_cells'] == 0
    assert percentages['scan_complete'] is False


@pytest.mark.parametrize(('reported', 'candidate_count'), [('12', 1), ('13', 0)])
def test_markdown_percentage_half_unit_uses_round_half_up(tmp_path, reported, candidate_count):
    source_text = (
        '| Outcome | All (n=8) |\n'
        '| --- | ---: |\n'
        f'| Event, n (%) | 1 ({reported}) |\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode(), '.md')
    assert len(report['candidate_anomalies']) == candidate_count


def test_irregular_pipe_table_discards_candidates_and_reports_incomplete_coverage(tmp_path):
    source_text = (
        '# Table 1 Results\n'
        '| Outcome | Group A (n=10) | Group B (n=10) |\n'
        '| --- | ---: | ---: |\n'
        '| Responders, n (%) | 9 (50) | 9 (50) |\n'
        '| Grouped header with a missing stub | |\n'
    )
    _, report, output = _run(tmp_path, source_text.encode(), '.md')

    assert report['arithmetic_screens']['table_percentages']['findings'] == []
    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert report['arithmetic_screens']['table_percentages']['scan_complete'] is False
    assert any('inconsistent row widths' in item for item in report['unsupported_checks'])
    html = (output / 'report.html').read_text(encoding='utf-8')
    assert 'No candidate was identified, but extraction or scan coverage was incomplete.' in html
    assert 'inconsistent row widths' in html


def test_missing_stub_header_and_jagged_data_row_are_not_column_aligned(tmp_path):
    source_text = (
        '# Table 2 Results\n'
        '| Outcome | All participants (n=100) | Follow-up subset (n=50) |\n'
        '| --- | ---: | ---: |\n'
        '| 80 (80) | 25 (50) |\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode(), '.md')

    assert report['arithmetic_screens']['table_percentages']['findings'] == []
    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert any('inconsistent row widths' in item for item in report['unsupported_checks'])


def test_row_local_denominator_or_footnoted_percentage_label_is_skipped(tmp_path):
    source_text = (
        '| Outcome | Group A (n=30) | Group B (n=30) |\n'
        '| --- | ---: | ---: |\n'
        '| Participants with data (n=25) | 20 (50) | 20 (50) |\n'
        '| Follow-up complete, n (%)a | 20 (50) | 20 (50) |\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode(), '.md')

    assert report['arithmetic_screens']['table_percentages']['findings'] == []
    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert any('local denominator or footnoted n (%) label' in item
               for item in report['unsupported_checks'])


def test_footnoted_column_denominator_is_omitted_but_unambiguous_column_remains_usable(tmp_path):
    source_text = (
        '| Outcome | Group A (n=30a) | Group B (n=30) |\n'
        '| --- | ---: | ---: |\n'
        '| Responders, n (%) | 20 (50) | 15 (50) |\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode(), '.md')

    assert report['arithmetic_screens']['table_percentages']['findings'] == []
    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert any('attached footnote marker' in item for item in report['unsupported_checks'])


def test_count_percentage_cell_with_footnote_is_omitted_and_reported(tmp_path):
    source_text = (
        '| Outcome | Group A (n=30) | Group B (n=30) |\n'
        '| --- | ---: | ---: |\n'
        '| Responders, n (%) | 20 (50)a | 15 (50) |\n'
    )
    _, report, _ = _run(tmp_path, source_text.encode(), '.md')

    assert report['arithmetic_screens']['table_percentages']['findings'] == []
    assert report['decision'] == 'SCAN_INCOMPLETE_NO_CANDIDATES'
    assert any('count/percentage cell with an attached footnote marker' in item
               for item in report['unsupported_checks'])


def test_repeated_smaller_denominators_are_scope_notes_not_error_candidates(tmp_path):
    content = (
        '# Table 1 Baseline\n'
        '| Characteristic | Control (n=21) | Intervention (n=20) |\n'
        '| --- | ---: | ---: |\n'
        '| Screen time, n (%) | 13 (92) | 11 (85) |\n'
        '| Vegetable use, n (%) | 12 (86) | 9 (69) |\n'
    ).encode()
    _, report, _ = _run(tmp_path, content, '.md')

    assert report['candidate_anomalies'] == []
    assert {item['compatible_alternate_denominators_exact'][0]
            for item in report['possible_scope_differences']} == {'13', '14'}


def test_explicit_exclusion_flow_with_unresolved_overlap_is_not_a_candidate(tmp_path):
    content = (
        'Of the 17,708 study participants, we excluded 1,841 under age 45, '
        '2,789 with baseline disease, and 1,878 with incomplete data. '
        'Finally, 12,417 participants were included.\n'
    ).encode()
    _, report, _ = _run(tmp_path, content)

    flow = report['arithmetic_screens']['sample_exclusion_flow']
    assert flow['candidate_anomalies'] == []
    assert len(flow['ambiguous_relations']) == 1
    relation = flow['ambiguous_relations'][0]
    assert relation['status'] == 'FLOW_RELATION_AMBIGUOUS'
    assert relation['source_total_exact'] == '17708'
    assert relation['excluded_values_exact'] == ['1841', '2789', '1878']
    assert relation['reported_included_exact'] == '12417'
    assert report['paper_error_established'] is False
    for anchor in relation['source_anchors']:
        assert content[anchor['start_byte']:anchor['end_byte']].decode('utf-8') == anchor['quote']


def test_source_size_and_invalid_text_fail_closed_without_output(tmp_path, monkeypatch):
    import researchwitness.paper_audit as paper_audit

    source = tmp_path / 'large.txt'
    source.write_bytes(b'12345')
    monkeypatch.setattr(paper_audit, 'MAX_SOURCE_BYTES', 4)
    with pytest.raises(Invalid, match='size limit'):
        run_paper_audit(source, tmp_path / 'large-out')
    assert not (tmp_path / 'large-out').exists()

    monkeypatch.setattr(paper_audit, 'MAX_SOURCE_BYTES', 32 * 1024 * 1024)
    source.write_bytes(b'bad utf-8 \xff')
    with pytest.raises(Invalid, match='UTF-8'):
        run_paper_audit(source, tmp_path / 'invalid-out')
    assert not (tmp_path / 'invalid-out').exists()
