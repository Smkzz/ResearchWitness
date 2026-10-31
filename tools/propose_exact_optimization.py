"""Bounded optional numerical proposal search, OUTSIDE the exact verifier.

Requires already-installed SciPy. Solver outcomes are untrusted proposals:
every admitted leaf and the final complete certificate are checked exactly.
A timeout, solver failure, or exhausted grid produces an inconclusive result,
never a false certificate. This tool does not parse papers or use AI/network.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time

from researchwitness import exact_optimization as exact

MAX_NODES = 4095
MAX_SECONDS = 300


class Inconclusive(ValueError):
    """A bounded search failed to produce a complete exact proof."""


def _solve(model, lower, upper, seconds):
    # Optional development dependency: never imported by the installed checker.
    try:
        from scipy.optimize import linprog
    except ImportError as exc:
        raise Inconclusive("SCIPY_NOT_PROVISIONED") from exc
    n = len(model.bounds)
    def dense(rows):
        result = []
        for row, _ in rows:
            values = [0.0] * n
            for j, value in row:
                values[j] = float(value)
            result.append(values)
        return result or None
    inequalities = exact.relaxed_rows(model, lower, upper)
    objective = [0.0] * n
    for j, value in model.objective:
        objective[j] = -float(value)
    result = linprog(
        objective, A_ub=dense(inequalities),
        b_ub=[float(b) for _, b in inequalities] or None,
        A_eq=dense(model.equalities), b_eq=[float(b) for _, b in model.equalities] or None,
        bounds=[(float(lo), float(hi)) for lo, hi in zip(lower, upper)], method="highs",
        options={"time_limit": min(seconds, 10.0), "maxiter": 100_000},
    )
    if not result.success:
        raise Inconclusive("SOLVER_DID_NOT_SUPPLY_CANDIDATE")
    return {
        "lambda": [-float(x) for x in result.ineqlin.marginals],
        "nu": [-float(x) for x in result.eqlin.marginals],
        "point": [float(x) for x in result.x],
    }


def _weights(values, scheme, nonnegative):
    result = []
    for j, value in enumerate(values):
        if not math.isfinite(value):
            raise Inconclusive("SOLVER_NONFINITE_MULTIPLIER")
        value = max(0.0, value) if nonnegative else value
        if scheme == "small_rational":
            q = Fraction(str(value)).limit_denominator(1_000_000)
        else:
            q = Fraction(round(value * 10**10), 10**10)
        if q:
            result.append([j, str(q)])
    return result


def propose_bytes(model_bytes: bytes, claimed_upper: str, *,
                  expected_model_sha256: str, max_nodes: int = 255,
                  max_seconds: int = 30):
    exact.require(type(max_nodes) is int and 1 <= max_nodes <= MAX_NODES, "SEARCH_NODE_BUDGET")
    exact.require(type(max_seconds) is int and 1 <= max_seconds <= MAX_SECONDS, "SEARCH_TIME_BUDGET")
    exact.require(hashlib.sha256(model_bytes).hexdigest() == expected_model_sha256,
                  "EXTERNAL_MODEL_PIN_MISMATCH")
    document = exact.parse_json(model_bytes, exact.MAX_MODEL_BYTES)
    model = exact.compile_model(document)
    target = exact.rational(claimed_upper)
    started = time.monotonic()
    pending = [((0,) * len(model.variables), (model.grid,) * len(model.variables))]
    leaves = []
    nodes = solves = 0
    best_point = None
    best_value = None
    while pending:
        if nodes >= max_nodes:
            raise Inconclusive("SEARCH_NODE_BUDGET_EXHAUSTED")
        remaining = max_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise Inconclusive("SEARCH_TIME_BUDGET_EXHAUSTED")
        lo, hi = pending.pop()
        nodes += 1
        lower, upper, empty = exact.bounds_for_leaf(model, lo, hi)
        if empty:
            leaves.append({"kind": "empty", "lower": list(lo), "upper": list(hi)})
            continue
        try:
            proposal = _solve(model, lower, upper, remaining)
        except (OverflowError, ArithmeticError) as exc:
            raise Inconclusive("SOLVER_NUMERIC_LIMIT") from exc
        solves += 1
        if time.monotonic() - started > max_seconds:
            raise Inconclusive("SEARCH_TIME_BUDGET_EXHAUSTED")
        rows = len(model.inequalities) + 4 * len(model.products)
        if (len(proposal["lambda"]) != rows or len(proposal["nu"]) != len(model.equalities)
                or len(proposal["point"]) != len(model.bounds)):
            raise Inconclusive("SOLVER_CANDIDATE_DIMENSION")
        if all(math.isfinite(v) for v in proposal["point"]):
            point = [str(Fraction(str(v)).limit_denominator(1_000_000)) for v in proposal["point"]]
            try:
                value = exact.verify_point(model, point)
            except exact.CertificateError:
                pass
            else:
                if best_value is None or value > best_value:
                    best_value, best_point = value, point
        accepted = None
        for scheme in ("small_rational", "decimal_grid"):
            candidate = {"kind": "bound", "lower": list(lo), "upper": list(hi),
                         "lambda": _weights(proposal["lambda"], scheme, True),
                         "nu": _weights(proposal["nu"], scheme, False)}
            try:
                value = exact.leaf_upper(model, candidate)
            except exact.CertificateError:
                continue
            if value is not None and value <= target:
                accepted = candidate
                break
        if accepted is not None:
            leaves.append(accepted)
            continue
        widths = [b - a for a, b in zip(lo, hi)]
        axis = max(range(len(widths)), key=lambda j: widths[j])
        if widths[axis] <= 1:
            raise Inconclusive("GRID_EXHAUSTED_WITHOUT_EXACT_PROOF")
        middle = (lo[axis] + hi[axis]) // 2
        left_high, right_low = list(hi), list(lo)
        left_high[axis] = middle
        right_low[axis] = middle
        pending.append((tuple(right_low), hi))
        pending.append((lo, tuple(left_high)))
    header = {"schema_version": exact.CERTIFICATE_VERSION,
              "model_sha256": expected_model_sha256,
              "claimed_upper": claimed_upper, "leaf_count": len(leaves)}
    report = exact.verify_records(model, header, leaves, model_sha256=expected_model_sha256)
    proof = exact.canonical_bytes(header) + b"".join(exact.canonical_bytes(l) for l in leaves)
    exact.require(len(proof) <= exact.MAX_PROOF_BYTES, "PROOF_BYTE_LIMIT")
    return proof, {
        "status": "exact_certificate_produced", "visited_nodes": nodes, "solver_calls": solves,
        "verification": report, "certificate_sha256": hashlib.sha256(proof).hexdigest(),
        "feasible_point": best_point, "feasible_point_value": None if best_value is None else str(best_value),
        "model_optimum_certified": best_value is not None and report["verified_upper"] == str(best_value),
        "source_correspondence": "not_established_by_this_tool",
        "solver_is_trusted_for_verification": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--claimed-upper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-nodes", type=int, default=255)
    parser.add_argument("--max-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        with exact._open_regular(args.model, exact.MAX_MODEL_BYTES) as handle:
            raw = handle.read(exact.MAX_MODEL_BYTES + 1)
        proof, report = propose_bytes(raw, args.claimed_upper,
                                     expected_model_sha256=args.expected_model_sha256,
                                     max_nodes=args.max_nodes, max_seconds=args.max_seconds)
        # No partial certificate is written; even a valid result never overwrites a file.
        with args.output.open("xb") as handle:
            handle.write(proof)
    except (Inconclusive, exact.CertificateError, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, (Inconclusive, exact.CertificateError)) else type(exc).__name__
        print(json.dumps({"status": "inconclusive", "reason": code}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
