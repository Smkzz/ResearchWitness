"""Retained upstream 2x2 cases plus malformed-input and rounding regressions."""
from decimal import Inexact, ROUND_DOWN, localcontext
from fractions import Fraction
import random

import pytest

from researchwitness.paper_statistics import recompute_two_by_two

COMMON = dict(exposed_events=10, exposed_non_events=90, reference_events=20,
              reference_non_events=80, reference_group_explicit=True,
              timepoint_explicit=True, adjustment_status='unadjusted')


def check(**changes):
    return recompute_two_by_two(**(COMMON | {'measure': 'risk_ratio', 'reported': '0.5'} | changes))


def test_retained_rr_or_and_difference_cases():
    rr = check()
    assert rr['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert (rr['exact_numerator'], rr['exact_denominator']) == ('1', '2')
    assert check(measure='odds_ratio', reported='0.444')['status'] == 'CONSISTENT_WITH_ROUNDING'
    assert check(measure='difference_in_proportions', reported='-0.1')['status'] == 'CONSISTENT_WITH_ROUNDING'


def test_retained_mismatch_is_only_an_arithmetic_candidate():
    result = check(reported='0.8')
    assert result['status'] == 'ARITHMETIC_CANDIDATE'
    assert result['candidate']['reported'] == '0.8'
    assert 'paper_error_established' not in result


def test_retained_adjustment_and_zero_policy():
    assert check(adjustment_status='unknown')['status'] == 'UNSUPPORTED'
    assert check(exposed_non_events=0, measure='odds_ratio', reported='2')['reason'] == 'ZERO_CELL_POLICY_UNSPECIFIED'


def test_retained_half_up_boundary_and_count_limit():
    result = check(exposed_events=1, exposed_non_events=7, reference_events=0,
                   reference_non_events=8, measure='difference_in_proportions', reported='0.12')
    assert result['recomputed_at_display_precision'] == '0.13'
    assert result['status'] == 'ARITHMETIC_CANDIDATE'
    assert check(exposed_events=1_000_000_001)['reason'] == 'RESOURCE_LIMIT_EXCEEDED'


@pytest.mark.parametrize('value', [None, 1, False, [], {}, 0.5])
def test_nontext_display_abstains(value):
    assert check(reported=value)['reason'] == 'REPORTED_VALUE_OR_PRECISION_UNSUPPORTED'


@pytest.mark.parametrize('value', [1, 'yes', [], None, False])
@pytest.mark.parametrize('name', ['reference_group_explicit', 'timepoint_explicit'])
def test_truthy_context_cannot_become_explicit_context(name, value):
    assert check(**{name: value})['reason'] == 'REFERENCE_GROUP_OR_TIMEPOINT_UNSPECIFIED'


@pytest.mark.parametrize('value', [True, 0.5, None, -1, '10'])
def test_counts_are_nonnegative_integers_not_booleans(value):
    assert check(exposed_events=value)['reason'] == 'OPERANDS_MISSING_OR_INVALID'


@pytest.mark.parametrize('value', ['1e2', 'NaN', '0.123456789', '00.5', ' 0.5', '', 'x' * 33])
def test_unsupported_number_formats(value):
    assert check(reported=value)['status'] == 'UNSUPPORTED'


def test_zero_groups_unknown_measure_and_reference_risk():
    assert check(exposed_events=0, exposed_non_events=0)['reason'] == 'ZERO_GROUP_TOTAL'
    assert check(reference_events=0, reference_non_events=0)['reason'] == 'ZERO_GROUP_TOTAL'
    assert check(reference_events=0)['reason'] == 'ZERO_REFERENCE_RISK'
    assert check(measure='adjusted_odds_ratio')['reason'] == 'STATISTIC_TYPE_UNSUPPORTED'


def test_decimal_context_does_not_change_results_or_raise_inexact():
    expected = check(measure='odds_ratio', reported='0.5')
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        context.Emax = 1
        context.Emin = -1
        context.traps[Inexact] = True
        assert check(measure='odds_ratio', reported='0.5') == expected


def test_negative_half_tie_rounds_away_from_zero():
    result = check(exposed_events=0, exposed_non_events=8, reference_events=1,
                   reference_non_events=7, measure='difference_in_proportions', reported='-0.12')
    assert result['recomputed_at_display_precision'] == '-0.13'


def test_bounded_random_cases_against_independent_integer_rounding():
    rng = random.Random(20261024)
    for _ in range(100):
        a, b, c, d = [rng.randint(1, 1_000_000_000) for _ in range(4)]
        for measure, fraction in (
            ('risk_ratio', Fraction(a, a + b) / Fraction(c, c + d)),
            ('odds_ratio', Fraction(a * d, b * c)),
            ('difference_in_proportions', Fraction(a, a + b) - Fraction(c, c + d)),
        ):
            scaled = abs(fraction) * 10**8
            q, r = divmod(scaled.numerator, scaled.denominator)
            rounded = q + (2 * r >= scaled.denominator)
            sign = '-' if fraction < 0 else ''
            display = f'{sign}{rounded // 10**8}.{rounded % 10**8:08d}'
            result = check(exposed_events=a, exposed_non_events=b, reference_events=c,
                           reference_non_events=d, measure=measure, reported=display)
            assert result['status'] == 'CONSISTENT_WITH_ROUNDING'
            assert Fraction(int(result['exact_numerator']), int(result['exact_denominator'])) == fraction


def test_mutated_decimal_default_context_cannot_change_calculation(monkeypatch):
    from decimal import DefaultContext
    rr = dict(exposed_events=1, exposed_non_events=2, reference_events=1,
              reference_non_events=0, reported='0.33')
    odds = dict(exposed_events=100, exposed_non_events=1, reference_events=1,
                reference_non_events=100, reported='10000', measure='odds_ratio')
    expected_rr, expected_odds = check(**rr), check(**odds)
    monkeypatch.setitem(DefaultContext.traps, Inexact, True)
    monkeypatch.setattr(DefaultContext, 'Emax', 1)
    monkeypatch.setattr(DefaultContext, 'Emin', -1)
    monkeypatch.setattr(DefaultContext, 'clamp', 1)
    assert check(**rr) == expected_rr
    assert check(**odds) == expected_odds
