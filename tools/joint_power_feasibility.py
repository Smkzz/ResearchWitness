"""Exact joint positive/safety study power under SOURCE-FREE fictional assumptions.

Development planning only: no scientifically grounded rates, original articles,
external preregistration, independent labels or qualified protected evaluation.
For a fixed proposed pair of sample sizes, enumerate the *paired* negative
alarm distribution and use the unchanged RW-04E conservative safety criterion.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from math import lcm
from pathlib import Path
import sys
from typing import Any

from tools import exact_family_analysis as exact
from tools import power_feasibility as power
from tools import research_preregistration as registration
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-joint-power-scenario.v1"
REPORT_VERSION = "rw-development-joint-power-feasibility.v1"
MAX_INPUT_BYTES = 32 * 1024
MAX_POSITIVE_FAMILIES = 256
MAX_NEGATIVE_FAMILIES = 200
MAX_COMMON_DENOMINATOR = 10_000
NEGATIVE_KEYS = (
    "neither_alarm", "candidate_only_alarm",
    "baseline_only_alarm", "both_alarm",
)


def require(condition: bool, code: str) -> None:
    vb.require(condition, code)


def validate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    require(type(scenario) is dict and set(scenario) == {
        "schema_version", "partition", "positive_families", "negative_families",
        "candidate_only_positive_probability",
        "baseline_only_positive_probability", "negative_joint_outcomes",
        "target_joint_power", "assumptions_basis", "family_sampling_model",
    }, "JOINT_SCENARIO_FIELDS")
    require(scenario["schema_version"] == VERSION, "JOINT_SCENARIO_VERSION")
    require(scenario["partition"] == "hypothetical_development_only",
            "JOINT_PROTECTED_PARTITION_FORBIDDEN")
    require(scenario["assumptions_basis"] == "invented_not_estimated_from_source",
            "JOINT_EMPIRICAL_BASIS_NOT_AUTHENTICATED")
    require(scenario["family_sampling_model"] ==
            "iid_within_strata_independent_positive_and_negative",
            "JOINT_INDEPENDENCE_ASSUMPTION_REQUIRED")
    np = scenario["positive_families"]
    nn = scenario["negative_families"]
    require(type(np) is int and 1 <= np <= MAX_POSITIVE_FAMILIES,
            "JOINT_POSITIVE_FAMILY_LIMIT")
    require(type(nn) is int and 1 <= nn <= MAX_NEGATIVE_FAMILIES,
            "JOINT_NEGATIVE_FAMILY_LIMIT")
    a = power.fraction(scenario["candidate_only_positive_probability"])
    b = power.fraction(scenario["baseline_only_positive_probability"])
    require(a + b <= 1, "JOINT_POSITIVE_PROBABILITY_SUM")
    target = power.fraction(scenario["target_joint_power"], nonzero=True)
    require(target < 1, "JOINT_POWER_TARGET")
    negative = scenario["negative_joint_outcomes"]
    require(type(negative) is dict and set(negative) == set(NEGATIVE_KEYS),
            "JOINT_NEGATIVE_OUTCOME_FIELDS")
    rates = [power.fraction(negative[key]) for key in NEGATIVE_KEYS]
    require(sum(rates, Fraction(0)) == 1, "JOINT_NEGATIVE_PROBABILITY_SUM")
    common = lcm(*(rate.denominator for rate in rates))
    require(common <= MAX_COMMON_DENOMINATOR, "JOINT_PROBABILITY_DENOMINATOR_LIMIT")
    return scenario


def _negative_safety_pass_probability(
    negative_families: int,
    outcome_probabilities: list[Fraction],
    alpha: Fraction,
    margin: Fraction,
) -> tuple[Fraction, Fraction]:
    """Exact multinomial arm-count probability with conservative CP inversion.

    Work-family outcomes are (no alarm, candidate only, baseline only, both).
    Integer DP accumulates the bivariate marginal alarm count distribution
    without erroneously assuming the two arms are independent.
    """
    n = negative_families
    base = lcm(*(rate.denominator for rate in outcome_probabilities))
    weights = tuple(int(rate * base) for rate in outcome_probabilities)
    require(sum(weights) == base, "JOINT_NEGATIVE_WEIGHTS")
    # Separate one-sided Clopper-Pearson marginal bounds; the Bonferroni
    # difference is exactly the same conservative criterion as RW-04E.
    cp = [
        exact._one_sided_cp_harm_upper(
            candidate_alarms=count,
            baseline_alarms=count,
            negative_families=n,
            safety_alpha=alpha,
        )
        for count in range(n + 1)
    ]
    candidate_uppers = [upper for upper, _lower in cp]
    baseline_lowers = [lower for _upper, lower in cp]

    # dp[c][b] = integer mass * base**n after n hypothetical families.
    dp = [[1]]
    neither, candidate, baseline, both = weights
    for i in range(n):
        following = [[0] * (i + 2) for _ in range(i + 2)]
        for cand_count, row in enumerate(dp):
            for base_count, value in enumerate(row):
                if value == 0:
                    continue
                following[cand_count][base_count] += value * neither
                following[cand_count + 1][base_count] += value * candidate
                following[cand_count][base_count + 1] += value * baseline
                following[cand_count + 1][base_count + 1] += value * both
        dp = following
    total = base**n
    require(sum(sum(row) for row in dp) == total,
            "JOINT_PROBABILITY_MASS_NOT_CONSERVED")
    favorable = 0
    grid = exact.DENOMINATOR
    for c, row in enumerate(dp):
        upper = candidate_uppers[c]
        for b, value in enumerate(row):
            if value and Fraction(upper - baseline_lowers[b], grid) <= margin:
                favorable += value
    return Fraction(favorable, total), outcome_probabilities[0]**n


def plan(
    draft: dict[str, Any], scenario: dict[str, Any], *,
    expected_registration_sha256: str,
) -> dict[str, Any]:
    registration.validate(
        draft, expected_registration_sha256=expected_registration_sha256,
    )
    validate_scenario(scenario)
    pos = scenario["positive_families"]
    neg = scenario["negative_families"]
    require(
        pos >= draft["sampling"]["minimum_positive_families"],
        "JOINT_POSITIVE_BELOW_REGISTERED_MINIMUM",
    )
    require(
        neg >= draft["sampling"]["minimum_negative_families"],
        "JOINT_NEGATIVE_BELOW_REGISTERED_MINIMUM",
    )
    analysis = draft["analysis"]
    primary_alpha = registration._fraction(analysis["primary_alpha"])
    safety_alpha = registration._fraction(analysis["safety_alpha"])
    gain = registration._fraction(analysis["minimum_practical_gain"])
    margin = registration._fraction(analysis["maximum_false_alarm_increase"],
                                    allow_zero=True)
    a = power.fraction(scenario["candidate_only_positive_probability"])
    b = power.fraction(scenario["baseline_only_positive_probability"])
    q = a + b
    p = a / q if q else Fraction(0)
    critical = power._critical_wins(pos, primary_alpha)
    tails = power._alternative_win_tails(pos, p)
    primary_power = power._power(pos, a, b, gain, critical, tails)

    rates = [
        power.fraction(scenario["negative_joint_outcomes"][key])
        for key in NEGATIVE_KEYS
    ]
    safety_power, all_silent = _negative_safety_pass_probability(
        neg, rates, safety_alpha, margin,
    )
    # This product is exact ONLY under the scenario's distinct, independent
    # positive and negative families. Neither independence nor rates are
    # established from observed scientific work.
    combined = primary_power * safety_power
    threshold = power.fraction(scenario["target_joint_power"], nonzero=True)
    result = {
        "schema_version": REPORT_VERSION,
        "classification": "HYPOTHETICAL_PAIRED_JOINT_POWER_NOT_EMPIRICAL_EVIDENCE",
        "study_draft_sha256": vb.commitment(draft),
        "scenario_sha256": vb.commitment(scenario),
        "positive_families": pos,
        "negative_families": neg,
        "hypothetical_distinct_family_total": pos + neg,
        "primary_success_probability_decimal_lower": exact._decimal_outward(
            primary_power.numerator, primary_power.denominator, upper=False,
        ),
        "paired_negative_safety_pass_probability_decimal_lower": exact._decimal_outward(
            safety_power.numerator, safety_power.denominator, upper=False,
        ),
        "both_endpoints_success_probability_decimal_lower": exact._decimal_outward(
            combined.numerator, combined.denominator, upper=False,
        ),
        "zero_negative_alarms_probability_decimal_lower": exact._decimal_outward(
            all_silent.numerator, all_silent.denominator, upper=False,
        ),
        "target_joint_power": scenario["target_joint_power"],
        "hypothetical_joint_target_met": combined >= threshold,
        "statistical_method": {
            "primary": "exact_binomial_mixture_of_paired_discordance_and_practical_gain",
            "safety": "exact_bivariate_multinomial_alarm_counts_bonferroni_cp",
            "safety_interval_grid": "outward_40_bit_dyadic",
            "combined": "product_of_stratum_powers_under_explicit_hypothetical_independence",
            "probability_arithmetic": "exact_python_integer_and_fraction",
            "decimal_display": "12_place_outward_lower_bounds",
            "negative_family_cap": MAX_NEGATIVE_FAMILIES,
        },
        "observed_discordance_probabilities_authenticated": False,
        "negative_joint_distribution_empirically_validated": False,
        "family_independence_verified": False,
        "negative_relationship_count_qualified": False,
        "source_label_provenance_verified": False,
        "actual_sample_size_power_verified": False,
        "chronological_preregistration_established": False,
        "protected_holdout_accessed": False,
        "scientific_superiority_established": False,
        "limitations": [
            "Joint negative alarms are modeled as paired outcomes; no arm independence is assumed.",
            "The four negative outcome rates and two positive discordance rates are invented.",
            "Separate independent sampled positive and negative work families are hypothetical.",
            "The calculation does not model source failures, unresolved labels, clustering or label misclassification.",
            "Actual negative relationship count and completeness are not established by family counts.",
            "Outward Clopper-Pearson grid can only conservatively reduce reported safety pass probability.",
            "No actual review, prospective freeze, scientific conclusion, rights or protected custody is established.",
        ],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--expected-registration-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        draft = vb.parse_document(
            read_regular(args.registration, registration.MAX_INPUT_BYTES)
        )
        scenario = vb.parse_document(
            read_regular(args.scenario, MAX_INPUT_BYTES)
        )
        response = plan(
            draft, scenario,
            expected_registration_sha256=args.expected_registration_sha256,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(response))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
