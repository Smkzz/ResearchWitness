"""Correction/revision event projection for historical evidence tracking.

Timeline events are operator- or agent-recorded metadata. They do not authenticate authors,
messages, publisher records, or scientific truth. Revision checks re-test only the old witness.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .capsule import _hash, _identifier, _iso_date, load_bundle, subject_digest
from .checkers import check
from .strict import Bundle, fields, text, integer, require, loads, digest

TIMELINE_SCHEMA_VERSION = '1.0'
KINDS = {
    'INQUIRY_RECORDED',
    'AUTHOR_POSITION_RECORDED',
    'CORRECTION_NOTICE_RECORDED',
    'REVISION_WITNESS_RECHECK',
    'CASE_WITHDRAWN',
    'CASE_REOPENED',
}


def project(case: dict, artifacts: dict[str, bytes], timeline: dict, as_of: date,
            expected_timeline_sha256: str | None = None) -> dict:
    """Project a validated event chain; never infer authenticity from the event labels."""
    fields(timeline, {'schema_version', 'subject_sha256', 'events'})
    require(timeline['schema_version'] == TIMELINE_SCHEMA_VERSION, 'Unsupported timeline schema')
    _hash(timeline['subject_sha256'])
    require(timeline['subject_sha256'] == subject_digest(case), 'Timeline subject mismatch')
    pin = digest(timeline)
    if expected_timeline_sha256 is not None:
        _hash(expected_timeline_sha256)
        require(pin == expected_timeline_sha256, 'External timeline digest mismatch')

    events = timeline['events']
    require(type(events) is list and len(events) <= 256, 'Invalid event list')
    previous = digest({'schema_version': TIMELINE_SCHEMA_VERSION,
                       'subject_sha256': timeline['subject_sha256']})
    previous_day = date.min
    communication, author, resolution = 'NOT_RECORDED', 'NOT_RECORDED', 'OPEN'
    withdrawn = False
    revision = None
    recheck = None
    before_withdrawal = 'OPEN'

    for index, event in enumerate(events, 1):
        fields(event, {'seq', 'previous_sha256', 'kind', 'on', 'actor_id', 'evidence_artifact', 'data'})
        integer(event['seq'], 1, 256)
        require(event['seq'] == index, 'Event sequence is not contiguous')
        _hash(event['previous_sha256'])
        require(event['previous_sha256'] == previous, 'Event chain mismatch')
        _identifier(event['actor_id'])
        text(event['kind'], 100)
        require(event['kind'] in KINDS, 'Unknown event kind')
        day = _iso_date(event['on'])
        require(previous_day <= day <= as_of, 'Events must be ordered and not future-dated')
        previous_day = day
        name = text(event['evidence_artifact'], 240)
        require(name in artifacts and artifacts[name].strip(), 'Missing or empty event evidence')
        kind, payload = event['kind'], event['data']
        require(not withdrawn or kind == 'CASE_REOPENED', 'Withdrawn case must be explicitly reopened')

        if kind == 'INQUIRY_RECORDED':
            fields(payload, {'note'})
            text(payload['note'], 4000)
            communication = 'INQUIRY_RECORDED_NOT_AUTHENTICATED'
        elif kind == 'AUTHOR_POSITION_RECORDED':
            fields(payload, {'position', 'note'})
            text(payload['note'], 4000)
            require(payload['position'] in ('agrees', 'disagrees', 'clarifies'), 'Unknown author position')
            author = payload['position'].upper() + '_RECORDED_NOT_AUTHENTICATED'
        elif kind == 'CORRECTION_NOTICE_RECORDED':
            fields(payload, {'revision_artifact', 'version'})
            text(payload['revision_artifact'], 240)
            text(payload['version'], 100)
            require(payload['revision_artifact'] in artifacts, 'Revision bytes missing')
            require(artifacts[payload['revision_artifact']].strip(), 'Revision bytes empty')
            revision = {
                'artifact': payload['revision_artifact'],
                'version': payload['version'],
                'sha256': case['artifacts'][payload['revision_artifact']],
            }
            recheck = None
            resolution = 'NOTICE_RECORDED_UNCHECKED'
        elif kind == 'REVISION_WITNESS_RECHECK':
            fields(payload, {'revision_sha256', 'formalization_artifact'})
            _hash(payload['revision_sha256'])
            require(revision is not None and payload['revision_sha256'] == revision['sha256'],
                    'Recheck must target the latest recorded revision')
            name = text(payload['formalization_artifact'], 240)
            require(name in artifacts, 'Revision formalization missing')
            spec = loads(artifacts[name])
            require(type(spec) is dict and spec.get('kind') == case['claim']['formalization']['kind'],
                    'Revision checker kind mismatch')
            recheck = check(spec, loads(artifacts[case['witness_artifact']]))
            resolution = {
                'REFUTED_FOR_FORMALIZATION': 'OLD_WITNESS_STILL_REFUTES_REVISION',
                'NO_REFUTATION_AT_WITNESS': 'OLD_WITNESS_NO_LONGER_REFUTES_REVISION',
                'INCONCLUSIVE_INTERVAL': 'REVISION_CHECK_INCONCLUSIVE',
            }[recheck['status']]
        elif kind == 'CASE_WITHDRAWN':
            fields(payload, {'reason'})
            text(payload['reason'], 4000)
            before_withdrawal = resolution
            resolution, withdrawn = 'WITHDRAWN_BY_OPERATOR', True
        elif kind == 'CASE_REOPENED':
            fields(payload, {'reason'})
            text(payload['reason'], 4000)
            require(withdrawn, 'Only a withdrawn case can be reopened')
            resolution, withdrawn = before_withdrawal, False
        previous = digest(event)

    return {
        'protocol': 'ResearchWitness-timeline/1.0',
        'subject_sha256': timeline['subject_sha256'],
        'timeline_sha256': pin,
        'externally_pinned': expected_timeline_sha256 is not None,
        'event_count': len(events),
        'chain_head_sha256': previous,
        'communication': communication,
        'author_position': author,
        'resolution': resolution,
        'latest_revision': revision,
        'revision_witness_result': recheck,
        'original_mathematical_result_changed': False,
        'correction_verified': False,
        'external_actions': 'OUT_OF_SCOPE',
        'warnings': [
            'Event hashes do not authenticate authors, sending, or publication.',
            'Author agreement, disagreement, and silence do not establish mathematical truth.',
            'A notice is not verification; an old witness failing is not proof a revision is globally correct.',
            'Revision formalization-to-source alignment is not machine-proved by ResearchWitness.',
        ],
    }


def evaluate_timeline(root: Path | str, timeline_path: Path | str, as_of: date,
                      expected_timeline_sha256: str | None = None) -> dict:
    case, artifacts = load_bundle(root)
    path = Path(timeline_path).absolute()
    timeline = loads(Bundle(path.parent).read(path.name, 2 * 1024 * 1024))
    return project(case, artifacts, timeline, as_of, expected_timeline_sha256)
