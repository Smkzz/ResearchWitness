"""Source-grounded DEVELOPMENT annotation packets for JATS denominator scope.

These are reviewer *declarations*, not independent verification or scientific
ground truth. No model is invoked, no reviewer identity is authenticated, no
protected data is accessed, and no paper/error decision is returned. The
packet intentionally omits existing detector verdicts and selected bases.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import sys
from typing import Any

from researchwitness import _jats_parser as jats
from researchwitness.jats_denominator_trace import trace_denominators
from tools import verification_benchmark as vb
from tools.offline_files import read_regular

PACKET_VERSION = "rw-development-denominator-scope-packet.v1"
REVIEW_VERSION = "rw-development-denominator-scope-annotation.v1"
RESULT_VERSION = "rw-development-denominator-scope-reconciliation.v1"
MAX_PACKET_BYTES = 4 * 1024 * 1024
MAX_REVIEW_BYTES = 1024 * 1024
MAX_PACKET_RELATIONS = 1000
MAX_FACTS_PER_RELATION = 64
MAX_REVIEW_EVIDENCE_REFS = 32
DIMENSIONS = ("population", "group", "timepoint", "analysis_set", "percentage_base")
VALUES = frozenset({"explicitly_same", "explicitly_different", "unstated"})
DECISIONS = frozenset({"same_scope_proposed", "different_scope_proposed", "unresolved"})
MODES = frozenset({
    "manual_source_reading_declared", "ai_assisted_development",
    "synthetic_demonstration",
})


def require(ok: bool, code: str) -> None:
    vb.require(ok, code)


def exact_dict(value: Any, keys: str, code: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == set(keys.split()), code)
    return value


def as_sha(value: Any) -> str:
    require(type(value) is str and vb.HASH.fullmatch(value) is not None,
            "INVALID_SHA256")
    return value


def as_id(value: Any) -> str:
    require(type(value) is str and vb.ID.fullmatch(value) is not None,
            "INVALID_REVIEWER_ID")
    return value


def make_packet(source: bytes) -> dict[str, Any]:
    """Derive a BLINDED review packet from the existing source trace.

    This is blinded only to the detector's *decision*; it is not a blinded
    empirical study because its source excerpts and selection are exposed.
    """
    require(type(source) is bytes and 0 < len(source) <= jats.MAX_SOURCE_BYTES,
            "SOURCE_BYTE_LIMIT")
    trace = trace_denominators(source)
    require(trace["relation_count"] <= MAX_PACKET_RELATIONS,
            "PACKET_RELATION_LIMIT")
    rows: list[dict[str, Any]] = []
    for relation in trace["relations"]:
        require(relation["denominator_fact_count"] <= MAX_FACTS_PER_RELATION,
                "PACKET_FACT_LIMIT")
        rid = relation["relation_id"]
        # Stable ordering by ORIGINAL XML position, not detector preference
        # or its selected denominator. Duplicate printed facts remain visible.
        source_facts = sorted(
            relation["denominator_facts"],
            key=lambda fact: (
                fact["source_anchor"]["start_byte"],
                fact["source_anchor"]["end_byte"],
                fact["source_anchor"]["element_path"],
                fact["printed_integer"],
                fact["detector_provenance_role"],
            ),
        )
        rows.append({
            "relation_id": rid,
            "relation_source_anchor": relation["relation_source_anchor"],
            "facts": [
                {
                    "fact_id": f"{rid}:f-{index:02d}",
                    "printed_integer": fact["printed_integer"],
                    "provenance_role": fact["detector_provenance_role"],
                    "source_anchor": fact["source_anchor"],
                }
                for index, fact in enumerate(source_facts, start=1)
            ],
        })
    packet = {
        "schema_version": PACKET_VERSION,
        "exposure": "development_only",
        "source_sha256": sha256(source).hexdigest(),
        "source_format": "jats_xml",
        "source_origin_authenticated": False,
        "reviewer_independence_authenticated": False,
        "detector_verdict_and_selected_base_included": False,
        "packet_generation": "existing_detector_source_fact_projection",
        "relations": rows,
    }
    require(len(vb.canonical_bytes(packet)) <= MAX_PACKET_BYTES,
            "PACKET_OUTPUT_BYTE_LIMIT")
    return packet


def packet_commitment(packet: dict[str, Any]) -> str:
    return vb.commitment(packet)


def validate_packet(source: bytes, packet: dict[str, Any],
                    expected_packet_sha256: str) -> str:
    """Byte-match a supplied packet against a fresh original-source projection."""
    wanted = as_sha(expected_packet_sha256)
    require(vb.commitment(packet) == wanted, "PACKET_PIN_MISMATCH")
    require(packet == make_packet(source), "PACKET_SOURCE_REPLAY_MISMATCH")
    return wanted


def validate_review(packet: dict[str, Any], review: dict[str, Any],
                    packet_sha256: str) -> dict[str, Any]:
    exact_dict(review,
               "schema_version packet_sha256 reviewer_id review_method "
               "independence_declared rows", "REVIEW_FIELDS")
    require(review["schema_version"] == REVIEW_VERSION, "REVIEW_SCHEMA")
    require(review["packet_sha256"] == packet_sha256, "REVIEW_PACKET_PIN")
    as_id(review["reviewer_id"])
    require(type(review["review_method"]) is str
            and review["review_method"] in MODES,
            "REVIEW_METHOD_UNSUPPORTED")
    require(type(review["independence_declared"]) is bool,
            "INDEPENDENCE_DECLARATION_TYPE")
    require(type(review["rows"]) is list
            and len(review["rows"]) == len(packet["relations"]), "REVIEW_COVERAGE")
    validated = []
    for expected, entry in zip(packet["relations"], review["rows"], strict=True):
        exact_dict(entry,
                   "relation_id decision selected_fact_id basis_fact_ids "
                   "scope_dimensions rationale", "REVIEW_ROW_FIELDS")
        require(entry["relation_id"] == expected["relation_id"],
                "REVIEW_RELATION_ORDER_OR_ID")
        require(entry["decision"] in DECISIONS, "REVIEW_DECISION")
        scope = exact_dict(entry["scope_dimensions"], " ".join(DIMENSIONS),
                           "REVIEW_SCOPE_DIMENSIONS")
        require(all(type(scope[name]) is str and scope[name] in VALUES
                    for name in DIMENSIONS), "REVIEW_SCOPE_VALUE")
        rationale = entry["rationale"]
        require(type(rationale) is str and 35 <= len(rationale) <= 600
                and rationale == rationale.strip()
                and not any(ord(ch) < 32 for ch in rationale),
                "REVIEW_RATIONALE_REQUIRED")
        references = entry["basis_fact_ids"]
        require(type(references) is list
                and len(references) <= MAX_REVIEW_EVIDENCE_REFS
                and all(type(ref) is str for ref in references)
                and len(references) == len(set(references)),
                "REVIEW_BASIS_REFERENCE_LIST")
        available = {fact["fact_id"] for fact in expected["facts"]}
        require(all(type(ref) is str and ref in available for ref in references),
                "REVIEW_SOURCE_REFERENCE_MISSING")
        chosen = entry["selected_fact_id"]
        require(chosen is None or (type(chosen) is str and chosen in available),
                "REVIEW_SELECTED_FACT_INVALID")
        if entry["decision"] == "same_scope_proposed":
            require(chosen is not None and chosen in references
                    and all(scope[name] == "explicitly_same"
                            for name in DIMENSIONS),
                    "REVIEW_SAME_SCOPE_NOT_ESTABLISHED_BY_DECLARATION")
        elif entry["decision"] == "different_scope_proposed":
            require(chosen is not None and chosen in references
                    and any(scope[name] == "explicitly_different"
                            for name in DIMENSIONS),
                    "REVIEW_DIFFERENT_SCOPE_NOT_EXPLAINED")
        else:
            require(chosen is None and
                    ("unstated" in scope.values()
                     or not expected["facts"]),
                    "REVIEW_UNRESOLVED_CONTRACT")
        if not expected["facts"]:
            require(entry["decision"] == "unresolved" and not references,
                    "REVIEW_CANNOT_RESOLVE_ABSENT_FACT")
        validated.append(entry)
    return {"reviewer_id": review["reviewer_id"],
            "review_method": review["review_method"],
            "independence_declared": review["independence_declared"],
            "rows": validated}


def reconcile(source: bytes, packet: dict[str, Any],
              review_a: dict[str, Any], review_b: dict[str, Any],
              *, expected_source_sha256: str,
              expected_packet_sha256: str) -> dict[str, Any]:
    """Reconcile declared opinions, never certify independent scientific truth."""
    require(sha256(source).hexdigest() == as_sha(expected_source_sha256),
            "SOURCE_PIN_MISMATCH")
    pinned = validate_packet(source, packet, expected_packet_sha256)
    a = validate_review(packet, review_a, pinned)
    b = validate_review(packet, review_b, pinned)
    require(a["reviewer_id"] != b["reviewer_id"], "REVIEWER_ID_REUSED")
    results = []
    statuses: Counter[str] = Counter()
    for row, left, right in zip(packet["relations"], a["rows"], b["rows"], strict=True):
        distinct = {fact["printed_integer"] for fact in row["facts"]}
        same = (left["decision"] == right["decision"]
                and left["selected_fact_id"] == right["selected_fact_id"]
                and left["scope_dimensions"] == right["scope_dimensions"])
        copied_row = left == right
        if len(distinct) > 1:
            state = "VISIBLE_BASE_CONFLICT_REQUIRES_ADJUDICATION"
        elif copied_row:
            state = "IDENTICAL_REVIEW_RECORDS_REQUIRE_INDEPENDENCE_CHECK"
        elif left["decision"] == right["decision"] == "unresolved":
            state = "BOTH_DECLARED_UNRESOLVED"
        elif same and left["decision"] != "unresolved":
            state = "DECLARED_CONCORDANCE_NOT_AUTHENTICATED"
        else:
            state = "REVIEWER_DISAGREEMENT_OR_INCOMPLETE"
        statuses[state] += 1
        results.append({
            "relation_id": row["relation_id"],
            "state": state,
            "reviewer_decisions": [left["decision"], right["decision"]],
            "reviewer_selected_fact_ids": [left["selected_fact_id"],
                                           right["selected_fact_id"]],
            "distinct_visible_base_count": len(distinct),
            "scientific_label_independently_authenticated": False,
            "ready_for_sealed_evaluation": False,
        })
    out = {
        "schema_version": RESULT_VERSION,
        "source_sha256": sha256(source).hexdigest(),
        "packet_sha256": pinned,
        "review_sha256s": [vb.commitment(review_a), vb.commitment(review_b)],
        "reviewers": [
            {"reviewer_id": a["reviewer_id"], "method": a["review_method"],
             "independence_declared": a["independence_declared"]},
            {"reviewer_id": b["reviewer_id"], "method": b["review_method"],
             "independence_declared": b["independence_declared"]},
        ],
        "status_counts": dict(sorted(statuses.items())),
        "registered_relation_count": len(packet["relations"]),
        "relations": results,
        "classification": "DEVELOPMENT_SOURCE_ANNOTATION_ACCOUNTING_ONLY",
        "reviewer_identity_authenticated": False,
        "reviewer_independence_authenticated": False,
        "source_origin_authenticated": False,
        "scientific_truth_established": False,
        "protected_custody_qualified": False,
        "limitations": [
            "The packet is derived from existing detector source facts; omitted facts are not recovered.",
            "Reviewer identities, isolation and independent reading are not authenticated by this CLI.",
            "Source paths and cited numbers are verified structurally, not semantically.",
            "Two matching declarations do not establish a correct scientific denominator.",
            "Different bases, reviewer disagreement, absent facts and uncertainty remain unresolved.",
            "Only development-exposed source material is permitted; no protected-data access.",
        ],
    }
    require(len(vb.canonical_bytes(out)) <= MAX_PACKET_BYTES,
            "RECONCILIATION_BYTE_LIMIT")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True, choices=("prepare", "reconcile"))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--expected-packet-sha256")
    parser.add_argument("--review-a", type=Path)
    parser.add_argument("--review-b", type=Path)
    args = parser.parse_args(argv)
    try:
        data = read_regular(args.source, jats.MAX_SOURCE_BYTES)
        require(sha256(data).hexdigest() == as_sha(args.expected_source_sha256),
                "SOURCE_PIN_MISMATCH")
        if args.action == "prepare":
            require(args.packet is None and args.expected_packet_sha256 is None
                    and args.review_a is None and args.review_b is None,
                    "PREPARE_EXTRA_ARGUMENTS")
            packet = make_packet(data)
            result = {"packet": packet, "packet_sha256": vb.commitment(packet)}
        else:
            require(args.packet is not None
                    and args.expected_packet_sha256 is not None
                    and args.review_a is not None and args.review_b is not None,
                    "RECONCILE_INPUTS_REQUIRED")
            envelope = vb.parse_document(read_regular(args.packet, MAX_PACKET_BYTES))
            exact_dict(envelope, "packet packet_sha256", "PACKET_ENVELOPE_FIELDS")
            require(envelope["packet_sha256"] == as_sha(args.expected_packet_sha256),
                    "PACKET_ENVELOPE_PIN")
            packet = envelope["packet"]
            left = vb.parse_document(read_regular(args.review_a, MAX_REVIEW_BYTES))
            right = vb.parse_document(read_regular(args.review_b, MAX_REVIEW_BYTES))
            result = reconcile(data, packet, left, right,
                               expected_source_sha256=args.expected_source_sha256,
                               expected_packet_sha256=args.expected_packet_sha256)
        sys.stdout.buffer.write(vb.canonical_bytes(result))
        return 0
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        code = str(exc) if isinstance(exc, vb.BenchmarkError) else "INVALID_INPUT_OR_IO"
        sys.stderr.buffer.write(vb.canonical_bytes(
            {"status": "invalid", "code": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
