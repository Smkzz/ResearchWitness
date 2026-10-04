from datetime import date
from pathlib import Path

import pytest

from researchwitness import Invalid, evaluate
from researchwitness.checkers import capabilities, check

KIND = 'finite_graph_chromatic_lower_bound'
ROOT = Path(__file__).resolve().parents[1]


def graph_pair():
    formalization = {
        'kind': KIND,
        'vertices': ['a', 'b', 'c'],
        'edges': [['a', 'b'], ['b', 'c']],
        'minimum_colors': 3,
    }
    witness = {
        'kind': KIND,
        'coloring': {'a': 'red', 'b': 'blue', 'c': 'red'},
    }
    return formalization, witness


def test_proper_coloring_refutes_a_chromatic_lower_bound():
    formalization, witness = graph_pair()
    result = check(formalization, witness)
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['predicate'] == 'chromatic_number_at_least_minimum_colors'
    assert result['detail'] == {
        'vertex_count': 3,
        'edge_count': 2,
        'minimum_colors_claimed': 3,
        'colors_used': 2,
        'color_classes': {'blue': ['b'], 'red': ['a', 'c']},
    }


def test_coloring_using_at_least_the_claimed_number_does_not_refute():
    formalization, witness = graph_pair()
    formalization['minimum_colors'] = 2
    result = check(formalization, witness)
    assert result['status'] == 'NO_REFUTATION_AT_WITNESS'
    assert result['detail']['colors_used'] == 2


@pytest.mark.parametrize('mutation', [
    'self-loop', 'reversed-duplicate-edge', 'unknown-endpoint', 'duplicate-vertex',
    'missing-color', 'improper-coloring', 'wrong-kind', 'extra-formalization-field',
    'boolean-lower-bound', 'control-character-label', 'long-color-label',
])
def test_malformed_graph_or_coloring_fails_closed(mutation):
    formalization, witness = graph_pair()
    if mutation == 'self-loop':
        formalization['edges'] = [['a', 'a']]
    elif mutation == 'reversed-duplicate-edge':
        formalization['edges'] = [['a', 'b'], ['b', 'a']]
    elif mutation == 'unknown-endpoint':
        formalization['edges'] = [['a', 'missing']]
    elif mutation == 'duplicate-vertex':
        formalization['vertices'].append('a')
    elif mutation == 'missing-color':
        witness['coloring'].pop('c')
    elif mutation == 'improper-coloring':
        witness['coloring']['b'] = 'red'
    elif mutation == 'wrong-kind':
        witness['kind'] = 'finite_map_fixed_point'
    elif mutation == 'extra-formalization-field':
        formalization['claim'] = 'chromatic_number_at_least'
    elif mutation == 'boolean-lower-bound':
        formalization['minimum_colors'] = True
    elif mutation == 'control-character-label':
        formalization['vertices'][0] = 'a\nb'
        witness['coloring'] = {'a\nb': 'red', 'b': 'blue', 'c': 'red'}
    elif mutation == 'long-color-label':
        witness['coloring']['a'] = 'x' * 65

    with pytest.raises(Invalid):
        check(formalization, witness)


def test_graph_and_coloring_limits_are_enforced_before_iteration():
    formalization, witness = graph_pair()
    formalization['vertices'] = [f'v{i}' for i in range(257)]
    witness['coloring'] = {}
    with pytest.raises(Invalid, match='vertex list'):
        check(formalization, witness)

    formalization, witness = graph_pair()
    formalization['edges'] = [['a', 'b']] * 8193
    with pytest.raises(Invalid, match='edge list'):
        check(formalization, witness)


def test_graph_capability_states_exact_limits_and_no_optimization_search():
    capability = next(item for item in capabilities() if item['kind'] == KIND)
    assert 'proper coloring' in capability['proves']
    assert '256 vertices' in capability['limits']
    assert '8,192 edges' in capability['limits']
    assert 'does not search' in capability['limits']


def test_graph_example_replays_through_the_capsule_report():
    report = evaluate(ROOT / 'examples' / 'graph-chromatic-lower-bound', date(2026, 10, 4))
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['paper_error_established'] is False
    assert report['formalization_result']['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert report['formalization_result']['detail']['colors_used'] == 2
