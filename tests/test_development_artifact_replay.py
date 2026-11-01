"""Synthetic-only RW-04I: real source/model/point replay behind receipts."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import exact_optimization as exact
from researchwitness import source_claims as source
from tools import development_artifact_replay as audit
from tools import verification_benchmark as vb

SOURCE = (b"RW-MATH-BEGIN v1\ndomain: bounded_real\nvariables: x[0,1]\n"
          b"maximize: x\nconstraints: x <= 1\nupper_bound: 1/2\nRW-MATH-END\n")


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def fixture(tmp_path: Path):
    claim, model = source.compile_candidate(
        SOURCE, block_index=0, expected_source_sha256=digest(SOURCE))
    raw_candidate = exact.canonical_bytes(claim)
    raw_model = exact.canonical_bytes(model)
    point = exact.canonical_bytes(["1"])
    evidence = tmp_path / "evidence"
    folder = evidence / "p1"
    folder.mkdir(parents=True)
    for name, data in (("source.txt", SOURCE), ("candidate.json", raw_candidate),
                       ("model.json", raw_model), ("point.json", point)):
        (folder / name).write_bytes(data)
    registry = {"schema_version": vb.REGISTRY_VERSION, "exposure": "synthetic",
                "label_basis": "synthetic_construction", "works": [
        {"work_id": "p1", "family_id": "f1", "source_sha256": digest(SOURCE),
         "interpretation_sha256": claim["source_block_sha256"],
         "label": "positive", "eligible": True, "exclusion_reason": None,
         "target_id": "synthetic-target"},
        {"work_id": "n1", "family_id": "f2", "source_sha256": "1" * 64,
         "interpretation_sha256": "2" * 64, "label": "negative", "eligible": True,
         "exclusion_reason": None, "target_id": None},
        {"work_id": "n2", "family_id": "f3", "source_sha256": "3" * 64,
         "interpretation_sha256": "4" * 64, "label": "negative", "eligible": True,
         "exclusion_reason": None, "target_id": None},
    ]}
    protocol = {"schema_version": vb.PROTOCOL_VERSION,
                "registry_sha256": vb.commitment(registry),
                "implementation_sha256": "5" * 64,
                "schedule": ["p1", "n1", "n2"], "max_elapsed_ms": 1000,
                "max_calls": 1, "max_cost_micro_eur": 0}
    common = {"elapsed_ms": 1, "calls": 0, "cost_micro_eur": 0}
    positive = {"work_id": "p1", "source_sha256": digest(SOURCE),
                "interpretation_sha256": claim["source_block_sha256"],
                "status": "completed", "alarm_emitted": True,
                "candidate_sha256": digest(raw_candidate),
                "certificate_sha256": digest(point),
                "certificate_status": "accepted", "source_correspondence": "supported",
                "target_id": "synthetic-target", **common}
    negative = {"work_id": "n1", "source_sha256": "1" * 64,
                "interpretation_sha256": "2" * 64,
                "status": "completed", "alarm_emitted": True,
                "candidate_sha256": "6" * 64,
                "certificate_sha256": "7" * 64,
                "certificate_status": "rejected", "source_correspondence": "contradicted",
                "target_id": None, **common}
    run = {"schema_version": vb.RUN_VERSION,
           "registry_sha256": vb.commitment(registry),
           "protocol_sha256": vb.commitment(protocol),
           "implementation_sha256": protocol["implementation_sha256"],
           "results": [positive, negative]}
    return registry, protocol, run, evidence


def pins(registry, protocol, run):
    return {"expected_registry_sha256": vb.commitment(registry),
            "expected_protocol_sha256": vb.commitment(protocol),
            "expected_run_sha256": vb.commitment(run)}


def repin(registry, protocol, run):
    protocol["registry_sha256"] = vb.commitment(registry)
    run["registry_sha256"] = vb.commitment(registry)
    run["protocol_sha256"] = vb.commitment(protocol)
    return pins(registry, protocol, run)


def execute(registry, protocol, run, evidence):
    return audit.replay(registry, protocol, run, evidence, **pins(registry, protocol, run))


def test_real_formal_refutation_replayed_without_changing_denominators(tmp_path):
    r, p, run, root = fixture(tmp_path)
    original = vb.score(r, p, run, expected_registry_sha256=vb.commitment(r),
                        expected_protocol_sha256=vb.commitment(p))
    result = execute(r, p, run, root)
    assert result["status"] == "accepted_formal_refutations_replayed"
    assert result["accepted_receipts_declared"] == result["accepted_formal_refutations_replayed"] == 1
    assert result["replayed"][0]["formal_refutation_margin"] == "1/2"
    assert result["original_development_score"] == original
    assert result["original_denominators_and_alarm_counts_preserved"] is True
    assert original["work_counts"]["registered"] == 3
    assert original["work_counts"]["missing"] == 1
    assert original["family_counts"]["negative_incomplete_without_alarm"] == 1
    assert original["rates"]["recorded_detection"] == {"numerator": 1, "denominator": 1}
    assert original["rates"]["observed_false_alarm"] == {"numerator": 1, "denominator": 2}
    assert original["rates"]["false_alarm_completion_upper_bound"] == {"numerator": 2, "denominator": 2}
    assert not result["source_interpretation_independently_adjudicated"]
    assert not result["publication_error_established"]
    assert not result["protected_evaluation_performed"]


@pytest.mark.parametrize("variant", ["point_not_refuting", "missing_point", "point_not_canonical",
                                     "malformed_point", "changed_source", "substitute_candidate",
                                     "substitute_model", "missing_candidate", "multiple_blocks",
                                     "interpretation_mismatch", "candidate_spoof"])
def test_invalid_accepted_evidence_never_produces_a_verified_score(tmp_path, variant):
    reg, protocol, run, root = fixture(tmp_path)
    folder = root / "p1"
    if variant == "point_not_refuting":
        new = exact.canonical_bytes(["1/4"])
        (folder / "point.json").write_bytes(new)
        run["results"][0]["certificate_sha256"] = digest(new)
    elif variant == "missing_point":
        (folder / "point.json").unlink()
    elif variant == "point_not_canonical":
        new = b'["1"]\n\n'
        (folder / "point.json").write_bytes(new)
        run["results"][0]["certificate_sha256"] = digest(new)
    elif variant == "malformed_point":
        new = b'[true]\n'
        (folder / "point.json").write_bytes(new)
        run["results"][0]["certificate_sha256"] = digest(new)
    elif variant == "changed_source":
        new = SOURCE.replace(b"1/2", b"1")
        (folder / "source.txt").write_bytes(new)
    elif variant == "substitute_candidate":
        new = (folder / "candidate.json").read_bytes().replace(b'"claimed_upper":"1/2"', b'"claimed_upper":"2"')
        (folder / "candidate.json").write_bytes(new)
        run["results"][0]["candidate_sha256"] = digest(new)
    elif variant == "substitute_model":
        new = (folder / "model.json").read_bytes().replace(b'"bounds":[["0","1"]]', b'"bounds":[["0","2"]]')
        (folder / "model.json").write_bytes(new)
    elif variant == "missing_candidate":
        (folder / "candidate.json").unlink()
    elif variant == "multiple_blocks":
        new = SOURCE + SOURCE
        (folder / "source.txt").write_bytes(new)
        reg["works"][0]["source_sha256"] = digest(new)
        run["results"][0]["source_sha256"] = digest(new)
        candidate, model = source.compile_candidate(new, block_index=0,
                                      expected_source_sha256=digest(new))
        candidate_raw = exact.canonical_bytes(candidate)
        (folder / "candidate.json").write_bytes(candidate_raw)
        (folder / "model.json").write_bytes(exact.canonical_bytes(model))
        run["results"][0]["candidate_sha256"] = digest(candidate_raw)
    elif variant == "interpretation_mismatch":
        reg["works"][0]["interpretation_sha256"] = "9" * 64
        run["results"][0]["interpretation_sha256"] = "9" * 64
    elif variant == "candidate_spoof":
        new = (folder / "candidate.json").read_bytes().replace(b'"mathematical_certificate_verified":false', b'"mathematical_certificate_verified":true')
        (folder / "candidate.json").write_bytes(new)
        run["results"][0]["candidate_sha256"] = digest(new)
    repin(reg, protocol, run)
    with pytest.raises((ValueError, OSError)):
        execute(reg, protocol, run, root)


def test_separately_trusted_run_pin_refuses_posthoc_success(tmp_path):
    reg, protocol, run, root = fixture(tmp_path)
    old = pins(reg, protocol, run)
    run["results"][0]["status"] = "failed"
    with pytest.raises(vb.BenchmarkError, match="RUN_EXTERNAL_PIN_MISMATCH"):
        audit.replay(reg, protocol, run, root, **old)


def test_no_verified_proofs_is_explicitly_not_applicable_not_complete_evidence(tmp_path):
    reg, protocol, run, root = fixture(tmp_path)
    run["results"][0]["certificate_status"] = "rejected"
    result = execute(reg, protocol, run, root)
    assert result["status"] == "no_accepted_records_to_replay"
    assert result["accepted_receipts_declared"] == 0
    assert result["accepted_formal_refutations_replayed"] == 0
    assert result["original_development_score"]["rates"]["recorded_detection"]["numerator"] == 0
    assert result["original_development_score"]["rates"]["observed_false_alarm"]["numerator"] == 1


def test_unsupported_accepted_on_incomplete_or_unalarmed_receipt(tmp_path):
    reg, protocol, run, root = fixture(tmp_path)
    run["results"][0]["status"] = "timeout"
    with pytest.raises(vb.BenchmarkError, match="ACCEPTANCE_ON_NONCOMPLETED"):
        execute(reg, protocol, run, root)
    run["results"][0]["status"] = "completed"
    run["results"][0]["alarm_emitted"] = False
    with pytest.raises(vb.BenchmarkError, match="NO_ALARM_EVIDENCE"):
        execute(reg, protocol, run, root)


def test_case_fold_work_id_aliases_rejected(tmp_path):
    reg, protocol, run, root = fixture(tmp_path)
    work = deepcopy(reg["works"][1])
    work["work_id"] = "P1"
    work["family_id"] = "f4"
    work["source_sha256"] = "a" * 64
    reg["works"].append(work)
    protocol["schedule"].append("P1")
    repin(reg, protocol, run)
    with pytest.raises(vb.BenchmarkError, match="CASE_COLLISION"):
        execute(reg, protocol, run, root)


def test_non_directory_and_symlinked_evidence_rejected(tmp_path):
    reg, protocol, run, root = fixture(tmp_path)
    with pytest.raises((ValueError, OSError)):
        execute(reg, protocol, run, tmp_path / "missing")
    file = tmp_path / "singlefile"
    file.write_text("private")
    with pytest.raises(vb.BenchmarkError, match="EVIDENCE_DIR"):
        execute(reg, protocol, run, file)
    shortcut = tmp_path / "link"
    try:
        shortcut.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(vb.BenchmarkError, match="EVIDENCE_DIR"):
        execute(reg, protocol, run, shortcut)


def test_cli_replays_exact_bytes_and_never_returns_fake_success(tmp_path, capsys):
    reg, proto, run, root = fixture(tmp_path)
    regpath, protocolpath, runpath = (tmp_path / f"{x}.json" for x in ("reg", "proto", "run"))
    for path, document in ((regpath, reg), (protocolpath, proto), (runpath, run)):
        path.write_bytes(vb.canonical_bytes(document))
    args = ["--registry", str(regpath), "--protocol", str(protocolpath),
            "--run", str(runpath), "--evidence-root", str(root),
            "--expected-registry-sha256", vb.commitment(reg),
            "--expected-protocol-sha256", vb.commitment(proto),
            "--expected-run-sha256", vb.commitment(run)]
    assert audit.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["accepted_formal_refutations_replayed"] == 1
    bad = args[:-1] + ["0" * 64]
    assert audit.main(bad) == 2
    err = capsys.readouterr()
    assert not err.out and json.loads(err.err)["code"] == "RUN_EXTERNAL_PIN_MISMATCH"


def test_python_optimized_mode_matches_validation(tmp_path):
    reg, proto, run, root = fixture(tmp_path)
    filenames = {}
    for key, doc in (("registry", reg), ("protocol", proto), ("run", run)):
        filename = tmp_path / f"{key}.json"
        filename.write_bytes(vb.canonical_bytes(doc))
        filenames[key] = filename
    args = ["-m", "tools.development_artifact_replay"]
    for key in ("registry", "protocol", "run"):
        args.extend((f"--{key}", str(filenames[key])))
    args.extend(("--evidence-root", str(root),
                 "--expected-registry-sha256", vb.commitment(reg),
                 "--expected-protocol-sha256", vb.commitment(proto),
                 "--expected-run-sha256", vb.commitment(run)))
    outputs = []
    for flag in ([], ["-O"]):
        p = subprocess.run([sys.executable, *flag, *args], cwd=Path(__file__).resolve().parents[1],
                           text=True, capture_output=True, timeout=20)
        assert p.returncode == 0, p.stderr
        outputs.append(p.stdout)
    assert outputs[0] == outputs[1]


def test_evidence_directory_never_uses_paths_from_json(tmp_path):
    reg, proto, run, root = fixture(tmp_path)
    injected = deepcopy(run)
    injected["results"][0]["source_path"] = "../../private"
    with pytest.raises(vb.BenchmarkError, match="OBJECT_FIELDS"):
        execute(reg, proto, injected, root)
