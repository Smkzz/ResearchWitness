"""Paper-screening tests assert narrow candidate behavior and its limits."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from researchwitness.paper_audit import capabilities, run_paper_audit
from researchwitness.strict import Invalid


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/paper-audit.schema.json').read_text(encoding='utf-8'))
SCHEMA_VALIDATOR = Draft202012Validator(SCHEMA)


def test_capability_registry_labels_paper_scan_as_candidate_discovery_only():
    screens = capabilities()

    assert len(screens) == 3
    assert all(item['role'] == 'candidate_discovery_only' for item in screens)
    assert 'same cohort or scope' in screens[0]['does_not_prove']


def _run(tmp_path: Path, content: bytes, suffix: str = '.txt', **kwargs):
    source = tmp_path / ('paper' + suffix)
    source.write_bytes(content)
    output = tmp_path / 'screening'
    result = run_paper_audit(source, output, **kwargs)
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    assert not list(SCHEMA_VALIDATOR.iter_errors(report))
    return result, report, output


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

    assert report['decision'] == 'NO_CANDIDATES_IN_SUPPORTED_SCAN'
    assert report['candidate_anomalies'] == []
    assert [item['value_exact'] for item in report['discovery']['assertions']] == ['20', '20']


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


def test_born_digital_pdf_maps_count_markers_back_to_physical_pages(tmp_path):
    import pypdf

    pdf = _pdf_with_text(pypdf, ['Group A n=20', 'Group B n=18'])
    _, report, output = _run(tmp_path, pdf, '.pdf')

    assert report['decision'] == 'CANDIDATES_FOUND'
    assert report['extraction']['status'] == 'TEXT_AVAILABLE'
    assert report['extraction']['page_count'] == 2
    assert {anchor['page_number'] for anchor in report['candidate_anomalies'][0]['source_anchors']} == {1, 2}
    assert (output / 'source.pdf').read_bytes() == pdf


def test_partial_pdf_extraction_never_returns_a_clean_scan(tmp_path):
    import pypdf

    pdf = _pdf_with_text(pypdf, ['Group A n=20', '', 'Group B n=18'])
    _, report, _ = _run(tmp_path, pdf, '.pdf')

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


def test_malformed_pdf_is_not_treated_as_paper_text(tmp_path):
    _, report, _ = _run(tmp_path, b'%PDF-1.4\n%%EOF\n', '.pdf')

    assert report['extraction']['status'] == 'MALFORMED_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []


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

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['candidate_anomalies'] == []


def test_pdf_extraction_cap_is_degraded_to_a_clear_report(tmp_path, monkeypatch):
    import pypdf
    import researchwitness.paper_audit as paper_audit

    monkeypatch.setattr(paper_audit, 'MAX_PDF_PAGES', 1)
    pdf = _pdf_with_text(pypdf, ['Group A n=20', 'Group B n=18'])

    _, report, _ = _run(tmp_path, pdf, '.pdf')

    assert report['extraction']['status'] == 'LIMIT_OR_UNSUPPORTED'
    assert report['decision'] == 'EXTRACTION_UNAVAILABLE_OR_EMPTY'
    assert report['extraction']['text_bytes'] == 0
    assert report['candidate_anomalies'] == []


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
    _, report, _ = _run(tmp_path, content, '.md')

    assert report['decision'] == 'CANDIDATES_FOUND'
    findings = report['arithmetic_screens']['table_percentages']['findings']
    assert [(item['reported_percent'], item['recomputed_percent']) for item in findings] == [
        ('73.3', '76.666667'), ('70', '76.666667'),
    ]
    assert all(item['status'] == 'CANDIDATE_ANOMALY' for item in findings)
    assert report['verified_findings'] == []
    for finding in findings:
        for anchor in finding['source_anchors']:
            assert content[anchor['start_byte']:anchor['end_byte']].decode('utf-8') == anchor['quote']


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


def test_explicit_exclusion_flow_mismatch_is_anchored_candidate(tmp_path):
    content = (
        'Of the 17,708 study participants, we excluded 1,841 under age 45, '
        '2,789 with baseline disease, and 1,878 with incomplete data. '
        'Finally, 12,417 participants were included.\n'
    ).encode()
    _, report, _ = _run(tmp_path, content)

    flow = report['arithmetic_screens']['sample_exclusion_flow']['candidate_anomalies']
    assert len(flow) == 1
    assert flow[0]['expected_included_exact'] == '11200'
    assert flow[0]['reported_included_exact'] == '12417'
    assert flow[0]['difference_exact'] == '1217'
    assert report['paper_error_established'] is False
    for anchor in flow[0]['source_anchors']:
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
