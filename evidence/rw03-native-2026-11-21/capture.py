import concurrent.futures
import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).parent
PYTHON = sys.executable
DOCKER = shutil.which('docker')


def run(log, cwd, args, env):
    log.write('\nCOMMAND: ' + subprocess.list2cmdline(args) + '\n')
    log.flush()
    result = subprocess.run(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    log.write(f'EXIT CODE: {result.returncode}\n')
    log.flush()
    return result.returncode


def capture(name, cwd, commands, pdf=False):
    env = dict(os.environ, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               COVERAGE_FILE=str(ROOT / (name + '.coverage')))
    with (ROOT / (name + '.log')).open('x', encoding='utf-8') as log:
        log.write('UTC: ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + '\n')
        run(log, cwd, ['git', 'rev-parse', 'HEAD'], env)
        run(log, cwd, ['powershell', '-NoProfile', '-Command',
            'Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber | Format-List'], env)
        run(log, cwd, ['cmd', '/c', 'ver'], env)
        run(log, cwd, [PYTHON, '-VV'], env)
        if pdf:
            run(log, cwd, [DOCKER, '--host', 'npipe:////./pipe/docker_engine', 'version'], env)
            run(log, cwd, [DOCKER, '--host', 'npipe:////./pipe/docker_engine', 'info', '--format', '{{json .SecurityOptions}}'], env)
        log.write('\nEVIDENCE COMMANDS\n')
        for args, extra in commands:
            run(log, cwd, args, dict(env, **extra))
    print(name + ': complete', flush=True)


def release():
    return [([PYTHON, *args], {}) for args in [
        ['-m', 'ruff', 'check', '.'],
        ['-m', 'coverage', 'run', '-m', 'pytest', '-q'],
        ['-m', 'coverage', 'report'],
        ['-m', 'coverage', 'report', '--include=researchwitness/*.py', '--fail-under=90'],
        ['benchmarks/run_synthetic.py'],
        ['validation/mvp_real/run_validation.py'],
        ['tools/quality_gate.py'],
    ]]


def windows():
    cwd = r'C:\Users\Administrator\repos\rw03-main-evidence'
    capture('windows-focused', cwd, [([PYTHON, '-m', 'pytest',
        'tests/test_windows_rate_security.py', 'tests/test_offline_file_boundary_unittest.py',
        '-k', 'WindowsRateSecurityTests or rate_state', '-v', '-rs'], {})])
    capture('windows-release', cwd, release())


def pdf():
    cwd = r'C:\Users\Administrator\repos\ResearchWitness'
    minimal = """import os, shutil, subprocess, tempfile
docker = shutil.which('docker')
with tempfile.TemporaryDirectory(prefix='rw03-evidence-empty-config-') as config:
    env = {'PATH': os.defpath, 'LANG': 'C', 'LC_ALL': 'C'}
    command = [docker, '--host', 'npipe:////./pipe/docker_engine', '--config', config, 'info', '--format', '{{json .SecurityOptions}}']
    print('Empty config contents:', os.listdir(config), flush=True)
    print('Child environment:', env, flush=True)
    print('Child command:', command, flush=True)
    result = subprocess.run(command, env=env, check=False)
    print('Child exit code:', result.returncode, flush=True)
    raise SystemExit(result.returncode)
"""
    capture('pdf-focused', cwd, [([PYTHON, '-m', 'pytest',
        'tests/test_pdf_percentage_audit_unittest.py', '-v', '-rs'], {})], True)
    capture('pdf-runtime', cwd, [
        ([PYTHON, '-c', minimal], {}),
        ([PYTHON, '-m', 'tools.pdf_sandbox_smoke', '--output', str(ROOT / 'pdf-smoke.json')],
         {'RESEARCHWITNESS_PDF_SANDBOX_IMAGE': 'sha256:' + '0' * 64}),
        ([PYTHON, '-c', "from pathlib import Path; print(Path(r'" + str(ROOT / 'pdf-smoke.json') + "').read_text())"], {}),
        ([DOCKER, '--host', 'npipe:////./pipe/docker_engine', 'ps', '-a'], {}),
        ([DOCKER, '--host', 'npipe:////./pipe/docker_engine', 'images'], {}),
    ], True)
    capture('pdf-release', cwd, release(), True)


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(windows), pool.submit(pdf)]
        for future in futures:
            future.result()
