"""Run the post-hoc v1.2 percentage-contract development replay.

Publisher captures are supplied outside the repository and are checked against
the pinned manifests. The output is a compact metrics/coverage artifact; full
JSON and HTML reports exist only in temporary directories during execution.
This is development evidence, not a blind evaluation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
WAVE1_MANIFEST = ROOT / 'validation/paper-audit-wave-1/cases.json'
WAVE2_MANIFEST = ROOT / 'validation/paper-audit-wave-2/source_manifest.json'
WAVE2_LOCK = ROOT / 'validation/paper-audit-wave-2/results/LOCK.json'
REGRESSION_EVIDENCE = ROOT / 'validation/paper-audit-capability-wave-2/DETECTOR_REGRESSION_EVIDENCE.json'
SCHEMA = ROOT / 'schemas/paper-audit.schema.json'
BASE_ELIGIBILITY = ROOT / 'validation/paper-audit-capability-wave/DEVELOPMENT_ELIGIBILITY.json'

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from researchwitness.paper_audit import run_paper_audit
from researchwitness.paper_contracts import contract_registry


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _normalized_element_path(value: Any) -> tuple[tuple[str, int], ...] | None:
    """Normalize the two equivalent JATS path spellings used by source reviews."""
    if not isinstance(value, str) or not value.startswith('/'):
        return None
    path = re.sub(r"\*\[local-name\(\)=['\"]([^'\"]+)['\"]\]", r'\1', value)
    path = re.sub(r"\[@id=['\"][^'\"]*['\"]\]", '', path)
    parts: list[tuple[str, int]] = []
    for component in path.split('/'):
        if not component:
            continue
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_.:-]*)(?:\[(\d+)\])?', component)
        if match is None:
            return None
        parts.append((match.group(1), int(match.group(2) or '1')))
    return tuple(parts) if parts else None


def _negative_locator_matches(record: dict[str, Any], locator: dict[str, Any]) -> bool:
    """Disambiguate separate relations sharing one paragraph or table-cell anchor."""
    return (
        record.get('numerator_exact') == str(locator.get('numerator'))
        and record.get('denominator_exact') == str(locator.get('denominator'))
        and record.get('reported_percent') == str(locator.get('reported_percent'))
        and record.get('display_precision') == locator.get('display_precision_digits')
    )


def _pair_negative_source_relations(
    source_locators: list[dict[str, Any]], report_relations: list[dict[str, Any]],
) -> list[tuple[dict[str, Any] | None, bool]]:
    """Pair source labels by exact operands, then unique source anchor.

    Exact operand matching disambiguates several direct ratios in one source
    element. When one source relation and one report relation share an anchor,
    the report still belongs to that source relation if its parsed operands
    differ; this is how denominator-parsing false candidates are counted.
    """
    source_groups: dict[tuple[str, tuple[tuple[str, int], ...] | None], list[int]] = defaultdict(list)
    report_groups: dict[tuple[str, tuple[tuple[str, int], ...] | None], list[dict[str, Any]]] = defaultdict(list)
    for index, locator in enumerate(source_locators):
        source_groups[(str(locator.get('contract_id', '')),
                       _normalized_element_path(locator.get('cell_path')))].append(index)
    for relation in report_relations:
        anchor = relation.get('source_anchor')
        path = _normalized_element_path(anchor.get('element_path')) if isinstance(anchor, dict) else None
        report_groups[(str(relation.get('detector_id', '')), path)].append(relation)

    paired: dict[int, tuple[dict[str, Any] | None, bool]] = {}
    for key, source_indices in source_groups.items():
        remaining_reports = list(report_groups.get(key, []))
        remaining_sources: list[int] = []
        for index in source_indices:
            locator = source_locators[index]
            exact = [record for record in remaining_reports if _negative_locator_matches(record, locator)]
            if len(exact) == 1:
                record = exact[0]
                paired[index] = (record, True)
                remaining_reports.remove(record)
            else:
                remaining_sources.append(index)
        if len(remaining_sources) == 1 and len(remaining_reports) == 1:
            paired[remaining_sources[0]] = (remaining_reports[0], False)
        for index in remaining_sources:
            paired.setdefault(index, (None, False))
    return [paired.get(index, (None, False)) for index in range(len(source_locators))]


def _negative_source_table_ids(source: dict[str, Any]) -> set[str]:
    """Count represented JATS tables, excluding prose-only source relations."""
    return {
        str(item['table_id']) for item in source.get('relation_locators', [])
        if item.get('table_id') is not None
    }


def _target_matches(candidate: dict[str, Any], target: dict[str, Any]) -> bool:
    keys = ('table_id', 'row_identity', 'numerator_exact', 'denominator_exact', 'reported_percent')
    matches = all(
        key not in target or candidate.get(key) == target.get(key)
        for key in keys
    )
    source_cell_xpath = target.get('source_cell_xpath')
    if source_cell_xpath is not None:
        expected_path = _normalized_element_path(source_cell_xpath)
        candidate_paths = {
            _normalized_element_path(anchor.get('element_path'))
            for anchor in candidate.get('source_anchors', [])
            if isinstance(anchor, dict)
        }
        matches = matches and expected_path is not None and expected_path in candidate_paths
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


def _eligibility_input(path: Path) -> dict[str, Any]:
    supplied = json.loads(path.read_text(encoding='utf-8'))
    if supplied.get('artifact_type') != 'PERCENTAGE_V1_2_SOURCE_FIRST_POSITIVE_ELIGIBILITY':
        return supplied

    eligibility = json.loads(BASE_ELIGIBILITY.read_text(encoding='utf-8'))
    cases = {item['case_id']: item for item in eligibility['cases']}
    issue_count = 0
    target_count = 0
    for issue in supplied.get('issues', []):
        if issue.get('eligibility') != 'ELIGIBLE_CHECKED_MISMATCH':
            raise ValueError('v1.2 positive eligibility may contain only source-qualified mismatch issues')
        case = cases.get(issue.get('case_id'))
        if case is None:
            raise ValueError(f"v1.2 positive eligibility names an unknown development case: {issue.get('case_id')}")
        if issue.get('source_sha256') != case.get('source_sha256'):
            raise ValueError(f"{issue['case_id']}: source-first eligibility does not bind the baseline source")
        assertions = []
        for target in issue.get('target_relations', []):
            assertion = {
                'source_cell_xpath': target['source_cell_xpath'],
                'table_id': target['table_id'],
                'numerator_exact': target['numerator'],
                'denominator_exact': target['denominator'],
                'reported_percent': target['reported_percent'],
                'expected_recomputed_percent': target['recomputed_at_original_precision'],
            }
            assertions.append(assertion)
        if len(assertions) != issue.get('target_relation_count') or not assertions:
            raise ValueError(f"{issue['case_id']}: target relation count is inconsistent")
        case.update({
            'eligibility': 'SUPPORTED_BY_CURRENT_CONTRACT',
            'contract_id': issue['contract_id'],
            'target_cell_assertions': assertions,
            'target_cells': len(assertions),
        })
        issue_count += 1
        target_count += len(assertions)
    eligibility['classification_counts'] = {
        'correction_issues_total': len(cases),
        'supported_by_current_contract': issue_count,
        'unsupported_by_current_contract': len(cases) - issue_count,
    }
    eligibility['v1_2_source_first_eligibility_sha256'] = _file_sha256(path)
    eligibility['v1_2_eligible_target_relations'] = target_count
    eligibility['classification_timing'] = 'POST_HOC_DEVELOPMENT_SOURCE_FIRST; score join follows source label lock'
    return eligibility


def _specifications(eligibility_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wave1 = json.loads(WAVE1_MANIFEST.read_text(encoding='utf-8'))
    wave2 = json.loads(WAVE2_MANIFEST.read_text(encoding='utf-8'))
    lock = json.loads(WAVE2_LOCK.read_text(encoding='utf-8'))
    eligibility = _eligibility_input(eligibility_path)
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
        'percentage_relation_telemetry': report.get('arithmetic_screens', {}).get(
            'percentage_relation_telemetry', {},
        ),
    }


def _sum_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: Counter[str] = Counter()
    for row in rows:
        counts = row.get(key, {})
        for name, value in counts.items():
            if isinstance(value, int) and not isinstance(value, bool):
                result[name] += value
    return dict(sorted(result.items()))


def _table_reason_key(value: Any) -> str:
    """Normalize row-specific suffixes so aggregates describe reason classes."""
    return re.sub(r' \(row \d+\)$', '', str(value))


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
        'candidate_ids': [candidate['id'] for candidate in candidates],
        'candidate_records': [
            {
                'id': candidate.get('id'),
                'relation_id': candidate.get('relation_id'),
                'table_id': candidate.get('table_id'),
                'row_identity': candidate.get('row_identity'),
                'numerator_exact': candidate.get('numerator_exact'),
                'denominator_exact': candidate.get('denominator_exact'),
                'reported_percent': candidate.get('reported_percent'),
                'display_precision': candidate.get('display_precision'),
                'recomputed_at_display_precision': candidate.get('recomputed_at_display_precision'),
                'anchor_paths': sorted({
                    anchor.get('element_path') for anchor in candidate.get('source_anchors', [])
                    if isinstance(anchor, dict) and anchor.get('element_path')
                }),
            }
            for candidate in candidates
        ],
        'candidate_types': candidate_types,
        'candidate_items_not_matching_eligible_correction_targets': len(candidates) - len(matched_candidate_ids),
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
        table_reason_counts: dict[str, Counter[str]] = {}
        table_status_counts: Counter[str] = Counter()
        parser_status_counts: Counter[str] = Counter()
        table_records = 0
        for item in values:
            reason_counts.update(item.get('reason_codes', {}))
            for table in item.get('tables', []):
                table_records += 1
                if table.get('status'):
                    table_status_counts[table['status']] += 1
                table_status = table.get('status', 'UNKNOWN')
                table_reason_counts.setdefault(table_status, Counter()).update(
                    _table_reason_key(reason) for reason in table.get('reason_codes', [])
                )
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
            'table_reason_counts_by_status': {
                status: dict(sorted(counts.items()))
                for status, counts in sorted(table_reason_counts.items())
                if counts
            },
            'table_reason_count_unit': 'normalized reason strings per table result, grouped by table status',
        })
    return output


def _aggregate_percentage_relation_telemetry(rows: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter()
    primary_reasons = Counter()
    secondary_reasons = Counter()
    totals = Counter()
    for paper in rows:
        telemetry = paper.get('coverage', {}).get('percentage_relation_telemetry', {})
        if not isinstance(telemetry, dict) or telemetry.get('accounting_invariant') is not True:
            raise ValueError('percentage relation accounting invariant failed in a development report')
        row_statuses = telemetry.get('status_counts')
        row_reasons = telemetry.get('primary_skip_reason_counts')
        if not isinstance(row_statuses, dict) or not isinstance(row_reasons, dict):
            raise ValueError('percentage relation status and reason counts must be mappings')
        required_statuses = {
            'NOT_APPLICABLE', 'ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH',
            'INCOMPLETE', 'UNSUPPORTED',
        }
        if set(row_statuses) != required_statuses or any(
            type(value) is not int or value < 0 for value in row_statuses.values()
        ):
            raise ValueError('percentage relation status counts are incomplete or invalid')
        if any(type(value) is not int or value < 1 for value in row_reasons.values()):
            raise ValueError('percentage primary skip-reason counts are invalid')
        required_totals = (
            'potential_relations', 'applicable_relations', 'eligible_relations', 'checked_matches',
            'checked_mismatches', 'checked_relations', 'incomplete_relations', 'unsupported_relations',
            'skipped_relations',
        )
        if any(type(telemetry.get(key)) is not int or telemetry[key] < 0 for key in required_totals):
            raise ValueError('percentage relation totals are incomplete or invalid')
        row_skipped = row_statuses['INCOMPLETE'] + row_statuses['UNSUPPORTED']
        row_checked = row_statuses['ELIGIBLE_CHECKED_MATCH'] + row_statuses['ELIGIBLE_CHECKED_MISMATCH']
        if (
            telemetry.get('potential_relations') != sum(row_statuses.values())
            or telemetry.get('applicable_relations') != telemetry.get('potential_relations') - row_statuses['NOT_APPLICABLE']
            or telemetry.get('eligible_relations') != row_checked
            or telemetry.get('checked_relations') != row_checked
            or telemetry.get('checked_matches') != row_statuses['ELIGIBLE_CHECKED_MATCH']
            or telemetry.get('checked_mismatches') != row_statuses['ELIGIBLE_CHECKED_MISMATCH']
            or telemetry.get('incomplete_relations') != row_statuses['INCOMPLETE']
            or telemetry.get('unsupported_relations') != row_statuses['UNSUPPORTED']
            or telemetry.get('skipped_relations') != row_skipped
            or sum(row_reasons.values()) != row_skipped
        ):
            raise ValueError('percentage relation counts do not satisfy the frozen partition equations')
        for key in (
            'potential_relations', 'applicable_relations', 'eligible_relations', 'checked_matches',
            'checked_mismatches', 'checked_relations', 'incomplete_relations', 'unsupported_relations',
            'skipped_relations',
        ):
            totals[key] += telemetry.get(key, 0)
        statuses.update(telemetry.get('status_counts', {}))
        primary_reasons.update(telemetry.get('primary_skip_reason_counts', {}))
        secondary_reasons.update(telemetry.get('secondary_skip_reason_counts_overlapping', {}))
    skipped = totals['incomplete_relations'] + totals['unsupported_relations']
    checked = totals['checked_matches'] + totals['checked_mismatches']
    if (sum(statuses.values()) != totals['potential_relations']
            or sum(primary_reasons.values()) != skipped
            or totals['applicable_relations'] != totals['potential_relations'] - statuses['NOT_APPLICABLE']
            or totals['eligible_relations'] != checked
            or checked != totals['checked_relations']
            or totals['skipped_relations'] != skipped
            or totals['incomplete_relations'] != statuses['INCOMPLETE']
            or totals['unsupported_relations'] != statuses['UNSUPPORTED']
            or totals['checked_matches'] != statuses['ELIGIBLE_CHECKED_MATCH']
            or totals['checked_mismatches'] != statuses['ELIGIBLE_CHECKED_MISMATCH']):
        raise ValueError('aggregated relation telemetry does not exactly partition potential or skipped relations')
    return {
        **{key: totals[key] for key in sorted(totals)},
        'status_counts': dict(sorted(statuses.items())),
        'primary_skip_reason_counts': dict(sorted(primary_reasons.items())),
        'secondary_skip_reason_counts_overlapping': dict(sorted(secondary_reasons.items())),
        'accounting_invariant': True,
        'primary_skip_reason_count_unit': 'one canonical primary reason per skipped relation',
    }


def _negative_relation_replay(manifest_path: Path, validator: Draft202012Validator) -> dict[str, Any]:
    """Join locked source-first correct negatives to deterministic relation outputs."""
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('source_pool') not in ('DEVELOPMENT', 'DEVELOPMENT_ONLY') or manifest.get('reserved_records_included') is not False:
        raise ValueError('negative replay accepts only a DEVELOPMENT manifest with no reserved records')
    if manifest.get('contract_version') != '1.2':
        raise ValueError('negative replay manifest must bind percentage contract 1.2')
    manifest_hash = _sha256(manifest_bytes)
    document_rows: list[dict[str, Any]] = []
    false_candidate_relation_ids: set[str] = set()
    matched_relation_count = 0
    checked_matches = 0
    checked_mismatches = 0
    invalid_relation_count = 0
    reported_table_count = 0
    labelled_relation_count = 0
    labelled_relation_keys: set[tuple[Any, ...]] = set()
    expected_relation_types = {
        'table_percentage_recomputation': 'CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
        'jats_cell_ratio_percentage_recomputation': 'DIRECT_N_OVER_N_PERCENTAGE',
    }

    def relation_anchor_path(record: dict[str, Any]) -> tuple[tuple[str, int], ...] | None:
        anchor = record.get('source_anchor')
        return _normalized_element_path(anchor.get('element_path')) if isinstance(anchor, dict) else None

    for source in manifest.get('source_files', []):
        if (source.get('allocation_status') not in ('DEVELOPMENT_DOI_HASH_SPLIT', 'PREEXISTING_DEVELOPMENT')
                or source.get('split_status') != 'DEVELOPMENT'):
            raise ValueError('negative replay manifest contains a non-DEVELOPMENT source')
        source_path = Path(source['source_file'])
        raw = source_path.read_bytes()
        source_hash = _sha256(raw)
        if source_hash != source.get('source_sha256'):
            raise ValueError(f"{source_path.name}: negative source hash differs from locked manifest")
        identifier = 'doi:' + str(source.get('normalized_doi', '')).strip().lower()
        if identifier == 'doi:':
            raise ValueError(f"{source_path.name}: missing stable source identifier")
        source_version = 'locked development JATS source ' + str(source.get('source_id', source_path.name))
        with tempfile.TemporaryDirectory(prefix='rw-percentage-negative-') as first_dir:
            first_output = Path(first_dir) / 'report'
            run_paper_audit(source_path, first_output, identifier, source_version)
            report_bytes = (first_output / 'report.json').read_bytes()
            html_bytes = (first_output / 'report.html').read_bytes()
            report = json.loads(report_bytes)
            errors = list(validator.iter_errors(report))
            if errors:
                raise ValueError(f"{source_path.name}: negative replay report fails schema: {errors[0].message}")
            if report.get('source', {}).get('sha256') != source_hash:
                raise ValueError(f"{source_path.name}: report does not bind locked negative source")
            with tempfile.TemporaryDirectory(prefix='rw-percentage-negative-repeat-') as second_dir:
                second_output = Path(second_dir) / 'report'
                run_paper_audit(source_path, second_output, identifier, source_version)
                repeatable_json = report_bytes == (second_output / 'report.json').read_bytes()
                repeatable_html = html_bytes == (second_output / 'report.html').read_bytes()
            if not repeatable_json or not repeatable_html:
                raise ValueError(f"{source_path.name}: negative replay is not byte-repeatable")

        screens = report.get('arithmetic_screens', {})
        relations = (
            screens.get('structured_table_percentages', {}).get('relations', [])
            + screens.get('cell_ratio_percentages', {}).get('relations', [])
        )
        by_key: dict[tuple[str, tuple[tuple[str, int], ...] | None], list[dict[str, Any]]] = {}
        for record in relations:
            by_key.setdefault((str(record.get('detector_id')), relation_anchor_path(record)), []).append(record)
        candidates_by_relation = {
            str(item.get('relation_id')): item for item in report.get('candidate_anomalies', [])
            if item.get('relation_id')
        }
        source_relation_count = 0
        source_table_ids = _negative_source_table_ids(source)
        source_has_false_candidate = False
        source_locators = source.get('relation_locators', [])
        relation_pairs = _pair_negative_source_relations(source_locators, relations)
        anchor_joined_relation_count = 0
        anchor_joined_status_counts: Counter[str] = Counter()
        anchor_mismatch_candidate_ids: set[str] = set()
        anchor_operand_mismatch_status_counts: Counter[str] = Counter()
        for locator, (relation, operands_exact) in zip(source_locators, relation_pairs):
            source_relation_count += 1
            labelled_relation_count += 1
            contract_id = str(locator.get('contract_id', ''))
            path_key = _normalized_element_path(locator.get('cell_path'))
            relation_key = (
                source_hash, contract_id, path_key, str(locator.get('numerator')),
                str(locator.get('denominator')), str(locator.get('reported_percent')),
                locator.get('display_precision_digits'),
            )
            if relation_key in labelled_relation_keys:
                raise ValueError('negative source manifest contains a duplicate relation label')
            labelled_relation_keys.add(relation_key)
            if relation is None:
                invalid_relation_count += 1
                continue
            anchor_joined_relation_count += 1
            anchor = relation.get('source_anchor', {})
            if (locator.get('arithmetic_correct') is not True or not isinstance(anchor, dict)
                    or anchor.get('source_sha256') != source_hash
                    or _normalized_element_path(anchor.get('element_path')) != path_key
                    or relation.get('contract_version') != '1.2'
                    or relation.get('relation_type') != expected_relation_types.get(contract_id)):
                invalid_relation_count += 1
                continue
            anchor_joined_status_counts[str(relation.get('status'))] += 1
            relation_id_value = str(relation.get('relation_id'))
            emitted_candidate = (
                relation.get('finding_emitted') is True or relation_id_value in candidates_by_relation
            )
            if not operands_exact:
                # A detector mismatch on the independently labeled source
                # anchor is a false candidate even when its parsed denominator
                # differs from the source-first denominator. Keep this
                # separate from exact-operand coverage.
                invalid_relation_count += 1
                anchor_operand_mismatch_status_counts[str(relation.get('status'))] += 1
                if (relation.get('status') == 'ELIGIBLE_CHECKED_MISMATCH'
                        and emitted_candidate):
                    false_candidate_relation_ids.add(relation_id_value)
                    anchor_mismatch_candidate_ids.add(relation_id_value)
                    source_has_false_candidate = True
                continue
            matched_relation_count += 1
            if (relation.get('numerator_exact') != str(locator.get('numerator'))
                    or relation.get('denominator_exact') != str(locator.get('denominator'))
                    or relation.get('reported_percent') != str(locator.get('reported_percent'))
                    or relation.get('display_precision') != locator.get('display_precision_digits')):
                invalid_relation_count += 1
                continue
            if (relation.get('status') == 'ELIGIBLE_CHECKED_MATCH'
                    and relation.get('finding_emitted') is False):
                checked_matches += 1
            elif relation.get('status') == 'ELIGIBLE_CHECKED_MISMATCH' or relation.get('finding_emitted') is True:
                checked_mismatches += 1
                if emitted_candidate:
                    false_candidate_relation_ids.add(relation_id_value)
                    source_has_false_candidate = True
            else:
                invalid_relation_count += 1

        telemetry = screens.get('percentage_relation_telemetry', {})
        document_rows.append({
            'coverage': {'percentage_relation_telemetry': telemetry},
            'source_relation_count': source_relation_count,
            'source_table_count': len(source_table_ids),
            'source_anchor_joined_relation_count': anchor_joined_relation_count,
            'source_anchor_joined_status_counts': dict(anchor_joined_status_counts),
            'source_anchor_operand_mismatch_status_counts': dict(anchor_operand_mismatch_status_counts),
            'anchor_mismatch_candidate_count': len(anchor_mismatch_candidate_ids),
            'false_candidate_document': source_has_false_candidate,
            'repeatable_json': repeatable_json,
            'repeatable_html': repeatable_html,
        })
        reported_table_count += len(source_table_ids)

    if (
        len(document_rows) != manifest.get('source_document_count')
        or reported_table_count != manifest.get('table_count')
        or labelled_relation_count != manifest.get('relation_count')
    ):
        raise ValueError('negative source manifest document, table, or relation totals do not match its records')

    # Source documents are the clustering unit; the locator-to-report join above is exact.
    false_candidate_documents = sum(row['false_candidate_document'] for row in document_rows)

    telemetry_rows = [{'coverage': row['coverage']} for row in document_rows]
    telemetry = _aggregate_percentage_relation_telemetry(telemetry_rows)
    source_anchor_statuses: Counter[str] = Counter()
    source_anchor_operand_mismatch_statuses: Counter[str] = Counter()
    for row in document_rows:
        source_anchor_statuses.update(row['source_anchor_joined_status_counts'])
        source_anchor_operand_mismatch_statuses.update(row['source_anchor_operand_mismatch_status_counts'])
    return {
        'source_manifest_sha256': manifest_hash,
        'eligible_correct_relations': labelled_relation_count,
        'source_documents': len(document_rows),
        'source_tables': reported_table_count,
        'matched_relation_records': matched_relation_count,
        'source_anchor_joined_relation_records': sum(
            row['source_anchor_joined_relation_count'] for row in document_rows
        ),
        'source_anchor_joined_status_counts': dict(sorted(source_anchor_statuses.items())),
        'source_anchor_operand_mismatch_status_counts': dict(sorted(source_anchor_operand_mismatch_statuses.items())),
        'anchor_mismatch_candidate_records': sum(
            row['anchor_mismatch_candidate_count'] for row in document_rows
        ),
        'checked_matches': checked_matches,
        'checked_mismatches': checked_mismatches,
        'unmatched_or_invalid_relation_records': invalid_relation_count,
        'false_candidate_relations': len(false_candidate_relation_ids),
        'false_candidate_documents': false_candidate_documents,
        'relation_false_candidate_rate': {
            'numerator': len(false_candidate_relation_ids), 'denominator': labelled_relation_count,
        },
        'document_false_candidate_occurrence': {
            'numerator': false_candidate_documents, 'denominator': len(document_rows),
        },
        'source_report_replay': {
            'repeatable_json_reports': sum(row['repeatable_json'] for row in document_rows),
            'repeatable_html_reports': sum(row['repeatable_html'] for row in document_rows),
            'report_denominator': len(document_rows),
        },
        'percentage_relation_telemetry': telemetry,
        'source_first_labels_joined_after_lock': True,
    }


def _candidate_adjudication_metrics(
    path: Path | None, rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if path is None:
        return None
    artifact = json.loads(path.read_text(encoding='utf-8'))
    if (artifact.get('status') != 'POST_HOC_DEVELOPMENT_SOURCE_ADJUDICATION'
            or artifact.get('percentage_contract_version') != '1.2'):
        raise ValueError('candidate review must be a post-hoc v1.2 DEVELOPMENT adjudication')
    output_map = {
        (row['case_id'], candidate_id): row
        for row in rows for candidate_id in row.get('candidate_ids', [])
    }
    seen: set[tuple[str, str]] = set()
    classifications = Counter()
    arithmetic_discrepancy_classifications = {
        'SOURCE_REPRODUCED_KNOWN_CORRECTION_TARGET',
        'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY',
        'SOURCE_REPRODUCED_ARITHMETIC_DISCREPANCY_VERSION_UNVERIFIED',
    }
    allowed = arithmetic_discrepancy_classifications | {
        'SCOPE_DENOMINATOR_NOT_EXPLICIT', 'PARSER_SOURCE_ARTIFACT', 'UNRESOLVED',
    }
    for item in artifact.get('items', []):
        key = (str(item.get('case_id')), str(item.get('candidate_id')))
        row = output_map.get(key)
        if key in seen or row is None:
            raise ValueError('candidate review contains a duplicate or absent report candidate')
        seen.add(key)
        if (item.get('report_sha256') != row.get('report_sha256')
                or item.get('source_sha256') != row.get('source_sha256')):
            raise ValueError(f'candidate review is not bound to the current report/source: {key[0]}/{key[1]}')
        report_candidate = next(
            (candidate for candidate in row.get('candidate_records', [])
             if candidate.get('id') == key[1]),
            None,
        )
        if report_candidate is None:
            raise ValueError('candidate review key is missing its deterministic report candidate')
        binding_pairs = {
            'relation_id': 'relation_id',
            'table_id': 'table_id',
            'row_identity': 'row_identity',
            'numerator': 'numerator_exact',
            'denominator': 'denominator_exact',
            'reported_percent': 'reported_percent',
            'display_precision_digits': 'display_precision',
            'recomputed_at_display_precision': 'recomputed_at_display_precision',
            'anchors': 'anchor_paths',
        }
        if any(item.get(review_key) != report_candidate.get(report_key)
               for review_key, report_key in binding_pairs.items()):
            raise ValueError(f'candidate review facts differ from the bound report: {key[0]}/{key[1]}')
        classification = item.get('classification')
        if classification not in allowed:
            raise ValueError(f'candidate review has an unknown classification: {classification}')
        classifications[classification] += 1
    total = sum(row.get('candidate_count', 0) for row in rows)
    reviewed = len(seen)
    if reviewed != total:
        raise ValueError('candidate review must adjudicate every current replay candidate')
    confirmed = sum(classifications[name] for name in arithmetic_discrepancy_classifications)
    target_count = classifications['SOURCE_REPRODUCED_KNOWN_CORRECTION_TARGET']
    return {
        'total_current_candidate_items': total,
        'reviewed_candidate_items': reviewed,
        'not_yet_adjudicated_candidate_items': total - reviewed,
        'classification_counts': dict(sorted(classifications.items())),
        'candidate_arithmetic_validity': {'numerator': confirmed, 'denominator': reviewed},
        'known_correction_target_share': {'numerator': target_count, 'denominator': reviewed},
        'source_reproduced_uncorrected_non_target_discrepancies': classifications[
            'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY'
        ],
        'source_reproduced_version_status_unverified_discrepancies': classifications[
            'SOURCE_REPRODUCED_ARITHMETIC_DISCREPANCY_VERSION_UNVERIFIED'
        ],
        'scope_denominator_not_explicit_candidates': classifications['SCOPE_DENOMINATOR_NOT_EXPLICIT'],
        'parser_source_artifact_candidates': classifications['PARSER_SOURCE_ARTIFACT'],
        'unresolved_candidates': classifications['UNRESOLVED'],
        'all_current_candidates_adjudicated': reviewed == total,
        'candidate_review_sha256': _file_sha256(path),
    }


def run(wave1_source_dir: Path, wave2_source_dir: Path, eligibility_path: Path,
        summary_path: Path, negative_manifest_path: Path | None = None,
        candidate_review_path: Path | None = None) -> dict[str, Any]:
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
    candidate_adjudication = _candidate_adjudication_metrics(candidate_review_path, rows)
    summary = {
        'record_version': '1',
        'status': 'AGGREGATE_ONLY_POST_HOC_SOURCE_NATIVE_JATS_V1_2_DEVELOPMENT_REPLAY',
        'evaluation_use': 'DEVELOPMENT_ONLY_NOT_HOLDOUT',
        'artifact_scope': (
            'Aggregate detector and corpus metrics only. Individual source identifiers, '
            'source hashes, per-paper outputs, and candidate records are omitted.'
        ),
        'general_contract_version': contract_rows[0]['version'] if contract_rows else None,
        'percentage_contract_version': '1.2',
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
            'candidate_items_not_matching_eligible_correction_targets': sum(
                item['candidate_items_not_matching_eligible_correction_targets'] for item in rows
            ),
            'candidate_adjudication': candidate_adjudication,
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
            'Selected historical controls are not certified error-free. The source-first matched-negative rate is '
            'reported separately and is development-only; it is not a population estimate.'
        ),
        'synthetic_regression_evidence': regression_evidence,
        'contracts': per_contract,
        'per_detector_coverage': _aggregate_detector_coverage(rows),
        'percentage_relation_telemetry': _aggregate_percentage_relation_telemetry(rows),
        'matched_negative_relation_replay': (
            _negative_relation_replay(negative_manifest_path, validator)
            if negative_manifest_path else None
        ),
        'limitations': [
            'The direct JATS replay and eligibility classification are post-hoc development work; neither is blinded.',
            'Individual source bindings and per-document reports are deliberately omitted from this public summary.',
            'Source-level candidate adjudication is post-hoc DEVELOPMENT evidence and does not establish a paper error; '
            'paper_error_established remains false and verified_findings remains empty in every report.',
            'Publisher-version and supplement checks are limited to the evidence capsules for the reviewed items; '
            'no claim is made about scientific consequences.',
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
    parser.add_argument(
        '--negative-manifest', type=Path,
        help='Hash-bound DEVELOPMENT-only source-first v1.2 negative label manifest.',
    )
    parser.add_argument(
        '--candidate-review-file', type=Path,
        help='Optional hash-bound post-hoc DEVELOPMENT candidate adjudication.',
    )
    args = parser.parse_args()
    result = run(
        args.wave1_source_dir, args.wave2_source_dir, args.eligibility_file,
        args.summary, args.negative_manifest, args.candidate_review_file,
    )
    print(json.dumps(result['metrics'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
