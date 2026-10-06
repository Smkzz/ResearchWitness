"""Run a post-hoc, source-native JATS development replay without retaining reports.

Publisher captures are supplied outside the repository and are checked against
the pinned manifests. The output is a compact metrics/coverage artifact; full
JSON and HTML reports exist only in temporary directories during execution.
This is development evidence, not a blind evaluation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
WAVE1_MANIFEST = ROOT / 'validation/paper-audit-wave-1/cases.json'
WAVE2_MANIFEST = ROOT / 'validation/paper-audit-wave-2/source_manifest.json'
WAVE2_LOCK = ROOT / 'validation/paper-audit-wave-2/results/LOCK.json'
REGRESSION_EVIDENCE = ROOT / 'validation/paper-audit-capability-wave-2/DETECTOR_REGRESSION_EVIDENCE.json'
SCHEMA = ROOT / 'schemas/paper-audit.schema.json'

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from researchwitness.paper_audit import run_paper_audit
from researchwitness.paper_contracts import contract_registry


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _target_matches(candidate: dict[str, Any], target: dict[str, Any]) -> bool:
    keys = ('table_id', 'row_identity', 'numerator_exact', 'denominator_exact', 'reported_percent')
    matches = all(candidate.get(key) == target.get(key) for key in keys)
    expected = target.get('expected_recomputed_percent')
    return matches and (expected is None or candidate.get('recomputed_at_display_precision') == expected)


def _positive_classifications(eligibility: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    wave1 = {
        item['case_id']: item for item in eligibility['cases']
        if item.get('corpus') == 'wave1_correction_development'
    }
    wave2 = {
        item['paper_id']: item for item in eligibility['cases']
        if item.get('corpus') == 'wave2_correction_posthoc_development'
    }
    return wave1, wave2


def _specifications(eligibility_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wave1 = json.loads(WAVE1_MANIFEST.read_text(encoding='utf-8'))
    wave2 = json.loads(WAVE2_MANIFEST.read_text(encoding='utf-8'))
    lock = json.loads(WAVE2_LOCK.read_text(encoding='utf-8'))
    eligibility = json.loads(eligibility_path.read_text(encoding='utf-8'))
    bindings = eligibility['bindings']
    checks = {
        'wave1_manifest_sha256': _file_sha256(WAVE1_MANIFEST),
        'wave2_source_manifest_sha256': _file_sha256(WAVE2_MANIFEST),
        'wave2_output_lock_sha256': _file_sha256(WAVE2_LOCK),
    }
    for key, actual in checks.items():
        if bindings.get(key) != actual:
            raise ValueError(f'Eligibility binding mismatch for {key}')
    if lock.get('source_manifest_sha256') != checks['wave2_source_manifest_sha256']:
        raise ValueError('Wave-2 lock does not bind the current source manifest')

    wave1_classified, wave2_classified = _positive_classifications(eligibility)
    specs: list[dict[str, Any]] = []
    for case in wave1['cases']:
        source = case['source']
        classified = wave1_classified.get(case['case_id'])
        is_positive = case['role'] == 'development_positive'
        if is_positive != (classified is not None):
            raise ValueError(f"Wave-1 eligibility does not match the manifest role for {case['case_id']}")
        specs.append({
            'case_id': case['case_id'],
            'corpus': 'wave1_correction_development',
            'role': 'positive' if is_positive else 'negative',
            'source_file': source['snapshot_name'],
            'expected_sha256': source['sha256'],
            'identifier': 'doi:' + source['doi'],
            'source_version': f"Europe PMC JATS capture for {source['pmcid']} retrieved {source['retrieved_at']}",
            'eligibility_record': classified,
        })
    for paper in wave2['papers']:
        source = paper['source']
        classified = wave2_classified.get(paper['paper_id'])
        specs.append({
            'case_id': paper['paper_id'],
            'corpus': 'wave2_posthoc_development',
            'role': 'positive' if classified else 'negative',
            'source_file': source['snapshot_name'],
            'expected_sha256': source['sha256'],
            'identifier': 'local:' + paper['paper_id'],
            'source_version': source['source_version'][:160],
            'eligibility_record': classified,
        })

    positives = [item for item in specs if item['role'] == 'positive']
    supported = sum(item['eligibility_record']['eligibility'] == 'SUPPORTED_BY_CURRENT_CONTRACT'
                    for item in positives)
    unsupported = sum(item['eligibility_record']['eligibility'] == 'UNSUPPORTED_BY_CURRENT_CONTRACT'
                      for item in positives)
    declared = eligibility['classification_counts']
    if (len(positives) != declared['correction_issues_total']
            or supported != declared['supported_by_current_contract']
            or unsupported != declared['unsupported_by_current_contract']):
        raise ValueError('Eligibility counts do not match manifest and case classifications')
    return specs, eligibility


def _safe_reason_counts(reasons: list[Any]) -> dict[str, int]:
    return dict(sorted(Counter(
        str(item.get('reason')) if isinstance(item, dict) else str(item)
        for item in reasons if item
    ).items()))


def _coverage_record(report: dict[str, Any]) -> dict[str, Any]:
    coverage = report.get('coverage', {})
    detector_rows = []
    for detector in coverage.get('detectors', []):
        tables = []
        for table in detector.get('tables', []):
            tables.append({
                'table_id': table.get('table_id'),
                'parser_status': table.get('parser_status'),
                'applicability': table.get('applicability'),
                'status': table.get('status'),
                'object_counts': table.get('counts', {}).get('objects', {}),
                'operand_counts': table.get('counts', {}).get('operands', {}),
                'reason_codes': sorted(set(
                    [str(item) for item in table.get('reasons', [])]
                    + [str(item) for item in table.get('skip_reasons', [])]
                )),
            })
        detector_rows.append({
            'detector_id': detector.get('detector_id'),
            'scope': detector.get('scope'),
            'status': detector.get('status'),
            'object_counts': detector.get('object_counts', {}),
            'operand_counts': detector.get('operand_counts', {}),
            'status_counts': detector.get('status_counts', {}),
            'reason_codes': _safe_reason_counts(detector.get('reasons', [])),
            'tables': tables,
        })
    paper = coverage.get('paper', {})
    return {
        'paper_tables': paper.get('tables', {}),
        'detectors': detector_rows,
    }


def _sum_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: Counter[str] = Counter()
    for row in rows:
        counts = row.get(key, {})
        for name, value in counts.items():
            if isinstance(value, int) and not isinstance(value, bool):
                result[name] += value
    return dict(sorted(result.items()))


def _run_one(spec: dict[str, Any], source_root: Path,
             validator: Draft202012Validator) -> dict[str, Any]:
    source_path = source_root / spec['source_file']
    raw = source_path.read_bytes()
    source_hash = _sha256(raw)
    if source_hash != spec['expected_sha256']:
        raise ValueError(f"{spec['case_id']}: raw source hash differs from its pinned manifest")

    with tempfile.TemporaryDirectory(prefix='rw-capability-wave2-replay-') as first_dir:
        first_output = Path(first_dir) / 'report'
        source_version = spec['source_version'][:100]
        run_paper_audit(source_path, first_output, spec['identifier'], source_version)
        report_bytes = (first_output / 'report.json').read_bytes()
        html_bytes = (first_output / 'report.html').read_bytes()
        report = json.loads(report_bytes)
        errors = list(validator.iter_errors(report))
        if errors:
            raise ValueError(f"{spec['case_id']}: current report fails schema: {errors[0].message}")
        if report['source']['sha256'] != source_hash:
            raise ValueError(f"{spec['case_id']}: report does not bind the pinned source")
        if report['paper_error_established'] is not False or report['verified_findings']:
            raise ValueError(f"{spec['case_id']}: report crossed the candidate-only boundary")
        with tempfile.TemporaryDirectory(prefix='rw-capability-wave2-repeat-') as second_dir:
            second_output = Path(second_dir) / 'report'
            run_paper_audit(source_path, second_output, spec['identifier'], source_version)
            repeatable_json = report_bytes == (second_output / 'report.json').read_bytes()
            repeatable_html = html_bytes == (second_output / 'report.html').read_bytes()

    candidates = report['candidate_anomalies']
    classification = spec.get('eligibility_record') or {}
    target_assertions = classification.get('target_cell_assertions', [])
    matched_targets = [target for target in target_assertions if any(
        _target_matches(candidate, target) for candidate in candidates
    )]
    eligible = classification.get('eligibility') == 'SUPPORTED_BY_CURRENT_CONTRACT'
    if eligible and len(matched_targets) != len(target_assertions):
        raise ValueError(f"{spec['case_id']}: one or more predeclared target cells were not reproduced")
    matched_candidate_ids = {
        candidate['id'] for candidate in candidates
        if any(_target_matches(candidate, target) for target in target_assertions)
    }
    candidate_types = dict(sorted(Counter(item['type'] for item in candidates).items()))
    detector_coverage = _coverage_record(report)
    return {
        'case_id': spec['case_id'],
        'corpus': spec['corpus'],
        'role': spec['role'],
        'source_sha256': source_hash,
        'source_bytes': len(raw),
        'eligibility': classification.get('eligibility', 'SELECTED_CONTROL'),
        'contract_id': classification.get('contract_id'),
        'eligible_target_cells': len(target_assertions),
        'matched_target_cells': len(matched_targets),
        'eligible_issue_detected': (len(matched_targets) == len(target_assertions)) if eligible else None,
        'candidate_count': len(candidates),
        'candidate_types': candidate_types,
        'unmatched_candidate_count_not_adjudicated': len(candidates) - len(matched_candidate_ids),
        'decision': report.get('decision'),
        'extraction_status': report.get('extraction', {}).get('status'),
        'paper_error_established': report['paper_error_established'],
        'report_sha256': _sha256(report_bytes),
        'report_html_sha256': _sha256(html_bytes),
        'repeatable_json': repeatable_json,
        'repeatable_html': repeatable_html,
        'coverage': detector_coverage,
    }


def _aggregate_detector_coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detectors: dict[str, list[dict[str, Any]]] = {}
    for paper in rows:
        for detector in paper['coverage']['detectors']:
            detectors.setdefault(detector['detector_id'], []).append(detector)
    output = []
    for detector_id in sorted(detectors):
        values = detectors[detector_id]
        status_counts = Counter(item.get('status', 'UNKNOWN') for item in values)
        reason_counts: Counter[str] = Counter()
        table_status_counts: Counter[str] = Counter()
        parser_status_counts: Counter[str] = Counter()
        table_records = 0
        for item in values:
            reason_counts.update(item.get('reason_codes', {}))
            for table in item.get('tables', []):
                table_records += 1
                if table.get('status'):
                    table_status_counts[table['status']] += 1
                if table.get('parser_status'):
                    parser_status_counts[table['parser_status']] += 1
        output.append({
            'detector_id': detector_id,
            'papers_reported': len(values),
            'coverage_status_counts': dict(sorted(status_counts.items())),
            'object_counts': _sum_counts(values, 'object_counts'),
            'operand_counts': _sum_counts(values, 'operand_counts'),
            'per_table_records': table_records,
            'per_table_status_counts': dict(sorted(table_status_counts.items())),
            'parser_status_counts': dict(sorted(parser_status_counts.items())),
            'skip_reason_counts': dict(sorted(reason_counts.items())),
        })
    return output


def run(wave1_source_dir: Path, wave2_source_dir: Path, eligibility_path: Path,
        summary_path: Path) -> dict[str, Any]:
    specs, eligibility = _specifications(eligibility_path)
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding='utf-8')))
    rows = []
    for spec in specs:
        source_root = wave1_source_dir if spec['corpus'] == 'wave1_correction_development' else wave2_source_dir
        rows.append(_run_one(spec, source_root, validator))

    positives = [item for item in rows if item['role'] == 'positive']
    controls = [item for item in rows if item['role'] == 'negative']
    eligible_cases = [item for item in positives if item['eligibility'] == 'SUPPORTED_BY_CURRENT_CONTRACT']
    unsupported_cases = [item for item in positives if item['eligibility'] == 'UNSUPPORTED_BY_CURRENT_CONTRACT']
    target_cells = sum(item['eligible_target_cells'] for item in eligible_cases)
    target_matches = sum(item['matched_target_cells'] for item in eligible_cases)
    candidate_type_counts: Counter[str] = Counter()
    for paper in rows:
        candidate_type_counts.update(paper['candidate_types'])
    contract_issue_counts: Counter[str] = Counter(
        item['contract_id'] for item in eligible_cases if item.get('contract_id')
    )
    contract_rows = contract_registry()
    per_contract = [{
        'detector_id': item['detector_id'],
        'implementation_status': item['implementation_status'],
        'eligible_correction_issues': contract_issue_counts[item['detector_id']],
    } for item in contract_rows]
    regression_evidence = json.loads(REGRESSION_EVIDENCE.read_text(encoding='utf-8'))
    summary = {
        'record_version': '1',
        'status': 'AGGREGATE_ONLY_POST_HOC_SOURCE_NATIVE_JATS_DEVELOPMENT_REPLAY',
        'evaluation_use': 'DEVELOPMENT_ONLY_NOT_HOLDOUT',
        'artifact_scope': (
            'Aggregate detector and corpus metrics only. Individual source identifiers, '
            'source hashes, per-paper outputs, and candidate records are omitted.'
        ),
        'detector_contract_version': contract_rows[0]['version'] if contract_rows else None,
        'metrics': {
            'source_documents': len(rows),
            'correction_issues_considered': len(positives),
            'eligible_correction_issues': len(eligible_cases),
            'unsupported_correction_issues': len(unsupported_cases),
            'overall_correction_mechanism_coverage': {
                'numerator': len(eligible_cases), 'denominator': len(positives),
            },
            'conditional_sensitivity_by_eligible_issue': {
                'numerator': sum(item['eligible_issue_detected'] is True for item in eligible_cases),
                'denominator': len(eligible_cases),
            },
            'matched_target_cells': {'numerator': target_matches, 'denominator': target_cells},
            'eligible_issues_by_detector': dict(sorted(contract_issue_counts.items())),
            'selected_negative_controls': len(controls),
            'candidate_bearing_selected_controls': sum(item['candidate_count'] > 0 for item in controls),
            'candidate_items_on_selected_controls': sum(item['candidate_count'] for item in controls),
            'all_candidate_items': sum(item['candidate_count'] for item in rows),
            'candidate_type_counts': dict(sorted(candidate_type_counts.items())),
            'unmatched_candidate_items_not_adjudicated': sum(
                item['unmatched_candidate_count_not_adjudicated'] for item in rows
            ),
            'adjudicated_candidate_precision': None,
            'reports_with_incomplete_table_or_detector_coverage': sum(
                item['coverage']['paper_tables'].get('structure_unsupported', 0) > 0
                or any(detector['status'] in ('INCOMPLETE', 'UNSUPPORTED')
                       for detector in item['coverage']['detectors'])
                for item in rows
            ),
            'extraction_failures': sum(item['extraction_status'] != 'TEXT_AVAILABLE' for item in rows),
            'repeatable_json_and_html_reports': sum(
                item['repeatable_json'] and item['repeatable_html'] for item in rows
            ),
            'repeatability_denominator': len(rows),
        },
        'historical_metrics_warning': (
            'No hard-negative false-candidate rate is estimated from the selected controls. '
            'They are not certified error-free, and unmatched candidates remain unadjudicated.'
        ),
        'synthetic_regression_evidence': regression_evidence,
        'contracts': per_contract,
        'per_detector_coverage': _aggregate_detector_coverage(rows),
        'limitations': [
            'The direct JATS replay and eligibility classification are post-hoc development work; neither is blinded.',
            'Individual source bindings and per-document reports are deliberately omitted from this public summary.',
            'All candidate findings remain unverified; paper_error_established is false for every report.',
            'Publisher PDFs, supplements, later versions, and scientific consequences were not independently adjudicated here.',
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wave1-source-dir', type=Path, required=True)
    parser.add_argument('--wave2-source-dir', type=Path, required=True)
    parser.add_argument(
        '--eligibility-file', type=Path, required=True,
        help='Private, source-level eligibility input; this file is not included in the repository.',
    )
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.wave1_source_dir, args.wave2_source_dir, args.eligibility_file, args.summary)
    print(json.dumps(result['metrics'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
