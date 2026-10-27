"""Private, offline evidence accounting for the 2–5-family PMC development pilot.

Not an acquisition tool, rights assessment, external timestamp, independent
adjudication or sealed evaluation. It replays each supplied original-byte chain,
refuses forged success statuses and counts ALL selected families/attempts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
from typing import Any

from researchwitness import _jats_parser as jats
from tools import denominator_scope_review as scope
from tools import pmc_oai_envelope as pmc
from tools import pmc_source_review_chain as chain
from tools import pmc_pilot_selection_frame as selection
from tools import source_capture_manifest as capture
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-private-pmc-development-pilot.v1"
REPORT_VERSION = "rw-private-pmc-development-pilot-report.v1"
MAX_LEDGER_BYTES = 64 * 1024
MAX_RECORDS = 12
MAX_DISTINCT_FAMILIES = 5
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z", re.ASCII)
OUTCOMES = frozenset({
    "acquisition_unavailable", "rights_excluded", "parser_refused",
    "captured_pending_review", "development_reviews_submitted", "not_attempted",
})
REASONS = {
    "acquisition_unavailable": frozenset({
        "provider_unavailable", "not_found", "transport_failed", "timeout",
    }),
    "rights_excluded": frozenset({
        "rights_unknown", "rights_restricted", "rights_not_redistributable",
    }),
    "parser_refused": frozenset({
        "ENVELOPE_DTD_OR_ENTITY", "ENVELOPE_MALFORMED_XML",
        "ENVELOPE_BYTE_LIMIT", "ENVELOPE_XINCLUDE_FORBIDDEN",
        "OAI_ARTICLE_COUNT", "ARTICLE_KIND_UNSUPPORTED",
        "ARTICLE_LICENSE_UNCLEAR", "DERIVED_JATS_NOT_SUPPORTED",
        "INVALID_INPUT_OR_IO",
    }),
}
CAPTURE_FILES = (
    "raw_envelope", "transfer", "derived_source", "derivation_envelope",
    "metadata", "capture_envelope", "packet_envelope", "review_a", "review_b",
)
PIN_NAMES = (
    "expected_derivation_sha256", "expected_capture_sha256",
    "expected_packet_sha256",
)


def require(ok: bool, diagnostic: str) -> None:
    vb.require(ok, diagnostic)


def fields(item: Any, required: set[str], diagnostic: str) -> dict[str, Any]:
    require(type(item) is dict and set(item) == required, diagnostic)
    return item


def filename(name: Any) -> str:
    require(type(name) is str and NAME.fullmatch(name) is not None
            and name not in {".", ".."} and ".." not in name
            and not name.endswith("."), "PILOT_PRIVATE_FILENAME")
    require(name.partition(".")[0].casefold() not in {
        "con", "prn", "aux", "nul", "com1", "lpt1",
    }, "PILOT_PRIVATE_FILENAME")
    return name


def _private_root(root: Path) -> Path:
    require(root.is_dir() and not root.is_symlink(), "PILOT_PRIVATE_ROOT")
    return root


def _read(root: Path, name: Any, limit: int, used: set[str]) -> bytes:
    value = filename(name)
    require(value.casefold() not in used, "PILOT_PRIVATE_FILE_REUSED")
    used.add(value.casefold())
    return read_regular(root / value, limit)


def _document(root: Path, name: Any, limit: int, used: set[str]) -> dict[str, Any]:
    return vb.parse_document(_read(root, name, limit, used))


def evaluate(ledger: dict[str, Any], private_root: Path, *,
             expected_ledger_sha256: str,
             selection_frame: dict[str, Any] | None = None,
             expected_frame_sha256: str | None = None) -> dict[str, Any]:
    """Replay supplied private inputs and report only aggregate development states."""
    vb.parse_document(vb.canonical_bytes(ledger))
    require(vb.commitment(ledger) == capture.digest(expected_ledger_sha256),
            "PILOT_LEDGER_EXTERNAL_PIN_MISMATCH")
    fields(ledger, {"schema_version", "partition", "selection",
                    "records"}, "PILOT_LEDGER_FIELDS")
    require(ledger["schema_version"] == VERSION, "PILOT_LEDGER_VERSION")
    require(ledger["partition"] == "development_exposed",
            "PILOT_PROTECTED_PARTITION")
    require(ledger["selection"] == "operator_declared_not_time_authenticated",
            "PILOT_SELECTION_NOT_AUTHENTICATED")
    records = ledger["records"]
    require(type(records) is list and 2 <= len(records) <= MAX_RECORDS,
            "PILOT_RECORD_COUNT")
    require((selection_frame is None) == (expected_frame_sha256 is None),
            "PILOT_FRAME_ARGUMENTS")
    frame_index = (selection.validate(
        selection_frame, expected_frame_sha256=expected_frame_sha256,
    ) if selection_frame is not None else None)
    if frame_index is not None:
        require(all(type(row) is dict and type(row.get("record_id")) is str
                    for row in records), "PILOT_RECORD_FIELDS")
        require(len(records) == len(frame_index)
                and {row["record_id"] for row in records} == set(frame_index),
                "PILOT_FRAME_COVERAGE_MISMATCH")
    root = _private_root(private_root)

    keys: set[str] = set()
    families: set[str] = set()
    versions: set[tuple[str, str]] = set()
    used_paths: set[str] = set()
    source_hash_family: dict[str, str] = {}
    captured_envelopes: list[dict[str, Any]] = []
    outcomes: Counter[str] = Counter()
    refusals: Counter[str] = Counter()
    relation_count = 0
    for row in records:
        fields(row, {"record_id", "family_id", "version_id", "outcome",
                     "reason", "files", "pins"}, "PILOT_RECORD_FIELDS")
        rid, family, version = (
            capture.identifier(row[name])
            for name in ("record_id", "family_id", "version_id")
        )
        require(rid not in keys, "PILOT_DUPLICATE_RECORD")
        require((family, version) not in versions, "PILOT_DUPLICATE_VERSION")
        keys.add(rid)
        versions.add((family, version))
        families.add(family)
        frame_entry = frame_index[rid] if frame_index is not None else None
        if frame_entry is not None:
            require(family == frame_entry["family_id"]
                    and version == frame_entry["version_id"],
                    "PILOT_FRAME_DECLARED_IDENTITY_MISMATCH")
        outcome = row["outcome"]
        require(type(outcome) is str and outcome in OUTCOMES,
                "PILOT_OUTCOME_INVALID")
        reason = row["reason"]
        outcomes[outcome] += 1
        if outcome == "not_attempted":
            require(reason is None and row["files"] is None
                    and row["pins"] is None, "PILOT_NOT_ATTEMPTED_FIELDS")
            continue
        if outcome in {"acquisition_unavailable", "rights_excluded"}:
            require(reason in REASONS[outcome] and row["files"] is None
                    and row["pins"] is None, "PILOT_NEGATIVE_EVIDENCE_FIELDS")
            refusals[reason] += 1
            continue

        if outcome == "parser_refused":
            require(reason in REASONS[outcome] and row["pins"] is None,
                    "PILOT_PARSER_REFUSAL_FIELDS")
            f = fields(row["files"], {"raw_envelope", "transfer"},
                       "PILOT_PARSER_FILE_FIELDS")
            raw = _read(root, f["raw_envelope"], pmc.MAX_ENVELOPE_BYTES, used_paths)
            transfer = _document(root, f["transfer"], pmc.MAX_TRANSFER_BYTES,
                                 used_paths)
            if frame_entry is not None:
                require(transfer.get("requested_identifier") ==
                        frame_entry["oai_identifier"],
                        "PILOT_FRAME_OAI_IDENTITY_MISMATCH")
            try:
                pmc.derive(raw, transfer)
            except (ValueError, TypeError, RecursionError) as exc:
                actual = (str(exc) if isinstance(exc, vb.BenchmarkError)
                          else "INVALID_INPUT_OR_IO")
                require(actual == reason, "PILOT_PARSER_REFUSAL_MISMATCH")
            else:
                require(False, "PILOT_PARSER_SUCCESS_NOT_REFUSAL")
            refusals["parser_refused"] += 1
            continue

        require(reason is None, "PILOT_CAPTURE_UNEXPECTED_REASON")
        f = fields(row["files"], set(CAPTURE_FILES), "PILOT_CAPTURE_FILES")
        pins = fields(row["pins"], set(PIN_NAMES), "PILOT_CAPTURE_PINS")
        for name in PIN_NAMES:
            capture.digest(pins[name])
        reviews_exist = outcome == "development_reviews_submitted"
        require((f["review_a"] is not None) == (f["review_b"] is not None)
                and (f["review_a"] is not None) == reviews_exist,
                "PILOT_REVIEW_COMPLETENESS")
        raw = _read(root, f["raw_envelope"], pmc.MAX_ENVELOPE_BYTES, used_paths)
        transfer = _document(root, f["transfer"], pmc.MAX_TRANSFER_BYTES, used_paths)
        if frame_entry is not None:
            require(transfer.get("requested_identifier") ==
                    frame_entry["oai_identifier"],
                    "PILOT_FRAME_OAI_IDENTITY_MISMATCH")
        source = _read(root, f["derived_source"], jats.MAX_SOURCE_BYTES, used_paths)
        derivation = _document(root, f["derivation_envelope"],
                               pmc.MAX_RECEIPT_BYTES, used_paths)
        metadata = _document(root, f["metadata"], capture.MAX_METADATA_BYTES,
                             used_paths)
        captured = _document(root, f["capture_envelope"], capture.MAX_MANIFEST_BYTES,
                             used_paths)
        packet = _document(root, f["packet_envelope"], scope.MAX_PACKET_BYTES,
                           used_paths)
        left = (_document(root, f["review_a"], scope.MAX_REVIEW_BYTES, used_paths)
                if reviews_exist else None)
        right = (_document(root, f["review_b"], scope.MAX_REVIEW_BYTES, used_paths)
                 if reviews_exist else None)
        require(metadata["record_id"] == rid
                and metadata["work_family_id"] == family
                and metadata["version_id"] == version,
                "PILOT_DECLARED_IDENTITY_MISMATCH")
        if frame_entry is not None:
            require(metadata.get("kind") == frame_entry["kind"]
                    and metadata.get("parent_record_id") ==
                    frame_entry["parent_record_id"],
                    "PILOT_FRAME_SOURCE_LINEAGE_MISMATCH")
        outcome_report = chain.bind_chain(
            raw, transfer, source, derivation, metadata, captured, packet,
            **pins, review_a=left, review_b=right,
        )
        require((outcome_report["review_status"] ==
                 "DECLARATIONS_RECONCILED_NOT_ADJUDICATED") == reviews_exist,
                "PILOT_REVIEW_STATUS_MISMATCH")
        source_hash = outcome_report["derived_jats_sha256"]
        require(source_hash not in source_hash_family,
                "PILOT_REUSED_SOURCE_BYTES")
        source_hash_family[source_hash] = family
        relation_count += outcome_report["relation_count"]
        captured_envelopes.append(captured)

    require(2 <= len(families) <= MAX_DISTINCT_FAMILIES,
            "PILOT_DISTINCT_FAMILY_COUNT")
    registry_hash = None
    if captured_envelopes:
        registry = {
            "schema_version": capture.REGISTRY_INPUT_VERSION,
            "captures": captured_envelopes,
        }
        registry_hash = vb.commitment(registry)
        capture.validate_registry(registry,
                                  expected_registry_sha256=registry_hash)
    report = {
        "schema_version": REPORT_VERSION,
        "status": "DECLARED_DEVELOPMENT_PILOT_EVIDENCE_NOT_ADJUDICATED",
        "pilot_ledger_sha256": vb.commitment(ledger),
        "capture_registry_sha256": registry_hash,
        "selected_record_count": len(records),
        "distinct_declared_family_count": len(families),
        "raw_to_review_chains_replayed": len(captured_envelopes),
        "source_fact_relations_replayed": relation_count,
        "outcomes": {kind: outcomes.get(kind, 0) for kind in sorted(OUTCOMES)},
        "refusal_reasons": dict(sorted(refusals.items())),
        "unreviewed_captured_records": outcomes.get("captured_pending_review", 0),
        "review_declarations_submitted": outcomes.get("development_reviews_submitted", 0),
        "candidate_identifiers_or_source_text_emitted": False,
        "independent_retrieval_provenance_verified": False,
        "article_specific_rights_independently_verified": False,
        "independent_work_families_verified": False,
        "independent_scientific_labels_established": False,
        "protected_holdout_qualified": False,
        "scientific_detection_improvement_established": False,
        "limitations": [
            "All source origin, transport times, permissions and declared families are operator claims.",
            "A separately pinned input digest proves continuity but no pre-outcome selection date.",
            "Source chain replay proves exact supplied bytes, not acquisition authenticity.",
            "Developer reviewer records are declarations; two records do not prove independence.",
            "All negative outcomes are operator-declared and cannot be independently replayed.",
            "No original paper, private identifier or reviewer rationale is included in this report.",
            "Unframed v1 input cannot establish the preselected source population.",
        ],
    }
    if frame_index is not None:
        report.update({
            "schema_version": "rw-private-pmc-development-pilot-report.v2",
            "status": "DECLARED_FRAME_FULLY_ACCOUNTED_NOT_TIME_AUTHENTICATED",
            "selection_frame_sha256": vb.commitment(selection_frame),
            "selection_frame_coverage": "all_selected_record_ids_accounted",
            "selected_attempts_not_yet_run": outcomes.get("not_attempted", 0),
            "selected_attempts_with_declared_outcomes":
                len(records) - outcomes.get("not_attempted", 0),
            "source_identifiers_and_lineage_match_frame": True,
            "pre_outcome_frame_timing_authenticated": False,
        })
        report["limitations"] = [
            limitation for limitation in report["limitations"]
            if limitation !=
            "Unframed v1 input cannot establish the preselected source population."
        ] + [
            "A matching externally pinned frame is not independently timestamped.",
            "No proof exists that the frame preceded article or method outcome access.",
        ]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--expected-ledger-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        ledger = vb.parse_document(read_regular(args.ledger, MAX_LEDGER_BYTES))
        result = evaluate(
            ledger, args.private_root,
            expected_ledger_sha256=args.expected_ledger_sha256,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
