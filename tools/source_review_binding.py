"""Bind a private JATS reviewer packet to one exact development source capture.

This is deterministic identity accounting, not publisher/license authentication,
scientific adjudication or access to protected evaluation material.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import sys
from typing import Any

from researchwitness import _jats_parser as jats
from tools import denominator_scope_review as scope
from tools import source_capture_manifest as capture
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-development-source-review-binding.v1"


def require(condition: bool, code: str) -> None:
    vb.require(condition, code)


def bind(source: bytes, metadata: dict[str, Any],
         capture_envelope: dict[str, Any], packet_envelope: dict[str, Any],
         *, expected_capture_sha256: str,
         expected_packet_sha256: str,
         review_a: dict[str, Any] | None = None,
         review_b: dict[str, Any] | None = None) -> dict[str, Any]:
    """Replay source capture and reviewer packet from exactly the same bytes."""
    require((review_a is None) == (review_b is None),
            "BOTH_REVIEWS_REQUIRED_OR_OMITTED")
    reviewed = capture.replay_capture(
        source, metadata, capture_envelope,
        expected_manifest_sha256=expected_capture_sha256,
    )
    scope.exact_dict(packet_envelope, "packet packet_sha256",
                     "PACKET_ENVELOPE_FIELDS")
    require(packet_envelope["packet_sha256"] == scope.as_sha(expected_packet_sha256),
            "PACKET_ENVELOPE_PIN")
    packet = packet_envelope["packet"]
    scope.validate_packet(source, packet, expected_packet_sha256)
    actual_hash = sha256(source).hexdigest()
    require(actual_hash == reviewed["source_sha256"]
            and packet["source_sha256"] == actual_hash,
            "CROSS_WORKFLOW_SOURCE_VERSION_MISMATCH")
    record = metadata["record_id"]
    family = metadata["work_family_id"]
    version = metadata["version_id"]
    exposure = metadata["exposure"]
    require(exposure["partition"] == "development_exposed",
            "PROTECTED_PARTITION_NOT_ALLOWED")
    result: dict[str, Any] = {
        "schema_version": VERSION,
        "classification": "DEVELOPMENT_SOURCE_REVIEW_BINDING_NOT_INDEPENDENT_ADJUDICATION",
        "record_id": record,
        "work_family_id_declared": family,
        "version_id_declared": version,
        "source_sha256": actual_hash,
        "capture_manifest_sha256": scope.as_sha(expected_capture_sha256),
        "review_packet_sha256": scope.as_sha(expected_packet_sha256),
        "relation_count": len(packet["relations"]),
        "review_status": "REVIEWS_NOT_SUPPLIED",
        "review_reconciliation_sha256": None,
        "review_reconciliation_status_counts": None,
        "source_origin_authenticated": False,
        "rights_verified_by_tool": False,
        "family_independence_authenticated": False,
        "reviewer_independence_authenticated": False,
        "scientific_scope_truth_established": False,
        "protected_evaluation_permitted": False,
    }
    if review_a is not None and review_b is not None:
        reconciliation = scope.reconcile(
            source, packet, review_a, review_b,
            expected_source_sha256=actual_hash,
            expected_packet_sha256=expected_packet_sha256,
        )
        result["review_status"] = "DECLARATIONS_RECONCILED_NOT_ADJUDICATED"
        result["review_reconciliation_sha256"] = vb.commitment(reconciliation)
        result["review_reconciliation_status_counts"] = reconciliation["status_counts"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--capture-envelope", required=True, type=Path)
    parser.add_argument("--expected-capture-sha256", required=True)
    parser.add_argument("--packet-envelope", required=True, type=Path)
    parser.add_argument("--expected-packet-sha256", required=True)
    parser.add_argument("--review-a", type=Path)
    parser.add_argument("--review-b", type=Path)
    args = parser.parse_args(argv)
    try:
        require((args.review_a is None) == (args.review_b is None),
                "BOTH_REVIEWS_REQUIRED_OR_OMITTED")
        source = read_regular(args.source, jats.MAX_SOURCE_BYTES)
        metadata = vb.parse_document(read_regular(args.metadata, capture.MAX_METADATA_BYTES))
        captured = vb.parse_document(read_regular(args.capture_envelope,
                                                   capture.MAX_MANIFEST_BYTES))
        packet = vb.parse_document(read_regular(args.packet_envelope,
                                                 scope.MAX_PACKET_BYTES))
        left = vb.parse_document(read_regular(args.review_a, scope.MAX_REVIEW_BYTES)) if args.review_a else None
        right = vb.parse_document(read_regular(args.review_b, scope.MAX_REVIEW_BYTES)) if args.review_b else None
        outcome = bind(
            source, metadata, captured, packet,
            expected_capture_sha256=args.expected_capture_sha256,
            expected_packet_sha256=args.expected_packet_sha256,
            review_a=left, review_b=right,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(outcome))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
