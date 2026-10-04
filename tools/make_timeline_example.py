"""Generate a synthetic correction lifecycle; no actual authors or messages."""
from copy import deepcopy
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.make_examples import base_case, write_case
from researchwitness.capsule import subject_digest
from researchwitness.resolution import TIMELINE_SCHEMA_VERSION
from researchwitness.strict import digest


def main():
    root = Path(__file__).resolve().parents[1] / 'examples' / 'correction-history'
    case, data = base_case()
    case['case_id'] = 'synthetic-correction-history'
    revised = deepcopy(case['claim']['formalization'])
    revised['upper_bound'] = '1'
    data.update({
        'revision-v2.txt': b'SYNTHETIC v2: For every x in [0,1], x^2 <= 1.\n',
        'revision-formalization.json': json.dumps(revised).encode(),
        'synthetic-correspondence.txt': b'Entirely fictional event evidence. No actual messages or authors.\n',
    })
    write_case(root, case, data)
    subject = subject_digest(case)
    timeline = {'schema_version': TIMELINE_SCHEMA_VERSION, 'subject_sha256': subject, 'events': []}
    previous = digest({'schema_version': TIMELINE_SCHEMA_VERSION, 'subject_sha256': subject})
    for i, (kind, payload) in enumerate([
        ('INQUIRY_RECORDED', {'note': 'Fictional inquiry, not sent.'}),
        ('AUTHOR_POSITION_RECORDED', {'position': 'agrees', 'note': 'Fictional agreement; not proof.'}),
        ('CORRECTION_NOTICE_RECORDED', {'revision_artifact': 'revision-v2.txt', 'version': 'synthetic-v2'}),
        ('REVISION_WITNESS_RECHECK', {
            'revision_sha256': case['artifacts']['revision-v2.txt'],
            'formalization_artifact': 'revision-formalization.json',
        }),
    ], 1):
        event = {
            'seq': i,
            'previous_sha256': previous,
            'kind': kind,
            'on': '2026-10-04',
            'actor_id': 'synthetic-operator',
            'evidence_artifact': 'synthetic-correspondence.txt',
            'data': payload,
        }
        timeline['events'].append(event)
        previous = digest(event)
    (root / 'timeline.json').write_text(json.dumps(timeline, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
