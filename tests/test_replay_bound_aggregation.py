"""Synthetic-only RW-04K: comparative aggregation counts only replayed evidence."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import exact_optimization as exact_opt
from researchwitness import source_claims as source
from tests.test_exact_family_analysis import synthetic_data
from tests.test_paired_development_comparison import construct
from tools import exact_family_analysis as exact
from tools import paired_development_comparison as pc
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def write_evidence(root: Path, work_id: str, index: int) -> dict[str, str]:
    """Write a real refuting bundle; return the hashes a receipt must bind."""
    raw_source = (f"RW-MATH-BEGIN v1\ndomain: bounded_real\nvariables: x[0,1]\n"
                  f"maximize: x\nconstraints: x <= 1\nupper_bound: {index + 1}/{index + 3}\n"
                  f"RW-MATH-END\n").encode()
    claim, model = source.compile_candidate(
        raw_source, block_index=0, expected_source_sha256=digest(raw_source))
    raw_candidate = exact_opt.canonical_bytes(claim)
    point = exact_opt.canonical_bytes(["1"])
    folder = root / work_id
    folder.mkdir(parents=True)
    for name, data in (("source.txt", raw_source), ("candidate.json", raw_candidate),
                       ("model.json", exact_opt.canonical_bytes(model)),
                       ("point.json", point)):
        (folder / name).write_bytes(data)
    return {"source_sha256": digest(raw_source),
            "interpretation_sha256": claim["source_block_sha256"],
            "candidate_sha256": digest(raw_candidate),
            "certificate_sha256": digest(point)}


def bind(registry, runs, work_id, hashes, accepting):
    """Point the registry and every arm's row at the evidence hashes."""
    for work in registry["works"]:
        if work["work_id"] == work_id:
            work.update(source_sha256=hashes["source_sha256"],
                        interpretation_sha256=hashes["interpretation_sha256"])
    for run in runs:
        for row in run["results"]:
            if row["work_id"] == work_id:
                row.update(source_sha256=hashes["source_sha256"],
                           interpretation_sha256=hashes["interpretation_sha256"])
                if run in accepting:
                    row.update(candidate_sha256=hashes["candidate_sha256"],
                               certificate_sha256=hashes["certificate_sha256"])


def repin(registry, protocols, runs, pins):
    rh = vb.commitment(registry)
    for protocol, run in zip(protocols, runs, strict=True):
        protocol["registry_sha256"] = rh
        run["registry_sha256"] = rh
        run["protocol_sha256"] = vb.commitment(protocol)
    pins["expected_registry_sha256"] = rh
    pins["expected_baseline_protocol_sha256"] = vb.commitment(protocols[0])
    pins["expected_candidate_protocol_sha256"] = vb.commitment(protocols[1])


def roots(tmp_path):
    base, cand = tmp_path / "baseline", tmp_path / "candidate"
    base.mkdir()
    cand.mkdir()
    return base, cand


def paired_fixture(tmp_path):
    registry, bp, baseline, cp, candidate, pins = construct()
    base_root, cand_root = roots(tmp_path)
    hashes = write_evidence(cand_root, "p", 0)
    bind(registry, [baseline, candidate], "p", hashes, [candidate])
    repin(registry, [bp, cp], [baseline, candidate], pins)
    return registry, bp, baseline, cp, candidate, pins, base_root, cand_root


def strict(registry, bp, baseline, cp, candidate, pins, base_root, cand_root):
    return pc.compare(registry, bp, baseline, cp, candidate, **pins,
                      baseline_evidence_root=base_root, candidate_evidence_root=cand_root,
                      expected_baseline_run_sha256=vb.commitment(baseline),
                      expected_candidate_run_sha256=vb.commitment(candidate))


def counted(report):
    return report["positive_detection"], report["negative_false_alarm"]


def row(run, work_id):
    return next(r for r in run["results"] if r["work_id"] == work_id)


def test_replayed_detection_counts_and_unverified_outcomes_stay_in_denominator(tmp_path):
    data = paired_fixture(tmp_path)
    out = strict(*data)
    assert out["schema_version"] == pc.REPLAY_VERSION
    assert out["aggregation_evidence"] == "replay_verified_only"
    pos, neg = counted(out)
    assert pos["independent_family_count_declared"] == 1 and neg["independent_family_count_declared"] == 2
    assert pos["candidate_lower_bound"] == {"numerator": 1, "denominator": 1}
    # Baseline's declared miss and every clean or alarmed negative are unverified.
    assert pos["baseline_lower_bound"]["numerator"] == 0
    assert pos["baseline_upper_bound"]["numerator"] == 1
    assert neg["paired_unknown"] == 2
    assert neg["candidate_lower_bound"]["numerator"] == 0
    assert neg["candidate_upper_bound"]["numerator"] == 2
    assert out["status"] == "incomplete"
    assert out["replay"]["candidate"]["accepted_formal_refutations_replayed"] == 1
    assert out["replay"]["declared_known_family_outcomes_left_unverified"] == {
        "positive": {"baseline": 1, "candidate": 0},
        "negative": {"baseline": 1, "candidate": 2}}
    declared = out["declared_positive_detection_not_counted"]
    assert declared["baseline_lower_bound"]["numerator"] == 0
    assert out["declared_negative_false_alarm_not_counted"]["baseline_lower_bound"]["numerator"] == 1


@pytest.mark.parametrize("forgery", ["certificate_hash", "candidate_hash", "missing_bundle",
                                     "non_refuting_point"])
def test_forged_or_missing_evidence_cannot_count(tmp_path, forgery):
    registry, bp, baseline, cp, candidate, pins, base_root, cand_root = paired_fixture(tmp_path)
    if forgery == "certificate_hash":
        row(candidate, "p")["certificate_sha256"] = "f" * 64
    elif forgery == "candidate_hash":
        row(candidate, "p")["candidate_sha256"] = "f" * 64
    elif forgery == "missing_bundle":
        for item in (cand_root / "p").iterdir():
            item.unlink()
        (cand_root / "p").rmdir()
    else:
        point = exact_opt.canonical_bytes(["0"])
        (cand_root / "p" / "point.json").write_bytes(point)
        row(candidate, "p")["certificate_sha256"] = digest(point)
    out = strict(registry, bp, baseline, cp, candidate, pins, base_root, cand_root)
    pos, _ = counted(out)
    assert pos["independent_family_count_declared"] == 1
    assert pos["candidate_lower_bound"]["numerator"] == 0
    assert pos["paired_unknown"] == 1
    assert out["replay"]["candidate"]["accepted_receipts_unverified"] == 1
    # The same forgery still improves the legacy declaration-only accounting.
    assert out["declared_positive_detection_not_counted"]["candidate_lower_bound"]["numerator"] == 1


def test_relabelled_abstentions_and_rejected_alarms_cannot_move_counts(tmp_path):
    data = list(paired_fixture(tmp_path))
    before = counted(strict(*data))
    baseline, candidate = data[2], data[4]
    for run in (baseline, candidate):
        for r in run["results"]:
            if r["status"] == "abstained" or r["certificate_status"] == "rejected":
                r.update(status="completed", alarm_emitted=False, candidate_sha256=None,
                         certificate_sha256=None, certificate_status="not_checked",
                         source_correspondence="unresolved", target_id=None)
    # A relabelled abstention of the positive family by the baseline arm too.
    row(baseline, "p")["status"] = "completed"
    declared_before = pc.compare(*data[:5], **data[5])
    assert counted(strict(*data)) == before
    assert declared_before["negative_false_alarm"]["baseline_lower_bound"]["numerator"] == 0


def test_target_or_correspondence_declarations_only_demote(tmp_path):
    data = list(paired_fixture(tmp_path))
    candidate = data[4]
    row(candidate, "p")["target_id"] = "other"
    assert counted(strict(*data))[0]["candidate_lower_bound"]["numerator"] == 0


def test_replayed_refutation_on_negative_family_is_a_verified_false_alarm(tmp_path):
    registry, bp, baseline, cp, candidate, pins = construct()
    base_root, cand_root = roots(tmp_path)
    hashes = write_evidence(cand_root, "n", 3)
    bind(registry, [baseline, candidate], "n", hashes, [candidate])
    row(candidate, "n").update(alarm_emitted=True, certificate_status="accepted",
                               source_correspondence="contradicted")
    repin(registry, [bp, cp], [baseline, candidate], pins)
    pins_run = {"baseline_evidence_root": base_root, "candidate_evidence_root": cand_root,
                "expected_baseline_run_sha256": vb.commitment(baseline),
                "expected_candidate_run_sha256": vb.commitment(candidate)}
    out = pc.compare(registry, bp, baseline, cp, candidate, **pins, **pins_run)
    assert out["negative_false_alarm"]["candidate_lower_bound"]["numerator"] == 1


def test_replay_arguments_fail_closed(tmp_path):
    registry, bp, baseline, cp, candidate, pins, base_root, cand_root = paired_fixture(tmp_path)
    with pytest.raises(vb.BenchmarkError, match="REPLAY_EVIDENCE_ARGUMENTS_INCOMPLETE"):
        pc.compare(registry, bp, baseline, cp, candidate, **pins,
                   candidate_evidence_root=cand_root)
    with pytest.raises(vb.BenchmarkError, match="RUN_EXTERNAL_PIN_MISMATCH"):
        pc.compare(registry, bp, baseline, cp, candidate, **pins,
                   baseline_evidence_root=base_root, candidate_evidence_root=cand_root,
                   expected_baseline_run_sha256=vb.commitment(baseline),
                   expected_candidate_run_sha256=vb.commitment(baseline))
    with pytest.raises(vb.BenchmarkError, match="ARM_EVIDENCE_ROOTS_NOT_DISTINCT"):
        strict(registry, bp, baseline, cp, candidate, pins, cand_root, cand_root)
    with pytest.raises(vb.BenchmarkError, match="EVIDENCE_DIR_NOT_PLAIN"):
        regular = tmp_path / "file"
        regular.write_bytes(b"")
        strict(registry, bp, baseline, cp, candidate, pins, base_root, regular)


def exact_fixture(tmp_path, forge=False):
    draft, registry, bp, baseline, cp, candidate, pins = synthetic_data()
    base_root, cand_root = roots(tmp_path)
    for index in range(6):
        work_id = "p" + str(index).zfill(4)
        hashes = write_evidence(cand_root, work_id, index)
        bind(registry, [baseline, candidate], work_id, hashes, [candidate])
        if forge:
            row(candidate, work_id)["certificate_sha256"] = "f" * 64
    repin(registry, [bp, cp], [baseline, candidate], pins)
    evidence = {"baseline_evidence_root": base_root, "candidate_evidence_root": cand_root,
                "expected_baseline_run_sha256": vb.commitment(baseline),
                "expected_candidate_run_sha256": vb.commitment(candidate)}
    return (draft, registry, bp, baseline, cp, candidate), pins, evidence


def test_declaration_only_exact_analysis_never_passes(tmp_path):
    docs, pins, _ = exact_fixture(tmp_path)
    out = exact.analyze(*docs, **pins)
    assert out["aggregation_evidence"] == "declaration_only"
    assert out["accepted_formal_refutations_replayed_by_this_analysis"] is None
    assert out["numeric_thresholds"] == "declared_thresholds_met_not_replay_verified"
    assert "DECLARATION_ONLY_RECEIPTS_NOT_REPLAYED" in out["reasons"]


@pytest.mark.parametrize("forge", [False, True])
def test_replay_bound_exact_analysis_counts_no_unverified_wins(tmp_path, forge):
    docs, pins, evidence = exact_fixture(tmp_path, forge)
    out = exact.analyze(*docs, **pins, **evidence)
    assert out["aggregation_evidence"] == "replay_verified_only"
    assert out["accepted_formal_refutations_replayed_by_this_analysis"] == {
        "baseline": 0, "candidate": 0 if forge else 6}
    assert out["numeric_thresholds"] == "not_evaluated"
    assert out["complete_declared_endpoints"] is False
    assert "UNVERIFIED_DECLARED_OUTCOMES" in out["reasons"]
    assert out["positive_families_declared"] == 6 and out["negative_families_declared"] == 86
    assert out["incomplete_paired_positive_families"] == 6
    assert out["incomplete_paired_negative_families"] == 86
    assert out["metrics"] is None


def test_exact_cli_accepts_replay_evidence(tmp_path):
    docs, pins, evidence = exact_fixture(tmp_path)
    names = ("registration", "registry", "baseline-protocol", "baseline-run",
             "candidate-protocol", "candidate-run")
    command = [sys.executable, "-m", "tools.exact_family_analysis"]
    for name, doc in zip(names, docs, strict=True):
        path = tmp_path / (name + ".json")
        path.write_bytes(vb.canonical_bytes(doc))
        command += ["--" + name, str(path)]
    for key, value in {**pins, **evidence}.items():
        command += ["--" + key.replace("_", "-"), str(value)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out == exact.analyze(*deepcopy(docs), **pins, **evidence)
    assert out["aggregation_evidence"] == "replay_verified_only"
