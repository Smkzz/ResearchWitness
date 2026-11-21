"""Synthetic-only checks for replay of completed non-alarm receipts."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from researchwitness import exact_optimization as opt
from researchwitness import source_claims as source
from tests.test_exact_family_analysis import synthetic_data
from tests.test_replay_bound_aggregation import digest, repin, roots, row
from tools import development_artifact_replay as replay
from tools import exact_family_analysis as exact
from tools import paired_development_comparison as paired
from tools import verification_benchmark as vb

ROOT = Path(__file__).resolve().parents[1]


def marked(index, *, bound, objective="x", constraints="none"):
    return (f"Synthetic work {index}\nRW-MATH-BEGIN v1\ndomain: bounded_real\n"
            f"variables: x[-1,1]\nmaximize: {objective}\nconstraints: {constraints}\n"
            f"upper_bound: {bound}\nRW-MATH-END\n").encode()


def put_source(raw, work, receipts, folders):
    candidate, _model = source.compile_candidate(
        raw, block_index=0, expected_source_sha256=digest(raw))
    bindings = {"source_sha256": digest(raw),
                "interpretation_sha256": candidate["source_block_sha256"]}
    for obj in (work, *receipts):
        obj.update(bindings)
    for root in folders:
        folder = root / work["work_id"]
        folder.mkdir(exist_ok=True)
        (folder / "source.txt").write_bytes(raw)
    return digest(opt.canonical_bytes(candidate))


def frozen_fixture(tmp_path, *, positives=1, negatives=1):
    study, registry, bp, baseline, cp, candidate, pins = synthetic_data(
        positives=positives, negatives=negatives)
    implementations = replay.frozen_implementation_pins()
    for method, profile, protocol, run in zip(
            replay.FROZEN_ARMS, study["arms"], (bp, cp), (baseline, candidate), strict=True):
        pin = implementations[method]
        protocol["implementation_sha256"] = run["implementation_sha256"] = profile["implementation_sha256"] = pin
    folders = roots(tmp_path)
    for index, work in enumerate(registry["works"]):
        positive = work["label"] == "positive"
        if positive:
            work["target_id"] = replay.FROZEN_TARGET_ID
        receipts = [row(run, work["work_id"]) for run in (baseline, candidate)]
        raw = marked(index, bound="0" if positive else str(index + 1))
        candidate_sha = put_source(raw, work, receipts, folders)
        if positive:
            receipts[1].update(target_id=replay.FROZEN_TARGET_ID, candidate_sha256=candidate_sha,
                               certificate_sha256=digest(opt.canonical_bytes(["1"])))
    return study, registry, bp, baseline, cp, candidate, pins, folders


def args(data):
    study, registry, bp, baseline, cp, candidate, pins, folders = data
    repin(registry, (bp, cp), (baseline, candidate), pins)
    return dict(pins, expected_registration_sha256=vb.commitment(study),
                baseline_evidence_root=folders[0], candidate_evidence_root=folders[1],
                expected_baseline_run_sha256=vb.commitment(baseline),
                expected_candidate_run_sha256=vb.commitment(candidate), replay_frozen_arms=True)


def comparison(data):
    options = args(data)
    options.pop("expected_registration_sha256")
    return paired.compare(*data[1:6], **options)


def test_numerical_gate_reachable_only_with_verified_completions(tmp_path):
    data = frozen_fixture(tmp_path, positives=6, negatives=86)
    out = exact.analyze(*data[:6], **args(data))
    assert out["numeric_thresholds"] == "met_on_replay_verified_development_data"
    assert out["frozen_arm_non_alarm_receipts_replayed_by_this_analysis"] == {
        "baseline": 92, "candidate": 86}
    assert out["accepted_formal_refutations_replayed_by_this_analysis"] == {
        "baseline": 0, "candidate": 6}
    assert out["scientific_superiority_established"] is False
    assert out["protected_holdout_evaluated"] is False
    legacy = exact.analyze(*data[:6], **dict(args(data), replay_frozen_arms=False))
    assert legacy["numeric_thresholds"] == "not_evaluated"


@pytest.mark.parametrize("mutation,code", [
    ("hidden_alarm", "FROZEN_ARM_ALARM_MISMATCH"),
    ("substituted_source", "EXTERNAL_SOURCE_PIN_MISMATCH"),
    ("substituted_interpretation", "INTERPRETATION_SOURCE_BLOCK_MISMATCH"),
    ("unknown_target", "FROZEN_ARM_TARGET_ID_MISMATCH"),
    ("unsupported", "FROZEN_ARM_REQUIRES_AFFINE_BOX"),
    ("multiple_blocks", "MULTIPLE_SOURCE_BLOCKS"),
    ("missing", "ARTIFACT_UNAVAILABLE_OR_INVALID"),
    ("hard_link", "ARTIFACT_UNAVAILABLE_OR_INVALID"),
])
def test_repinned_declarations_do_not_buy_a_non_alarm(tmp_path, mutation, code):
    study, registry, bp, baseline, cp, candidate, pins, folders = data = frozen_fixture(tmp_path)
    work = registry["works"][0]
    b, c = (row(run, work["work_id"]) for run in (baseline, candidate))
    path = folders[0] / work["work_id"] / "source.txt"
    if mutation == "hidden_alarm":
        for field in ("alarm_emitted", "candidate_sha256", "certificate_status",
                      "certificate_sha256", "source_correspondence", "target_id"):
            c[field] = b[field]
    elif mutation == "substituted_source":
        path.write_bytes(marked(999, bound="3"))
    elif mutation == "substituted_interpretation":
        for obj in (work, b, c):
            obj["interpretation_sha256"] = "0" * 64
    elif mutation == "unknown_target":
        work["target_id"] = "different"
    elif mutation == "unsupported":
        put_source(marked(999, bound="0", constraints="x <= 1"), work, (b, c), folders)
    elif mutation == "multiple_blocks":
        put_source(marked(99, bound="0") + marked(99, bound="1"), work, (b, c), folders)
    elif mutation == "missing":
        path.unlink()
    elif mutation == "hard_link":
        path.unlink()
        path.hardlink_to(folders[1] / work["work_id"] / "source.txt")
    report = comparison(data)
    arm = "candidate" if mutation == "hidden_alarm" else "baseline"
    assert report["positive_detection"]["paired_unknown"] == 1
    assert report["positive_detection"]["independent_family_count_declared"] == 1
    assert report["replay"][arm]["non_alarm_unverified_codes"] == {code: 1}


@pytest.mark.parametrize("status", ["abstained", "failed", "timeout", "unsupported",
                                    "budget_exceeded", "not_attempted", "source_unavailable", "missing"])
def test_every_negative_family_member_needs_completed_replay(tmp_path, status):
    data = frozen_fixture(tmp_path)
    registry, bp, baseline, cp, candidate = data[1:6]
    work = deepcopy(registry["works"][1])
    work["work_id"] = "version"
    registry["works"].append(work)
    for protocol, run, root in zip((bp, cp), (baseline, candidate), data[-1], strict=True):
        protocol["schedule"].append("version")
        record = deepcopy(run["results"][1])
        record["work_id"] = "version"
        (root / "version").mkdir()
        (root / "version/source.txt").write_bytes(
            (root / registry["works"][1]["work_id"] / "source.txt").read_bytes())
        if run is baseline:
            if status == "missing":
                continue
            record["status"] = status
        run["results"].append(record)
    out = comparison(data)["negative_false_alarm"]
    assert out["independent_family_count_declared"] == 1
    assert out["paired_unknown"] == 1
    assert out["baseline_upper_bound"]["numerator"] == 1
    assert out["candidate_upper_bound"]["numerator"] == 0


def test_a_different_valid_refuting_point_is_not_the_frozen_arm_point(tmp_path):
    data = frozen_fixture(tmp_path)
    candidate = data[5]
    candidate["results"][0]["certificate_sha256"] = digest(opt.canonical_bytes(["1/2"]))
    out = comparison(data)
    assert out["positive_detection"]["paired_unknown"] == 1
    assert out["replay"]["candidate"]["unverified_codes"] == {"FROZEN_ARM_ALARM_DIGEST_MISMATCH": 1}


def test_corner_uses_objective_sign_and_does_not_hide_false_alarms(tmp_path):
    data = frozen_fixture(tmp_path)
    work = data[1]["works"][1]
    b, c = (row(run, work["work_id"]) for run in (data[3], data[5]))
    digest_ = put_source(marked(1, bound="0", objective="-x"), work, (b, c), data[-1])
    c.update(alarm_emitted=True, certificate_status="accepted", candidate_sha256=digest_,
             certificate_sha256=digest(opt.canonical_bytes(["-1"])))
    assert comparison(data)["negative_false_alarm"]["paired_table"]["candidate_only"] == 1
    c["certificate_status"] = "rejected"
    assert comparison(data)["negative_false_alarm"]["paired_unknown"] == 1


def test_wrong_arm_or_run_pin_does_not_fall_back(tmp_path):
    data = frozen_fixture(tmp_path)
    options = args(data)
    bad_pin = dict(options, expected_baseline_run_sha256="0" * 64)
    with pytest.raises(vb.BenchmarkError, match="RUN_EXTERNAL_PIN_MISMATCH"):
        exact.analyze(*data[:6], **bad_pin)
    data[2]["implementation_sha256"] = data[3]["implementation_sha256"] = "f" * 64
    with pytest.raises(vb.BenchmarkError, match="FROZEN_ARM_IMPLEMENTATION_MISMATCH"):
        comparison(data)


def test_elapsed_limit_does_not_count_semantically_valid_result(tmp_path, monkeypatch):
    data = frozen_fixture(tmp_path)
    times = iter([0, 2_000_000_000] * 4)
    monkeypatch.setattr(replay, "time", SimpleNamespace(monotonic_ns=lambda: next(times)))
    report = comparison(data)
    assert report["negative_false_alarm"]["paired_unknown"] == 1
    assert report["replay"]["baseline"]["non_alarm_unverified_codes"] == {
        "FROZEN_ARM_REPLAY_TIME_LIMIT": 2}


def test_frozen_replay_shares_the_existing_record_cap(tmp_path, monkeypatch):
    data = frozen_fixture(tmp_path)
    monkeypatch.setattr(replay, "MAX_ACCEPTED", 1)
    with pytest.raises(vb.BenchmarkError, match="FROZEN_ARM_REPLAY_BUDGET"):
        comparison(data)


@pytest.mark.parametrize("alias", ["NUL.txt", "trailing."])
def test_frozen_work_path_aliases_are_refused_before_io(tmp_path, alias):
    data = frozen_fixture(tmp_path)
    data[1]["works"][0]["work_id"] = alias
    for protocol, run in ((data[2], data[3]), (data[4], data[5])):
        protocol["schedule"][0] = run["results"][0]["work_id"] = alias
    with pytest.raises(vb.BenchmarkError, match="FROZEN_ARM_WORK_PATH_NOT_PORTABLE"):
        comparison(data)


def test_frozen_cli_cannot_downgrade_to_declarations_without_run_pins(tmp_path):
    data = frozen_fixture(tmp_path)
    options = args(data)
    command = [sys.executable, "-O", "-m", "tools.paired_development_comparison",
               "--replay-frozen-arms"]
    for name, doc in zip(("registry", "baseline-protocol", "baseline-run",
                          "candidate-protocol", "candidate-run"), data[1:6], strict=True):
        path = tmp_path / (name + ".json")
        path.write_bytes(vb.canonical_bytes(doc))
        command += ["--" + name, str(path)]
        if name.endswith("protocol") or name == "registry":
            command += [f"--expected-{name}-sha256",
                        options[f"expected_{name.replace('-', '_')}_sha256"]]
    result = subprocess.run(command, capture_output=True, cwd=ROOT, timeout=20, check=False)
    assert result.returncode == 2 and not result.stdout
    assert vb.parse_document(result.stderr)["code"] == "FROZEN_ARM_REPLAY_REQUIRES_EVIDENCE"
