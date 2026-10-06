"""Guard public validation packets against case-level source disclosure."""
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'validation/paper-audit-capability-wave-2'
PUBLIC_JSON = (
    PACKET / 'DETECTOR_REGRESSION_EVIDENCE.json',
    PACKET / 'DEVELOPMENT_ELIGIBILITY_AGGREGATE.json',
    PACKET / 'DEVELOPMENT_REPLAY_SUMMARY.json',
    PACKET / 'HISTORICAL_DISCREPANCY_VALIDATION.json',
    ROOT / 'validation/paper-audit-real-evidence-wave/SOURCE_ADJUDICATION_AGGREGATE.json',
)
CASE_LEVEL_KEYS = {
    'bindings', 'cases', 'candidate_arithmetic', 'case_id', 'paper_id',
    'papers', 'source_bindings', 'source_sha256', 'report_sha256',
}


def _keys(value):
    if isinstance(value, dict):
        yield from value.keys()
        for child in value.values():
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def test_public_validation_artifacts_contain_aggregate_data_only():
    for path in PUBLIC_JSON:
        raw = path.read_text(encoding='utf-8')
        parsed = json.loads(raw)

        assert not (CASE_LEVEL_KEYS & set(_keys(parsed))), path.name
        assert not re.search(r'(?i)paper[-_ ]?\d+', raw), path.name
        assert not re.search(r'(?i)PMC\d+', raw), path.name
        assert not re.search(r'(?i)10\.\d{4,9}/', raw), path.name
        assert not re.search(r'\b[0-9a-f]{64}\b', raw), path.name


def test_package_checksum_manifest_omits_case_level_source_corpora():
    raw = (ROOT / 'CHECKSUMS.sha256').read_text(encoding='utf-8')

    assert 'validation/paper-audit-wave-1/' not in raw
    assert 'validation/paper-audit-wave-2/' not in raw
    assert 'validation/paper-audit-capability-wave/' not in raw
    assert 'validation/paper-audit-real-evidence-wave/SOURCE_ADJUDICATION_AGGREGATE.json' in raw
    assert not re.search(r'validation/[^\n]*/paper-\d+/', raw)
