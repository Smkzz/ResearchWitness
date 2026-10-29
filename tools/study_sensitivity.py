"""RW-04H: exact hypothetical joint bounds and bounded attrition sensitivity.

Source-free development planning only. A quota probability is not scientific
power; all binomial calculations assume independent retention within a stratum.
This module reads no articles, credentials, network, or protected evaluation data.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import re
from typing import Sequence

REPORT_VERSION = "rw-study-sensitivity-hypothetical.v1"
MAX_ENROLLED = 512
_PROBABILITY = re.compile(r"(?:0(?:\.[0-9]{1,6})?|1(?:\.0{1,6})?)\Z")


def probability(raw: str) -> Fraction:
    """Read a literal decimal probability without binary-float rounding."""
    if not _PROBABILITY.fullmatch(raw):
        raise ValueError("Probability must be decimal 0..1 with at most 6 places")
    return Fraction(Decimal(raw))


def binomial_tail(enrolled: int, required: int, retained: Fraction) -> Fraction:
    """Exact P(Binomial(enrolled, retained) >= required)."""
    if not (0 <= required <= enrolled <= MAX_ENROLLED):
        raise ValueError("Invalid bounded enrollment or required family count")
    if not 0 <= retained <= 1:
        raise ValueError("Invalid retention probability")
    if required == 0:
        return Fraction(1)
    if retained == 0:
        return Fraction(0)
    if retained == 1:
        return Fraction(1)
    # Start at P(X=n) and walk down to the required successes; each ratio
    # is exact, with no tail cancellation or underflow from tiny probabilities.
    mass = retained**enrolled
    cumulative = mass
    for k in range(enrolled, required, -1):
        mass *= Fraction(k, enrolled - k + 1) * (1 - retained) / retained
        cumulative += mass
    return cumulative


def joint_bounds(*marginals: Fraction) -> tuple[Fraction, Fraction]:
    """Sharp Fréchet bounds; no joint independence required."""
    if not marginals or any(not 0 <= p <= 1 for p in marginals):
        raise ValueError("At least one valid marginal probability is required")
    return max(Fraction(0), sum(marginals) - len(marginals) + 1), min(marginals)


def minimum_enrollment(
    required: int,
    retained: Fraction,
    confidence: Fraction,
    *,
    maximum: int = MAX_ENROLLED,
) -> int | None:
    """Smallest bounded n with enough complete cases, or None if infeasible."""
    if not 1 <= required <= maximum <= MAX_ENROLLED:
        raise ValueError("Required family count or maximum is out of range")
    if not 0 <= retained <= 1 or not 0 < confidence <= 1:
        raise ValueError("Retention/confidence probability is out of range")
    if binomial_tail(maximum, required, retained) < confidence:
        return None
    left, right = required, maximum
    while left < right:
        middle = (left + right) // 2
        if binomial_tail(middle, required, retained) >= confidence:
            right = middle
        else:
            left = middle + 1
    return left


def _decimal(x: Fraction) -> str:
    with localcontext() as context:
        context.prec = 42
        return format(Decimal(x.numerator) / Decimal(x.denominator), ".12g")


def analyze(
    positive_pass: Fraction,
    safety_pass: Fraction,
    positive_required: int,
    safety_required: int,
    positive_missing: Fraction,
    safety_missing: Fraction,
    joint_quota_confidence: Fraction,
) -> dict[str, object]:
    """No empirical claim: hypothetical endpoint and retention marginals."""
    if not all(0 <= p <= 1 for p in (
        positive_pass, safety_pass, positive_missing, safety_missing
    )) or not 0 < joint_quota_confidence < 1:
        raise ValueError("Probabilities must lie in their stated ranges")
    if not all(1 <= n <= MAX_ENROLLED for n in (
        positive_required, safety_required
    )):
        raise ValueError("Required complete family counts exceed bounds")

    lower, upper = joint_bounds(positive_pass, safety_pass)
    # Bonferroni allocation: each marginal quota failure at most (1-g)/2.
    side_confidence = (1 + joint_quota_confidence) / 2
    groups = []
    for kind, needed, missing in (
        ("positive", positive_required, positive_missing),
        ("negative", safety_required, safety_missing),
    ):
        retained = 1 - missing
        enrolled = minimum_enrollment(needed, retained, side_confidence)
        groups.append({
            "stratum": kind,
            "required_complete_families": needed,
            "missing_probability": _decimal(missing),
            "enrolled_for_joint_quota_target": enrolled,
            "quota_probability": _decimal(binomial_tail(enrolled, needed, retained))
            if enrolled is not None else None,
            "exact_quota_at_no_overenrollment": _decimal(retained**needed),
        })
    both_feasible = all(g["enrolled_for_joint_quota_target"] is not None
                        for g in groups)
    if both_feasible:
        qpos, qneg = (binomial_tail(
            int(g["enrolled_for_joint_quota_target"]),
            int(g["required_complete_families"]),
            1 - (positive_missing if i == 0 else safety_missing),
        ) for i, g in enumerate(groups))
        quota_min, quota_max = joint_bounds(qpos, qneg)
    else:
        quota_min = quota_max = None

    return {
        "schema_version": REPORT_VERSION,
        "partition": "hypothetical_development_only",
        "endpoint_pass_marginals": {
            "positive": _decimal(positive_pass),
            "safety": _decimal(safety_pass),
            "frechet_joint_lower": _decimal(lower),
            "frechet_joint_upper": _decimal(upper),
            "joint_if_independent_only": _decimal(positive_pass * safety_pass),
        },
        "quota_plan": {
            "joint_confidence_target": _decimal(joint_quota_confidence),
            "per_stratum_confidence_target": _decimal(side_confidence),
            "groups": groups,
            "joint_quota_lower_without_cross_stratum_independence": (
                _decimal(quota_min) if quota_min is not None else None
            ),
            "joint_quota_upper_without_cross_stratum_independence": (
                _decimal(quota_max) if quota_max is not None else None
            ),
            "joint_quota_feasible_within_512": both_feasible,
        },
        "limitations": [
            "No source-based power or real observed missingness is estimated.",
            "Within-stratum family retention must be independent for binomial quotas.",
            "Missingness may depend on study outcomes; do not multiply quotas by power.",
            "No across-strata independence is assumed for the Fréchet bounds.",
            "Published marginal percentages are rounded illustrative inputs.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-pass", required=True)
    parser.add_argument("--safety-pass", required=True)
    parser.add_argument("--positive-target", type=int, required=True)
    parser.add_argument("--safety-target", type=int, required=True)
    parser.add_argument("--positive-missing", required=True)
    parser.add_argument("--safety-missing", required=True)
    parser.add_argument("--joint-quota-confidence", default="0.95")
    args = parser.parse_args(argv)
    try:
        result = analyze(
            probability(args.positive_pass), probability(args.safety_pass),
            args.positive_target, args.safety_target,
            probability(args.positive_missing), probability(args.safety_missing),
            probability(args.joint_quota_confidence),
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
