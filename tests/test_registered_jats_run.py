"""Actual fixed-worker integration plus bounded scheduling/recording regressions."""
from copy import deepcopy
from hashlib import sha256
import json
import os
import sys
import pytest

from tools import registered_jats_run as runner
from tools import verification_benchmark as vb
from tools.jats_source_adapter import audit_jats_source, canonical_bytes, component_id, interpretation_sha256


def source(value='8.10', denominator=True):
    header = 'n (%) N=50' if denominator else 'n (%)'
    return (f'<article><body><table-wrap id="T1"><table><thead><tr>'
            f'<th>Outcome</th><th>{header}</th></tr></thead><tbody><tr>'
            f'<td>Response</td><td>4 ({value}%)</td></tr></tbody>'
            '</table></table-wrap></body></article>').encode()


def registration(tmp_path, specs=None):
    specs = specs or [('positive',source(),'positive'),('negative',source('8.00'),'negative'),
                      ('unknown',source(denominator=False),'unresolved')]
    inputs = tmp_path/'inputs'
    inputs.mkdir()
    works, paths = [], {}
    for name, data, label in specs:
        (inputs/f'{name}.xml').write_bytes(data)
        raw = b'<td>4 (8.10%)</td>'
        start = data.find(raw)
        target = component_id(sha256(data).hexdigest(),start,start+len(raw),0,len('4 (8.10%)')) if label == 'positive' else None
        works.append({'work_id':name,'family_id':name,'source_sha256':sha256(data).hexdigest(),
                      'interpretation_sha256':interpretation_sha256(),'label':label,'eligible':True,
                      'exclusion_reason':None,'target_id':target})
        paths[name] = f'{name}.xml'
    registry = {'schema_version':vb.REGISTRY_VERSION,'exposure':'synthetic',
                'label_basis':'synthetic_construction','works':works}
    _,identity = runner.capture_implementation()
    protocol = {'schema_version':vb.PROTOCOL_VERSION,'registry_sha256':vb.commitment(registry),
                'implementation_sha256':vb.commitment(identity),'schedule':list(paths),
                'max_elapsed_ms':10000,'max_calls':0,'max_cost_micro_eur':0}
    sources = {'schema_version':'rw-jats-sources.v1','paths':paths}
    return registry,protocol,sources,inputs


def execute(tmp_path, prepared, name='result'):
    registry,protocol,sources,inputs = prepared
    return runner.run_registered(registry,protocol,sources,inputs,tmp_path/name,
                                 expected_registry_sha256=vb.commitment(registry),
                                 expected_protocol_sha256=vb.commitment(protocol))


@pytest.mark.parametrize('path', ['/absolute.xml','../a.xml','a/../b.xml','a\\b.xml','C:/a.xml',
                                 'a//b.xml','./a.xml','NUL.xml','foo./x.xml','', 'a\x00b.xml'])
def test_nonportable_or_escaping_paths_rejected(path):
    with pytest.raises(vb.BenchmarkError):
        runner._relative_path(path)


def test_safe_relative_source_path(tmp_path):
    directory = tmp_path/'sub'
    directory.mkdir()
    file = directory/'a.xml'
    file.write_bytes(b'<article/>')
    assert runner._relative_path('sub/a.xml') == 'sub/a.xml'
    assert runner._source_path(tmp_path,'sub/a.xml') == file


def test_source_symlink_and_hardlink_are_not_inputs(tmp_path):
    target = tmp_path/'target.xml'
    target.write_bytes(b'<article/>')
    link = tmp_path/'link.xml'
    try:
        os.symlink(target,link)
    except (OSError,NotImplementedError):
        pytest.skip('Native symlink creation is unavailable in this test account')
    with pytest.raises(vb.BenchmarkError,match='SOURCE_LINK'):
        runner._source_path(tmp_path,'link.xml')
    link.unlink()
    os.link(target,link)
    with pytest.raises(ValueError):
        runner.read_regular(link,1024)


def test_fixed_worker_has_no_ambient_module_path_or_label_arguments(tmp_path):
    command = runner._worker_command(tmp_path)
    assert command[:4] == [sys.executable,'-I','-S','-B']
    assert 'label' not in command[-1] and 'target_id' not in command[-1]
    assert 'tools.jats_worker' in command[-1]


@pytest.mark.parametrize('stream',['stdout','stderr'])
def test_pipe_output_is_bounded_during_production(tmp_path,monkeypatch,stream):
    monkeypatch.setattr(runner,'MAX_REPORT_BYTES',256)
    monkeypatch.setattr(runner,'MAX_STDERR_BYTES',128)
    command = [sys.executable,'-I','-S','-c',f'import sys;sys.{stream}.buffer.write(b"x"*65536)']
    data,reason = runner._exchange(command,b'',tmp_path,5000)
    assert data is None and reason == 'WORKER_OUTPUT_LIMIT'


def test_timeout_kills_and_reaps_owned_child(tmp_path):
    command = [sys.executable,'-I','-S','-c','import time;time.sleep(30)']
    data,reason = runner._exchange(command,b'',tmp_path,50)
    assert data is None and reason == 'WORKER_TIMEOUT'


def test_child_does_not_inherit_secrets_or_pythonpath(tmp_path,monkeypatch):
    monkeypatch.setenv('RW_TEST_SECRET','never-send')
    monkeypatch.setenv('PYTHONPATH',str(tmp_path))
    command = [sys.executable,'-I','-S','-c',
               'import os,sys;sys.stdout.write(str(os.getenv("RW_TEST_SECRET"))+":"+str(os.getenv("PYTHONPATH")))']
    data,reason = runner._exchange(command,b'',tmp_path,5000)
    assert reason == 'OK' and data == b'None:None'


def test_actual_end_to_end_source_execution_and_recovery(tmp_path):
    prepared = registration(tmp_path)
    result = execute(tmp_path,prepared)
    receipts = {r['work_id']:r for r in result['run']['results']}
    assert receipts['positive']['alarm_emitted'] is True
    assert receipts['positive']['certificate_status'] == 'accepted'
    assert receipts['positive']['target_id'] == prepared[0]['works'][0]['target_id']
    assert receipts['negative']['status'] == 'completed'
    assert receipts['negative']['alarm_emitted'] is False
    assert receipts['unknown']['status'] == 'abstained'
    assert result['score']['rates']['recorded_detection'] == {'numerator':1,'denominator':1}
    assert result['score']['rates']['observed_false_alarm'] == {'numerator':0,'denominator':1}
    assert result['scientific_performance_established'] is False
    assert result['score']['status'] == 'incomplete'
    recovered = runner.recover_registered(tmp_path/'result')
    assert recovered['status'] == 'recorded_finished'
    assert recovered['run'] == result['run'] and recovered['score'] == result['score']
    assert recovered['reexecuted'] is False
    events = [json.loads(line) for line in (tmp_path/'result/events.jsonl').read_bytes().splitlines()]
    assert [e['event'] for e in events] == ['attempt_started','output_recorded','attempt_finished']*3
    for index,event in enumerate(events):
        assert event['sequence'] == index
    assert b'\r\n' not in (tmp_path/'result/summary.json').read_bytes()


def test_missing_source_preserves_registered_denominator(tmp_path):
    prepared = registration(tmp_path)
    (prepared[3]/'positive.xml').unlink()
    result = execute(tmp_path,prepared)
    assert result['run']['results'][0]['status'] == 'source_unavailable'
    assert result['score']['rates']['recorded_detection'] == {'numerator':0,'denominator':1}
    assert result['score']['rates']['recorded_detection_completion_upper_bound'] == {'numerator':1,'denominator':1}
    assert len(result['run']['results']) == 3


def test_actual_source_hash_mismatch_is_recorded_not_relabelled(tmp_path):
    prepared = registration(tmp_path)
    (prepared[3]/'positive.xml').write_bytes(source('8.00'))
    result = execute(tmp_path,prepared)
    assert result['run']['results'][0]['status'] == 'failed'
    assert result['outcomes'][0]['actual_source_sha256'] != prepared[0]['works'][0]['source_sha256']
    assert result['score']['family_counts']['positive'] == 1


def test_failed_certificate_does_not_erase_negative_alarm(tmp_path,monkeypatch):
    data = source()
    prepared = registration(tmp_path,[('negative',data,'negative')])
    report = audit_jats_source(data)
    report['relations'][0]['certificate_status'] = 'rejected'
    monkeypatch.setattr(runner,'_exchange',lambda *args:(canonical_bytes(report),'OK'))
    result = execute(tmp_path,prepared)
    assert result['run']['results'][0]['alarm_emitted'] is True
    assert result['run']['results'][0]['certificate_status'] == 'rejected'
    assert result['score']['rates']['observed_false_alarm'] == {'numerator':1,'denominator':1}


def test_registration_and_actual_code_pin_fail_before_outputs(tmp_path):
    prepared = registration(tmp_path)
    registry,protocol,sources,inputs = prepared
    with pytest.raises(vb.BenchmarkError,match='REGISTRY_PIN_MISMATCH'):
        runner.run_registered(registry,protocol,sources,inputs,tmp_path/'bad',
                              expected_registry_sha256='0'*64,
                              expected_protocol_sha256=vb.commitment(protocol))
    assert not (tmp_path/'bad').exists()
    protocol['implementation_sha256'] = '0'*64
    with pytest.raises(vb.BenchmarkError,match='ACTUAL_IMPLEMENTATION_BINDING'):
        execute(tmp_path,prepared,'bad-code')
    assert not (tmp_path/'bad-code').exists()


@pytest.mark.parametrize('change',['protected','paid','calls'])
def test_no_protected_or_paid_modes(tmp_path,change):
    prepared = registration(tmp_path)
    registry,protocol,_,_ = prepared
    if change == 'protected':
        registry['exposure'] = 'sealed'
        protocol['registry_sha256'] = vb.commitment(registry)
    elif change == 'paid':
        protocol['max_cost_micro_eur'] = 1
    else:
        protocol['max_calls'] = 1
    with pytest.raises(vb.BenchmarkError):
        execute(tmp_path,prepared)
    assert not (tmp_path/'result').exists()


def test_total_deadline_keeps_unattempted_tail(tmp_path,monkeypatch):
    prepared = registration(tmp_path)
    monkeypatch.setattr(runner,'MAX_TOTAL_MS',0)
    result = execute(tmp_path,prepared)
    assert all(r['status'] == 'not_attempted' for r in result['run']['results'])
    assert result['score']['family_counts']['registered'] == 3
    assert result['score']['status'] == 'incomplete'


def test_recovery_without_completion_marker_is_interrupted(tmp_path):
    prepared = registration(tmp_path,[('negative',source('8.00'),'negative')])
    execute(tmp_path,prepared)
    (tmp_path/'result/finished.json').unlink()
    recovered = runner.recover_registered(tmp_path/'result')
    assert recovered['status'] == 'interrupted'
    assert recovered['score']['status'] == 'complete'  # Coverage is distinct from durable completion.
    with (tmp_path/'result/events.jsonl').open('ab') as stream:
        stream.write(b'{"partial":')
    assert runner.recover_registered(tmp_path/'result')['partial_trailing_record'] is True


def test_interrupted_started_work_is_not_retried(tmp_path):
    prepared = registration(tmp_path)
    execute(tmp_path,prepared)
    (tmp_path/'result/finished.json').unlink()
    events_path = tmp_path/'result/events.jsonl'
    events = events_path.read_bytes().splitlines(keepends=True)
    events_path.write_bytes(b''.join(events[:-1]))
    recovered = runner.recover_registered(tmp_path/'result')
    assert recovered['unfinished'] == ['unknown']
    assert recovered['score']['work_counts']['missing'] == 0
    assert recovered['run']['results'][-1]['status'] == 'failed'
    assert recovered['reexecuted'] is False


def test_recovery_rejects_changed_artifact(tmp_path):
    prepared = registration(tmp_path,[('negative',source('8.00'),'negative')])
    execute(tmp_path,prepared)
    (tmp_path/'result/case-0000.json').write_bytes(b'{}\n')
    with pytest.raises(vb.BenchmarkError,match='RECOVERY_ARTIFACT_HASH'):
        runner.recover_registered(tmp_path/'result')


def test_source_manifest_cannot_smuggle_unknown_work_or_parent_path(tmp_path):
    prepared = registration(tmp_path)
    corrupted = deepcopy(prepared)
    corrupted[2]['paths']['positive'] = '../secret.xml'
    with pytest.raises(vb.BenchmarkError,match='SOURCE_PATH'):
        execute(tmp_path,corrupted)
    assert not (tmp_path/'result').exists()


def test_public_demo_cli_runs_without_network_or_provider(tmp_path):
    import subprocess
    result = subprocess.run([sys.executable,'-m','tools.jats_demo','--output-dir',str(tmp_path/'demo')],
                            cwd=runner.ROOT,capture_output=True,timeout=45)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert len(summary['run']['results']) == 3
    assert summary['run']['results'][0]['alarm_emitted'] is True
    assert summary['run']['results'][1]['alarm_emitted'] is False
    assert summary['run']['results'][2]['status'] == 'abstained'
    assert summary['score']['rates']['recorded_detection'] == {'numerator':1,'denominator':1}
    assert summary['scientific_performance_established'] is False
    assert b'\r\n' not in result.stdout


@pytest.mark.parametrize('defect', ['sibling', 'duplicate', 'certificate', 'binding'])
def test_invalid_worker_output_keeps_emitted_negative_alarm(tmp_path, monkeypatch, defect):
    data = source()
    prepared = registration(tmp_path, [('negative', data, 'negative')])
    report = audit_jats_source(data)
    if defect == 'sibling':
        report['relations'].insert(0, {'broken': True})
    elif defect == 'duplicate':
        report['relations'].append(deepcopy(report['relations'][0]))
    elif defect == 'certificate':
        report['relations'][0]['certificate_sha256'] = '0' * 64
    else:
        report['source_sha256'] = '0' * 64
    monkeypatch.setattr(runner, '_exchange', lambda *args: (canonical_bytes(report), 'OK'))
    result = execute(tmp_path, prepared)
    receipt = result['run']['results'][0]
    assert receipt['status'] == 'failed'
    assert receipt['alarm_emitted'] is True
    assert result['score']['rates']['observed_false_alarm'] == {'numerator': 1, 'denominator': 1}
    assert runner.recover_registered(tmp_path / 'result')['run'] == result['run']


def test_missing_registered_target_is_not_replaced_by_another_finding(tmp_path):
    data = source()
    prepared = registration(tmp_path, [('positive', data, 'positive')])
    work = prepared[0]['works'][0]
    work['target_id'] = 'src-' + '0' * 64
    prepared[1]['registry_sha256'] = vb.commitment(prepared[0])
    result = execute(tmp_path, prepared)
    receipt = result['run']['results'][0]
    assert receipt['alarm_emitted'] is True
    assert receipt['certificate_status'] == 'rejected'
    assert receipt['target_id'] is None
    assert result['score']['rates']['recorded_detection'] == {'numerator': 0, 'denominator': 1}


def test_negative_alarm_survives_other_relationship_abstention(tmp_path):
    data = source().replace(b'</body>', source(denominator=False).split(b'<body>')[1].split(b'</body>')[0] + b'</body>')
    prepared = registration(tmp_path, [('negative', data, 'negative')])
    result = execute(tmp_path, prepared)
    assert result['run']['results'][0]['status'] == 'abstained'
    assert result['run']['results'][0]['alarm_emitted'] is True
    assert result['score']['rates']['observed_false_alarm'] == {'numerator': 1, 'denominator': 1}


def test_interruption_after_emission_recovers_negative_alarm(tmp_path):
    prepared = registration(tmp_path, [('negative', source(), 'negative')])
    execute(tmp_path, prepared)
    (tmp_path / 'result/finished.json').unlink()
    events = tmp_path / 'result/events.jsonl'
    events.write_bytes(b''.join(events.read_bytes().splitlines(keepends=True)[:-1]))
    recovered = runner.recover_registered(tmp_path / 'result')
    assert recovered['status'] == 'interrupted' and recovered['unfinished'] == ['negative']
    assert recovered['run']['results'][0]['status'] == 'failed'
    assert recovered['score']['rates']['observed_false_alarm'] == {'numerator': 1, 'denominator': 1}
