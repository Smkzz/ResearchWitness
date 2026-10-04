"""Offline release qualification for maintainers.

Requires development dependencies already installed. It performs no network fetches.
"""
from __future__ import annotations

import ast
import compileall
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'researchwitness'
BANNED_IMPORT_ROOTS = {'socket', 'urllib', 'http', 'requests', 'subprocess', 'pickle', 'ctypes'}
BANNED_CALLS = {'eval', 'exec', 'compile', '__import__'}


def run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True, env=env)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_core() -> None:
    for path in sorted(CORE.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split('.')[0] for alias in node.names}
                if roots & BANNED_IMPORT_ROOTS:
                    raise RuntimeError(f'banned import in trusted core: {path.name}: {roots & BANNED_IMPORT_ROOTS}')
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split('.')[0]
                if root in BANNED_IMPORT_ROOTS:
                    raise RuntimeError(f'banned import in trusted core: {path.name}: {root}')
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                raise RuntimeError(f'banned dynamic call in trusted core: {path.name}: {node.func.id}')


def main() -> int:
    pyproject = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    version = pyproject['project']['version']
    sys.path.insert(0, str(ROOT))
    from researchwitness import VERSION
    from tools.write_schema import make as make_schema
    from benchmarks.run_synthetic import run as run_synthetic

    if VERSION != version:
        raise RuntimeError(f'version mismatch: package={VERSION} pyproject={version}')
    if json.loads((ROOT / 'schemas/case.schema.json').read_text()) != make_schema():
        raise RuntimeError('generated schema drift')
    if not compileall.compile_dir(CORE, quiet=1):
        raise RuntimeError('compileall failed')
    scan_core()

    tests = run(sys.executable, '-m', 'pytest', '-q')

    with tempfile.TemporaryDirectory(prefix='researchwitness-quality-') as td:
        temp = Path(td)
        bench = run_synthetic(temp / 'evidence')
        if bench['matched'] != bench['case_count']:
            raise RuntimeError('synthetic conformance mismatch')
        real = json.loads(run(sys.executable, 'validation/mvp_real/run_validation.py').stdout)
        if real['matched'] != real['cases']:
            raise RuntimeError('MVP real-paper replay mismatch')

        build_env = dict(os.environ)
        build_env['SOURCE_DATE_EPOCH'] = '1760000000'
        dist = temp / 'dist-a'
        dist2 = temp / 'dist-b'
        dist.mkdir(); dist2.mkdir()
        run(sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '-w', str(dist), env=build_env)
        run(sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '-w', str(dist2), env=build_env)
        wheels = list(dist.glob('researchwitness-*.whl'))
        wheels2 = list(dist2.glob('researchwitness-*.whl'))
        if len(wheels) != 1 or len(wheels2) != 1:
            raise RuntimeError('expected exactly one wheel per build')
        wheel, wheel2 = wheels[0], wheels2[0]
        if wheel.read_bytes() != wheel2.read_bytes():
            raise RuntimeError('wheel build is not reproducible with SOURCE_DATE_EPOCH')
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            if any(name.endswith(('.pyc', '.pyo')) or '/tests/' in name for name in names):
                raise RuntimeError('wheel contains development artifacts')
            if not any(name == 'researchwitness/__main__.py' for name in names):
                raise RuntimeError('wheel missing CLI module')

        env = temp / 'venv'
        venv.EnvBuilder(with_pip=True, clear=True).create(env)
        python = env / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        cli = env / ('Scripts/researchwitness.exe' if sys.platform == 'win32' else 'bin/researchwitness')
        run(str(python), '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel), cwd=temp)
        version_out = run(str(cli), '--version', cwd=temp).stdout.strip()
        if version_out != f'researchwitness {version}':
            raise RuntimeError('installed CLI version mismatch')
        smoke = json.loads(run(str(cli), 'verify', str(ROOT / 'examples/counterexample'),
                               '--as-of', '2026-10-04', cwd=temp).stdout)
        if smoke['decision'] != 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED':
            raise RuntimeError('installed-wheel smoke check failed')
        if smoke['paper_error_established'] or smoke['external_actions'] != 'OUT_OF_SCOPE':
            raise RuntimeError('scope invariant failed in installed wheel')

        summary = {
            'version': version,
            'python': sys.version.split()[0],
            'tests': tests.stdout.strip().splitlines()[-1],
            'synthetic_cases': bench['case_count'],
            'synthetic_matched': bench['matched'],
            'mvp_real_cases': real['cases'],
            'mvp_real_matched': real['matched'],
            'trusted_core_static_scan': 'PASS',
            'schema_drift': 'PASS',
            'compileall': 'PASS',
            'wheel_sha256': sha256(wheel),
            'wheel_reproducible': 'PASS',
            'wheel_install_smoke': 'PASS',
            'runtime_dependencies': pyproject['project'].get('dependencies', []),
        }
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
