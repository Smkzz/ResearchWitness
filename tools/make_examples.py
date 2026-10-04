"""Generate explicitly synthetic v1 examples with no reviewer or approver objects."""
from copy import deepcopy
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from researchwitness.strict import byte_hash
from researchwitness.checkers import check


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


def write_checker_example(out, name, statement, formalization, witness):
    case, data = base_case()
    case['case_id'] = 'synthetic-' + name
    case['source']['identifier'] = 'synthetic:' + name
    case['claim']['statement'] = statement
    case['claim']['scope'] = f'Synthetic {name} checker fixture only.'
    case['claim']['assumptions'] = [
        'The supplied formalization and witness are exactly the inputs shown.'
    ]
    case['claim']['excluded_claims'] = [
        'This fixture is synthetic and is not evidence about a real publication.',
        'No source-to-formalization alignment or paper-level conclusion is asserted.',
    ]
    case['claim']['anchor']['quote'] = statement
    case['claim']['formalization'] = formalization
    data['source.txt'] = (
        statement + '\nSYNTHETIC CHECKER FIXTURE, NOT A PUBLISHED CLAIM.\n'
    ).encode()
    data['correction-check.txt'] = b'Synthetic fixture: no external correction search was performed.\n'
    data['witness.json'] = json.dumps(witness, sort_keys=True, separators=(',', ':')).encode()
    write_case(out / name, case, data)


def build_capability_examples(out):
    directories = {
        'scalar_radical_comparison': 'scalar-radical-comparison',
        'polynomial_upper_bound': 'counterexample',
        'rational_expression_upper_bound': 'rational-expression',
        'uc_binary_upper_bound': 'uc-binary-upper-bound',
        'finite_field_polynomial_residue': 'finite-field-polynomial-residue',
        'finite_field_quadratic_quartic_residue_rule': 'finite-field-quadratic-quartic-residue-rule',
        'finite_map_fixed_point': 'finite-map-fixed-point',
        'finite_graph_chromatic_lower_bound': 'graph-chromatic-lower-bound',
        'finite_pmf_bound': 'finite-pmf-probability',
        'modular_linear_system': 'modular-linear-system',
    }
    examples = {}
    for kind, directory in directories.items():
        root = out / directory
        case = json.loads((root / 'case.json').read_text(encoding='utf-8'))
        witness = json.loads((root / case['witness_artifact']).read_text(encoding='utf-8'))
        formalization = case['claim']['formalization']
        result = check(formalization, witness)
        if result['status'] != 'REFUTED_FOR_FORMALIZATION':
            raise RuntimeError(f'Capability example did not replay as expected: {kind}')
        examples[kind] = {
            'statement': case['claim']['statement'],
            'scope': case['claim']['scope'],
            'assumptions': case['claim']['assumptions'],
            'excluded_claims': case['claim']['excluded_claims'],
            'formalization': formalization,
            'witness': witness,
            'expected_status': result['status'],
            'expected_result': result,
        }
        if 'value_exact' in result.get('detail', {}):
            examples[kind]['expected_value_exact'] = result['detail']['value_exact']
    return examples


def write_capability_examples(out):
    examples = build_capability_examples(out)
    target = Path(__file__).resolve().parents[1] / 'researchwitness' / 'capability_examples.json'
    target.write_text(json.dumps(examples, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main():
    out = Path(__file__).resolve().parents[1] / 'examples'
    generated = (
        'counterexample', 'no-finding', 'already-corrected', 'unverified-source',
        'open-objection', 'graph-chromatic-lower-bound', 'scalar-radical-comparison',
        'uc-binary-upper-bound', 'finite-field-polynomial-residue',
        'finite-field-quadratic-quartic-residue-rule', 'finite-map-fixed-point',
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

    write_checker_example(
        out, 'scalar-radical-comparison',
        'In the supplied exact comparison, sqrt(2) is at most 1.',
        {'kind': 'scalar_radical_comparison',
         'left': {'constant': '0', 'terms': [{'coefficient': '1', 'radicand': '2'}]},
         'upper_bound': {'constant': '1', 'terms': []}},
        {'kind': 'scalar_radical_comparison'},
    )
    write_checker_example(
        out, 'uc-binary-upper-bound',
        'For the supplied binary-source strategy, the functional is at most -19.',
        {'kind': 'uc_binary_upper_bound', 'functional': 'uc_sqrt_penalty_v1',
         'upper_bound': {'constant': '-19', 'terms': []}},
        {'kind': 'uc_binary_upper_bound', 'gamma': ['1', '0', '0', '0'],
         'alpha': ['1', '0', '0', '0'], 'b0': [['0'] * 4 for _ in range(4)]},
    )
    field_polynomial = {
        'kind': 'finite_field_polynomial_residue', 'prime': 3,
        'variables': ['x'], 'parameters': ['c'],
        'terms': [
            {'coefficient': 1, 'powers': {'x': 2}},
            {'coefficient': -1, 'powers': {'c': 1}},
        ],
        'point_count_adjustment': 0, 'modulus': 2, 'allowed_residues': [0],
    }
    write_checker_example(
        out, 'finite-field-polynomial-residue',
        'For c = 0 over F_3, the solution-count residue modulo 2 is 0.',
        field_polynomial,
        {'kind': 'finite_field_polynomial_residue', 'parameters': {'c': 0}},
    )
    write_checker_example(
        out, 'finite-field-quadratic-quartic-residue-rule',
        'For c = 1 over F_5, the quadratic/quartic class predicts count residue 1 modulo 2.',
        {'kind': 'finite_field_quadratic_quartic_residue_rule', 'prime': 5,
         'variables': ['x'], 'parameters': ['c'],
         'terms': [
             {'coefficient': 1, 'powers': {'x': 2}},
             {'coefficient': -1, 'powers': {'c': 1}},
         ],
         'point_count_adjustment': 0, 'modulus': 2,
         'classification_parameter': 'c',
         'expected_residues': {
             'quartic_residue': [1], 'quadratic_nonquartic': [0],
             'quadratic_nonresidue': [0],
         }},
        {'kind': 'finite_field_quadratic_quartic_residue_rule', 'parameters': {'c': 1}},
    )
    write_checker_example(
        out, 'finite-map-fixed-point',
        'The supplied finite self-map has a fixed point.',
        {'kind': 'finite_map_fixed_point', 'universe': ['0', '1'],
         'conclusion': 'has_fixed_point'},
        {'kind': 'finite_map_fixed_point', 'mapping': {'0': '1', '1': '0'}},
    )
    write_capability_examples(out)


if __name__ == '__main__':
    main()
