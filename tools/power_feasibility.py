"""Finite exact prospective power planning on hypothetical work-family outcomes.

No source papers, outcomes, held-out identities, new permissions, provider access,
actual preregistration, verified source labels or scientific power qualification.
This calculator only quantifies stated independent-family *assumptions*.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from math import comb
from pathlib import Path
import sys
from typing import Any

from tools import exact_family_analysis as exact
from tools import research_preregistration as study
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-development-power-scenario.v1"
REPORT_VERSION = "rw-development-power-feasibility.v1"
MAX_SCENARIO_BYTES = 32 * 1024
MAX_POSITIVE_FAMILIES = 256
MAX_NEGATIVE_FAMILIES = 2048


def require(condition: bool, diagnostic: str) -> None:
    vb.require(condition, diagnostic)


def fraction(value: Any, *, nonzero: bool = False) -> Fraction:
    require(type(value) is dict and set(value) == {"numerator", "denominator"},
            "SCENARIO_FRACTION_FIELDS")
    n, d = value["numerator"], value["denominator"]
    require(type(n) is int and type(d) is int and 0 <= n <= d
            and 1 <= d <= 10000, "SCENARIO_FRACTION_RANGE")
    require(not nonzero or n > 0, "SCENARIO_ZERO_FRACTION")
    return Fraction(n, d)


def validate_scenario(value: dict[str, Any]) -> dict[str, Any]:
    require(type(value) is dict and set(value) == {
        "schema_version", "partition", "candidate_only_positive_probability",
        "baseline_only_positive_probability", "target_primary_power",
        "negative_joint_no_alarm_probability", "max_positive_families",
        "max_negative_families", "assumptions_basis",
    }, "SCENARIO_FIELDS")
    require(value["schema_version"] == VERSION, "SCENARIO_VERSION")
    require(value["partition"] == "hypothetical_development_only",
            "PROTECTED_OR_EMPIRICAL_PARTITION_FORBIDDEN")
    cand = fraction(value["candidate_only_positive_probability"])
    base = fraction(value["baseline_only_positive_probability"])
    require(cand + base <= 1, "POSITIVE_DISCORDANCE_PROBABILITIES")
    power = fraction(value["target_primary_power"], nonzero=True)
    require(power < 1, "VACUOUS_OR_IMPOSSIBLE_POWER_TARGET")
    fraction(value["negative_joint_no_alarm_probability"])
    require(type(value["max_positive_families"]) is int
            and 1 <= value["max_positive_families"] <= MAX_POSITIVE_FAMILIES,
            "POSITIVE_PLANNING_LIMIT")
    require(type(value["max_negative_families"]) is int
            and 1 <= value["max_negative_families"] <= MAX_NEGATIVE_FAMILIES,
            "NEGATIVE_PLANNING_LIMIT")
    require(value["assumptions_basis"] == "invented_not_estimated_from_source",
            "EMPIRICAL_ESTIMATE_NOT_AUTHENTICATED")
    return value


def _critical_wins(max_d: int, alpha: Fraction) -> list[int]:
    """Minimum wins for exact P(Binomial(d, 1/2) >= wins) < alpha."""
    critical = []
    for d in range(max_d + 1):
        cumulative = 0
        chosen = d + 1
        for wins in range(d, -1, -1):
            cumulative += comb(d, wins)
            if cumulative * alpha.denominator < alpha.numerator * (1 << d):
                chosen = wins
            else:
                break
        critical.append(chosen)
    return critical


def _alternative_win_tails(max_d: int, p: Fraction) -> list[list[Fraction]]:
    """Exact P(W >= k | D=d) for every discordance count and threshold."""
    distributions: list[list[Fraction]] = []
    for d in range(max_d + 1):
        if p == 0:
            row = [Fraction(int(k == 0)) for k in range(d + 2)]
        elif p == 1:
            row = [Fraction(int(k <= d)) for k in range(d + 2)]
        else:
            row = [Fraction(0)] * (d + 2)
            term = p**d
            accumulator = term
            row[d] = accumulator
            for k in range(d - 1, -1, -1):
                term = term * (k + 1) * (1 - p) / ((d - k) * p)
                accumulator += term
                row[k] = accumulator
            require(accumulator == 1, "POWER_PROBABILITY_CONSERVATION")
        distributions.append(row)
    return distributions


def _practical_minimum_wins(discordant: int, n: int, gain: Fraction) -> int:
    # 2*w - d >= n*gain; take the exact integer ceiling.
    numerator = discordant * gain.denominator + n * gain.numerator
    return -(-numerator // (2 * gain.denominator))


def _power(n: int, candidate_only: Fraction, baseline_only: Fraction,
           practical_gain: Fraction, critical: list[int],
           conditional_tails: list[list[Fraction]]) -> Fraction:
    """Unconditional exact chance of both predeclared positive test gates.

    For independent families: D ~ Bin(n, a+b); W|D ~ Bin(D, a/(a+b)).
    No independence between the paired methods themselves is assumed.
    """
    q = candidate_only + baseline_only
    if q == 0:
        return Fraction(0)
    if q == 1:
        threshold = max(critical[n], _practical_minimum_wins(n, n, practical_gain))
        return conditional_tails[n][threshold]
    probability_d = (1 - q)**n
    accepted = Fraction(0)
    for d in range(n + 1):
        threshold = max(critical[d], _practical_minimum_wins(d, n, practical_gain))
        if threshold <= d:
            accepted += probability_d * conditional_tails[d][threshold]
        if d < n:
            probability_d = (
                probability_d * (n - d) * q / ((d + 1) * (1 - q))
            )
    require(0 <= accepted <= 1, "POWER_OUT_OF_RANGE")
    return accepted


def _zero_zero_safety_minimum(alpha: Fraction, harm_margin: Fraction,
                              floor: int, ceiling: int) -> int | None:
    """Exact first n where 1-(alpha/2)**(1/n) <= margin.

    The inequality is equivalently (1-margin)**n <= alpha/2,
    without floating-point logarithms or an approximate confidence endpoint.
    """
    if harm_margin == 0 or floor > ceiling:
        return None
    probability = Fraction(1)
    survive = 1 - harm_margin
    half_alpha = alpha / 2
    for n in range(1, ceiling + 1):
        probability *= survive
        if n >= floor and probability <= half_alpha:
            return n
    return None


def plan(registration: dict[str, Any], scenario: dict[str, Any], *,
         expected_registration_sha256: str) -> dict[str, Any]:
    """Return numerical feasibility diagnostics, never scientific clearance."""
    study.validate(registration,
                   expected_registration_sha256=expected_registration_sha256)
    validate_scenario(scenario)
    alpha = study._fraction(registration["analysis"]["primary_alpha"])
    safety_alpha = study._fraction(registration["analysis"]["safety_alpha"])
    gain = study._fraction(registration["analysis"]["minimum_practical_gain"])
    margin = study._fraction(registration["analysis"]["maximum_false_alarm_increase"],
                             allow_zero=True)
    positive_floor = registration["sampling"]["minimum_positive_families"]
    negative_floor = registration["sampling"]["minimum_negative_families"]
    positive_cap = scenario["max_positive_families"]
    negative_cap = scenario["max_negative_families"]
    a = fraction(scenario["candidate_only_positive_probability"])
    b = fraction(scenario["baseline_only_positive_probability"])
    desired_power = fraction(scenario["target_primary_power"])
    silence = fraction(scenario["negative_joint_no_alarm_probability"])

    positive_n: int | None = None
    positive_power: Fraction | None = None
    at_preceding_power: Fraction | None = None
    if positive_floor <= positive_cap:
        q = a + b
        p = a / q if q > 0 else Fraction(0)
        critical = _critical_wins(positive_cap, alpha)
        tails = _alternative_win_tails(positive_cap, p)
        # An exact discrete rejection region need not have monotone power in n.
        # Therefore search every n in increasing order, never binary search.
        previous: Fraction | None = None
        for n in range(positive_floor, positive_cap + 1):
            observed_power = _power(n, a, b, gain, critical, tails)
            if observed_power >= desired_power:
                positive_n = n
                positive_power = observed_power
                at_preceding_power = previous
                break
            previous = observed_power

    negative_n = _zero_zero_safety_minimum(
        safety_alpha, margin, negative_floor, negative_cap
    )
    chance_no_negative_alarms: Fraction | None = (
        silence**negative_n if negative_n is not None else None
    )
    return {
        "schema_version": REPORT_VERSION,
        "classification": "HYPOTHETICAL_EXACT_POWER_PLANNING_NOT_SCIENTIFIC_EVIDENCE",
        "registration_sha256": vb.commitment(registration),
        "scenario_sha256": vb.commitment(scenario),
        "positive_discordance_assumptions": {
            "candidate_only": scenario["candidate_only_positive_probability"],
            "baseline_only": scenario["baseline_only_positive_probability"],
            "neither_or_both_aggregate": {
                "numerator": (1-a-b).numerator,
                "denominator": (1-a-b).denominator,
            },
        },
        "primary_alpha": registration["analysis"]["primary_alpha"],
        "safety_alpha": registration["analysis"]["safety_alpha"],
        "practical_detection_gain": registration["analysis"]["minimum_practical_gain"],
        "false_alarm_harm_margin": registration["analysis"]["maximum_false_alarm_increase"],
        "target_power": scenario["target_primary_power"],
        "minimum_positive_families_for_assumed_primary_power": positive_n,
        "achieved_primary_power_decimal_lower": (
            exact._decimal_outward(positive_power.numerator,
                                   positive_power.denominator, upper=False)
            if positive_power is not None else None
        ),
        "preceding_sample_primary_power_decimal_lower": (
            exact._decimal_outward(at_preceding_power.numerator,
                                   at_preceding_power.denominator, upper=False)
            if at_preceding_power is not None else None
        ),
        "minimum_negative_families_in_zero_zero_alarm_scenario": negative_n,
        "probability_of_zero_alarms_in_either_arm_decimal_lower": (
            exact._decimal_outward(chance_no_negative_alarms.numerator,
                                   chance_no_negative_alarms.denominator, upper=False)
            if chance_no_negative_alarms is not None else None
        ),
        "illustrative_total_distinct_families": (
            positive_n + negative_n
            if positive_n is not None and negative_n is not None else None
        ),
        "design_status": (
            "hypothetical_thresholds_reachable_within_search_limits"
            if positive_n is not None and negative_n is not None
            else "hypothetical_thresholds_not_reached_within_search_limits"
        ),
        "power_and_safety_jointly_verified": False,
        "actual_source_label_evidence_supplied": False,
        "actual_sample_size_power_verified": False,
        "independent_work_family_sampling_verified": False,
        "registration_frozen_before_outcomes": False,
        "protected_data_accessed": False,
        "scientific_superiority_established": False,
        "methodology": {
            "positive": "exact_multinomial_reduced_to_binomial_discordance",
            "selection": "linear_first_pass_without_monotonicity_assumption",
            "safety": "zero_zero_alarm_bonferroni_cp_necessary_scenario_only",
            "negative_zero_probability": "joint_silent_event_iid_over_hypothetical_negative_families",
            "arithmetic": "python_fraction_integer_exact",
            "reported_decimals": "12_place_outward_lower_bounds",
            "maximum_positive_families_searched": positive_cap,
            "maximum_negative_families_searched": negative_cap,
        },
        "limitations": [
            "This is a mathematical what-if calculation, not actual observed study power.",
            "Assumed per-family positive discordance and negative silence probabilities are invented.",
            "The zero/zero false-alarm safety minimum is not the safety test's power.",
            "Probability of all negative families emitting no alarms is a lower bound on the safety-pass chance only under the stated independent-family assumptions.",
            "Positive and negative strata independence, source labels, licence and provenance are unverified.",
            "The development draft is not independently pre-outcome preregistered and no holdout was run.",
            "The legacy 15-work requirement is not a substitute for a powered confirmatory research design.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--expected-registration-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        input_registration = vb.parse_document(
            read_regular(args.registration, study.MAX_INPUT_BYTES)
        )
        input_scenario = vb.parse_document(
            read_regular(args.scenario, MAX_SCENARIO_BYTES)
        )
        result = plan(
            input_registration, input_scenario,
            expected_registration_sha256=args.expected_registration_sha256,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        diagnostic = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": diagnostic}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
