"""Offline original PMC GetRecord -> derived JATS -> installed JATS audit/replay.

Checkout-only engineering adapter. It does not download articles or authenticate
source provenance, rights, source interpretation, reviewer independence or paper errors.
No original research text or case-specific numerical values are printed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import os
import stat
import sys
from typing import Any

from researchwitness import jats_product
from tools import pmc_oai_envelope as pmc
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-pmc-oai-jats-development-pilot.v1"
MAX_SUMMARY_BYTES = 32 * 1024


def require(condition: bool, code: str) -> None:
    vb.require(condition, code)


def _private_write(path: Path, content: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(content)
        out.flush()
        os.fsync(out.fileno())


def _plain_dir(path: Path) -> None:
    mode = path.lstat().st_mode
    require(stat.S_ISDIR(mode) and not path.is_symlink(), "UNSAFE_PARENT")


def _private_destination(output_dir: Path) -> None:
    """Refuse original-response output inside source and version-control trees.

    This guards against an accidental public commit of original article bytes.
    It is not a proof of destination privacy, safe synchronization or rights.
    The source is still expected to be kept outside the public checkout.
    """
    parent = output_dir.parent.resolve(strict=True)
    checkout = Path(__file__).resolve().parents[1]
    require(parent != checkout and checkout not in parent.parents,
            "OUTPUT_IN_SOURCE_CHECKOUT")
    for ancestor in (parent, *parent.parents):
        if any((ancestor / marker).exists() or (ancestor / marker).is_symlink()
               for marker in (".git", ".hg", ".svn")):
            raise vb.BenchmarkError("OUTPUT_IN_VERSION_CONTROL_TREE")


def run(raw_file: Path, transfer_file: Path, output_dir: Path, *,
        expected_raw_sha256: str, document_id: str,
        include_denominator_trace: bool = False,
        include_structure: bool = False) -> dict[str, Any]:
    """Return only after complete original/derived/audit/replay verification.

    An expected SHA provided at call time is a byte pin, not independent pre-
    capture evidence. Never call it publisher authenticity or research validity.
    """
    require(type(expected_raw_sha256) is str and
            jats_product.HASH.fullmatch(expected_raw_sha256) is not None,
            "EXPECTED_RAW_PIN_INVALID")
    require(type(document_id) is str and jats_product.IDENTIFIER.fullmatch(document_id)
            is not None and document_id.startswith("PMC") and document_id[3:].isdigit(),
            "DOCUMENT_ID_INVALID")
    require(type(include_denominator_trace) is bool and type(include_structure) is bool,
            "FEATURE_FLAGS_INVALID")
    raw = read_regular(Path(raw_file), pmc.MAX_ENVELOPE_BYTES)
    require(sha256(raw).hexdigest() == expected_raw_sha256,
            "EXTERNAL_RAW_PIN_MISMATCH")
    declaration_raw = read_regular(Path(transfer_file), pmc.MAX_TRANSFER_BYTES)
    transfer = vb.parse_document(declaration_raw)
    require(transfer.get("requested_identifier") ==
            "oai:pubmedcentral.nih.gov:" + document_id[3:],
            "DOCUMENT_ID_TRANSFER_MISMATCH")
    # Rebuild all source/model semantics from input bytes; no reported status is trusted.
    derived, derivation = pmc.derive(raw, transfer)
    require(sha256(derived).hexdigest() == derivation["derived_jats_sha256"],
            "DERIVED_SHA_MISMATCH")
    # Fail before opening output on malformed/unsupported JATS or output overflow.
    calculated = jats_product.make_report(
        derived, document_id, True, include_structure=include_structure,
        include_denominator_trace=include_denominator_trace,
    )
    report_bytes = jats_product.canonical_json(calculated)
    html_bytes = jats_product.render_html(calculated)
    require(len(report_bytes) <= jats_product.MAX_REPORT_BYTES and
            len(html_bytes) <= jats_product.MAX_REPORT_BYTES,
            "REPORT_SIZE_LIMIT")
    output_dir = Path(output_dir)
    _plain_dir(output_dir.parent)
    _private_destination(output_dir)
    require(not output_dir.exists() and not output_dir.is_symlink(),
            "OUTPUT_MUST_BE_FRESH")
    # This directory is private, caller-chosen, and assumed quiescent. Source is
    # retained byte-for-byte, not normalized/reformatted. No remote copy occurs.
    output_dir.mkdir(mode=0o700, exist_ok=False)
    _private_write(output_dir / "original-oai-response.xml", raw)
    _private_write(output_dir / "transfer-declaration.json", declaration_raw)
    _private_write(output_dir / "derived-article.xml", derived)
    envelope = pmc.receipt_envelope(derivation)
    receipt_raw = vb.canonical_bytes(envelope)
    _private_write(output_dir / "derivation-receipt.json", receipt_raw)
    # Verify before emitting a final success receipt; corrupted locally pinned
    # data must fail, even if the failure leaves an incomplete private folder.
    pmc.replay(raw, transfer, derived, envelope,
               expected_receipt_sha256=envelope["receipt_sha256"])
    bundle = jats_product.audit_source(
        output_dir / "derived-article.xml", output_dir / "jats-audit", document_id,
        derivation["derived_jats_sha256"],
        include_structure=include_structure,
        include_denominator_trace=include_denominator_trace,
    )
    verified = jats_product.replay_bundle(
        output_dir / "jats-audit", bundle["manifest_sha256"])
    require(verified["status"] == "verified" and
            verified["manifest_sha256"] == bundle["manifest_sha256"],
            "JATS_REPLAY_FAILED")
    require(bundle["document_id"] == document_id and
            bundle["summary"] == calculated["summary"],
            "AUDIT_RECOMPUTATION_MISMATCH")
    result = {
        "schema_version": VERSION,
        "status": "OFFLINE_SOURCE_DERIVED_AND_JATS_REPLAYED",
        "document_id": document_id,
        "raw_envelope_sha256": sha256(raw).hexdigest(),
        "raw_envelope_bytes": len(raw),
        "raw_pin_matched_supplied_value": True,
        "raw_pin_independent_of_run": "NOT_AUTHENTICATED_BY_THIS_TOOL",
        "transfer_declaration_sha256": sha256(declaration_raw).hexdigest(),
        "derived_jats_sha256": derivation["derived_jats_sha256"],
        "derived_jats_bytes": len(derived),
        "original_article_span": derivation["original_article_span"],
        "derivation_receipt_sha256": envelope["receipt_sha256"],
        "jats_audit_manifest_sha256": bundle["manifest_sha256"],
        "source_linked_results": calculated["summary"],
        "tables_inspected": calculated["processing"]["tables_inspected"],
        "relationships_detected": calculated["processing"]["relationships_detected"],
        "jats_replay_status": verified["status"],
        "analyzed_features": {
            "include_structure": include_structure,
            "include_denominator_trace": include_denominator_trace,
        },
        "source_origin_authenticated": False,
        "rights_independently_verified": False,
        "source_interpretation_independently_reviewed": False,
        "paper_error_established": False,
        "scientific_accuracy_established": False,
        "historical_2026_xml_snapshot_reproduced": False,
        "no_network_used": True,
        "external_actions": "OUT_OF_SCOPE",
        "limitations": [
            "The complete HTTP entity and declared HTTP status originate outside this tool.",
            "A matching supplied hash establishes byte continuity only, not publisher authenticity.",
            "Only the supplied OAI article's JATS was examined, not all paper claims.",
            "JATS arithmetic mismatches are unreviewed source-linked candidates.",
            "The source rights, correction context and scientific label require separate adjudication.",
            "Current provider XML is not automatically the 2026 historic XML snapshot.",
        ],
    }
    encoded = vb.canonical_bytes(result)
    require(len(encoded) <= MAX_SUMMARY_BYTES, "SUMMARY_SIZE_LIMIT")
    _private_write(output_dir / "result.json", encoded)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-envelope", type=Path, required=True)
    parser.add_argument("--transfer", type=Path, required=True)
    parser.add_argument("--expected-raw-sha256", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--include-denominator-trace", action="store_true")
    parser.add_argument("--include-structure", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.raw_envelope, args.transfer, args.output_dir,
                     expected_raw_sha256=args.expected_raw_sha256,
                     document_id=args.document_id,
                     include_denominator_trace=args.include_denominator_trace,
                     include_structure=args.include_structure)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2
    sys.stdout.buffer.write(vb.canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
