"""Exact, bounded family-level statistical diagnostics for exposed paired runs.

This is NOT a qualified or sealed scientific evaluator. It reuses the validated
development receipt scorer and a *draft* preregistration. The input labels,
source correspondence, provenance, reviewer independence and timing of pins
remain unverified. Results cannot authorize a superiority claim.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from math import comb
from pathlib import Path
import sys
from typing import Any

from tools import paired_development_comparison as paired
from tools import research_preregistration as registration
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-development-exact-family-analysis.v1"
MAX_FAMILIES_PER_ENDPOINT = 2048
DYADIC_BITS = 40
DENOMINATOR = 1 << DYADIC_BITS
DECIMAL_PLACES = 12
DECIMAL_SCALE = 10**DECIMAL_PLACES


def _fraction(value: dict[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _decimal_outward(numerator: int, denominator: int, *, upper: bool) -> str:
    """Render an exact rational outward to a fixed 12-place decimal."""
    vb.require(denominator > 0, "ZERO_DENOMINATOR")
    scaled = ((-(-numerator * DECIMAL_SCALE // denominator)) if upper
              else (numerator * DECIMAL_SCALE // denominator))
    sign = "-" if scaled < 0 else ""
    whole, part = divmod(abs(scaled), DECIMAL_SCALE)
    return f"{sign}{whole}.{part:0{DECIMAL_PLACES}d}"


def _tail_count(n: int, k: int, successes: int, total: int) -> int:
    """Exact numerator of Binomial(n, successes/total) P(X <= k)."""
    if k < 0:
        return 0
    if k >= n or successes == 0:
        return total**n
    misses = total - successes
    if misses == 0:
        return 0
    term = misses**n
    result = term
    for index in range(k):
        # Each term is an exact integer. Never use floating-point binomial CDFs.
        term = term * (n - index) * successes // ((index + 1) * misses)
        result += term
    return result


def _one_sided_cp_harm_upper(*, candidate_alarms: int,
                              baseline_alarms: int,
                              negative_families: int,
                              safety_alpha: Fraction) -> tuple[int, int]:
    """Conservative one-sided Bonferroni CP difference on a dyadic grid.

    Candidate upper: smallest grid point with P(X <= k) <= alpha/2.
    Baseline lower: largest grid point with P(X >= k) <= alpha/2.
    Therefore U_candidate - L_baseline is never understated by grid error.
    """
    n = negative_families
    vb.require(0 <= candidate_alarms <= n and 0 <= baseline_alarms <= n
               and 1 <= n <= MAX_FAMILIES_PER_ENDPOINT, "STAT_INPUT_COUNTS")
    tail = safety_alpha / 2
    total_power = DENOMINATOR**n

    def lower_tail_within(k: int, candidate: int) -> bool:
        return (_tail_count(n, k, candidate, DENOMINATOR) * tail.denominator
                <= tail.numerator * total_power)

    def upper_tail_within(k: int, candidate: int) -> bool:
        return ((total_power - _tail_count(n, k - 1, candidate, DENOMINATOR))
                * tail.denominator <= tail.numerator * total_power)

    if candidate_alarms == n:
        upper = DENOMINATOR
    else:
        low, high = 0, DENOMINATOR
        while high - low > 1:
            mid = (low + high) // 2
            if lower_tail_within(candidate_alarms, mid):
                high = mid
            else:
                low = mid
        upper = high

    if baseline_alarms == 0:
        lower = 0
    else:
        low, high = 0, DENOMINATOR
        while high - low > 1:
            mid = (low + high) // 2
            if upper_tail_within(baseline_alarms, mid):
                low = mid
            else:
                high = mid
        lower = low
    return upper, lower


def _exact_p_value(wins: int, losses: int) -> tuple[int, int]:
    """P(Binomial(wins + losses, .5) >= wins) under the paired null."""
    vb.require(type(wins) is int and type(losses) is int
               and wins >= 0 and losses >= 0
               and wins + losses <= MAX_FAMILIES_PER_ENDPOINT,
               "STAT_DISCORDANCE_COUNTS")
    n = wins + losses
    return sum(comb(n, i) for i in range(wins, n + 1)), 1 << n


def analyze(
    study: dict[str, Any],
    registry: dict[str, Any],
    baseline_protocol: dict[str, Any],
    baseline_run: dict[str, Any],
    candidate_protocol: dict[str, Any],
    candidate_run: dict[str, Any],
    *,
    expected_registration_sha256: str,
    expected_registry_sha256: str,
    expected_baseline_protocol_sha256: str,
    expected_candidate_protocol_sha256: str,
) -> dict[str, Any]:
    """Replay the exact paired ledger; report ONLY development-stage diagnostics."""
    registration.validate(
        study, expected_registration_sha256=expected_registration_sha256,
    )
    report = paired.compare(
        registry, baseline_protocol, baseline_run,
        candidate_protocol, candidate_run,
        expected_registry_sha256=expected_registry_sha256,
        expected_baseline_protocol_sha256=expected_baseline_protocol_sha256,
        expected_candidate_protocol_sha256=expected_candidate_protocol_sha256,
    )
    arms = study["arms"]
    resources = study["resources"]
    vb.require(
        baseline_protocol["implementation_sha256"] == arms[0]["implementation_sha256"]
        and candidate_protocol["implementation_sha256"] == arms[1]["implementation_sha256"],
        "STUDY_ARM_IMPLEMENTATION_MISMATCH",
    )
    for proto in (baseline_protocol, candidate_protocol):
        vb.require(
            proto["max_elapsed_ms"] == resources["max_elapsed_ms_per_work"]
            and proto["max_calls"] == resources["max_calls_per_work"]
            and proto["max_cost_micro_eur"] == resources["max_cost_micro_eur_per_work"],
            "STUDY_RESOURCE_BUDGET_MISMATCH",
        )
    pos = report["positive_detection"]
    neg = report["negative_false_alarm"]
    npos = pos["independent_family_count_declared"]
    nneg = neg["independent_family_count_declared"]
    nneg_relationships = sum(
        row["eligible"] and row["label"] == "negative"
        for row in registry["works"]
    )
    count_adequate = (
        npos >= study["sampling"]["minimum_positive_families"]
        and nneg >= study["sampling"]["minimum_negative_families"]
        and nneg_relationships >= study["sampling"]["minimum_negative_relationships"]
    )
    complete = (
        report["status"] == "complete"
        and report["unresolved_family_count"] == 0
        and pos["paired_unknown"] == 0
        and neg["paired_unknown"] == 0
    )
    computable = (0 < npos <= MAX_FAMILIES_PER_ENDPOINT
                  and 0 < nneg <= MAX_FAMILIES_PER_ENDPOINT)
    metrics: dict[str, Any] | None = None
    numeric_gates = "not_evaluated"
    if complete and computable:
        positive_table = pos["paired_table"]
        negative_table = neg["paired_table"]
        wins = positive_table["candidate_only"]
        losses = positive_table["baseline_only"]
        p_num, p_den = _exact_p_value(wins, losses)
        primary_alpha = _fraction(study["analysis"]["primary_alpha"])
        safety_alpha = _fraction(study["analysis"]["safety_alpha"])
        harm_margin = _fraction(study["analysis"]["maximum_false_alarm_increase"])
        minimum_gain = _fraction(study["analysis"]["minimum_practical_gain"])
        candidate_alarms = negative_table["both"] + negative_table["candidate_only"]
        baseline_alarms = negative_table["both"] + negative_table["baseline_only"]
        upper, lower = _one_sided_cp_harm_upper(
            candidate_alarms=candidate_alarms, baseline_alarms=baseline_alarms,
            negative_families=nneg, safety_alpha=safety_alpha,
        )
        delta = wins - losses
        significance = p_num * primary_alpha.denominator < p_den * primary_alpha.numerator
        practical = Fraction(delta, npos) >= minimum_gain
        safety = Fraction(upper - lower, DENOMINATOR) <= harm_margin
        thresholds_met = significance and practical and safety
        numeric_gates = (
            "met_on_unverified_development_data" if thresholds_met and count_adequate
            else "not_met_or_sample_inadequate"
        )
        metrics = {
            "positive_families": npos,
            "positive_paired_discordant": wins + losses,
            "candidate_only_positive": wins,
            "baseline_only_positive": losses,
            "positive_gain_candidate_minus_baseline": {
                "numerator": delta, "denominator": npos,
            },
            "exact_one_sided_discordance_p_value_upper_decimal": (
                _decimal_outward(p_num, p_den, upper=True)
            ),
            "primary_significant_against_declared_alpha": significance,
            "minimum_practical_gain_met": practical,
            "negative_families": nneg,
            "candidate_negative_alarm_families": candidate_alarms,
            "baseline_negative_alarm_families": baseline_alarms,
            "candidate_one_sided_cp_upper_decimal": (
                _decimal_outward(upper, DENOMINATOR, upper=True)
            ),
            "baseline_one_sided_cp_lower_decimal": (
                _decimal_outward(lower, DENOMINATOR, upper=False)
            ),
            "bonferroni_cp_harm_upper_decimal": (
                _decimal_outward(upper - lower, DENOMINATOR, upper=True)
            ),
            "safety_margin_met": safety,
            "precision": {
                "binomial_tails": "exact_integer_arithmetic",
                "confidence_endpoints": "outward_dyadic_brackets",
                "dyadic_bits": DYADIC_BITS,
                "decimal_places": DECIMAL_PLACES,
            },
        }

    reasons = []
    if not complete:
        reasons.append("MISSING_OR_UNRESOLVED_ELIGIBLE_FAMILIES")
    if not computable:
        reasons.append("NO_ENDPOINT_DATA_OR_SIZE_LIMIT")
    if not count_adequate:
        reasons.append("DECLARED_MINIMUM_SAMPLE_NOT_MET")
    if metrics is not None and numeric_gates != "met_on_unverified_development_data":
        reasons.append("STATISTICAL_OR_PRACTICAL_THRESHOLD_NOT_MET")
    return {
        "schema_version": VERSION,
        "classification": "DEVELOPMENT_DIAGNOSTICS_NOT_SCIENTIFIC_VALIDATION",
        "registration_sha256": vb.commitment(study),
        "paired_report_sha256": vb.commitment(report),
        "registry_sha256": vb.commitment(registry),
        "baseline_protocol_sha256": vb.commitment(baseline_protocol),
        "candidate_protocol_sha256": vb.commitment(candidate_protocol),
        "baseline_run_sha256": vb.commitment(baseline_run),
        "candidate_run_sha256": vb.commitment(candidate_run),
        "registered_work_count": report["registered_work_count"],
        "positive_families_declared": npos,
        "negative_families_declared": nneg,
        "negative_relationships_declared": nneg_relationships,
        "excluded_families_declared": report["excluded_family_count"],
        "unresolved_families_declared": report["unresolved_family_count"],
        "incomplete_paired_positive_families": pos["paired_unknown"],
        "incomplete_paired_negative_families": neg["paired_unknown"],
        "complete_declared_endpoints": complete,
        "declared_minimum_sample_met": count_adequate,
        "numeric_thresholds": numeric_gates,
        "metrics": metrics,
        "reasons": reasons,
        "registration_frozen_by_independent_custodian": False,
        "independent_source_labels_verified": False,
        "family_independence_verified": False,
        "source_and_certificate_replayed_by_this_analysis": False,
        "protected_holdout_evaluated": False,
        "scientific_superiority_established": False,
        "limitations": [
            "Registry labels, identities, eligibility, family partitions and run receipts are unverified declarations.",
            "Hash equality cannot demonstrate pre-outcome registration, ownership or actual acquisition.",
            "An exact statistical calculation on incorrect labels does not establish source or scientific truth.",
            "At least one unresolved or incomplete eligible family makes the statistical gates inconclusive.",
            "All results are development-exposed. A numerical pass never promotes a protected evaluation.",
            "Clopper-Pearson bounds assume independently sampled work families, not independently sampled rows.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("registration", "registry", "baseline-protocol", "baseline-run",
                 "candidate-protocol", "candidate-run"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("registration", "registry", "baseline-protocol",
                 "candidate-protocol"):
        parser.add_argument("--expected-" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        inputs = {
            name: vb.parse_document(
                read_regular(getattr(args, name.replace("-", "_")), vb.MAX_BYTES)
            )
            for name in ("registration", "registry", "baseline-protocol",
                         "baseline-run", "candidate-protocol", "candidate-run")
        }
        result = analyze(
            inputs["registration"], inputs["registry"],
            inputs["baseline-protocol"], inputs["baseline-run"],
            inputs["candidate-protocol"], inputs["candidate-run"],
            expected_registration_sha256=args.expected_registration_sha256,
            expected_registry_sha256=args.expected_registry_sha256,
            expected_baseline_protocol_sha256=args.expected_baseline_protocol_sha256,
            expected_candidate_protocol_sha256=args.expected_candidate_protocol_sha256,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
