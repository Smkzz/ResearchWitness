"""Low-friction agent intake for building strict evidence bundles."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .strict import Bundle, MAX_BUNDLE_BYTES, byte_hash, canonical, fields, loads, relative_path, require, text
from .capsule import SCHEMA_VERSION, _identifier, _iso_date, _strings, validate_case
from .checkers import KINDS, check

INTAKE_VERSION = '0.1'


def _read_relative(base: Path, name: Any, limit: int = 16 * 1024 * 1024) -> bytes:
    relative_path(name)
    return Bundle(base).read(name, limit)


def validate_intake(doc: Any) -> None:
    fields(doc, {'intake_version', 'case_id', 'source', 'claim', 'witness',
                 'unresolved_objections'}, {'notes_files'})
    require(doc['intake_version'] == INTAKE_VERSION, 'Unsupported intake version')
    _identifier(doc['case_id'])
    source = doc['source']
    fields(source, {'identifier', 'version', 'text_file', 'capture_status', 'correction_check'})
    text(source['identifier'], 2000)
    text(source['version'], 100)
    relative_path(source['text_file'])
    require(source['capture_status'] in ('unverified', 'captured', 'synthetic'), 'Unknown source capture status')
    correction = source['correction_check']
    fields(correction, {'checked_on', 'status', 'evidence_file'})
    _iso_date(correction['checked_on'])
    relative_path(correction['evidence_file'])
    require(correction['status'] in ('unchecked', 'none_found', 'present'), 'Unknown correction status')

    claim = doc['claim']
    fields(claim, {'id', 'statement', 'scope', 'assumptions', 'excluded_claims', 'quote', 'formalization'},
           {'quote_offset'})
    _identifier(claim['id'])
    text(claim['statement'], 8000)
    text(claim['scope'], 4000)
    text(claim['quote'], 8000)
    _strings(claim['assumptions'], 'assumptions', minimum=1)
    _strings(claim['excluded_claims'], 'excluded claims', minimum=1)
    require(type(claim['formalization']) is dict and
            type(claim['formalization'].get('kind')) is str and
            claim['formalization']['kind'] in KINDS,
            'Unsupported formalization kind')
    require(type(doc['witness']) is dict and doc['witness'].get('kind') == claim['formalization']['kind'],
            'Witness kind must match formalization')
    _strings(doc['unresolved_objections'], 'objections')
    notes = doc.get('notes_files', [])
    require(type(notes) is list and len(notes) <= 32, 'Invalid notes file list')
    for item in notes:
        relative_path(item)


def _quote_offset(claim: dict, source_bytes: bytes) -> int:
    quote = claim['quote'].encode('utf-8')
    if 'quote_offset' in claim:
        offset = claim['quote_offset']
        require(type(offset) is int and 0 <= offset <= len(source_bytes), 'Invalid quote offset')
        require(source_bytes[offset:offset + len(quote)] == quote, 'Quote does not match supplied offset')
        return offset
    first = source_bytes.find(quote)
    require(first >= 0, 'Claim quote not found in source text')
    require(source_bytes.find(quote, first + 1) < 0, 'Claim quote is ambiguous; supply quote_offset')
    return first


def _intake_artifacts(base: Path, doc: dict) -> dict[str, bytes]:
    """Apply the same generated-path and total-byte limits before validation or export."""
    artifacts = {'witness.json': canonical(doc['witness']) + b'\n'}
    total = len(artifacts['witness.json'])
    paths = [
        ('source.txt', doc['source']['text_file']),
        ('correction-check.txt', doc['source']['correction_check']['evidence_file']),
    ]
    paths.extend((f'notes/{index:02d}-{Path(name).name}', name)
                 for index, name in enumerate(doc.get('notes_files', []), start=1))
    for target_name, source_name in paths:
        relative_path(target_name)
        content = _read_relative(base, source_name)
        total += len(content)
        require(total <= MAX_BUNDLE_BYTES, 'Total bundle size limit exceeded')
        artifacts[target_name] = content
    return artifacts


def validate_intake_file(intake_path: Path | str) -> dict[str, Any]:
    """Validate an intake and its local artifacts without writing an evidence bundle."""
    intake_path = Path(intake_path).absolute()
    base = intake_path.parent
    doc = loads(Bundle(base).read(intake_path.name, 2 * 1024 * 1024))
    validate_intake(doc)
    artifacts = _intake_artifacts(base, doc)
    _quote_offset(doc['claim'], artifacts['source.txt'])
    result = check(doc['claim']['formalization'], doc['witness'])
    return {
        'valid': True,
        'case_id': doc['case_id'],
        'verifier_kind': doc['claim']['formalization']['kind'],
        'witness_status': result['status'],
        'source_anchor': 'VERIFIED_IN_SUPPLIED_BYTES',
        'source_provenance': 'NOT_AUTHENTICATED',
    }


def prepare(intake_path: Path | str, output: Path | str) -> Path:
    """Convert a convenient agent intake into the strict ResearchWitness bundle format."""
    intake_path = Path(intake_path).absolute()
    base = intake_path.parent
    doc = loads(Bundle(base).read(intake_path.name, 2 * 1024 * 1024))
    validate_intake(doc)
    out = Path(output).absolute()
    require(not out.exists(), 'Output bundle already exists')

    artifacts = _intake_artifacts(base, doc)
    offset = _quote_offset(doc['claim'], artifacts['source.txt'])

    case = {
        'schema_version': SCHEMA_VERSION,
        'case_id': doc['case_id'],
        'artifacts': {name: byte_hash(value) for name, value in artifacts.items()},
        'source': {
            'artifact': 'source.txt',
            'text_artifact': 'source.txt',
            'identifier': doc['source']['identifier'],
            'version': doc['source']['version'],
            'capture_status': doc['source']['capture_status'],
            'correction_check': {
                'checked_on': doc['source']['correction_check']['checked_on'],
                'status': doc['source']['correction_check']['status'],
                'evidence_artifact': 'correction-check.txt',
            },
        },
        'claim': {
            'id': doc['claim']['id'],
            'statement': doc['claim']['statement'],
            'scope': doc['claim']['scope'],
            'assumptions': doc['claim']['assumptions'],
            'excluded_claims': doc['claim']['excluded_claims'],
            'anchor': {'offset': offset, 'quote': doc['claim']['quote']},
            'formalization': doc['claim']['formalization'],
        },
        'witness_artifact': 'witness.json',
        'unresolved_objections': doc['unresolved_objections'],
        'disclosure': 'private',
    }
    validate_case(case)
    out.mkdir(parents=True)
    for name, value in artifacts.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    (out / 'case.json').write_bytes(canonical(case) + b'\n')
    return out
