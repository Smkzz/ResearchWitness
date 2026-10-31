"""Proposal generation must never trust numerical success as proof.

The repository tests stub the optional solver; actual SciPy runs are a separate
local development receipt, not a CI dependency or a fabricated solver result.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

import pytest

from researchwitness import exact_optimization as exact
from tools import optimization_examples as examples
from tools import propose_exact_optimization as producer


def source(fixture):
    raw = exact.canonical_bytes(fixture["model"])
    return raw, hashlib.sha256(raw).hexdigest()


def linear_proposal(model, lower, upper, seconds):
    return {"lambda": [2.0], "nu": [], "point": [2.0, 0.0]}


def bilinear_proposal(model, lower, upper, seconds):
    lam = [0.0] * 4
    # At the root this relaxation proves only 1/2, not 1/4.
    if upper[0] == Fraction(1, 2):
        lam[3] = 1.0
    elif lower[0] == Fraction(1, 2):
        lam[2] = 1.0
    return {"lambda": lam, "nu": [0.5], "point": [0.5, 0.5, 0.25]}


def test_generation_linear_and_replay(monkeypatch):
    monkeypatch.setattr(producer, "_solve", linear_proposal)
    raw, pin = source(examples.linear_resource())
    proof, report = producer.propose_bytes(raw, "11", expected_model_sha256=pin)
    rows = [exact.parse_json(line) for line in proof.splitlines()]
    replay = exact.verify_records(exact.compile_model(exact.parse_json(raw)),
                                  rows[0], rows[1:], model_sha256=pin)
    assert report["verification"] == replay
    assert report["model_optimum_certified"] is True
    assert report["feasible_point_value"] == "11"
    assert report["solver_is_trusted_for_verification"] is False
    assert report["certificate_sha256"] == hashlib.sha256(proof).hexdigest()


def test_root_not_enough_splits_complete_tree(monkeypatch):
    monkeypatch.setattr(producer, "_solve", bilinear_proposal)
    raw, pin = source(examples.bilinear_half())
    proof, report = producer.propose_bytes(raw, "1/4", expected_model_sha256=pin)
    assert report["visited_nodes"] == report["solver_calls"] == 3
    assert report["verification"]["checked_leaves"] == 2
    assert report["verification"]["verified_upper"] == "1/4"
    assert report["model_optimum_certified"] is True  # This stub supplies the exact witness.
    assert len(proof.splitlines()) == 3


def test_false_goal_and_node_exhaustion_never_succeed(monkeypatch):
    monkeypatch.setattr(producer, "_solve", bilinear_proposal)
    raw, pin = source(examples.bilinear_half())
    with pytest.raises(producer.Inconclusive, match="GRID_EXHAUSTED"):
        producer.propose_bytes(raw, "1/5", expected_model_sha256=pin)
    with pytest.raises(producer.Inconclusive, match="NODE_BUDGET_EXHAUSTED"):
        producer.propose_bytes(raw, "1/4", expected_model_sha256=pin, max_nodes=1)


def test_bad_solver_point_is_not_claimed_as_optimum(monkeypatch):
    def invalid_point(*args):
        result = linear_proposal(*args)
        result["point"] = [200.0, 0.0]
        return result
    monkeypatch.setattr(producer, "_solve", invalid_point)
    raw, pin = source(examples.linear_resource())
    _, report = producer.propose_bytes(raw, "11", expected_model_sha256=pin)
    assert report["feasible_point"] is None
    assert report["model_optimum_certified"] is False


@pytest.mark.parametrize("mutation", ["negative", "nan", "short", "fake_success"])
def test_solver_mutations_fail_closed(monkeypatch, mutation):
    def corrupt(*args):
        result = linear_proposal(*args)
        if mutation == "negative":
            result["lambda"] = [-100.0]
        elif mutation == "nan":
            result["lambda"] = [float("nan")]
        elif mutation == "short":
            result["lambda"] = []
        else:
            result["lambda"] = [0.0]
        return result
    monkeypatch.setattr(producer, "_solve", corrupt)
    raw, pin = source(examples.linear_resource())
    with pytest.raises(producer.Inconclusive):
        producer.propose_bytes(raw, "11", expected_model_sha256=pin)


def test_empty_model_needs_no_solver(monkeypatch):
    fixture = examples.infeasible_leaf()
    fixture["model"]["bounds"] = [["0", "1"], ["2", "3"]]
    raw, pin = source(fixture)
    def unavailable(*args):
        raise AssertionError("Solver must not be called for interval contradiction")
    monkeypatch.setattr(producer, "_solve", unavailable)
    _, report = producer.propose_bytes(raw, "0", expected_model_sha256=pin)
    assert report["solver_calls"] == 0
    assert report["verification"]["status"] == "infeasible_model_certified"
    assert report["model_optimum_certified"] is False


def test_budgets_and_pins(monkeypatch):
    monkeypatch.setattr(producer, "_solve", linear_proposal)
    raw, pin = source(examples.linear_resource())
    for kw in ({"max_nodes": True}, {"max_nodes": 4096}, {"max_seconds": 0}, {"max_seconds": 301}):
        with pytest.raises(exact.CertificateError):
            producer.propose_bytes(raw, "11", expected_model_sha256=pin, **kw)
    with pytest.raises(exact.CertificateError, match="PIN_MISMATCH"):
        producer.propose_bytes(raw, "11", expected_model_sha256="0" * 64)
    clock = iter([0.0, 31.0])
    monkeypatch.setattr(producer.time, "monotonic", lambda: next(clock))
    with pytest.raises(producer.Inconclusive, match="TIME_BUDGET_EXHAUSTED"):
        producer.propose_bytes(raw, "11", expected_model_sha256=pin)


def test_cli_no_partial_and_no_overwrite(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(producer, "_solve", linear_proposal)
    raw, pin = source(examples.linear_resource())
    model_path = tmp_path / "model.json"
    model_path.write_bytes(raw)
    target = tmp_path / "proof.jsonl"
    args = ["--model", str(model_path), "--expected-model-sha256", pin,
            "--claimed-upper", "11", "--output", str(target)]
    assert producer.main(args) == 0
    before = target.read_bytes()
    assert json.loads(capsys.readouterr().out)["status"] == "exact_certificate_produced"
    assert producer.main(args) == 1
    assert target.read_bytes() == before
    assert json.loads(capsys.readouterr().out)["status"] == "inconclusive"
    target.unlink()
    bad = deepcopy(args)
    bad[bad.index("11")] = "9"
    assert producer.main(bad) == 1
    assert not target.exists()
    assert json.loads(capsys.readouterr().out)["status"] == "inconclusive"


def test_solver_failure_or_overrun_stays_inconclusive(monkeypatch):
    raw, pin = source(examples.linear_resource())
    def failed(*args):
        raise producer.Inconclusive("SOLVER_DID_NOT_SUPPLY_CANDIDATE")
    monkeypatch.setattr(producer, "_solve", failed)
    with pytest.raises(producer.Inconclusive, match="SOLVER_DID_NOT"):
        producer.propose_bytes(raw, "11", expected_model_sha256=pin)
    monkeypatch.setattr(producer, "_solve", linear_proposal)
    clock = iter([0.0, 0.1, 32.0])
    monkeypatch.setattr(producer.time, "monotonic", lambda: next(clock))
    with pytest.raises(producer.Inconclusive, match="TIME_BUDGET_EXHAUSTED"):
        producer.propose_bytes(raw, "11", expected_model_sha256=pin)


def test_box_invalid_solver_point_cannot_certify_false_optimum(monkeypatch):
    # Reviewer's precise attack: x<=2 is redundant to the true box x in [0,1].
    m = examples.model([["0", "1"]], [[0, "1"]],
                       inequalities=[examples.row([[0, "1"]], "2")])
    raw = exact.canonical_bytes(m)
    pin = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(producer, "_solve", lambda *args: {
        "lambda": [1.0], "nu": [], "point": [2.0]})
    _, report = producer.propose_bytes(raw, "2", expected_model_sha256=pin)
    assert report["verification"]["verified_upper"] == "2"  # Loose upper bound is valid.
    assert report["feasible_point"] is None
    assert report["model_optimum_certified"] is False  # x=2 is outside the true box.
