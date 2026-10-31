"""Create deterministic ResearchWitness source and wheel release artifacts offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
SOURCE_DATE_EPOCH = '1760000000'
TOP_FILES = {
    '.editorconfig', '.gitattributes', '.gitignore', 'AGENTS.md', 'CLAUDE.md',
    'CHANGELOG.md', 'CITATION.cff',
    'CODE_OF_CONDUCT.md', 'CONTRIBUTING.md', 'LICENSE', 'NOTICE.md',
    'README.md', 'SECURITY.md', 'SUPPORT.md', 'pyproject.toml', 'CHECKSUMS.sha256',
    'RESEARCHWITNESS_NEXT_CAMPAIGN_REPORT.md',
}
TOP_DIRS = {'.github', 'researchwitness', 'schemas', 'examples', 'benchmarks', 'prompts', 'tests', 'tools', 'docs', 'evidence', 'validation'}
EXCLUDED_PARTS = {'.git', '.pytest_cache', '__pycache__', 'build', 'dist', 'researchwitness.egg-info'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo'}
EXCLUDED_REL_PATHS = {'evidence/synthetic-scenarios.jsonl', 'evidence/synthetic-summary.json'}
WINDOWS_RESERVED_BASENAMES = {
    'aux', 'con', 'conin$', 'conout$', 'nul', 'prn',
    *(f'com{digit}' for digit in '123456789¹²³'),
    *(f'lpt{digit}' for digit in '123456789¹²³'),
}


def _portable_archive_path_key(relative_path: str) -> str:
    """Validate an ASCII Git path for safe, unambiguous cross-platform extraction."""
    def invalid(reason: str) -> RuntimeError:
        return RuntimeError(f'Refusing non-portable release path ({reason}): {relative_path!r}')

    if not relative_path or relative_path.startswith('/'):
        raise invalid('path must be relative')
    if '\\' in relative_path:
        raise invalid('backslash is not a portable archive separator')
    if not relative_path.isascii():
        raise invalid('non-ASCII names have platform-dependent case equivalence')

    parts = relative_path.split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise invalid('empty or traversal component')
    for part in parts:
        if part.endswith(('.', ' ')):
            raise invalid('component ends in a dot or space')
        if any(ord(char) < 32 or char in '<>:"|?*' for char in part):
            raise invalid('component contains a Windows-unsafe character')
        basename = part.split('.', 1)[0].rstrip(' .').casefold()
        if basename in WINDOWS_RESERVED_BASENAMES:
            raise invalid('component uses a reserved Windows device name')

    return relative_path.casefold()


def _register_archive_path(
    relative_path: str,
    archive_path_keys: dict[str, str],
    archive_directory_keys: dict[str, str],
) -> None:
    """Reject case-folded collisions and file/directory conflicts before filesystem access."""
    path_key = _portable_archive_path_key(relative_path)
    path_parts = path_key.split('/')
    file_ancestor = next(
        (
            archive_path_keys['/'.join(path_parts[:index])]
            for index in range(1, len(path_parts))
            if '/'.join(path_parts[:index]) in archive_path_keys
        ),
        None,
    )
    if file_ancestor is not None:
        raise RuntimeError(
            f'Refusing release file/directory path conflict: '
            f'{file_ancestor!r} and {relative_path!r}'
        )
    previous = archive_path_keys.get(path_key)
    if previous is not None:
        raise RuntimeError(
            f'Refusing colliding release paths on case-insensitive filesystems: '
            f'{previous!r} and {relative_path!r}'
        )
    descendant = archive_directory_keys.get(path_key)
    if descendant is not None:
        raise RuntimeError(
            f'Refusing release file/directory path conflict: '
            f'{relative_path!r} and {descendant!r}'
        )
    archive_path_keys[path_key] = relative_path
    for index in range(1, len(path_parts)):
        archive_directory_keys.setdefault('/'.join(path_parts[:index]), relative_path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def included_files(include_checksums: bool = True) -> list[Path]:
    files: list[Path] = []
    archive_path_keys: dict[str, str] = {}
    archive_directory_keys: dict[str, str] = {}
    indexed = subprocess.run(
        ['git', 'ls-files', '--stage', '-z'],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    unstaged = set(subprocess.run(
        ['git', 'diff', '--name-only', '-z'],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.split(b'\0'))
    selected_entries: list[tuple[str, bytes, bytes, bytes, list[str]]] = []
    for entry in indexed.split(b'\0'):
        if not entry:
            continue
        metadata, raw_path = entry.split(b'\t', 1)
        mode, _object_id, stage = metadata.split()
        try:
            relative_path = raw_path.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise RuntimeError('Refusing a release path that is not valid UTF-8') from exc
        parts = relative_path.split('/')
        if any(part in EXCLUDED_PARTS for part in parts):
            continue
        if Path(parts[-1]).suffix in EXCLUDED_SUFFIXES or parts[-1] == '.coverage':
            continue
        if relative_path in EXCLUDED_REL_PATHS:
            continue
        if len(parts) == 1:
            if parts[0] not in TOP_FILES:
                continue
        elif parts[0] not in TOP_DIRS:
            continue
        if not include_checksums and relative_path == 'CHECKSUMS.sha256':
            continue
        _register_archive_path(relative_path, archive_path_keys, archive_directory_keys)

        selected_entries.append((relative_path, raw_path, mode, stage, parts))

    # Validate the complete path inventory before touching the filesystem. This makes
    # collision checks deterministic even on case-insensitive checkout filesystems.
    for relative_path, raw_path, mode, stage, parts in selected_entries:
        if raw_path in unstaged and relative_path != 'CHECKSUMS.sha256':
            raise RuntimeError(f'Refusing to package unstaged changes: {relative_path}')
        if stage != b'0':
            raise RuntimeError(f'Cannot package an unmerged Git index entry: {relative_path}')
        if mode == b'120000':
            raise RuntimeError(f'Refusing to package a symbolic link: {relative_path}')
        if mode not in {b'100644', b'100755'}:
            raise RuntimeError(f'Refusing non-regular indexed release file: {relative_path}')
        rel = Path(*parts)
        path = ROOT / rel
        current = ROOT
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError(f'Refusing a release path through a symbolic link: {relative_path}')
        try:
            file_stat = path.stat()
        except FileNotFoundError as exc:
            raise RuntimeError(f'Missing indexed release file: {relative_path}') from exc
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeError(f'Refusing non-regular release file: {rel.as_posix()}')
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def write_checksums() -> None:
    lines = []
    for path in included_files(include_checksums=False):
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f'{sha256_file(path)}  {rel}')
    (ROOT / 'CHECKSUMS.sha256').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_source_zip(destination: Path, version: str) -> None:
    archive_root = f'researchwitness-{version}'
    _portable_archive_path_key(archive_root)
    selected_files = included_files()
    archive_members = [
        (path, f'{archive_root}/{path.relative_to(ROOT).as_posix()}')
        for path in selected_files
    ]
    for _path, member in archive_members:
        _portable_archive_path_key(member)
    with destination.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            for path, member in archive_members:
                info = zipfile.ZipInfo(member, date_time=FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


def build_wheel(destination_dir: Path) -> Path:
    env = dict(os.environ)
    env['SOURCE_DATE_EPOCH'] = SOURCE_DATE_EPOCH
    subprocess.run(
        [sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '-w', str(destination_dir)],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wheels = list(destination_dir.glob('researchwitness-*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Expected exactly one ResearchWitness wheel')
    return wheels[0]


def cleanup_build_artifacts() -> None:
    for path in (ROOT / 'build', ROOT / 'researchwitness.egg-info'):
        if path.exists():
            shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    import tomllib
    meta = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    version = meta['project']['version']

    write_checksums()
    source = out / f'ResearchWitness-v{version}-source.zip'
    wheel_target = out / f'researchwitness-{version}-py3-none-any.whl'
    for path in (source, wheel_target):
        if path.exists():
            path.unlink()

    write_source_zip(source, version)
    with tempfile.TemporaryDirectory(prefix='researchwitness-wheel-') as td:
        built = build_wheel(Path(td))
        shutil.copy2(built, wheel_target)
    cleanup_build_artifacts()

    manifest = {
        'version': version,
        'source': {'file': source.name, 'sha256': sha256_file(source), 'bytes': source.stat().st_size},
        'wheel': {'file': wheel_target.name, 'sha256': sha256_file(wheel_target), 'bytes': wheel_target.stat().st_size},
        'source_file_count': len(included_files()),
        'source_date_epoch': SOURCE_DATE_EPOCH,
    }
    manifest_path = out / f'ResearchWitness-v{version}-release.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    sums = out / f'ResearchWitness-v{version}-SHA256SUMS.txt'
    sums.write_text(
        f"{manifest['source']['sha256']}  {source.name}\n"
        f"{manifest['wheel']['sha256']}  {wheel_target.name}\n"
        f"{sha256_file(manifest_path)}  {manifest_path.name}\n",
        encoding='utf-8',
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
