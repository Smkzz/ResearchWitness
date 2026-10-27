"""Exact paired-alarm safety planning on invented family labels only."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import joint_power_feasibility as joint
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "examples/synthetic-study-registration/draft.json"
SCENARIO = ROOT / "examples/synthetic-study-registration/joint-power-scenario.json"


def inputs():
    return (
        json.loads(DRAFT.read_text(encoding="utf-8")),
        json.loads(SCENARIO.read_text(encoding="utf-8")),
    )


def calculate(study=None, scenario=None):
    draft, scenario_input = inputs()
    draft = draft if study is None else study
    scenario_input = scenario_input if scenario is None else scenario
    return joint.plan(
        draft, scenario_input,
        expected_registration_sha256=vb.commitment(draft),
    )


def test_exact_paired_negative_safety_model_removes_zero_zero_assumption():
    report = calculate()
    assert report["schema_version"] == joint.REPORT_VERSION
    assert report["positive_families"] == 129
    assert report["negative_families"] == 86
    assert report["hypothetical_distinct_family_total"] == 215
    assert report["primary_success_probability_decimal_lower"] == "0.802810397513"
    assert report["paired_negative_safety_pass_probability_decimal_lower"] == (
        "0.421701565319"
    )
    assert report["zero_negative_alarms_probability_decimal_lower"] == (
        "0.175971570312"
    )
    assert report["both_endpoints_success_probability_decimal_lower"] == (
        "0.338546401286"
    )
    assert report["hypothetical_joint_target_met"] is False
    for flag in (
        "observed_discordance_probabilities_authenticated",
        "negative_joint_distribution_empirically_validated",
        "family_independence_verified",
        "negative_relationship_count_qualified",
        "source_label_provenance_verified",
        "actual_sample_size_power_verified",
        "chronological_preregistration_established",
        "protected_holdout_accessed",
        "scientific_superiority_established",
    ):
        assert report[flag] is False, flag
    assert report == calculate(*deepcopy(inputs()))


def test_negative_128_scenario_is_not_80_percent_joint_study_power():
    study, scenario = inputs()
    scenario["negative_families"] = 128
    report = calculate(study, scenario)
    assert report["paired_negative_safety_pass_probability_decimal_lower"] == (
        "0.636909470872"
    )
    assert report["both_endpoints_success_probability_decimal_lower"] == (
        "0.511317545491"
    )
    assert report["hypothetical_joint_target_met"] is False


def test_zero_alarm_certainty_obeys_registered_cp_harm_threshold():
    study, scenario = inputs()
    scenario["negative_joint_outcomes"] = {
        "neither_alarm": {"numerator": 1, "denominator": 1},
        "candidate_only_alarm": {"numerator": 0, "denominator": 1},
        "baseline_only_alarm": {"numerator": 0, "denominator": 1},
        "both_alarm": {"numerator": 0, "denominator": 1},
    }
    out = calculate(study, scenario)
    assert out["paired_negative_safety_pass_probability_decimal_lower"] == (
        "1.000000000000"
    )
    assert out["zero_negative_alarms_probability_decimal_lower"] == (
        "1.000000000000"
    )
    scenario["negative_families"] = 85
    under = calculate(study, scenario)
    assert under["paired_negative_safety_pass_probability_decimal_lower"] == (
        "0.000000000000"
    )


def test_all_candidate_only_negative_alarms_fail_safety():
    study, scenario = inputs()
    scenario["negative_joint_outcomes"] = {
        "neither_alarm": {"numerator": 0, "denominator": 1},
        "candidate_only_alarm": {"numerator": 1, "denominator": 1},
        "baseline_only_alarm": {"numerator": 0, "denominator": 1},
        "both_alarm": {"numerator": 0, "denominator": 1},
    }
    out = calculate(study, scenario)
    assert out["paired_negative_safety_pass_probability_decimal_lower"] == (
        "0.000000000000"
    )


def test_registered_minima_enforced_before_statistical_report():
    study, scenario = inputs()
    study["sampling"]["minimum_positive_families"] = 130
    with pytest.raises(vb.BenchmarkError, match="JOINT_POSITIVE_BELOW_REGISTERED_MINIMUM"):
        calculate(study, scenario)
    study, scenario = inputs()
    study["sampling"]["minimum_negative_families"] = 90
    with pytest.raises(vb.BenchmarkError, match="JOINT_NEGATIVE_BELOW_REGISTERED_MINIMUM"):
        calculate(study, scenario)


@pytest.mark.parametrize(("field", "value", "diagnostic"), [
    ("partition", "sealed_holdout", "JOINT_PROTECTED_PARTITION_FORBIDDEN"),
    ("assumptions_basis", "independently_source_reviewed", "JOINT_EMPIRICAL_BASIS_NOT_AUTHENTICATED"),
    ("family_sampling_model", "rows_are_independent", "JOINT_INDEPENDENCE_ASSUMPTION_REQUIRED"),
    ("positive_families", True, "JOINT_POSITIVE_FAMILY_LIMIT"),
    ("positive_families", 257, "JOINT_POSITIVE_FAMILY_LIMIT"),
    ("negative_families", 201, "JOINT_NEGATIVE_FAMILY_LIMIT"),
    ("target_joint_power", {"numerator": 1, "denominator": 1}, "JOINT_POWER_TARGET"),
])
def test_no_unbounded_or_protected_joint_study_assumptions(field, value, diagnostic):
    _study, assumed = inputs()
    assumed[field] = value
    with pytest.raises(vb.BenchmarkError, match=diagnostic):
        joint.validate_scenario(assumed)


def test_joint_probabilities_are_complete_and_bounded():
    _draft, scenario = inputs()
    scenario["negative_joint_outcomes"]["neither_alarm"] = {
        "numerator": 97, "denominator": 100,
    }
    with pytest.raises(vb.BenchmarkError, match="JOINT_NEGATIVE_PROBABILITY_SUM"):
        joint.validate_scenario(scenario)
    _draft, scenario = inputs()
    scenario["candidate_only_positive_probability"] = {
        "numerator": 9, "denominator": 10,
    }
    with pytest.raises(vb.BenchmarkError, match="JOINT_POSITIVE_PROBABILITY_SUM"):
        joint.validate_scenario(scenario)


def test_mismatched_study_digest_fails_before_hypothetical_analysis():
    draft, scenario = inputs()
    old = vb.commitment(draft)
    draft["analysis"]["minimum_practical_gain"] = {
        "numerator": 1, "denominator": 20,
    }
    with pytest.raises(vb.BenchmarkError, match="REGISTRATION_PIN_MISMATCH"):
        joint.plan(draft, scenario, expected_registration_sha256=old)


def test_cli_replays_exact_source_free_invented_math(tmp_path):
    draft, scenario = inputs()
    args = [
        sys.executable, "-m", "tools.joint_power_feasibility",
        "--registration", str(DRAFT), "--scenario", str(SCENARIO),
        "--expected-registration-sha256", vb.commitment(draft),
    ]
    run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr.decode()
    assert b"\r\n" not in run.stdout
    report = json.loads(run.stdout)
    assert report["both_endpoints_success_probability_decimal_lower"] == (
        "0.338546401286"
    )
    assert report["scientific_superiority_established"] is False
    args[-1] = "f" * 64
    invalid = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["code"] == "REGISTRATION_PIN_MISMATCH"

    # A source ID or evidence claim would violate the strict source-free schema.
    changed = deepcopy(scenario)
    changed["paper_source_uri"] = "https://example.org/not-part-of-the-model"
    p = tmp_path / "injected.json"
    p.write_bytes(vb.canonical_bytes(changed))
    args[-1] = vb.commitment(draft)
    args[6] = str(p)
    invalid2 = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert invalid2.returncode == 2
    assert json.loads(invalid2.stderr)["code"] == "JOINT_SCENARIO_FIELDS"
