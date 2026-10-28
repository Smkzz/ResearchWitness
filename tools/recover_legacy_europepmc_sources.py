"""Recover exact *historical* Europe PMC JATS bytes, only with explicit network authority.

Default mode makes zero network calls and zero writes; it checks an existing
private cache against independently pinned October-2026 exposed development
source hashes. Network recovery is an operator-only opt-in; it does not widen
or work around this process's actual network policy. It never substitutes a
changed current publication version for the historic snapshot.

This does NOT retrieve PMC OAI-PMH original envelopes, prove legal reuse,
publisher authenticity, 2026 historical transfer time, independent labels,
scientific detection or protected custody.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tools import verification_benchmark as vb
from tools.offline_files import read_regular

INDEX_VERSION = "rw-historical-europepmc-source-index.v1"
REPORT_VERSION = "rw-historical-europepmc-recovery-report.v1"
RECEIPT_VERSION = "rw-historical-europepmc-current-transfer.v1"
ORIGINAL_MANIFEST_HASH = (
    "f626061019cafddb25164abe647fa127f3843ef8f1187bbbbf94398a8c19134d"
)
ORIGINAL_MANIFEST_REF = "6843593ff443d4a44c48d15a76949b323d0951ca"
SOURCE_URL_PREFIX = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
MAX_INDEX_BYTES = 64 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 16
MAX_NETWORK_REQUESTS = 5
PMCID = re.compile(r"PMC[1-9][0-9]{0,11}\Z", re.ASCII)
DATE = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]\Z", re.ASCII)
HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
INDEX_FIELDS = {
    "schema_version", "partition", "source_manifest", "restrictions", "records",
}
MANIFEST_FIELDS = {
    "repository", "ref", "path", "sha256", "retrieved_date",
}
ROW_FIELDS = {
    "pmcid", "source_kind", "parent_pmcid", "filename",
    "expected_bytes", "expected_sha256", "source_url",
    "declared_license", "declared_retrieval_date",
}
RESTRICTION_FIELDS = {
    "historical_hash_is_not_publisher_authentication",
    "article_licence_not_independently_verified",
    "source_correction_labels_not_independent",
    "newly_retrieved_body_does_not_prove_original_transport_event",
    "historical_exposed_only",
}


def require(condition: bool, code: str) -> None:
    vb.require(condition, code)


def _fields(value: Any, fields: set[str], code: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == fields, code)
    return value


def validate_index(index: dict[str, Any], *, expected_index_sha256: str,
                   exact_index_bytes: bytes) -> tuple[dict[str, Any], ...]:
    """Validate a separately pinned source index before any filesystem writes."""
    require(type(expected_index_sha256) is str
            and HASH.fullmatch(expected_index_sha256) is not None,
            "RECOVERY_INDEX_PIN_FORMAT")
    require(len(exact_index_bytes) <= MAX_INDEX_BYTES
            and sha256(exact_index_bytes).hexdigest() == expected_index_sha256,
            "RECOVERY_INDEX_EXTERNAL_PIN_MISMATCH")
    require(vb.parse_document(exact_index_bytes) == index,
            "RECOVERY_INDEX_DOCUMENT_MISMATCH")
    _fields(index, INDEX_FIELDS, "RECOVERY_INDEX_FIELDS")
    require(index["schema_version"] == INDEX_VERSION,
            "RECOVERY_INDEX_VERSION")
    require(index["partition"] == "exposed_development_historical_not_sealed",
            "RECOVERY_PROTECTED_DATA_FORBIDDEN")
    manifest = _fields(index["source_manifest"], MANIFEST_FIELDS,
                       "RECOVERY_INDEX_MANIFEST_FIELDS")
    require(manifest["repository"] == "Smkzz/ResearchWitness"
            and manifest["ref"] == ORIGINAL_MANIFEST_REF
            and manifest["path"] == "validation/paper-audit-wave-1/cases.json"
            and manifest["sha256"] == ORIGINAL_MANIFEST_HASH
            and manifest["retrieved_date"] == "2026-10-05",
            "RECOVERY_INDEX_ORIGIN_MISMATCH")
    restrictions = _fields(index["restrictions"], RESTRICTION_FIELDS,
                           "RECOVERY_INDEX_RESTRICTIONS")
    require(all(value is True for value in restrictions.values()),
            "RECOVERY_AUTHORITY_CLAIM_FORBIDDEN")
    records = index["records"]
    require(type(records) is list and 1 <= len(records) <= MAX_RECORDS,
            "RECOVERY_INDEX_RECORD_COUNT")
    output: dict[str, dict[str, Any]] = {}
    for record in records:
        _fields(record, ROW_FIELDS, "RECOVERY_RECORD_FIELDS")
        pmcid = record["pmcid"]
        require(type(pmcid) is str and PMCID.fullmatch(pmcid) is not None
                and pmcid not in output, "RECOVERY_PMCID_INVALID_OR_DUPLICATE")
        require(record["filename"] == f"{pmcid}.xml"
                and record["source_url"] == SOURCE_URL_PREFIX
                + f"{pmcid}/fullTextXML",
                "RECOVERY_SOURCE_URL_OR_FILENAME")
        require(type(record["expected_bytes"]) is int
                and 1 <= record["expected_bytes"] <= MAX_SOURCE_BYTES
                and type(record["expected_sha256"]) is str
                and HASH.fullmatch(record["expected_sha256"]) is not None,
                "RECOVERY_SOURCE_PIN_INVALID")
        require(record["source_kind"] in {"article", "correction"},
                "RECOVERY_SOURCE_KIND")
        parent = record["parent_pmcid"]
        require((parent is None and record["source_kind"] == "article")
                or (record["source_kind"] == "correction"
                    and type(parent) is str and PMCID.fullmatch(parent) is not None
                    and parent != pmcid),
                "RECOVERY_CORRECTION_PARENT")
        require(type(record["declared_license"]) is str
                and 1 <= len(record["declared_license"]) <= 160
                and type(record["declared_retrieval_date"]) is str
                and DATE.fullmatch(record["declared_retrieval_date"]) is not None
                and record["declared_retrieval_date"] == manifest["retrieved_date"],
                "RECOVERY_DECLARED_RIGHTS_OR_DATE")
        output[pmcid] = record
    for record in records:
        parent = record["parent_pmcid"]
        if parent is not None:
            require(parent in output
                    and output[parent]["source_kind"] == "article",
                    "RECOVERY_PARENT_NOT_PRESENT")
    return tuple(output[pmcid] for pmcid in sorted(output))


def _private_root(root: Path) -> Path:
    require(root.is_dir() and not root.is_symlink(),
            "RECOVERY_PRIVATE_ROOT_REQUIRED")
    # Source bytes must never be written into this public repo or a worktree.
    repo_root = Path(__file__).resolve().parents[1]
    require(not root.resolve().is_relative_to(repo_root),
            "RECOVERY_SOURCE_INSIDE_CHECKOUT_FORBIDDEN")
    return root


def _existing(root: Path, record: dict[str, Any]) -> str | None:
    path = root / record["filename"]
    if not path.exists() and not path.is_symlink():
        return None
    try:
        data = read_regular(path, MAX_SOURCE_BYTES)
    except (OSError, ValueError):
        return "EXISTING_SOURCE_UNSAFE_OR_UNREADABLE"
    if (len(data) == record["expected_bytes"]
            and sha256(data).hexdigest() == record["expected_sha256"]):
        return "EXACT_HISTORICAL_BYTES_PRESENT"
    return "EXISTING_SOURCE_VERSION_MISMATCH_NO_OVERWRITE"


def _receipt(record: dict[str, Any], *, observed_at_utc: str,
             content_type: str, data: bytes) -> dict[str, Any]:
    return {
        "schema_version": RECEIPT_VERSION,
        "pmcid": record["pmcid"],
        "provider_url": record["source_url"],
        "http_status_observed": 200,
        "response_body_stage": "http_decoded_entity_identity_encoding",
        "response_body_sha256": sha256(data).hexdigest(),
        "response_body_bytes": len(data),
        "content_type_observed": content_type,
        "observed_at_utc": observed_at_utc,
        "source_version_matches_2026_10_05_pin": True,
        "historical_2026_10_05_transport_proven": False,
        "article_specific_licence_independently_verified": False,
        "publisher_origin_independently_certified": False,
        "scientific_label_verified": False,
        "protected_partition_accessed": False,
    }


class _NoRedirect(HTTPRedirectHandler):
    """Do not send a second request to any host via a provider redirect."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def _official_open(request: Request, *, timeout: int) -> Any:
    return build_opener(_NoRedirect).open(request, timeout=timeout)


def _recover_one(root: Path, record: dict[str, Any],
                 opener: Callable[..., Any]) -> str:
    """One bounded, allowlisted provider request; never write a version drift."""
    request = Request(record["source_url"], headers={
        "User-Agent": "ResearchWitness-historical-development-source-recovery/1.0",
        "Accept-Encoding": "identity",
        "Accept": "application/xml, text/xml",
    })
    try:
        with opener(request, timeout=25) as response:
            if (response.geturl() != record["source_url"]
                    or response.status != 200):
                return "PROVIDER_URL_OR_STATUS_UNEXPECTED"
            encoding = response.headers.get("Content-Encoding", "identity")
            if encoding.lower() != "identity":
                return "PROVIDER_UNSUPPORTED_CONTENT_ENCODING"
            content_type = response.headers.get("Content-Type", "")[:100]
            data = response.read(MAX_SOURCE_BYTES + 1)
    except (HTTPError, URLError, OSError, TimeoutError):
        return "PROVIDER_UNAVAILABLE_NO_WRITE"
    if len(data) > MAX_SOURCE_BYTES:
        return "PROVIDER_BYTE_LIMIT_NO_WRITE"
    if (len(data) != record["expected_bytes"]
            or sha256(data).hexdigest() != record["expected_sha256"]):
        return "PROVIDER_BODY_DIFFERS_FROM_HISTORICAL_PIN_NO_WRITE"
    observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = vb.canonical_bytes(
        _receipt(record, observed_at_utc=observed,
                 content_type=content_type, data=data)
    )
    path = root / record["filename"]
    receipt_path = root / f"{record['pmcid']}.transfer.json"
    # Fail closed on existing untrusted/reparse entries. Never rewrite.
    if path.exists() or path.is_symlink() or receipt_path.exists() or receipt_path.is_symlink():
        return "RECOVERY_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE"
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        with receipt_path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        return "RECOVERY_INCOMPLETE_WRITE_REVIEW_REQUIRED"
    return "RECOVERED_EXACT_HISTORICAL_BYTES_NEW_TRANSPORT"


def recover(index: dict[str, Any], root: Path, *, expected_index_sha256: str,
            exact_index_bytes: bytes, network_authorized: bool = False,
            max_network_requests: int = 1, only_pmcid: str | None = None,
            opener: Callable[..., Any] = _official_open,
            pause: Callable[[float], Any] = time.sleep) -> dict[str, Any]:
    """Audit existing exact copies or run a bounded explicit authorized recovery.

    Callers that set network_authorized must independently have actual egress
    authority and article-specific legal permission. This flag grants none.
    """
    records = validate_index(index, expected_index_sha256=expected_index_sha256,
                             exact_index_bytes=exact_index_bytes)
    private = _private_root(Path(root))
    require(type(network_authorized) is bool and type(max_network_requests) is int
            and 1 <= max_network_requests <= MAX_NETWORK_REQUESTS,
            "RECOVERY_REQUEST_CAP")
    if only_pmcid is not None:
        require(type(only_pmcid) is str and PMCID.fullmatch(only_pmcid) is not None
                and only_pmcid in {r["pmcid"] for r in records},
                "RECOVERY_RECORD_NOT_IN_PINNED_INDEX")
        records = tuple(r for r in records if r["pmcid"] == only_pmcid)
    outcomes: list[dict[str, Any]] = []
    attempted = 0
    for record in records:
        status = _existing(private, record)
        if status is None:
            if not network_authorized:
                status = "SOURCE_MISSING_OFFLINE"
            elif record["declared_license"] != "CC BY 4.0":
                status = "RIGHTS_DECLARATION_AMBIGUOUS_NO_REQUEST"
            elif attempted >= max_network_requests:
                status = "NOT_ATTEMPTED_REQUEST_CAP"
            else:
                if attempted:
                    pause(0.4)  # Sequential official Europe PMC requests, never concurrent.
                attempted += 1
                status = _recover_one(private, record, opener)
        outcomes.append({"pmcid": record["pmcid"],
                         "source_kind": record["source_kind"],
                         "status": status})
    counts = Counter(row["status"] for row in outcomes)
    verified = (counts["EXACT_HISTORICAL_BYTES_PRESENT"]
                + counts["RECOVERED_EXACT_HISTORICAL_BYTES_NEW_TRANSPORT"])
    return {
        "schema_version": REPORT_VERSION,
        "status": ("ALL_SELECTED_HISTORICAL_BYTES_PRESENT"
                   if verified == len(records) else
                   "HISTORICAL_SOURCE_RESTORATION_INCOMPLETE"),
        "partition": "exposed_development_historical_not_sealed",
        "source_index_raw_sha256": sha256(exact_index_bytes).hexdigest(),
        "source_manifest_sha256": ORIGINAL_MANIFEST_HASH,
        "selected_records": len(records),
        "exact_original_content_hash_matches": verified,
        "network_requests_made": attempted,
        "network_opt_in_given": network_authorized,
        "counts_by_status": dict(sorted(counts.items())),
        "records": outcomes,
        "raw_source_text_emitted": False,
        "permission_or_network_policy_changed": False,
        "historical_provider_transport_authenticated": False,
        "article_licences_independently_verified": False,
        "scientific_labels_established": False,
        "protected_evaluation_qualified": False,
        "scientific_detection_improvement_established": False,
        "limitations": [
            "Identical archived SHA-256/length proves byte continuity, not the original 2026 retrieval event.",
            "Only Europe PMC historical fullTextXML JATS; never PMC OAI-PMH GetRecord raw envelopes.",
            "Source permissions and reviewer-independent correction truth remain external gates.",
            "Any changed provider bytes are refused, not silently reindexed or declared equivalent.",
            "The current index is known exposed development data, not fresh holdout selection.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--only-pmcid")
    parser.add_argument("--allow-authorized-network", action="store_true",
                        help="Requires pre-existing egress and verified reuse rights.")
    parser.add_argument("--max-network-requests", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        raw = read_regular(args.index, MAX_INDEX_BYTES)
        index = vb.parse_document(raw)
        report = recover(
            index, args.private_root,
            expected_index_sha256=args.expected_index_sha256,
            exact_index_bytes=raw,
            network_authorized=args.allow_authorized_network,
            max_network_requests=args.max_network_requests,
            only_pmcid=args.only_pmcid,
        )
        sys.stdout.buffer.write(vb.canonical_bytes(report))
        return 0 if report["status"] == "ALL_SELECTED_HISTORICAL_BYTES_PRESENT" else 1
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes(
            {"status": "invalid", "code": code}
        ))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
