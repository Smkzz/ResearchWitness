"""Synthetic integration, integrity, and regression tests for development audits."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.audit_contracts import SCHEMA_ROOT, schema_documents, validate
from tools.jats_percentage_audit import _descendants, _parse_jats, _text, audit_jats_percentage_tables
from tools.percentage_benchmark import compare_runs, regression_failures, pairs_in_span
from tools.offline_files import read_regular
from tools.research_audit import audit_document, audit_markdown, main, safe_text, write_reports


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ResearchAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = (b'<article><body><table-wrap id="t"><caption><p>N=40</p></caption><table>'
            b'<thead><tr><th>Category</th><th>n (%)</th></tr></thead><tbody>'
            b'<tr><td>None</td><td>0 (0.00)</td></tr><tr><td>A</td><td>4 (10.0)</td></tr>'
            b'<tr><td>B</td><td>4 (11.0)</td></tr></tbody></table></table-wrap></body></article>')
        self.source = self.root / 'source.xml'
        self.source.write_bytes(self.data)
        self.report = audit_jats_percentage_tables(self.data)
        tree = _parse_jats(self.data)
        denominator = next(_descendants(tree, 'caption'))
        denominator_anchor = {'byte_start': denominator.byte_start, 'byte_end': denominator.byte_end, 'quote': _text(denominator)}
        self.annotations = {'schema_version': 1, 'exposure': 'development',
            'annotation_provenance': 'Synthetic hand-constructed source; all expected calculations reviewed.',
            'documents': [{'document_id': 'synthetic', 'work_family_id': 'synthetic-family',
                'independence_status': 'synthetic fixture, never a scientific work',
                'source': {'path': 'source.xml', 'sha256': sha(self.data), 'url': '',
                    'provenance_status': 'synthetic', 'license': 'Apache-2.0'}, 'relationships': []}]}
        for index, result in enumerate(self.report['results']):
            evidence = result['evidence']
            self.annotations['documents'][0]['relationships'].append({
                'relationship_id': f'synthetic:{index}', 'table_id': 't', 'numerator': result['numerator'],
                'denominator': 40, 'reported_percent': result['reported_percent'], 'precision': result['display_precision'],
                'scope_status': 'explicit_table', 'arithmetic_status': result['status'],
                'review_outcome': 'arithmetic_only', 'scope_rationale': 'Explicit caption N=40.',
                'anchor': {'byte_start': evidence['byte_start'], 'byte_end': evidence['byte_end'],
                    'quote': evidence['cell_quote'], 'character_start': 0, 'character_end': len(evidence['cell_quote'])},
                'denominator_evidence': [denominator_anchor]})
        self.annotation_path = self.root / 'annotations.json'
        self.annotation_path.write_text(json.dumps(self.annotations))

    def run_manifest(self, label, report=None, *, failure=None):
        report = copy.deepcopy(self.report if report is None else report)
        report_path = self.root / f'{label}-report.json'
        report_path.write_text(json.dumps(report, sort_keys=True))
        run = {'schema_version': 1, 'label': label, 'detector_revision': 'synthetic-revision',
            'detector_files': {'tools/jats_percentage_audit.py': '1' * 64},
            'documents': [{'document_id': 'synthetic', 'source_sha256': sha(self.data),
                'status': 'extraction_failed' if failure else 'analyzed',
                'report_path': None if failure else report_path.name,
                'report_sha256': None if failure else sha(report_path.read_bytes()), 'reason': failure}]}
        path = self.root / f'{label}.json'
        path.write_text(json.dumps(run))
        return path

    def test_audit_is_schema_valid_and_preserves_unreviewed_arithmetic(self):
        report = audit_document(self.data, document_id='synthetic', input_format='jats',
            expected_sha256=sha(self.data), provenance_status='owner_hash_verified_handoff')
        self.assertEqual(report['summary'], {'arithmetic_matches': 2, 'mismatch_candidates': 1,
            'abstentions': 0, 'conditional_mismatches': 0})
        self.assertFalse(report['document']['provenance_authenticated_by_tool'])
        self.assertTrue(report['document']['expected_hash_verified'])
        self.assertTrue(all(f['review_state'] == 'unreviewed' for f in report['findings']))
        self.assertIn('XML bytes', audit_markdown(report))
        self.assertIsNotNone(report['processing']['extracted_text_sha256'])
        elevated = copy.deepcopy(report)
        elevated['findings'][0]['scientific_error_status'] = 'confirmed'
        with self.assertRaises(ValueError):
            validate(elevated, 'research-audit.v1.schema.json')

    def test_hash_or_provenance_claims_cannot_silently_authenticate_a_source(self):
        for kwargs in [{'expected_sha256': '0' * 64},
                       {'provenance_status': 'owner_hash_verified_handoff'},
                       {'source_url': 'https://user:secret@example.org/article'},
                       {'provenance_status': 'recorded_public_retrieval'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                audit_document(self.data, document_id='synthetic', input_format='jats', **kwargs)

    def test_pdf_and_html_failure_are_structured_without_host_fallback(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            report = audit_document(b'%PDF-1.7\nnot a valid PDF', document_id='synthetic', input_format='pdf')
        self.assertEqual(report['processing']['status'], 'extraction_failed')
        self.assertIn('SHA-256-pinned', report['processing']['reason'])
        self.assertEqual(report['findings'], [])
        report = audit_document(b'<html><p>Challenge</p></html>', document_id='synthetic', input_format='jats')
        self.assertEqual(report['processing']['status'], 'extraction_failed')

    def test_markdown_escapes_untrusted_text_and_reports_never_overwrite_inputs(self):
        text = safe_text('<script>run()</script> | [click](https://example.org)')
        self.assertNotIn('<script>', text)
        self.assertIn('\\|', text)
        self.assertIn('\\[click\\]', text)
        report = audit_document(self.data, document_id='synthetic', input_format='jats')
        with self.assertRaises(ValueError):
            write_reports(self.source, self.root / 'out.md', report, audit_markdown(report), protected_paths=(self.source,))
        target = self.root / 'out.json'
        target.write_text('owner notes')
        with self.assertRaises(ValueError):
            write_reports(target, self.root / 'out.md', report, audit_markdown(report))
        self.assertEqual(target.read_text(), 'owner notes')

    def test_cli_produces_reproducible_json_and_markdown(self):
        args = ['audit', str(self.source), '--document-id', 'synthetic', '--format', 'jats',
            '--json-output', str(self.root / 'audit.json'), '--markdown-output', str(self.root / 'audit.md')]
        self.assertEqual(main(args), 0)
        before = (self.root / 'audit.json').read_bytes()
        self.assertEqual(main(args), 0)
        self.assertEqual(before, (self.root / 'audit.json').read_bytes())

    def test_comparison_is_deterministic_offline_and_counts_work_families(self):
        run = self.run_manifest('current')
        with mock.patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            a, b = compare_runs(self.annotation_path, [run]), compare_runs(self.annotation_path, [run])
        self.assertEqual(a, b)
        self.assertEqual(a['work_family_count'], 1)
        metrics = a['runs'][0]['metrics']
        self.assertEqual(metrics['annotated_relationships_surfaced'], 3)
        self.assertEqual(metrics['matched_reference_discrepancies'], 1)
        self.assertEqual(metrics['source_anchor_failures'], 0)

    def test_duplicate_ids_and_duplicate_source_relationships_fail(self):
        for same_id in [True, False]:
            annotations = copy.deepcopy(self.annotations)
            duplicate = copy.deepcopy(annotations['documents'][0]['relationships'][0])
            if not same_id:
                duplicate['relationship_id'] = 'different-id'
            annotations['documents'][0]['relationships'].append(duplicate)
            self.annotation_path.write_text(json.dumps(annotations))
            with self.subTest(same_id=same_id), self.assertRaisesRegex(ValueError, 'Duplicate'):
                compare_runs(self.annotation_path, [self.run_manifest('current')])

    def test_source_hash_report_hash_and_confined_paths_are_enforced(self):
        run = self.run_manifest('current')
        source = self.source.read_bytes()
        self.source.write_bytes(source + b' ')
        with self.assertRaisesRegex(ValueError, 'Source version/hash mismatch'):
            compare_runs(self.annotation_path, [run])
        self.source.write_bytes(source)
        report_path = self.root / 'current-report.json'
        report_path.write_text(report_path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'report hash mismatch'):
            compare_runs(self.annotation_path, [run])
        annotations = copy.deepcopy(self.annotations)
        annotations['documents'][0]['source']['path'] = '../outside.xml'
        self.annotation_path.write_text(json.dumps(annotations))
        with self.assertRaisesRegex(ValueError, 'confined'):
            compare_runs(self.annotation_path, [run])

    def test_zero_count_wrong_denominator_fails_regression_gate_even_when_math_matches(self):
        baseline = self.run_manifest('baseline')
        bad = copy.deepcopy(self.report)
        bad['results'][0]['denominator'] = 4
        bad['results'][0]['exact_ratio_percent'] = '0/4'
        revised = self.run_manifest('revised', bad)
        comparison = compare_runs(self.annotation_path, [baseline, revised])
        self.assertEqual(comparison['runs'][1]['metrics']['incorrect_denominator_assignments'], 1)
        self.assertTrue(regression_failures(comparison))

    def test_new_false_candidate_and_anchor_failure_are_visible(self):
        baseline = self.run_manifest('baseline')
        bad = copy.deepcopy(self.report)
        r = bad['results'][1]
        r.update(denominator=20, status='arithmetic_mismatch_candidate',
            contract_expected_percent='20.0', exact_ratio_percent='400/20')
        r['evidence']['cell_quote'] = 'invented source quote'
        comparison = compare_runs(self.annotation_path, [baseline, self.run_manifest('revised', bad)])
        self.assertGreater(comparison['runs'][1]['metrics']['source_anchor_failures'], 0)
        self.assertTrue(regression_failures(comparison))
        r['evidence']['cell_quote'] = self.report['results'][1]['evidence']['cell_quote']
        comparison = compare_runs(self.annotation_path, [self.run_manifest('candidate', bad)])
        self.assertEqual(comparison['runs'][0]['metrics']['candidate_false_positives_against_annotations'], 1)

    def test_extraction_failure_is_reported_and_stale_annotations_fail(self):
        report = compare_runs(self.annotation_path, [self.run_manifest('failed', failure='safe parser rejected source')])
        self.assertEqual(report['runs'][0]['metrics']['extraction_failures'], 1)
        self.assertEqual(report['runs'][0]['metrics']['missed_reference_discrepancies'], 1)
        self.annotations['documents'][0]['relationships'][0]['anchor']['quote'] = 'stale quote'
        self.annotation_path.write_text(json.dumps(self.annotations))
        with self.assertRaisesRegex(ValueError, 'Invalid annotation anchor'):
            compare_runs(self.annotation_path, [self.run_manifest('current')])

    def test_schema_documents_match_checked_in_contracts(self):
        for name, schema in schema_documents().items():
            expected = {'$schema': 'https://json-schema.org/draft/2020-12/schema', **schema}
            with self.subTest(name=name):
                self.assertEqual(json.loads((SCHEMA_ROOT / name).read_text()), expected)

    def test_discrepancy_loss_is_not_hidden_by_unchanged_extraction_coverage(self):
        baseline = self.run_manifest('baseline')
        bad = copy.deepcopy(self.report)
        bad['results'][2].update(status='scope_ambiguous', reason='scope_unknown', denominator=None,
            contract_expected_percent=None, exact_ratio_percent=None)
        comparison = compare_runs(self.annotation_path, [baseline, self.run_manifest('revised', bad)])
        self.assertEqual(comparison['runs'][1]['metrics']['annotated_relationships_surfaced'], 3)
        self.assertEqual(comparison['runs'][1]['metrics']['matched_reference_discrepancies'], 0)
        self.assertTrue(any('source-bound discrepancy' in error for error in regression_failures(comparison)))

    def test_wrong_denominator_mismatch_cannot_receive_discrepancy_credit(self):
        bad = copy.deepcopy(self.report)
        bad['results'][2].update(denominator=20, contract_expected_percent='20.0', exact_ratio_percent='400/20')
        comparison = compare_runs(self.annotation_path, [self.run_manifest('bad', bad)])
        metrics = comparison['runs'][0]['metrics']
        self.assertEqual(metrics['incorrect_denominator_assignments'], 1)
        self.assertEqual(metrics['matched_reference_discrepancies'], 0)
        self.assertEqual(metrics['missed_reference_discrepancies'], 1)

    def test_explicit_annotation_denominator_must_match_source_evidence(self):
        self.annotations['documents'][0]['relationships'][0]['denominator'] = 4
        self.annotation_path.write_text(json.dumps(self.annotations))
        with self.assertRaisesRegex(ValueError, 'denominator differs from source evidence'):
            compare_runs(self.annotation_path, [self.run_manifest('current')])

    def test_annotations_reject_partial_or_signed_count_tokens(self):
        for invalid in ['1.4', '-4', '+4', '−4', '1,4']:
            with self.subTest(invalid=invalid):
                data = self.data.replace(b'4 (10.0)', (invalid + ' (10.0)').encode())
                self.source.write_bytes(data)
                annotations = copy.deepcopy(self.annotations)
                annotations['documents'][0]['source']['sha256'] = sha(data)
                tree = _parse_jats(data)
                cells = [n for n in _descendants(tree, 'td') if '(' in _text(n)]
                for r, cell in zip(annotations['documents'][0]['relationships'], cells):
                    r['anchor'] = {'byte_start': cell.byte_start, 'byte_end': cell.byte_end,
                        'quote': _text(cell), 'character_start': 0, 'character_end': len(_text(cell))}
                self.annotation_path.write_text(json.dumps(annotations))
                with self.assertRaisesRegex(ValueError, 'numeric tokens'):
                    compare_runs(self.annotation_path, [self.run_manifest('current')])

    def test_compact_multi_component_labels_require_exhaustive_grammar(self):
        text = 'P12 (25%) C4 (8.3%)'
        pairs = pairs_in_span(text, 0, 9)
        self.assertEqual([(m.group('n'), m.group('p')) for m in pairs], [('12', '25')])
        self.assertEqual(pairs_in_span('X1.4 (10%) Y2.5 (20%)', 0, 10), [])

    def test_integrated_audit_must_agree_with_manifest_identity_and_processing(self):
        audit = audit_document(self.data, document_id='synthetic', input_format='jats')
        for change in ['detector', 'status', 'count', 'document']:
            with self.subTest(change=change):
                report = copy.deepcopy(audit)
                if change == 'status': report['processing']['status'] = 'extraction_failed'
                if change == 'count': report['processing']['relationships_detected'] = 0
                if change == 'document': report['document']['document_id'] = 'another'
                path = self.run_manifest('current', report)
                run = json.loads(path.read_text())
                if change != 'detector': run['detector_files'] = audit['detector_files']
                path.write_text(json.dumps(run))
                with self.assertRaisesRegex(ValueError, 'contradict'):
                    compare_runs(self.annotation_path, [path])
        path = self.run_manifest('valid', audit)
        run = json.loads(path.read_text()); run['detector_files'] = audit['detector_files']
        path.write_text(json.dumps(run))
        self.assertEqual(compare_runs(self.annotation_path, [path])['runs'][0]['metrics']['parsed_documents'], 1)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'requires POSIX FIFOs')
    def test_special_files_are_rejected_before_blocking_reads(self):
        fifo = self.root / 'pipe'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            read_regular(fifo, 100)
        self.assertEqual(main(['audit', str(fifo), '--document-id', 'synthetic', '--format', 'jats',
            '--json-output', str(self.root / 'audit.json'), '--markdown-output', str(self.root / 'audit.md')]), 2)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            compare_runs(fifo, [self.run_manifest('current')])
        report = audit_document(self.data, document_id='synthetic', input_format='jats')
        with self.assertRaisesRegex(ValueError, 'regular file'):
            write_reports(fifo, self.root / 'out.md', report, '')

    def test_symlinks_and_oversized_files_fail_regular_file_reader(self):
        link = self.root / 'link'; link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            read_regular(link, len(self.data))
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            read_regular(self.source, 1)


if __name__ == '__main__':
    unittest.main()
