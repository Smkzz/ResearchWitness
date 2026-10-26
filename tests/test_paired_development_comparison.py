"""Paired benchmark tests are synthetic engineering checks, not scientific data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import paired_development_comparison as pc
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]


def construct():
    registry = {
        "schema_version": vb.REGISTRY_VERSION, "exposure": "synthetic",
        "label_basis": "synthetic_construction",
        "works": [
            {"work_id": name, "family_id": family, "source_sha256": source * 64,
             "interpretation_sha256": interpretation * 64, "label": label,
             "eligible": eligible, "exclusion_reason": None if eligible else "excluded",
             "target_id": "expected" if label == "positive" else None}
            for name, family, source, interpretation, label, eligible in [
                ("p", "f1", "1", "2", "positive", True),
                ("n", "f2", "3", "4", "negative", True),
                ("n2", "f3", "5", "6", "negative", True),
                ("u", "f4", "7", "8", "unresolved", True),
                ("x", "f5", "9", "a", "negative", False),
            ]
        ],
    }
    rh = vb.commitment(registry)
    protocol = {
        "schema_version": vb.PROTOCOL_VERSION, "registry_sha256": rh,
        "implementation_sha256": "b" * 64, "schedule": ["p", "n", "n2", "u", "x"],
        "max_elapsed_ms": 1000, "max_calls": 0, "max_cost_micro_eur": 0,
    }
    other = deepcopy(protocol)
    other["implementation_sha256"] = "c" * 64

    def record(work, status="completed", alarm=False, accepted=False):
        return {
            "work_id": work["work_id"], "source_sha256": work["source_sha256"],
            "interpretation_sha256": work["interpretation_sha256"],
            "status": status, "alarm_emitted": alarm,
            "candidate_sha256": "d" * 64 if alarm else None,
            "certificate_sha256": "e" * 64 if alarm else None,
            "certificate_status": ("accepted" if accepted else "rejected") if alarm else "not_checked",
            "source_correspondence": "supported" if accepted else "unresolved",
            "target_id": "expected" if accepted else None,
            "elapsed_ms": 1, "calls": 0, "cost_micro_eur": 0,
        }
    works = {w["work_id"]: w for w in registry["works"]}
    baseline_rows = [
        record(works["p"]), record(works["n"], alarm=True),
        record(works["u"], status="abstained"),
        record(works["x"], status="not_attempted"),
    ]
    candidate_rows = [
        record(works["p"], alarm=True, accepted=True),
        record(works["n"]), record(works["n2"]),
        record(works["u"], status="abstained"),
        record(works["x"], status="not_attempted"),
    ]
    def run(p, rows):
        return {
            "schema_version": vb.RUN_VERSION,
            "registry_sha256": rh, "protocol_sha256": vb.commitment(p),
            "implementation_sha256": p["implementation_sha256"], "results": rows,
        }
    baseline = run(protocol, baseline_rows)
    candidate = run(other, candidate_rows)
    pins = {
        "expected_registry_sha256": rh,
        "expected_baseline_protocol_sha256": vb.commitment(protocol),
        "expected_candidate_protocol_sha256": vb.commitment(other),
    }
    return registry, protocol, baseline, other, candidate, pins


def test_pairing_retains_incomplete_negatives_and_false_alarms():
    registry, bp, br, cp, cr, pins = construct()
    report = pc.compare(registry, bp, br, cp, cr, **pins)
    assert report["status"] == "incomplete"
    assert report["registered_work_count"] == 5
    assert report["excluded_family_count"] == 1
    assert report["unresolved_family_count"] == 1
    assert report["positive_detection"]["paired_table"]["candidate_only"] == 1
    assert report["negative_false_alarm"]["paired_table"]["baseline_only"] == 1
    assert report["negative_false_alarm"]["paired_unknown"] == 1
    assert report["negative_false_alarm"]["baseline_upper_bound"] == {
        "numerator": 2, "denominator": 2,
    }
    assert report["negative_false_alarm"]["candidate_upper_bound"] == {
        "numerator": 0, "denominator": 2,
    }
    assert report["scientific_performance_established"] is False


def test_rejected_certificate_still_counts_negative_alarm():
    registry, bp, br, cp, cr, pins = construct()
    # Reject certificate AND fail work: emission must still be counted.
    cr["results"][1]["status"] = "failed"
    cr["results"][1]["alarm_emitted"] = True
    cr["results"][1]["candidate_sha256"] = "a" * 64
    cr["results"][1]["certificate_sha256"] = "b" * 64
    cr["results"][1]["certificate_status"] = "rejected"
    cr["results"][1]["source_correspondence"] = "unresolved"
    report = pc.compare(registry, bp, br, cp, cr, **pins)
    assert report["negative_false_alarm"]["candidate_lower_bound"]["numerator"] == 1
    assert report["negative_false_alarm"]["paired_table"]["both"] == 1


def test_complete_pair_table_requires_complete_runs():
    registry, bp, br, cp, cr, pins = construct()
    works = {w["work_id"]: w for w in registry["works"]}
    row = deepcopy(cr["results"][2])
    row["work_id"] = "n2"
    br["results"].insert(2, row)
    for run in (br, cr):
        for receipt in run["results"]:
            if receipt["work_id"] in {"u", "x"}:
                receipt["status"] = "completed"
    report = pc.compare(registry, bp, br, cp, cr, **pins)
    assert report["status"] == "complete"
    assert report["negative_false_alarm"]["paired_unknown"] == 0


def test_mismatched_resource_budget_rejected():
    registry, bp, br, cp, cr, pins = construct()
    cp["max_elapsed_ms"] = 2000
    cr["protocol_sha256"] = vb.commitment(cp)
    pins["expected_candidate_protocol_sha256"] = vb.commitment(cp)
    with pytest.raises(vb.BenchmarkError, match="RESOURCE_BUDGET_MISMATCH"):
        pc.compare(registry, bp, br, cp, cr, **pins)


def test_external_pin_prevents_pretense_of_new_registration():
    registry, bp, br, cp, cr, pins = construct()
    registry["works"][0]["target_id"] = "changed"
    with pytest.raises(vb.BenchmarkError, match="REGISTRY_PIN_MISMATCH"):
        pc.compare(registry, bp, br, cp, cr, **pins)


def test_unknown_or_duplicate_work_fails():
    registry, bp, br, cp, cr, pins = construct()
    cr["results"].append(deepcopy(cr["results"][0]))
    with pytest.raises(vb.BenchmarkError, match="UNKNOWN_OR_DUPLICATE_RESULT"):
        pc.compare(registry, bp, br, cp, cr, **pins)


def test_determinism_for_same_declared_inputs():
    docs = construct()
    a = pc.compare(*docs[:5], **docs[5])
    b = pc.compare(*deepcopy(docs[:5]), **deepcopy(docs[5]))
    assert vb.canonical_bytes(a) == vb.canonical_bytes(b)


def test_cli_accepts_only_external_pins_and_prints_canonical_lf(tmp_path):
    registry, bp, br, cp, cr, pins = construct()
    names = ("registry", "baseline-protocol", "baseline-run",
             "candidate-protocol", "candidate-run")
    paths = []
    for name, obj in zip(names, (registry, bp, br, cp, cr)):
        path = tmp_path / f"{name}.json"
        path.write_bytes(vb.canonical_bytes(obj))
        paths += [f"--{name}", str(path)]
    args = ([sys.executable, "-m", "tools.paired_development_comparison"]
            + paths + [entry for key, value in pins.items()
                       for entry in ("--" + key.replace("_", "-"), value)])
    run = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert b"\r\n" not in run.stdout
    assert json.loads(run.stdout)["status"] == "incomplete"
    args[-1] = "0" * 64
    bad = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30)
    assert bad.returncode == 2
    assert json.loads(bad.stderr)["status"] == "invalid"
