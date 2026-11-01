"""Source-bound, deliberately narrow mathematical *candidate* formalizations.

Explicit RW-MATH marked claims only. This module parses no arbitrary prose,
runs no source code, and never decides scientific truth or source authenticity.
Every supported statement is rederived from an exact UTF-8 byte span; a supplied
mathematical proof is checked by the separate exact_optimization verifier.
"""
from __future__ import annotations

import ast
from fractions import Fraction
import hashlib
import re
from typing import Any

from researchwitness import exact_optimization as exact

SCHEMA = "rw-source-claim-candidate.v1"
HINTS_SCHEMA = "rw-source-claim-hints.v1"
BEGIN = b"RW-MATH-BEGIN v1"
END = b"RW-MATH-END"
MAX_SOURCE_BYTES = 1_048_576
MAX_BLOCK_BYTES = 4096
MAX_BLOCKS = 16
MAX_AST_NODES = 64
MAX_AST_DEPTH = 14
MAX_EXPRESSION_CHARS = 256
MAX_SYMBOLS = 12
MAX_CONSTRAINTS = 32
_EXPR_CHARS = re.compile(r"[A-Za-z0-9_+*/<>=() \-]+\Z")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,19}\Z")
_DECLARATION = re.compile(r"([a-z][a-z0-9_]{0,19})\[([^,\]]{1,64}),([^\]]{1,64})\]\Z")


class UnsupportedClaim(ValueError):
    """The source fragment exceeds the intentionally strict grammar."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise UnsupportedClaim(code)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _line(value: bytes) -> bytes:
    # Only LF and CRLF are admitted; a stray CR or NUL is not normalized away.
    require(value.endswith(b"\n"), "SOURCE_LINE_ENDING")
    content = value[:-1]
    if content.endswith(b"\r"):
        content = content[:-1]
    require(b"\r" not in content and b"\x00" not in content, "SOURCE_LINE_CONTROL")
    return content


def _source_lines(source: bytes) -> list[tuple[int, int, bytes]]:
    require(type(source) is bytes and 0 < len(source) <= MAX_SOURCE_BYTES,
            "SOURCE_BYTES")
    try:
        source.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise UnsupportedClaim("SOURCE_UTF8") from exc
    # Complete source must end in LF. That also prevents truncating a final
    # lexical marker by ignoring an unterminated line.
    require(source.endswith(b"\n"), "SOURCE_FINAL_LF")
    output = []
    pos = 0
    for raw in source.splitlines(keepends=True):
        require(raw.endswith(b"\n"), "SOURCE_LINE_ENDING")
        line = _line(raw)
        output.append((pos, pos + len(raw), line))
        pos += len(raw)
    require(pos == len(source), "SOURCE_LINE_ACCOUNTING")
    return output


def select_block(source: bytes, block_index: int) -> dict[str, Any]:
    """Find all strict markers, then select one by explicit zero-based index."""
    lines = _source_lines(source)
    starts: list[int] = []
    blocks: list[tuple[int, int]] = []
    for first, last, line in lines:
        if line == BEGIN:
            require(not starts, "NESTED_CLAIM_MARKER")
            starts.append(first)
            require(len(blocks) + 1 <= MAX_BLOCKS, "CLAIM_COUNT_LIMIT")
        elif line == END:
            require(len(starts) == 1, "ORPHAN_CLAIM_END")
            begin = starts.pop()
            require(last - begin <= MAX_BLOCK_BYTES, "CLAIM_BLOCK_BYTES")
            blocks.append((begin, last))
    require(not starts, "UNCLOSED_CLAIM_MARKER")
    require(blocks, "NO_EXPLICIT_CLAIM")
    require(type(block_index) is int and 0 <= block_index < len(blocks),
            "CLAIM_INDEX")
    first, last = blocks[block_index]
    body = source[first:last]
    return {
        "start": first, "end": last, "source_sha256": _sha(source),
        "source_bytes": len(source), "block_sha256": _sha(body),
        "block_index": block_index, "block_count": len(blocks),
        "raw_block": body,
    }


def _expression(text: str) -> ast.expr:
    require(type(text) is str and 0 < len(text) <= MAX_EXPRESSION_CHARS,
            "EXPR_LENGTH")
    # ASCII only: no homoglyphs, Unicode mathematical operators, formatting
    # controls or fullwidth digits can be silently interpreted as names.
    require(text.isascii() and _EXPR_CHARS.fullmatch(text) is not None,
            "EXPR_UNSUPPORTED_CHARACTER")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise UnsupportedClaim("EXPR_SYNTAX") from exc
    nodes = [(tree, 0)]
    seen = 0
    while nodes:
        node, depth = nodes.pop()
        seen += 1
        require(seen <= MAX_AST_NODES and depth <= MAX_AST_DEPTH,
                "EXPR_STRUCTURE")
        nodes.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return tree.body


def _constant_number(node: ast.AST) -> Fraction:
    if isinstance(node, ast.Constant):
        require(type(node.value) is int and abs(node.value) <= 10**12,
                "INTEGER_LITERAL")
        return Fraction(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        require(not (isinstance(node.op, ast.USub) and
                     isinstance(node.operand, ast.Constant) and
                     type(node.operand.value) is int and node.operand.value == 0),
                "NEGATIVE_ZERO_LITERAL")
        value = _constant_number(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub,
                                                             ast.Mult, ast.Div)):
        left = _constant_number(node.left)
        right = _constant_number(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        require(right != 0, "DIVISION_BY_ZERO")
        return left / right
    raise UnsupportedClaim("NOT_A_RATIONAL_CONSTANT")


def _affine(node: ast.AST, symbols: dict[str, int]) -> tuple[dict[int, Fraction], Fraction]:
    """A strict symbolic linear expression; no eval or arbitrary Python AST."""
    if isinstance(node, ast.Name):
        require(node.id in symbols, "UNDECLARED_VARIABLE")
        return {symbols[node.id]: Fraction(1)}, Fraction(0)
    if isinstance(node, ast.Constant):
        return {}, _constant_number(node)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        coeff, constant = _affine(node.operand, symbols)
        sign = -1 if isinstance(node.op, ast.USub) else 1
        return {i: sign * a for i, a in coeff.items()}, sign * constant
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub,
                                                             ast.Mult, ast.Div)):
        lhs, lc = _affine(node.left, symbols)
        rhs, rc = _affine(node.right, symbols)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            sign = 1 if isinstance(node.op, ast.Add) else -1
            out = lhs.copy()
            for j, val in rhs.items():
                out[j] = out.get(j, Fraction(0)) + sign * val
            return {j: val for j, val in out.items() if val}, lc + sign * rc
        if isinstance(node.op, ast.Mult):
            require(not (lhs and rhs), "NONLINEAR_AFFINE")
            if lhs:
                return {j: val * rc for j, val in lhs.items()}, lc * rc
            if rhs:
                return {j: val * lc for j, val in rhs.items()}, lc * rc
            return {}, lc * rc
        require(not rhs and rc != 0, "VARIABLE_DIVISION_OR_ZERO")
        return {j: val / rc for j, val in lhs.items()}, lc / rc
    raise UnsupportedClaim("UNSUPPORTED_EXPRESSION_NODE")


def _constant(text: str) -> Fraction:
    return _constant_number(_expression(text))


def _sparse(coeff: dict[int, Fraction]) -> list[list[Any]]:
    return [[j, str(a)] for j, a in sorted(coeff.items()) if a]


def _parse_claim(body: bytes) -> tuple[dict[str, Any], str, list[str]]:
    try:
        contents = body.decode("ascii")
    except UnicodeError as exc:
        raise UnsupportedClaim("CLAIM_NON_ASCII") from exc
    lines = contents.splitlines()
    require(len(lines) == 7 and lines[0] == "RW-MATH-BEGIN v1" and
            lines[1] == "domain: bounded_real" and lines[-1] == "RW-MATH-END",
            "CLAIM_LINE_SHAPE")
    tags = ("variables: ", "maximize: ", "constraints: ", "upper_bound: ")
    # Exact four semantic lines; comments, modifiers and hidden extra lines
    # are rejected instead of silently ignored or treated as mathematical facts.
    require(lines[2].startswith(tags[0]) and lines[3].startswith(tags[1])
            and lines[4].startswith(tags[2]) and lines[5].startswith(tags[3]),
            "CLAIM_TAG_ORDER")
    declaration = lines[2][len(tags[0]):]
    variables = declaration.split("; ")
    require(0 < len(variables) <= MAX_SYMBOLS, "VARIABLE_COUNT")
    symbols: dict[str, int] = {}
    bounds = []
    for item in variables:
        item = item.strip()
        match = _DECLARATION.fullmatch(item)
        require(match is not None, "VARIABLE_DECLARATION")
        name, left, right = match.groups()
        require(name not in symbols and _IDENTIFIER.fullmatch(name) is not None,
                "DUPLICATE_OR_BAD_SYMBOL")
        lo, hi = _constant(left), _constant(right)
        require(lo <= hi, "VARIABLE_BOUNDS_CONTRADICTION")
        symbols[name] = len(symbols)
        bounds.append([str(lo), str(hi)])
    objective, offset = _affine(_expression(lines[3][len(tags[1]):]), symbols)
    text = lines[4][len(tags[2]):]
    require(text != "" and len(text) <= 2048, "CONSTRAINT_TEXT_LENGTH")
    statements = [] if text == "none" else text.split("; ")
    require(len(statements) <= MAX_CONSTRAINTS, "CONSTRAINT_COUNT")
    inequalities = []
    equalities = []
    products = []
    for statement in statements:
        expr = _expression(statement)
        require(isinstance(expr, ast.Compare) and len(expr.ops) == 1 and
                len(expr.comparators) == 1, "CONSTRAINT_COMPARISON")
        cmp = expr.ops[0]
        require(isinstance(cmp, (ast.Eq, ast.LtE, ast.GtE)), "CONSTRAINT_RELATION")
        left, right = expr.left, expr.comparators[0]
        if (isinstance(cmp, ast.Eq) and isinstance(left, ast.Name) and
                isinstance(right, ast.BinOp) and isinstance(right.op, ast.Mult)
                and isinstance(right.left, ast.Name) and
                isinstance(right.right, ast.Name)):
            for name in (left.id, right.left.id, right.right.id):
                require(name in symbols, "UNDECLARED_PRODUCT_SYMBOL")
            triple = [symbols[right.left.id], symbols[right.right.id], symbols[left.id]]
            require(triple[2] not in triple[:2], "PRODUCT_OUTPUT_IS_FACTOR")
            require(triple not in products, "DUPLICATE_PRODUCT")
            products.append(triple)
            continue
        lc, lk = _affine(left, symbols)
        rc, rk = _affine(right, symbols)
        # Write sum_j(a[j]*x[j]) <= rhs, even if input comparison was >=.
        sign = -1 if isinstance(cmp, ast.GtE) else 1
        coefficients = {j: sign * (lc.get(j, Fraction(0)) - rc.get(j, Fraction(0)))
                        for j in set(lc) | set(rc)}
        statement_row = {"coefficients": _sparse(coefficients),
                         "rhs": str(sign * (rk - lk))}
        if isinstance(cmp, ast.Eq):
            equalities.append(statement_row)
        else:
            inequalities.append(statement_row)
    target = _constant(lines[5][len(tags[3]):])
    return ({
        "schema_version": exact.MODEL_VERSION,
        "bounds": bounds,
        "objective": {"coefficients": _sparse(objective), "constant": str(offset)},
        "inequalities": inequalities,
        "equalities": equalities,
        "products": products,
        "bound_derivations": [],
        "partition": {"variables": [], "grid": 1},
    }, str(target), list(symbols))


def _apply_hints(model: dict[str, Any], variables: list[str], hints: Any
                 ) -> tuple[dict[str, Any], str]:
    if hints is None:
        hints = {"schema_version": HINTS_SCHEMA, "partition": None, "derive": []}
    exact._fields(hints, {"schema_version", "partition", "derive"}, "SOURCE_HINT_FIELDS")
    require(hints["schema_version"] == HINTS_SCHEMA, "SOURCE_HINT_VERSION")
    names = {name: i for i, name in enumerate(variables)}
    if hints["partition"] is None:
        nonfixed = [i for i, (lo, hi) in enumerate(model["bounds"]) if
                    Fraction(lo) < Fraction(hi)]
        require(nonfixed, "ALL_VARIABLES_FIXED_UNSUPPORTED_PARTITION")
        partition = {"variables": [nonfixed[0]], "grid": 1}
    else:
        raw = exact._fields(hints["partition"], {"variables", "grid"},
                            "SOURCE_HINT_PARTITION")
        arr = raw["variables"]
        require(type(arr) is list and 1 <= len(arr) <= exact.MAX_DIMENSIONS,
                "SOURCE_HINT_PARTITION_SIZE")
        require(all(type(x) is str and x in names for x in arr),
                "SOURCE_HINT_UNKNOWN_VARIABLE")
        idx = [names[x] for x in arr]
        require(idx == sorted(set(idx)), "SOURCE_HINT_PARTITION_ORDER")
        partition = {"variables": idx, "grid": raw["grid"]}
    model["partition"] = partition
    raw_derive = hints["derive"]
    require(type(raw_derive) is list and len(raw_derive) <= 32,
            "SOURCE_HINT_DERIVE_COUNT")
    derivations = []
    for entry in raw_derive:
        exact._fields(entry, {"variable", "equality_index"}, "SOURCE_HINT_DERIVE_FIELDS")
        var, row = entry["variable"], entry["equality_index"]
        require(type(var) is str and var in names and type(row) is int,
                "SOURCE_HINT_DERIVE_ENTRY")
        derivations.append([names[var], row])
    model["bound_derivations"] = derivations
    # The exact verifier refuses invalid derivations/partitions, ensuring hints
    # can never create new mathematical facts, modify the objective or assumptions.
    exact.compile_model(model)
    return model, _sha(exact.canonical_bytes(hints))


def compile_candidate(source: bytes, *, block_index: int,
                      expected_source_sha256: str, hints: Any = None
                      ) -> tuple[dict[str, Any], dict[str, Any]]:
    exact._sha(expected_source_sha256)
    selected = select_block(source, block_index)
    require(selected["source_sha256"] == expected_source_sha256,
            "EXTERNAL_SOURCE_PIN_MISMATCH")
    model, target, variables = _parse_claim(selected["raw_block"])
    model, hint_digest = _apply_hints(model, variables, hints)
    model_digest = _sha(exact.canonical_bytes(model))
    candidate = {
        "schema_version": SCHEMA,
        "status": "source_bound_model_candidate_only",
        "claim_domain": "all_bounded_real_assignments",
        "source_scope": "explicit_marker_block_only",
        "source_sha256": selected["source_sha256"],
        "source_byte_length": selected["source_bytes"],
        "source_span": {"start": selected["start"], "end": selected["end"]},
        "source_block_sha256": selected["block_sha256"],
        "selected_block_index": selected["block_index"],
        "explicit_block_count": selected["block_count"],
        "model_sha256": model_digest,
        "hints_sha256": hint_digest,
        "claimed_upper": target,
        "source_origin_authenticated": False,
        "unmarked_source_context_interpreted": False,
        "external_scientific_accuracy_established": False,
        "mathematical_certificate_verified": False,
    }
    return candidate, model


def recheck_candidate(source: bytes, *, block_index: int,
                      expected_source_sha256: str, candidate_bytes: bytes,
                      model_bytes: bytes, expected_candidate_sha256: str,
                      expected_model_sha256: str, hints: Any = None
                      ) -> tuple[dict[str, Any], dict[str, Any]]:
    exact._sha(expected_candidate_sha256)
    exact._sha(expected_model_sha256)
    require(_sha(candidate_bytes) == expected_candidate_sha256,
            "EXTERNAL_CANDIDATE_PIN_MISMATCH")
    require(_sha(model_bytes) == expected_model_sha256,
            "EXTERNAL_MODEL_PIN_MISMATCH")
    candidate = exact.parse_json(candidate_bytes, exact.MAX_MODEL_BYTES)
    model = exact.parse_json(model_bytes, exact.MAX_MODEL_BYTES)
    regenerated_candidate, regenerated_model = compile_candidate(
        source, block_index=block_index,
        expected_source_sha256=expected_source_sha256, hints=hints)
    require(candidate == regenerated_candidate and model == regenerated_model,
            "SOURCE_CANDIDATE_REDERIVATION_MISMATCH")
    require(model_bytes == exact.canonical_bytes(regenerated_model) and
            candidate_bytes == exact.canonical_bytes(regenerated_candidate),
            "SOURCE_CANDIDATE_NONCANONICAL_BYTES")
    return regenerated_candidate, regenerated_model
