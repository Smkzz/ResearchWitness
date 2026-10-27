"""Synthetic-only exact family analysis; never evidence of real-paper superiority."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import exact_family_analysis as exact
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "examples/synthetic-study-registration/draft.json"


def synthetic_data(*, positives=6, negatives=86, wins=None, candidate_alarms=0):
    if wins is None:
        wins = positives
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    draft["arms"][0]["implementation_sha256"] = "b" * 64
    draft["arms"][1]["implementation_sha256"] = "c" * 64
    draft["resources"]["max_elapsed_ms_per_work"] = 1000
    draft["sampling"]["minimum_positive_families"] = max(1, positives)
    draft["sampling"]["minimum_negative_families"] = max(1, negatives)
    draft["sampling"]["minimum_negative_relationships"] = max(1, negatives)
    works = []
    for index in range(positives + negatives):
        positive = index < positives
        ident = ("p" if positive else "n") + str(index).zfill(4)
        works.append({
            "work_id": ident,
            "family_id": "f" + str(index).zfill(4),
            "source_sha256": f"{index+1:064x}",
            "interpretation_sha256": f"{index+10000:064x}",
            "label": "positive" if positive else "negative",
            "eligible": True,
            "exclusion_reason": None,
            "target_id": "expected" if positive else None,
        })
    registry = {
        "schema_version": vb.REGISTRY_VERSION,
        "exposure": "synthetic",
        "label_basis": "synthetic_construction",
        "works": works,
    }
    rh = vb.commitment(registry)
    protocols = [
        {
            "schema_version": vb.PROTOCOL_VERSION,
            "registry_sha256": rh,
            "implementation_sha256": model_hash,
            "schedule": [w["work_id"] for w in works],
            "max_elapsed_ms": 1000,
            "max_calls": 0,
            "max_cost_micro_eur": 0,
        }
        for model_hash in ("b" * 64, "c" * 64)
    ]

    def record(w, alarm: bool, correct: bool) -> dict:
        return {
            "work_id": w["work_id"],
            "source_sha256": w["source_sha256"],
            "interpretation_sha256": w["interpretation_sha256"],
            "status": "completed",
            "alarm_emitted": alarm,
            "candidate_sha256": "d" * 64 if alarm else None,
            "certificate_sha256": "e" * 64 if alarm else None,
            "certificate_status": "accepted" if correct else ("rejected" if alarm else "not_checked"),
            "source_correspondence": "supported" if correct else "unresolved",
            "target_id": "expected" if correct else None,
            "elapsed_ms": 1,
            "calls": 0,
            "cost_micro_eur": 0,
        }
    base_rows = [record(w, False, False) for w in works]
    cand_rows = []
    for index, w in enumerate(works):
        success = index < wins
        false_alarm = positives <= index < positives + candidate_alarms
        cand_rows.append(record(w, success or false_alarm, success))
    runs = [
        {
            "schema_version": vb.RUN_VERSION,
            "registry_sha256": rh,
            "protocol_sha256": vb.commitment(protocol),
            "implementation_sha256": protocol["implementation_sha256"],
            "results": rows,
        }
        for protocol, rows in zip(protocols, (base_rows, cand_rows), strict=True)
    ]
    pins = {
        "expected_registration_sha256": vb.commitment(draft),
        "expected_registry_sha256": rh,
        "expected_baseline_protocol_sha256": vb.commitment(protocols[0]),
        "expected_candidate_protocol_sha256": vb.commitment(protocols[1]),
    }
    return (draft, registry, protocols[0], runs[0], protocols[1], runs[1], pins)


def evaluate(data):
    return exact.analyze(*data[:6], **data[6])


def test_six_one_sided_wins_and_eighty_six_zero_alarm_negatives_meet_numeric_gate():
    docs = synthetic_data()
    out = evaluate(docs)
    metrics = out["metrics"]
    assert out["numeric_thresholds"] == "met_on_unverified_development_data"
    assert out["complete_declared_endpoints"] is True
    assert out["declared_minimum_sample_met"] is True
    assert metrics["exact_one_sided_discordance_p_value_upper_decimal"] == "0.015625000000"
    assert metrics["positive_gain_candidate_minus_baseline"] == {
        "numerator": 6, "denominator": 6,
    }
    assert metrics["primary_significant_against_declared_alpha"] is True
    assert metrics["minimum_practical_gain_met"] is True
    assert metrics["safety_margin_met"] is True
    assert "0.0496" < metrics["bonferroni_cp_harm_upper_decimal"] < "0.0498"
    assert all(out[flag] is False for flag in (
        "registration_frozen_by_independent_custodian",
        "independent_source_labels_verified", "family_independence_verified",
        "source_and_certificate_replayed_by_this_analysis",
        "protected_holdout_evaluated", "scientific_superiority_established",
    ))
    assert vb.canonical_bytes(out) == vb.canonical_bytes(evaluate(deepcopy(docs)))


def test_eighty_five_zero_alarm_negatives_cannot_meet_five_point_safety_margin():
    out = evaluate(synthetic_data(negatives=85))
    assert out["declared_minimum_sample_met"] is True
    assert out["metrics"]["primary_significant_against_declared_alpha"] is True
    assert out["metrics"]["safety_margin_met"] is False
    assert out["numeric_thresholds"] == "not_met_or_sample_inadequate"
    assert "0.0502" < out["metrics"]["bonferroni_cp_harm_upper_decimal"] < "0.0503"


def test_five_candidate_only_wins_are_not_significant_at_0025():
    out = evaluate(synthetic_data(wins=5))
    assert out["metrics"]["exact_one_sided_discordance_p_value_upper_decimal"] == "0.031250000000"
    assert out["metrics"]["primary_significant_against_declared_alpha"] is False
    assert out["numeric_thresholds"] == "not_met_or_sample_inadequate"


def test_one_candidate_false_alarm_counts_even_with_rejected_certificate_and_failure():
    draft, reg, bp, br, cp, cr, pins = synthetic_data(candidate_alarms=1)
    offender = cr["results"][6]
    assert offender["certificate_status"] == "rejected"
    offender["status"] = "failed"
    result = exact.analyze(draft, reg, bp, br, cp, cr, **pins)
    assert result["metrics"] is None
    assert result["numeric_thresholds"] == "not_evaluated"
    assert result["incomplete_paired_negative_families"] == 0
    assert result["complete_declared_endpoints"] is False


def test_rejected_alarm_in_completed_work_is_counted_for_harm():
    out = evaluate(synthetic_data(candidate_alarms=1))
    assert out["metrics"]["candidate_negative_alarm_families"] == 1
    assert out["metrics"]["safety_margin_met"] is False


def test_missing_family_is_inconclusive_not_posthoc_complete_case():
    docs = list(synthetic_data())
    docs[3]["results"].pop()
    out = evaluate(docs)
    assert out["metrics"] is None
    assert out["numeric_thresholds"] == "not_evaluated"
    assert out["incomplete_paired_negative_families"] == 1
    assert "MISSING_OR_UNRESOLVED_ELIGIBLE_FAMILIES" in out["reasons"]


def test_underpowered_declared_frame_never_yields_numeric_pass():
    docs = list(synthetic_data())
    docs[0]["sampling"]["minimum_negative_families"] = 90
    docs[-1]["expected_registration_sha256"] = vb.commitment(docs[0])
    out = evaluate(docs)
    assert out["metrics"] is not None
    assert out["declared_minimum_sample_met"] is False
    assert out["numeric_thresholds"] == "not_met_or_sample_inadequate"
    assert "DECLARED_MINIMUM_SAMPLE_NOT_MET" in out["reasons"]


def test_absent_discordance_yields_exact_one_and_not_significant():
    out = evaluate(synthetic_data(wins=0))
    assert out["metrics"]["positive_paired_discordant"] == 0
    assert out["metrics"]["exact_one_sided_discordance_p_value_upper_decimal"] == "1.000000000000"
    assert out["metrics"]["primary_significant_against_declared_alpha"] is False


def test_arm_commitment_and_budget_mismatches_fail_closed():
    d = list(synthetic_data())
    d[0]["arms"][0]["implementation_sha256"] = "9" * 64
    d[-1]["expected_registration_sha256"] = vb.commitment(d[0])
    with pytest.raises(vb.BenchmarkError, match="STUDY_ARM_IMPLEMENTATION_MISMATCH"):
        evaluate(d)
    d = list(synthetic_data())
    d[0]["resources"]["max_elapsed_ms_per_work"] = 1001
    d[-1]["expected_registration_sha256"] = vb.commitment(d[0])
    with pytest.raises(vb.BenchmarkError, match="STUDY_RESOURCE_BUDGET_MISMATCH"):
        evaluate(d)


def test_external_protocol_registration_pins_and_defective_runs_refused():
    d = list(synthetic_data())
    d[-1]["expected_registration_sha256"] = "f" * 64
    with pytest.raises(vb.BenchmarkError, match="REGISTRATION_PIN_MISMATCH"):
        evaluate(d)
    d = list(synthetic_data())
    d[5]["results"][0]["source_sha256"] = "f" * 64
    with pytest.raises(vb.BenchmarkError, match="SOURCE_BINDING"):
        evaluate(d)


def test_one_sided_cp_grid_extremes_are_conservative():
    upper, lower = exact._one_sided_cp_harm_upper(
        candidate_alarms=0, baseline_alarms=0,
        negative_families=1, safety_alpha=Fraction(1, 40),
    )
    assert lower == 0
    assert Fraction(upper, exact.DENOMINATOR) >= Fraction(79, 80)
    assert Fraction(upper, exact.DENOMINATOR) - Fraction(79, 80) < Fraction(1, exact.DENOMINATOR)
    other_upper, other_lower = exact._one_sided_cp_harm_upper(
        candidate_alarms=1, baseline_alarms=1,
        negative_families=1, safety_alpha=Fraction(1, 40),
    )
    assert other_upper == exact.DENOMINATOR
    assert Fraction(other_lower, exact.DENOMINATOR) <= Fraction(1, 80)
    assert Fraction(1, 80) - Fraction(other_lower, exact.DENOMINATOR) < Fraction(1, exact.DENOMINATOR)


def test_exact_paired_tail_known_reference_cases():
    assert exact._exact_p_value(0, 0) == (1, 1)
    assert exact._exact_p_value(1, 0) == (1, 2)
    assert exact._exact_p_value(6, 0) == (1, 64)
    assert exact._exact_p_value(5, 1) == (7, 64)
    assert exact._exact_p_value(0, 6) == (64, 64)
    assert exact._decimal_outward(-1, 3, upper=True) == "-0.333333333333"
    assert exact._decimal_outward(-1, 3, upper=False) == "-0.333333333334"


def test_more_than_maximum_stat_families_reports_non_evaluation():
    docs = list(synthetic_data(positives=1, negatives=exact.MAX_FAMILIES_PER_ENDPOINT + 1, wins=1))
    result = evaluate(docs)
    assert result["metrics"] is None
    assert "NO_ENDPOINT_DATA_OR_SIZE_LIMIT" in result["reasons"]


def test_cli_requires_external_pins_and_outputs_canonical_lf(tmp_path):
    docs = synthetic_data(positives=6, negatives=86)
    names = ("registration", "registry", "baseline-protocol", "baseline-run",
             "candidate-protocol", "candidate-run")
    arguments = [sys.executable, "-m", "tools.exact_family_analysis"]
    for name, obj in zip(names, docs[:6], strict=True):
        p = tmp_path / (name + ".json")
        p.write_bytes(vb.canonical_bytes(obj))
        arguments.extend(("--" + name, str(p)))
    for name, value in docs[-1].items():
        arguments.extend(("--" + name.replace("_", "-"), value))
    ok = subprocess.run(arguments, cwd=ROOT, capture_output=True, timeout=30)
    assert ok.returncode == 0, ok.stderr.decode()
    assert b"\r\n" not in ok.stdout
    assert json.loads(ok.stdout)["scientific_superiority_established"] is False
    bad = arguments[:]
    bad[-1] = "f" * 64
    no = subprocess.run(bad, cwd=ROOT, capture_output=True, timeout=30)
    assert no.returncode == 2
    assert json.loads(no.stderr)["status"] == "invalid"
