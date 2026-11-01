"""RW-MATH-04: strictly declared, source-byte-bound literal attribution.

This opt-in processor labels a complete existing prose_math candidate only
when an adjacent, versioned *source declaration* names its context role.
These roles are untrusted declarations, not authenticated author intent, paper
truth or scientific review. Mathematical results are regenerated unchanged.
No natural-language attribution heuristics, network, dynamic code or solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from researchwitness import exact_optimization as exact
from researchwitness import prose_math as literal

SCHEMA = "rw-source-declared-prose-attribution.v1"
PROFILE = "rw-adjacent-literal-context.v1"
MAX_SOURCE_BYTES = literal.MAX_SOURCE_BYTES
MAX_REPORT_BYTES = 1024 * 1024
MAX_BLOCKS = 64
_ID = rb"([a-z][a-z0-9_]{0,31})"
_ROLE = rb"(asserted|quoted|negated|hypothetical|corrected)"
_BEGIN = re.compile(rb"RW-MATH-CONTEXT-BEGIN v1 id=" + _ID + rb" role=" + _ROLE + rb"\Z")
_END = re.compile(rb"RW-MATH-CONTEXT-END v1 id=" + _ID + rb"\Z")
_MARKER = b"RW-MATH-CONTEXT"


class AttributionError(ValueError):
    """A context declaration or its immutable evidence was rejected."""


def require(value: bool, code: str) -> None:
    if not value:
        raise AttributionError(code)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _span(start: int, end: int) -> dict[str, int]:
    return {"start": start, "end": end}


def _interpret(role: str, math: dict[str, Any]) -> str:
    result = math["formal_result"]
    require(result in ("model_bound_supported", "model_bound_refuted"),
            "UNSUPPORTED_FORMAL_RESULT")
    suffix = "refuted" if result == "model_bound_refuted" else "supported"
    # The prefix is always a *declared* role. It does not identify an author.
    return f"declared_{role}_literal_{suffix}"


def attribute_source(raw: bytes, *, expected_source_sha256: str) -> dict[str, Any]:
    """Reparse full source bytes and annotate only strictly framed lines.

    Each three-line block consists of BEGIN, exactly one fully recognized math
    sentence, and matching END. All physically unframed lines stay unresolved.
    A context marker that is malformed/partial anywhere fails the entire run.
    """
    exact._sha(expected_source_sha256)
    require(type(raw) is bytes and _hash(raw) == expected_source_sha256,
            "EXTERNAL_SOURCE_PIN_MISMATCH")
    lines = literal._source_lines(raw)
    base = literal.scan_source(raw, expected_source_sha256=expected_source_sha256)
    by_span = {
        (x["source_span"]["start"], x["source_span"]["end"]): x
        for x in base["candidates"]
    }
    require(len(by_span) == len(base["candidates"]), "DUPLICATE_LITERAL_SPANS")

    active: dict[str, Any] | None = None
    blocks: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    matched_spans: set[tuple[int, int]] = set()

    for number, (start, end, text) in enumerate(lines, 1):
        # Recognize directives only as complete, standalone physical lines.
        # Even a malformed lookalike token is not silently ignored.
        begin = _BEGIN.fullmatch(text)
        finish = _END.fullmatch(text)
        if _MARKER in text and begin is None and finish is None:
            raise AttributionError("MALFORMED_CONTEXT_DIRECTIVE")
        if begin is not None:
            require(active is None, "NESTED_CONTEXT_DIRECTIVE")
            require(len(blocks) < MAX_BLOCKS, "CONTEXT_BLOCK_LIMIT")
            ident, role = begin.group(1).decode("ascii"), begin.group(2).decode("ascii")
            require(ident not in used_ids, "DUPLICATE_CONTEXT_ID")
            used_ids.add(ident)
            active = {
                "id": ident,
                "declared_role": role,
                "begin_span": _span(start, end),
                "begin_sha256": _hash(text),
                "begin_line": number,
                "candidate": None,
            }
            continue
        if finish is not None:
            require(active is not None, "UNMATCHED_CONTEXT_END")
            require(finish.group(1).decode("ascii") == active["id"],
                    "MISMATCHED_CONTEXT_ID")
            require(active["candidate"] is not None, "CONTEXT_WITHOUT_LITERAL")
            candidate = active.pop("candidate")
            role = active["declared_role"]
            blocks.append({
                "declaration_id": active["id"],
                "declared_role": role,
                "begin_marker_span": active["begin_span"],
                "begin_marker_sha256": active["begin_sha256"],
                "end_marker_span": _span(start, end),
                "end_marker_sha256": _hash(text),
                "literal_source_span": candidate["source_span"],
                "literal_sentence_sha256": candidate["sentence_sha256"],
                "literal_line_number": candidate["line_number"],
                # Reuse RW-MATH-03 unchanged: the same exact arithmetic proof.
                "math": candidate["math"],
                "model": candidate["model"],
                "interpretation": _interpret(role, candidate["math"]),
                "premises": "only_explicit_independent_closed_real_bounds_on_literal_line",
                "context_role_is_source_declaration_only": True,
                "author_intent_authenticated": False,
                "publisher_source_authenticated": False,
                "surrounding_prose_adjudicated": False,
                "paper_error_established": False,
            })
            active = None
            continue
        if active is not None:
            require(active["candidate"] is None,
                    "MORE_THAN_ONE_LINE_IN_CONTEXT_BLOCK")
            candidate = by_span.get((start, end))
            require(candidate is not None, "UNSUPPORTED_OR_UNSAFE_CONTEXT_LITERAL")
            require(candidate["sentence_sha256"] == _hash(text),
                    "LITERAL_BYTES_CHANGED")
            require((start, end) not in matched_spans, "DUPLICATE_LITERAL_CONTEXT")
            matched_spans.add((start, end))
            active["candidate"] = candidate

    require(active is None, "UNCLOSED_CONTEXT_BLOCK")
    unattributed = [
        {"line_number": x["line_number"],
         "source_span": x["source_span"],
         "sentence_sha256": x["sentence_sha256"]}
        for x in base["candidates"]
        if (x["source_span"]["start"], x["source_span"]["end"]) not in matched_spans
    ]
    result = {
        "schema_version": SCHEMA,
        "declaration_profile": PROFILE,
        "source_sha256": expected_source_sha256,
        "source_byte_length": len(raw),
        "source_line_count": len(lines),
        "context_block_count": len(blocks),
        "unattributed_literal_count": len(unattributed),
        "unattributed_literal_spans": unattributed,
        "context_blocks": blocks,
        "all_declared_contexts_structurally_checked": True,
        "unstated_premises_in_other_prose_examined": False,
        "natural_language_author_attribution_verified": False,
        "whole_paper_meaning_verified": False,
        "publisher_identity_verified": False,
        "paper_error_established": False,
        "scientific_accuracy_established": False,
        "external_actions": "NONE",
    }
    require(len(exact.canonical_bytes(result)) <= MAX_REPORT_BYTES, "REPORT_BYTE_LIMIT")
    return result


def replay_report(source: bytes, report: bytes, *, expected_source_sha256: str,
                  expected_report_sha256: str) -> dict[str, Any]:
    """Regenerate every context/math field; embedded status fields are inert."""
    exact._sha(expected_report_sha256)
    require(type(report) is bytes and len(report) <= MAX_REPORT_BYTES,
            "REPORT_BYTE_LIMIT")
    require(_hash(report) == expected_report_sha256, "EXTERNAL_REPORT_PIN_MISMATCH")
    exact.parse_json(report, MAX_REPORT_BYTES)
    regenerated = attribute_source(source, expected_source_sha256=expected_source_sha256)
    require(report == exact.canonical_bytes(regenerated), "REPORT_REPLAY_MISMATCH")
    return regenerated


def _read(path: Path, limit: int) -> bytes:
    with exact._open_regular(path, limit) as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, "INPUT_BYTE_LIMIT")
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
        source = _read(args.source, MAX_SOURCE_BYTES)
        if args.action == "scan":
            result = attribute_source(source, expected_source_sha256=args.expected_source_sha256)
            encoded = exact.canonical_bytes(result)
            if args.output is None:
                sys.stdout.buffer.write(encoded)
            else:
                require(args.source.resolve() != args.output.resolve(), "OUTPUT_OVERWRITES_SOURCE")
                with args.output.open("xb") as handle:
                    handle.write(encoded)
                print(json.dumps({
                    "status": "source_declared_context_report_saved",
                    "source_sha256": result["source_sha256"],
                    "report_sha256": _hash(encoded),
                    "context_block_count": len(result["context_blocks"]),
                    "author_attribution_verified": False,
                }, sort_keys=True))
        else:
            report = _read(args.report, MAX_REPORT_BYTES)
            result = replay_report(source, report,
                                   expected_source_sha256=args.expected_source_sha256,
                                   expected_report_sha256=args.expected_report_sha256)
            print(json.dumps({
                "status": "source_declared_context_replayed",
                "report_sha256": _hash(report),
                "context_block_count": len(result["context_blocks"]),
                "author_attribution_verified": False,
            }, sort_keys=True))
    except (AttributionError, exact.CertificateError, literal.UnsupportedSentence,
            ValueError, TypeError, UnicodeError, OSError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, (AttributionError, exact.CertificateError)) else type(exc).__name__
        print(json.dumps({"status": "rejected", "error": code}, sort_keys=True), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
