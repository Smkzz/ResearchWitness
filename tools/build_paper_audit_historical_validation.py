"""Build an aggregate-only validation summary for the 15 locked candidates.

Source-level checks are performed against the pinned JATS captures, deterministic
renderings, locked reports, and PDF comparison metadata. The output contains
aggregate counts only; it omits source identifiers, hashes, arithmetic records,
and per-case findings.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACK = ROOT / 'validation/paper-audit-capability-wave/NOVEL_CANDIDATE_TRACK.json'
SOURCE_MANIFEST = ROOT / 'validation/paper-audit-wave-2/source_manifest.json'
OUTPUT_LOCK = ROOT / 'validation/paper-audit-wave-2/results/LOCK.json'
SOURCE_FORMAT = ROOT / 'validation/paper-audit-wave-2/frozen-baseline/SOURCE_FORMAT_SUMMARY.json'
RENDERER = ROOT / 'tools/render_pmc_jats.py'

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from researchwitness.paper_audit import run_paper_audit
from tools.render_pmc_jats import render


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _candidate_values(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        'id', 'type', 'numerator_exact', 'denominator_exact', 'reported_percent',
        'recomputed_percent', 'recomputed_at_display_precision', 'rounding_tolerance_percentage_points',
        'marker', 'values_exact',
    )
    return {key: candidate[key] for key in keys if key in candidate}


def _same_arithmetic(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if all(old.get(key) is not None for key in ('numerator_exact', 'denominator_exact', 'reported_percent')):
        return all(old.get(key) == new.get(key) for key in (
            'numerator_exact', 'denominator_exact', 'reported_percent',
        ))
    values = set(old.get('values_exact', []))
    return bool(values) and values.issubset(set(new.get('values_exact', [])))


def build(source_dir: Path, output_path: Path) -> dict[str, Any]:
    track = json.loads(TRACK.read_text(encoding='utf-8'))
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf-8'))
    lock = json.loads(OUTPUT_LOCK.read_text(encoding='utf-8'))
    format_summary = json.loads(SOURCE_FORMAT.read_text(encoding='utf-8'))
    if _file_sha256(SOURCE_MANIFEST) != lock['source_manifest_sha256']:
        raise ValueError('The locked wave-2 report does not bind the current source manifest')
    if _file_sha256(RENDERER) != lock['renderer_sha256']:
        raise ValueError('The JATS-to-Markdown renderer differs from the locked renderer')

    source_by_id = {item['paper_id']: item['source'] for item in manifest['papers']}
    pdf_by_id = {item['paper_id']: item for item in format_summary.get('pairs', [])}
    output_hashes = {
        item['path']: item['sha256'] for item in lock.get('raw_outputs', [])
        if item.get('kind') == 'report_json'
    }
    cases = []
    for tracked in track['cases']:
        paper_id, old_finding_id = tracked['case_id'].split('/', 1)
        source = source_by_id[paper_id]
        source_path = source_dir / source['snapshot_name']
        source_bytes = source_path.read_bytes()
        source_hash = _sha256(source_bytes)
        if source_hash != source['sha256']:
            raise ValueError(f'{paper_id}: JATS source hash differs from the source manifest')

        rendered = render(source_bytes)
        rendered_hash = _sha256(rendered)
        report_path = f"validation/paper-audit-wave-2/results/{paper_id}/run-1/report.json"
        frozen_report_bytes = (ROOT / report_path).read_bytes()
        if _sha256(frozen_report_bytes) != output_hashes.get(report_path):
            raise ValueError(f'{paper_id}: frozen report does not match its output lock')
        frozen_report = json.loads(frozen_report_bytes)
        if frozen_report['source']['sha256'] != rendered_hash:
            raise ValueError(f'{paper_id}: current renderer does not reproduce the locked rendered input')
        candidate = next((item for item in frozen_report['candidate_anomalies']
                          if item.get('id') == old_finding_id), None)
        if candidate is None:
            raise ValueError(f'{paper_id}/{old_finding_id}: finding is absent from the locked report')

        run_metadata = json.loads((ROOT / f'validation/paper-audit-wave-2/results/{paper_id}/run-1/run_metadata.json')
                                  .read_text(encoding='utf-8'))
        if run_metadata['source']['staged_input_sha256'] != rendered_hash:
            raise ValueError(f'{paper_id}: locked run metadata has a different rendered-input hash')

        with tempfile.TemporaryDirectory(prefix='rw-historical-source-native-') as tmp:
            output_dir = Path(tmp) / 'report'
            run_paper_audit(
                source_path, output_dir, 'local:' + paper_id,
                source['source_version'][:100],
            )
            current = json.loads((output_dir / 'report.json').read_text(encoding='utf-8'))
        current_matches = [item for item in current['candidate_anomalies'] if _same_arithmetic(candidate, item)]

        pdf_pair = pdf_by_id.get(paper_id)
        if pdf_pair and pdf_pair.get('jats_source_sha256') != source_hash:
            raise ValueError(f'{paper_id}: PDF comparison references a different JATS source hash')
        recorded_outcome = tracked['outcome']
        internal_classification = (
            'KNOWN_CORRECTION' if recorded_outcome == 'KNOWN_CORRECTION'
            else 'SOURCE_REPRODUCED_INTERNAL_DISCREPANCY'
        )
        cases.append({
            'case_id': tracked['case_id'],
            'paper_id': paper_id,
            'internal_classification': internal_classification,
            'prior_adjudication_label': recorded_outcome,
            'source': {
                'format': 'JATS XML',
                'source_url': source['source_url'],
                'source_version': source['source_version'],
                'sha256': source_hash,
                'bytes': len(source_bytes),
                'renderer_version': lock['renderer_version'],
                'renderer_sha256': lock['renderer_sha256'],
                'rendered_markdown_sha256': rendered_hash,
                'frozen_report_path': report_path,
                'frozen_report_sha256': _sha256(frozen_report_bytes),
            },
            'candidate_arithmetic': _candidate_values(candidate),
            'jats_to_locked_representation': 'EXACT_RENDERED_INPUT_REPRODUCED',
            'current_source_native_exact_arithmetic_match': bool(current_matches),
            'current_source_native_matching_candidate_types': sorted({item['type'] for item in current_matches}),
            'publisher_pdf_comparison': ({
                'pair_record_available': True,
                'pdf_sha256': pdf_pair['pdf_source_sha256'],
                'source_record_and_identity_checks_passed': bool(
                    pdf_pair.get('same_pmc_record_endpoint') and pdf_pair.get('doi_in_pdf_front_matter')
                ),
                'jats_candidate_count': pdf_pair.get('jats_candidate_count'),
                'pdf_candidate_count': pdf_pair.get('pdf_candidate_count'),
                'matched_candidate_count': pdf_pair.get('matched_candidate_count'),
                'candidate_signature_sets_equal': pdf_pair.get('candidate_signature_sets_equal'),
                'finding_level_corroboration': 'NOT_ESTABLISHED_BY_AGGREGATE_SIGNATURE_COMPARISON',
            } if pdf_pair else {
                'pair_record_available': False,
                'status': 'NOT_ASSESSED_NO_HASHED_PUBLISHER_PDF_PAIR_RECORD',
            }),
            'correction_or_erratum': (
                'A correction is recorded in the adjudication notes; mapping it to this exact candidate remains unconfirmed.'
                if recorded_outcome == 'KNOWN_CORRECTION'
                else 'No correction target is recorded for this candidate in the wave-2 adjudication notes; no independent erratum search was made.'
            ),
            'supplement_resolution': 'NOT_ASSESSED',
            'later_version_resolution': 'NOT_ASSESSED',
            'scientific_consequence': 'NOT_ASSESSED',
            'external_validation_status': 'UNRESOLVED',
            'interpretation_limit': (
                'This packet reproduces an arithmetic candidate from a hash-locked JATS-derived rendering. '
                'It does not establish publisher-PDF agreement, a paper error, or scientific consequence.'
            ),
        })

    counts = Counter(item['internal_classification'] for item in cases)
    summary = {
        'record_version': '1',
        'evaluation_use': 'AGGREGATE_ONLY_DEVELOPMENT_VALIDATION',
        'artifact_scope': (
            'Aggregate counts only. Source identifiers, source hashes, candidate '
            'arithmetic, and individual case records are omitted.'
        ),
        'cases_total': len(cases),
        'classification_counts': dict(sorted(counts.items())),
        'external_validation_status_counts': dict(sorted(Counter(
            item['external_validation_status'] for item in cases
        ).items())),
        'confirmed_resolution_counts': {
            'KNOWN_CORRECTION_MAPPING': sum(
                item['prior_adjudication_label'] == 'KNOWN_CORRECTION'
                and item['external_validation_status'] != 'UNRESOLVED'
                for item in cases
            ),
            'RESOLVED_BY_SUPPLEMENT': sum(
                item['supplement_resolution'] == 'RESOLVED' for item in cases
            ),
            'FORMAT_ARTIFACT': sum(
                item['external_validation_status'] == 'FORMAT_ARTIFACT' for item in cases
            ),
            'BENIGN_PRESENTATION': sum(
                item['external_validation_status'] == 'BENIGN_PRESENTATION' for item in cases
            ),
            'UNRESOLVED': sum(
                item['external_validation_status'] == 'UNRESOLVED' for item in cases
            ),
        },
        'publisher_pdf_pair_records_available': sum(
            item['publisher_pdf_comparison']['pair_record_available'] for item in cases
        ),
        'publisher_pdf_pairs_with_candidate_signature_difference': sum(
            item['publisher_pdf_comparison'].get('candidate_signature_sets_equal') is False
            for item in cases
        ),
        'supplement_resolved_cases': sum(item['supplement_resolution'] == 'RESOLVED' for item in cases),
        'later_version_resolved_cases': sum(item['later_version_resolution'] == 'RESOLVED' for item in cases),
        'scientific_consequence_assessed_cases': sum(item['scientific_consequence'] != 'NOT_ASSESSED' for item in cases),
        'limitations': [
            'The 14 source-reproduced labels mean the archived arithmetic candidate and JATS-derived rendered input reproduce under their recorded hashes; they are not scientific discoveries.',
            'Publisher PDF comparisons are available for only a subset, and aggregate candidate-signature differences do not identify whether a particular finding was independently confirmed.',
            'No supplements, corrigenda beyond the recorded correction pointer, later versions, or scientific consequences were independently reviewed.',
            'This public summary does not include source-specific allegations or individual findings.',
            'No author was contacted and no public accusation is made.',
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wave2-source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.wave2_source_dir, args.output)
    print(json.dumps({
        'cases_total': result['cases_total'],
        'classification_counts': result['classification_counts'],
        'external_validation_status_counts': result['external_validation_status_counts'],
        'publisher_pdf_pair_records_available': result['publisher_pdf_pair_records_available'],
        'publisher_pdf_pairs_with_candidate_signature_difference': result['publisher_pdf_pairs_with_candidate_signature_difference'],
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
