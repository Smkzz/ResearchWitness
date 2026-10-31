"""Separate AI-authored development checker: dense rows / integer arithmetic.

Algorithm contributed by LocalControl agent agt-6a438a8b0fbf4b31, without
reading the primary implementation. Coordinator added aligned input/resource
limits. No primary verifier imports. No file, JSON, or network acquisition:
callers must separately verify actual external byte pins. This is not external
human validation or source-to-model authentication.
"""
from fractions import Fraction
from math import lcm
import re

_MODEL = "rw-exact-bilinear-model.v1"
_CERT = "rw-exact-bilinear-certificate.v1"
_ZERO = Fraction(0)
_ONE = Fraction(1)


class _Reject(ValueError):
    pass


def _need(condition, message):
    if not condition:
        raise _Reject(message)


def _keys(value, names, label):
    _need(type(value) is dict and all(type(k) is str for k in value)
          and set(value) == set(names), label + ": incorrect fields")


def _list(value, label, cap=None):
    _need(type(value) is list, label + ": expected list")
    if cap is not None:
        _need(len(value) <= cap, label + ": resource cap exceeded")
    return value


def _index(value, size, label):
    _need(type(value) is int and 0 <= value < size, label + ": invalid index")
    return value


def _rational(value):
    _need(type(value) is str, "rational must be a string")
    _need(len(value) <= 62 and re.fullmatch(
        r"-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?", value) is not None,
        "invalid rational syntax")
    parts = value.split("/")
    numerator = parts[0]
    denominator = parts[1] if len(parts) == 2 else "1"
    _need(len(numerator.lstrip("-")) <= 30 and len(denominator) <= 30,
          "rational exceeds 30 digits per part")
    result = Fraction(int(numerator), int(denominator))
    _need(str(result) == value, "noncanonical rational")
    return result


def _cap(value):
    _need(value.numerator.bit_length() <= 4096 and
          value.denominator.bit_length() <= 4096, "reference arithmetic budget")
    return value


def _sparse(value, size, label, positive=False):
    _list(value, label, size)
    result = []
    previous = -1
    for pair in value:
        _list(pair, label + " entry")
        _need(len(pair) == 2, label + ": wrong entry length")
        index = _index(pair[0], size, label)
        _need(index > previous, label + ": indices must strictly increase")
        coefficient = _rational(pair[1])
        _need(coefficient != 0, label + ": zero coefficient")
        if positive:
            _need(coefficient > 0, label + ": multiplier must be positive")
        result.append((index, coefficient))
        previous = index
    return result


def _dense(value, n, label):
    row = [_ZERO] * n
    for index, coefficient in _sparse(value, n, label):
        row[index] = coefficient
    return row


def _rows(value, n, label):
    _list(value, label, 1024)
    matrix, rhs = [], []
    for row in value:
        _keys(row, ("coefficients", "rhs"), label)
        matrix.append(_dense(row["coefficients"], n, label))
        rhs.append(_rational(row["rhs"]))
    return matrix, rhs


def _coordinates(value, d, grid, label):
    _list(value, label)
    _need(len(value) == d, label + ": wrong dimension")
    for coordinate in value:
        _need(type(coordinate) is int and 0 <= coordinate <= grid,
              label + ": invalid grid coordinate")


def _tree_path(lower, upper, grid):
    d = len(lower)
    current_lower, current_upper = [0] * d, [grid] * d
    path = []
    while True:
        if current_lower == lower and current_upper == upper:
            return "".join(path)
        k = max(range(d), key=lambda j: current_upper[j] - current_lower[j])
        width = current_upper[k] - current_lower[k]
        _need(width > 1, "leaf box is not a canonical tree node")
        middle = (current_lower[k] + current_upper[k]) // 2
        if upper[k] <= middle:
            current_upper[k] = middle
            path.append("0")
        elif lower[k] >= middle:
            current_lower[k] = middle
            path.append("1")
        else:
            raise _Reject("leaf box crosses a canonical split")


def _coverage(paths):
    """Bottom-up sibling merging, unlike the primary top-down traversal."""
    _need(len(set(paths)) == len(paths), "duplicate leaf")
    levels = [set() for _ in range(max(map(len, paths)) + 1)]
    for path in paths:
        levels[len(path)].add(path)
    for depth in range(len(levels) - 1, 0, -1):
        current = levels[depth]
        for path in tuple(current):
            if path not in current:
                continue
            sibling = path[:-1] + ("1" if path[-1] == "0" else "0")
            _need(sibling in current, "partition has a gap or overlap")
            parent = path[:-1]
            _need(parent not in levels[depth - 1], "ancestor overlap")
            current.remove(path)
            current.remove(sibling)
            levels[depth - 1].add(parent)
    _need(levels[0] == {""}, "partition does not cover the root")


def _leaf_intervals(bounds, variables, grid, leaf, E, f, derivations):
    lower, upper = [p[0] for p in bounds], [p[1] for p in bounds]
    for k, variable in enumerate(variables):
        a, b = bounds[variable]
        lower[variable] = _cap(a + (b - a) * Fraction(leaf["lower"][k], grid))
        upper[variable] = _cap(a + (b - a) * Fraction(leaf["upper"][k], grid))
    for target, equality in derivations:
        row = E[equality]
        sum_lower = sum_upper = _ZERO
        for j, coefficient in enumerate(row):
            if j == target or coefficient == 0:
                continue
            a, b = coefficient * lower[j], coefficient * upper[j]
            sum_lower = _cap(sum_lower + min(a, b))
            sum_upper = _cap(sum_upper + max(a, b))
        a = _cap((f[equality] - sum_upper) / row[target])
        b = _cap((f[equality] - sum_lower) / row[target])
        lower[target] = max(lower[target], min(a, b))
        upper[target] = min(upper[target], max(a, b))
        if lower[target] > upper[target]:
            return lower, upper, True
    return lower, upper, False


def _mccormick(n, products, lower, upper):
    matrix, rhs = [], []
    def append(terms, bound):
        row = [_ZERO] * n
        for column, coefficient in terms:
            row[column] = _cap(row[column] + coefficient)
        matrix.append(row)
        rhs.append(_cap(bound))
    for x, y, w in products:
        lx, ux, ly, uy = lower[x], upper[x], lower[y], upper[y]
        append(((w, -_ONE), (y, lx), (x, ly)), lx * ly)
        append(((w, -_ONE), (y, ux), (x, uy)), ux * uy)
        append(((w, _ONE), (y, -lx), (x, -uy)), -lx * uy)
        append(((w, _ONE), (y, -ux), (x, -ly)), -ux * ly)
    return matrix, rhs


def _integer_bound(c0, c, A, b, E, f, lower, upper, lam, nu, claim):
    """Independent integer scaling: residual numerator / D**2, bound / D**3.

    Coordinator optimization after a bounded full replay timed out: only rows
    with nonzero multipliers enter the expression, so only those rows need
    scaling. All constraints are still reconstructed and all input checked.
    """
    active = [(weight, A[i], b[i]) for i, weight in lam]
    active += [(weight, E[i], f[i]) for i, weight in nu]
    # Dense row construction is independent of the primary sparse compiler.
    # Drop exact zero columns only when evaluating this fixed scalar sum.
    active = [(weight, [(j, a) for j, a in enumerate(row) if a], rhs)
              for weight, row, rhs in active]
    denominator = 1
    def absorb(values):
        nonlocal denominator
        for value in values:
            denominator = lcm(denominator, value.denominator)
            _need(denominator.bit_length() <= 2048, "reference LCM budget")
    absorb((c0, claim))
    for vector in (c, lower, upper):
        absorb(vector)
    for weight, row, rhs in active:
        absorb((weight, rhs))
        absorb(a for _, a in row)
    D = denominator
    def integer(value):
        return value.numerator * (D // value.denominator)
    residual = [integer(value) * D for value in c]
    numerator = integer(c0) * D * D
    for weight, row, rhs in active:
        multiplier = integer(weight)
        numerator += multiplier * integer(rhs) * D
        for j, coefficient in row:
            residual[j] -= multiplier * integer(coefficient)
    for j, value in enumerate(residual):
        numerator += max(value * integer(lower[j]), value * integer(upper[j]))
    _need(numerator <= integer(claim) * D * D,
          "leaf upper bound exceeds claimed_upper")
    return _cap(Fraction(numerator, D * D * D))


def _verify(model, header, leaves):
    _keys(model, ("schema_version", "bounds", "objective", "inequalities",
                  "equalities", "products", "bound_derivations", "partition"), "model")
    _need(model["schema_version"] == _MODEL, "unsupported model schema")
    raw_bounds = _list(model["bounds"], "bounds", 128)
    n = len(raw_bounds)
    _need(n >= 1, "model must have at least one variable")
    bounds = []
    for pair in raw_bounds:
        _list(pair, "bound pair")
        _need(len(pair) == 2, "wrong bound pair length")
        lower, upper = map(_rational, pair)
        _need(lower <= upper, "contradictory global bounds")
        bounds.append((lower, upper))
    objective = model["objective"]
    _keys(objective, ("coefficients", "constant"), "objective")
    c = _dense(objective["coefficients"], n, "objective coefficients")
    c0 = _rational(objective["constant"])
    A, b = _rows(model["inequalities"], n, "inequality")
    E, f = _rows(model["equalities"], n, "equality")
    raw_products = _list(model["products"], "products", 128)
    _need(len(A) + len(E) + 4 * len(raw_products) <= 1024,
          "total dense constraint row cap exceeded")
    products = []
    for product in raw_products:
        _list(product, "product")
        _need(len(product) == 3, "wrong product length")
        item = tuple(_index(v, n, "product column") for v in product)
        _need(item[2] not in item[:2] and item not in products,
              "unsupported product alias or duplicate")
        products.append(item)
    nonzeros = sum(v != 0 for v in c) + sum(v != 0 for row in A + E for v in row)
    _need(nonzeros + 12 * len(products) <= 16384, "nonzero budget")
    derivations = []
    for item in _list(model["bound_derivations"], "bound_derivations", 128):
        _list(item, "bound derivation")
        _need(len(item) == 2, "wrong bound derivation length")
        target = _index(item[0], n, "derivation target")
        equality = _index(item[1], len(E), "derivation equality")
        _need(E[equality][target] != 0, "zero derivation target coefficient")
        _need((target, equality) not in derivations, "duplicate derivation")
        derivations.append((target, equality))
    partition = model["partition"]
    _keys(partition, ("variables", "grid"), "partition")
    variables = _list(partition["variables"], "partition variables", 8)
    _need(len(variables) >= 1, "partition needs at least one variable")
    for variable in variables:
        _index(variable, n, "partition variable")
    _need(sorted(set(variables)) == variables, "partition variable order")
    _need(all(bounds[v][0] < bounds[v][1] for v in variables), "fixed split variable")
    grid = partition["grid"]
    _need(type(grid) is int and 1 <= grid <= 1024 and (grid & (grid - 1)) == 0,
          "invalid dyadic grid")
    d = len(variables)
    _keys(header, ("schema_version", "model_sha256", "claimed_upper", "leaf_count"), "header")
    _need(header["schema_version"] == _CERT, "unsupported certificate schema")
    digest = header["model_sha256"]
    _need(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
          "invalid model_sha256")
    claim = _rational(header["claimed_upper"])
    count = header["leaf_count"]
    _need(type(count) is int and 1 <= count <= 32768, "invalid leaf_count")
    _list(leaves, "leaves", 32768)
    _need(len(leaves) == count, "leaf_count mismatch")
    per_leaf = nonzeros + 12 * len(products) + n + sum(
        sum(v != 0 for v in E[row]) for _, row in derivations)
    _need(max(1, per_leaf) * count <= 40_000_000, "work budget")
    _need(count * (len(A) + len(E) + 4 * len(products)) * n <= 200_000_000,
          "reference dense work budget")
    paths = []
    for leaf in leaves:
        _need(type(leaf) is dict, "leaf must be a dictionary")
        kind = leaf.get("kind")
        _need(type(kind) is str and kind in ("bound", "empty"), "invalid leaf kind")
        fields = (("kind", "lower", "upper", "lambda", "nu") if kind == "bound"
                  else ("kind", "lower", "upper"))
        _keys(leaf, fields, "leaf")
        _coordinates(leaf["lower"], d, grid, "leaf lower")
        _coordinates(leaf["upper"], d, grid, "leaf upper")
        _need(all(a < b for a, b in zip(leaf["lower"], leaf["upper"])), "leaf widths")
        paths.append(_tree_path(leaf["lower"], leaf["upper"], grid))
    _coverage(paths)
    maximum = None
    bounded = empty = 0
    for leaf in leaves:
        if leaf["kind"] == "bound":
            lam = _sparse(leaf["lambda"], len(A) + 4 * len(products), "lambda", positive=True)
            nu = _sparse(leaf["nu"], len(E), "nu")
        else:
            lam, nu = [], []
        lower, upper, contradictory = _leaf_intervals(
            bounds, variables, grid, leaf, E, f, derivations)
        if leaf["kind"] == "empty":
            _need(contradictory, "empty leaf lacks interval contradiction")
            empty += 1
            continue
        _need(not contradictory, "bound leaf has contradictory intervals")
        extra_A, extra_b = _mccormick(n, products, lower, upper)
        value = _integer_bound(c0, c, A + extra_A, b + extra_b, E, f,
                               lower, upper, lam, nu, claim)
        maximum = value if maximum is None else max(maximum, value)
        bounded += 1
    return {"valid": True, "status": "verified", "maximum_upper": None if maximum is None else str(maximum),
            "bounded_leaves": bounded, "empty_leaves": empty, "complete_coverage": True}


def reference_verify(model: dict, header: dict, leaves: list[dict]) -> dict:
    """Syntax and math only: external acquisition/hash binding is caller-owned."""
    try:
        return _verify(model, header, leaves)
    except _Reject as error:
        reason = str(error)
        limited = "budget" in reason or "cap exceeded" in reason or "exceeds 30 digits" in reason
        return {"valid": False, "status": "inconclusive" if limited else "rejected",
                "error": reason}
