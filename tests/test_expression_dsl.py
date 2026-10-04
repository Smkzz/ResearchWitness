"""The rational-expression checker evaluates a small closed AST with exact arithmetic."""
from datetime import date
from pathlib import Path

import pytest

from researchwitness.checkers import check
from researchwitness.capsule import evaluate
from researchwitness.strict import Invalid


ROOT = Path(__file__).resolve().parents[1]


def const(value):
    return {'op': 'const', 'value': value}


def var(name='x'):
    return {'op': 'var', 'name': name}


def domain(lower='1', upper='3', lower_closed=False, upper_closed=True):
    return {'x': {'lower': lower, 'upper': upper,
                  'lower_closed': lower_closed, 'upper_closed': upper_closed}}


def spec(expression, upper_bound='2'):
    return {'kind': 'rational_expression_upper_bound', 'domain': domain(),
            'expression': expression, 'upper_bound': upper_bound}


def witness(x='2'):
    return {'kind': 'rational_expression_upper_bound', 'point': {'x': x}}


def quotient_counterexample():
    return {
        'op': 'div',
        'left': {
            'op': 'sub',
            'left': {'op': 'pow', 'base': var(), 'exponent': 2},
            'right': const('1'),
        },
        'right': {
            'op': 'sub', 'left': var(), 'right': const('1'),
        },
    }


def test_rational_function_counterexample_is_exact():
    result = check(spec(quotient_counterexample()), witness())
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['left']['lower_exact'] == result['left']['upper_exact'] == '3'
    assert result['detail'] == {'point': {'x': '2'}, 'value_exact': '3', 'expression_nodes': 8}


def test_exact_value_at_or_below_bound_is_not_a_refutation():
    expression = {'op': 'div', 'left': var(),
                  'right': {'op': 'sub', 'left': var(), 'right': const('1')}}
    result = check(spec(expression, upper_bound='2'), witness())
    assert result['status'] == 'NO_REFUTATION_AT_WITNESS'
    assert result['left']['lower_exact'] == '2'


def test_division_by_zero_fails_closed():
    zero = {'op': 'sub', 'left': var(), 'right': var()}
    with pytest.raises(Invalid, match='division by zero'):
        check(spec({'op': 'div', 'left': const('1'), 'right': zero}), witness())


@pytest.mark.parametrize('expression', [
    {'op': 'call', 'name': 'system', 'args': [const('1')]},
    {'op': 'import', 'name': 'os'},
    {'op': 'var', 'name': 'x', 'attribute': '__class__'},
])
def test_calls_imports_attributes_and_unknown_ops_are_rejected(expression):
    with pytest.raises(Invalid):
        check(spec(expression), witness())


def test_unknown_variable_and_point_outside_domain_are_rejected():
    with pytest.raises(Invalid, match='Unknown rational-expression variable'):
        check(spec(var('y')), witness())
    with pytest.raises(Invalid, match='Witness outside domain'):
        check(spec(var()), witness('1'))


def test_node_and_depth_budgets_are_enforced():
    expression = const('0')
    for _ in range(4):
        expression = {'op': 'add', 'args': [expression] * 8}
    with pytest.raises(Invalid, match='node budget'):
        check(spec(expression), witness())

    expression = const('0')
    for _ in range(21):
        expression = {'op': 'neg', 'arg': expression}
    with pytest.raises(Invalid, match='depth budget'):
        check(spec(expression), witness())


def test_power_and_exact_fraction_size_are_bounded():
    with pytest.raises(Invalid, match='Integer outside allowed bounds'):
        check(spec({'op': 'pow', 'base': var(), 'exponent': 13}), witness())

    expression = {'op': 'pow', 'base': const('9' * 64), 'exponent': 12}
    expression = {'op': 'pow', 'base': expression, 'exponent': 4}
    with pytest.raises(Invalid, match='resource limit'):
        check(spec(expression), witness())


def test_example_bundle_replays():
    report = evaluate(ROOT / 'examples' / 'rational-expression', date(2026, 10, 4))
    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    result = report['formalization_result']
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['value_exact'] == '3'
