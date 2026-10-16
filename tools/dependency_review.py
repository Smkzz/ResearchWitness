"""Capture installed development/build distributions, licenses and advisories.

Maintainer-only online audit: sends public package names/versions to PyPI and OSV.
It neither imports dependency code nor runs in the installed verifier core.
License texts are evidence for human/AI review, not automatic legal approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.request import Request, urlopen


def query(url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=data, headers={
        'User-Agent': 'ResearchWitness-dependency-review/1',
        'Content-Type': 'application/json',
    })
    with urlopen(request, timeout=30) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('advisory response exceeds audit bound')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('invalid advisory response')
    return result


def capture_distribution(dist, output: Path) -> dict:
    name = dist.metadata['Name']
    version = dist.version
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not re.fullmatch(r'[A-Za-z0-9_.+!-]+', version):
        raise ValueError('nonportable distribution identity')
    license_files = []
    distribution_root = Path(dist.locate_file('')).resolve()
    for entry in dist.files or ():
        # Include vendored LICENSE/COPYING/NOTICE and dist-info license directories.
        parts = [part.lower() for part in entry.parts]
        if not any('license' in p or 'licence' in p or p.startswith(('copying', 'notice', 'copyright')) for p in parts):
            continue
        relative = Path(entry)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('license path escapes distribution root')
        source = distribution_root / relative
        current = distribution_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('symbolic link in license evidence')
        if not source.resolve().is_relative_to(distribution_root):
            raise ValueError('license path escapes distribution root')
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('license evidence must be a regular unlinked file')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(source, flags), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError('license evidence changed during open')
            if opened.st_size > 4 * 1024 * 1024:
                raise ValueError('license evidence exceeds file bound')
            data = stream.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError('license evidence exceeds file bound')
        digest = hashlib.sha256(data).hexdigest()
        target = output / 'licenses' / name / f'{digest}.txt'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        license_files.append({'installed_path': str(entry), 'sha256': digest,
                              'bytes': len(data), 'evidence': target.relative_to(output).as_posix()})
    pypi = query(f'https://pypi.org/pypi/{name}/{version}/json')
    osv = osv_advisories(name, version)
    if not isinstance(pypi.get('vulnerabilities'), list) or any(not isinstance(a, dict) or not isinstance(a.get('id'), str) for a in pypi['vulnerabilities']):
        raise ValueError('PyPI vulnerability inventory missing')
    urls = pypi.get('urls', [])
    return {
        'name': name, 'version': version,
        'role': 'build-backend' if name.lower() == 'setuptools' else 'development-or-transitive',
        'requires_dist': dist.requires or [],
        'license_expression': dist.metadata.get('License-Expression'),
        'license_metadata': dist.metadata.get('License'),
        'license_classifiers': [v for v in dist.metadata.get_all('Classifier', []) if v.startswith('License ::')],
        'license_files': license_files,
        'pypi_advisories': pypi['vulnerabilities'], 'osv_advisories': osv,
        'published_distributions': [{'filename': v['filename'], 'sha256': v['digests']['sha256'],
                                     'yanked': v['yanked']} for v in urls],
    }


def osv_advisories(name: str, version: str) -> list:
    """Retain all pages; reject unknown payloads. OSV may encode an empty list as {}.

    Pagination contract: https://google.github.io/osv.dev/post-v1-query/
    """
    payload = {'package': {'name': name, 'ecosystem': 'PyPI'}, 'version': version}
    advisories = []
    seen = set()
    for _page in range(10):
        response = query('https://api.osv.dev/v1/query', payload)
        if set(response) - {'vulns', 'next_page_token'} or not isinstance(response.get('vulns', []), list) or any(not isinstance(a, dict) or not isinstance(a.get('id'), str) for a in response.get('vulns', [])):
            raise ValueError('OSV vulnerability inventory malformed')
        advisories.extend(response.get('vulns', []))
        token = response.get('next_page_token')
        if token is None or token == '':
            return advisories
        if not isinstance(token, str) or token in seen:
            raise ValueError('OSV pagination token invalid')
        seen.add(token)
        payload['page_token'] = token
    raise ValueError('OSV inventory exceeds page bound; review is incomplete')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    distributions = sorted((d for d in metadata.distributions()
                            if d.metadata['Name'].lower() not in {'pip', 'researchwitness'}),
                           key=lambda d: d.metadata['Name'].lower())
    rows = []
    errors = []
    for dist in distributions:
        try:
            rows.append(capture_distribution(dist, args.output))
        except Exception as exc:
            errors.append({'name': dist.metadata['Name'], 'version': dist.version,
                           'error': f'{type(exc).__name__}: {exc}'})
    result = {
        'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'runtime_dependencies': [],
        'scope': 'Installed distributions in this CI environment; no claim about uninstalled optional environments or legal approval',
        'excluded_tools': [{'name': 'pip', 'version': metadata.version('pip'), 'role': 'runner package manager'}],
        'distributions': rows, 'errors': errors,
        'advisory_count': sum(len(r['pypi_advisories']) + len(r['osv_advisories']) for r in rows),
        'license_review': 'REQUIRES_REVIEW_OF_CAPTURED_TEXTS',
    }
    path = args.output / 'dependency-review.json'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: result[k] for k in ('checked_at', 'errors', 'advisory_count', 'license_review')}))
    for row in rows:
        print(json.dumps({'name': row['name'], 'version': row['version'],
                          'license_expression': row['license_expression'],
                          'license_files': len(row['license_files']),
                          'pypi_advisories': [a.get('id') for a in row['pypi_advisories']],
                          'osv_advisories': [a.get('id') for a in row['osv_advisories']]}))
    return int(bool(errors) or bool(result['advisory_count']))


if __name__ == '__main__':
    raise SystemExit(main())
