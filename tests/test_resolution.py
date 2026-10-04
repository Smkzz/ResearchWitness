from copy import deepcopy
from datetime import date
import json
import subprocess
import sys

import pytest

from researchwitness import Invalid
from researchwitness.capsule import subject_digest
from researchwitness.strict import digest, byte_hash
from researchwitness.resolution import project, evaluate_timeline, TIMELINE_SCHEMA_VERSION

TODAY = date(2026, 10, 4)


def timeline(case, specs):
    obj = {'schema_version': TIMELINE_SCHEMA_VERSION, 'subject_sha256': subject_digest(case), 'events': []}
    previous = digest({'schema_version': TIMELINE_SCHEMA_VERSION, 'subject_sha256': obj['subject_sha256']})
    for i, (kind, data) in enumerate(specs, 1):
        event = {
            'seq': i,
            'previous_sha256': previous,
            'kind': kind,
            'on': '2026-10-04',
            'actor_id': 'fixture-operator',
            'evidence_artifact': 'correction-check.txt',
            'data': data,
        }
        obj['events'].append(event)
        previous = digest(event)
    return obj



def test_inquiry_record_is_metadata(bundle):
    root, case, data = bundle
    result = project(case, data, timeline(case, [('INQUIRY_RECORDED', {'note': 'Synthetic inquiry.'})]), TODAY)
    assert result['communication'] == 'INQUIRY_RECORDED_NOT_AUTHENTICATED'
    assert result['resolution'] == 'OPEN'

def test_author_agreement_is_metadata_not_proof(bundle):
    root, case, data = bundle
    result = project(case, data, timeline(case, [
        ('AUTHOR_POSITION_RECORDED', {'position': 'agrees', 'note': 'Synthetic fixture.'})
    ]), TODAY)
    assert result['resolution'] == 'OPEN'
    assert result['author_position'] == 'AGREES_RECORDED_NOT_AUTHENTICATED'
    assert result['original_mathematical_result_changed'] is False
    assert result['correction_verified'] is False
    assert result['external_actions'] == 'OUT_OF_SCOPE'


def test_silence_is_not_agreement(bundle):
    root, case, data = bundle
    result = project(case, data, timeline(case, []), TODAY)
    assert result['author_position'] == 'NOT_RECORDED'
    assert result['resolution'] == 'OPEN'


def test_notice_is_not_verified_correction(bundle):
    root, case, data = bundle
    events = [('CORRECTION_NOTICE_RECORDED', {'revision_artifact': 'source.txt', 'version': 'synthetic-v2'})]
    result = project(case, data, timeline(case, events), TODAY)
    assert result['resolution'] == 'NOTICE_RECORDED_UNCHECKED'
    assert result['revision_witness_result'] is None
    assert result['correction_verified'] is False


@pytest.mark.parametrize('bound,expected', [
    ('1', 'OLD_WITNESS_NO_LONGER_REFUTES_REVISION'),
    ('1/2', 'OLD_WITNESS_STILL_REFUTES_REVISION'),
])
def test_revision_rechecks_only_old_witness(bundle, bound, expected):
    root, case, data = bundle
    revision = deepcopy(case['claim']['formalization'])
    revision['upper_bound'] = bound
    data['revised-spec.json'] = json.dumps(revision).encode()
    case['artifacts']['revised-spec.json'] = byte_hash(data['revised-spec.json'])
    events = [
        ('CORRECTION_NOTICE_RECORDED', {'revision_artifact': 'source.txt', 'version': 'synthetic-v2'}),
        ('REVISION_WITNESS_RECHECK', {
            'revision_sha256': case['artifacts']['source.txt'],
            'formalization_artifact': 'revised-spec.json',
        }),
    ]
    result = project(case, data, timeline(case, events), TODAY)
    assert result['resolution'] == expected
    assert result['correction_verified'] is False


def test_new_revision_invalidates_previous_recheck(bundle):
    root, case, data = bundle
    revision = deepcopy(case['claim']['formalization'])
    revision['upper_bound'] = '1'
    data['revised-spec.json'] = json.dumps(revision).encode()
    case['artifacts']['revised-spec.json'] = byte_hash(data['revised-spec.json'])
    events = [
        ('CORRECTION_NOTICE_RECORDED', {'revision_artifact': 'source.txt', 'version': 'synthetic-v2'}),
        ('REVISION_WITNESS_RECHECK', {
            'revision_sha256': case['artifacts']['source.txt'],
            'formalization_artifact': 'revised-spec.json',
        }),
        ('CORRECTION_NOTICE_RECORDED', {'revision_artifact': 'source.txt', 'version': 'synthetic-v3'}),
    ]
    assert project(case, data, timeline(case, events), TODAY)['revision_witness_result'] is None


def test_withdrawal_and_reopen_preserve_resolution(bundle):
    root, case, data = bundle
    t = timeline(case, [
        ('CASE_WITHDRAWN', {'reason': 'Counterargument accepted.'}),
        ('CASE_REOPENED', {'reason': 'New evidence.'}),
    ])
    result = project(case, data, t, TODAY)
    assert result['resolution'] == 'OPEN'
    assert result['correction_verified'] is False


@pytest.mark.parametrize('specs', [
    [('CASE_REOPENED', {'reason': 'Not withdrawn'})],
    [('CASE_WITHDRAWN', {'reason': 'Mistake'}), ('INQUIRY_RECORDED', {'note': 'Bad transition'})],
    [('REVISION_WITNESS_RECHECK', {'revision_sha256': '0' * 64, 'formalization_artifact': 'source.txt'})],
    [('AUTHOR_POSITION_RECORDED', {'position': 'silent', 'note': 'Silence cannot count'})],
    [('SEND_EMAIL', {'note': 'No sender exists'})],
])
def test_bad_transitions_reject(bundle, specs):
    root, case, data = bundle
    with pytest.raises(Invalid):
        project(case, data, timeline(case, specs), TODAY)


@pytest.mark.parametrize('field,value', [
    ('seq', 2), ('previous_sha256', '0' * 64), ('on', '2027-01-01'),
    ('kind', []), ('evidence_artifact', {}), ('actor_id', None),
])
def test_event_mutation_fails(bundle, field, value):
    root, case, data = bundle
    t = timeline(case, [('INQUIRY_RECORDED', {'note': 'Synthetic fixture.'})])
    t['events'][0][field] = value
    with pytest.raises(Invalid):
        project(case, data, t, TODAY)


def test_wrong_subject_rejects(bundle):
    root, case, data = bundle
    t = timeline(case, [])
    t['subject_sha256'] = '0' * 64
    with pytest.raises(Invalid):
        project(case, data, t, TODAY)


def test_timeline_pin_detects_coherent_rewrite(bundle):
    root, case, data = bundle
    t = timeline(case, [])
    pin = digest(t)
    altered = timeline(case, [('AUTHOR_POSITION_RECORDED', {'position': 'agrees', 'note': 'Invented'})])
    with pytest.raises(Invalid):
        project(case, data, altered, TODAY, pin)
    assert project(case, data, t, TODAY, pin)['externally_pinned']


def test_timeline_cli(bundle, tmp_path):
    root, case, data = bundle
    path = tmp_path / 'timeline.json'
    path.write_text(json.dumps(timeline(case, [])))
    assert evaluate_timeline(root, path, TODAY)['event_count'] == 0
    result = subprocess.run(
        [sys.executable, '-m', 'researchwitness', 'timeline', str(root), '--timeline', str(path), '--as-of', '2026-10-04'],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['external_actions'] == 'OUT_OF_SCOPE'
