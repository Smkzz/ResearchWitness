"""Strict private sampling-frame commitment for the PMC *development* pilot.

A separately retained hash prevents changing the set of declared attempted
sources without detection. Neither the hash nor this tool proves that the frame
was selected BEFORE outcome access or independently time-stamped.
No source content, protected labels, network or provider connection is used.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from tools import pmc_oai_envelope as pmc
from tools import source_capture_manifest as capture
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

VERSION = "rw-private-pmc-selection-frame.v1"
MAX_FRAME_BYTES = 32 * 1024
MAX_RECORDS = 12
MAX_FAMILIES = 5


def require(condition: bool, code: str) -> None:
    vb.require(condition, code)


def _fields(value: Any, names: set[str], code: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == names, code)
    return value


def validate(frame: dict[str, Any], *, expected_frame_sha256: str
             ) -> dict[str, dict[str, Any]]:
    """Validate pinned, outcome-free private selection identities and lineage."""
    vb.parse_document(vb.canonical_bytes(frame))
    require(vb.commitment(frame) == capture.digest(expected_frame_sha256),
            "PILOT_FRAME_EXTERNAL_PIN_MISMATCH")
    _fields(frame, {"schema_version", "partition", "selection", "records"},
            "PILOT_FRAME_FIELDS")
    require(frame["schema_version"] == VERSION, "PILOT_FRAME_VERSION")
    require(frame["partition"] == "development_exposed",
            "PILOT_FRAME_PROTECTED_PARTITION")
    require(frame["selection"] == "operator_declared_not_time_authenticated",
            "PILOT_FRAME_TIMING_NOT_AUTHENTICATED")
    rows = frame["records"]
    require(type(rows) is list and 2 <= len(rows) <= MAX_RECORDS,
            "PILOT_FRAME_RECORD_COUNT")
    identities: dict[str, dict[str, Any]] = {}
    families: set[str] = set()
    versions: set[tuple[str, str]] = set()
    source_families: dict[str, str] = {}
    for entry in rows:
        _fields(entry, {"record_id", "family_id", "version_id",
                        "oai_identifier", "kind", "parent_record_id"},
                "PILOT_FRAME_RECORD_FIELDS")
        rid = capture.identifier(entry["record_id"])
        family = capture.identifier(entry["family_id"])
        version = capture.identifier(entry["version_id"])
        requested = entry["oai_identifier"]
        require(type(requested) is str and
                pmc.OAI_ID.fullmatch(requested) is not None,
                "PILOT_FRAME_OAI_IDENTIFIER")
        kind = entry["kind"]
        require(type(kind) is str and kind in capture.KINDS,
                "PILOT_FRAME_SOURCE_KIND")
        parent = entry["parent_record_id"]
        require(parent is None if kind == "article"
                else type(parent) is str and parent != rid,
                "PILOT_FRAME_SOURCE_PARENT")
        if parent is not None:
            capture.identifier(parent)
        require(rid not in identities, "PILOT_FRAME_DUPLICATE_RECORD")
        require((family, version) not in versions,
                "PILOT_FRAME_DUPLICATE_VERSION")
        previous_family = source_families.setdefault(requested, family)
        require(previous_family == family,
                "PILOT_FRAME_SOURCE_CROSSES_FAMILIES")
        families.add(family)
        versions.add((family, version))
        identities[rid] = entry

    require(2 <= len(families) <= MAX_FAMILIES,
            "PILOT_FRAME_FAMILY_COUNT")
    for record_id, entry in identities.items():
        parent = entry["parent_record_id"]
        if parent is None:
            continue
        require(parent in identities, "PILOT_FRAME_PARENT_NOT_SELECTED")
        previous = identities[parent]
        require(previous["family_id"] == entry["family_id"],
                "PILOT_FRAME_PARENT_CROSSES_FAMILIES")
        if entry["kind"] == "revision":
            require(previous["oai_identifier"] == entry["oai_identifier"],
                    "PILOT_FRAME_REVISION_OAI_IDENTITY_MISMATCH")
    for record_id in identities:
        seen: set[str] = set()
        cursor: str | None = record_id
        while cursor is not None:
            require(cursor not in seen, "PILOT_FRAME_LINEAGE_CYCLE")
            seen.add(cursor)
            cursor = identities[cursor]["parent_record_id"]
    return identities


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", required=True, type=Path)
    parser.add_argument("--expected-frame-sha256", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--expected-ledger-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        from tools import pmc_pilot_ledger as pilot

        frame = vb.parse_document(read_regular(args.frame, MAX_FRAME_BYTES))
        ledger = vb.parse_document(
            read_regular(args.ledger, pilot.MAX_LEDGER_BYTES)
        )
        report = pilot.evaluate(
            ledger, args.private_root,
            expected_ledger_sha256=args.expected_ledger_sha256,
            selection_frame=frame,
            expected_frame_sha256=args.expected_frame_sha256,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(report))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes({"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
