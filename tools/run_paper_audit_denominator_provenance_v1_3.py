"""Replay pinned DEVELOPMENT percentage evidence under contract v1.3.

This versioned runner leaves the historical v1.2 summaries and manifests
untouched. It accepts only the hash-locked DEVELOPMENT negative manifest and
the existing positive DEVELOPMENT source manifests. Reserved records are not
loaded, scored, or joined.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NEGATIVE_MANIFEST_SHA256 = '76114422e36c3891700fbbdae2b23d20c3fb1be6bd964850f1c3eedb2145a6a6'
EXPECTED_NEGATIVE_RELATIONS = 4163

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from researchwitness.paper_audit import run_paper_audit
from tools.run_paper_audit_percentage_qualification import (
    _negative_source_table_ids,
    _normalized_element_path,
    _pair_negative_source_relations,
    _specifications,
    _target_matches,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _percentage_relations(report: dict[str, Any]) -> list[dict[str, Any]]:
    screens = report.get('arithmetic_screens', {})
    return (
        screens.get('structured_table_percentages', {}).get('relations', [])
        + screens.get('cell_ratio_percentages', {}).get('relations', [])
    )


def _denominator_provenance_record(relation: dict[str, Any]) -> dict[str, Any] | None:
    provenance = relation.get('denominator_provenance')
    if not isinstance(provenance, dict):
        return None
    return provenance


def _provenance_scope_summary(scope: Any) -> dict[str, Any] | None:
    if not isinstance(scope, dict):
        return None
    return {
        field: {'value': dimension.get('value'), 'status': dimension.get('status')}
        for field, dimension in scope.items() if isinstance(dimension, dict)
    }


def _candidate_provenance_summary(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    return {
        'candidate_id': candidate.get('candidate_id'),
        'value_exact': candidate.get('value_exact'),
        'source_anchor': candidate.get('source_anchor'),
        'structural_source': candidate.get('structural_source'),
        'provenance_class': candidate.get('provenance_class'),
        'semantic_scope': _provenance_scope_summary(candidate.get('semantic_scope')),
        'applicability': candidate.get('applicability'),
        'precedence_class': candidate.get('precedence_class'),
        'scope_match': candidate.get('scope_match'),
        'rejection_reasons': candidate.get('rejection_reasons'),
    }


def _provenance_capture(relation: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
    provenance = _denominator_provenance_record(relation) if relation else None
    if provenance is None:
        return 'NONE', None
    if relation and relation.get('status') in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
        return 'FULL_CHECKED_RELATION', provenance
    return 'COMPACT_SKIPPED_RELATION', {
        'resolution_status': provenance.get('resolution_status'),
        'resolution_reason': provenance.get('resolution_reason'),
        'relationship_scope': _provenance_scope_summary(provenance.get('relationship_scope')),
        'selected_denominator': _candidate_provenance_summary(provenance.get('selected_denominator')),
        'rejected_competing_denominators': [
            _candidate_provenance_summary(item)
            for item in provenance.get('rejected_competing_denominators', [])
            if isinstance(item, dict)
        ],
    }


def _selected_value(relation: dict[str, Any]) -> str | None:
    provenance = _denominator_provenance_record(relation)
    selected = provenance.get('selected_denominator') if provenance else None
    return selected.get('value_exact') if isinstance(selected, dict) else None


def _negative_source_relation_disposition(
    locator: dict[str, Any], relation: dict[str, Any] | None, operands_exact: bool,
) -> str:
    """Classify a source-confirmed correct relation against the current replay.

    Only an exact operand join that the current contract checks as a match is
    eligible negative evidence. An abstention, a changed parse, or an unmatched
    source locator remains visible but cannot increase that count.
    """
    if locator.get('arithmetic_correct') is not True:
        return 'SOURCE_LABEL_NOT_CONFIRMED'
    if relation is None:
        return 'UNMATCHED'
    if not operands_exact:
        return 'ANCHOR_ONLY_OR_CHANGED_OPERANDS'
    status = relation.get('status')
    if status == 'ELIGIBLE_CHECKED_MATCH':
        return 'ELIGIBLE_CORRECT_NEGATIVE'
    if status in ('INCOMPLETE', 'UNSUPPORTED'):
        return 'EXACT_OPERAND_ABSTENTION'
    if status == 'ELIGIBLE_CHECKED_MISMATCH':
        return 'EXACT_OPERAND_CHECKED_MISMATCH'
    return 'EXACT_OPERAND_OTHER_STATUS'


def _negative_relation_accounting(
    disposition_counts: Counter[str], source_labelled_abstentions: int,
) -> dict[str, Any]:
    """Build source-label accounting without treating locators as eligible checks."""
    return {
        'source_labelled_correct_relations': sum(disposition_counts.values()),
        'eligible_correct_source_relations': disposition_counts['ELIGIBLE_CORRECT_NEGATIVE'],
        'exact_operand_abstentions': disposition_counts['EXACT_OPERAND_ABSTENTION'],
        'exact_operand_checked_mismatches': disposition_counts['EXACT_OPERAND_CHECKED_MISMATCH'],
        'source_labelled_abstentions': source_labelled_abstentions,
        'source_anchor_only_or_changed_operand_relations': (
            disposition_counts['ANCHOR_ONLY_OR_CHANGED_OPERANDS']
        ),
        'unmatched_source_relations': disposition_counts['UNMATCHED'],
        'negative_relation_disposition_counts': dict(sorted(disposition_counts.items())),
    }


def _document_identity_accounting(source_records: list[dict[str, Any]]) -> dict[str, int]:
    """Separate manifest record count from distinct normalized DOI values.

    DOI equality is a conservative duplicate check, not proof of independent
    works: alternate identifiers and DOI aliases require separate resolution.
    """
    normalized_dois: set[str] = set()
    for source in source_records:
        if not isinstance(source, dict):
            raise ValueError('negative DEVELOPMENT source records must be objects')
        value = source.get('normalized_doi')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('negative DEVELOPMENT source record has no normalized DOI')
        normalized_dois.add(value.strip().lower())
    return {
        'source_records': len(source_records),
        'distinct_normalized_doi_count': len(normalized_dois),
    }


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        'candidate_id': candidate.get('id'),
        'relation_id': candidate.get('relation_id'),
        'type': candidate.get('type'),
        'table_id': candidate.get('table_id'),
        'row_identity': candidate.get('row_identity'),
        'table_caption': candidate.get('table_caption'),
        'numerator_exact': candidate.get('numerator_exact'),
        'denominator_exact': candidate.get('denominator_exact'),
        'reported_percent': candidate.get('reported_percent'),
        'recomputed_at_display_precision': candidate.get('recomputed_at_display_precision'),
        'source_anchor_paths': sorted({
            anchor.get('element_path') for anchor in candidate.get('source_anchors', [])
            if isinstance(anchor, dict) and anchor.get('element_path')
        }),
        'source_anchors': candidate.get('source_anchors', []),
    }


def _negative_replay(
    manifest_path: Path,
    output_path: Path,
    validator: Draft202012Validator,
) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest_hash = _sha256(manifest_bytes)
    if manifest_hash != EXPECTED_NEGATIVE_MANIFEST_SHA256:
        raise ValueError('negative replay requires the frozen v1.2 DEVELOPMENT source manifest')
    manifest = json.loads(manifest_bytes)
    if (manifest.get('source_pool') not in ('DEVELOPMENT', 'DEVELOPMENT_ONLY')
            or manifest.get('reserved_records_included') is not False
            or manifest.get('contract_version') != '1.2'
            or manifest.get('relation_count') != EXPECTED_NEGATIVE_RELATIONS):
        raise ValueError('negative replay manifest does not match the frozen DEVELOPMENT label contract')
    source_records = manifest.get('source_files', [])
    if not isinstance(source_records, list):
        raise ValueError('negative DEVELOPMENT manifest source_files must be a list')
    document_identity_counts = _document_identity_accounting(source_records)

    ledger: list[dict[str, Any]] = []
    report_records: list[dict[str, Any]] = []
    exact_join_count = 0
    anchor_only_count = 0
    unmatched_count = 0
    false_candidate_rows: list[dict[str, Any]] = []
    checked_wrong_denominator_rows: list[dict[str, Any]] = []
    zero_n_wrong_denominator_matches: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    abstained_source_relation_count = 0
    table_count = 0
    locator_count = 0
    expected_relation_types = {
        'table_percentage_recomputation': 'CELL_COUNT_OVER_DENOMINATOR_PERCENTAGE',
        'jats_cell_ratio_percentage_recomputation': 'DIRECT_N_OVER_N_PERCENTAGE',
    }

    for source in source_records:
        if (source.get('allocation_status') not in ('DEVELOPMENT_DOI_HASH_SPLIT', 'PREEXISTING_DEVELOPMENT')
                or source.get('split_status') != 'DEVELOPMENT'):
            raise ValueError('refusing to replay a source outside the DEVELOPMENT allocation')
        source_locators = source.get('relation_locators', [])
        if (not isinstance(source_locators, list)
                or any(not isinstance(item, dict) or item.get('arithmetic_correct') is not True
                       for item in source_locators)):
            raise ValueError(
                'negative DEVELOPMENT manifest contains a relation not source-confirmed as arithmetically correct'
            )
        source_path = Path(source['source_file'])
        raw = source_path.read_bytes()
        source_hash = _sha256(raw)
        if source_hash != source.get('source_sha256'):
            raise ValueError(f'{source_path.name}: source differs from its pinned hash')
        identifier = 'doi:' + str(source.get('normalized_doi', '')).strip().lower()
        if identifier == 'doi:':
            raise ValueError(f'{source_path.name}: missing stable source identifier')
        source_version = 'locked DEVELOPMENT JATS source ' + str(source.get('source_id', source_path.name))

        with tempfile.TemporaryDirectory(prefix='rw-denominator-v13-first-') as first_dir:
            first_output = Path(first_dir) / 'report'
            run_paper_audit(source_path, first_output, identifier, source_version)
            report_bytes = (first_output / 'report.json').read_bytes()
            html_bytes = (first_output / 'report.html').read_bytes()
            report = json.loads(report_bytes)
            errors = list(validator.iter_errors(report))
            if errors:
                raise ValueError(f'{source_path.name}: v1.3 report fails schema: {errors[0].message}')
            if report.get('source', {}).get('sha256') != source_hash:
                raise ValueError(f'{source_path.name}: report does not bind the locked source')
            if report.get('paper_error_established') is not False or report.get('verified_findings'):
                raise ValueError(f'{source_path.name}: report crossed the candidate-only boundary')
            with tempfile.TemporaryDirectory(prefix='rw-denominator-v13-repeat-') as second_dir:
                second_output = Path(second_dir) / 'report'
                run_paper_audit(source_path, second_output, identifier, source_version)
                repeat_report_bytes = (second_output / 'report.json').read_bytes()
                repeat_html_bytes = (second_output / 'report.html').read_bytes()
                repeat_report_hash = _sha256(repeat_report_bytes)
                repeat_json = report_bytes == repeat_report_bytes
                repeat_html = html_bytes == repeat_html_bytes
            if not repeat_json or not repeat_html:
                raise ValueError(f'{source_path.name}: v1.3 JSON/HTML replay differs')

        relations = _percentage_relations(report)
        relation_pairs = _pair_negative_source_relations(source_locators, relations)
        candidates_by_relation = {
            str(item.get('relation_id')): item
            for item in report.get('candidate_anomalies', []) if item.get('relation_id')
        }
        report_relation_count = 0
        source_table_ids = _negative_source_table_ids(source)
        table_count += len(source_table_ids)
        for locator, (relation, operands_exact) in zip(source_locators, relation_pairs):
            locator_count += 1
            report_relation_count += 1
            path_key = _normalized_element_path(locator.get('cell_path'))
            anchor_matches = False
            if relation is not None:
                anchor = relation.get('source_anchor')
                anchor_matches = (
                    isinstance(anchor, dict)
                    and anchor.get('source_sha256') == source_hash
                    and _normalized_element_path(anchor.get('element_path')) == path_key
                    and relation.get('relation_type') == expected_relation_types.get(locator.get('contract_id'))
                    and relation.get('contract_version') == '1.3'
                )
                if not anchor_matches:
                    raise ValueError(f'{source_path.name}: relation join has an invalid source anchor or contract')
            join_level = 'EXACT_OPERANDS' if relation is not None and operands_exact else (
                'SOURCE_ANCHOR_ONLY' if anchor_matches else 'UNMATCHED'
            )
            disposition = _negative_source_relation_disposition(locator, relation, operands_exact)
            disposition_counts[disposition] += 1
            if join_level == 'EXACT_OPERANDS':
                exact_join_count += 1
            elif join_level == 'SOURCE_ANCHOR_ONLY':
                anchor_only_count += 1
            else:
                unmatched_count += 1

            relation_id = str(relation.get('relation_id')) if relation else None
            candidate = candidates_by_relation.get(relation_id) if relation_id else None
            status = str(relation.get('status')) if relation else 'UNMATCHED'
            if relation is not None:
                status_counts[status] += 1
                if status in ('INCOMPLETE', 'UNSUPPORTED'):
                    abstained_source_relation_count += 1
            selected_value = _selected_value(relation) if relation else None
            displayed_denominator = relation.get('denominator_exact') if relation else None
            expected_denominator = str(locator.get('denominator'))
            denominator_differs = (
                displayed_denominator is not None and str(displayed_denominator) != expected_denominator
            ) or (
                status in ('INCOMPLETE', 'UNSUPPORTED') and selected_value is not None
                and selected_value != expected_denominator
            )
            emitted = bool(candidate) or (relation is not None and relation.get('finding_emitted') is True)
            ledger_row = {
                'source_id': source.get('source_id'),
                'source_sha256': source_hash,
                'contract_id': locator.get('contract_id'),
                'table_id': locator.get('table_id'),
                'source_cell_path': locator.get('cell_path'),
                'source_operands': {
                    'numerator_exact': str(locator.get('numerator')),
                    'denominator_exact': expected_denominator,
                    'reported_percent': str(locator.get('reported_percent')),
                    'display_precision': locator.get('display_precision_digits'),
                    'arithmetic_correct': locator.get('arithmetic_correct'),
                },
                'join_level': join_level,
                'negative_relation_disposition': disposition,
                'report_relation_id': relation_id,
                'report_relation_status': status,
                'report_operands': {
                    'numerator_exact': relation.get('numerator_exact') if relation else None,
                    'denominator_exact': displayed_denominator,
                    'reported_percent': relation.get('reported_percent') if relation else None,
                    'display_precision': relation.get('display_precision') if relation else None,
                },
                'report_source_anchor': relation.get('source_anchor') if relation else None,
                'operand_differences': {
                    'numerator': relation is not None and relation.get('numerator_exact') != str(locator.get('numerator')),
                    'denominator': denominator_differs,
                    'percentage': relation is not None and relation.get('reported_percent') != str(locator.get('reported_percent')),
                    'display_precision': relation is not None and relation.get('display_precision') != locator.get('display_precision_digits'),
                },
                'denominator_scope_resolved': relation.get('denominator_scope_resolved') if relation else None,
                'primary_skip_reason': relation.get('primary_skip_reason') if relation else 'RELATION_UNMATCHED',
                'candidate_emitted': emitted,
                'candidate': _candidate_summary(candidate),
                'denominator_provenance_capture_level': _provenance_capture(relation)[0],
                'denominator_provenance': _provenance_capture(relation)[1],
            }
            ledger.append(ledger_row)
            if emitted and status == 'ELIGIBLE_CHECKED_MISMATCH':
                false_candidate_rows.append(ledger_row)
            if denominator_differs and status in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
                checked_wrong_denominator_rows.append(ledger_row)
                if str(locator.get('numerator')) == '0' and status == 'ELIGIBLE_CHECKED_MATCH':
                    zero_n_wrong_denominator_matches.append(ledger_row)

        if report_relation_count != len(source_locators):
            raise ValueError(f'{source_path.name}: locator/replay ledger count differs')
        telemetry = report.get('arithmetic_screens', {}).get('percentage_relation_telemetry', {})
        if telemetry.get('accounting_invariant') is not True:
            raise ValueError(f'{source_path.name}: relation telemetry accounting invariant failed')
        report_records.append({
            'source_id': source.get('source_id'),
            'source_sha256': source_hash,
            'source_bytes': len(raw),
            'labelled_relation_count': len(source_locators),
            'source_table_count': len(source_table_ids),
            'report_sha256': _sha256(report_bytes),
            'report_html_sha256': _sha256(html_bytes),
            'repeat_report_sha256': repeat_report_hash,
            'repeatable_json': repeat_json,
            'repeatable_html': repeat_html,
            'relation_telemetry': telemetry,
        })

    if (len(report_records) != manifest.get('source_document_count')
            or table_count != manifest.get('table_count')
            or locator_count != EXPECTED_NEGATIVE_RELATIONS):
        raise ValueError('negative DEVELOPMENT replay does not reconcile with the frozen manifest totals')

    source_document_false_candidates = sorted({item['source_id'] for item in false_candidate_rows})
    output = {
        'artifact_type': 'RESEARCHWITNESS_PERCENTAGE_DENOMINATOR_PROVENANCE_NEGATIVE_REPLAY_V1_3',
        'record_version': 1,
        'evaluation_use': 'POST_HOC_DEVELOPMENT_ONLY_NOT_HOLDOUT',
        'contract_version': '1.3',
        'source_label_contract_version': '1.2_LOCKED_SOURCE_FIRST_LABELS',
        'reserved_records_included': False,
        'detector_executed_on_reserved_records': False,
        'source_manifest_path': str(manifest_path.relative_to(ROOT)),
        'source_manifest_sha256': manifest_hash,
        'runner_sha256': _file_sha256(Path(__file__)),
        'ledger_provenance_capture_policy': (
            'Full selected and rejected denominator candidates are retained for every checked relation. '
            'Skipped relations retain scope values, selected/rejected anchors, applicability, scope-match details, and reasons.'
        ),
        'summary': {
            **_negative_relation_accounting(disposition_counts, abstained_source_relation_count),
            **document_identity_counts,
            'source_tables': table_count,
            'exact_operand_joins': exact_join_count,
            'anchor_only_joins': anchor_only_count,
            'source_anchor_join_coverage': exact_join_count + anchor_only_count,
            'candidate_emissions_on_source_labelled_correct_relations': len(false_candidate_rows),
            'candidate_emission_documents': source_document_false_candidates,
            'checked_wrong_denominator_relations': len(checked_wrong_denominator_rows),
            'zero_numerator_wrong_denominator_checked_matches': len(zero_n_wrong_denominator_matches),
            'report_relation_status_counts': dict(sorted(status_counts.items())),
            'report_json_repeatable': sum(item['repeatable_json'] for item in report_records),
            'report_html_repeatable': sum(item['repeatable_html'] for item in report_records),
            'report_repeatability_denominator': len(report_records),
            'telemetry_accounting_invariant': all(
                item['relation_telemetry'].get('accounting_invariant') is True for item in report_records
            ),
        },
        'reports': report_records,
        'relation_ledger': ledger,
        'false_candidate_records': false_candidate_rows,
        'checked_wrong_denominator_records': checked_wrong_denominator_rows,
        'zero_numerator_wrong_denominator_records': zero_n_wrong_denominator_matches,
        'limitations': [
            'This is post-hoc DEVELOPMENT evidence and does not estimate unseen error rates.',
            'The source-first labels remain authoritative; exact operand and anchor-only joins are reported separately.',
            'A denominator arithmetic candidate does not establish that a paper is wrong or affect its conclusions.',
            'Distinct normalized DOI values do not establish independent works without alias resolution.',
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return output


def _positive_replay(
    wave1_source_dir: Path,
    wave2_source_dir: Path,
    eligibility_path: Path,
    historical_review_path: Path,
    new_candidate_review_path: Path,
    output_path: Path,
    validator: Draft202012Validator,
) -> dict[str, Any]:
    specs, eligibility = _specifications(eligibility_path)
    if len(specs) != 33:
        raise ValueError(f'expected the locked 33-report DEVELOPMENT corpus, got {len(specs)}')
    report_rows: list[dict[str, Any]] = []
    runtime_reports: dict[str, dict[str, Any]] = {}
    current_candidate_ledger: list[dict[str, Any]] = []
    checked_relationship_provenance: list[dict[str, Any]] = []
    total_candidates = 0
    target_cells = target_matches = eligible_issues = eligible_issue_matches = 0
    report_statuses: Counter[str] = Counter()

    for spec in specs:
        root = wave1_source_dir if spec['corpus'] == 'wave1_correction_development' else wave2_source_dir
        source_path = root / spec['source_file']
        raw = source_path.read_bytes()
        source_hash = _sha256(raw)
        if source_hash != spec['expected_sha256']:
            raise ValueError(f"{spec['case_id']}: source differs from its pinned manifest hash")
        with tempfile.TemporaryDirectory(prefix='rw-denominator-v13-positive-first-') as first_dir:
            first_output = Path(first_dir) / 'report'
            run_paper_audit(source_path, first_output, spec['identifier'], spec['source_version'][:100])
            report_bytes = (first_output / 'report.json').read_bytes()
            html_bytes = (first_output / 'report.html').read_bytes()
            report = json.loads(report_bytes)
            errors = list(validator.iter_errors(report))
            if errors:
                raise ValueError(f"{spec['case_id']}: v1.3 report fails schema: {errors[0].message}")
            if (report.get('source', {}).get('sha256') != source_hash
                    or report.get('paper_error_established') is not False
                    or report.get('verified_findings')):
                raise ValueError(f"{spec['case_id']}: source binding/candidate-only report invariant failed")
            with tempfile.TemporaryDirectory(prefix='rw-denominator-v13-positive-repeat-') as second_dir:
                second_output = Path(second_dir) / 'report'
                run_paper_audit(source_path, second_output, spec['identifier'], spec['source_version'][:100])
                repeat_json_bytes = (second_output / 'report.json').read_bytes()
                repeat_html_bytes = (second_output / 'report.html').read_bytes()
                repeat_json = report_bytes == repeat_json_bytes
                repeat_html = html_bytes == repeat_html_bytes
                repeat_report_hash = _sha256(repeat_json_bytes)
            if not repeat_json or not repeat_html:
                raise ValueError(f"{spec['case_id']}: v1.3 JSON/HTML replay differs")

        relations = _percentage_relations(report)
        candidates = report.get('candidate_anomalies', [])
        total_candidates += len(candidates)
        targets = (spec.get('eligibility_record') or {}).get('target_cell_assertions', [])
        matched_target_records = [
            target for target in targets
            if any(_target_matches(candidate, target) for candidate in candidates)
        ]
        eligible = (spec.get('eligibility_record') or {}).get('eligibility') == 'SUPPORTED_BY_CURRENT_CONTRACT'
        if eligible:
            eligible_issues += 1
            if len(matched_target_records) == len(targets):
                eligible_issue_matches += 1
        target_cells += len(targets) if eligible else 0
        target_matches += len(matched_target_records) if eligible else 0
        for relation in relations:
            report_statuses[str(relation.get('status'))] += 1
        candidate_by_relation = {
            str(item.get('relation_id')): item for item in candidates if item.get('relation_id')
        }
        relation_by_id = {
            str(item.get('relation_id')): item for item in relations if item.get('relation_id')
        }
        for relation in relations:
            if relation.get('status') not in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH'):
                continue
            provenance = _denominator_provenance_record(relation)
            selected = provenance.get('selected_denominator') if provenance else None
            if (relation.get('denominator_scope_resolved') is not True
                    or not isinstance(selected, dict)
                    or provenance.get('resolution_status') != 'RESOLVED'
                    or selected.get('value_exact') != relation.get('denominator_exact')
                    or selected.get('source_anchor') != relation.get('denominator_source_anchor')
                    or not all(item.get('rejection_reasons') for item in provenance.get('rejected_competing_denominators', []))):
                raise ValueError(
                    f"{spec['case_id']}: checked v1.3 relation lacks a complete selected/rejected denominator record"
                )
            checked_relationship_provenance.append({
                'case_id': spec['case_id'],
                'corpus': spec['corpus'],
                'role': spec['role'],
                'source_sha256': source_hash,
                'report_sha256': _sha256(report_bytes),
                'relation_id': relation['relation_id'],
                'relation_type': relation['relation_type'],
                'detector_id': relation['detector_id'],
                'contract_version': relation['contract_version'],
                'status': relation['status'],
                'source_anchor': relation['source_anchor'],
                'numerator_exact': relation['numerator_exact'],
                'denominator_exact': relation['denominator_exact'],
                'reported_percent': relation['reported_percent'],
                'display_precision': relation['display_precision'],
                'recomputed_at_display_precision': relation['recomputed_at_display_precision'],
                'denominator_scope_resolved': relation['denominator_scope_resolved'],
                'denominator_source_anchor': relation['denominator_source_anchor'],
                'denominator_provenance': provenance,
            })
        for candidate in candidates:
            candidate_relation = relation_by_id.get(str(candidate.get('relation_id')))
            current_candidate_ledger.append({
                'case_id': spec['case_id'],
                'corpus': spec['corpus'],
                'role': spec['role'],
                'source_sha256': source_hash,
                'report_sha256': _sha256(report_bytes),
                'source_cell_path': (
                    candidate_relation.get('source_anchor', {}).get('element_path')
                    if candidate_relation else None
                ),
                'candidate': _candidate_summary(candidate),
                'relation_status': candidate_relation.get('status') if candidate_relation else None,
                'relation_primary_skip_reason': candidate_relation.get('primary_skip_reason') if candidate_relation else None,
                'denominator_scope_resolved': candidate_relation.get('denominator_scope_resolved') if candidate_relation else None,
                'denominator_exact': candidate_relation.get('denominator_exact') if candidate_relation else None,
                'denominator_provenance': (
                    _denominator_provenance_record(candidate_relation) if candidate_relation else None
                ),
            })
        runtime_reports[spec['case_id']] = {
            'report': report,
            'spec': spec,
            'relations': relations,
            'candidate_by_relation': candidate_by_relation,
            'report_sha256': _sha256(report_bytes),
        }
        telemetry = report.get('arithmetic_screens', {}).get('percentage_relation_telemetry', {})
        if telemetry.get('accounting_invariant') is not True:
            raise ValueError(f"{spec['case_id']}: relation telemetry accounting invariant failed")
        report_rows.append({
            'case_id': spec['case_id'],
            'corpus': spec['corpus'],
            'role': spec['role'],
            'source_sha256': source_hash,
            'source_bytes': len(raw),
            'report_sha256': _sha256(report_bytes),
            'repeat_report_sha256': repeat_report_hash,
            'report_html_sha256': _sha256(html_bytes),
            'repeatable_json': repeat_json,
            'repeatable_html': repeat_html,
            'candidate_count': len(candidates),
            'candidate_records': [_candidate_summary(item) for item in candidates],
            'relation_status_counts': dict(sorted(Counter(
                str(item.get('status')) for item in relations
            ).items())),
            'percentage_relation_telemetry': telemetry,
            'eligible_target_cells': len(targets) if eligible else 0,
            'matched_target_cells': len(matched_target_records) if eligible else 0,
            'eligibility': (spec.get('eligibility_record') or {}).get('eligibility', 'SELECTED_CONTROL'),
        })

    historical = json.loads(historical_review_path.read_text(encoding='utf-8'))
    if (historical.get('status') != 'POST_HOC_DEVELOPMENT_SOURCE_ADJUDICATION'
            or historical.get('percentage_contract_version') != '1.2'
            or len(historical.get('items', [])) != 19):
        raise ValueError('historical candidate adjudication is not the pinned 19-item v1.2 review')
    reviewed_items: list[dict[str, Any]] = []
    current_candidate_items = 0
    for item in historical['items']:
        case_id = item['case_id']
        replay = runtime_reports.get(case_id)
        if replay is None or replay['report'].get('source', {}).get('sha256') != item.get('source_sha256'):
            raise ValueError(f'{case_id}: candidate review does not bind a replayed positive DEVELOPMENT source')
        candidate_type_prefix = 'jats-cell-ratio' if item['candidate_id'].startswith('jats-cell-ratio-') else 'structured-table'
        detector_id = (
            'jats_cell_ratio_percentage_recomputation'
            if candidate_type_prefix == 'jats-cell-ratio'
            else 'table_percentage_recomputation'
        )
        anchor_paths = {
            _normalized_element_path(path) for path in item.get('anchors', [])
            if _normalized_element_path(path) is not None
        }
        target_assertions = (replay['spec'].get('eligibility_record') or {}).get('target_cell_assertions', [])
        source_path_from_target = next((
            target.get('source_cell_xpath') for target in target_assertions
            if _normalized_element_path(target.get('source_cell_xpath')) in anchor_paths
        ), None)
        preferred_path = _normalized_element_path(source_path_from_target)
        relation_path_candidates = {preferred_path} if preferred_path is not None else anchor_paths
        relation_matches = [
            relation for relation in replay['relations']
            if relation.get('detector_id') == detector_id
            and _normalized_element_path(relation.get('source_anchor', {}).get('element_path')) in relation_path_candidates
        ]
        if len(relation_matches) > 1:
            relation_matches = [
                relation for relation in relation_matches
                if relation.get('numerator_exact') == str(item.get('numerator'))
                and relation.get('reported_percent') == str(item.get('reported_percent'))
                and relation.get('display_precision') == item.get('display_precision_digits')
            ]
        relation = relation_matches[0] if len(relation_matches) == 1 else None
        source_cell_path = (
            source_path_from_target
            or (relation.get('source_anchor', {}).get('element_path') if relation else None)
        )
        normalized_path = _normalized_element_path(source_cell_path)
        current_candidate = replay['candidate_by_relation'].get(str(relation.get('relation_id'))) if relation else None
        if current_candidate is not None:
            current_candidate_items += 1

        target_match = False
        for target in target_assertions:
            if _normalized_element_path(target.get('source_cell_xpath')) == normalized_path:
                target_match = bool(current_candidate and _target_matches(current_candidate, target))
                break

        previous_class = item['classification']
        if 'KNOWN_CORRECTION_TARGET' in previous_class:
            classification = 'KNOWN_CORRECTION_TARGET' if target_match else 'UNRESOLVED'
        elif relation is None:
            classification = 'PARSER_ARTIFACT'
        elif relation.get('status') == 'ELIGIBLE_CHECKED_MISMATCH':
            if previous_class == 'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY':
                classification = 'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY'
            elif previous_class == 'SOURCE_REPRODUCED_ARITHMETIC_DISCREPANCY_VERSION_UNVERIFIED':
                classification = 'SOURCE_REPRODUCED_VERSION_UNVERIFIED_DISCREPANCY'
            elif (previous_class == 'SCOPE_DENOMINATOR_NOT_EXPLICIT' and current_candidate is not None
                    and re.search(r'(?:correction|corrected table).{0,80}(?:reviewed|checked)',
                                  str(item.get('review_basis', '')), re.IGNORECASE)):
                classification = 'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY'
            else:
                classification = 'UNRESOLVED'
        elif relation.get('status') == 'ELIGIBLE_CHECKED_MATCH':
            classification = (
                'BENIGN_AFTER_DENOMINATOR_FIX'
                if str(relation.get('denominator_exact')) != str(item.get('denominator'))
                else 'UNRESOLVED'
            )
        elif relation.get('status') in ('INCOMPLETE', 'UNSUPPORTED'):
            reason = relation.get('primary_skip_reason')
            classification = (
                'SCOPE_DENOMINATOR_NOT_EXPLICIT'
                if isinstance(reason, str) and (
                    'DENOMINATOR' in reason or reason == 'MISSINGNESS_CHANGES_DENOMINATOR'
                ) else 'PARSER_ARTIFACT' if reason == 'TABLE_STRUCTURE_UNSUPPORTED' else 'UNRESOLVED'
            )
        else:
            classification = 'UNRESOLVED'

        reviewed_items.append({
            'case_id': case_id,
            'source_sha256': item['source_sha256'],
            'v1_2_candidate_id': item['candidate_id'],
            'v1_2_relation_id': item['relation_id'],
            'v1_2_classification': previous_class,
            'source_cell_path': source_cell_path,
            'v1_3_relation_id': relation.get('relation_id') if relation else None,
            'v1_3_relation_status': relation.get('status') if relation else 'RELATION_NOT_FOUND',
            'v1_3_primary_skip_reason': relation.get('primary_skip_reason') if relation else None,
            'v1_3_candidate': _candidate_summary(current_candidate),
            'v1_3_selected_denominator': (
                _denominator_provenance_record(relation).get('selected_denominator')
                if relation and _denominator_provenance_record(relation) else None
            ),
            'target_candidate_match': target_match if 'KNOWN_CORRECTION_TARGET' in previous_class else None,
            'classification': classification,
        })

    classification_counts = Counter(item['classification'] for item in reviewed_items)
    adjudicated_candidate_paths = {
        (item['case_id'], _normalized_element_path(item['source_cell_path']))
        for item in reviewed_items if item.get('source_cell_path')
    }
    for item in current_candidate_ledger:
        item['matches_historical_v1_2_slot'] = (
            item.get('source_cell_path') is not None
            and (item['case_id'], _normalized_element_path(item['source_cell_path']))
            in adjudicated_candidate_paths
        )
        item['classification'] = (
            next((reviewed['classification'] for reviewed in reviewed_items
                  if reviewed['case_id'] == item['case_id']
                  and _normalized_element_path(reviewed.get('source_cell_path'))
                  == _normalized_element_path(item.get('source_cell_path'))),
                 'UNRESOLVED')
        )
    newly_emitted_candidates = [
        item for item in current_candidate_ledger if not item['matches_historical_v1_2_slot']
    ]
    new_candidate_review = json.loads(new_candidate_review_path.read_text(encoding='utf-8'))
    if (new_candidate_review.get('artifact_type')
            != 'RESEARCHWITNESS_PERCENTAGE_V1_3_NEW_CANDIDATE_SOURCE_ADJUDICATIONS'
            or new_candidate_review.get('contract_version') != '1.3'
            or new_candidate_review.get('reserved_records_included') is not False
            or new_candidate_review.get('detector_executed_on_reserved_records') is not False):
        raise ValueError('new candidate source adjudication is not the pinned v1.3 DEVELOPMENT-only artifact')
    new_review_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for review in new_candidate_review.get('records', []):
        key = (str(review.get('case_id')), str(review.get('relation_id')))
        if key in new_review_by_key:
            raise ValueError(f'duplicate new candidate source adjudication: {key}')
        new_review_by_key[key] = review
    new_candidate_by_key = {
        (str(item['case_id']), str((item.get('candidate') or {}).get('relation_id'))): item
        for item in newly_emitted_candidates
    }
    if set(new_review_by_key) != set(new_candidate_by_key):
        raise ValueError('new candidate source adjudications do not exactly cover unmatched v1.3 outputs')
    allowed_new_candidate_classes = {
        'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY',
        'SOURCE_REPRODUCED_VERSION_UNVERIFIED_DISCREPANCY',
    }
    for key, review in new_review_by_key.items():
        emitted = new_candidate_by_key[key]
        candidate = emitted['candidate']
        evidence = review.get('relationship_evidence') or {}
        provenance = emitted.get('denominator_provenance') or {}
        selected = provenance.get('selected_denominator') or {}
        anchors = {
            anchor.get('element_path'): anchor
            for anchor in candidate.get('source_anchors', [])
            if isinstance(anchor, dict) and anchor.get('element_path')
        }
        if (review.get('source_sha256') != emitted.get('source_sha256')
                or review.get('candidate_id') != candidate.get('candidate_id')
                or _normalized_element_path(review.get('source_cell_path'))
                != _normalized_element_path(emitted.get('source_cell_path'))
                or review.get('classification') not in allowed_new_candidate_classes
                or emitted.get('relation_status') != 'ELIGIBLE_CHECKED_MISMATCH'
                or emitted.get('denominator_scope_resolved') is not True
                or candidate.get('numerator_exact') != evidence.get('numerator')
                or candidate.get('denominator_exact') != evidence.get('denominator')
                or candidate.get('reported_percent') != evidence.get('reported_percent')
                or candidate.get('recomputed_at_display_precision') != evidence.get('recomputed_percent')
                or selected.get('value_exact') != evidence.get('denominator')
                or selected.get('provenance_class') != evidence.get('denominator_provenance_class')
                or selected.get('source_anchor', {}).get('element_path') != evidence.get('denominator_source_path')
                or selected.get('source_anchor', {}).get('quote') != evidence.get('denominator_quote')):
            raise ValueError(f'new candidate source adjudication does not match replay evidence: {key}')
        for path_key, quote_key in (
            ('numerator_source_path', 'numerator_quote'),
            ('percentage_source_path', 'percentage_quote'),
        ):
            anchor = anchors.get(evidence.get(path_key))
            if anchor is None or anchor.get('quote') != evidence.get(quote_key):
                raise ValueError(f'new candidate source quote is not bound to its pinned source anchor: {key}/{path_key}')
        emitted['classification'] = review['classification']
        emitted['source_adjudication'] = review

    arithmetic_valid_classes = {
        'KNOWN_CORRECTION_TARGET',
        'SOURCE_REPRODUCED_UNCORRECTED_ARITHMETIC_DISCREPANCY',
        'SOURCE_REPRODUCED_VERSION_UNVERIFIED_DISCREPANCY',
    }
    arithmetic_valid_count = sum(classification_counts[key] for key in arithmetic_valid_classes)
    current_classification_counts = Counter(
        str(item.get('classification', 'UNRESOLVED')) for item in current_candidate_ledger
    )
    expected_checked_relationships = sum(
        report_statuses[status]
        for status in ('ELIGIBLE_CHECKED_MATCH', 'ELIGIBLE_CHECKED_MISMATCH')
    )
    if len(checked_relationship_provenance) != expected_checked_relationships:
        raise ValueError('checked v1.3 relation provenance ledger does not cover every arithmetic check')
    current_arithmetic_valid_count = sum(
        current_classification_counts[key] for key in arithmetic_valid_classes
    )
    eligible_historical_slots = [
        item for item in reviewed_items
        if item.get('v1_3_relation_status') == 'ELIGIBLE_CHECKED_MISMATCH'
        and item.get('v1_3_candidate') is not None
    ]
    v13_output = {
        'artifact_type': 'RESEARCHWITNESS_PERCENTAGE_DENOMINATOR_PROVENANCE_POSITIVE_REPLAY_V1_3',
        'record_version': 1,
        'evaluation_use': 'POST_HOC_DEVELOPMENT_ONLY_NOT_HOLDOUT',
        'contract_version': '1.3',
        'reserved_records_included': False,
        'detector_executed_on_reserved_records': False,
        'positive_source_eligibility_sha256': _file_sha256(eligibility_path),
        'historical_candidate_review_sha256': _file_sha256(historical_review_path),
        'new_candidate_source_adjudication_sha256': _file_sha256(new_candidate_review_path),
        'runner_sha256': _file_sha256(Path(__file__)),
        'summary': {
            'development_reports': len(report_rows),
            'repeatable_json_reports': sum(item['repeatable_json'] for item in report_rows),
            'repeatable_html_reports': sum(item['repeatable_html'] for item in report_rows),
            'correction_issues_eligible_under_v1_2_source_review': eligible_issues,
            'eligible_target_cells_under_v1_2_source_review': target_cells,
            'matched_target_cells_under_v1_3': target_matches,
            'all_eligible_issues_detected_under_v1_3': eligible_issue_matches == eligible_issues,
            'current_report_candidates_across_development_corpus': total_candidates,
            'new_v1_3_candidates_not_in_historical_v1_2_review': len(newly_emitted_candidates),
            'current_percentage_candidate_types': dict(sorted(Counter(
                candidate.get('type')
                for report_row in report_rows for candidate in report_row['candidate_records']
                if candidate.get('type')
            ).items())),
            'historical_candidate_slots_reaudited': len(reviewed_items),
            'historical_candidate_slots_with_v1_3_candidate': current_candidate_items,
            'historical_candidate_classification_counts': dict(sorted(classification_counts.items())),
            'arithmetic_valid_historical_slots': arithmetic_valid_count,
            'arithmetic_validity_over_all_19_historical_slots': {
                'numerator': arithmetic_valid_count,
                'denominator': len(reviewed_items),
            },
            'arithmetic_validity_after_v1_3_historical_eligibility_reaudit': {
                'numerator': sum(item['classification'] in arithmetic_valid_classes for item in eligible_historical_slots),
                'denominator': len(eligible_historical_slots),
                'scope_ineligible_historical_slots': len(reviewed_items) - len(eligible_historical_slots),
                'scope_ineligible_reason_counts': dict(sorted(Counter(
                    item['classification'] for item in reviewed_items if item not in eligible_historical_slots
                ).items())),
            },
            'current_candidate_classification_counts': dict(sorted(current_classification_counts.items())),
            'current_candidate_arithmetic_validity': {
                'numerator': current_arithmetic_valid_count,
                'denominator': len(current_candidate_ledger),
                'invalid_or_unresolved_candidates': len(current_candidate_ledger) - current_arithmetic_valid_count,
            },
            'relation_status_counts_across_33_reports': dict(sorted(report_statuses.items())),
            'checked_relationships_with_full_denominator_provenance': len(checked_relationship_provenance),
            'checked_relationship_provenance_complete': (
                len(checked_relationship_provenance) == expected_checked_relationships
            ),
            'telemetry_accounting_invariant': all(
                item['percentage_relation_telemetry'].get('accounting_invariant') is True
                for item in report_rows
            ),
        },
        'reports': report_rows,
        'checked_relationship_provenance': checked_relationship_provenance,
        'historical_candidate_readjudication': reviewed_items,
        'all_v1_3_percentage_candidate_records': current_candidate_ledger,
        'limitations': [
            'The positive corpus is post-hoc DEVELOPMENT evidence and does not estimate unseen sensitivity or precision.',
            'All 19 v1.2 candidate slots remain visible in the denominator of the frozen comparison ratio.',
            'The candidate arithmetic-validity result is source-screen evidence, not evidence that a paper is wrong or that conclusions change.',
            'Correction eligibility remains bound to the source-first v1.2 review; v1.3 replay verifies target-cell behavior, not correction notice truth.',
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(v13_output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return v13_output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wave1-source-dir', type=Path, required=True)
    parser.add_argument('--wave2-source-dir', type=Path, required=True)
    parser.add_argument('--negative-manifest', type=Path,
                        default=ROOT / 'validation/paper-audit-percentage-qualification/DEVELOPMENT_NEGATIVE_SOURCE_MANIFEST_V1_2.json')
    parser.add_argument('--positive-eligibility', type=Path,
                        default=ROOT / 'validation/paper-audit-percentage-qualification/POSITIVE_SOURCE_FIRST_ELIGIBILITY_V1_2.json')
    parser.add_argument('--historical-candidate-review', type=Path,
                        default=ROOT / 'validation/paper-audit-percentage-qualification/DEVELOPMENT_CANDIDATE_ADJUDICATION_V1_2.json')
    parser.add_argument('--new-candidate-adjudications', type=Path,
                        default=ROOT / 'validation/paper-audit-denominator-provenance/DEVELOPMENT_NEW_CANDIDATE_SOURCE_ADJUDICATIONS_V1_3.json')
    parser.add_argument('--negative-output', type=Path,
                        default=ROOT / 'validation/paper-audit-denominator-provenance/DEVELOPMENT_NEGATIVE_REPLAY_V1_3.json')
    parser.add_argument('--positive-output', type=Path,
                        default=ROOT / 'validation/paper-audit-denominator-provenance/DEVELOPMENT_POSITIVE_REPLAY_V1_3.json')
    parser.add_argument('--negative-only', action='store_true')
    parser.add_argument('--positive-only', action='store_true')
    args = parser.parse_args()
    if args.negative_only and args.positive_only:
        parser.error('choose at most one replay scope')
    schema = json.loads((ROOT / 'schemas/paper-audit.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    result: dict[str, Any] = {}
    if not args.positive_only:
        result['negative'] = _negative_replay(args.negative_manifest, args.negative_output, validator)
    if not args.negative_only:
        result['positive'] = _positive_replay(
            args.wave1_source_dir, args.wave2_source_dir,
            args.positive_eligibility, args.historical_candidate_review,
            args.new_candidate_adjudications,
            args.positive_output, validator,
        )
    print(json.dumps({key: value['summary'] for key, value in result.items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
