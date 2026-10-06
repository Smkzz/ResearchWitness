"""Reproduce the post-hoc, source-native JATS development replay.

Publisher captures are supplied by the operator and are never checked into the
repository. Eligibility is loaded from the pre-replay classification artifact;
each source hash and both report renderings are checked before metrics are
written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT)
import sys

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from researchwitness.paper_audit import run_paper_audit

WAVE1_MANIFEST = ROOT / 'validation/paper-audit-wave-1/cases.json'
WAVE2_MANIFEST = ROOT / 'validation/paper-audit-wave-2/source_manifest.json'
ELIGIBILITY = ROOT / 'validation/paper-audit-capability-wave/DEVELOPMENT_ELIGIBILITY.json'
SCHEMA = ROOT / 'schemas/paper-audit.schema.json'
WAVE2_LOCK = ROOT / 'validation/paper-audit-wave-2/results/LOCK.json'


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _target_matches(candidate: dict[str, Any], target: dict[str, Any]) -> bool:
    return all(candidate.get(key) == target.get(key) for key in (
        'table_id', 'row_identity', 'numerator_exact', 'denominator_exact', 'reported_percent',
    ))


def _paper_id_from_source(source_url: str) -> str:
    parts = source_url.rstrip('/').split('/')
    pmc = parts[-2] if parts[-1] == 'fullTextXML' and len(parts) > 1 else parts[-1]
    if pmc.startswith('PMC'):
        return 'pmc:' + pmc
    return 'local:' + parts[-1]


def _case_specs() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wave1 = json.loads(WAVE1_MANIFEST.read_text(encoding='utf-8'))
    wave2 = json.loads(WAVE2_MANIFEST.read_text(encoding='utf-8'))
    eligibility = json.loads(ELIGIBILITY.read_text(encoding='utf-8'))
    bindings = eligibility['bindings']
    if bindings['wave1_manifest_sha256'] != _file_sha256(WAVE1_MANIFEST):
        raise ValueError('Wave-1 source/correction manifest hash differs from pre-replay eligibility binding')
    if bindings['wave2_source_manifest_sha256'] != _file_sha256(WAVE2_MANIFEST):
        raise ValueError('Wave-2 source manifest hash differs from pre-replay eligibility binding')
    if bindings['wave2_output_lock_sha256'] != _file_sha256(WAVE2_LOCK):
        raise ValueError('Wave-2 locked output hash differs from pre-replay eligibility binding')

    classified_wave1 = {item['case_id']: item for item in eligibility['cases']
                        if item.get('corpus') == 'wave1_correction_development'}
    classified_wave2 = {item['paper_id']: item for item in eligibility['cases']
                        if item.get('corpus') == 'wave2_correction_posthoc_development'}
    specs: list[dict[str, Any]] = []
    for case in wave1['cases']:
        source = case['source']
        classified = classified_wave1.get(case['case_id'])
        role = 'positive' if case['role'] == 'development_positive' else 'negative'
        if role == 'positive' and classified is None:
            raise ValueError(f"Missing pre-replay eligibility for {case['case_id']}")
        specs.append({
            'case_id': case['case_id'],
            'corpus': 'wave1_correction_development',
            'role': role,
            'source_file': source['snapshot_name'],
            'expected_sha256': source['sha256'],
            'identifier': 'doi:' + source['doi'],
            'source_version': f"Europe PMC JATS capture for {source['pmcid']} retrieved {source['retrieved_at']}",
            'eligibility_record': classified,
        })

    for paper in wave2['papers']:
        source = paper['source']
        classified = classified_wave2.get(paper['paper_id'])
        role = 'positive' if classified is not None else 'negative'
        specs.append({
            'case_id': paper['paper_id'],
            'corpus': 'wave2_posthoc_development',
            'role': role,
            'source_file': source['snapshot_name'],
            'expected_sha256': source['sha256'],
            'identifier': _paper_id_from_source(source['source_url']),
            'source_version': source['source_version'][:100],
            'eligibility_record': classified,
        })

    expected_counts = eligibility['classification_counts']
    actual = [item for item in specs if item['role'] == 'positive']
    supported = sum(item['eligibility_record']['eligibility'] == 'SUPPORTED_BY_CURRENT_CONTRACT'
                    for item in actual)
    unsupported = sum(item['eligibility_record']['eligibility'] == 'UNSUPPORTED_BY_CURRENT_CONTRACT'
                      for item in actual)
    if len(actual) != expected_counts['correction_issues_total']:
        raise ValueError('Positive correction cases do not match the eligibility artifact count')
    if supported != expected_counts['supported_by_current_contract']:
        raise ValueError('Supported issue count differs from the pre-replay eligibility artifact')
    if unsupported != expected_counts['unsupported_by_current_contract']:
        raise ValueError('Unsupported issue count differs from the pre-replay eligibility artifact')
    return specs, eligibility


def _run_case(spec: dict[str, Any], source_dir: Path, output_dir: Path,
              validator: Draft202012Validator) -> dict[str, Any]:
    source_path = source_dir / spec['source_file']
    source_bytes = source_path.read_bytes()
    source_hash = _sha256(source_bytes)
    if source_hash != spec['expected_sha256']:
        raise ValueError(f"{spec['case_id']}: source does not match its pinned manifest hash")

    first_output = output_dir / spec['case_id']
    run_paper_audit(source_path, first_output, spec['identifier'], spec['source_version'])
    report_bytes = (first_output / 'report.json').read_bytes()
    html_bytes = (first_output / 'report.html').read_bytes()
    report = json.loads(report_bytes)
    schema_errors = list(validator.iter_errors(report))
    if schema_errors:
        raise ValueError(f"{spec['case_id']}: invalid report schema: {schema_errors[0].message}")
    if report['source']['sha256'] != source_hash:
        raise ValueError(f"{spec['case_id']}: report source hash is not the pinned raw JATS hash")
    if report['paper_error_established'] is not False or report['verified_findings']:
        raise ValueError(f"{spec['case_id']}: report crossed the candidate-only boundary")

    with tempfile.TemporaryDirectory(prefix='rw-capability-replay-') as temp:
        second_output = Path(temp) / 'second-run'
        run_paper_audit(source_path, second_output, spec['identifier'], spec['source_version'])
        same_json = report_bytes == (second_output / 'report.json').read_bytes()
        same_html = html_bytes == (second_output / 'report.html').read_bytes()

    candidates = report['candidate_anomalies']
    eligibility_record = spec['eligibility_record']
    eligibility_status = (
        eligibility_record['eligibility'] if eligibility_record else 'SELECTED_CONTROL'
    )
    target_assertions = (eligibility_record or {}).get('target_cell_assertions', [])
    matched_targets = [target for target in target_assertions if any(
        _target_matches(candidate, target) for candidate in candidates
    )]
    target_match_count = len(matched_targets)
    eligible_issue_detected: bool | None = None
    if eligibility_status == 'SUPPORTED_BY_CURRENT_CONTRACT':
        if len(target_assertions) != eligibility_record['target_cells']:
            raise ValueError(f"{spec['case_id']}: eligible target cell map is incomplete")
        eligible_issue_detected = target_match_count == len(target_assertions)

    table_screen = report['arithmetic_screens']['structured_table_percentages']
    table_status_counts: dict[str, int] = {}
    for table in table_screen['tables']:
        table_status_counts[table['status']] = table_status_counts.get(table['status'], 0) + 1
    table_incomplete = (not table_screen['scan_complete'] or any(
        table['status'] in ('INCOMPLETE', 'UNSUPPORTED') for table in table_screen['tables']
    ))
    candidate_rows = [{
        'type': item['type'],
        'table_id': item.get('table_id'),
        'row_identity': item.get('row_identity'),
        'numerator_exact': item.get('numerator_exact'),
        'denominator_exact': item.get('denominator_exact'),
        'reported_percent': item.get('reported_percent'),
        'recomputed_at_display_precision': item.get('recomputed_at_display_precision'),
        'source_anchors': item.get('source_anchors', []),
    } for item in candidates]

    return {
        'case_id': spec['case_id'],
        'corpus': spec['corpus'],
        'role': spec['role'],
        'source_sha256': source_hash,
        'source_bytes': len(source_bytes),
        'eligibility': eligibility_status,
        'contract_id': (eligibility_record or {}).get('contract_id'),
        'decision': report['decision'],
        'extraction_status': report['extraction']['status'],
        'candidate_count': len(candidates),
        'candidate_types': {kind: sum(item['type'] == kind for item in candidates)
                            for kind in sorted({item['type'] for item in candidates})},
        'candidate_records': candidate_rows,
        'structured_table_status_counts': table_status_counts,
        'table_coverage_incomplete': table_incomplete,
        'repeatable_json_and_html': same_json and same_html,
        'eligible_target_cells': len(target_assertions),
        'matched_target_cells': target_match_count,
        'eligible_issue_detected': eligible_issue_detected,
        'selected_control_candidates_are_adjudicated_false': False,
    }


def _stratum(rows: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [item for item in rows if item['role'] == 'positive']
    controls = [item for item in rows if item['role'] == 'negative']
    eligible = [item for item in positives if item['eligibility'] == 'SUPPORTED_BY_CURRENT_CONTRACT']
    unsupported = [item for item in positives if item['eligibility'] == 'UNSUPPORTED_BY_CURRENT_CONTRACT']
    detected = sum(item['eligible_issue_detected'] is True for item in eligible)
    return {
        'source_format': 'JATS XML parsed directly',
        'papers': len(rows),
        'correction_issues': len(positives),
        'eligible_correction_issues': len(eligible),
        'unsupported_correction_issues': len(unsupported),
        'coverage': {'numerator': len(eligible), 'denominator': len(positives)},
        'eligible_issue_sensitivity': {'numerator': detected, 'denominator': len(eligible)},
        'candidates': sum(item['candidate_count'] for item in rows),
        'candidate_bearing_selected_controls': sum(item['candidate_count'] > 0 for item in controls),
        'selected_controls': len(controls),
        'table_coverage_incomplete_papers': sum(item['table_coverage_incomplete'] for item in rows),
        'extraction_failures': sum(item['extraction_status'] != 'TEXT_AVAILABLE' for item in rows),
        'repeatable_papers': sum(item['repeatable_json_and_html'] for item in rows),
    }


def run(wave1_source_dir: Path, wave2_source_dir: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError('Output directory must be empty: ' + str(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    specs, eligibility = _case_specs()
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding='utf-8')))
    rows = []
    for spec in specs:
        source_dir = wave1_source_dir if spec['corpus'] == 'wave1_correction_development' else wave2_source_dir
        rows.append(_run_case(spec, source_dir, output_dir, validator))

    positives = [item for item in rows if item['role'] == 'positive']
    controls = [item for item in rows if item['role'] == 'negative']
    eligible = [item for item in positives if item['eligibility'] == 'SUPPORTED_BY_CURRENT_CONTRACT']
    unsupported = [item for item in positives if item['eligibility'] == 'UNSUPPORTED_BY_CURRENT_CONTRACT']
    detected = sum(item['eligible_issue_detected'] is True for item in eligible)
    target_cells = sum(item['eligible_target_cells'] for item in eligible)
    target_matches = sum(item['matched_target_cells'] for item in eligible)
    summary = {
        'report_version': '1',
        'status': 'FINAL_POSTHOC_SOURCE_NATIVE_JATS_DEVELOPMENT_REPLAY',
        'evaluation_label': 'post-hoc source-native JATS development replay; not holdout',
        'eligibility_file_sha256': _file_sha256(ELIGIBILITY),
        'wave1_manifest_sha256': _file_sha256(WAVE1_MANIFEST),
        'wave2_source_manifest_sha256': _file_sha256(WAVE2_MANIFEST),
        'wave2_output_lock_sha256': _file_sha256(WAVE2_LOCK),
        'metrics': {
            'source_documents': len(rows),
            'positive_correction_issues': len(positives),
            'supported_correction_issues_preclassified': len(eligible),
            'unsupported_correction_issues_preclassified': len(unsupported),
            'overall_correction_coverage': {'numerator': len(eligible), 'denominator': len(positives)},
            'eligible_positive_sensitivity': {'numerator': detected, 'denominator': len(eligible)},
            'eligible_target_cell_match': {'numerator': target_matches, 'denominator': target_cells},
            'selected_control_papers': len(controls),
            'selected_control_papers_with_candidates': sum(item['candidate_count'] > 0 for item in controls),
            'candidate_items_on_selected_controls': sum(item['candidate_count'] for item in controls),
            'all_candidate_items': sum(item['candidate_count'] for item in rows),
            'adjudicated_candidate_precision': None,
            'table_coverage_incomplete_papers': sum(item['table_coverage_incomplete'] for item in rows),
            'extraction_failures': sum(item['extraction_status'] != 'TEXT_AVAILABLE' for item in rows),
            'repeatable_papers': sum(item['repeatable_json_and_html'] for item in rows),
            'repeatability_denominator': len(rows),
        },
        'limitations': [
            'Selected controls are not certified error-free; candidate counts on them are not false-positive counts without output adjudication.',
            'Wave-2 correction labels and source candidates were previously visible during development.',
            'An unadjudicated paper-020 table candidate is not counted as a true or false finding.',
            'All findings remain candidates and no paper-level error was established.',
            'The separate ground-truth payload is not present in this repository; its bound hash is recorded in the eligibility artifact.',
        ],
        'cases': rows,
        'strata': {
            'wave1_correction_development': _stratum([item for item in rows if item['corpus'] == 'wave1_correction_development']),
            'wave2_posthoc_development': _stratum([item for item in rows if item['corpus'] == 'wave2_posthoc_development']),
        },
    }
    (output_dir / 'REPLAY_SUMMARY.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wave1-source-dir', type=Path, required=True,
                        help='Directory containing wave-1 JATS captures named by cases.json')
    parser.add_argument('--wave2-source-dir', type=Path, required=True,
                        help='Directory containing wave-2 JATS captures named by source_manifest.json')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='New or empty directory for reports and REPLAY_SUMMARY.json')
    args = parser.parse_args()
    summary = run(args.wave1_source_dir, args.wave2_source_dir, args.output_dir)
    print(json.dumps(summary['metrics'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
