"""Run the frozen ResearchWitness paper-audit CLI on source-only inputs.

The input manifest is deliberately narrow: it may describe source captures,
but cannot carry roles, labels, corrections, or expected outcomes. Each source
is screened twice in separate temporary directories. The final output retains
only the two reports and a metadata record for each input; LOCK.json is written
last and records the SHA-256 of every retained file and of the source manifest.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import PackageNotFoundError, version as installed_version
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from researchwitness import VERSION  # noqa: E402
from tools.render_pmc_jats import RENDERER_VERSION, render  # noqa: E402


FROZEN_COMMIT = '3042b3d62b8f20cc646b0c121dff376bfdd201cb'
FROZEN_TREE = 'a19c53c2c2e6c400ee8b0d7feb0d0261f0cf009f'
PAPER_AUDIT_SCHEMA_VERSION = '0.2'
FROZEN_PACKAGE_VERSION = '0.4.0.dev0'
FROZEN_FILE_HASHES = {
    'researchwitness/paper_audit.py': '82286f5fdbfd63338a9df94eb537c9245860b8b610d656be2b7f47a910c64138',
    'researchwitness/_pdf_worker.py': 'd9ef80daae1f16ffd9ed052a2732d5362a6f76c9d79860415ff0a65386307775',
    'researchwitness/__main__.py': '679bbd0be925ebad174ea53fd80b681594fc6faf82e1b12ba77473c6c141aaa8',
    'researchwitness/strict.py': 'e3d3c4424df0b8326f09209ebdc7e3eee6c598cc12819a2d20dedcae5db00690',
    'researchwitness/capsule.py': '6cf2dfd889972014473be2e769653ad32195f814c9b338cf98a389ee9b106339',
    'pyproject.toml': '7dc1fa7a5bfa8259b6e92f24818503cd33101677524f5305ebda3213068a0ed1',
    'schemas/paper-audit.schema.json': '01b4a356835c2e77d6bd255daf6a1e309dd5d642a4e8e5dc7a02ca409b31bd28',
    'researchwitness/schemas/paper-audit.schema.json': '01b4a356835c2e77d6bd255daf6a1e309dd5d642a4e8e5dc7a02ca409b31bd28',
}
RENDERER_SHA256 = '4cc3e37323a8b7b86139a55d72a5c1adf6d0c0c54f624cbf4ee5baaa77870a13'
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
TOP_LEVEL_KEYS = {'renderer', 'papers'}
PAPER_KEYS = {'paper_id', 'source'}
SOURCE_KEYS = {
    'source_kind', 'snapshot_name', 'source_url', 'retrieved_at', 'sha256',
    'source_version', 'license',
}
SOURCE_SUFFIXES = {
    'jats_xml': '.md',
    'text': '.txt',
    'markdown': '.md',
    'pdf': '.pdf',
}


def _installed_pypdf_version() -> str | None:
    try:
        return installed_version('pypdf')
    except PackageNotFoundError:
        return None


EXECUTION_ENVIRONMENT = {
    'python_version': sys.version.split()[0],
    'platform': platform.platform(),
    'pypdf_version': _installed_pypdf_version(),
}


class BlindRunError(ValueError):
    """Raised when source-only inputs or frozen-baseline checks fail."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BlindRunError('Manifest contains a duplicate JSON key')
        result[key] = value
    return result


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise BlindRunError(f'Manifest {label} has an invalid source-only shape')
    return value


def _nonempty_string(value: Any, label: str, limit: int = 4000) -> str:
    if type(value) is not str or not value or len(value) > limit:
        raise BlindRunError(f'Manifest {label} must be a bounded nonempty string')
    if any(ord(character) < 32 and character not in '\n\t' for character in value):
        raise BlindRunError(f'Manifest {label} contains a control character')
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise BlindRunError(f'Manifest {label} contains an invalid Unicode surrogate')
    return value


def _load_source_manifest(manifest_path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise BlindRunError('Cannot read source-only manifest') from exc
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise BlindRunError('Source-only manifest exceeds the size limit')
    try:
        document = json.loads(manifest_bytes.decode('utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindRunError('Source-only manifest must be UTF-8 JSON') from exc

    top = _exact_keys(document, TOP_LEVEL_KEYS, 'top level')
    if top['renderer'] != RENDERER_VERSION:
        raise BlindRunError('Source-only manifest declares an unsupported renderer version')
    papers = top['papers']
    if type(papers) is not list or not papers:
        raise BlindRunError('Source-only manifest must contain at least one paper')

    seen_paper_ids: set[str] = set()
    for index, raw_paper in enumerate(papers, start=1):
        paper = _exact_keys(raw_paper, PAPER_KEYS, f'paper {index}')
        paper_id = _nonempty_string(paper['paper_id'], f'paper {index} identifier', 32)
        if re.fullmatch(r'paper-[0-9]{3}', paper_id) is None:
            raise BlindRunError(f'Manifest paper {index} identifier is not an opaque path-safe token')
        if paper_id in seen_paper_ids:
            raise BlindRunError(f'Manifest paper {index} has a duplicate identifier')
        seen_paper_ids.add(paper_id)
        source = _exact_keys(paper['source'], SOURCE_KEYS, f'paper {index} source')
        kind = _nonempty_string(source['source_kind'], f'case {index} source kind', 40)
        if kind not in SOURCE_SUFFIXES:
            raise BlindRunError(f'Manifest paper {index} uses an unsupported source kind')
        _nonempty_string(source['snapshot_name'], f'paper {index} source path', 1000)
        _nonempty_string(source['source_url'], f'paper {index} source URL', 4000)
        _nonempty_string(source['retrieved_at'], f'paper {index} retrieval date', 100)
        _nonempty_string(source['source_version'], f'paper {index} source version', 2000)
        _nonempty_string(source['license'], f'paper {index} license/access note', 2000)
        digest = source['sha256']
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise BlindRunError(f'Manifest paper {index} has an invalid source SHA-256')
    return top, manifest_bytes


def _resolve_snapshot(source_root: Path, snapshot_name: str, index: int) -> Path:
    if '\\' in snapshot_name or '\x00' in snapshot_name:
        raise BlindRunError(f'Manifest case {index} has an unsafe source path')
    relative = PurePosixPath(snapshot_name)
    if relative.is_absolute() or not relative.parts or any(part in ('', '.', '..') for part in relative.parts):
        raise BlindRunError(f'Manifest case {index} has an unsafe source path')
    path = source_root.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(source_root)
    except (OSError, ValueError) as exc:
        raise BlindRunError(f'Manifest case {index} source is missing or outside the source directory') from exc
    if not resolved.is_file():
        raise BlindRunError(f'Manifest case {index} source is not a regular file')
    return resolved


def _verify_frozen_detector() -> None:
    if VERSION != FROZEN_PACKAGE_VERSION:
        raise BlindRunError('Installed ResearchWitness package version does not match the frozen baseline')
    if RENDERER_VERSION != 'jats-markdown-v1':
        raise BlindRunError('JATS renderer version does not match the source manifest protocol')
    if _sha256_file(ROOT / 'tools/render_pmc_jats.py') != RENDERER_SHA256:
        raise BlindRunError('JATS renderer code does not match the wave baseline')
    for relative_name, expected_hash in FROZEN_FILE_HASHES.items():
        path = ROOT / relative_name
        if not path.is_file() or _sha256_file(path) != expected_hash:
            raise BlindRunError('ResearchWitness detector files differ from the frozen baseline')
    try:
        completed = subprocess.run(
            ['git', 'rev-parse', f'{FROZEN_COMMIT}^{{tree}}'], cwd=ROOT,
            text=True, capture_output=True, check=False,
        )
    except OSError as exc:
        raise BlindRunError('Cannot verify the frozen baseline commit') from exc
    if completed.returncode != 0 or completed.stdout.strip() != FROZEN_TREE:
        raise BlindRunError('Frozen baseline commit or tree is unavailable')


def _run_cli(
    source_bytes: bytes,
    suffix: str,
    output_root: Path,
    opaque_identifier: str,
    opaque_source_version: str,
) -> dict[str, Any]:
    input_path = output_root.parent / ('source' + suffix)
    input_path.write_bytes(source_bytes)
    command = [
        sys.executable, '-m', 'researchwitness', 'paper-audit', str(input_path),
        '--identifier', opaque_identifier,
        '--source-version', opaque_source_version,
        '--output', str(output_root),
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, cwd=ROOT, text=True, encoding='utf-8', errors='strict',
            capture_output=True, check=False,
        )
    except (OSError, UnicodeError) as exc:
        raise BlindRunError('Frozen ResearchWitness CLI could not be started') from exc
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise BlindRunError(f'Frozen ResearchWitness CLI failed with exit code {completed.returncode}')
    try:
        cli_result = json.loads(completed.stdout)
        report_bytes = (output_root / 'report.json').read_bytes()
        html_bytes = (output_root / 'report.html').read_bytes()
        report = json.loads(report_bytes.decode('utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindRunError('Frozen ResearchWitness CLI returned an incomplete report') from exc
    if type(cli_result) is not dict or type(report) is not dict:
        raise BlindRunError('Frozen ResearchWitness CLI returned an invalid report shape')
    if report.get('paper_audit_version') != PAPER_AUDIT_SCHEMA_VERSION:
        raise BlindRunError('Frozen ResearchWitness report schema version changed')
    if report.get('source', {}).get('identifier') != opaque_identifier:
        raise BlindRunError('Frozen ResearchWitness report identifier did not match the opaque run identifier')
    if report.get('source', {}).get('version') != opaque_source_version:
        raise BlindRunError('Frozen ResearchWitness report source version did not match the opaque version')
    if report.get('source', {}).get('sha256') != sha256(source_bytes):
        raise BlindRunError('Frozen ResearchWitness report source hash did not match the staged input')
    candidates = report.get('candidate_anomalies')
    if type(candidates) is not list:
        raise BlindRunError('Frozen ResearchWitness report has no candidate list')
    candidate_types: list[str] = []
    for candidate in candidates:
        if type(candidate) is not dict or type(candidate.get('type')) is not str:
            raise BlindRunError('Frozen ResearchWitness report has an invalid candidate type')
        candidate_types.append(candidate['type'])
    if cli_result.get('candidate_anomalies') != len(candidates) or cli_result.get('decision') != report.get('decision'):
        raise BlindRunError('CLI summary disagrees with its saved report')
    extraction = report.get('extraction')
    if type(extraction) is not dict or type(extraction.get('warnings')) is not list:
        raise BlindRunError('Frozen ResearchWitness report has invalid extraction metadata')
    if type(report.get('checks_attempted')) is not list or type(report.get('unsupported_checks')) is not list:
        raise BlindRunError('Frozen ResearchWitness report has invalid check metadata')

    return {
        'report_bytes': report_bytes,
        'html_bytes': html_bytes,
        'runtime_seconds': round(elapsed, 6),
        'summary': {
            'decision': report['decision'],
            'extraction_status': extraction.get('status'),
            'extraction_warnings': extraction['warnings'],
            'checks_attempted': report['checks_attempted'],
            'unsupported_checks': report['unsupported_checks'],
            'candidate_count': len(candidates),
            'candidate_types': candidate_types,
            'candidate_type_counts': dict(sorted(Counter(candidate_types).items())),
        },
    }


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def _run_one(
    index: int,
    record: dict[str, Any],
    source_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    source = record['source']
    source_path = _resolve_snapshot(source_root, source['snapshot_name'], index)
    source_bytes = source_path.read_bytes()
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise BlindRunError(f'Manifest case {index} source exceeds the frozen input size limit')
    original_hash = sha256(source_bytes)
    if original_hash != source['sha256']:
        raise BlindRunError(f'Manifest case {index} source hash does not match the capture')

    source_kind = source['source_kind']
    rendered_bytes = render(source_bytes) if source_kind == 'jats_xml' else source_bytes
    if len(rendered_bytes) > MAX_SOURCE_BYTES:
        raise BlindRunError(f'Manifest case {index} staged input exceeds the frozen input size limit')
    rendered_hash = sha256(rendered_bytes)
    suffix = SOURCE_SUFFIXES[source_kind]

    # IDs and versions are detached from publication metadata. The version token
    # binds the exact captured bytes and the manifest's opaque source-version
    # value without putting that value into CLI arguments or retained metadata.
    paper_id = record['paper_id']
    version_material = original_hash.encode('ascii') + b'\0' + source['source_version'].encode('utf-8')
    opaque_source_version = 'source-version-sha256:' + sha256(version_material)

    run_results: list[dict[str, Any]] = []
    for run_number in (1, 2):
        with tempfile.TemporaryDirectory(prefix='researchwitness-wave-2-') as temporary:
            run_root = Path(temporary)
            result = _run_cli(
                rendered_bytes, suffix, run_root / 'output',
                paper_id, opaque_source_version,
            )
            run_results.append(result)

    record_dir = output_root / paper_id
    file_hashes: dict[str, dict[str, str]] = {}
    for run_number, result in enumerate(run_results, start=1):
        run_name = f'run-{run_number}'
        json_bytes = result['report_bytes']
        html_bytes = result['html_bytes']
        _write_bytes(record_dir / run_name / 'report.json', json_bytes)
        _write_bytes(record_dir / run_name / 'report.html', html_bytes)
        file_hashes[run_name] = {
            'report.json': sha256(json_bytes),
            'report.html': sha256(html_bytes),
        }

    first, second = run_results
    same_json = first['report_bytes'] == second['report_bytes']
    same_html = first['html_bytes'] == second['html_bytes']
    repeatability = {
        'report_json_identical': same_json,
        'report_html_identical': same_html,
        'decision_identical': first['summary']['decision'] == second['summary']['decision'],
        'candidate_types_identical': first['summary']['candidate_types'] == second['summary']['candidate_types'],
        'repeatable': same_json and same_html,
    }
    metadata_hashes: dict[str, str] = {}
    for run_number, result in enumerate(run_results, start=1):
        run_name = f'run-{run_number}'
        saved_json_sha256 = _sha256_file(record_dir / run_name / 'report.json')
        saved_html_sha256 = _sha256_file(record_dir / run_name / 'report.html')
        if (
            saved_json_sha256 != file_hashes[run_name]['report.json']
            or saved_html_sha256 != file_hashes[run_name]['report.html']
        ):
            raise BlindRunError('Saved report bytes do not match their recorded hashes')
        metadata = {
            'metadata_version': 1,
            'paper_id': paper_id,
            'run_id': run_name,
            'source': {
                'source_kind': source_kind,
                'source_sha256': original_hash,
                'staged_input_sha256': rendered_hash,
                'source_version_token': opaque_source_version,
                'renderer_version': RENDERER_VERSION if source_kind == 'jats_xml' else None,
                'renderer_sha256': RENDERER_SHA256 if source_kind == 'jats_xml' else None,
            },
            'frozen_baseline': {
                'commit': FROZEN_COMMIT,
                'tree_sha': FROZEN_TREE,
                'package_version': VERSION,
                'paper_audit_schema_version': PAPER_AUDIT_SCHEMA_VERSION,
            },
            'execution_environment': EXECUTION_ENVIRONMENT,
            'runtime_seconds': result['runtime_seconds'],
            **result['summary'],
            'file_sha256': {
                'report.json': saved_json_sha256,
                'report.html': saved_html_sha256,
            },
            'repeatability': repeatability,
        }
        metadata_bytes = (json.dumps(metadata, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        _write_bytes(record_dir / run_name / 'run_metadata.json', metadata_bytes)
        metadata_hashes[run_name] = sha256(metadata_bytes)
    return {
        'output_dir': record_dir,
        'file_hashes': file_hashes,
        'metadata_hashes': metadata_hashes,
    }


def run(manifest_path: Path, source_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run two blinded CLI passes per source and create the final output lock."""
    _verify_frozen_detector()
    manifest_argument = Path(os.path.abspath(manifest_path))
    if manifest_argument != manifest_argument.resolve(strict=True):
        raise BlindRunError('Source manifest path must not use symlinks')
    manifest_path = manifest_argument.resolve(strict=True)
    source_root = source_dir.resolve(strict=True)
    if not source_root.is_dir():
        raise BlindRunError('Source directory is not a directory')
    try:
        manifest_repo_path = manifest_path.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise BlindRunError('Source manifest must be inside this repository') from exc
    manifest, manifest_bytes = _load_source_manifest(manifest_path)

    output_argument = Path(os.path.abspath(output_dir))
    output_root = output_argument.resolve()
    if output_argument != output_root:
        raise BlindRunError('Output directory path must not use symlinks')
    try:
        output_repo_path = output_root.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise BlindRunError('Output directory must be inside this repository') from exc
    if output_root == source_root or source_root in output_root.parents or output_root in source_root.parents:
        raise BlindRunError('Output and source directories must not overlap')
    if manifest_path == output_root or output_root in manifest_path.parents:
        raise BlindRunError('Source manifest must be outside the output directory')
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise BlindRunError('Output directory must be empty')
    output_root.mkdir(parents=True, exist_ok=True)

    papers: list[dict[str, str]] = []
    expected_output_hashes: dict[str, str] = {}
    raw_outputs: list[dict[str, str]] = []
    for index, record in enumerate(manifest['papers'], start=1):
        result = _run_one(index, record, source_root, output_root)
        paper_id = record['paper_id']
        papers.append({'paper_id': paper_id})
        for run_name, named_hashes in result['file_hashes'].items():
            run_id = run_name
            for filename, file_hash in named_hashes.items():
                relative_path = (result['output_dir'] / run_name / filename).relative_to(ROOT).as_posix()
                relative_name = (result['output_dir'] / run_name / filename).relative_to(output_root).as_posix()
                kind = 'report_json' if filename == 'report.json' else 'report_html'
                expected_output_hashes[relative_name] = file_hash
                raw_outputs.append({
                    'path': relative_path,
                    'sha256': file_hash,
                    'kind': kind,
                    'paper_id': paper_id,
                    'run_id': run_id,
                })
            metadata_path = result['output_dir'] / run_name / 'run_metadata.json'
            metadata_hash = result['metadata_hashes'][run_name]
            expected_output_hashes[metadata_path.relative_to(output_root).as_posix()] = metadata_hash
            raw_outputs.append({
                'path': metadata_path.relative_to(ROOT).as_posix(),
                'sha256': metadata_hash,
                'kind': 'run_metadata',
                'paper_id': paper_id,
                'run_id': run_id,
            })

    persisted_paths = sorted(
        path for path in output_root.rglob('*') if path.is_file()
    )
    persisted_hashes = {
        path.relative_to(output_root).as_posix(): _sha256_file(path)
        for path in persisted_paths
    }
    if persisted_hashes != expected_output_hashes:
        raise BlindRunError('Persisted raw outputs differ from the files prepared for locking')

    manifest_hash = sha256(manifest_bytes)
    runner_path = Path(__file__).resolve()
    runner_repo_path = runner_path.relative_to(ROOT).as_posix()
    runner_hash = _sha256_file(runner_path)
    raw_outputs.append({
        'path': manifest_repo_path,
        'sha256': manifest_hash,
        'kind': 'source_metadata',
    })

    lock = {
        'lock_version': 1,
        'evaluation_wave': 'paper-audit-wave-2',
        'status': 'RAW_OUTPUTS_LOCKED_BEFORE_ADJUDICATION',
        'frozen_baseline_commit': FROZEN_COMMIT,
        'frozen_baseline_tree_sha': FROZEN_TREE,
        'package_version': VERSION,
        'paper_audit_schema_version': PAPER_AUDIT_SCHEMA_VERSION,
        'execution_environment': EXECUTION_ENVIRONMENT,
        'renderer_version': manifest['renderer'],
        'renderer_sha256': RENDERER_SHA256,
        'source_manifest': {
            'path': manifest_repo_path,
            'sha256': manifest_hash,
        },
        'source_manifest_path': manifest_repo_path,
        'source_manifest_sha256': manifest_hash,
        'runner': {
            'path': runner_repo_path,
            'sha256': runner_hash,
        },
        'runner_path': runner_repo_path,
        'runner_sha256': runner_hash,
        'papers': papers,
        'raw_outputs': raw_outputs,
        'output_root': output_repo_path,
        'raw_output_count': len(raw_outputs),
        'lock_policy': 'Only report.json, report.html, and per-paper run metadata are retained under output_root; CLI source copies and extracted text are discarded with temporary directories. The committed source-only manifest is separately hash-locked as source_metadata.',
    }
    lock_bytes = (json.dumps(lock, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    _write_bytes(output_root / 'LOCK.json', lock_bytes)
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True,
                        help='source-only JSON manifest (renderer and source captures only)')
    parser.add_argument('--source-dir', type=Path, required=True,
                        help='directory containing the exact captured source files')
    parser.add_argument('--output', type=Path, required=True,
                        help='new or empty directory for locked blind-run outputs')
    args = parser.parse_args()
    try:
        lock = run(args.manifest, args.source_dir, args.output)
    except (BlindRunError, OSError) as exc:
        print(json.dumps({'status': 'FAILED', 'reason': str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    print(json.dumps({
        'status': lock['status'],
        'paper_count': len(lock['papers']),
        'raw_output_count': lock['raw_output_count'],
        'source_manifest_sha256': lock['source_manifest']['sha256'],
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
