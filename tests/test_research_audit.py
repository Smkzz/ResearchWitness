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
from tools.percentage_benchmark import compare_runs, regression_failures, pairs_in_span, table_cell_context_map
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

    def test_integrated_report_explains_conditional_group_population_mapping(self):
        source = (b'<article><body><p>Intervention group (n=41) was allocated.</p>'
            b'<table-wrap><caption><p>Interventional Group outcomes</p></caption><table>'
            b'<thead><tr><th>Outcome</th><th>n (%)</th></tr></thead><tbody>'
            b'<tr><td>Response</td><td>38 (85.4%)</td></tr></tbody></table></table-wrap>'
            b'</body></article>')
        report = audit_document(source, document_id='synthetic-group', input_format='jats')
        self.assertEqual(report['summary']['mismatch_candidates'], 0)
        self.assertEqual(report['summary']['conditional_mismatches'], 1)
        self.assertIsNone(report['findings'][0]['relationship']['denominator'])
        self.assertEqual(report['findings'][0]['state'], 'extracted_evidence')
        markdown = audit_markdown(report)
        self.assertIn('Intervention group', markdown)
        self.assertIn('Interventional Group outcomes', markdown)
        self.assertIn('Conditional scope link', markdown)

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

    def test_nested_conditional_population_anchors_are_validated(self):
        self.data = (b'<article><body><p>Intervention group (n=41) was allocated.</p>'
            b'<table-wrap><caption><p>Interventional Group outcomes</p></caption><table>'
            b'<thead><tr><th>Outcome</th><th>n (%)</th></tr></thead><tbody>'
            b'<tr><td>Response</td><td>38 (85.4%)</td></tr></tbody></table></table-wrap>'
            b'</body></article>')
        self.source.write_bytes(self.data)
        self.report = audit_jats_percentage_tables(self.data)
        self.annotations['documents'][0]['source']['sha256'] = sha(self.data)
        self.annotations['documents'][0]['relationships'] = []
        self.annotation_path.write_text(json.dumps(self.annotations))

        candidate = copy.deepcopy(self.report)
        revised = self.run_manifest('conditional-valid', candidate)
        comparison = compare_runs(self.annotation_path, [revised])
        self.assertEqual(comparison['runs'][0]['metrics']['source_anchor_failures'], 0)
        self.assertEqual(comparison['runs'][0]['metrics']['conditional_mismatch_candidates'], 1)

        tree = _parse_jats(self.data)
        caption = next(_descendants(tree, 'caption'))
        forged = copy.deepcopy(candidate)
        forged_evidence = forged['results'][0]['conditional_calculation']['evidence']
        forged_evidence['group_population'] = {
            'role': 'article_group_population', 'byte_start': caption.byte_start,
            'byte_end': caption.byte_end, 'quote': _text(caption), 'quote_truncated': False,
        }
        revised = self.run_manifest('conditional-caption-as-article', forged)
        comparison = compare_runs(self.annotation_path, [revised])
        self.assertGreater(comparison['runs'][0]['metrics']['source_anchor_failures'], 0)
        self.assertEqual(comparison['runs'][0]['metrics']['conditional_mismatch_candidates'], 0)

        wrong_n = copy.deepcopy(candidate)
        wrong_n['results'][0]['conditional_calculation']['denominator'] += 1
        revised = self.run_manifest('conditional-wrong-n', wrong_n)
        comparison = compare_runs(self.annotation_path, [revised])
        self.assertGreater(comparison['runs'][0]['metrics']['source_anchor_failures'], 0)
        self.assertEqual(comparison['runs'][0]['metrics']['conditional_mismatch_candidates'], 0)

        bad_quote = copy.deepcopy(candidate)
        bad_quote['results'][0]['conditional_calculation']['evidence']['group_population']['quote'] = 'not source text'
        revised = self.run_manifest('conditional-bad-anchor', bad_quote)
        comparison = compare_runs(self.annotation_path, [revised])
        self.assertGreater(comparison['runs'][0]['metrics']['source_anchor_failures'], 0)

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

    def test_v2_annotations_preserve_separate_numeric_anchors_and_compare(self):
        tree = _parse_jats(self.data)
        cell = next(node for node in _descendants(tree, 'td') if _text(node) == '4 (11.0)')
        caption = next(_descendants(tree, 'caption'))

        def anchor(node, start, end):
            text = _text(node)
            return {'byte_start': node.byte_start, 'byte_end': node.byte_end, 'quote': text,
                'character_start': start, 'character_end': end, 'span_quote': text[start:end]}

        count_anchor = anchor(cell, 0, 1)
        percent_anchor = anchor(cell, 3, 7)
        relationship_anchor = anchor(cell, 0, len(_text(cell)))
        caption_anchor = anchor(caption, 0, len(_text(caption)))
        correction_data = b'<article><body><p>Correction notice: value should read 10.0.</p></body></article>'
        correction_path = self.root / 'synthetic-correction.xml'
        correction_path.write_bytes(correction_data)
        correction_tree = _parse_jats(correction_data)
        correction_node = next(_descendants(correction_tree, 'p'))
        correction_text = _text(correction_node)
        correction_anchor = anchor(correction_node, 0, len(correction_text))
        annotations = {
            'schema_version': 2, 'exposure': 'development',
            'annotation_provenance': 'Synthetic source with exact source-token and scope anchors.',
            'documents': [{
                'document_id': 'synthetic', 'work_family_id': 'synthetic-family',
                'independence_status': 'synthetic fixture', 'annotation_authority': 'developer',
                'reviewer_status': 'model_reviewed',
                'source': {'path': 'source.xml', 'sha256': sha(self.data), 'url': '',
                    'provenance_status': 'synthetic', 'license': 'Apache-2.0',
                    'version_label': 'synthetic-fixture-v1',
                    'retrieved_at_utc': '2026-10-15T00:00:00Z'},
                'relationships': [{
                    'relationship_id': 'synthetic:v2:1', 'table_id': 't',
                    'row_index': 4, 'numerator_cell_index': 1, 'percentage_cell_index': 1,
                    'component_group_id': '', 'component_index': 0, 'component_count': 1,
                    'component_label': '', 'numerator': 4, 'denominator': 40,
                    'denominator_basis': 'caption_or_footnote', 'reported_percent': '11.0',
                    'precision': 1, 'scope_status': 'explicit_table',
                    'scope_linkage_status': 'explicit_same_population',
                    'population_scope': 'Table-caption analysis population N=40.',
                    'arithmetic_status': 'arithmetic_mismatch_candidate',
                    'review_outcome': 'correction_corroborated',
                    'scope_rationale': 'The table caption states N=40 and the cell is n (%).',
                    'numerator_anchor': count_anchor, 'percentage_anchor': percent_anchor,
                    'anchor': relationship_anchor,
                    'denominator_evidence': [{'kind': 'caption', 'value': 40,
                        'anchor': caption_anchor}],
                    'scope_evidence': [caption_anchor], 'alternative_interpretations': [],
                    'correction_evidence': [{'source_id': 'synthetic-correction',
                        'statement': 'The correction explicitly replaces the printed percentage.',
                        'anchor': correction_anchor}],
                }],
                'related_sources': [{'source_id': 'synthetic-correction', 'relationship': 'correction',
                    'source': {'path': correction_path.name, 'sha256': sha(correction_data),
                        'url': 'https://example.org/synthetic-correction',
                        'provenance_status': 'synthetic', 'license': 'Apache-2.0',
                        'version_label': 'synthetic-correction-v1',
                        'retrieved_at_utc': '2026-10-15T00:00:00Z'}}],
            }],
        }
        path = self.root / 'annotations-v2.json'
        path.write_text(json.dumps(annotations))
        comparison = compare_runs(path, [self.run_manifest('v2-current')])
        metrics = comparison['runs'][0]['metrics']
        self.assertEqual(metrics['annotated_relationships_surfaced'], 1)
        self.assertEqual(metrics['matched_reference_discrepancies'], 1)
        self.assertEqual(metrics['source_anchor_failures'], 0)

        invalid_variants = []
        wrong_row = copy.deepcopy(annotations)
        wrong_row['documents'][0]['relationships'][0]['row_index'] = 3
        invalid_variants.append(wrong_row)
        wrong_denominator = copy.deepcopy(annotations)
        wrong_denominator['documents'][0]['relationships'][0]['denominator_evidence'][0]['value'] = 41
        invalid_variants.append(wrong_denominator)
        wrong_span = copy.deepcopy(annotations)
        wrong_span['documents'][0]['relationships'][0]['numerator_anchor']['span_quote'] = '5'
        invalid_variants.append(wrong_span)
        missing_correction = copy.deepcopy(annotations)
        missing_correction['documents'][0]['relationships'][0]['correction_evidence'] = []
        invalid_variants.append(missing_correction)
        for index, invalid in enumerate(invalid_variants):
            path.write_text(json.dumps(invalid))
            with self.subTest(index=index), self.assertRaises(ValueError):
                compare_runs(path, [self.run_manifest(f'v2-invalid-{index}')])

    def test_v2_annotations_cover_separate_columns_and_multiple_cell_components(self):
        data = (b'<article><body>'
            b'<table-wrap id="multi"><caption><p>Population N=48.</p></caption><table>'
            b'<thead><tr><th>Outcome</th><th>Values</th></tr></thead><tbody>'
            b'<tr><td>Combined</td><td>P12 (25%) C4 (8.3%)</td></tr>'
            b'</tbody></table></table-wrap>'
            b'<table-wrap id="separate"><caption><p>Population N=8.</p></caption><table>'
            b'<thead><tr><th>Outcome</th><th>Frequency</th><th>Percent</th></tr></thead><tbody>'
            b'<tr><td>Category A</td><td>2</td><td>25.0</td></tr>'
            b'</tbody></table></table-wrap></body></article>')
        source = self.root / 'v2-source.xml'
        source.write_bytes(data)
        report = audit_jats_percentage_tables(data)
        tree = _parse_jats(data)
        nodes = {(node.byte_start, node.byte_end): node for node in _descendants(tree, 'table')}
        nodes.update({(node.byte_start, node.byte_end): node for node in _descendants(tree, 'td')})
        nodes.update({(node.byte_start, node.byte_end): node for node in _descendants(tree, 'caption')})
        contexts = table_cell_context_map(data)
        count_by_group = {}
        for result in report['results']:
            e = result['evidence']
            group = (e['table_id'], e['byte_start'], e['byte_end'])
            count_by_group[group] = count_by_group.get(group, 0) + 1

        relationships = []
        for index, result in enumerate(report['results']):
            e = result['evidence']
            count_evidence = e.get('count_evidence')
            if count_evidence:
                count_node = nodes[(count_evidence['byte_start'], count_evidence['byte_end'])]
                count_text = _text(count_node)
                count_start = count_text.find(str(result['numerator']))
                numerator_anchor = {'byte_start': count_node.byte_start, 'byte_end': count_node.byte_end,
                    'quote': count_text, 'character_start': count_start,
                    'character_end': count_start + len(str(result['numerator'])),
                    'span_quote': str(result['numerator'])}
            else:
                count_node = nodes[(e['byte_start'], e['byte_end'])]
                count_text = _text(count_node)
                pair_span = e['relationship_quote']
                rel_start = e['normalized_character_start']
                count_start = pair_span.find(str(result['numerator']))
                numerator_anchor = {'byte_start': count_node.byte_start, 'byte_end': count_node.byte_end,
                    'quote': count_text, 'character_start': rel_start + count_start,
                    'character_end': rel_start + count_start + len(str(result['numerator'])),
                    'span_quote': str(result['numerator'])}
            percent_node = nodes[(e['byte_start'], e['byte_end'])]
            percent_text = _text(percent_node)
            percent_cell_start = e['normalized_character_start']
            percent_cell_end = e['normalized_character_end']
            relationship_text = e.get('relationship_quote', percent_text[percent_cell_start:percent_cell_end])
            percent_start = relationship_text.find(result['reported_percent'])
            percentage_anchor = {'byte_start': percent_node.byte_start, 'byte_end': percent_node.byte_end,
                'quote': percent_text, 'character_start': percent_cell_start + percent_start,
                'character_end': percent_cell_start + percent_start + len(result['reported_percent']),
                'span_quote': result['reported_percent']}
            relationship_anchor = {'byte_start': percent_node.byte_start, 'byte_end': percent_node.byte_end,
                'quote': percent_text, 'character_start': percent_cell_start,
                'character_end': percent_cell_end, 'span_quote': relationship_text}
            denominator_fact = next(f for f in e['denominator_sources']
                if f['evidence']['role'] in {'table_caption', 'table_total_row'})
            denominator_node = nodes[(denominator_fact['evidence']['byte_start'],
                                      denominator_fact['evidence']['byte_end'])]
            denominator_text = _text(denominator_node)
            denominator_anchor = {'byte_start': denominator_node.byte_start,
                'byte_end': denominator_node.byte_end, 'quote': denominator_text,
                'character_start': 0, 'character_end': len(denominator_text),
                'span_quote': denominator_text}
            numerator_context = contexts[(numerator_anchor['byte_start'], numerator_anchor['byte_end'])]
            percent_context = contexts[(percentage_anchor['byte_start'], percentage_anchor['byte_end'])]
            group_key = (e['table_id'], e['byte_start'], e['byte_end'])
            component_index = sum(1 for prior in relationships
                if prior['component_group_id'] == f'{group_key[0]}:{group_key[1]}:{group_key[2]}')
            component_count = count_by_group[group_key]
            relationships.append({
                'relationship_id': f'v2-source:{index}', 'table_id': e['table_id'],
                'row_index': percent_context['row_index'],
                'numerator_cell_index': numerator_context['cell_index'],
                'percentage_cell_index': percent_context['cell_index'],
                'component_group_id': f'{group_key[0]}:{group_key[1]}:{group_key[2]}' if component_count > 1 else '',
                'component_index': component_index, 'component_count': component_count,
                'component_label': e.get('component_label', ''),
                'numerator': result['numerator'], 'denominator': result['denominator'],
                'denominator_basis': 'caption_or_footnote',
                'reported_percent': result['reported_percent'],
                'precision': result['display_precision'], 'scope_status': 'explicit_table',
                'scope_linkage_status': 'explicit_same_population',
                'population_scope': denominator_text,
                'arithmetic_status': result['status'], 'review_outcome': 'arithmetic_only',
                'scope_rationale': 'Caption gives one explicit population N for the table.',
                'numerator_anchor': numerator_anchor, 'percentage_anchor': percentage_anchor,
                'anchor': relationship_anchor,
                'denominator_evidence': [{'kind': 'caption', 'value': denominator_fact['value'],
                    'anchor': denominator_anchor}],
                'scope_evidence': [denominator_anchor], 'alternative_interpretations': [],
                'correction_evidence': [],
            })
        annotations = {'schema_version': 2, 'exposure': 'development',
            'annotation_provenance': 'Synthetic test for separate cells and packed components.',
            'documents': [{'document_id': 'synthetic-v2', 'work_family_id': 'synthetic-v2-family',
                'independence_status': 'synthetic fixture', 'annotation_authority': 'developer',
                'reviewer_status': 'unreviewed',
                'source': {'path': source.name, 'sha256': sha(data), 'url': '',
                    'provenance_status': 'synthetic', 'license': 'Apache-2.0',
                    'version_label': 'synthetic-v2', 'retrieved_at_utc': '2026-10-15T00:00:00Z'},
                'related_sources': [],
                'relationships': relationships}]}
        annotations_path = self.root / 'v2-source-annotations.json'
        annotations_path.write_text(json.dumps(annotations))
        report_path = self.root / 'v2-source-report.json'
        report_path.write_text(json.dumps(report, sort_keys=True))
        run = {'schema_version': 1, 'label': 'v2-source-run', 'detector_revision': 'synthetic-v2',
            'detector_files': {'tools/jats_percentage_audit.py': 'a' * 64},
            'documents': [{'document_id': 'synthetic-v2', 'source_sha256': sha(data),
                'status': 'analyzed', 'report_path': report_path.name,
                'report_sha256': sha(report_path.read_bytes()), 'reason': None}]}
        run_path = self.root / 'v2-source-run.json'
        run_path.write_text(json.dumps(run))
        metrics = compare_runs(annotations_path, [run_path])['runs'][0]['metrics']
        self.assertEqual(metrics['annotated_relationships_surfaced'], 3)
        self.assertEqual(metrics['source_anchor_failures'], 0)

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
                if change == 'status':
                    report['processing']['status'] = 'extraction_failed'
                if change == 'count':
                    report['processing']['relationships_detected'] = 0
                if change == 'document':
                    report['document']['document_id'] = 'another'
                path = self.run_manifest('current', report)
                run = json.loads(path.read_text())
                if change != 'detector':
                    run['detector_files'] = audit['detector_files']
                path.write_text(json.dumps(run))
                with self.assertRaisesRegex(ValueError, 'contradict'):
                    compare_runs(self.annotation_path, [path])
        path = self.run_manifest('valid', audit)
        run = json.loads(path.read_text())
        run['detector_files'] = audit['detector_files']
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
        link = self.root / 'link'
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            read_regular(link, len(self.data))
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            read_regular(self.source, 1)


if __name__ == '__main__':
    unittest.main()
