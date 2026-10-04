"""Malformed-input, differential and trust-boundary tests for the v1 contract."""
from datetime import date
from fractions import Fraction as F
from itertools import product
import json
import random

import pytest

from researchwitness import evaluate, Invalid
from researchwitness.checkers import check, uc_table
from researchwitness.capsule import subject_digest
from researchwitness.strict import byte_hash, digest, relative_path

TODAY = date(2026, 10, 4)

STRING_PATHS = [
    ('schema_version',), ('case_id',), ('disclosure',), ('witness_artifact',),
    ('source', 'artifact'), ('source', 'text_artifact'), ('source', 'identifier'),
    ('source', 'version'), ('source', 'capture_status'),
    ('source', 'correction_check', 'checked_on'), ('source', 'correction_check', 'status'),
    ('source', 'correction_check', 'evidence_artifact'),
    ('claim', 'id'), ('claim', 'statement'), ('claim', 'scope'),
    ('claim', 'anchor', 'quote'), ('claim', 'formalization', 'kind'),
]


def _set_path(obj, path, value):
    for part in path[:-1]:
        obj = obj[part]
    obj[path[-1]] = value


@pytest.mark.parametrize('path', STRING_PATHS, ids=lambda p: '.'.join(map(str, p)))
@pytest.mark.parametrize('value', [None, [], {}, True, 1])
def test_wrong_types_reject_cleanly(bundle, path, value):
    root, case, data = bundle
    _set_path(case, path, value)
    (root / 'case.json').write_text(json.dumps(case))
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


def test_no_review_objects_are_needed(bundle):
    root, case, data = bundle
    assert 'reviews' not in case and 'origin' not in case
    report = evaluate(root, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'


def test_captured_metadata_is_not_authentication(bundle):
    root, case, data = bundle
    case['source']['capture_status'] = 'captured'
    (root / 'case.json').write_text(json.dumps(case))
    report = evaluate(root, TODAY)
    assert report['paper_error_established'] is False
    assert any('not machine-proved' in warning for warning in report['warnings'])


def test_external_digest_detects_consistent_rewrite(bundle):
    root, case, data = bundle
    old = evaluate(root, TODAY)['bundle_sha256']
    case['claim']['formalization']['upper_bound'] = '1/3'
    (root / 'case.json').write_text(json.dumps(case))
    with pytest.raises(Invalid, match='External bundle digest mismatch'):
        evaluate(root, TODAY, expected_bundle_sha256=old)


def test_matching_external_pin(bundle):
    root, case, data = bundle
    pin = evaluate(root, TODAY)['bundle_sha256']
    report = evaluate(root, TODAY, pin)
    assert report['externally_pinned']
    assert 'BUNDLE_NOT_EXTERNALLY_PINNED' not in {f['code'] for f in report['context_flags']}


@pytest.mark.parametrize('name', ['CASE.JSON', 'Report.json', 'checksums.sha256'])
def test_reserved_export_filename_cannot_shadow(bundle, name):
    root, case, data = bundle
    case['artifacts'][name] = '0' * 64
    (root / 'case.json').write_text(json.dumps(case))
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


@pytest.mark.parametrize('name', ['CON', 'a/NUL.txt', 'LPT1', 'file.', 'a /b'])
def test_windows_special_paths_rejected(name):
    with pytest.raises(Invalid):
        relative_path(name)


def test_casefold_collision_rejected(bundle):
    root, case, data = bundle
    case['artifacts']['SOURCE.TXT'] = case['artifacts']['source.txt']
    (root / 'case.json').write_text(json.dumps(case))
    with pytest.raises(Invalid, match='Case-insensitive path collision'):
        evaluate(root, TODAY)


def test_prefix_collision_rejected(bundle):
    root, case, data = bundle
    case['artifacts']['source.txt/child'] = '0' * 64
    (root / 'case.json').write_text(json.dumps(case))
    with pytest.raises(Invalid, match='prefix collision'):
        evaluate(root, TODAY)


def test_arithmetic_resource_limit():
    from researchwitness.arithmetic import Interval
    with pytest.raises(Invalid):
        Interval(F(1, 2**9000), F(1))


def test_subject_and_bundle_have_distinct_semantics(bundle):
    root, case, data = bundle
    subject = subject_digest(case)
    bundle_hash = digest(case)
    case['artifacts']['supplement.txt'] = byte_hash(b'supplement')
    assert subject_digest(case) == subject
    assert digest(case) != bundle_hash


def test_uc_crosscheck_cellwise_against_correlator_form():
    rng = random.Random(448912)
    for _ in range(300):
        weights = [[rng.randrange(1, 30) for _ in range(4)] for _ in range(2)]
        witness = {
            'kind': 'uc_binary_upper_bound',
            'gamma': [str(F(x, sum(weights[0]))) for x in weights[0]],
            'alpha': [str(F(x, sum(weights[1]))) for x in weights[1]],
            'b0': [[str(F(rng.randrange(21), 20)) for _ in range(4)] for _ in range(4)],
        }
        probabilities = uc_table(witness)

        def corr(b, ap, cp):
            return sum((-1) ** (a * ap + c * cp) * probabilities[a, b, c]
                       for a, c in product(range(2), repeat=2))

        q = F(1, 4)
        penalty = (
            18 * abs(sum(probabilities[a, 0, c] for a, c in product(range(2), repeat=2)) - q)
            + 18 * abs(probabilities[0, 1, 1] + probabilities[1, 1, 0] - q)
            + 4 * abs(probabilities[0, 1, 0] - q)
            + 4 * abs(probabilities[1, 1, 1] - q)
            + 4 * abs(corr(1, 1, 1) - q)
            + abs(corr(1, 1, 0) + corr(1, 0, 1))
            + abs(corr(0, 1, 0))
            + abs(corr(0, 0, 1))
        )
        spec = {
            'kind': 'uc_binary_upper_bound',
            'functional': 'uc_sqrt_penalty_v1',
            'upper_bound': {'constant': '3', 'terms': []},
        }
        result = check(spec, witness)
        assert F(result['detail']['penalty_exact']) == penalty
        assert sum(F(x) for x in result['detail']['probabilities'].values()) == 1


def test_polynomial_random_differential():
    rng = random.Random(920011)
    for _ in range(500):
        x = F(rng.randrange(-10, 11), rng.randrange(1, 11))
        y = F(rng.randrange(-10, 11), rng.randrange(1, 11))
        a = F(rng.randrange(-8, 9), rng.randrange(1, 9))
        b = F(rng.randrange(-8, 9), rng.randrange(1, 9))
        c = F(rng.randrange(-8, 9), rng.randrange(1, 9))
        expected = a * x * x + b * x * y + c
        spec = {
            'kind': 'polynomial_upper_bound',
            'domain': {
                'x': {'lower': '-10', 'upper': '10', 'lower_closed': True, 'upper_closed': True},
                'y': {'lower': '-10', 'upper': '10', 'lower_closed': True, 'upper_closed': True},
            },
            'terms': [
                {'coefficient': str(a), 'powers': {'x': 2}},
                {'coefficient': str(b), 'powers': {'x': 1, 'y': 1}},
                {'coefficient': str(c), 'powers': {}},
            ],
            'upper_bound': str(expected - F(1, 100)),
        }
        witness = {'kind': 'polynomial_upper_bound', 'point': {'x': str(x), 'y': str(y)}}
        result = check(spec, witness)
        assert F(result['detail']['value_exact']) == expected
        assert result['status'] == 'REFUTED_FOR_FORMALIZATION'


def test_unrecognized_legacy_schema_rejected(bundle):
    root, case, data = bundle
    case['schema_version'] = '0.1'
    (root / 'case.json').write_text(json.dumps(case))
    with pytest.raises(Invalid, match='Unsupported schema version'):
        evaluate(root, TODAY)
