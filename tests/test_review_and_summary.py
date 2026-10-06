"""Review-ledger resource bounds and exact file-backed summary checks."""
from pathlib import Path
import json

import pytest

from researchwitness import Invalid
import researchwitness.review as review_module
from researchwitness.review import (
    REVIEW_AREAS,
    _EvidenceStore,
    html_review_report,
    validate_review,
    validate_review_file,
)
from researchwitness.statistics import validate_summary_file
from researchwitness.strict import canonical
from make_examples import base_case, write_case


ROOT = Path(__file__).resolve().parents[1]


def _review(source: bytes, finding: dict | None = None) -> dict:
    areas = {
        name: {
            'status': 'not_reviewed',
            'method': 'Not reviewed',
            'notes': 'Not reviewed in this fixture.',
            'evidence_files': [],
        }
        for name in REVIEW_AREAS
    }
    if finding is not None:
        area = finding['area']
        areas[area]['status'] = 'findings_recorded'
        areas[area]['method'] = 'Replay one bounded fixture.'
        areas[area]['notes'] = 'Synthetic test fixture.'
    return {
        'review_version': '0.1',
        'review_id': 'review-test',
        'reviewed_on': '2026-10-06',
        'source': {
            'identifier': 'synthetic:review-test',
            'version': 'v1',
            'text_file': 'paper.txt',
            'capture_status': 'synthetic',
        },
        'areas': areas,
        'findings': [] if finding is None else [finding],
    }


def _formalization_finding(quote: str, offset: int = 0) -> dict:
    return {
        'id': 'F1',
        'area': 'mathematics_logic',
        'status': 'formalization_replay',
        'location': 'Introduction',
        'statement': 'Synthetic linked checker case.',
        'quote': quote,
        'quote_offset': offset,
        'rationale': 'Test only.',
        'evidence_files': [],
        'verification_bundle': 'bundle',
    }


def test_file_backed_summary_parses_exact_decimals_and_records_missing_rows(tmp_path):
    source = 'Reported mean: 2.'
    (tmp_path / 'paper.txt').write_text(source, encoding='utf-8')
    (tmp_path / 'values.csv').write_text(
        'group,measurement\nA,1.25\nB,NA\nC,2.75\n', encoding='utf-8'
    )
    doc = {
        'summary_check_version': '0.1',
        'source': {
            'identifier': 'synthetic:decimal-summary',
            'version': 'v1',
            'text_file': 'paper.txt',
            'capture_status': 'synthetic',
            'quote': source,
        },
        'data': {
            'column': 'measurement',
            'data_source': 'Synthetic local CSV.',
            'transformation': 'No transformation; omit only declared missing values.',
            'file': {
                'path': 'values.csv',
                'format': 'csv',
                'header': True,
                'column_name': 'measurement',
                'missing_values': ['NA'],
                'missing_policy': 'drop',
            },
        },
        'reported': [{'statistic': 'mean', 'value': '2', 'tolerance': '0'}],
    }
    (tmp_path / 'summary.json').write_bytes(canonical(doc) + b'\n')

    report = validate_summary_file(tmp_path / 'summary.json')

    assert report['decision'] == 'NO_MISMATCH_WITHIN_DECLARED_TOLERANCES'
    assert report['data']['observation_count'] == 2
    assert report['comparisons'][0]['computed_exact'] == '2'
    extraction = report['data']['extraction']
    assert extraction['file_sha256']
    assert extraction['included_record_numbers'] == [1, 3]
    assert extraction['missing_record_numbers'] == [2]


def test_file_backed_summary_without_header_uses_zero_based_index(tmp_path):
    source = 'Reported mean: 1/4.'
    (tmp_path / 'paper.txt').write_text(source, encoding='utf-8')
    (tmp_path / 'values.tsv').write_text('A\t0.125\nB\t3/8\n', encoding='utf-8')
    doc = {
        'summary_check_version': '0.1',
        'source': {
            'identifier': 'synthetic:tsv-summary',
            'version': 'v1',
            'text_file': 'paper.txt',
            'capture_status': 'synthetic',
            'quote': source,
        },
        'data': {
            'column': 'measurement',
            'data_source': 'Synthetic local TSV.',
            'transformation': 'No transformation.',
            'file': {
                'path': 'values.tsv',
                'format': 'tsv',
                'header': False,
                'column_index': 1,
                'missing_values': [''],
                'missing_policy': 'reject',
            },
        },
        'reported': [{'statistic': 'mean', 'value': '1/4', 'tolerance': '0'}],
    }
    (tmp_path / 'summary.json').write_bytes(canonical(doc) + b'\n')

    report = validate_summary_file(tmp_path / 'summary.json')

    assert report['decision'] == 'NO_MISMATCH_WITHIN_DECLARED_TOLERANCES'
    assert report['data']['extraction']['column_index'] == 1
    assert report['data']['extraction']['column_name'] is None


def test_file_backed_summary_rejects_missing_values_by_default(tmp_path):
    source = 'Reported mean: 1.'
    (tmp_path / 'paper.txt').write_text(source, encoding='utf-8')
    (tmp_path / 'values.csv').write_text('value\n1\n""\n', encoding='utf-8')
    doc = {
        'summary_check_version': '0.1',
        'source': {
            'identifier': 'synthetic:missing-summary',
            'version': 'v1',
            'text_file': 'paper.txt',
            'capture_status': 'synthetic',
            'quote': source,
        },
        'data': {
            'column': 'value',
            'data_source': 'Synthetic local CSV.',
            'transformation': 'None.',
            'file': {
                'path': 'values.csv',
                'format': 'csv',
                'header': True,
                'column_name': 'value',
                'missing_values': [''],
                'missing_policy': 'reject',
            },
        },
        'reported': [{'statistic': 'mean', 'value': '1', 'tolerance': '0'}],
    }
    (tmp_path / 'summary.json').write_bytes(canonical(doc) + b'\n')

    with pytest.raises(Invalid, match='Missing value found'):
        validate_summary_file(tmp_path / 'summary.json')


def test_review_report_hashes_linked_summary_and_data_files():
    root = ROOT / 'examples' / 'paper-review-ledger'
    report = validate_review_file(root / 'review.json')
    finding = report['findings'][0]

    assert finding['verification']['input_path'] == 'summary-check.json'
    assert finding['evidence_sha256']['summary-check.json']
    assert finding['evidence_sha256']['observations.csv']
    assert finding['verification']['result']['data']['extraction']['file_sha256'] == (
        finding['evidence_sha256']['observations.csv']
    )


def test_review_html_leads_with_plain_language_ledger_scope():
    root = ROOT / 'examples' / 'paper-review-ledger'
    html = html_review_report(validate_review_file(root / 'review.json'))

    assert '<h2>Review ledger validated</h2>' in html
    assert 'Paper error established: no.' in html
    assert 'record-keeping measure' in html
    assert 'findings_recorded' not in html


def test_evidence_store_caches_reads_and_enforces_aggregate_byte_budget(tmp_path, monkeypatch):
    (tmp_path / 'first.txt').write_bytes(b'abc')
    (tmp_path / 'second.txt').write_bytes(b'de')
    monkeypatch.setattr(review_module, 'MAX_REVIEW_EVIDENCE_BYTES', 4)
    store = _EvidenceStore(tmp_path)

    first_hash = store.hash('first.txt')
    assert store.read('first.txt') == b'abc'
    assert store.hash('first.txt') == first_hash
    assert store._total_bytes == 3
    with pytest.raises(Invalid, match='aggregate evidence-size limit'):
        store.hash('second.txt')


def test_evidence_store_enforces_reference_count_even_for_cached_files(tmp_path, monkeypatch):
    (tmp_path / 'evidence.txt').write_bytes(b'evidence')
    monkeypatch.setattr(review_module, 'MAX_REVIEW_EVIDENCE_REFERENCES', 2)
    store = _EvidenceStore(tmp_path)

    store.hash('evidence.txt')
    store.hash('evidence.txt')
    with pytest.raises(Invalid, match='reference limit'):
        store.hash('evidence.txt')


def test_linked_formalization_must_use_exact_same_source_snapshot(tmp_path):
    case, data = base_case()
    case['source']['identifier'] = 'synthetic:review-test'
    case['source']['version'] = 'v1'
    quote = case['claim']['anchor']['quote']
    review_source = data['source.txt']
    (tmp_path / 'paper.txt').write_bytes(review_source)
    data['source.txt'] = review_source + b'Added text from another source snapshot.\n'
    write_case(tmp_path / 'bundle', case, data)
    doc = _review(review_source, _formalization_finding(quote))

    with pytest.raises(Invalid, match='source bytes must match'):
        validate_review(doc, tmp_path, canonical(doc))


def test_linked_formalization_bundle_bytes_have_review_wide_cap(tmp_path, monkeypatch):
    case, data = base_case()
    case['source']['identifier'] = 'synthetic:review-test'
    case['source']['version'] = 'v1'
    quote = case['claim']['anchor']['quote']
    source_bytes = data[case['source']['text_artifact']]
    (tmp_path / 'paper.txt').write_bytes(source_bytes)
    write_case(tmp_path / 'bundle', case, data)
    doc = _review(source_bytes, _formalization_finding(quote))
    monkeypatch.setattr(review_module, 'MAX_LINKED_BUNDLE_BYTES', 0)

    with pytest.raises(Invalid, match='linked-bundle aggregate limit'):
        validate_review(doc, tmp_path, canonical(doc))


def test_linked_summary_replay_count_is_bounded(monkeypatch):
    root = ROOT / 'examples' / 'paper-review-ledger'
    raw = (root / 'review.json').read_bytes()
    doc = json.loads(raw)
    monkeypatch.setattr(review_module, 'MAX_LINKED_REPLAYS', 0)

    with pytest.raises(Invalid, match='linked-replay limit'):
        validate_review(doc, root, raw)
