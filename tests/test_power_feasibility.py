"""Exact synthetic power design tests: no real sources or sealed outcomes."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import power_feasibility as power
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "examples/synthetic-study-registration/draft.json"
SCENARIO = ROOT / "examples/synthetic-study-registration/power-scenario.json"


def inputs():
    return (
        json.loads(DRAFT.read_text(encoding="utf-8")),
        json.loads(SCENARIO.read_text(encoding="utf-8")),
    )


def evaluate(study=None, scenario=None):
    registered, assumed = inputs()
    if study is not None:
        registered = study
    if scenario is not None:
        assumed = scenario
    return power.plan(
        registered, assumed,
        expected_registration_sha256=vb.commitment(registered),
    )


def test_exact_discordance_power_and_zero_zero_safety_design_example():
    out = evaluate()
    assert out["schema_version"] == power.REPORT_VERSION
    assert out["positive_discordance_assumptions"]["neither_or_both_aggregate"] == {
        "numerator": 13, "denominator": 20,
    }
    assert out["minimum_positive_families_for_assumed_primary_power"] == 129
    assert out["achieved_primary_power_decimal_lower"] == "0.802810397513"
    assert out["preceding_sample_primary_power_decimal_lower"] == "0.799259445807"
    assert out["minimum_negative_families_in_zero_zero_alarm_scenario"] == 86
    assert out["illustrative_total_distinct_families"] == 215
    assert out["probability_of_zero_alarms_in_either_arm_decimal_lower"] == (
        "0.175971570312"
    )
    assert out["design_status"] == "hypothetical_thresholds_reachable_within_search_limits"
    assert all(out[field] is False for field in (
        "power_and_safety_jointly_verified", "actual_source_label_evidence_supplied",
        "actual_sample_size_power_verified", "independent_work_family_sampling_verified",
        "registration_frozen_before_outcomes", "protected_data_accessed",
        "scientific_superiority_established",
    ))
    assert out == evaluate(*deepcopy(inputs()))


def test_exact_safety_zero_zero_threshold_85_vs_86():
    from tools import research_preregistration as rp
    draft, _ = inputs()
    alpha = rp._fraction(draft["analysis"]["safety_alpha"])
    margin = rp._fraction(
        draft["analysis"]["maximum_false_alarm_increase"], allow_zero=True
    )
    assert power._zero_zero_safety_minimum(alpha, margin, 1, 85) is None
    assert power._zero_zero_safety_minimum(alpha, margin, 1, 86) == 86
    # Analytically, at 86, (1-.05)^86 <= .025/2.
    assert Fraction(19, 20)**85 > Fraction(1, 80)
    assert Fraction(19, 20)**86 <= Fraction(1, 80)


def test_exact_primary_critical_values_and_effect_gain_gate():
    critical = power._critical_wins(6, Fraction(1, 40))
    assert critical[5] == 6
    assert critical[6] == 6
    assert power._practical_minimum_wins(6, 6, Fraction(1, 10)) == 4
    assert power._practical_minimum_wins(0, 6, Fraction(1, 10)) == 1
    tails = power._alternative_win_tails(6, Fraction(1))
    assert power._power(6, Fraction(1), Fraction(0),
                        Fraction(1, 10), critical, tails) == 1
    assert tails[6][6] == 1


def test_no_discordance_or_no_candidate_wins_never_reaches_positive_power():
    study, scenario = inputs()
    scenario["max_positive_families"] = 20
    scenario["candidate_only_positive_probability"] = {"numerator": 0, "denominator": 1}
    scenario["baseline_only_positive_probability"] = {"numerator": 0, "denominator": 1}
    out = evaluate(study, scenario)
    assert out["minimum_positive_families_for_assumed_primary_power"] is None
    assert out["design_status"] == "hypothetical_thresholds_not_reached_within_search_limits"
    scenario["baseline_only_positive_probability"] = {"numerator": 1, "denominator": 1}
    out2 = evaluate(study, scenario)
    assert out2["minimum_positive_families_for_assumed_primary_power"] is None


def test_impossible_zero_safety_margin_never_reports_sufficient_finite_sample():
    study, scenario = inputs()
    study["analysis"]["maximum_false_alarm_increase"] = {
        "numerator": 0, "denominator": 1,
    }
    out = evaluate(study, scenario)
    assert out["minimum_positive_families_for_assumed_primary_power"] == 129
    assert out["minimum_negative_families_in_zero_zero_alarm_scenario"] is None
    assert out["probability_of_zero_alarms_in_either_arm_decimal_lower"] is None


def test_registered_sampling_floor_is_respected_without_fabricating_power():
    study, scenario = inputs()
    study["sampling"]["minimum_positive_families"] = 150
    out = evaluate(study, scenario)
    assert out["minimum_positive_families_for_assumed_primary_power"] == 150
    assert out["preceding_sample_primary_power_decimal_lower"] is None
    study["sampling"]["minimum_positive_families"] = 200
    out = evaluate(study, scenario)
    assert out["minimum_positive_families_for_assumed_primary_power"] is None
    assert out["illustrative_total_distinct_families"] is None


@pytest.mark.parametrize(("field", "value", "diagnostic"), [
    ("partition", "sealed_confirmatory", "PROTECTED_OR_EMPIRICAL_PARTITION_FORBIDDEN"),
    ("assumptions_basis", "verified_empirical", "EMPIRICAL_ESTIMATE_NOT_AUTHENTICATED"),
    ("max_positive_families", True, "POSITIVE_PLANNING_LIMIT"),
    ("max_positive_families", 257, "POSITIVE_PLANNING_LIMIT"),
    ("max_negative_families", 2049, "NEGATIVE_PLANNING_LIMIT"),
    ("target_primary_power", {"numerator": 1, "denominator": 1},
     "VACUOUS_OR_IMPOSSIBLE_POWER_TARGET"),
    ("target_primary_power", {"numerator": 0, "denominator": 1},
     "SCENARIO_ZERO_FRACTION"),
    ("candidate_only_positive_probability", {"numerator": -1, "denominator": 5},
     "SCENARIO_FRACTION_RANGE"),
    ("negative_joint_no_alarm_probability", {"numerator": 1.0, "denominator": 2},
     "SCENARIO_FRACTION_RANGE"),
])
def test_invalid_or_privileged_design_declaration_fails_closed(field, value, diagnostic):
    _study, scenario = inputs()
    scenario[field] = value
    with pytest.raises(vb.BenchmarkError, match=diagnostic):
        power.validate_scenario(scenario)


def test_discordance_probabilities_must_be_jointly_feasible():
    _study, scenario = inputs()
    scenario["candidate_only_positive_probability"] = {
        "numerator": 7, "denominator": 10,
    }
    scenario["baseline_only_positive_probability"] = {
        "numerator": 4, "denominator": 10,
    }
    with pytest.raises(vb.BenchmarkError, match="POSITIVE_DISCORDANCE_PROBABILITIES"):
        power.validate_scenario(scenario)


def test_strict_study_pin_rejects_later_protocol_revision():
    registered, assumed = inputs()
    recorded_hash = vb.commitment(registered)
    registered["analysis"]["primary_alpha"] = {"numerator": 1, "denominator": 50}
    with pytest.raises(vb.BenchmarkError, match="REGISTRATION_PIN_MISMATCH"):
        power.plan(registered, assumed,
                   expected_registration_sha256=recorded_hash)


def test_cli_is_canonical_and_rejects_stale_pin_and_extra_fields(tmp_path):
    registered, assumed = inputs()
    args = [
        sys.executable, "-m", "tools.power_feasibility",
        "--registration", str(DRAFT), "--scenario", str(SCENARIO),
        "--expected-registration-sha256", vb.commitment(registered),
    ]
    run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr.decode()
    assert b"\r\n" not in run.stdout
    result = json.loads(run.stdout)
    assert result["illustrative_total_distinct_families"] == 215
    assert result["scientific_superiority_established"] is False
    invalid = args.copy()
    invalid[-1] = "f" * 64
    no = subprocess.run(invalid, cwd=ROOT, capture_output=True, timeout=30)
    assert no.returncode == 2
    assert json.loads(no.stderr)["code"] == "REGISTRATION_PIN_MISMATCH"

    revised = deepcopy(assumed)
    revised["protected_source_ids"] = ["not_allowed"]
    name = tmp_path / "bad.json"
    name.write_bytes(vb.canonical_bytes(revised))
    no_extra = subprocess.run(
        args[:5] + [str(name)] + args[6:],
        cwd=ROOT, capture_output=True, timeout=30,
    )
    assert no_extra.returncode == 2
    assert json.loads(no_extra.stderr)["status"] == "invalid"
