"""Validate evidence bundles and compute narrowly scoped machine-verification reports."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import platform
from typing import Any

from .strict import Bundle, fields, text, integer, require, loads, digest, byte_hash, HASH_RE, relative_path
from .checkers import check, KINDS

VERSION = '0.3.0.dev0'
PROTOCOL = 'ResearchWitness/1.1'
SCHEMA_VERSION = '1.0'
POLICY_VERSION = 'formalization-only-1.1'
MAX_STATUS_AGE_DAYS = 30  # Informational freshness threshold, not a scientific standard.


def _strings(value: Any, name: str, minimum: int = 0) -> None:
    require(type(value) is list and minimum <= len(value) <= 64, 'Invalid ' + name)
    for item in value:
        text(item, 4000)
    require(len(set(value)) == len(value), 'Duplicate ' + name)


def _identifier(value: Any) -> None:
    text(value, 100)
    require(value.isascii() and all(c.isalnum() or c in '-_.' for c in value), 'Invalid identifier')


def _hash(value: Any) -> None:
    require(type(value) is str and HASH_RE.fullmatch(value) is not None, 'Invalid SHA-256')


def _iso_date(value: Any) -> date:
    text(value, 10)
    require(len(value) == 10 and value[4] == '-' and value[7] == '-', 'Expected ISO date')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        from .strict import Invalid
        raise Invalid('Invalid date') from exc


def validate_case(case: Any) -> None:
    """Validate the v1 interchange contract.

    The schema intentionally contains no reviewer/approver objects. Review notes may be
    carried as ordinary manifested artifacts, but they do not affect the deterministic result.
    """
    fields(case, {'schema_version', 'case_id', 'artifacts', 'source', 'claim',
                  'witness_artifact', 'unresolved_objections', 'disclosure'})
    require(case['schema_version'] == SCHEMA_VERSION, 'Unsupported schema version')
    _identifier(case['case_id'])
    require(case['disclosure'] == 'private', 'ResearchWitness v1 supports private evidence bundles only')

    artifacts = case['artifacts']
    require(type(artifacts) is dict and 1 <= len(artifacts) <= 64, 'Invalid artifact manifest')
    for name, hash_value in artifacts.items():
        relative_path(name)
        require(name.casefold() not in {'case.json', 'report.json', 'checksums.sha256'}, 'Reserved artifact name')
        _hash(hash_value)
    require(len({name.casefold() for name in artifacts}) == len(artifacts), 'Case-insensitive path collision')
    for name in artifacts:
        require(not any(other.casefold().startswith(name.casefold() + '/') for other in artifacts),
                'Artifact path prefix collision')

    src = case['source']
    fields(src, {'artifact', 'text_artifact', 'identifier', 'version', 'capture_status', 'correction_check'})
    for key in ('artifact', 'text_artifact'):
        text(src[key], 240)
        require(src[key] in artifacts, 'Source artifact not manifested')
    text(src['identifier'], 2000)
    text(src['version'], 100)
    require(src['capture_status'] in ('unverified', 'captured', 'synthetic'), 'Unknown source capture status')

    status = src['correction_check']
    fields(status, {'checked_on', 'status', 'evidence_artifact'})
    _iso_date(status['checked_on'])
    require(status['status'] in ('unchecked', 'none_found', 'present'), 'Unknown correction status')
    text(status['evidence_artifact'], 240)
    require(status['evidence_artifact'] in artifacts, 'Missing correction-check evidence')

    claim = case['claim']
    fields(claim, {'id', 'statement', 'scope', 'assumptions', 'excluded_claims', 'anchor', 'formalization'})
    _identifier(claim['id'])
    text(claim['statement'], 8000)
    text(claim['scope'], 4000)
    _strings(claim['assumptions'], 'assumptions', minimum=1)
    _strings(claim['excluded_claims'], 'excluded claims', minimum=1)
    fields(claim['anchor'], {'offset', 'quote'})
    integer(claim['anchor']['offset'], 0, 16 * 1024 * 1024)
    text(claim['anchor']['quote'], 8000)
    require(type(claim['formalization']) is dict and
            type(claim['formalization'].get('kind')) is str and
            claim['formalization']['kind'] in KINDS, 'Unsupported formalization kind')

    text(case['witness_artifact'], 240)
    require(case['witness_artifact'] in artifacts, 'Witness artifact not manifested')
    _strings(case['unresolved_objections'], 'objections')


def subject_digest(case: dict) -> str:
    """Bind the exact source snapshot, claim, formalization and witness inputs."""
    src = case['source']
    inputs = {src['artifact'], src['text_artifact'], src['correction_check']['evidence_artifact'],
              case['witness_artifact']}
    return digest({k: case[k] for k in ('schema_version', 'case_id', 'source', 'claim',
                                       'witness_artifact', 'unresolved_objections', 'disclosure')} |
                  {'input_hashes': {name: case['artifacts'][name] for name in sorted(inputs)}})


def load_bundle(root: Path | str) -> tuple[dict, dict[str, bytes]]:
    bundle = Bundle(root)
    case = loads(bundle.read('case.json', 2 * 1024 * 1024))
    validate_case(case)
    data: dict[str, bytes] = {}
    total = 0
    for name, expected in case['artifacts'].items():
        content = bundle.read(name)
        total += len(content)
        require(total <= 64 * 1024 * 1024, 'Total bundle size limit exceeded')
        require(byte_hash(content) == expected, 'Artifact hash mismatch: ' + name)
        data[name] = content

    src = case['source']
    anchor = case['claim']['anchor']
    body = data[src['text_artifact']]
    quote = anchor['quote'].encode('utf-8')
    offset = anchor['offset']
    require(body[offset: offset + len(quote)] == quote, 'Source quote/byte offset mismatch')
    return case, data


def core_digest() -> str:
    root = Path(__file__).parent
    return digest({name: byte_hash((root / name).read_bytes())
                   for name in ('__init__.py', '__main__.py', 'strict.py', 'arithmetic.py',
                                'checkers.py', 'capsule.py', 'resolution.py')})


def evaluate_loaded(case: dict, data: dict[str, bytes], as_of: date,
                    expected_bundle_sha256: str | None = None) -> dict:
    """Evaluate a loaded bundle without pretending to verify paper-level interpretation.

    A positive result means only that the supplied witness contradicts the supplied formalization
    under an allowlisted deterministic checker. Source authenticity and semantic transcription are
    separate questions and are never silently promoted to machine-proved facts.
    """
    bundle_sha = digest(case)
    if expected_bundle_sha256 is not None:
        _hash(expected_bundle_sha256)
        require(bundle_sha == expected_bundle_sha256, 'External bundle digest mismatch')

    subject = subject_digest(case)
    proof = check(case['claim']['formalization'], loads(data[case['witness_artifact']]))
    source = case['source']
    status = source['correction_check']
    objections = list(case['unresolved_objections'])

    context_flags: list[dict[str, str]] = []
    warnings = [
        'The deterministic result applies only to the supplied formalization and witness.',
        'Source-to-formalization semantic equivalence is not machine-proved by ResearchWitness.',
        'Hashes prove internal byte consistency, not publication authenticity or scientific truth.',
        'External communication, publication, misconduct inference, and author-contact authorization are not performed by the verifier.',
    ]

    if expected_bundle_sha256 is None:
        context_flags.append({'code': 'BUNDLE_NOT_EXTERNALLY_PINNED',
                              'detail': 'A coordinated rewrite of case metadata and artifact hashes is not externally detectable.'})
    if source['capture_status'] == 'unverified':
        context_flags.append({'code': 'SOURCE_CAPTURE_UNVERIFIED',
                              'detail': 'The declared source identifier/version has not been authenticated by this package.'})
    elif source['capture_status'] == 'synthetic':
        context_flags.append({'code': 'SYNTHETIC_SOURCE',
                              'detail': 'This is a fixture, not evidence about a real publication.'})

    checked = _iso_date(status['checked_on'])
    age = (as_of - checked).days
    if age < 0:
        context_flags.append({'code': 'FUTURE_CORRECTION_CHECK',
                              'detail': 'The correction-status record is dated after the evaluation date.'})
    elif age > MAX_STATUS_AGE_DAYS:
        context_flags.append({'code': 'STALE_CORRECTION_CHECK',
                              'detail': 'The correction-status record is older than the informational freshness window.'})
    if status['status'] == 'unchecked':
        context_flags.append({'code': 'CORRECTION_STATUS_UNCHECKED',
                              'detail': 'No correction-status search is recorded.'})
    elif status['status'] == 'present':
        context_flags.append({'code': 'CORRECTION_PRESENT',
                              'detail': 'A correction is recorded; use the timeline/revision mechanism for historical comparison.'})
    if not data[status['evidence_artifact']].strip():
        context_flags.append({'code': 'EMPTY_CORRECTION_EVIDENCE',
                              'detail': 'The correction-status evidence artifact is empty.'})
    for objection in objections:
        context_flags.append({'code': 'OPEN_OBJECTION', 'detail': objection})

    decision = {
        'REFUTED_FOR_FORMALIZATION': 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED',
        'NO_REFUTATION_AT_WITNESS': 'NO_REFUTATION_AT_WITNESS',
        'INCONCLUSIVE_INTERVAL': 'INCONCLUSIVE_INTERVAL',
    }[proof['status']]

    return {
        'protocol': PROTOCOL,
        'version': VERSION,
        'policy': POLICY_VERSION,
        'case_id': case['case_id'],
        'as_of': as_of.isoformat(),
        'subject_sha256': subject,
        'bundle_sha256': bundle_sha,
        'externally_pinned': expected_bundle_sha256 is not None,
        'core_sha256': core_digest(),
        'python': platform.python_version(),
        'decision': decision,
        'formalization_result': proof,
        'evidence_complete_for_formalization': proof['status'] == 'REFUTED_FOR_FORMALIZATION',
        'paper_error_established': False,
        'source_anchor_verified': True,
        'source_capture_status': source['capture_status'],
        'correction_status': status['status'],
        'context_flags': context_flags,
        'open_objections': objections,
        'external_actions': 'OUT_OF_SCOPE',
        'scope': case['claim']['scope'],
        'excluded_claims': case['claim']['excluded_claims'],
        'warnings': warnings,
    }


def evaluate(root: Path | str, as_of: date, expected_bundle_sha256: str | None = None) -> dict:
    case, data = load_bundle(root)
    return evaluate_loaded(case, data, as_of, expected_bundle_sha256)
