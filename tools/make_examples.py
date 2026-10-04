"""Generate explicitly synthetic v1 examples with no reviewer or approver objects."""
from copy import deepcopy
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from researchwitness.strict import byte_hash


def write_case(root, case, data):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    case['artifacts'] = {name: byte_hash(content) for name, content in data.items()}
    for name, content in data.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (root / 'case.json').write_text(json.dumps(case, indent=2) + '\n', encoding='utf-8')
    return case


def base_case():
    statement = 'For every x in [0,1], x^2 <= 1/2.'
    case = {
        'schema_version': '1.0',
        'case_id': 'synthetic-bound',
        'artifacts': {},
        'source': {
            'artifact': 'source.txt',
            'text_artifact': 'source.txt',
            'identifier': 'synthetic:polynomial-example',
            'version': 'v1',
            'capture_status': 'synthetic',
            'correction_check': {
                'checked_on': '2026-10-04',
                'status': 'none_found',
                'evidence_artifact': 'correction-check.txt',
            },
        },
        'claim': {
            'id': 'C1',
            'statement': statement,
            'scope': 'Synthetic claim C1 in v1 only.',
            'assumptions': ['x is real and lies in the stated closed interval.'],
            'excluded_claims': [
                'This fixture is not a real paper or an independent discovery.',
                'No global optimum or paper-level error is asserted.',
            ],
            'anchor': {'offset': 0, 'quote': statement},
            'formalization': {
                'kind': 'polynomial_upper_bound',
                'domain': {
                    'x': {
                        'lower': '0',
                        'upper': '1',
                        'lower_closed': True,
                        'upper_closed': True,
                    }
                },
                'terms': [{'coefficient': '1', 'powers': {'x': 2}}],
                'upper_bound': '1/2',
            },
        },
        'witness_artifact': 'witness.json',
        'unresolved_objections': [],
        'disclosure': 'private',
    }
    data = {
        'source.txt': (statement + '\nSYNTHETIC, NOT A PUBLISHED PAPER.\n').encode(),
        'correction-check.txt': b'Synthetic fixture v1: this is test metadata, not an external search.\n',
        'witness.json': json.dumps({'kind': 'polynomial_upper_bound', 'point': {'x': '1'}}).encode(),
    }
    return case, data


def main():
    out = Path(__file__).resolve().parents[1] / 'examples'
    generated = (
        'counterexample', 'no-finding', 'already-corrected', 'unverified-source',
        'open-objection', 'graph-chromatic-lower-bound',
    )
    for name in generated:
        child = out / name
        if child.is_dir():
            import shutil
            shutil.rmtree(child)

    case, data = base_case()
    write_case(out / 'counterexample', case, data)

    for name in ('no-finding', 'already-corrected', 'unverified-source', 'open-objection'):
        case, data = base_case()
        case['case_id'] = 'synthetic-' + name
        if name == 'no-finding':
            case['claim']['formalization']['upper_bound'] = '1'
            statement = 'For every x in [0,1], x^2 <= 1.'
            case['claim']['statement'] = statement
            case['claim']['anchor']['quote'] = statement
            data['source.txt'] = statement.encode()
        elif name == 'already-corrected':
            case['source']['correction_check']['status'] = 'present'
        elif name == 'unverified-source':
            case['source']['capture_status'] = 'unverified'
        elif name == 'open-objection':
            case['unresolved_objections'] = ['Example objection: the transcription may omit a restriction.']
        write_case(out / name, case, data)

    statement = 'The explicitly listed graph has chromatic number at least 3.'
    case, data = base_case()
    case['case_id'] = 'synthetic-graph-chromatic-bound'
    case['source']['identifier'] = 'synthetic:graph-chromatic-bound'
    case['claim']['statement'] = statement
    case['claim']['scope'] = 'Only the listed three-vertex simple graph and the claimed lower bound are formalized.'
    case['claim']['assumptions'] = ['The graph is finite, simple, and undirected.']
    case['claim']['excluded_claims'] = [
        'This fixture is not a real paper or an independent discovery.',
        'No search for the graph chromatic number is performed.',
    ]
    case['claim']['anchor']['quote'] = statement
    data['correction-check.txt'] = b'Synthetic graph fixture: no external correction search was performed.\n'
    case['claim']['formalization'] = {
        'kind': 'finite_graph_chromatic_lower_bound',
        'vertices': ['a', 'b', 'c'],
        'edges': [['a', 'b'], ['b', 'c']],
        'minimum_colors': 3,
    }
    source_text = (
        statement + '\n'
        'Fixture graph: a--b--c. This is a synthetic example, not a published result.\n'
    )
    data['source.txt'] = source_text.encode()
    data['witness.json'] = json.dumps({
        'kind': 'finite_graph_chromatic_lower_bound',
        'coloring': {'a': 'red', 'b': 'blue', 'c': 'red'},
    }, sort_keys=True, separators=(',', ':')).encode()
    write_case(out / 'graph-chromatic-lower-bound', case, data)


if __name__ == '__main__':
    main()
