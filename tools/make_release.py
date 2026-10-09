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
    '.editorconfig', '.gitignore', 'CHANGELOG.md', 'CITATION.cff',
    'CODE_OF_CONDUCT.md', 'CONTRIBUTING.md', 'LICENSE', 'NOTICE.md',
    'README.md', 'SECURITY.md', 'SUPPORT.md', 'pyproject.toml', 'CHECKSUMS.sha256',
}
TOP_DIRS = {'.github', 'researchwitness', 'schemas', 'examples', 'benchmarks', 'prompts'}
# These directories can also hold owner-only or paper-specific qualification
# material. Source artifacts therefore include reviewed documentation and
# maintainer utilities by path, not every tracked file under those roots.
RELEASE_DOCS = {
    'docs/ARCHITECTURE.md', 'docs/EXPRESSION_DSL.md',
    'docs/MVP.md', 'docs/PAPER_AUDIT_CAPABILITIES.md', 'docs/PROTOCOL.md',
    'docs/RELEASING.md', 'docs/ROADMAP.md',
}
RELEASE_TOOLS = {
    'tools/make_examples.py', 'tools/make_release.py',
    'tools/make_timeline_example.py', 'tools/qualify_app_wheel.py',
    'tools/write_schema.py',
}
EXCLUDED_PARTS = {'.git', '.pytest_cache', '__pycache__', 'build', 'dist', 'researchwitness.egg-info'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo'}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise RuntimeError(f'release file unavailable: {path.name}') from exc
    if (os.path.islink(path) or getattr(info, 'st_file_attributes', 0) & 0x400
            or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise RuntimeError(f'unsafe release file: {path.name}')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f'cannot safely open release file: {path.name}') from exc
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
            raise RuntimeError(f'release file changed during validation: {path.name}')
        digest = hashlib.sha256()
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        after = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise RuntimeError(f'release file changed while hashing: {path.name}')
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _read_tracked_file(path: Path) -> bytes:
    _validate_release_path(path)
    relative = path.relative_to(ROOT)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    directory_flags = flags | getattr(os, 'O_DIRECTORY', 0)
    descriptor = None
    info = None
    try:
        if (os.open in os.supports_dir_fd and hasattr(os, 'O_DIRECTORY')
                and hasattr(os, 'O_NOFOLLOW')):
            # Anchor the read at directory handles so replacing a validated
            # parent with a symlink cannot redirect the final open.
            directory = os.open(ROOT, directory_flags)
            try:
                for part in relative.parts[:-1]:
                    child = os.open(part, directory_flags, dir_fd=directory)
                    os.close(directory)
                    directory = child
                descriptor = os.open(relative.parts[-1], flags, dir_fd=directory)
            finally:
                os.close(directory)
        else:
            # Windows does not expose dir_fd/O_NOFOLLOW through Python. Keep
            # its reparse-point component check and verify the opened leaf.
            info = os.lstat(path)
            descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f'cannot safely open tracked release file: {path.name}') from exc
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (info is not None
                    and (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino))):
            raise RuntimeError(f'tracked release file changed during validation: {path.name}')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            data = stream.read()
        after = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise RuntimeError(f'tracked release file changed while reading: {path.name}')
        return data
    finally:
        os.close(descriptor)


def _validate_release_path(path: Path) -> None:
    try:
        relative = path.relative_to(ROOT)
    except ValueError as exc:
        raise RuntimeError('release input escaped the repository root') from exc
    current = ROOT
    try:
        root_info = os.lstat(current)
        if os.path.islink(current) or getattr(root_info, 'st_file_attributes', 0) & 0x400:
            raise RuntimeError('repository root cannot be a link')
        for index, part in enumerate(relative.parts):
            current = current / part
            info = os.lstat(current)
            is_reparse = bool(getattr(info, 'st_file_attributes', 0) & 0x400)
            if os.path.islink(current) or is_reparse:
                raise RuntimeError(f'unsafe release input path: {relative.as_posix()}')
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise RuntimeError(f'unsafe release input parent: {relative.as_posix()}')
    except OSError as exc:
        raise RuntimeError(f'release input unavailable: {relative.as_posix()}') from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RuntimeError(f'unsafe release input: {relative.as_posix()}')


def _tracked_paths() -> list[Path]:
    result = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-z', '--cached'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise RuntimeError('cannot enumerate tracked release files')
    paths = []
    for raw in result.stdout.split(b'\0'):
        if not raw:
            continue
        rel = Path(os.fsdecode(raw))
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if rel.suffix in EXCLUDED_SUFFIXES or rel.name == '.coverage':
            continue
        if len(rel.parts) == 1:
            if rel.name not in TOP_FILES:
                continue
        elif rel.parts[0] in {'docs', 'tools'}:
            if rel.as_posix() not in RELEASE_DOCS | RELEASE_TOOLS:
                continue
        elif rel.parts[0] not in TOP_DIRS:
            continue
        path = ROOT / rel
        _validate_release_path(path)
        paths.append(path)
    return sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix())


def included_files(include_checksums: bool = True) -> list[Path]:
    files = _tracked_paths()
    if not include_checksums:
        files = [path for path in files if path.relative_to(ROOT).as_posix() != 'CHECKSUMS.sha256']
    return files


def checksum_files() -> list[Path]:
    return included_files(include_checksums=False)


def write_checksums() -> None:
    lines = []
    for path in checksum_files():
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f'{sha256_bytes(_read_tracked_file(path))}  {rel}')
    (ROOT / 'CHECKSUMS.sha256').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_source_zip(destination: Path, version: str) -> None:
    prefix = f'researchwitness-{version}/'
    with destination.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            for path in included_files():
                rel = path.relative_to(ROOT).as_posix()
                info = zipfile.ZipInfo(prefix + rel, date_time=FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, _read_tracked_file(path))


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
    status = subprocess.run(
        ['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if status.returncode or status.stdout:
        raise RuntimeError(
            'release artifacts require a committed source tree; '
            'the checksum manifest was regenerated if tracked inputs had changed'
        )
    names = {
        'source': f'ResearchWitness-v{version}-source.zip',
        'wheel': f'researchwitness-{version}-py3-none-any.whl',
        'manifest': f'ResearchWitness-v{version}-release.json',
        'sums': f'ResearchWitness-v{version}-SHA256SUMS.txt',
    }
    destinations = {key: out / name for key, name in names.items()}
    for path in destinations.values():
        if path.exists() or path.is_symlink():
            info = os.lstat(path)
            if (os.path.islink(path) or getattr(info, 'st_file_attributes', 0) & 0x400
                    or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise RuntimeError(f'unsafe existing release destination: {path.name}')

    with tempfile.TemporaryDirectory(prefix='.researchwitness-release-', dir=out) as staging_name:
        staging = Path(staging_name)
        source = staging / names['source']
        wheel_target = staging / names['wheel']
        manifest_path = staging / names['manifest']
        sums = staging / names['sums']
        write_source_zip(source, version)
        with tempfile.TemporaryDirectory(prefix='researchwitness-wheel-') as td:
            built = build_wheel(Path(td))
            shutil.copyfile(built, wheel_target)
        cleanup_build_artifacts()

        manifest = {
            'version': version,
            'source': {'file': source.name, 'sha256': sha256_file(source), 'bytes': source.stat().st_size},
            'wheel': {'file': wheel_target.name, 'sha256': sha256_file(wheel_target), 'bytes': wheel_target.stat().st_size},
            'source_file_count': len(included_files()),
            'source_date_epoch': SOURCE_DATE_EPOCH,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        sums.write_text(
            f"{manifest['source']['sha256']}  {source.name}\n"
            f"{manifest['wheel']['sha256']}  {wheel_target.name}\n"
            f"{sha256_file(manifest_path)}  {manifest_path.name}\n",
            encoding='utf-8',
        )
        for key, staged in (
            ('source', source), ('wheel', wheel_target),
            ('manifest', manifest_path), ('sums', sums),
        ):
            os.replace(staged, destinations[key])
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
