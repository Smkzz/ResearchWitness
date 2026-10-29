"""Source-free RW-04H mathematical regression checks."""
from fractions import Fraction as F

import pytest

from tools.study_sensitivity import (
    analyze, binomial_tail, joint_bounds, minimum_enrollment, probability,
)


def test_decimal_parser_is_exact_and_bounded():
    assert probability("0.8028") == F(2007, 2500)
    assert probability("1.000000") == 1
    for invalid in ("-0.1", "1.01", "0.00000001", "NaN", "1e-1", " 0.5"):
        with pytest.raises(ValueError):
            probability(invalid)


def test_exact_binomial_tail_and_edge_cases():
    assert binomial_tail(2, 1, F(1, 2)) == F(3, 4)
    assert binomial_tail(3, 2, F(1, 2)) == F(1, 2)
    assert binomial_tail(3, 3, F(9, 10)) == F(729, 1000)
    assert binomial_tail(2, 0, F(0)) == 1
    assert binomial_tail(2, 1, F(0)) == 0
    assert binomial_tail(2, 1, F(1)) == 1
    with pytest.raises(ValueError):
        binomial_tail(513, 1, F(1, 2))


def test_frechet_not_product_and_multiple_events():
    assert joint_bounds(F(4, 5), F(2, 5)) == (F(1, 5), F(2, 5))
    assert joint_bounds(F(1, 2), F(1, 2), F(1, 2)) == (F(0), F(1, 2))
    with pytest.raises(ValueError):
        joint_bounds()


def test_smallest_enrollment_at_exact_boundary():
    assert minimum_enrollment(2, F(1, 2), F(1, 2), maximum=8) == 3
    assert minimum_enrollment(2, F(1), F(99, 100), maximum=8) == 2
    assert minimum_enrollment(2, F(0), F(1, 2), maximum=8) is None
    assert minimum_enrollment(2, F(1, 2), F(1), maximum=8) is None


def test_exposed_hypothetical_scenario_no_empirical_claims():
    report = analyze(F(8028, 10000), F(4217, 10000), 129, 86,
                     F(1, 10), F(1, 10), F(95, 100))
    endpoints = report["endpoint_pass_marginals"]
    assert endpoints["frechet_joint_lower"] == "0.2245"
    assert endpoints["frechet_joint_upper"] == "0.4217"
    assert endpoints["joint_if_independent_only"] == "0.33854076"
    quota = report["quota_plan"]
    assert quota["per_stratum_confidence_target"] == "0.975"
    assert [g["enrolled_for_joint_quota_target"] for g in quota["groups"]] == [152, 102]
    assert float(quota["joint_quota_lower_without_cross_stratum_independence"]) > 0.95
    assert report["partition"] == "hypothetical_development_only"
    assert any("do not multiply" in note for note in report["limitations"])


def test_no_fake_result_when_quota_infeasible():
    report = analyze(F(1, 2), F(1, 2), 129, 86, F(1), F(1), F(95, 100))
    assert report["quota_plan"]["joint_quota_feasible_within_512"] is False
    assert report["quota_plan"]["joint_quota_lower_without_cross_stratum_independence"] is None


def test_probability_bounds_for_rejected_inputs():
    with pytest.raises(ValueError):
        analyze(F(2), F(1, 2), 129, 86, F(0), F(0), F(95, 100))
    with pytest.raises(ValueError):
        analyze(F(1, 2), F(1, 2), 0, 86, F(0), F(0), F(95, 100))
    with pytest.raises(ValueError):
        analyze(F(1, 2), F(1, 2), 129, 86, F(0), F(0), F(1))
