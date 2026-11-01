"""Conservative source-anchored *literal sentence* mathematics, not paper truth.

RW-MATH-03 recognizes a narrow, self-contained universal one-real-variable
sentence without RW-MATH markers. It proves/refutes only the literal bounded
formalization using the installed exact rational checker. Surrounding prose,
quotation status, publication authenticity, units and scientific applicability
are ALWAYS unresolved. Nonmatched text is never counted as correct or checked.

No network, executable source text, solver, author contact or publication path.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from researchwitness import exact_optimization as exact
from researchwitness import source_claims as marked

SCHEMA = "rw-unmarked-literal-math-screen.v1"
GRAMMAR = "rw-unmarked-one-real-affine-universal.v1"
MAX_SOURCE_BYTES = 1024 * 1024
MAX_LINE_BYTES = 2048
MAX_LINES = 12000
MAX_CANDIDATES = 64
MAX_VARIABLES = 3
MAX_REPORT_BYTES = 1024 * 1024
# Decimal, percentages, implicit ranges, approximate relations, strict
# inequalities, integers-only domains, multi-variable and implied premises
# are deliberately unsupported. Fractions must be reduced/canonical.
_NUMBER = r"-?(?:0|[1-9][0-9]{0,11})(?:/[1-9][0-9]{0,11})?"
_IDENTIFIER = r"[a-z][a-z0-9_]{0,19}"
_VARIABLE_SPEC = r"real " + _IDENTIFIER + r" in \[" + _NUMBER + r", ?" + _NUMBER + r"\]"
_DECLARATIONS = _VARIABLE_SPEC + r"(?: and " + _VARIABLE_SPEC + r"){0,2}"
_SPEC = re.compile(r"real (?P<variable>" + _IDENTIFIER + r") in \["
                   + r"(?P<low>" + _NUMBER + r"), ?(?P<high>" + _NUMBER + r")\]\Z")
_SENTENCE = re.compile(
    r"For (?P<quantifier>every|all|any) (?P<declarations>" + _DECLARATIONS
    + r"), (?P<expression>[A-Za-z0-9_+*/() \-]{1,160}?) "
    + r"(?P<operator><=|≤|is at most|is no greater than) "
    + r"(?P<target>" + _NUMBER + r")\.\Z"
)

_POSSIBLE = ("For every real ", "For all real ", "For any real ")


class UnsupportedSentence(ValueError):
    """A source could not be safely screened or a formal claim was unsupported."""


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise UnsupportedSentence(code)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source_lines(raw: bytes) -> list[tuple[int, int, bytes]]:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES,
             "SOURCE_BYTE_LIMIT")
    try:
        raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise UnsupportedSentence("SOURCE_NOT_UTF8") from exc
    lines: list[tuple[int, int, bytes]] = []
    cursor = 0
    while cursor < len(raw):
        line_end = raw.find(b"\n", cursor)
        end = len(raw) if line_end == -1 else line_end + 1
        line = raw[cursor:end]
        _require(len(line) <= MAX_LINE_BYTES, "SOURCE_LINE_LIMIT")
        # Newline terminators are not part of the mathematical statement.
        text = line[:-1] if line.endswith(b"\n") else line
        if line.endswith(b"\n") and text.endswith(b"\r"):
            text = text[:-1]
        lines.append((cursor, cursor + len(text), text))
        _require(len(lines) <= MAX_LINES, "SOURCE_LINE_COUNT")
        cursor = end
    return lines


def _candidate_model(sentence: bytes) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Only a complete, unquoted single sentence qualifies for formalization."""
    try:
        text = sentence.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise UnsupportedSentence("SENTENCE_ENCODING") from exc
    match = _SENTENCE.fullmatch(text)
    if match is None:
        return None
    try:
        declarations = match["declarations"].split(" and ")
        _require(1 <= len(declarations) <= MAX_VARIABLES, "VARIABLE_COUNT")
        symbols: dict[str, int] = {}
        bounds = []
        for declaration in declarations:
            entry = _SPEC.fullmatch(declaration)
            _require(entry is not None, "VARIABLE_SYNTAX")
            name = entry["variable"]
            _require(name not in symbols, "DUPLICATE_VARIABLE")
            lower, upper = exact.rational(entry["low"]), exact.rational(entry["high"])
            _require(lower < upper, "SENTENCE_REQUIRES_NONFIXED_RANGE")
            symbols[name] = len(symbols)
            bounds.append([str(lower), str(upper)])
        claimed = exact.rational(match["target"])
        expression = match["expression"]
        # Reuse the same AST-only, no-eval affine grammar as RW-MATH-02.
        coefficients, constant = marked._affine(marked._expression(expression), symbols)
        model = {
            "schema_version": exact.MODEL_VERSION,
            "bounds": bounds,
            "objective": {
                "coefficients": [[index, str(value)] for index, value in sorted(coefficients.items()) if value],
                "constant": str(constant),
            },
            "inequalities": [], "equalities": [], "products": [],
            "bound_derivations": [],
            "partition": {"variables": [0], "grid": 1},
        }
        exact.compile_model(model)
    except (marked.UnsupportedClaim, exact.CertificateError, UnsupportedSentence,
            ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise UnsupportedSentence("UNSUPPORTED_SENTENCE_MATH") from exc
    return model, {
        "symbols": list(symbols),
        "quantifier": "forall_reals_in_independent_closed_intervals",
        "claimed_upper": str(claimed),
        "spelled_quantifier": match["quantifier"],
        "spelled_relation": match["operator"],
        "grammar": GRAMMAR,
    }


def _exact_result(model: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    """Certify the box optimum with the generic solver-free exact checker."""
    compiled = exact.compile_model(model)
    model_bytes = exact.canonical_bytes(model)
    model_sha = _digest(model_bytes)
    leaf = {"kind": "bound", "lower": [0], "upper": [1], "lambda": [], "nu": []}
    # Empty-dual interval bounding is exact for a single affine expression
    # on a closed real interval. No heuristic or floating point is involved.
    independently_computed_upper = exact.leaf_upper(compiled, leaf)
    _require(independently_computed_upper is not None, "UNEXPECTED_EMPTY_BOX")
    header = {
        "schema_version": exact.CERTIFICATE_VERSION,
        "model_sha256": model_sha,
        "claimed_upper": str(independently_computed_upper),
        "leaf_count": 1,
    }
    proof = exact.canonical_bytes(header) + exact.canonical_bytes(leaf)
    verified = exact.verify_records(compiled, header, [leaf], model_sha256=model_sha)
    _require(verified["status"] == "upper_bound_certified" and
             verified["verified_upper"] == str(independently_computed_upper),
             "PROOF_REPLAY_MISMATCH")
    # A linear function over a finite product of closed intervals attains its
    # maximum at a corner; sign of each exact coefficient selects that corner.
    objective = dict(compiled.objective)
    point = [str(b if objective.get(i, Fraction(0)) > 0 else a)
             for i, (a, b) in enumerate(compiled.bounds)]
    point_value = exact.verify_point(compiled, point)
    _require(point_value == independently_computed_upper, "ATTAINMENT_MISMATCH")
    _require(point_value == independently_computed_upper, "WITNESS_REPLAY_MISMATCH")
    target = Fraction(claim["claimed_upper"])
    return {
        "formal_result": (
            "model_bound_supported" if independently_computed_upper <= target else "model_bound_refuted"
        ),
        "verified_model_maximum": str(independently_computed_upper),
        "claimed_upper": str(target),
        "exact_attaining_point": point,
        "exact_point_value": str(point_value),
        "counterexample_margin": str(point_value - target) if point_value > target else None,
        "model_sha256": model_sha,
        "exact_certificate_sha256": _digest(proof),
        "coverage": "complete_independent_closed_real_box",
        "proof_engine": "researchwitness.exact_optimization",
        "all_leaf_math_and_coverage_checked": True,
        "global_optimum_of_formal_model_established": True,
        "source_context_interpreted": False,
        "paper_error_established": False,
    }


def scan_source(raw: bytes, *, expected_source_sha256: str) -> dict[str, Any]:
    """Inventory all source lines; parse only fully matching literal sentences.

    No source quotation is emitted. The caller must protect the report according
    to the supplied source's rights. A syntactic match is not a paper assertion.
    """
    exact._sha(expected_source_sha256)
    _require(_digest(raw) == expected_source_sha256, "SOURCE_EXTERNAL_PIN_MISMATCH")
    lines = _source_lines(raw)
    candidates = []
    candidate_like_unsupported = []
    for line_number, (start, end, sentence) in enumerate(lines, 1):
        # Parsing is intentionally bounded and no automatic substring search
        # is allowed: quote/caveat prefixes cannot be dropped.
        prefix = sentence.decode("utf-8", "strict")
        looks_like = prefix.startswith(_POSSIBLE)
        try:
            parsed = _candidate_model(sentence)
        except UnsupportedSentence:
            parsed = None
        if parsed is None:
            if looks_like:
                candidate_like_unsupported.append(line_number)
            continue
        _require(len(candidates) < MAX_CANDIDATES, "CANDIDATE_COUNT_LIMIT")
        model, claim = parsed
        candidate = {
            "line_number": line_number,
            "source_span": {"start": start, "end": end},
            "sentence_sha256": _digest(sentence),
            "literal_grammar": GRAMMAR,
            "symbols": claim["symbols"],
            "quantifier": claim["quantifier"],
            "claimed_upper": claim["claimed_upper"],
            "model": model,
            "math": _exact_result(model, claim),
            "source_origin_authenticated": False,
            "surrounding_prose_adjudicated": False,
            "is_pub_claim_or_quotation_resolved": False,
        }
        candidates.append(candidate)
    return {
        "schema_version": SCHEMA,
        "source_sha256": _digest(raw),
        "source_byte_length": len(raw),
        "scan": {
            "lines_examined": len(lines),
            "literal_candidates": len(candidates),
            "candidate_like_unsupported_lines": candidate_like_unsupported,
            "unrecognized_lines": len(lines) - len(candidates),
            "entire_article_semantics_examined": False,
            "absence_of_errors_established": False,
        },
        "candidates": candidates,
        "scientific_accuracy_established": False,
        "source_origin_authenticated": False,
        "interpretation_of_context": "unresolved_for_every_candidate",
        "external_actions": "NONE",
    }


def replay_report(source: bytes, report: bytes, *, expected_source_sha256: str,
                  expected_report_sha256: str) -> dict[str, Any]:
    exact._sha(expected_report_sha256)
    _require(_digest(report) == expected_report_sha256, "REPORT_EXTERNAL_PIN_MISMATCH")
    _require(type(report) is bytes and len(report) <= MAX_REPORT_BYTES,
             "REPORT_SIZE_LIMIT")
    # Parse first to ensure duplicate keys/nonfinite literals fail closed even
    # when an attacker obtains a matching digest for a malformed report.
    exact.parse_json(report, MAX_REPORT_BYTES)
    regenerated = scan_source(source, expected_source_sha256=expected_source_sha256)
    _require(report == exact.canonical_bytes(regenerated), "REPORT_REPLAY_MISMATCH")
    return regenerated


def _read(path: Path, limit: int) -> bytes:
    with exact._open_regular(path, limit) as handle:
        raw = handle.read(limit + 1)
    _require(len(raw) <= limit, "INPUT_BYTES")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("scan", "replay"):
        command = sub.add_parser(action)
        command.add_argument("--source", required=True, type=Path)
        command.add_argument("--expected-source-sha256", required=True)
        if action == "scan":
            command.add_argument("--output", type=Path)
        else:
            command.add_argument("--report", required=True, type=Path)
            command.add_argument("--expected-report-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        raw = _read(args.source, MAX_SOURCE_BYTES)
        if args.action == "scan":
            report = scan_source(raw, expected_source_sha256=args.expected_source_sha256)
            encoded = exact.canonical_bytes(report)
            _require(len(encoded) <= MAX_REPORT_BYTES, "REPORT_SIZE_LIMIT")
            if args.output is not None:
                _require(args.source.resolve() != args.output.resolve(), "OUTPUT_IS_SOURCE")
                with args.output.open("xb") as handle:
                    handle.write(encoded)
                output = {"status": "saved_candidate_screen", "report_sha256": _digest(encoded),
                          "candidate_count": report["scan"]["literal_candidates"],
                          "source_context_verified": False}
                print(json.dumps(output, sort_keys=True))
            else:
                sys.stdout.buffer.write(encoded)
        else:
            current = _read(args.report, MAX_REPORT_BYTES)
            result = replay_report(raw, current,
                                   expected_source_sha256=args.expected_source_sha256,
                                   expected_report_sha256=args.expected_report_sha256)
            print(json.dumps({"status": "exact_replay_complete",
                              "source_sha256": result["source_sha256"],
                              "report_sha256": _digest(current),
                              "candidate_count": result["scan"]["literal_candidates"],
                              "source_context_verified": False}, sort_keys=True))
    except (UnsupportedSentence, marked.UnsupportedClaim, exact.CertificateError,
            UnicodeError, OSError, TypeError, ValueError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, (UnsupportedSentence, exact.CertificateError)) else type(exc).__name__
        print(json.dumps({"status": "rejected", "error": code}, sort_keys=True), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
