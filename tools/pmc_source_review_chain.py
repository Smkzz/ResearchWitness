"""Replay a private PMC raw-response -> JATS -> capture -> review chain.

Offline and development-exposed. Neither provenance, licence, scientific
interpretation nor reviewer independence is authenticated by this bridge.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from researchwitness import _jats_parser as jats
from tools import denominator_scope_review as scope
from tools import pmc_oai_envelope as pmc
from tools import source_capture_manifest as capture
from tools import source_review_binding as binding
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-pmc-development-source-review-chain.v1"


def require(ok: bool, code: str) -> None:
    vb.require(ok, code)


def bind_chain(
    raw: bytes, transfer: dict[str, Any],
    source: bytes, derivation_envelope: dict[str, Any],
    metadata: dict[str, Any], capture_envelope: dict[str, Any],
    packet_envelope: dict[str, Any], *,
    expected_derivation_sha256: str,
    expected_capture_sha256: str,
    expected_packet_sha256: str,
    review_a: dict[str, Any] | None = None,
    review_b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate every stage against exact input bytes and external pins."""
    require((review_a is None) == (review_b is None),
            "BOTH_REVIEWS_REQUIRED_OR_OMITTED")
    derived = pmc.replay(
        raw, transfer, source, derivation_envelope,
        expected_receipt_sha256=expected_derivation_sha256,
    )
    capture.validate_metadata(metadata)
    require(metadata["origin"]["retrieval_route"] == "pmc_open_access"
            and metadata["origin"]["capture_uri"] == pmc.ENDPOINT,
            "PMC_CAPTURE_ROUTE_MISMATCH")
    require(metadata["origin"]["captured_at_utc"] == transfer["captured_at_utc"],
            "PMC_CAPTURE_TIME_DECLARATION_MISMATCH")
    require(metadata["rights"]["classification"] == "declared_open_license"
            and metadata["rights"]["license_id"] == transfer["declared_license_id"]
            and metadata["rights"]["evidence_uri"] == transfer["rights_evidence_uri"],
            "PMC_LICENSE_DECLARATIONS_MISMATCH")
    require(metadata["origin"]["expected_source_sha256"]
            == derived["derived_jats_sha256"],
            "PMC_DERIVED_SOURCE_HASH_MISMATCH")
    reviewed = binding.bind(
        source, metadata, capture_envelope, packet_envelope,
        expected_capture_sha256=expected_capture_sha256,
        expected_packet_sha256=expected_packet_sha256,
        review_a=review_a, review_b=review_b,
    )
    require(reviewed["source_sha256"] == derived["derived_jats_sha256"],
            "PMC_REVIEW_SOURCE_HASH_MISMATCH")
    require(reviewed["source_origin_authenticated"] is False
            and reviewed["scientific_scope_truth_established"] is False
            and reviewed["protected_evaluation_permitted"] is False,
            "UNSUPPORTED_REVIEW_AUTHORITY")
    return {
        "schema_version": VERSION,
        "classification": "DECLARED_DEVELOPMENT_CHAIN_ONLY",
        "raw_envelope_sha256": derived["raw_envelope_sha256"],
        "derived_jats_sha256": derived["derived_jats_sha256"],
        "derivation_receipt_sha256": capture.digest(expected_derivation_sha256),
        "source_capture_manifest_sha256": reviewed["capture_manifest_sha256"],
        "review_packet_sha256": reviewed["review_packet_sha256"],
        "record_id_declared": reviewed["record_id"],
        "work_family_id_declared": reviewed["work_family_id_declared"],
        "version_id_declared": reviewed["version_id_declared"],
        "relation_count": reviewed["relation_count"],
        "review_status": reviewed["review_status"],
        "review_reconciliation_sha256": reviewed["review_reconciliation_sha256"],
        "review_reconciliation_status_counts": reviewed["review_reconciliation_status_counts"],
        "operator_retrieval_verified": False,
        "publisher_authenticity_verified": False,
        "license_rights_verified_by_tool": False,
        "family_independence_authenticated": False,
        "reviewer_independence_authenticated": False,
        "scientific_scope_truth_established": False,
        "protected_evaluation_permitted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-envelope", required=True, type=Path)
    parser.add_argument("--transfer", required=True, type=Path)
    parser.add_argument("--derived-source", required=True, type=Path)
    parser.add_argument("--derivation-envelope", required=True, type=Path)
    parser.add_argument("--expected-derivation-sha256", required=True)
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
        raw = read_regular(args.raw_envelope, pmc.MAX_ENVELOPE_BYTES)
        transfer = vb.parse_document(read_regular(args.transfer, pmc.MAX_TRANSFER_BYTES))
        source = read_regular(args.derived_source, jats.MAX_SOURCE_BYTES)
        derivation = vb.parse_document(read_regular(args.derivation_envelope,
                                                  pmc.MAX_RECEIPT_BYTES))
        metadata = vb.parse_document(read_regular(args.metadata,
                                               capture.MAX_METADATA_BYTES))
        captured = vb.parse_document(read_regular(args.capture_envelope,
                                               capture.MAX_MANIFEST_BYTES))
        packet = vb.parse_document(read_regular(args.packet_envelope,
                                             scope.MAX_PACKET_BYTES))
        left = (vb.parse_document(read_regular(args.review_a, scope.MAX_REVIEW_BYTES))
                if args.review_a else None)
        right = (vb.parse_document(read_regular(args.review_b, scope.MAX_REVIEW_BYTES))
                 if args.review_b else None)
        result = bind_chain(
            raw, transfer, source, derivation, metadata, captured, packet,
            expected_derivation_sha256=args.expected_derivation_sha256,
            expected_capture_sha256=args.expected_capture_sha256,
            expected_packet_sha256=args.expected_packet_sha256,
            review_a=left, review_b=right,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
