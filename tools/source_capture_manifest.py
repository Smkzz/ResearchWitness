"""Offline development-source capture and declared-version lineage, not authentication.

This tool NEVER downloads a paper or verifies an external license, publisher,
timestamp, research label or reviewer. Source XML stays in the caller's private
filesystem; printed manifests contain metadata and SHA-256, not paper text.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

from researchwitness import _jats_parser as jats
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

METADATA_VERSION = "rw-development-source-metadata.v1"
MANIFEST_VERSION = "rw-development-source-capture.v1"
REGISTRY_INPUT_VERSION = "rw-development-source-registry-input.v1"
REGISTRY_REPORT_VERSION = "rw-development-source-registry-report.v1"
MAX_METADATA_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 96 * 1024
MAX_REGISTRY_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 2048
KINDS = frozenset({"article", "revision", "correction", "supplement"})
ROUTES = frozenset({"publisher_open_access", "pmc_open_access",
                    "institutional_repository", "operator_supplied"})
RIGHTS = frozenset({"declared_open_license", "documented_permission",
                    "unknown", "restricted"})
PRIOR_EXPOSURE = frozenset({"known_exposed", "unknown", "declared_not_exposed"})
LICENSES = frozenset({"CC-BY-4.0", "CC0-1.0"})


def require(ok: bool, code: str) -> None:
    vb.require(ok, code)


def fields(value: Any, names: str, diagnostic: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == set(names.split()), diagnostic)
    return value


def identifier(value: Any) -> str:
    require(type(value) is str and vb.ID.fullmatch(value) is not None,
            "SOURCE_IDENTIFIER")
    return value


def digest(value: Any) -> str:
    require(type(value) is str and vb.HASH.fullmatch(value) is not None,
            "SOURCE_SHA256")
    return value


def https_uri(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    require(type(value) is str and 8 <= len(value) <= 512,
            "PROVENANCE_URI_INVALID")
    try:
        parts = urlsplit(value)
        valid = (parts.scheme == "https" and bool(parts.hostname)
                 and parts.username is None and parts.password is None
                 and parts.query == "" and parts.fragment == ""
                 and parts.path != "//" and not any(ord(c) < 33 for c in value)
                 and value == parts.geturl())
    except ValueError:
        valid = False
    require(valid, "PROVENANCE_URI_INVALID")
    return value


def utc_timestamp(value: Any) -> str:
    require(type(value) is str and len(value) == 20 and value.endswith("Z"),
            "CAPTURE_TIMESTAMP_NOT_UTC")
    try:
        stamp = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise vb.BenchmarkError("CAPTURE_TIMESTAMP_INVALID") from exc
    require(stamp.strftime("%Y-%m-%dT%H:%M:%SZ") == value,
            "CAPTURE_TIMESTAMP_INVALID")
    return value


def validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    fields(metadata, "schema_version record_id work_family_id version_id kind "
                     "parent_record_id correction_notice_uri origin rights exposure",
           "SOURCE_METADATA_FIELDS")
    require(metadata["schema_version"] == METADATA_VERSION, "SOURCE_SCHEMA")
    identifier(metadata["record_id"])
    identifier(metadata["work_family_id"])
    identifier(metadata["version_id"])
    kind = metadata["kind"]
    require(type(kind) is str and kind in KINDS, "SOURCE_KIND")
    parent = metadata["parent_record_id"]
    if kind == "article":
        require(parent is None, "SOURCE_INITIAL_HAS_PARENT")
    else:
        identifier(parent)
        require(parent != metadata["record_id"], "SOURCE_SELF_PARENT")
    correction_uri = https_uri(metadata["correction_notice_uri"], nullable=True)
    require(kind != "correction" or correction_uri is not None,
            "CORRECTION_NOTICE_REQUIRED")
    if kind != "correction":
        require(correction_uri is None, "UNEXPECTED_CORRECTION_NOTICE")
    origin = fields(metadata["origin"],
                    "retrieval_route capture_uri publisher_uri captured_at_utc expected_source_sha256",
                    "SOURCE_ORIGIN_FIELDS")
    require(type(origin["retrieval_route"]) is str
            and origin["retrieval_route"] in ROUTES, "RETRIEVAL_ROUTE")
    https_uri(origin["publisher_uri"], nullable=True)
    capture_uri = https_uri(origin["capture_uri"], nullable=True)
    if origin["retrieval_route"] != "operator_supplied":
        require(capture_uri is not None, "RETRIEVAL_URI_REQUIRED")
    utc_timestamp(origin["captured_at_utc"])
    digest(origin["expected_source_sha256"])
    rights = fields(metadata["rights"], "classification license_id evidence_uri",
                    "RIGHTS_FIELDS")
    require(type(rights["classification"]) is str
            and rights["classification"] in RIGHTS, "RIGHTS_CLASSIFICATION")
    evidence = https_uri(rights["evidence_uri"], nullable=True)
    licence = rights["license_id"]
    if rights["classification"] == "declared_open_license":
        require(type(licence) is str and licence in LICENSES and evidence is not None,
                "DECLARED_OPEN_LICENSE_EVIDENCE_REQUIRED")
    elif rights["classification"] == "documented_permission":
        require(licence is None and evidence is not None,
                "PERMISSION_EVIDENCE_REQUIRED")
    else:
        require(licence is None and evidence is None, "UNVERIFIED_RIGHTS_CANNOT_CLAIM_LICENSE")
    exposure = fields(metadata["exposure"], "partition prior_access label_status",
                      "EXPOSURE_FIELDS")
    require(exposure["partition"] == "development_exposed", "PROTECTED_PARTITION_FORBIDDEN")
    require(type(exposure["prior_access"]) is str
            and exposure["prior_access"] in PRIOR_EXPOSURE, "EXPOSURE_HISTORY")
    require(exposure["label_status"] == "no_independent_scientific_label",
            "UNSUPPORTED_SCIENTIFIC_LABEL")
    return metadata


def _manifest_structure(manifest: dict[str, Any]) -> dict[str, Any]:
    fields(manifest, "schema_version metadata source_sha256 source_bytes "
                     "parser_profile source_xml_root classification "
                     "publication_authenticity_verified rights_verified_by_tool "
                     "captured_at_authenticity_verified scientific_label_established "
                     "protected_evaluation_permitted", "MANIFEST_FIELDS")
    require(manifest["schema_version"] == MANIFEST_VERSION, "MANIFEST_VERSION")
    metadata = validate_metadata(manifest["metadata"])
    require(digest(manifest["source_sha256"])
            == metadata["origin"]["expected_source_sha256"],
            "SOURCE_HASH_METADATA_MISMATCH")
    require(type(manifest["source_bytes"]) is int
            and 0 < manifest["source_bytes"] <= jats.MAX_SOURCE_BYTES,
            "SOURCE_LENGTH_INVALID")
    require(manifest["parser_profile"] == "current_bounded_original_byte_jats",
            "PARSER_PROFILE")
    require(manifest["source_xml_root"] == "article", "SOURCE_ROOT_NOT_ARTICLE")
    require(manifest["classification"] == "DEVELOPMENT_CAPTURE_DECLARATION_ONLY",
            "CAPTURE_CLASSIFICATION")
    for name in ("publication_authenticity_verified", "rights_verified_by_tool",
                 "captured_at_authenticity_verified", "scientific_label_established",
                 "protected_evaluation_permitted"):
        require(manifest[name] is False, "FALSE_AUTHORITY_CLAIM")
    return metadata


def build_capture(source: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
    require(type(source) is bytes and 0 < len(source) <= jats.MAX_SOURCE_BYTES,
            "SOURCE_BYTE_LIMIT")
    validate_metadata(metadata)
    hash_value = sha256(source).hexdigest()
    require(hash_value == metadata["origin"]["expected_source_sha256"],
            "SOURCE_HASH_MISMATCH")
    root = jats._parse_jats(source)
    require(jats._local_name(root.tag) == "article", "SOURCE_ROOT_NOT_ARTICLE")
    result = {
        "schema_version": MANIFEST_VERSION,
        "metadata": metadata,
        "source_sha256": hash_value,
        "source_bytes": len(source),
        "parser_profile": "current_bounded_original_byte_jats",
        "source_xml_root": "article",
        "classification": "DEVELOPMENT_CAPTURE_DECLARATION_ONLY",
        "publication_authenticity_verified": False,
        "rights_verified_by_tool": False,
        "captured_at_authenticity_verified": False,
        "scientific_label_established": False,
        "protected_evaluation_permitted": False,
    }
    _manifest_structure(result)
    require(len(vb.canonical_bytes(result)) <= MAX_MANIFEST_BYTES,
            "MANIFEST_OUTPUT_BYTE_LIMIT")
    return result


def envelope(manifest: dict[str, Any]) -> dict[str, Any]:
    return {"manifest": manifest, "manifest_sha256": vb.commitment(manifest)}


def _valid_envelope(value: dict[str, Any]) -> dict[str, Any]:
    fields(value, "manifest manifest_sha256", "CAPTURE_ENVELOPE_FIELDS")
    require(digest(value["manifest_sha256"]) == vb.commitment(value["manifest"]),
            "CAPTURE_ENVELOPE_HASH_MISMATCH")
    _manifest_structure(value["manifest"])
    return value


def replay_capture(source: bytes, metadata: dict[str, Any],
                   capture_envelope: dict[str, Any],
                   *, expected_manifest_sha256: str) -> dict[str, Any]:
    _valid_envelope(capture_envelope)
    require(digest(expected_manifest_sha256) == vb.commitment(capture_envelope["manifest"]),
            "EXTERNAL_MANIFEST_PIN_MISMATCH")
    actual = build_capture(source, metadata)
    require(actual == capture_envelope["manifest"],
            "SOURCE_CAPTURE_REPLAY_MISMATCH")
    return {
        "status": "SOURCE_BYTES_AND_DECLARED_METADATA_REPLAYED",
        "manifest_sha256": expected_manifest_sha256,
        "source_sha256": actual["source_sha256"],
        "source_record_id": metadata["record_id"],
        "source_origin_authenticated": False,
        "rights_verified_by_tool": False,
        "eligible_for_protected_evaluation": False,
    }


def validate_registry(registry: dict[str, Any], *,
                      expected_registry_sha256: str) -> dict[str, Any]:
    require(vb.commitment(registry) == digest(expected_registry_sha256),
            "REGISTRY_INPUT_PIN_MISMATCH")
    fields(registry, "schema_version captures", "REGISTRY_FIELDS")
    require(registry["schema_version"] == REGISTRY_INPUT_VERSION,
            "REGISTRY_INPUT_VERSION")
    captures = registry["captures"]
    require(type(captures) is list and 1 <= len(captures) <= MAX_RECORDS,
            "REGISTRY_RECORD_COUNT")
    indexed: dict[str, dict[str, Any]] = {}
    version_ids: set[tuple[str, str]] = set()
    by_hash: dict[str, str] = {}
    families: dict[str, list[str]] = defaultdict(list)
    rights: Counter[str] = Counter()
    for row in captures:
        entry = _valid_envelope(row)
        manifest = entry["manifest"]
        metadata = manifest["metadata"]
        record_id, family_id = metadata["record_id"], metadata["work_family_id"]
        require(record_id not in indexed, "DUPLICATE_SOURCE_RECORD")
        version_key = (family_id, metadata["version_id"])
        require(version_key not in version_ids, "DUPLICATE_WORK_FAMILY_VERSION")
        version_ids.add(version_key)
        raw_hash = manifest["source_sha256"]
        if raw_hash in by_hash:
            require(by_hash[raw_hash] == family_id,
                    "SAME_SOURCE_BYTES_IN_DIFFERENT_FAMILIES")
            require(False, "SOURCE_BYTES_REUSED_AS_NEW_VERSION")
        by_hash[raw_hash] = family_id
        indexed[record_id] = metadata
        families[family_id].append(record_id)
        rights[metadata["rights"]["classification"]] += 1
    for record_id, metadata in indexed.items():
        parent = metadata["parent_record_id"]
        if parent is None:
            continue
        require(parent in indexed, "LINEAGE_PARENT_MISSING")
        prior = indexed[parent]
        require(prior["work_family_id"] == metadata["work_family_id"],
                "LINEAGE_PARENT_DIFFERENT_FAMILY")
        require(prior["record_id"] != record_id, "LINEAGE_SELF_REFERENCE")
        # These timestamps are operator declarations, not publisher-authenticated.
        require(prior["origin"]["captured_at_utc"]
                <= metadata["origin"]["captured_at_utc"],
                "LINEAGE_TIMESTAMP_ORDER")
    for record_id in indexed:
        seen = set()
        position: str | None = record_id
        while position is not None:
            require(position not in seen, "LINEAGE_CYCLE")
            seen.add(position)
            position = indexed[position]["parent_record_id"]
    output = {
        "schema_version": REGISTRY_REPORT_VERSION,
        "registry_input_sha256": expected_registry_sha256,
        "record_count": len(indexed),
        "declared_work_family_count": len(families),
        "distinct_source_byte_hash_count": len(by_hash),
        "families": [
            {"work_family_id": family, "record_ids": sorted(ids),
             "version_count": len(ids)}
            for family, ids in sorted(families.items())
        ],
        "rights_declarations": dict(sorted(rights.items())),
        "classification": "DECLARED_LINEAGE_NOT_SCIENTIFIC_INDEPENDENCE",
        "source_bytes_replayed_by_registry": False,
        "source_versions_publisher_authenticated": False,
        "license_rights_verified": False,
        "scientific_family_independence_established": False,
        "protected_holdout_qualified": False,
        "limitations": [
            "Only separately supplied capture-envelope hashes are checked; registry does not read XML.",
            "External registry pin is a value, not trusted timestamp, custodian signature or license.",
            "Same declared family may share source data with other families without detection.",
            "A declared publication version, correction or supplement is not publisher authenticated.",
            "All records are development-exposed and cannot become sealed holdout labels by registration.",
        ],
    }
    require(len(vb.canonical_bytes(output)) <= MAX_REGISTRY_BYTES,
            "REGISTRY_OUTPUT_BYTE_LIMIT")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("capture", "replay", "registry"),
                        required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--capture-envelope", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--expected-registry-sha256")
    args = parser.parse_args(argv)
    try:
        if args.action in {"capture", "replay"}:
            require(args.source is not None and args.metadata is not None
                    and args.registry is None and args.expected_registry_sha256 is None,
                    "CAPTURE_INPUTS")
            source = read_regular(args.source, jats.MAX_SOURCE_BYTES)
            metadata = vb.parse_document(read_regular(args.metadata, MAX_METADATA_BYTES))
            if args.action == "capture":
                require(args.capture_envelope is None
                        and args.expected_manifest_sha256 is None,
                        "CAPTURE_EXTRA_INPUTS")
                result = envelope(build_capture(source, metadata))
            else:
                require(args.capture_envelope is not None
                        and args.expected_manifest_sha256 is not None,
                        "REPLAY_INPUTS")
                item = vb.parse_document(read_regular(args.capture_envelope,
                                                      MAX_MANIFEST_BYTES))
                result = replay_capture(source, metadata, item,
                                        expected_manifest_sha256=args.expected_manifest_sha256)
        else:
            require(args.registry is not None
                    and args.expected_registry_sha256 is not None
                    and args.source is None and args.metadata is None
                    and args.capture_envelope is None
                    and args.expected_manifest_sha256 is None,
                    "REGISTRY_INPUTS")
            data = vb.parse_document(read_regular(args.registry, MAX_REGISTRY_BYTES))
            result = validate_registry(data,
                                       expected_registry_sha256=args.expected_registry_sha256)
        sys.stdout.buffer.write(vb.canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        error = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": error}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
