"""Synthetic transfer fixtures, hand-derived by a separate AI test agent.

Not new scientific discoveries or a blinded accuracy benchmark. The fixture
agent did not see the primary verifier. Files are optional local examples;
the immutable mathematical input and certificate have separate byte pins.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
from researchwitness.exact_optimization import canonical_bytes


def row(coefficients, rhs):
    return {"coefficients": deepcopy(coefficients), "rhs": rhs}


def model(bounds, coefficients, *, constant="0", inequalities=(), equalities=(),
          products=(), derivations=(), variables=(0,), grid=1):
    return deepcopy({
        "schema_version": "rw-exact-bilinear-model.v1", "bounds": bounds,
        "objective": {"coefficients": coefficients, "constant": constant},
        "inequalities": list(inequalities), "equalities": list(equalities),
        "products": list(products), "bound_derivations": list(derivations),
        "partition": {"variables": list(variables), "grid": grid},
    })


def bound(lower, upper, lam=(), nu=()):
    return {"kind": "bound", "lower": list(lower), "upper": list(upper),
            "lambda": [list(p) for p in lam], "nu": [list(p) for p in nu]}


def case(name, m, target, leaves, optimum, witness):
    return {"name": name, "model": m,
            "header": {"schema_version": "rw-exact-bilinear-certificate.v1",
                       "model_sha256": hashlib.sha256(canonical_bytes(m)).hexdigest(),
                       "claimed_upper": target, "leaf_count": len(leaves)},
            "leaves": leaves, "optimum": optimum, "witness": witness}


def bilinear_half():
    m = model([["0", "1"], ["0", "1"], ["0", "1"]], [[2, "1"]],
              equalities=[row([[0, "1"], [1, "1"]], "1")],
              products=[[0, 1, 2]], derivations=[[1, 0]], grid=2)
    return case("bilinear_half", m, "1/4", [
        bound([0], [1], [[3, "1"]], [[0, "1/2"]]),
        bound([1], [2], [[2, "1"]], [[0, "1/2"]]),
    ], "1/4", ["1/2", "1/2", "1/4"])


def linear_resource():
    m = model([["-1", "2"], ["0", "3"]], [[0, "3"], [1, "2"]], constant="5",
              inequalities=[row([[0, "1"], [1, "1"]], "2")], variables=[0, 1])
    return case("linear_resource", m, "11", [bound([0, 0], [1, 1], [[0, "2"]])],
                "11", ["2", "0"])


def infeasible_leaf():
    m = model([["0", "1"], ["0", "1"]], [[1, "1"]],
              equalities=[row([[0, "1"], [1, "-1"]], "3/4")],
              derivations=[[1, 0]], grid=2)
    return case("infeasible_leaf", m, "1/4", [
        {"kind": "empty", "lower": [0], "upper": [1]}, bound([1], [2]),
    ], "1/4", ["1", "1/4"])


def repeated_operand():
    m = model([["1/2", "1"], ["0", "1"]], [[1, "1"]], products=[[0, 0, 1]])
    return case("repeated_operand", m, "1", [bound([0], [1], [[2, "1"]])],
                "1", ["1", "1"])


def negative_equality_orientation():
    fixture = bilinear_half()
    fixture["name"] = "negative_equality_orientation"
    fixture["model"]["equalities"] = [row([[0, "-1"], [1, "-1"]], "-1")]
    for leaf in fixture["leaves"]:
        leaf["nu"] = [[0, "-1/2"]]
    fixture["header"]["model_sha256"] = hashlib.sha256(canonical_bytes(fixture["model"])).hexdigest()
    return fixture


def coverage_control():
    m = model([["0", "1"], ["0", "1"]], [], variables=[0, 1], grid=4)
    leaves = [bound([i, j], [i + 2, j + 2]) for i in (0, 2) for j in (0, 2)]
    return case("coverage_control", m, "0", leaves, "0", ["0", "0"])


def positive_cases():
    return [bilinear_half(), linear_resource(), infeasible_leaf(), repeated_operand(),
            negative_equality_orientation(), coverage_control()]


def write_examples(directory: Path):
    """Create in a new directory only; never overwrite an existing example set."""
    directory.mkdir(parents=False, exist_ok=False)
    manifest = {}
    for fixture in positive_cases():
        name = fixture["name"]
        model_bytes = canonical_bytes(fixture["model"])
        proof = canonical_bytes(fixture["header"]) + b"".join(
            canonical_bytes(leaf) for leaf in fixture["leaves"])
        for suffix, raw in (("model.json", model_bytes), ("certificate.jsonl", proof)):
            filename = name + "." + suffix
            with (directory / filename).open("xb") as handle:
                handle.write(raw)
            manifest[filename] = hashlib.sha256(raw).hexdigest()
    with (directory / "pins.json").open("xb") as handle:
        handle.write(canonical_bytes(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    options = parser.parse_args(argv)
    pins = write_examples(options.output_dir)
    print(canonical_bytes(pins).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
