"""Bounded, solver-free rational upper certificates for declared bilinear models.

This optional checker proves a universal bound for the supplied mathematical
model. It does not authenticate a paper, source correspondence, rights, scientific
validity, optimality, or independent review. There is no solver, plugin, eval,
network client or source-code execution on the verification path.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, BinaryIO, Iterable

MODEL_VERSION = "rw-exact-bilinear-model.v1"
CERTIFICATE_VERSION = "rw-exact-bilinear-certificate.v1"
REPORT_VERSION = "rw-exact-bilinear-verification.v1"
MAX_MODEL_BYTES = 2 * 1024 * 1024
MAX_PROOF_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_VARIABLES = 128
MAX_ROWS = 1024
MAX_PRODUCTS = 128
MAX_NONZEROS = 16384
MAX_LEAVES = 32768
MAX_DIMENSIONS = 8
MAX_GRID = 1024
MAX_INTEGER_BITS = 4096
MAX_WORK = 40_000_000
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 16
_RATIONAL = re.compile(r"-?(?:0|[1-9][0-9]{0,29})(?:/[1-9][0-9]{0,29})?\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class CertificateError(ValueError):
    """Malformed, unsupported, over-budget, or mathematically invalid evidence."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CertificateError(code)


def _checked(value: Fraction) -> Fraction:
    require(value.numerator.bit_length() <= MAX_INTEGER_BITS and
            value.denominator.bit_length() <= MAX_INTEGER_BITS,
            "ARITHMETIC_BIT_BUDGET")
    return value


def rational(value: Any) -> Fraction:
    require(type(value) is str and _RATIONAL.fullmatch(value) is not None,
            "RATIONAL_LITERAL")
    result = Fraction(value)
    require(str(result) == value, "RATIONAL_NOT_CANONICAL")
    return result


def _integer(value: Any, lower: int, upper: int, code: str) -> int:
    require(type(value) is int and lower <= value <= upper, code)
    return value


def _fields(value: Any, names: set[str], code: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == names, code)
    return value


def _array(value: Any, maximum: int, code: str) -> list[Any]:
    require(type(value) is list and len(value) <= maximum, code)
    return value


def _sha(value: Any) -> str:
    require(type(value) is str and _SHA.fullmatch(value) is not None, "SHA256_LITERAL")
    return value


def canonical_bytes(value: Any) -> bytes:
    """Convenience for producers; verification pins the actual supplied bytes."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in items:
        require(key not in output, "DUPLICATE_JSON_KEY")
        output[key] = value
    return output


def _not_number(value: str) -> Any:
    raise CertificateError("JSON_FLOAT_OR_NONFINITE_FORBIDDEN")


def _json_int(value: str) -> int:
    require(len(value) <= 18, "JSON_INTEGER_LENGTH")
    return int(value)


def parse_json(raw: bytes, maximum: int = MAX_LINE_BYTES) -> Any:
    require(type(raw) is bytes and 0 < len(raw) <= maximum, "JSON_BYTE_LIMIT")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_float=_not_number, parse_constant=_not_number,
                           parse_int=_json_int)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CertificateError("INVALID_JSON") from exc
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        require(nodes <= MAX_JSON_NODES and depth <= MAX_JSON_DEPTH,
                "JSON_STRUCTURE_LIMIT")
        if type(item) is dict:
            stack.extend((part, depth + 1) for part in item.values())
        elif type(item) is list:
            stack.extend((part, depth + 1) for part in item)
    return value


Sparse = tuple[tuple[int, Fraction], ...]


def _sparse(value: Any, size: int, *, positive: bool = False) -> Sparse:
    entries = _array(value, size, "SPARSE_LENGTH")
    result = []
    last = -1
    for pair in entries:
        require(type(pair) is list and len(pair) == 2, "SPARSE_PAIR")
        index = _integer(pair[0], 0, size - 1, "SPARSE_INDEX")
        require(index > last, "SPARSE_ORDER_OR_DUPLICATE")
        coefficient = rational(pair[1])
        require(coefficient != 0 and (not positive or coefficient > 0),
                "SPARSE_SIGN_OR_ZERO")
        result.append((index, coefficient))
        last = index
    return tuple(result)


def _rows(value: Any, size: int) -> tuple[tuple[Sparse, Fraction], ...]:
    result = []
    for row in _array(value, MAX_ROWS, "ROW_COUNT"):
        _fields(row, {"coefficients", "rhs"}, "ROW_FIELDS")
        result.append((_sparse(row["coefficients"], size), rational(row["rhs"])))
    return tuple(result)


@dataclass(frozen=True)
class Model:
    bounds: tuple[tuple[Fraction, Fraction], ...]
    objective: Sparse
    constant: Fraction
    inequalities: tuple[tuple[Sparse, Fraction], ...]
    equalities: tuple[tuple[Sparse, Fraction], ...]
    products: tuple[tuple[int, int, int], ...]
    derivations: tuple[tuple[int, int], ...]
    variables: tuple[int, ...]
    grid: int
    leaf_work: int


def compile_model(document: Any) -> Model:
    _fields(document, {"schema_version", "bounds", "objective", "inequalities",
                       "equalities", "products", "bound_derivations", "partition"},
            "MODEL_FIELDS")
    require(document["schema_version"] == MODEL_VERSION, "MODEL_VERSION")
    input_bounds = _array(document["bounds"], MAX_VARIABLES, "VARIABLE_COUNT")
    require(len(input_bounds) > 0, "EMPTY_VARIABLE_SET")
    bounds = []
    for pair in input_bounds:
        require(type(pair) is list and len(pair) == 2, "BOUND_PAIR")
        lo, hi = rational(pair[0]), rational(pair[1])
        require(lo <= hi, "GLOBAL_BOUND_CONTRADICTION")
        bounds.append((lo, hi))
    size = len(bounds)
    objective = _fields(document["objective"], {"coefficients", "constant"},
                        "OBJECTIVE_FIELDS")
    c = _sparse(objective["coefficients"], size)
    c0 = rational(objective["constant"])
    inequalities = _rows(document["inequalities"], size)
    equalities = _rows(document["equalities"], size)
    products = []
    for product in _array(document["products"], MAX_PRODUCTS, "PRODUCT_COUNT"):
        require(type(product) is list and len(product) == 3, "PRODUCT_FIELDS")
        indices = tuple(_integer(x, 0, size - 1, "PRODUCT_INDEX") for x in product)
        require(indices[2] not in indices[:2], "PRODUCT_OUTPUT_IS_OPERAND")
        require(indices not in products, "DUPLICATE_PRODUCT")
        products.append(indices)
    require(len(inequalities) + len(equalities) + 4 * len(products) <= MAX_ROWS,
            "TOTAL_ROW_BUDGET")
    nonzeros = len(c) + sum(len(a) for a, _ in inequalities + equalities)
    require(nonzeros + 12 * len(products) <= MAX_NONZEROS, "MODEL_NONZERO_BUDGET")
    derivations = []
    for pair in _array(document["bound_derivations"], MAX_VARIABLES,
                       "DERIVATION_COUNT"):
        require(type(pair) is list and len(pair) == 2, "DERIVATION_FIELDS")
        target = _integer(pair[0], 0, size - 1, "DERIVATION_VARIABLE")
        row = _integer(pair[1], 0, len(equalities) - 1, "DERIVATION_ROW")
        require(target in dict(equalities[row][0]), "DERIVATION_ZERO_TARGET")
        require((target, row) not in derivations, "DUPLICATE_DERIVATION")
        derivations.append((target, row))
    partition = _fields(document["partition"], {"variables", "grid"},
                        "PARTITION_FIELDS")
    variables = tuple(_integer(x, 0, size - 1, "PARTITION_VARIABLE") for x in
                      _array(partition["variables"], MAX_DIMENSIONS,
                             "PARTITION_DIMENSION"))
    require(len(variables) >= 1 and tuple(sorted(set(variables))) == variables,
            "PARTITION_VARIABLE_ORDER")
    require(all(bounds[j][0] < bounds[j][1] for j in variables),
            "PARTITION_FIXED_VARIABLE")
    grid = _integer(partition["grid"], 1, MAX_GRID, "PARTITION_GRID")
    require(grid & (grid - 1) == 0, "PARTITION_GRID_NOT_DYADIC")
    work = nonzeros + 12 * len(products) + size + sum(
        len(equalities[row][0]) for _, row in derivations)
    return Model(tuple(bounds), c, c0, inequalities, equalities, tuple(products),
                 tuple(derivations), variables, grid, max(1, work))


def leaf_box(model: Model, leaf: Any) -> tuple[tuple[int, ...], tuple[int, ...]]:
    require(type(leaf) is dict and leaf.get("kind") in ("bound", "empty"),
            "LEAF_KIND")
    expected = {"kind", "lower", "upper"}
    if leaf["kind"] == "bound":
        expected |= {"lambda", "nu"}
    _fields(leaf, expected, "LEAF_FIELDS")
    d = len(model.variables)
    require(type(leaf["lower"]) is list and type(leaf["upper"]) is list and
            len(leaf["lower"]) == len(leaf["upper"]) == d, "LEAF_DIMENSION")
    low = tuple(_integer(x, 0, model.grid, "LEAF_COORDINATE")
                for x in leaf["lower"])
    high = tuple(_integer(x, 0, model.grid, "LEAF_COORDINATE")
                 for x in leaf["upper"])
    require(all(a < b for a, b in zip(low, high)), "LEAF_EMPTY_GEOMETRY")
    return low, high


def bounds_for_leaf(model: Model, low: tuple[int, ...], high: tuple[int, ...]
                    ) -> tuple[list[Fraction], list[Fraction], bool]:
    lower = [x[0] for x in model.bounds]
    upper = [x[1] for x in model.bounds]
    for coordinate, variable in enumerate(model.variables):
        base, end = model.bounds[variable]
        width = end - base
        lower[variable] = _checked(base + width * Fraction(low[coordinate], model.grid))
        upper[variable] = _checked(base + width * Fraction(high[coordinate], model.grid))
    for target, row_index in model.derivations:
        row, rhs = model.equalities[row_index]
        coefficient = Fraction(0)
        other_min = other_max = Fraction(0)
        for j, a in row:
            if j == target:
                coefficient = a
            else:
                left, right = a * lower[j], a * upper[j]
                other_min = _checked(other_min + min(left, right))
                other_max = _checked(other_max + max(left, right))
        left = _checked((rhs - other_max) / coefficient)
        right = _checked((rhs - other_min) / coefficient)
        lower[target] = max(lower[target], min(left, right))
        upper[target] = min(upper[target], max(left, right))
        if lower[target] > upper[target]:
            return lower, upper, True
    return lower, upper, False


def _linear(terms: Iterable[tuple[int, Fraction]]) -> Sparse:
    out: dict[int, Fraction] = {}
    for j, coefficient in terms:
        out[j] = _checked(out.get(j, Fraction(0)) + coefficient)
    return tuple((j, value) for j, value in sorted(out.items()) if value)


def relaxed_rows(model: Model, lower: list[Fraction], upper: list[Fraction]
                 ) -> tuple[tuple[Sparse, Fraction], ...]:
    rows = list(model.inequalities)
    for x, y, w in model.products:
        lx, ux, ly, uy = lower[x], upper[x], lower[y], upper[y]
        rows.extend((
            (_linear(((w, Fraction(-1)), (y, lx), (x, ly))), _checked(lx * ly)),
            (_linear(((w, Fraction(-1)), (y, ux), (x, uy))), _checked(ux * uy)),
            (_linear(((w, Fraction(1)), (y, -lx), (x, -uy))), _checked(-lx * uy)),
            (_linear(((w, Fraction(1)), (y, -ux), (x, -ly))), _checked(-ux * ly)),
        ))
    return tuple(rows)


def leaf_upper(model: Model, leaf: Any) -> Fraction | None:
    low, high = leaf_box(model, leaf)
    lower, upper, empty = bounds_for_leaf(model, low, high)
    if leaf["kind"] == "empty":
        require(empty, "UNPROVED_EMPTY_LEAF")
        return None
    require(not empty, "EMPTY_BOX_REQUIRES_EMPTY_RECORD")
    rows = relaxed_rows(model, lower, upper)
    lam = _sparse(leaf["lambda"], len(rows), positive=True)
    nu = _sparse(leaf["nu"], len(model.equalities))
    residual = [Fraction(0)] * len(model.bounds)
    for j, value in model.objective:
        residual[j] = value
    bound = model.constant
    for row_index, weight in lam:
        row, rhs = rows[row_index]
        bound = _checked(bound + weight * rhs)
        for j, coefficient in row:
            residual[j] = _checked(residual[j] - weight * coefficient)
    for row_index, weight in nu:
        row, rhs = model.equalities[row_index]
        bound = _checked(bound + weight * rhs)
        for j, coefficient in row:
            residual[j] = _checked(residual[j] - weight * coefficient)
    for j, value in enumerate(residual):
        bound = _checked(bound + value * (upper[j] if value >= 0 else lower[j]))
    return bound


def check_partition(model: Model, boxes: list[tuple[tuple[int, ...], tuple[int, ...]]]
                    ) -> None:
    """A bounded canonical tree traversal, NOT a volume-only argument."""
    require(0 < len(boxes) <= MAX_LEAVES, "PARTITION_LEAF_COUNT")
    wanted = set(boxes)
    require(len(wanted) == len(boxes), "DUPLICATE_LEAF")
    d = len(model.variables)
    pending = [((0,) * d, (model.grid,) * d)]
    used = set()
    visits = 0
    while pending:
        low, high = pending.pop()
        visits += 1
        require(visits <= 2 * len(boxes) - 1, "PARTITION_NODE_BUDGET_OR_GAP")
        if (low, high) in wanted:
            used.add((low, high))
            continue
        widths = [b - a for a, b in zip(low, high)]
        axis = max(range(d), key=lambda j: widths[j])
        require(widths[axis] > 1 and widths[axis] % 2 == 0,
                "PARTITION_GAP_OR_NONCANONICAL")
        middle = (low[axis] + high[axis]) // 2
        left_high = list(high)
        left_high[axis] = middle
        right_low = list(low)
        right_low[axis] = middle
        pending.append((tuple(right_low), high))
        pending.append((low, tuple(left_high)))
    require(used == wanted, "PARTITION_OVERLAP_OR_EXTRANEOUS")


def verify_records(model: Model, header: Any, records: Iterable[Any], *,
                   model_sha256: str) -> dict[str, Any]:
    _fields(header, {"schema_version", "model_sha256", "claimed_upper", "leaf_count"},
            "CERTIFICATE_HEADER_FIELDS")
    require(header["schema_version"] == CERTIFICATE_VERSION, "CERTIFICATE_VERSION")
    require(_sha(header["model_sha256"]) == _sha(model_sha256), "MODEL_BINDING_MISMATCH")
    target = rational(header["claimed_upper"])
    expected = _integer(header["leaf_count"], 1, MAX_LEAVES, "LEAF_COUNT")
    require(expected * model.leaf_work <= MAX_WORK, "CERTIFICATE_WORK_BUDGET")
    boxes = []
    maximum: Fraction | None = None
    empty_count = 0
    for record in records:
        require(len(boxes) < expected, "ADDITIONAL_LEAVES")
        boxes.append(leaf_box(model, record))
        bound = leaf_upper(model, record)
        if bound is None:
            empty_count += 1
        else:
            require(bound <= target, "UPPER_EXCEEDS_CLAIM")
            maximum = bound if maximum is None else max(bound, maximum)
    require(len(boxes) == expected, "MISSING_LEAVES")
    check_partition(model, boxes)
    return {
        "schema_version": REPORT_VERSION,
        "status": "infeasible_model_certified" if maximum is None else "upper_bound_certified",
        "model_sha256": model_sha256,
        "claimed_upper": str(target),
        "verified_upper": None if maximum is None else str(maximum),
        "strictly_below_claimed_upper": maximum is not None and maximum < target,
        "checked_leaves": len(boxes),
        "bounded_leaves": len(boxes) - empty_count,
        "proved_empty_leaves": empty_count,
        "partition_complete": True,
        "arithmetic": "exact_rational",
        "source_correspondence": "not_established_by_this_checker",
        "feasible_point_established": False,
        "global_optimum_established": False,
        "uses_solver": False,
    }


def verify_point(model: Model, values: Any) -> Fraction:
    """Check a supplied exact feasible point; this is not a point finder."""
    require(type(values) is list and len(values) == len(model.bounds), "POINT_DIMENSION")
    point = [rational(x) for x in values]
    require(all(lo <= x <= hi for x, (lo, hi) in zip(point, model.bounds)), "POINT_BOUNDS")
    for row, rhs in model.inequalities:
        total = Fraction(0)
        for j, a in row:
            total = _checked(total + a * point[j])
        require(total <= rhs, "POINT_INEQUALITY")
    for row, rhs in model.equalities:
        total = Fraction(0)
        for j, a in row:
            total = _checked(total + a * point[j])
        require(total == rhs, "POINT_EQUALITY")
    for x, y, w in model.products:
        require(_checked(point[x] * point[y]) == point[w], "POINT_PRODUCT")
    total = model.constant
    for j, a in model.objective:
        total = _checked(total + a * point[j])
    return total


def _open_regular(path: Path, maximum: int) -> BinaryIO:
    """Trusted quiescent parent directory is required; no link or FIFO fallback."""
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            "UNSAFE_FILE_TYPE_OR_LINK")
    require(before.st_size <= maximum, "FILE_SIZE_LIMIT")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    # O_NONBLOCK avoids blocking if a racing process replaces a regular file by a FIFO.
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        current = os.fstat(descriptor)
        require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
                (before.st_dev, before.st_ino) == (current.st_dev, current.st_ino) and
                current.st_size <= maximum, "FILE_CHANGED_OR_UNSAFE")
        handle = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    return handle


def verify_paths(model_path: Path, certificate_path: Path, *,
                 expected_model_sha256: str, expected_certificate_sha256: str
                 ) -> dict[str, Any]:
    _sha(expected_model_sha256)
    _sha(expected_certificate_sha256)
    with _open_regular(model_path, MAX_MODEL_BYTES) as handle:
        model_bytes = handle.read(MAX_MODEL_BYTES + 1)
    require(len(model_bytes) <= MAX_MODEL_BYTES, "MODEL_BYTE_LIMIT")
    observed_model = hashlib.sha256(model_bytes).hexdigest()
    require(observed_model == expected_model_sha256, "EXTERNAL_MODEL_PIN_MISMATCH")
    model = compile_model(parse_json(model_bytes, MAX_MODEL_BYTES))
    digest = hashlib.sha256()
    consumed = 0
    with _open_regular(certificate_path, MAX_PROOF_BYTES) as handle:
        def lines() -> Iterable[Any]:
            nonlocal consumed
            for index in range(MAX_LEAVES + 2):
                raw = handle.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    return
                require(len(raw) <= MAX_LINE_BYTES and raw.endswith(b"\n"),
                        "PROOF_LINE_TOO_LONG_OR_UNTERMINATED")
                consumed += len(raw)
                require(consumed <= MAX_PROOF_BYTES, "PROOF_BYTE_LIMIT")
                digest.update(raw)
                yield parse_json(raw)
            raise CertificateError("PROOF_LINE_COUNT_LIMIT")
        iterator = iter(lines())
        header = next(iterator, None)
        require(header is not None, "EMPTY_CERTIFICATE_FILE")
        report = verify_records(model, header, iterator, model_sha256=observed_model)
    require(digest.hexdigest() == expected_certificate_sha256,
            "EXTERNAL_CERTIFICATE_PIN_MISMATCH")
    report["certificate_sha256"] = digest.hexdigest()
    report["certificate_bytes"] = consumed
    report["external_byte_pins_checked"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--certificate", required=True, type=Path)
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--expected-certificate-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_paths(args.model, args.certificate,
                              expected_model_sha256=args.expected_model_sha256,
                              expected_certificate_sha256=args.expected_certificate_sha256)
    except (CertificateError, OSError, ValueError, TypeError, RecursionError) as exc:
        # Error codes, not original model text or private file paths, go to logs.
        code = str(exc) if isinstance(exc, CertificateError) else type(exc).__name__
        print(json.dumps({"status": "rejected", "error": code}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
