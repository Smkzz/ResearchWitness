"""Local synthetic isolation evidence, never a qualification or security-review claim."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

from tools.pdf_percentage_audit import (
    MAX_PDF_BYTES, PDFSourceError, SANDBOX_IMAGE_ENV, _extract_layout_text,
    _sandbox_arguments, _verify_windows_docker_pipe,
)
from tools.pdf_sandbox_smoke import synthetic_pdf


def resource_pdf(*, overflow: bool) -> bytes:
    if overflow:
        pages = 60
        stream = b'BT /F1 2 Tf 10 980 Td\n' + (b'(' + b'A' * 1000 + b') Tj 0 -12 Td\n') * 60 + b'ET\n'
    else:
        pages = 1
        stream = b'0 0 m 1 1 l S\n' * 500_000
    page_ids = list(range(5, 5 + pages))
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [' + b' '.join(f'{i} 0 R'.encode() for i in page_ids)
               + f'] /Count {pages} >>'.encode(),
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'endstream']
    objects.extend([b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 3000 1000] '
                    b'/Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>'] * pages)
    data = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    if len(data) > MAX_PDF_BYTES:
        raise ValueError('Synthetic resource fixture exceeds the production input bound')
    return bytes(data)


def configuration_checks(container: dict, image: str, security: list[str], arguments: list[str]) -> dict[str, bool]:
    host, config = container.get('HostConfig') or {}, container.get('Config') or {}
    limits = {limit['Name']: (limit['Soft'], limit['Hard']) for limit in host.get('Ulimits') or []}
    tmpfs = host.get('Tmpfs') or {}
    options = set(tmpfs.get('/tmp', '').split(','))
    expected_env = [arguments[i + 1] for i, value in enumerate(arguments) if value == '--env']
    cpu = host.get('NanoCpus') == 1_000_000_000 or (
        host.get('CpuPeriod', 0) > 0 and host.get('CpuQuota') == host['CpuPeriod'])
    return {
        'network_none': host.get('NetworkMode') == 'none'
        and set((container.get('NetworkSettings') or {}).get('Networks') or {}) <= {'none'},
        'readonly_root': host.get('ReadonlyRootfs') is True,
        'capabilities_dropped': set(host.get('CapDrop') or []) == {'ALL'},
        'no_new_privileges': bool(set(host.get('SecurityOpt') or [])
                                  & {'no-new-privileges', 'no-new-privileges:true'}),
        'user': config.get('User') == '65534:65534',
        'memory': host.get('Memory') == 512 * 1024 * 1024,
        'memory_swap': host.get('MemorySwap') == 512 * 1024 * 1024,
        'one_cpu': cpu,
        'pids': host.get('PidsLimit') == 8,
        'ulimits': limits == {'cpu': (20, 20), 'fsize': (2097152, 2097152),
                             'nofile': (64, 64), 'core': (0, 0)},
        'tmpfs': set(tmpfs) == {'/tmp'} and {'nosuid', 'nodev', 'noexec'} <= options
        and bool(options & {'size=32m', 'size=32768k', 'size=33554432'})
        and 'ro' not in options,
        'no_mounts_or_binds': not container.get('Mounts') and not host.get('Binds')
        and not host.get('Mounts'),
        'environment': sorted(config.get('Env') or []) == sorted(expected_env),
        'image_pin': container.get('Image') == image,
        'default_seccomp': 'name=seccomp,profile=builtin' in security,
        'not_started': (container.get('State') or {}).get('Status') == 'created'
        and (container.get('State') or {}).get('Running') is False,
    }


class Evidence:
    def __init__(self, output: Path):
        self.output = output
        self.commands: list[dict] = []
        self.checks: list[dict] = []

    def run(self, command: list[str], *, env: dict | None = None) -> str:
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=60, shell=False, check=False)
        record = {'command': command, 'stdout': result.stdout, 'stderr': result.stderr,
                  'exit_code': result.returncode}
        self.commands.append(record)
        with self.output.with_suffix('.log').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write('$ ' + subprocess.list2cmdline(command) + '\n' + result.stdout
                         + result.stderr + f'\nEXIT CODE: {result.returncode}\n')
        if result.returncode:
            raise RuntimeError(f'Command failed: {command!r}: {result.stderr}')
        return result.stdout

    def check(self, name: str, passed: bool, **raw) -> None:
        self.checks.append({'check': name, 'passed': passed, **raw})
        if self.output.with_suffix('.log').exists():
            with self.output.with_suffix('.log').open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(self.checks[-1]) + '\n')
        if not passed:
            raise RuntimeError(f'Isolation evidence check failed: {name}')


def collect(evidence: Evidence, image: str, directory: Path) -> None:
    docker = shutil.which('docker')
    if not docker:
        raise RuntimeError('Docker unavailable')
    if sys.platform == 'win32':
        _verify_windows_docker_pipe()
    host = 'npipe:////./pipe/docker_engine' if sys.platform == 'win32' else 'unix:///var/run/docker.sock'
    config_dir = directory / 'config'
    config_dir.mkdir()
    prefix = [docker, '--host', host, '--config', str(config_dir)]
    env = {'PATH': os.defpath, 'LANG': 'C', 'LC_ALL': 'C'}

    def command(*args: str) -> str:
        return evidence.run([*prefix, *args], env=env)

    def containers() -> list[str]:
        return command('container', 'ls', '--all', '--quiet', '--no-trunc',
                       '--filter', f'ancestor={image}').split()

    def absent(cid: str) -> bool:
        return not command('container', 'ls', '--all', '--quiet', '--no-trunc',
                           '--filter', f'id={cid}').strip()

    evidence.run(['git', 'rev-parse', 'HEAD'])
    evidence.run([sys.executable, '-VV'])
    command('version')
    security = json.loads(command('info', '--format', '{{json .SecurityOptions}}'))
    evidence.check('initial_container_absence', containers() == [])
    cidfile = directory / 'inspection-cid'
    arguments = _sandbox_arguments(image, cidfile)
    cid = ''
    try:
        cid = command('create', *arguments).strip()
        evidence.check('created_cid', bool(re.fullmatch('[0-9a-f]{64}', cid)), cid=cid)
        raw = command('container', 'inspect', cid)
        evidence.output.with_name(evidence.output.stem + '-container-inspect.json').write_text(
            raw, encoding='utf-8', newline='\n')
        container = json.loads(raw)[0]
        for name, passed in configuration_checks(container, image, security, arguments).items():
            evidence.check(name, passed)
    finally:
        if re.fullmatch('[0-9a-f]{64}', cid):
            command('container', 'rm', '--force', cid)
            evidence.check('inspection_cleanup', absent(cid) and containers() == [], cid=cid)

    fixtures = [('success', synthetic_pdf(['Synthetic cleanup evidence']), None, 20),
                ('malformed', b'%PDF-1.4\ninvalid synthetic fixture\n',
                 'Isolated Poppler could not extract this PDF', 20),
                ('timeout', resource_pdf(overflow=False),
                 'Isolated Poppler exceeded the 0.5-second extraction limit', 0.5),
                ('output_overflow', resource_pdf(overflow=True),
                 'Isolated Poppler output exceeds the 2 MiB limit', 20)]
    for name, data, expected, timeout in fixtures:
        before = containers()
        evidence.check(f'{name}_before', before == [], containers=before)
        run_cid = directory / f'{name}-cid'
        started = time.monotonic()
        error = None
        text = ''
        try:
            text = _extract_layout_text(data, _timeout=timeout, _cidfile=run_cid)
        except PDFSourceError as exc:
            error = str(exc)
        finally:
            after = containers()
            recorded_cid = run_cid.read_text().strip() if run_cid.exists() else ''
            evidence.check(f'{name}_cleanup', before == after == []
                           and bool(re.fullmatch('[0-9a-f]{64}', recorded_cid)) and absent(recorded_cid),
                           before=before, after=after, cid=recorded_cid)
        evidence.check(name, error == expected and (expected is not None or bool(text.strip())),
                       error=error, expected_error=expected, seconds=time.monotonic() - started,
                       source_sha256=hashlib.sha256(data).hexdigest(), source_bytes=len(data),
                       timeout=timeout, production_arguments=_sandbox_arguments(image, run_cid),
                       returned_text=text,
                       returned_text_sha256=hashlib.sha256(text.encode()).hexdigest() if text else None)

    output = evidence.run([sys.executable, '-m', 'pytest', '-q',
                           'tests/test_pdf_percentage_audit_unittest.py', '-k',
                           'cleanup_failure or timeout_removes or output_overflow'])
    evidence.check('mocked_cleanup_failure_regressions', True, output=output,
                   evidence_kind='mocked; not real cleanup-denial enforcement')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    image = os.environ.get(SANDBOX_IMAGE_ENV, '')
    if not re.fullmatch('sha256:[0-9a-f]{64}', image):
        parser.error('Set the exact local image ID in ' + SANDBOX_IMAGE_ENV)
    if args.output.exists() or args.output.with_suffix('.log').exists():
        parser.error('Refusing to overwrite evidence')
    header = {'utc': datetime.now(timezone.utc).isoformat(), 'os': platform.platform(), 'image_id': image}
    args.output.with_suffix('.log').write_text(json.dumps(header) + '\n', encoding='utf-8', newline='\n')
    evidence = Evidence(args.output)
    error = None
    try:
        with tempfile.TemporaryDirectory(prefix='rw03-isolation-') as directory:
            collect(evidence, image, Path(directory))
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError,
            subprocess.SubprocessError, PDFSourceError) as exc:
        error = str(exc)
    report = {**header, 'status': 'evidence_recorded_not_qualified' if error is None else 'blocked_or_failed',
              'sandbox_qualified': False, 'error': error, 'checks': evidence.checks,
              'commands': evidence.commands,
              'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                                [Path(__file__), Path(__file__).with_name('pdf_percentage_audit.py')]}}
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    with args.output.with_suffix('.log').open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(f'HARNESS EXIT CODE: {0 if error is None else 2}\n')
    print(json.dumps(report, indent=2))
    return 0 if error is None else 2


if __name__ == '__main__':
    raise SystemExit(main())
