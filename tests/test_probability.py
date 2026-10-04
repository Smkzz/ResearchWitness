"""Focused tests for bounded exact finite-PMF arithmetic."""
from datetime import date
from fractions import Fraction as F
from pathlib import Path

import pytest

from researchwitness import Invalid
from researchwitness.checkers import check
from researchwitness.capsule import evaluate


ROOT = Path(__file__).resolve().parents[1]


def four_cell_pmf():
    return {
        'kind': 'finite_pmf_bound',
        'atoms': [
            {'assignment': {'coin': 'H', 'weather': 'sun'}, 'probability': '1/4'},
            {'assignment': {'coin': 'H', 'weather': 'rain'}, 'probability': '1/4'},
            {'assignment': {'coin': 'T', 'weather': 'sun'}, 'probability': '1/4'},
            {'assignment': {'coin': 'T', 'weather': 'rain'}, 'probability': '1/4'},
        ],
    }


def probability_spec(relation='at_most', bound='2/3'):
    return {
        'kind': 'finite_pmf_bound',
        'operation': 'probability',
        'domains': {'coin': ['H', 'T'], 'weather': ['sun', 'rain']},
        'event': [{'coin': 'H'}, {'weather': 'sun'}],
        'relation': relation,
        'bound': bound,
    }


def test_event_probability_unions_overlapping_clauses_exactly_once():
    result = check(probability_spec(), four_cell_pmf())

    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['operation'] == 'event_probability'
    assert F(result['detail']['quantity_exact']) == F(3, 4)
    assert F(result['detail']['signed_margin_exact']) == F(1, 12)
    assert result['detail']['positive_mass_atom_count'] == 4
    assert result['detail']['empirical_or_generalized_conclusion'] == 'NOT_ESTABLISHED_BY_THIS_CHECKER'
    assert 'population/generalized conclusions are not established' in result['scope']


@pytest.mark.parametrize('relation,bound', [('at_most', '3/4'), ('at_least', '1/2')])
def test_event_probability_equal_or_within_bound_does_not_refute(relation, bound):
    result = check(probability_spec(relation, bound), four_cell_pmf())
    assert result['status'] == 'NO_REFUTATION_AT_WITNESS'
    assert F(result['detail']['quantity_exact']) == F(3, 4)


def test_event_probability_supports_lower_bound_refutation():
    result = check(probability_spec('at_least', '4/5'), four_cell_pmf())
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['relation'] == 'at_least'
    assert F(result['detail']['signed_margin_exact']) == F(-1, 20)


def test_expectation_uses_complete_payoff_table_and_exact_masses():
    spec = {
        'kind': 'finite_pmf_bound',
        'operation': 'expectation',
        'domains': {'outcome': ['bad', 'good']},
        'payoffs': [
            {'assignment': {'outcome': 'bad'}, 'value': '-2'},
            {'assignment': {'outcome': 'good'}, 'value': '2'},
        ],
        'relation': 'at_most',
        'bound': '0',
    }
    witness = {
        'kind': 'finite_pmf_bound',
        'atoms': [
            {'assignment': {'outcome': 'bad'}, 'probability': '1/4'},
            {'assignment': {'outcome': 'good'}, 'probability': '3/4'},
        ],
    }

    result = check(spec, witness)
    assert result['status'] == 'REFUTED_FOR_FORMALIZATION'
    assert result['detail']['operation'] == 'expected_payoff'
    assert result['detail']['quantity_exact'] == '1'
    assert result['detail']['payoff_states'] == 2


@pytest.mark.parametrize('mutation,match', [
    ('mass_sum', 'sum exactly to one'),
    ('negative_mass', 'masses must lie'),
    ('duplicate_atom', 'Duplicate PMF support atom'),
    ('outside_domain', 'outside declared domain'),
    ('probability_bound', 'Probability bound'),
])
def test_malformed_pmf_or_target_fails_closed(mutation, match):
    spec = probability_spec()
    witness = four_cell_pmf()
    if mutation == 'mass_sum':
        witness['atoms'][0]['probability'] = '1/8'
    elif mutation == 'negative_mass':
        witness['atoms'][0]['probability'] = '-1/4'
    elif mutation == 'duplicate_atom':
        witness['atoms'][1]['assignment'] = dict(witness['atoms'][0]['assignment'])
    elif mutation == 'outside_domain':
        witness['atoms'][0]['assignment']['coin'] = 'sideways'
    else:
        spec['bound'] = '2'

    with pytest.raises(Invalid, match=match):
        check(spec, witness)


def test_expectation_rejects_incomplete_or_duplicate_payoff_tables():
    spec = {
        'kind': 'finite_pmf_bound',
        'operation': 'expectation',
        'domains': {'x': ['a', 'b']},
        'payoffs': [{'assignment': {'x': 'a'}, 'value': '0'},
                    {'assignment': {'x': 'a'}, 'value': '1'}],
        'relation': 'at_least',
        'bound': '0',
    }
    witness = {'kind': 'finite_pmf_bound', 'atoms': [{'assignment': {'x': 'a'}, 'probability': '1'}]}
    with pytest.raises(Invalid, match='Duplicate payoff assignment'):
        check(spec, witness)


def test_sample_space_resource_limit_is_checked_before_expansion():
    spec = {
        'kind': 'finite_pmf_bound',
        'operation': 'probability',
        'domains': {f'x{i}': ['a', 'b', 'c', 'd'] for i in range(5)},
        'event': [],
        'relation': 'at_most',
        'bound': '0',
    }
    witness = {'kind': 'finite_pmf_bound', 'atoms': []}
    with pytest.raises(Invalid, match='sample-space limit exceeded'):
        check(spec, witness)


def test_synthetic_probability_example_replays_as_scoped_evidence():
    report = evaluate(ROOT / 'examples' / 'finite-pmf-probability', date(2026, 10, 4))

    assert report['decision'] == 'FORMALIZATION_COUNTEREXAMPLE_VERIFIED'
    assert report['formalization_result']['detail']['quantity_exact'] == '3/4'
    assert report['paper_error_established'] is False
    assert 'SYNTHETIC_SOURCE' in {item['code'] for item in report['context_flags']}
