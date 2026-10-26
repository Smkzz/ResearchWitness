"""Run a fixed offline JATS adapter on a pinned, exposed development schedule.

No arbitrary commands/providers, protected data, retries, network acquisition or
paid work. This is trusted Python subprocess execution, NOT an OS security
sandbox. Caller-selected source/output roots and the Python/OS runtime must be
trusted and quiescent. Scientific adjudication remains outside this runner.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from tools import verification_benchmark as vb
from tools.jats_source_adapter import (
    ADAPTER_VERSION, MAX_REPORT_BYTES, canonical_bytes, commitment,
    component_id, interpretation_sha256, replay_percentage,
)
from tools.offline_files import read_regular

ROOT = Path(__file__).resolve().parents[1]
MAX_WORKS = 64
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_RETAINED_BYTES = 32 * 1024 * 1024
MAX_TOTAL_MS = 120_000
MAX_WORKER_MS = 30_000
FINALIZATION_RESERVE_MS = 5000
MAX_STDERR_BYTES = 4096
CODE_FILES = (
    'researchwitness/__init__.py', 'researchwitness/arithmetic.py',
    'researchwitness/capsule.py', 'researchwitness/checkers.py',
    'researchwitness/strict.py', 'researchwitness/example_data.py',
    'researchwitness/capability_examples.json', 'researchwitness/paper_document.py',
    'researchwitness/_jats_parser.py', 'researchwitness/_jats_math.py',
    'researchwitness/_jats_files.py',
    'tools/__init__.py', 'tools/offline_files.py', 'tools/public_discovery.py',
    'tools/jats_percentage_audit.py', 'tools/jats_source_adapter.py',
    'tools/jats_worker.py', 'tools/verification_benchmark.py', 'tools/registered_jats_run.py',
)


def capture_implementation() -> tuple[dict[str, bytes], dict[str, Any]]:
    files = {name: read_regular(ROOT / name, MAX_SOURCE_BYTES) for name in CODE_FILES}
    # The executable/stdlib/OS must be trusted; this pins the executable bytes but
    # is not a complete interpreter-DLL or operating-system attestation.
    executable = Path(sys.executable).resolve(strict=True)
    executable_hash = sha256()
    with executable.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            executable_hash.update(block)
    identity = {
        'schema_version': 'rw-jats-execution-identity.v1',
        'files': {name: sha256(data).hexdigest() for name, data in sorted(files.items())},
        'python_version': sys.version, 'platform': platform.system(),
        'executable_sha256': executable_hash.hexdigest(),
        'runtime_trust': 'interpreter_standard_library_and_os_remain_trusted',
    }
    return files, identity


def _snapshot(files: dict[str, bytes], root: Path) -> None:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)


def _worker_command(snapshot: Path) -> list[str]:
    bootstrap = (f'import sys; sys.path.insert(0, {str(snapshot)!r}); '
                 'from tools.jats_worker import main; raise SystemExit(main())')
    # -I ignores ambient Python paths/user site; -S disables site startup hooks;
    # -B avoids pycache writes. Only captured trusted modules are added to sys.path.
    return [sys.executable, '-I', '-S', '-B', '-c', bootstrap]


def _exchange(command: list[str], source: bytes, cwd: Path, timeout_ms: int) -> tuple[bytes | None, str]:
    """Bound both pipes while reading; kill/reap the owned child on any excess."""
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL'}}
    deadline = time.monotonic() + timeout_ms / 1000
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = [bytearray(), bytearray()]
    limits = [MAX_REPORT_BYTES, MAX_STDERR_BYTES]
    overflow = threading.Event()
    failures = threading.Event()

    def read_pipe(pipe: Any, index: int) -> None:
        try:
            while data := pipe.read(8192):
                if len(buffers[index]) + len(data) > limits[index]:
                    overflow.set()
                    return
                buffers[index].extend(data)
        except OSError:
            failures.set()
        finally:
            pipe.close()

    def write_input() -> None:
        try:
            process.stdin.write(source)
        except (BrokenPipeError, OSError):
            pass  # The exit status and bounded stderr carry the fixed diagnosis.
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    threads = [threading.Thread(target=read_pipe, args=(process.stdout, 0), daemon=True),
               threading.Thread(target=read_pipe, args=(process.stderr, 1), daemon=True),
               threading.Thread(target=write_input, daemon=True)]
    started_threads = []
    reason = 'OK'
    try:
        for thread in threads:
            thread.start()
            started_threads.append(thread)
        while process.poll() is None:
            if overflow.is_set():
                reason = 'WORKER_OUTPUT_LIMIT'
                break
            if failures.is_set():
                reason = 'WORKER_PIPE_ERROR'
                break
            if time.monotonic() >= deadline:
                reason = 'WORKER_TIMEOUT'
                break
            overflow.wait(min(0.01, max(0, deadline - time.monotonic())))
    finally:
        if process.poll() is None:
            process.kill()
        cleanup_deadline = time.monotonic() + FINALIZATION_RESERVE_MS / 1000
        try:
            process.wait(timeout=max(0.001, cleanup_deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('WORKER_CLEANUP_FAILED') from exc
        for thread in started_threads:
            thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
        if any(thread.is_alive() for thread in started_threads):
            raise RuntimeError('WORKER_CLEANUP_FAILED')
        for pipe in (process.stdin, process.stdout, process.stderr):
            if not pipe.closed:
                pipe.close()
    if overflow.is_set():
        return None, 'WORKER_OUTPUT_LIMIT'
    if reason != 'OK':
        return None, reason
    if failures.is_set():
        return None, 'WORKER_PIPE_ERROR'
    if process.returncode != 0:
        return None, 'WORKER_REJECTED_INPUT'
    return bytes(buffers[0]), 'OK'


def _relative_path(value: Any) -> str:
    vb.require(type(value) is str and 0 < len(value) <= 512, 'SOURCE_PATH')
    path = PurePosixPath(value)
    vb.require(not path.is_absolute() and path.as_posix() == value and
               all(part not in {'.', '..'} and re.fullmatch(r'[A-Za-z0-9_.-]+', part)
                   for part in path.parts), 'SOURCE_PATH')
    devices = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)),
               *(f'lpt{i}' for i in range(1, 10))}
    vb.require(all(not part.endswith('.') and part.split('.', 1)[0].lower() not in devices
                   for part in path.parts), 'SOURCE_PATH')
    return value


def _source_path(root: Path, relative: str) -> Path:
    current = root
    parts = PurePosixPath(relative).parts
    for i, part in enumerate(parts):
        current = current / part
        info = current.lstat()
        reparse = getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
        vb.require(not stat.S_ISLNK(info.st_mode) and not reparse, 'SOURCE_LINK')
        if i < len(parts) - 1:
            vb.require(stat.S_ISDIR(info.st_mode), 'SOURCE_PARENT')
    return current


def _write(path: Path, document: dict) -> int:
    data = canonical_bytes(document)
    vb.require(len(data) <= vb.MAX_BYTES, 'RECORD_OUTPUT_LIMIT')
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return len(data)


class Journal:
    def __init__(self, path: Path, run_id: str):
        self.stream = path.open('xb')
        self.run_id = run_id
        self.sequence = 0
        self.previous = '0' * 64

    def append(self, event: str, **fields: Any) -> None:
        record = {'sequence': self.sequence, 'run_id': self.run_id,
                  'previous_sha256': self.previous, 'event': event, **fields}
        data = canonical_bytes(record)
        self.stream.write(data)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.previous = sha256(data).hexdigest()
        self.sequence += 1

    def close(self) -> None:
        self.stream.close()


def _empty_run(registry: dict, protocol: dict) -> dict:
    return {'schema_version': vb.RUN_VERSION, 'registry_sha256': commitment(registry),
            'protocol_sha256': commitment(protocol),
            'implementation_sha256': protocol['implementation_sha256'], 'results': []}


def _receipt(work: dict, status: str = 'failed') -> dict:
    return {
        'work_id': work['work_id'], 'source_sha256': work['source_sha256'],
        'interpretation_sha256': work['interpretation_sha256'], 'status': status,
        'alarm_emitted': False, 'candidate_sha256': None, 'certificate_sha256': None,
        'certificate_status': 'not_checked', 'source_correspondence': 'unresolved',
        'target_id': None, 'elapsed_ms': 0, 'calls': 0, 'cost_micro_eur': 0,
    }


def _declared_alarm_receipt(report: dict, work: dict) -> dict:
    """Inventory bounded declarations before semantic checks can reject siblings.

    This deliberately counts a claimed candidate even if its certificate, identity,
    or other sibling is invalid. Unparseable output remains an incomplete failure.
    """
    receipt = _receipt(work)
    relations = report.get('relations')
    vb.require(type(relations) is list and len(relations) <= 1000, 'WORKER_RELATIONS')
    declarations = [item for item in relations if type(item) is dict and
                    (item.get('alarm_emitted') is True or
                     item.get('detector_status') == 'arithmetic_mismatch_candidate')]
    if declarations:
        receipt.update(alarm_emitted=True, candidate_sha256=commitment(declarations))
    return receipt


def _evaluate_report(data: bytes, source: bytes, work: dict) -> tuple[dict, dict]:
    report = vb.parse_document(data)
    vb.require(report.get('schema_version') == ADAPTER_VERSION and
               report.get('source_sha256') == work['source_sha256'] and
               report.get('interpretation_sha256') == interpretation_sha256(), 'WORKER_BINDING')
    relations = report.get('relations')
    vb.require(type(relations) is list and len(relations) <= 1000, 'WORKER_RELATIONS')
    seen: set[str] = set()
    alarms: list[dict] = []
    verified: list[dict] = []
    for item in relations:
        identifier = vb._id(item['relation_id'])
        vb.require(identifier not in seen, 'DUPLICATE_RELATION_ID')
        seen.add(identifier)
        anchor = item['assertion']['source_anchor']
        start, end = anchor['start_byte'], anchor['end_byte']
        vb.require(type(start) is int and type(end) is int and 0 <= start < end <= len(source),
                   'WORKER_ELEMENT_SPAN')
        vb.require(anchor['source_sha256'] == work['source_sha256'] and
                   sha256(source[start:end]).hexdigest() == item['element_sha256'], 'WORKER_SOURCE_SPAN')
        expected_target = component_id(work['source_sha256'], start, end,
                                       item['normalized_character_start'], item['normalized_character_end'])
        vb.require(item['target_id'] == expected_target, 'WORKER_COMPONENT_BINDING')
        alarm = vb._bool(item['alarm_emitted'])
        vb.require(alarm == (item['detector_status'] == 'arithmetic_mismatch_candidate'), 'WORKER_ALARM')
        if not alarm:
            continue
        alarms.append(item)  # Preserve emissions even when certificate replay rejects.
        certificate = item['certificate']
        if item['certificate_status'] != 'accepted':
            continue
        vb.require(commitment(certificate) == item['certificate_sha256'] and
                   certificate['source_sha256'] == work['source_sha256'] and
                   certificate['relation_id'] == identifier and
                   certificate['element_sha256'] == item['element_sha256'], 'WORKER_CERTIFICATE_BINDING')
        original = report['detector_report']['results'][item['legacy_result_index']]
        vb.require(certificate['legacy_result_sha256'] == commitment(original), 'WORKER_RESULT_BINDING')
        replay = replay_percentage(original['numerator'], original['denominator'],
                                   original['reported_percent'], original['display_precision'])
        vb.require(certificate['arithmetic'] == replay and not replay['arithmetic_matches'],
                   'WORKER_CERTIFICATE_REPLAY')
        verified.append(item)
    # Target/label matching happens after all source-only detection and replay.
    selected = (next((item for item in verified if item['target_id'] == work['target_id']), None)
                if work['target_id'] is not None else next(iter(verified), None))
    abstentions = any(item['detector_status'] not in {'arithmetic_match', 'arithmetic_mismatch_candidate'}
                      for item in relations)
    receipt = _receipt(work, 'abstained' if abstentions or not relations else 'completed')
    if alarms:
        receipt.update(alarm_emitted=True, candidate_sha256=commitment(alarms),
                       certificate_status='accepted' if selected else 'rejected',
                       certificate_sha256=commitment([item['certificate'] for item in alarms]),
                       source_correspondence='supported' if selected else 'unresolved',
                       target_id=None if selected is None else selected['target_id'])
    return receipt, report


def run_registered(registry: dict, protocol: dict, sources: dict, source_root: Path,
                   output: Path, *, expected_registry_sha256: str,
                   expected_protocol_sha256: str) -> dict:
    run = _empty_run(registry, protocol)
    pins = {'expected_registry_sha256': expected_registry_sha256,
            'expected_protocol_sha256': expected_protocol_sha256}
    vb.score(registry, protocol, run, **pins)  # Strict registration validation before side effects.
    works = vb._registry(registry)
    vb.require(len(works) <= MAX_WORKS and 0 < protocol['max_elapsed_ms'] <= MAX_WORKER_MS,
               'RUNNER_LIMIT')
    vb.require(protocol['max_calls'] == 0, 'PROVIDER_CALLS_NOT_SUPPORTED')
    vb._object(sources, 'schema_version paths')
    vb.require(sources['schema_version'] == 'rw-jats-sources.v1' and type(sources['paths']) is dict
               and set(sources['paths']) == set(works), 'SOURCE_SCHEDULE')
    for relative in sources['paths'].values():
        if relative is not None:
            _relative_path(relative)
    vb.require(all(work['interpretation_sha256'] == interpretation_sha256() for work in works.values()),
               'INTERPRETATION_BINDING')
    files, identity = capture_implementation()
    vb.require(commitment(identity) == protocol['implementation_sha256'], 'ACTUAL_IMPLEMENTATION_BINDING')
    root = source_root.resolve(strict=True)
    vb.require(root.is_dir(), 'SOURCE_ROOT')
    output.mkdir(mode=0o700, exist_ok=False)
    registration = {'schema_version': 'rw-jats-registration.v1', 'registry': registry,
                    'protocol': protocol, 'sources': sources, 'expected_pins': pins,
                    'implementation': identity, 'runner_limits': {
                        'max_source_total_bytes': MAX_SOURCE_TOTAL_BYTES,
                        'max_retained_bytes': MAX_RETAINED_BYTES, 'max_total_ms': MAX_TOTAL_MS},
                    'scope': 'exposed_development_only_not_independent_scientific_validation'}
    retained = _write(output / 'registration.json', registration)
    journal = Journal(output / 'events.jsonl', commitment(registration))
    deadline = time.monotonic() + MAX_TOTAL_MS / 1000
    source_bytes = 0
    outcomes = []
    try:
        # Captured bytes, not a mutable checkout or ambient Python module search.
        with tempfile.TemporaryDirectory(prefix='rw-jats-code-') as directory:
            snapshot = Path(directory)
            _snapshot(files, snapshot)
            command = _worker_command(snapshot)
            for index, work_id in enumerate(protocol['schedule']):
                work = works[work_id]
                journal.append('attempt_started', work_id=work_id, index=index)
                before = time.monotonic()
                remaining_ms = math.floor((deadline - before) * 1000) - FINALIZATION_RESERVE_MS
                receipt = _receipt(work)
                code = 'NOT_ATTEMPTED'
                artifact_hash = None
                actual_source_hash = None
                relative = sources['paths'][work_id]
                if remaining_ms <= 0 or source_bytes >= MAX_SOURCE_TOTAL_BYTES or retained >= MAX_RETAINED_BYTES - 1024 * 1024:
                    receipt['status'] = 'not_attempted'
                    code = 'TOTAL_BUDGET_EXHAUSTED'
                elif not work['eligible']:
                    receipt['status'] = 'not_attempted'
                    code = 'REGISTERED_EXCLUSION'
                elif relative is None:
                    receipt['status'] = 'source_unavailable'
                    code = 'SOURCE_UNAVAILABLE'
                else:
                    try:
                        source = read_regular(_source_path(root, relative),
                                              min(MAX_SOURCE_BYTES, MAX_SOURCE_TOTAL_BYTES - source_bytes))
                        source_bytes += len(source)
                        actual_source_hash = sha256(source).hexdigest()
                        vb.require(actual_source_hash == work['source_sha256'], 'SOURCE_HASH_MISMATCH')
                        vb.require(source_bytes <= MAX_SOURCE_TOTAL_BYTES, 'TOTAL_SOURCE_LIMIT')
                        remaining_ms = math.floor((deadline - time.monotonic()) * 1000) - FINALIZATION_RESERVE_MS
                        budget_ms = min(protocol['max_elapsed_ms'], remaining_ms)
                        vb.require(budget_ms > 0, 'TOTAL_TIME_LIMIT')
                        data, code = _exchange(command, source, snapshot, budget_ms)
                        if data is None:
                            receipt['status'] = 'timeout' if code == 'WORKER_TIMEOUT' else 'failed'
                        else:
                            vb.require(retained + len(data) <= MAX_RETAINED_BYTES - 1024 * 1024, 'TOTAL_OUTPUT_LIMIT')
                            with (output / f'case-{index:04d}.json').open('xb') as stream:
                                stream.write(data)
                                stream.flush()
                                os.fsync(stream.fileno())
                            artifact_hash = sha256(data).hexdigest()
                            retained += len(data)
                            receipt = _declared_alarm_receipt(vb.parse_document(data), work)
                            journal.append('output_recorded', work_id=work_id, index=index,
                                           artifact_sha256=artifact_hash, receipt=receipt)
                            receipt, _report = _evaluate_report(data, source, work)
                            if time.monotonic() >= deadline - FINALIZATION_RESERVE_MS / 1000:
                                receipt['status'] = 'budget_exceeded'
                                code = 'TOTAL_TIME_LIMIT'
                    except FileNotFoundError:
                        unavailable = actual_source_hash is None
                        receipt = _receipt(work, 'source_unavailable' if unavailable else 'failed')
                        code = 'SOURCE_UNAVAILABLE' if unavailable else 'WORKER_OR_OUTPUT_UNAVAILABLE'
                    except (OSError, ValueError, TypeError, KeyError, IndexError):
                        # Preserve any already observed alarm, but never count a failed
                        # execution as a verified detection. Other cases remain scheduled.
                        receipt['status'] = 'failed'
                        code = 'SOURCE_OR_WORKER_VALIDATION_FAILED'
                receipt['elapsed_ms'] = math.ceil((time.monotonic() - before) * 1000)
                if receipt['elapsed_ms'] > protocol['max_elapsed_ms']:
                    receipt['status'] = 'budget_exceeded'
                terminal = {'work_id': work_id, 'index': index, 'receipt': receipt,
                            'diagnostic': code, 'artifact_sha256': artifact_hash,
                            'actual_source_sha256': actual_source_hash}
                journal.append('attempt_finished', **terminal)
                outcomes.append(terminal)
                run['results'].append(receipt)
    finally:
        journal.close()  # A crash leaves a recoverable unmatched start, never a completion marker.
    score = vb.score(registry, protocol, run, **pins)
    summary = {
        'schema_version': 'rw-jats-execution-summary.v1', 'run': run, 'score': score,
        'outcomes': outcomes, 'source_bytes_read': source_bytes,
        'scientific_performance_established': False, 'protected_evaluation_performed': False,
        'source_correspondence_scope': 'detector_element_mapping_not_independent_adjudication',
        'arithmetic_replay_scope': 'supported_exact_count_percentage_operands_only',
        'runtime_boundary': 'fixed_code_subprocess_not_an_os_security_sandbox',
        'limitations': ['Registry labels and work-family independence remain supplied assertions.',
                        'Hashes/journal are not authenticated chronology or protection from a malicious local owner.',
                        'Trusted quiescent local filesystem, interpreter, standard library and OS are prerequisites.',
                        'Timeout/output caps do not qualify native PDF execution or general memory isolation.',
                        'A work with any extracted abstention remains incomplete; omitted relations are not measured.',
                        'The absolute execution deadline reserves cleanup time; OS file I/O and process creation are not hard real-time bounded.'],
    }
    _write(output / 'summary.json', summary)
    _write(output / 'finished.json', {'registration_sha256': commitment(registration),
                                     'summary_sha256': commitment(summary),
                                     'journal_tip_sha256': journal.previous,
                                     'ledger_complete': len(run['results']) == len(works),
                                     'coverage_complete': score['coverage_complete']})
    return summary


def recover_registered(output: Path) -> dict:
    """Read-only reconstruction after interruption; never re-executes or retries."""
    registration = vb.parse_document(read_regular(output / 'registration.json', vb.MAX_BYTES))
    registry, protocol = registration['registry'], registration['protocol']
    run = _empty_run(registry, protocol)
    vb.score(registry, protocol, run, **registration['expected_pins'])
    data = read_regular(output / 'events.jsonl', vb.MAX_BYTES)
    lines = data.splitlines(keepends=True)
    partial_tail = bool(lines and not lines[-1].endswith(b'\n'))
    if partial_tail:
        lines.pop()
    previous = '0' * 64
    starts: set[str] = set()
    terminals: set[str] = set()
    active = None
    observations: dict[str, dict] = {}
    for sequence, line in enumerate(lines):
        record = vb.parse_document(line)
        vb.require(record['sequence'] == sequence and record['previous_sha256'] == previous and
                   record['run_id'] == commitment(registration), 'JOURNAL_CHAIN')
        work_id, index = record['work_id'], record['index']
        vb.require(type(index) is int and 0 <= index < len(protocol['schedule']) and
                   protocol['schedule'][index] == work_id, 'JOURNAL_WORK')
        if record['event'] == 'attempt_started':
            vb.require(active is None and work_id not in starts and index == len(starts), 'JOURNAL_START')
            starts.add(work_id)
            active = work_id
        elif record['event'] == 'output_recorded':
            vb.require(active == work_id and work_id not in observations and
                       record['receipt']['work_id'] == work_id, 'JOURNAL_OUTPUT')
            body = read_regular(output / f'case-{index:04d}.json', MAX_REPORT_BYTES)
            vb.require(sha256(body).hexdigest() == record['artifact_sha256'], 'RECOVERY_ARTIFACT_HASH')
            observations[work_id] = record['receipt']
        elif record['event'] == 'attempt_finished':
            vb.require(active == work_id and work_id in starts and work_id not in terminals and
                       record['receipt']['work_id'] == work_id, 'JOURNAL_TERMINAL')
            artifact = record['artifact_sha256']
            if artifact is not None:
                body = read_regular(output / f'case-{index:04d}.json', MAX_REPORT_BYTES)
                vb.require(sha256(body).hexdigest() == artifact, 'RECOVERY_ARTIFACT_HASH')
            terminals.add(work_id)
            active = None
            run['results'].append(record['receipt'])
        else:
            raise vb.BenchmarkError('JOURNAL_EVENT')
        previous = sha256(line).hexdigest()
    for work_id in sorted(starts - terminals):
        if work_id in observations:
            observed = dict(observations[work_id])
            observed['status'] = 'failed'
            run['results'].append(observed)
    score = vb.score(registry, protocol, run, **registration['expected_pins'])
    completion = 'interrupted'
    marker_path = output / 'finished.json'
    if marker_path.exists():
        marker = vb.parse_document(read_regular(marker_path, vb.MAX_BYTES))
        summary = vb.parse_document(read_regular(output / 'summary.json', vb.MAX_BYTES))
        vb.require(not partial_tail and active is None and len(terminals) == len(protocol['schedule']) and
                   marker['registration_sha256'] == commitment(registration) and
                   marker['journal_tip_sha256'] == previous and
                   marker['summary_sha256'] == commitment(summary) and
                   summary['run'] == run and summary['score'] == score, 'COMPLETION_BINDING')
        completion = 'recorded_finished'
    return {'schema_version': 'rw-jats-recovery.v1', 'status': completion, 'run': run, 'score': score,
            'partial_trailing_record': partial_tail, 'unfinished': sorted(starts - terminals),
            'not_started': [w for w in protocol['schedule'] if w not in starts],
            'reexecuted': False, 'scientific_performance_established': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('identity')
    recover = sub.add_parser('recover')
    recover.add_argument('--run-dir', type=Path, required=True)
    execute = sub.add_parser('run')
    for name in ('registry', 'protocol', 'sources', 'source-root', 'output-dir'):
        execute.add_argument(f'--{name}', type=Path, required=True)
    execute.add_argument('--expected-registry-sha256', required=True)
    execute.add_argument('--expected-protocol-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'identity':
            _files, identity = capture_implementation()
            result = {'implementation_sha256': commitment(identity), 'identity': identity}
        elif args.action == 'recover':
            result = recover_registered(args.run_dir)
        else:
            documents = [vb.parse_document(read_regular(getattr(args, name), vb.MAX_BYTES))
                         for name in ('registry', 'protocol', 'sources')]
            result = run_registered(*documents, args.source_root, args.output_dir,
                                    expected_registry_sha256=args.expected_registry_sha256,
                                    expected_protocol_sha256=args.expected_protocol_sha256)
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        sys.stderr.buffer.write(b'{"status":"invalid","code":"REGISTERED_JATS_RUN_FAILED"}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
