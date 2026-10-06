"""Broad paper-review ledger with explicit evidence and verification levels."""
from __future__ import annotations

from datetime import date
from html import escape
import json
from pathlib import Path
from typing import Any

from .capsule import evaluate_loaded, load_bundle
from .statistics import validate_summary_check
from .strict import Bundle, Invalid, byte_hash, canonical, fields, integer, loads, relative_path, require, text

REVIEW_VERSION = '0.1'
REVIEW_AREAS = {
    'source_citations': 'Source and citation integrity',
    'internal_consistency': 'Internal consistency',
    'mathematics_logic': 'Mathematics and logic',
    'statistics_quantitative': 'Statistics and quantitative reporting',
    'data_integrity': 'Data integrity and provenance',
    'methods_design': 'Methods and experimental design',
    'code_reproducibility': 'Code and computational reproducibility',
    'figures_tables': 'Figures and tables',
    'interpretation': 'Interpretation and scope of conclusions',
    'ethics_reporting': 'Ethics and reporting requirements',
}
AREA_STATUSES = {
    'not_reviewed', 'reviewed_no_findings', 'findings_recorded', 'unsupported', 'not_applicable',
}
FINDING_STATUSES = {
    'candidate', 'unsupported', 'dismissed', 'formalization_replay', 'tabular_summary_replay',
}
MAX_REVIEW_EVIDENCE_REFERENCES = 512
MAX_REVIEW_EVIDENCE_FILES = 256
MAX_REVIEW_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_LINKED_REPLAYS = 32
MAX_LINKED_BUNDLE_BYTES = 64 * 1024 * 1024


class _EvidenceStore:
    """Cache evidence reads under review-wide count and byte budgets."""

    def __init__(self, root: Path):
        self.bundle = Bundle(root)
        self._cache: dict[str, tuple[bytes, str]] = {}
        self._references = 0
        self._total_bytes = 0

    def _entry(self, name: str, limit: int) -> tuple[bytes, str]:
        name = relative_path(name)
        self._references += 1
        require(self._references <= MAX_REVIEW_EVIDENCE_REFERENCES,
                'Review evidence reference limit exceeded')
        entry = self._cache.get(name)
        if entry is not None:
            require(len(entry[0]) <= limit, 'Artifact size limit exceeded: ' + name)
            return entry
        require(len(self._cache) < MAX_REVIEW_EVIDENCE_FILES,
                'Review evidence file-count limit exceeded')
        data = self.bundle.read(name, limit)
        require(self._total_bytes + len(data) <= MAX_REVIEW_EVIDENCE_BYTES,
                'Review aggregate evidence-size limit exceeded')
        entry = (data, byte_hash(data))
        self._cache[name] = entry
        self._total_bytes += len(data)
        return entry

    def read(self, name: str, limit: int = 16 * 1024 * 1024) -> bytes:
        return self._entry(name, limit)[0]

    def hash(self, name: str, limit: int = 16 * 1024 * 1024) -> str:
        return self._entry(name, limit)[1]


def _read_evidence(bundle: _EvidenceStore, names: Any) -> dict[str, str]:
    require(type(names) is list and len(names) <= 32, 'Invalid evidence file list')
    require(all(type(name) is str for name in names), 'Evidence file names must be strings')
    require(len(set(names)) == len(names), 'Duplicate evidence file path')
    hashes: dict[str, str] = {}
    for name in names:
        relative_path(name)
        hashes[name] = bundle.hash(name)
    return hashes


def _quote_offset(claim: dict, source_bytes: bytes) -> int:
    quote = claim['quote'].encode('utf-8')
    if 'quote_offset' in claim:
        offset = integer(claim['quote_offset'], 0, len(source_bytes))
        require(source_bytes[offset:offset + len(quote)] == quote,
                'Finding quote does not match supplied offset')
        return offset
    first = source_bytes.find(quote)
    require(first >= 0, 'Finding quote not found in supplied source text')
    require(source_bytes.find(quote, first + 1) < 0,
            'Finding quote is ambiguous; supply quote_offset')
    return first


def _review_bundle(root: Path, name: Any) -> Path:
    relative_path(name)
    candidate = root
    for component in name.split('/'):
        candidate = candidate / component
        require(not candidate.is_symlink(), 'Symlink rejected in verification bundle path')
    resolved = candidate.resolve(strict=True)
    require(resolved.is_relative_to(root), 'Verification bundle path escapes review directory')
    require(resolved.is_dir(), 'Verification bundle path must name a directory')
    return resolved


def validate_review(doc: Any, root: Path, raw_review: bytes) -> dict[str, Any]:
    """Validate a multi-area review and replay any explicitly linked checker bundles."""
    fields(doc, {'review_version', 'review_id', 'reviewed_on', 'source', 'areas', 'findings'})
    require(doc['review_version'] == REVIEW_VERSION, 'Unsupported review version')
    text(doc['review_id'], 100)
    reviewed_on = doc['reviewed_on']
    require(type(reviewed_on) is str, 'Review date must be ISO text')
    try:
        as_of = date.fromisoformat(reviewed_on)
    except ValueError as exc:
        raise Invalid('Invalid review date') from exc
    require(as_of.isoformat() == reviewed_on, 'Review date must use YYYY-MM-DD')

    source = doc['source']
    fields(source, {'identifier', 'version', 'text_file', 'capture_status'})
    text(source['identifier'], 2000)
    text(source['version'], 100)
    relative_path(source['text_file'])
    require(source['capture_status'] in ('unverified', 'captured', 'synthetic'),
            'Unknown source capture status')

    source_bundle = _EvidenceStore(root)
    source_bytes = source_bundle.read(source['text_file'])
    try:
        source_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Invalid('Review source text must be UTF-8') from exc
    source_hash = byte_hash(source_bytes)

    areas = doc['areas']
    fields(areas, set(REVIEW_AREAS))
    area_hashes: dict[str, dict[str, str]] = {}
    area_statuses: dict[str, str] = {}
    for area in REVIEW_AREAS:
        record = areas[area]
        fields(record, {'status', 'method', 'notes', 'evidence_files'})
        status = record['status']
        require(type(status) is str and status in AREA_STATUSES,
                f'Unknown review status for {area}')
        text(record['method'], 2000)
        text(record['notes'], 4000)
        area_hashes[area] = _read_evidence(source_bundle, record['evidence_files'])
        area_statuses[area] = status

    findings = doc['findings']
    require(type(findings) is list and len(findings) <= 256, 'Invalid finding list')
    seen_ids: set[str] = set()
    active_by_area = {area: 0 for area in REVIEW_AREAS}
    entries_by_area = {area: 0 for area in REVIEW_AREAS}
    result_findings: list[dict[str, Any]] = []
    linked_replays = 0
    linked_bundle_bytes = 0
    for item in findings:
        fields(item, {'id', 'area', 'status', 'location', 'statement', 'quote',
                      'rationale', 'evidence_files'},
               {'quote_offset', 'verification_bundle', 'summary_check'})
        finding_id = text(item['id'], 100)
        require(finding_id not in seen_ids, 'Duplicate finding id')
        seen_ids.add(finding_id)
        area = item['area']
        require(type(area) is str and area in REVIEW_AREAS, 'Unknown finding review area')
        entries_by_area[area] += 1
        status = item['status']
        require(type(status) is str and status in FINDING_STATUSES, 'Unknown finding status')
        if status in ('formalization_replay', 'tabular_summary_replay'):
            linked_replays += 1
            require(linked_replays <= MAX_LINKED_REPLAYS,
                    f'Review linked-replay limit exceeded ({MAX_LINKED_REPLAYS})')
        text(item['location'], 1000)
        text(item['statement'], 8000)
        text(item['quote'], 8000)
        text(item['rationale'], 4000)
        quote_offset = _quote_offset(item, source_bytes)
        evidence_hashes = _read_evidence(source_bundle, item['evidence_files'])
        if status in ('candidate', 'dismissed'):
            require(evidence_hashes, 'Candidate and dismissed findings need supporting evidence files')
        if status == 'formalization_replay':
            require('verification_bundle' in item, 'Formalization replay needs a linked bundle')
            require('summary_check' not in item, 'Formalization replay cannot link a summary check')
        elif status == 'tabular_summary_replay':
            require('summary_check' in item, 'Tabular-summary replay needs a linked input')
            require('verification_bundle' not in item, 'Tabular-summary replay cannot link a case bundle')
        else:
            require('verification_bundle' not in item and 'summary_check' not in item,
                    'Only replay findings may link checker inputs')

        record: dict[str, Any] = {
            'id': finding_id,
            'area': area,
            'area_title': REVIEW_AREAS[area],
            'status': status,
            'location': item['location'],
            'statement': item['statement'],
            'quote': item['quote'],
            'quote_offset': quote_offset,
            'quote_anchor': 'VERIFIED_IN_SUPPLIED_SOURCE_BYTES',
            'rationale': item['rationale'],
            'evidence_sha256': evidence_hashes,
        }
        if status != 'dismissed':
            active_by_area[area] += 1
        if status in ('candidate', 'unsupported'):
            record['assessment'] = ('UNVERIFIED_REVIEW_CANDIDATE' if status == 'candidate'
                                    else 'UNSUPPORTED_BY_CURRENT_REVIEW_METHOD')
        elif status == 'dismissed':
            record['assessment'] = 'DISMISSED_BY_REVIEWER'
        elif status == 'tabular_summary_replay':
            summary_name = relative_path(item['summary_check'])
            summary_raw = source_bundle.read(summary_name, 2 * 1024 * 1024)
            summary_hash = byte_hash(summary_raw)
            require(summary_name not in evidence_hashes or evidence_hashes[summary_name] == summary_hash,
                    'Summary-check evidence hash changed while the review was being read')
            evidence_hashes[summary_name] = summary_hash
            summary_doc = loads(summary_raw)
            require(type(summary_doc) is dict, 'Summary-check input must be an object')
            summary_source = summary_doc.get('source')
            require(type(summary_source) is dict, 'Summary-check source is missing')
            require(summary_source.get('identifier') == source['identifier']
                    and summary_source.get('version') == source['version']
                    and summary_source.get('text_file') == source['text_file'],
                    'Summary-check source identity/version/text mismatch')
            require(summary_source.get('quote') == item['quote'],
                    'Summary-check claim quote must match the review finding quote')
            summary_result = validate_summary_check(
                summary_doc, source_bytes, summary_raw, source_bundle
            )
            require(summary_result['source']['quote_offset'] == quote_offset,
                    'Summary-check and review quote anchors point to different occurrences')
            extraction = summary_result['data']['extraction']
            if extraction['input_kind'] == 'delimited_file':
                data_name = relative_path(extraction['file'])
                data_hash = extraction['file_sha256']
                require(data_name not in evidence_hashes or evidence_hashes[data_name] == data_hash,
                        'Tabular data evidence hash changed while the review was being read')
                evidence_hashes[data_name] = data_hash
            record['assessment'] = 'DETERMINISTIC_TABULAR_SUMMARY_REPLAY'
            record['verification'] = {
                'decision': summary_result['decision'],
                'result': summary_result,
                'input_path': summary_name,
                'input_sha256': summary_result['input_sha256'],
                'paper_error_established': False,
            }
        else:
            bundle_path = _review_bundle(root, item['verification_bundle'])
            case, data = load_bundle(bundle_path)
            linked_bundle_bytes += sum(len(content) for content in data.values())
            require(linked_bundle_bytes <= MAX_LINKED_BUNDLE_BYTES,
                    f'Review linked-bundle aggregate limit exceeded ({MAX_LINKED_BUNDLE_BYTES})')
            require(case['source']['identifier'] == source['identifier']
                    and case['source']['version'] == source['version'],
                    'Linked checker bundle source identity/version mismatch')
            claim = case['claim']
            case_quote = claim['anchor']['quote'].encode('utf-8')
            require(case_quote == item['quote'].encode('utf-8'),
                    'Linked checker claim quote must match the review finding quote')
            case_source = data[case['source']['text_artifact']]
            require(case_source == source_bytes,
                    'Linked checker source bytes must match the reviewed paper snapshot exactly')
            require(claim['anchor']['offset'] == quote_offset,
                    'Linked checker and review quote anchors must use the same source offset')
            require(case_quote in source_bytes and case_quote in case_source,
                    'Linked checker quote is not present in the reviewed source bytes')
            checker_report = evaluate_loaded(case, data, as_of)
            record['assessment'] = 'DETERMINISTIC_FORMALIZATION_REPLAY'
            record['verification'] = {
                'decision': checker_report['decision'],
                'formalization_result': checker_report['formalization_result'],
                'bundle_sha256': checker_report['bundle_sha256'],
                'paper_error_established': False,
            }
        result_findings.append(record)

    for area, status in area_statuses.items():
        if status == 'findings_recorded':
            require(active_by_area[area] > 0,
                    f'{area} says findings_recorded but has no active findings')
        elif status == 'reviewed_no_findings':
            require(active_by_area[area] == 0,
                    f'{area} says reviewed_no_findings but has active findings')
        elif status in ('not_reviewed', 'not_applicable'):
            require(entries_by_area[area] == 0,
                    f'{area} cannot have findings with status {status}')

    area_report = {
        area: {
            'title': REVIEW_AREAS[area],
            'status': area_statuses[area],
            'method': areas[area]['method'],
            'notes': areas[area]['notes'],
            'evidence_sha256': area_hashes[area],
            'active_findings': active_by_area[area],
        }
        for area in REVIEW_AREAS
    }
    statuses = [item['status'] for item in area_report.values()]
    return {
        'decision': 'PAPER_REVIEW_LEDGER_VALIDATED',
        'review_id': doc['review_id'],
        'reviewed_on': reviewed_on,
        'source': {
            'identifier': source['identifier'],
            'version': source['version'],
            'capture_status': source['capture_status'],
            'source_provenance': 'NOT_AUTHENTICATED',
            'text_sha256': source_hash,
        },
        'coverage': {
            'areas_total': len(REVIEW_AREAS),
            'areas_reviewed': sum(status in ('reviewed_no_findings', 'findings_recorded') for status in statuses),
            'areas_not_reviewed': sum(status == 'not_reviewed' for status in statuses),
            'areas_unsupported': sum(status == 'unsupported' for status in statuses),
            'areas_not_applicable': sum(status == 'not_applicable' for status in statuses),
            'all_areas_accounted_for': all(
                status != 'not_reviewed' and status != 'unsupported' for status in statuses
            ),
        },
        'summary': {
            'findings_total': len(result_findings),
            'candidate_unverified': sum(item['assessment'] == 'UNVERIFIED_REVIEW_CANDIDATE'
                                        for item in result_findings),
            'unsupported': sum(item['assessment'] == 'UNSUPPORTED_BY_CURRENT_REVIEW_METHOD'
                               for item in result_findings),
            'dismissed': sum(item['assessment'] == 'DISMISSED_BY_REVIEWER'
                             for item in result_findings),
            'formalization_replays': sum(item['assessment'] == 'DETERMINISTIC_FORMALIZATION_REPLAY'
                                         for item in result_findings),
            'tabular_summary_replays': sum(
                item['assessment'] == 'DETERMINISTIC_TABULAR_SUMMARY_REPLAY'
                for item in result_findings
            ),
        },
        'areas': area_report,
        'findings': result_findings,
        'review_sha256': byte_hash(raw_review),
        'paper_error_established': False,
        'meaning': ('The ledger organizes reviewer observations and exact source anchors. It does not establish '
                    'that the paper is correct or incorrect. Candidate findings are unverified; linked checker '
                    'replays apply only to their formalizations, witnesses, and stated scope.'),
    }


def validate_review_file(review_path: Path | str) -> dict[str, Any]:
    review_path = Path(review_path).absolute()
    root = Bundle(review_path.parent).root
    raw = Bundle(root).read(review_path.name, 2 * 1024 * 1024)
    doc = loads(raw)
    return validate_review(doc, root, raw)


def scaffold_review(source_file: Path | str, output: Path | str,
                    identifier: str, version: str, reviewed_on: date | None = None) -> Path:
    """Create a broad review workspace from a supplied UTF-8 paper text capture."""
    source_path = Path(source_file).absolute()
    source_bytes = Bundle(source_path.parent).read(source_path.name)
    try:
        source_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Invalid('Review source text must be UTF-8') from exc
    text(identifier, 2000)
    text(version, 100)
    root = Path(output).absolute()
    require(not root.exists(), 'Review output directory already exists')
    root.mkdir(parents=True)
    (root / 'paper.txt').write_bytes(source_bytes)
    areas = {
        area: {
            'status': 'not_reviewed',
            'method': 'Not reviewed',
            'notes': 'No review has been performed for this area.',
            'evidence_files': [],
        }
        for area in REVIEW_AREAS
    }
    review = {
        'review_version': REVIEW_VERSION,
        'review_id': root.name[:100] or 'paper-review',
        'reviewed_on': (reviewed_on or date.today()).isoformat(),
        'source': {
            'identifier': identifier,
            'version': version,
            'text_file': 'paper.txt',
            'capture_status': 'unverified',
        },
        'areas': areas,
        'findings': [],
    }
    (root / 'review.json').write_bytes(canonical(review) + b'\n')
    (root / 'README.txt').write_text(
        'ResearchWitness broad paper-review workspace.\n'
        'The copied paper.txt bytes are preserved exactly, but source identity is unverified.\n'
        'Review every area in review.json or mark it unsupported/not applicable with a reason.\n'
        'Add candidate findings with exact source quotes and local evidence files.\n'
        'Candidate observations remain unverified. Link an existing ResearchWitness bundle only when using\n'
        'the formalization_replay status; that replay still does not establish a paper-level error.\n'
        'Run: researchwitness validate-review review.json\n',
        encoding='utf-8',
    )
    return root


def html_review_report(report: dict[str, Any]) -> str:
    status_labels = {
        'not_reviewed': 'Not reviewed',
        'reviewed_no_findings': 'Reviewed; no candidate recorded',
        'findings_recorded': 'Findings recorded',
        'unsupported': 'Unsupported by current method',
        'not_applicable': 'Not applicable',
    }
    rows = ''.join(
        '<tr><td>' + escape(record['title']) + '</td><td>' +
        escape(status_labels.get(record['status'], record['status'])) +
        '</td><td>' + escape(record['method']) + '</td><td>' +
        escape(record['notes']) + '</td><td>' + str(record['active_findings']) + '</td></tr>'
        for record in report['areas'].values()
    )
    findings: list[str] = []
    for item in report['findings']:
        verification = ''
        if 'verification' in item:
            verification = '<pre>' + escape(json.dumps(item['verification'], indent=2, sort_keys=True)) + '</pre>'
        findings.append(
            '<article><h3>' + escape(item['id']) + ' — ' + escape(item['assessment']) + '</h3>'
            '<p><strong>Area:</strong> ' + escape(item['area_title']) + '<br><strong>Location:</strong> ' +
            escape(item['location']) + '</p><p>' + escape(item['statement']) + '</p><blockquote>' +
            escape(item['quote']) + '</blockquote><p>' + escape(item['rationale']) + '</p>' + verification + '</article>'
        )
    finding_html = ''.join(findings) or '<p>No findings recorded.</p>'
    coverage = report['coverage']
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ResearchWitness paper review — {escape(report['review_id'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:3rem auto;padding:0 1rem;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.45rem;text-align:left;vertical-align:top}}
article{{border-top:1px solid #bbb;padding:1rem 0}}blockquote,pre{{background:#f4f4f4;padding:1rem;overflow:auto}}
.notice{{border-left:4px solid #b66;padding:.5rem 1rem;background:#fff9ed}}</style></head><body>
<h1>ResearchWitness paper review ledger</h1><h2>Review ledger validated</h2>
<p><strong>{escape(report['source']['identifier'])}</strong> ({escape(report['source']['version'])}) · reviewed {escape(report['reviewed_on'])}</p>
<p>Source capture status: {escape(report['source']['capture_status'])}; source authenticity: not authenticated. Paper error established: no.</p>
<p class="notice">Candidate observations are unverified. A checker replay applies only to its encoded formalization and witness. This report does not establish that the paper is correct or incorrect.</p>
<h2>Coverage</h2><p>{coverage['areas_reviewed']} of {coverage['areas_total']} areas reviewed; {coverage['areas_not_reviewed']} not reviewed; {coverage['areas_unsupported']} unsupported; {coverage['areas_not_applicable']} marked not applicable.</p>
<p>All areas accounted for in the ledger: {'yes' if coverage['all_areas_accounted_for'] else 'no'}. This is a record-keeping measure, not evidence that all possible errors were checked.</p>
<table><thead><tr><th>Area</th><th>Status</th><th>Method</th><th>Notes</th><th>Active findings</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Findings ({report['summary']['findings_total']})</h2>{finding_html}
<h2>Integrity</h2><p>Source text SHA-256: <code>{escape(report['source']['text_sha256'])}</code><br>Review SHA-256: <code>{escape(report['review_sha256'])}</code></p>
</body></html>'''
