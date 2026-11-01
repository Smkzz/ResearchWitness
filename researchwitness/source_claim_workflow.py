"""Offline source-anchored claim compiler and exact proof replay (development).

Only explicit, ASCII RW-MATH blocks in pinned local UTF-8 text are understood;
unmarked prose, PDF, inferred scientific assumptions and external AI verdicts
remain unsupported. No provider calls, networking, publication or contact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from researchwitness import exact_optimization as exact
from researchwitness import source_claims as source

MAX_HINT_BYTES = 16 * 1024
MAX_CANDIDATE_BYTES = 32 * 1024
MAX_POINT_BYTES = 64 * 1024


def _read(path: Path, maximum: int) -> bytes:
    with exact._open_regular(path, maximum) as stream:
        contents = stream.read(maximum + 1)
    source.require(len(contents) <= maximum, "INPUT_BYTE_LIMIT")
    return contents


def _digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _read_hints(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.hints is None:
        source.require(args.expected_hints_sha256 is None, "HINTS_PIN_WITHOUT_FILE")
        return None
    source.require(args.expected_hints_sha256 is not None, "HINTS_EXTERNAL_PIN_REQUIRED")
    exact._sha(args.expected_hints_sha256)
    raw = _read(args.hints, MAX_HINT_BYTES)
    source.require(_digest(raw) == args.expected_hints_sha256,
                   "EXTERNAL_HINTS_PIN_MISMATCH")
    return exact.parse_json(raw, MAX_HINT_BYTES)


def compile_from_paths(args: argparse.Namespace) -> dict[str, Any]:
    hints = _read_hints(args)
    raw = _read(args.source, source.MAX_SOURCE_BYTES)
    candidate, model = source.compile_candidate(
        raw, block_index=args.block_index,
        expected_source_sha256=args.expected_source_sha256, hints=hints)
    model_bytes = exact.canonical_bytes(model)
    candidate_bytes = exact.canonical_bytes(candidate)
    source.require(len(candidate_bytes) <= MAX_CANDIDATE_BYTES and
                   len(model_bytes) <= exact.MAX_MODEL_BYTES, "OUTPUT_LIMIT")
    source.require(args.output_model != args.output_candidate, "SAME_OUTPUT_PATH")
    # Do not rewrite existing files, even for the same bytes. Input/output are
    # operator-selected paths in a quiescent trusted work directory, not source paths.
    source.require(not args.output_model.exists() and not args.output_candidate.exists(),
                   "OUTPUT_ALREADY_EXISTS")
    created: list[Path] = []
    try:
        for dest, contents in ((args.output_model, model_bytes),
                               (args.output_candidate, candidate_bytes)):
            with dest.open("xb") as stream:
                created.append(dest)
                stream.write(contents)
    except BaseException:
        # Clean only outputs newly created by this operation.
        for dest in created:
            dest.unlink(missing_ok=True)
        raise
    return {
        "status": "source_bound_model_candidate_only",
        "source_sha256": candidate["source_sha256"],
        "source_byte_span": candidate["source_span"],
        "selected_block": candidate["selected_block_index"],
        "explicit_blocks": candidate["explicit_block_count"],
        "model_sha256": _digest(model_bytes),
        "candidate_sha256": _digest(candidate_bytes),
        "claimed_upper": candidate["claimed_upper"],
        "source_origin_authenticated": False,
        "scientific_verdict": "not_established",
        "mathematical_proof": "not_supplied",
    }


def verify_from_paths(args: argparse.Namespace) -> dict[str, Any]:
    hints = _read_hints(args)
    raw = _read(args.source, source.MAX_SOURCE_BYTES)
    cand_bytes = _read(args.candidate, MAX_CANDIDATE_BYTES)
    model_bytes = _read(args.model, exact.MAX_MODEL_BYTES)
    candidate, _model = source.recheck_candidate(
        raw, block_index=args.block_index,
        expected_source_sha256=args.expected_source_sha256,
        candidate_bytes=cand_bytes, model_bytes=model_bytes,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_model_sha256=args.expected_model_sha256,
        hints=hints)
    math_report = exact.verify_paths(args.model, args.certificate,
                    expected_model_sha256=args.expected_model_sha256,
                    expected_certificate_sha256=args.expected_certificate_sha256)
    # A certified different upper bound is not a verification of the specific
    # claimed source threshold. Reject a too-loose substituted certificate.
    source.require(math_report["claimed_upper"] == candidate["claimed_upper"],
                   "CERTIFICATE_SOURCE_BOUND_MISMATCH")
    return {
        "status": "candidate_formalization_and_math_bound_replayed",
        "source_sha256": candidate["source_sha256"],
        "source_span": candidate["source_span"],
        "source_block_sha256": candidate["source_block_sha256"],
        "model_sha256": candidate["model_sha256"],
        "candidate_sha256": args.expected_candidate_sha256,
        "certificate_sha256": math_report["certificate_sha256"],
        "claimed_upper": candidate["claimed_upper"],
        "mathematical_model_upper_bound": math_report["verified_upper"],
        "mathematical_model_status": math_report["status"],
        "all_leaf_math_and_coverage_checked": math_report["partition_complete"],
        "source_span_rederived_exactly": True,
        "source_origin_authenticated": False,
        "unmarked_context_interpreted": False,
        "scientific_claim_correctness_established": False,
        "paper_error_established": False,
        "external_actions": "NONE",
    }


def refute_from_paths(args: argparse.Namespace) -> dict[str, Any]:
    """A checked exact feasible point can disprove a *formal* upper claim."""
    hints = _read_hints(args)
    raw = _read(args.source, source.MAX_SOURCE_BYTES)
    cand_bytes = _read(args.candidate, MAX_CANDIDATE_BYTES)
    model_bytes = _read(args.model, exact.MAX_MODEL_BYTES)
    candidate, model_doc = source.recheck_candidate(
        raw, block_index=args.block_index,
        expected_source_sha256=args.expected_source_sha256,
        candidate_bytes=cand_bytes, model_bytes=model_bytes,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_model_sha256=args.expected_model_sha256,
        hints=hints)
    exact._sha(args.expected_point_sha256)
    point_bytes = _read(args.point, MAX_POINT_BYTES)
    source.require(_digest(point_bytes) == args.expected_point_sha256,
                   "EXTERNAL_POINT_PIN_MISMATCH")
    point_values = exact.parse_json(point_bytes, MAX_POINT_BYTES)
    source.require(type(point_values) is list and
                   point_bytes == exact.canonical_bytes(point_values),
                   "POINT_NOT_CANONICAL_ARRAY")
    objective = exact.verify_point(exact.compile_model(model_doc), point_values)
    claimed = exact.rational(candidate["claimed_upper"])
    source.require(objective > claimed, "POINT_DOES_NOT_REFUTE_CLAIM")
    return {
        "status": "formal_model_upper_refuted_by_exact_point",
        "source_sha256": candidate["source_sha256"],
        "source_span": candidate["source_span"],
        "source_block_sha256": candidate["source_block_sha256"],
        "model_sha256": candidate["model_sha256"],
        "candidate_sha256": args.expected_candidate_sha256,
        "point_sha256": args.expected_point_sha256,
        "claimed_upper": candidate["claimed_upper"],
        "verified_feasible_point_value": str(objective),
        "strict_violation_margin": str(objective - claimed),
        "source_span_rederived_exactly": True,
        "source_origin_authenticated": False,
        "unmarked_context_interpreted": False,
        "paper_error_established": False,
        "scientific_claim_correctness_established": False,
        "external_actions": "NONE",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_subparsers(dest="mode", required=True)
    for command in ("compile", "verify", "refute"):
        p = mode.add_parser(command)
        p.add_argument("--source", required=True, type=Path)
        p.add_argument("--expected-source-sha256", required=True)
        p.add_argument("--block-index", type=int, default=0)
        p.add_argument("--hints", type=Path)
        p.add_argument("--expected-hints-sha256")
        p.add_argument("--model", type=Path, required=command != "compile")
        if command == "compile":
            p.add_argument("--output-model", required=True, type=Path)
            p.add_argument("--output-candidate", required=True, type=Path)
        else:
            p.add_argument("--candidate", required=True, type=Path)
            p.add_argument("--expected-model-sha256", required=True)
            p.add_argument("--expected-candidate-sha256", required=True)
            if command == "verify":
                p.add_argument("--certificate", required=True, type=Path)
                p.add_argument("--expected-certificate-sha256", required=True)
            else:
                p.add_argument("--point", required=True, type=Path)
                p.add_argument("--expected-point-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = (compile_from_paths(args) if args.mode == "compile"
                  else verify_from_paths(args) if args.mode == "verify"
                  else refute_from_paths(args))
    except (source.UnsupportedClaim, exact.CertificateError, OSError,
            ValueError, TypeError, RecursionError) as exc:
        # Do not echo private source text, input paths or raw exception payloads.
        code = str(exc) if isinstance(exc, (source.UnsupportedClaim, exact.CertificateError)) else type(exc).__name__
        print(json.dumps({"status": "rejected_or_unsupported", "reason": code},
                         sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
