"""Fetch or verify exact Europe PMC JATS snapshots for paper-audit wave 1.

Full paper text is not checked into the repository. The default cache is under
the system temporary directory; every download must match the pinned SHA-256
before it is written there.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'validation/paper-audit-wave-1/cases.json'
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def obtain(record: dict, cache: Path, download: bool) -> dict:
    pmcid = record['pmcid']
    path = cache / record['snapshot_name']
    if path.exists():
        data = path.read_bytes()
        if sha256(data) != record['sha256']:
            raise ValueError(f'{pmcid}: cached snapshot SHA-256 does not match the manifest')
        return {'pmcid': pmcid, 'status': 'VERIFIED_CACHE', 'path': str(path), 'sha256': record['sha256']}
    if not download:
        return {'pmcid': pmcid, 'status': 'MISSING', 'path': str(path), 'sha256': record['sha256']}
    expected_url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'
    if record.get('source_url') != expected_url:
        raise ValueError(f'{pmcid}: manifest source URL is not the fixed Europe PMC endpoint')
    request = Request(record['source_url'], headers={'User-Agent': 'ResearchWitness-paper-audit-wave/1.0'})
    try:
        with urlopen(request, timeout=30) as response:
            if urlparse(response.geturl()).hostname != 'www.ebi.ac.uk':
                raise ValueError(f'{pmcid}: Europe PMC redirected to an unapproved host')
            data = response.read(MAX_SOURCE_BYTES + 1)
    except (OSError, URLError) as exc:
        raise RuntimeError(f'{pmcid}: Europe PMC retrieval failed ({type(exc).__name__})') from exc
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError(f'{pmcid}: downloaded source exceeds the configured byte limit')
    actual = sha256(data)
    if actual != record['sha256']:
        raise ValueError(
            f'{pmcid}: Europe PMC bytes changed; expected {record["sha256"]}, received {actual}. '
            'The pinned corpus was left unchanged.'
        )
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {'pmcid': pmcid, 'status': 'DOWNLOADED_AND_VERIFIED', 'path': str(path), 'sha256': actual}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path(tempfile.gettempdir()) / 'researchwitness-paper-audit-wave-1')
    parser.add_argument('--download', action='store_true', help='download missing snapshots after checking the pinned hash')
    parser.add_argument('--include-corrections', action='store_true', help='also retrieve correction records for verification')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    records = []
    for case in manifest['cases']:
        records.append(case['source'])
        if args.include_corrections and case.get('correction'):
            records.append(case['correction'])
    results = [obtain(record, args.cache, args.download) for record in records]
    print(json.dumps({'cache': str(args.cache), 'snapshots': results}, indent=2))
    return 0 if all(item['status'] != 'MISSING' for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
