"""Run the ResearchWitness paper-audit CLI twice on the source-pinned dev set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'validation/paper-audit-wave-1/cases.json'
SCHEMA = ROOT / 'schemas/paper-audit.schema.json'
sys.path.insert(0, str(ROOT))
from researchwitness import VERSION
from tools.fetch_paper_audit_wave import obtain, sha256
from tools.render_pmc_jats import RENDERER_VERSION, render


def _matches(candidate: dict, expected: dict) -> bool:
    if candidate['type'] != expected['candidate_type']:
        return False
    target = expected['target']
    if candidate['type'] == 'TABLE_PERCENTAGE_ARITHMETIC_MISMATCH':
        allowed = target['reported_percent']
        allowed = {allowed} if isinstance(allowed, str) else set(allowed)
        return (
            candidate['numerator_exact'] == target['numerator_exact']
            and candidate['denominator_exact'] == target['denominator_exact']
            and candidate['reported_percent'] in allowed
        )
    if candidate['type'] == 'EXPLICIT_EXCLUSION_FLOW_ARITHMETIC_MISMATCH':
        return (
            candidate['source_total_exact'] == target['starting_total']
            and candidate['excluded_values_exact'] == target['exclusions']
            and candidate['reported_included_exact'] == target['reported_included']
        )
    return False


def _run_cli(input_path: Path, output_path: Path, doi: str, version: str) -> tuple[dict, float]:
    command = [
        sys.executable, '-m', 'researchwitness', 'paper-audit', str(input_path),
        '--identifier', 'doi:' + doi,
        '--source-version', version,
        '--output', str(output_path),
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    elapsed = time.perf_counter() - started
    return json.loads(completed.stdout), elapsed


def run(output: Path, source_dir: Path, download_missing: bool = False) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding='utf-8')))
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty: ' + str(output))
    output.mkdir(parents=True, exist_ok=True)

    case_results = []
    all_candidates = 0
    true_candidates = 0
    false_candidates = 0
    positive_detected = 0
    unsupported_positives = 0
    negative_candidate_papers = 0
    negative_candidate_items = 0
    extraction_errors = 0
    repeatable = 0
    arithmetic_recomputable_candidates = 0
    negative_scope_note_papers = 0

    for case in manifest['cases']:
        source_record = case['source']
        source_path = source_dir / source_record['snapshot_name']
        if not source_path.exists() and download_missing:
            obtain(source_record, source_dir, download=True)
        source_bytes = source_path.read_bytes()
        if sha256(source_bytes) != source_record['sha256']:
            raise ValueError(f"{case['case_id']}: source hash does not match the pinned manifest")
        markdown = render(source_bytes)
        if RENDERER_VERSION != manifest['renderer']:
            raise ValueError('Corpus renderer version does not match its manifest')

        with tempfile.TemporaryDirectory(prefix='researchwitness-paper-wave-') as temporary:
            temp = Path(temporary)
            input_path = temp / 'paper.md'
            input_path.write_bytes(markdown)
            first_out = temp / 'run-1'
            second_out = temp / 'run-2'
            version = f"{source_record['pmcid']} XML captured {source_record['retrieved_at']}; {RENDERER_VERSION}"
            first_cli, runtime = _run_cli(input_path, first_out, source_record['doi'], version)
            second_cli, _ = _run_cli(input_path, second_out, source_record['doi'], version)
            report_bytes = (first_out / 'report.json').read_bytes()
            html_bytes = (first_out / 'report.html').read_bytes()
            same_json = report_bytes == (second_out / 'report.json').read_bytes()
            same_html = html_bytes == (second_out / 'report.html').read_bytes()
            report = json.loads(report_bytes)
            errors = list(validator.iter_errors(report))
            if errors:
                raise ValueError(f"{case['case_id']}: invalid paper-audit report: {errors[0].message}")
            if report['source']['sha256'] != sha256(markdown):
                raise ValueError(f"{case['case_id']}: product report source hash does not match rendered input")
            if report['paper_error_established'] is not False or report['verified_findings']:
                raise ValueError(f"{case['case_id']}: candidate report crossed the verification boundary")

            candidates = report['candidate_anomalies']
            all_candidates += len(candidates)
            arithmetic_recomputable_candidates += sum(
                item['type'] in (
                    'TABLE_PERCENTAGE_ARITHMETIC_MISMATCH',
                    'EXPLICIT_EXCLUSION_FLOW_ARITHMETIC_MISMATCH',
                )
                for item in candidates
            )
            case_result = {
                'case_id': case['case_id'],
                'role': case['role'],
                'source': {
                    'pmcid': source_record['pmcid'],
                    'doi': source_record['doi'],
                    'snapshot_sha256': source_record['sha256'],
                    'rendered_markdown_sha256': sha256(markdown),
                    'source_version': version,
                },
                'run': {
                    'decision': report['decision'],
                    'extraction_status': report['extraction']['status'],
                    'checks_attempted': report['checks_attempted'],
                    'count_assertions': len(report['discovery']['assertions']),
                    'candidate_count': len(candidates),
                    'candidate_types': [item['type'] for item in candidates],
                    'possible_scope_difference_count': len(report['possible_scope_differences']),
                    'verified_finding_count': len(report['verified_findings']),
                    'unsupported_checks': report['unsupported_checks'],
                    'runtime_seconds': round(runtime, 3),
                    'deterministic_report_json': same_json,
                    'deterministic_report_html': same_html,
                },
            }
            if case['role'] == 'development_positive':
                case_result['expected_issue'] = case['expected']['issue']
                if case['expected']['candidate_type'] is None:
                    outcome = 'UNSUPPORTED_EXPECTED'
                    unsupported_positives += 1
                    matching = []
                else:
                    matching = [item for item in candidates if _matches(item, case['expected'])]
                    expected_count = (
                        len(case['expected']['target']['reported_percent'])
                        if isinstance(case['expected']['target'].get('reported_percent'), list) else 1
                    )
                    if len(matching) == expected_count:
                        outcome = 'DETECTED'
                        positive_detected += 1
                    elif matching:
                        outcome = 'PARTIALLY_DETECTED'
                    else:
                        outcome = 'MISSED'
                    case_result['expected_candidate_count'] = expected_count
                correct_items = len(matching)
                incorrect_items = len(candidates) - correct_items
                true_candidates += correct_items
                false_candidates += incorrect_items
                case_result['outcome'] = outcome
                case_result['matched_candidate_count'] = correct_items
            else:
                case_result['known_scope_traps'] = case['known_scope_traps']
                outcome = 'NO_CANDIDATE' if not candidates else 'FALSE_POSITIVE'
                if report['possible_scope_differences']:
                    negative_scope_note_papers += 1
                if candidates:
                    negative_candidate_papers += 1
                    negative_candidate_items += len(candidates)
                    false_candidates += len(candidates)
                case_result['outcome'] = outcome

            if report['extraction']['status'] != 'TEXT_AVAILABLE':
                extraction_errors += 1
            if same_json and same_html and second_cli['decision'] == first_cli['decision']:
                repeatable += 1
            case_dir = output / case['case_id']
            case_dir.mkdir()
            (case_dir / 'report.json').write_bytes(report_bytes)
            (case_dir / 'evaluation.json').write_text(
                json.dumps(case_result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
            )
            case_results.append(case_result)

    positives = sum(item['role'] == 'development_positive' for item in case_results)
    negatives = sum(item['role'] == 'development_negative' for item in case_results)
    total_scope_notes = sum(item['run']['possible_scope_difference_count'] for item in case_results)
    summary = {
        'corpus_version': manifest['corpus_version'],
        'paper_audit_version': '0.2',
        'product_version': VERSION,
        'corpus_role': 'development_only; corrections and labels were visible during detector iteration',
        'holdout': {'status': 'NOT_RUN', 'reason': 'No independent custodian and shared development workspace; public correction details were used while tuning.'},
        'metrics': {
            'positive_cases': positives,
            'known_issue_rediscovery': positive_detected,
            'known_issue_rediscovery_rate': positive_detected / positives if positives else None,
            'unsupported_positive_cases': unsupported_positives,
            'unsupported_positive_rate': unsupported_positives / positives if positives else None,
            'supported_positive_cases': positives - unsupported_positives,
            'candidate_items_with_recomputed_arithmetic': arithmetic_recomputable_candidates,
            'reproducible_arithmetic_rate_for_candidate_items': (
                arithmetic_recomputable_candidates / all_candidates if all_candidates else None
            ),
            'candidate_items': all_candidates,
            'matched_candidate_items': true_candidates,
            'unmatched_candidate_items': false_candidates,
            'candidate_precision_on_selected_development_set': (
                true_candidates / all_candidates if all_candidates else None
            ),
            'negative_controls': negatives,
            'negative_control_papers_with_candidates': negative_candidate_papers,
            'false_positive_rate_on_selected_negative_controls': (
                negative_candidate_papers / negatives if negatives else None
            ),
            'false_positive_candidates_per_negative_paper': (
                negative_candidate_items / negatives if negatives else None
            ),
            'possible_scope_difference_notes': total_scope_notes,
            'negative_control_papers_with_scope_notes': negative_scope_note_papers,
            'scope_note_adjudication': 'NOT_SYSTEMATICALLY_SCORED',
            'real_source_extraction_errors': extraction_errors,
            'verified_findings_promoted': 0,
            'repeatable_papers': repeatable,
            'repeatability_rate': repeatable / len(case_results) if case_results else None,
        },
        'cases': case_results,
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True,
                        help='directory containing the exact PMC snapshot_name files')
    parser.add_argument('--download-missing', action='store_true',
                        help='retrieve missing exact-hash sources from Europe PMC')
    parser.add_argument('--output', type=Path, required=True,
                        help='empty output directory for sanitized reports and metrics')
    args = parser.parse_args()
    summary = run(args.output, args.source_dir, args.download_missing)
    print(json.dumps(summary['metrics'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
