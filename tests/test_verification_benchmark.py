"""Synthetic-only development-ledger invariants; never a scientific benchmark."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples' / 'verification-benchmark'


def load_fixture():
    documents = [vb.parse_document((FIXTURE / f'{name}.json').read_bytes())
                 for name in ('registry', 'protocol', 'run')]
    pins = json.loads((FIXTURE / 'pins.json').read_text())
    return (*documents, pins)


def evaluate(registry=None, protocol=None, run=None, pins=None):
    original = load_fixture()
    supplied = (registry, protocol, run, pins)
    registry, protocol, run, pins = [old if new is None else new for old, new in zip(original, supplied)]
    return vb.score(registry, protocol, run, **pins)


def repin(registry, protocol, run):
    """Synthetic test construction only; never repair a real frozen protocol."""
    rh = vb.commitment(registry)
    protocol['registry_sha256'] = rh
    ph = vb.commitment(protocol)
    run['registry_sha256'], run['protocol_sha256'] = rh, ph
    return {'expected_registry_sha256': rh, 'expected_protocol_sha256': ph}


def test_reference_fixture_retains_missing_denominators_and_false_alarms():
    report = evaluate()
    assert report['status'] == 'incomplete'
    assert report['work_counts']['registered'] == 7
    assert report['work_counts']['missing'] == 2
    assert report['family_counts'] == {
        'registered': 6, 'eligible': 5, 'positive': 2, 'negative': 2,
        'unresolved': 1, 'ineligible': 1, 'negative_incomplete_without_alarm': 1,
    }
    assert report['rates']['recorded_detection'] == {'numerator': 1, 'denominator': 2}
    assert report['rates']['observed_false_alarm'] == {'numerator': 1, 'denominator': 2}
    assert report['rates']['false_alarm_completion_upper_bound'] == {'numerator': 2, 'denominator': 2}
    assert not report['scientific_performance_established']
    assert not report['protected_evaluation_performed']
    assert report['source_and_certificate_validation'] == 'SUPPLIED_DECLARATIONS_NOT_REPLAYED'


def test_all_missing_results_do_not_become_perfect_specificity():
    _, _, run, _ = load_fixture()
    run['results'] = []
    report = evaluate(run=run)
    assert report['work_counts']['missing'] == 7
    assert report['rates']['observed_false_alarm'] == {'numerator': 0, 'denominator': 2}
    assert report['rates']['false_alarm_completion_upper_bound'] == {'numerator': 2, 'denominator': 2}
    assert report['status'] == 'incomplete' and not report['coverage_complete']


@pytest.mark.parametrize('status', ['rejected', 'not_checked'])
def test_certificate_not_accepted_does_not_earn_detection(status):
    _, _, run, _ = load_fixture()
    run['results'][0]['certificate_status'] = status
    if status == 'not_checked':
        run['results'][0]['certificate_sha256'] = None
    assert evaluate(run=run)['rates']['recorded_detection']['numerator'] == 0


@pytest.mark.parametrize('correspondence', ['contradicted', 'unresolved'])
def test_valid_certificate_with_wrong_source_has_no_detection(correspondence):
    _, _, run, _ = load_fixture()
    run['results'][0]['source_correspondence'] = correspondence
    assert evaluate(run=run)['rates']['recorded_detection']['numerator'] == 0


def test_wrong_positive_target_has_no_detection():
    _, _, run, _ = load_fixture()
    run['results'][0]['target_id'] = 'wrong-target'
    assert evaluate(run=run)['rates']['recorded_detection']['numerator'] == 0


@pytest.mark.parametrize('field', ['source_sha256', 'interpretation_sha256'])
def test_mismatched_source_commitments_rejected(field):
    _, _, run, _ = load_fixture()
    run['results'][0][field] = '0' * 64
    with pytest.raises(vb.BenchmarkError, match='SOURCE_BINDING'):
        evaluate(run=run)


def test_external_pin_prevents_relabeling_and_rehashing_all_inputs():
    registry, protocol, run, pins = load_fixture()
    registry['works'][2]['label'] = 'unresolved'
    registry['works'][2]['target_id'] = None
    repin(registry, protocol, run)
    with pytest.raises(vb.BenchmarkError, match='REGISTRY_PIN_MISMATCH'):
        evaluate(registry, protocol, run, pins)


def test_schedule_cannot_omit_failed_cases():
    registry, protocol, run, _ = load_fixture()
    protocol['schedule'].remove('p2')
    pins = repin(registry, protocol, run)
    with pytest.raises(vb.BenchmarkError, match='SCHEDULE_COVERAGE'):
        evaluate(registry, protocol, run, pins)


@pytest.mark.parametrize('field', ['registry_sha256', 'protocol_sha256', 'implementation_sha256'])
def test_run_binding_mismatches(field):
    _, _, run, _ = load_fixture()
    run[field] = '0' * 64
    with pytest.raises(vb.BenchmarkError, match='BINDING'):
        evaluate(run=run)


@pytest.mark.parametrize('change', ['duplicate_result', 'new_result', 'duplicate_work', 'mixed_family', 'same_source_other_family'])
def test_no_family_or_result_inflation(change):
    registry, protocol, run, _ = load_fixture()
    if change == 'duplicate_result':
        run['results'].append(deepcopy(run['results'][0]))
    elif change == 'new_result':
        run['results'][0]['work_id'] = 'unregistered'
    elif change == 'duplicate_work':
        registry['works'].append(deepcopy(registry['works'][0]))
    elif change == 'mixed_family':
        registry['works'][3]['family_id'] = registry['works'][0]['family_id']
    else:
        registry['works'][2]['source_sha256'] = registry['works'][0]['source_sha256']
    pins = repin(registry, protocol, run)
    with pytest.raises(vb.BenchmarkError):
        evaluate(registry, protocol, run, pins)


@pytest.mark.parametrize('value', [True, -1, 1.5, float('nan'), float('inf'), vb.MAX_INTEGER + 1, '1'])
def test_bad_counters_fail_closed(value):
    _, _, run, _ = load_fixture()
    run['results'][0]['calls'] = value
    with pytest.raises(vb.BenchmarkError):
        evaluate(run=run)


def test_budget_overrun_cannot_remain_a_completed_detection():
    _, _, run, _ = load_fixture()
    run['results'][0]['elapsed_ms'] = 1001
    with pytest.raises(vb.BenchmarkError, match='BUDGET_STATE_MISMATCH'):
        evaluate(run=run)
    run['results'][0]['status'] = 'budget_exceeded'
    assert evaluate(run=run)['rates']['recorded_detection']['numerator'] == 0


def test_total_overflow_is_rejected():
    registry, protocol, run, _ = load_fixture()
    protocol['max_elapsed_ms'] = vb.MAX_INTEGER
    run['results'][0]['elapsed_ms'] = vb.MAX_INTEGER
    pins = repin(registry, protocol, run)
    with pytest.raises(vb.BenchmarkError, match='TOTAL_OUT_OF_BOUNDS'):
        evaluate(registry, protocol, run, pins)


@pytest.mark.parametrize('field', ['extra_field', 'attempts', 'reviewer_votes'])
def test_unsupported_or_hidden_retry_fields_rejected(field):
    _, _, run, _ = load_fixture()
    run[field] = []
    with pytest.raises(vb.BenchmarkError, match='OBJECT_FIELDS'):
        evaluate(run=run)


def test_sealed_and_paid_modes_are_not_silently_enabled():
    registry, protocol, run, _ = load_fixture()
    registry['exposure'] = 'sealed'
    pins = repin(registry, protocol, run)
    with pytest.raises(vb.BenchmarkError, match='ENUM_VALUE'):
        evaluate(registry, protocol, run, pins)
    registry['exposure'] = 'synthetic'
    protocol['max_cost_micro_eur'] = 1
    pins = repin(registry, protocol, run)
    with pytest.raises(vb.BenchmarkError, match='PAID_RUN_NOT_SUPPORTED'):
        evaluate(registry, protocol, run, pins)


def test_no_alarm_cannot_hide_an_accepted_candidate():
    _, _, run, _ = load_fixture()
    run['results'][0]['alarm_emitted'] = False
    with pytest.raises(vb.BenchmarkError, match='NO_ALARM_EVIDENCE'):
        evaluate(run=run)


def test_zero_denominators_are_null():
    registry, protocol, run, _ = load_fixture()
    registry['works'] = [registry['works'][-1]]
    protocol['schedule'] = ['x1']
    run['results'] = [run['results'][-1]]
    pins = repin(registry, protocol, run)
    report = evaluate(registry, protocol, run, pins)
    assert all(value is None for value in report['rates'].values())


def test_reordering_preserves_scores_and_identical_inputs_replay():
    expected = evaluate()
    assert vb.canonical_bytes(evaluate()) == vb.canonical_bytes(expected)
    registry, protocol, run, _ = load_fixture()
    registry['works'].reverse()
    protocol['schedule'].reverse()
    run['results'].reverse()
    pins = repin(registry, protocol, run)
    report = evaluate(registry, protocol, run, pins)
    assert report['rates'] == expected['rates']
    assert report['family_counts'] == expected['family_counts']
    assert report['resources_reported'] == expected['resources_reported']


@pytest.mark.parametrize('data', [b'{"a":1,"a":2}', b'{"n":NaN}', b'{"n":1.0}', b'{"n":1e3}',
                                  b'\xff', b'[]', b'{', b'{"n":9007199254740992}'])
def test_strict_json(data):
    with pytest.raises(vb.BenchmarkError):
        vb.parse_document(data)


def test_depth_size_node_and_string_limits(monkeypatch):
    with pytest.raises(vb.BenchmarkError, match='DEPTH'):
        vb.parse_document(b'{"x":' + b'[' * 17 + b'0' + b']' * 17 + b'}')
    assert vb.parse_document(b'{"x":"[[[\\\"{{{\\\\"}') == {'x': '[[["{{{\\'}
    with pytest.raises(vb.BenchmarkError, match='STRING'):
        vb.parse_document(json.dumps({'x': 'a' * 4097}).encode())
    monkeypatch.setattr(vb, 'MAX_NODES', 3)
    with pytest.raises(vb.BenchmarkError, match='NODE'):
        vb.parse_document(b'{"x":[1,2]}')
    monkeypatch.setattr(vb, 'MAX_BYTES', 2)
    with pytest.raises(vb.BenchmarkError, match='BYTE'):
        vb.parse_document(b'{"x":1}')


def command(*extra):
    _, _, _, pins = load_fixture()
    return [sys.executable, '-m', 'tools.verification_benchmark',
            '--registry', str(FIXTURE / 'registry.json'), '--protocol', str(FIXTURE / 'protocol.json'),
            '--run', str(FIXTURE / 'run.json'),
            '--expected-registry-sha256', pins['expected_registry_sha256'],
            '--expected-protocol-sha256', pins['expected_protocol_sha256'], *extra]


def test_cli_determinism_invalid_input_and_no_raw_path_leak(tmp_path):
    outputs = [subprocess.run(command(), cwd=ROOT, check=True, capture_output=True, timeout=10).stdout
               for _ in range(2)]
    assert outputs[0] == outputs[1] == vb.canonical_bytes(evaluate())
    absent = tmp_path / 'private-path-must-not-appear.json'
    result = subprocess.run(command('--run', str(absent)), cwd=ROOT, capture_output=True, timeout=10)
    assert result.returncode == 2 and not result.stdout
    assert b'private-path' not in result.stderr
    assert json.loads(result.stderr)['status'] == 'invalid'


def test_symlink_and_hardlink_inputs_are_rejected(tmp_path):
    regular = tmp_path / 'regular.json'
    regular.write_bytes((FIXTURE / 'run.json').read_bytes())
    hard = tmp_path / 'hard.json'
    try:
        os.link(regular, hard)
    except OSError:
        pytest.skip('Hard links unavailable on this platform')
    result = subprocess.run(command('--run', str(hard)), cwd=ROOT, capture_output=True, timeout=10)
    assert result.returncode == 2 and not result.stdout
    hard.unlink()
    link = tmp_path / 'link.json'
    try:
        link.symlink_to(regular)
    except OSError:
        pytest.skip('Symlink creation unavailable on this platform')
    result = subprocess.run(command('--run', str(link)), cwd=ROOT, capture_output=True, timeout=10)
    assert result.returncode == 2 and not result.stdout


@pytest.mark.skipif(os.name != 'posix', reason='POSIX FIFO')
def test_fifo_rejected_without_blocking(tmp_path):
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    result = subprocess.run(command('--run', str(fifo)), cwd=ROOT, capture_output=True, timeout=10)
    assert result.returncode == 2 and not result.stdout


def test_fixture_pins_match_sources():
    registry, protocol, _, pins = load_fixture()
    assert vb.commitment(registry) == pins['expected_registry_sha256']
    assert vb.commitment(protocol) == pins['expected_protocol_sha256']
    for document in (registry, protocol):
        assert sha256(vb.canonical_bytes(document)).hexdigest() == vb.commitment(document)
