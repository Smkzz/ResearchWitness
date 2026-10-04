from datetime import date
from fractions import Fraction as F
import json
import os
import random
import subprocess
import sys
import zipfile

import pytest

from researchwitness import evaluate, Invalid
from researchwitness.capsule import subject_digest
from researchwitness.arithmetic import rational, sqrt_interval, radical_sum
from researchwitness.checkers import check, uc_table
from researchwitness.strict import loads, relative_path, Bundle, MAX_JSON_BYTES, byte_hash
from make_examples import write_case, base_case

TODAY = date(2026, 10, 4)


def save(root, case):
    (root / 'case.json').write_text(json.dumps(case), encoding='utf-8')


def flags(report):
    return {x['code'] for x in report['context_flags']}


def test_counterexample_is_machine_scoped(bundle):
    root, case, data = bundle
    report = evaluate(root, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['formalization_result']['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert report['evidence_complete_for_formalization'] is True
    assert report['paper_error_established'] is False
    assert report['external_actions'] == 'OUT_OF_SCOPE'
    assert 'eligible_for_human_review' not in report
    assert 'contact_authorized' not in report
    assert 'publication_authorized' not in report


def test_no_refutation_is_not_global_validity(bundle):
    root, case, data = bundle
    case['claim']['formalization']['upper_bound'] = '1'
    save(root, case)
    report = evaluate(root, TODAY)
    assert report['decision'] == 'NO_REFUTATION_AT_WITNESS'
    assert report['evidence_complete_for_formalization'] is False
    assert report['paper_error_established'] is False


def test_open_objection_is_preserved_without_rewriting_math(bundle):
    root, case, data = bundle
    objection = 'An omitted restriction may invalidate the source-to-formalization mapping.'
    case['unresolved_objections'] = [objection]
    save(root, case)
    report = evaluate(root, TODAY)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert {'OPEN_OBJECTION'} <= flags(report)
    assert report['open_objections'] == [objection]
    assert report['paper_error_established'] is False


@pytest.mark.parametrize('value,code', [
    ('unverified', 'SOURCE_CAPTURE_UNVERIFIED'),
    ('synthetic', 'SYNTHETIC_SOURCE'),
])
def test_capture_status_is_context_not_fake_authentication(bundle, value, code):
    root, case, data = bundle
    case['source']['capture_status'] = value
    save(root, case)
    report = evaluate(root, TODAY)
    assert code in flags(report)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['paper_error_established'] is False


def test_captured_source_still_does_not_establish_paper_error(bundle):
    root, case, data = bundle
    case['source']['capture_status'] = 'captured'
    save(root, case)
    report = evaluate(root, TODAY)
    assert 'SOURCE_CAPTURE_UNVERIFIED' not in flags(report)
    assert report['source_anchor_verified'] is True
    assert report['paper_error_established'] is False


@pytest.mark.parametrize('value,code', [
    ('unchecked', 'CORRECTION_STATUS_UNCHECKED'),
    ('present', 'CORRECTION_PRESENT'),
])
def test_correction_check_is_context(bundle, value, code):
    root, case, data = bundle
    case['source']['correction_check']['status'] = value
    save(root, case)
    report = evaluate(root, TODAY)
    assert code in flags(report)
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'


@pytest.mark.parametrize('value,code', [
    ('2026-01-01', 'STALE_CORRECTION_CHECK'),
    ('2026-10-05', 'FUTURE_CORRECTION_CHECK'),
])
def test_correction_check_dates_are_reported(bundle, value, code):
    root, case, data = bundle
    case['source']['correction_check']['checked_on'] = value
    save(root, case)
    assert code in flags(evaluate(root, TODAY))


def test_empty_correction_evidence_is_visible(bundle):
    root, case, data = bundle
    name = case['source']['correction_check']['evidence_artifact']
    (root / name).write_bytes(b'')
    case['artifacts'][name] = byte_hash(b'')
    save(root, case)
    assert 'EMPTY_CORRECTION_EVIDENCE' in flags(evaluate(root, TODAY))


@pytest.mark.parametrize('mutation', ['quote', 'offset', 'hash', 'witness-hash'])
def test_source_or_bytes_corruption(bundle, mutation):
    root, case, data = bundle
    if mutation == 'quote':
        case['claim']['anchor']['quote'] = 'A sentence never in the captured source'
    elif mutation == 'offset':
        case['claim']['anchor']['offset'] = 1
    elif mutation == 'hash':
        (root / 'source.txt').write_text('tampered')
    else:
        (root / 'witness.json').write_text('{}')
    save(root, case)
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


@pytest.mark.parametrize('field', ['statement', 'scope', 'assumptions', 'excluded_claims', 'formalization'])
def test_claim_mutation_changes_subject_digest(bundle, field):
    root, case, data = bundle
    before = subject_digest(case)
    if field in ('assumptions', 'excluded_claims'):
        case['claim'][field].append('Additional scope fact.')
    elif field == 'formalization':
        case['claim'][field]['upper_bound'] = '1/3'
    else:
        case['claim'][field] += ' Changed.'
    assert subject_digest(case) != before


def test_witness_content_change_changes_subject_when_rehashed(bundle):
    root, case, data = bundle
    before = subject_digest(case)
    replacement = b'{"kind":"polynomial_upper_bound","point":{"x":"1/2"}}'
    case['artifacts']['witness.json'] = byte_hash(replacement)
    assert subject_digest(case) != before


def test_supplemental_artifact_does_not_change_subject_but_changes_bundle(bundle):
    root, case, data = bundle
    from researchwitness.strict import digest
    before_subject = subject_digest(case)
    before_bundle = digest(case)
    case['artifacts']['notes.md'] = byte_hash(b'note')
    assert subject_digest(case) == before_subject
    assert digest(case) != before_bundle


def test_target_cannot_be_supplied_in_witness(bundle):
    root, case, data = bundle
    data['witness.json'] = b'{"kind":"polynomial_upper_bound","point":{"x":"1"},"upper_bound":"0"}'
    write_case(root, case, data)
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


@pytest.mark.parametrize('field', ['reviews', 'origin', 'contact_authorized', 'publication_authorized', 'force', 'trusted', 'confidence'])
def test_old_or_approval_fields_are_rejected(bundle, field):
    root, case, data = bundle
    case[field] = [] if field in ('reviews',) else True
    save(root, case)
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


@pytest.mark.parametrize('payload', [
    b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1.25}',
    b'{"a":12345678901234}', b'\xff', b'{', b'{"x":"\\ud800"}',
])
def test_strict_json(payload):
    with pytest.raises(Invalid):
        loads(payload)


def test_large_json():
    with pytest.raises(Invalid):
        loads(b' ' * (MAX_JSON_BYTES + 1))


def test_deep_json():
    with pytest.raises(Invalid):
        loads(b'[' * 50 + b'0' + b']' * 50)


@pytest.mark.parametrize('name', ['../x', '/tmp/x', 'a/../../x', 'C:/x', 'a\\b', 'a//b', './x', 'a/./b', 'a\x00b', 'a/'])
def test_unsafe_paths(name):
    with pytest.raises(Invalid):
        relative_path(name)


def test_symlink_rejected(bundle):
    root, case, data = bundle
    target = root / 'source.txt'
    target.unlink()
    target.symlink_to(root / 'correction-check.txt')
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


def test_root_symlink_rejected(bundle):
    root, case, data = bundle
    alias = root / 'alias'
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(Invalid):
        Bundle(alias)


def test_hardlink_rejected(bundle):
    root, case, data = bundle
    os.link(root / 'source.txt', root / 'alias.txt')
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='POSIX-only FIFO attack test')
def test_fifo_is_not_read(bundle):
    root, case, data = bundle
    (root / 'source.txt').unlink()
    os.mkfifo(root / 'source.txt')
    with pytest.raises(Invalid):
        evaluate(root, TODAY)


@pytest.mark.parametrize('value', [
    '1.0', '1e9', 'nan', 'inf', '1/0', '01', '+1', ' 1', '1 ', None, 1, True, {},
    '__import__("os")', '1' * 140,
])
def test_bad_rationals(value):
    with pytest.raises(Invalid):
        rational(value)


def test_square_root_property_sweep():
    rng = random.Random(20261004)
    for _ in range(1000):
        x = F(rng.randrange(10**18), rng.randrange(1, 10**12))
        interval = sqrt_interval(x)
        assert 0 <= interval.lo <= interval.hi
        assert interval.lo * interval.lo <= x <= interval.hi * interval.hi
        assert interval.hi - interval.lo <= F(1, 10**40)


@pytest.mark.parametrize('x', ['0', '1', '4', '9/16', '100/49'])
def test_exact_square(x):
    interval = sqrt_interval(F(x))
    assert interval.lo * interval.lo <= F(x) <= interval.hi * interval.hi


def test_negative_radical_coefficient():
    interval = radical_sum({'constant': '1', 'terms': [{'coefficient': '-2', 'radicand': '2'}]})
    assert interval.lo < F('-1828/1000') < interval.hi + F('1/1000')
    assert interval.lo <= interval.hi


def test_negative_sqrt():
    with pytest.raises(Invalid):
        sqrt_interval(F(-1))


def test_uncertain_interval_abstains():
    spec = {
        'kind': 'scalar_radical_comparison',
        'left': {'constant': '0', 'terms': [{'coefficient': '1', 'radicand': '2'}]},
        'upper_bound': {'constant': '0', 'terms': [{'coefficient': '1', 'radicand': '2'}]},
    }
    assert check(spec, {'kind': 'scalar_radical_comparison'})['status'] == 'INCONCLUSIVE_INTERVAL'


@pytest.mark.parametrize('x', ['-1', '2'])
def test_infeasible_point_rejected(x):
    case, data = base_case()
    with pytest.raises(Invalid):
        check(case['claim']['formalization'], {'kind': 'polynomial_upper_bound', 'point': {'x': x}})


def test_open_endpoint_rejected():
    case, data = base_case()
    case['claim']['formalization']['domain']['x']['upper_closed'] = False
    with pytest.raises(Invalid):
        check(case['claim']['formalization'], {'kind': 'polynomial_upper_bound', 'point': {'x': '1'}})


def test_wrong_proof_kind_rejected():
    with pytest.raises(Invalid):
        check({'kind': 'global_optimizer'}, {})


def test_uc_deterministic_normalization():
    witness = {
        'kind': 'uc_binary_upper_bound',
        'gamma': ['1', '0', '0', '0'],
        'alpha': ['1', '0', '0', '0'],
        'b0': [['0'] * 4 for _ in range(4)],
    }
    table = uc_table(witness)
    assert table[0, 1, 0] == 1 and sum(table.values()) == 1


@pytest.mark.parametrize('mutation', ['negative-source', 'source-sum', 'bad-kernel', 'missing-cell'])
def test_uc_invalid_strategy(mutation):
    witness = {
        'kind': 'uc_binary_upper_bound',
        'gamma': ['1', '0', '0', '0'],
        'alpha': ['1', '0', '0', '0'],
        'b0': [['0'] * 4 for _ in range(4)],
    }
    if mutation == 'negative-source':
        witness['gamma'] = ['2', '-1', '0', '0']
    elif mutation == 'source-sum':
        witness['alpha'] = ['1', '1', '0', '0']
    elif mutation == 'bad-kernel':
        witness['b0'][0][0] = '2'
    else:
        witness['b0'][0].pop()
    with pytest.raises(Invalid):
        uc_table(witness)


def test_cli_optimized_python_still_rejects_invalid_input(bundle):
    root, case, data = bundle
    case['claim']['anchor']['quote'] = 'invented'
    save(root, case)
    out = subprocess.run(
        [sys.executable, '-O', '-m', 'researchwitness', 'verify', str(root), '--as-of', '2026-10-04'],
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 2
    assert json.loads(out.stderr)['decision'] == 'INVALID'


def test_verify_exit_zero_means_evaluated_not_refuted(bundle):
    root, case, data = bundle
    case['claim']['formalization']['upper_bound'] = '1'
    save(root, case)
    out = subprocess.run(
        [sys.executable, '-m', 'researchwitness', 'verify', str(root), '--as-of', '2026-10-04'],
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 0
    assert json.loads(out.stdout)['decision'] == 'NO_REFUTATION_AT_WITNESS'


def test_export_is_deterministic_allowlisted_and_stored(bundle):
    root, case, data = bundle
    (root / 'unrelated-secret.txt').write_text('DO NOT EXPORT')
    for name in ('one.zip', 'two.zip'):
        out = subprocess.run(
            [sys.executable, '-m', 'researchwitness', 'pack', str(root), '--as-of', '2026-10-04',
             '--output', str(root / name)],
            capture_output=True, text=True, timeout=10,
        )
        assert out.returncode == 0, out.stderr
    assert (root / 'one.zip').read_bytes() == (root / 'two.zip').read_bytes()
    with zipfile.ZipFile(root / 'one.zip') as archive:
        assert 'unrelated-secret.txt' not in archive.namelist()
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        report = json.loads(archive.read('report.json'))
        assert report['external_actions'] == 'OUT_OF_SCOPE'
        assert report['paper_error_established'] is False


def test_export_refuses_overwrite(bundle):
    root, case, data = bundle
    outpath = root / 'existing.zip'
    outpath.write_bytes(b'preserve')
    out = subprocess.run(
        [sys.executable, '-m', 'researchwitness', 'pack', str(root), '--as-of', '2026-10-04', '--output', str(outpath)],
        capture_output=True, text=True, timeout=10,
    )
    assert out.returncode == 2 and outpath.read_bytes() == b'preserve'


def test_version_command():
    out = subprocess.run([sys.executable, '-m', 'researchwitness', '--version'], capture_output=True, text=True)
    assert out.returncode == 0
    assert out.stdout.strip() == 'researchwitness 0.2.0'


def test_invalid_calendar_date_rejected(bundle):
    root, case, data = bundle
    case['source']['correction_check']['checked_on'] = '2026-02-30'
    save(root, case)
    with pytest.raises(Invalid, match='Invalid date'):
        evaluate(root, TODAY)


def test_missing_manifested_file_rejected(bundle):
    root, case, data = bundle
    (root / 'witness.json').unlink()
    with pytest.raises(Invalid, match='Cannot read artifact'):
        evaluate(root, TODAY)


def elliptic_residue_spec(allowed):
    return {
        'kind': 'finite_field_polynomial_residue',
        'prime': 29,
        'variables': ['x', 'y'],
        'parameters': ['c'],
        'terms': [
            {'coefficient': 1, 'powers': {'y': 2}},
            {'coefficient': -1, 'powers': {'x': 3}},
            {'coefficient': -1, 'powers': {'c': 1, 'x': 1}},
        ],
        'point_count_adjustment': 1,
        'modulus': 8,
        'allowed_residues': allowed,
    }


def test_finite_field_elliptic_c4_historical_counterexample():
    result = check(elliptic_residue_spec([4]), {
        'kind': 'finite_field_polynomial_residue', 'parameters': {'c': 4},
    })
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['total_solution_count'] == 40
    assert result['detail']['observed_residue'] == 0


def test_finite_field_elliptic_c7_historical_counterexample():
    result = check(elliptic_residue_spec([0]), {
        'kind': 'finite_field_polynomial_residue', 'parameters': {'c': 7},
    })
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['total_solution_count'] == 20
    assert result['detail']['observed_residue'] == 4


def test_finite_field_negative_control_accepts_observed_residue():
    result = check(elliptic_residue_spec([0]), {
        'kind': 'finite_field_polynomial_residue', 'parameters': {'c': 4},
    })
    assert result['status'] == 'NO_REFUTATION_AT_WITNESS'


def test_finite_field_composite_modulus_rejected():
    spec = elliptic_residue_spec([0])
    spec['prime'] = 21
    with pytest.raises(Invalid, match='prime'):
        check(spec, {'kind': 'finite_field_polynomial_residue', 'parameters': {'c': 4}})


def test_finite_field_work_budget_rejected():
    spec = {
        'kind': 'finite_field_polynomial_residue', 'prime': 251,
        'variables': ['x', 'y', 'z'], 'parameters': [],
        'terms': [{'coefficient': 1, 'powers': {'x': 1}}],
        'point_count_adjustment': 0, 'modulus': 2, 'allowed_residues': [0],
    }
    with pytest.raises(Invalid, match='budget'):
        check(spec, {'kind': 'finite_field_polynomial_residue', 'parameters': {}})


def test_finite_map_swap_refutes_fixed_point_conclusion():
    spec = {'kind': 'finite_map_fixed_point', 'universe': ['0', '1'], 'conclusion': 'has_fixed_point'}
    result = check(spec, {'kind': 'finite_map_fixed_point', 'mapping': {'0': '1', '1': '0'}})
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['fixed_points'] == []
    assert result['detail']['theorem_premises'] == 'NOT_ESTABLISHED_BY_THIS_CHECKER'


def test_finite_map_identity_is_not_refuting():
    spec = {'kind': 'finite_map_fixed_point', 'universe': ['0', '1'], 'conclusion': 'has_fixed_point'}
    result = check(spec, {'kind': 'finite_map_fixed_point', 'mapping': {'0': '0', '1': '1'}})
    assert result['status'] == 'NO_REFUTATION_AT_WITNESS'
    assert result['detail']['fixed_points'] == ['0', '1']


def test_finite_map_must_be_self_map():
    spec = {'kind': 'finite_map_fixed_point', 'universe': ['0', '1'], 'conclusion': 'has_fixed_point'}
    with pytest.raises(Invalid):
        check(spec, {'kind': 'finite_map_fixed_point', 'mapping': {'0': '1', '1': '2'}})


def elliptic_power_rule_spec():
    return {
        'kind': 'finite_field_quadratic_quartic_residue_rule',
        'prime': 29,
        'variables': ['x', 'y'],
        'parameters': ['c'],
        'terms': [
            {'coefficient': 1, 'powers': {'y': 2}},
            {'coefficient': -1, 'powers': {'x': 3}},
            {'coefficient': -1, 'powers': {'c': 1, 'x': 1}},
        ],
        'point_count_adjustment': 1,
        'modulus': 8,
        'classification_parameter': 'c',
        'expected_residues': {
            'quartic_residue': [0],
            'quadratic_nonquartic': [4],
            'quadratic_nonresidue': [2],
        },
    }


def test_elliptic_power_rule_c4_verifies_class_and_counterexample():
    result = check(elliptic_power_rule_spec(), {
        'kind': 'finite_field_quadratic_quartic_residue_rule', 'parameters': {'c': 4},
    })
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['power_class'] == 'quadratic_nonquartic'
    assert result['detail']['total_solution_count'] == 40
    assert result['detail']['observed_residue'] == 0
    assert result['detail']['expected_residues_for_class'] == [4]


def test_elliptic_power_rule_c7_verifies_class_and_counterexample():
    result = check(elliptic_power_rule_spec(), {
        'kind': 'finite_field_quadratic_quartic_residue_rule', 'parameters': {'c': 7},
    })
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['power_class'] == 'quartic_residue'
    assert result['detail']['total_solution_count'] == 20
    assert result['detail']['observed_residue'] == 4
    assert result['detail']['expected_residues_for_class'] == [0]
