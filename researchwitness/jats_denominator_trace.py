"""Offline JATS denominator-evidence trace over the EXISTING percentage detector.

This module DOES NOT RESOLVE scopes, select bases, change arithmetic decisions
or authenticate a scientific paper. It proves that the detector's already
reported XML element references exist in the preserved, identical source bytes.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from typing import Any

from . import _jats_parser as jats
from .jats_table_projection import _paths

VERSION = "rw-jats-denominator-evidence.v1"
MAX_FACTS_PER_RELATION = 64
MAX_TOTAL_FACTS = 32768
_DETECTOR_STATES = frozenset({
    "scope_ambiguous", "rounding_ambiguous",
    "arithmetic_match", "arithmetic_mismatch_candidate",
})
_CHECKED_STATES = frozenset({"arithmetic_match", "arithmetic_mismatch_candidate"})


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise jats.JATSSourceError(code)


def _source_index(root: jats._Node) -> dict[tuple[int, int], jats._Node]:
    """Index actual parsed XML element byte spans, never free-text searches."""
    output: dict[tuple[int, int], jats._Node] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        key = (node.byte_start, node.byte_end)
        _require(key not in output and key[0] < key[1],
                 "SOURCE_ELEMENT_SPAN_AMBIGUOUS")
        output[key] = node
        stack.extend(node.children)
    return output


def _anchor(
    evidence: dict[str, Any], positions: dict[tuple[int, int], jats._Node],
    paths: dict[int, str], source_hash: str, *,
    quote_field: str,
) -> dict[str, Any]:
    _require(type(evidence) is dict, "SOURCE_EVIDENCE_NOT_OBJECT")
    start, end = evidence.get("byte_start"), evidence.get("byte_end")
    _require(type(start) is int and type(end) is int,
             "SOURCE_EVIDENCE_SPAN_NOT_INTEGER")
    node = positions.get((start, end))
    _require(node is not None, "SOURCE_EVIDENCE_ELEMENT_NOT_FOUND")
    quote = jats._text(node)
    _require(evidence.get(quote_field) == quote[:jats.MAX_EVIDENCE_TEXT],
             "SOURCE_EVIDENCE_QUOTE_MISMATCH")
    if quote_field == "quote":
        _require(evidence.get("quote_truncated") is (len(quote) > jats.MAX_EVIDENCE_TEXT),
                 "SOURCE_EVIDENCE_TRUNCATION_MISMATCH")
    else:
        _require(evidence.get("cell_quote_truncated") is (len(quote) > jats.MAX_EVIDENCE_TEXT),
                 "SOURCE_CELL_TRUNCATION_MISMATCH")
    return {
        "source_file": "source.xml",
        "source_format": "jats_xml",
        "source_sha256": source_hash,
        "element_path": paths[id(node)],
        "start_byte": start,
        "end_byte": end,
        "normalized_quote": quote[:jats.MAX_EVIDENCE_TEXT],
        "normalized_quote_truncated": len(quote) > jats.MAX_EVIDENCE_TEXT,
        "range_semantics": "original_xml_element_including_markup_not_numeric_token",
    }


def trace_denominators(source: bytes, detector_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Document existing decisions with exact original-byte source references.

    Caller-supplied detector results are completely recomputed before use, not
    trusted because their hash happens to match. Contradictory or unresolved
    source facts remain visible and are never overridden by arithmetic fit.
    """
    root = jats._parse_jats(source)
    source_hash = sha256(source).hexdigest()
    original = jats.audit_jats_percentage_tables(source)
    if detector_report is not None:
        _require(type(detector_report) is dict and detector_report == original,
                 "SUPPLIED_DETECTOR_RESULTS_NOT_REPLAYED_FROM_SOURCE")
    _require(original["source_sha256"] == source_hash, "SOURCE_DIGEST_CHANGED")
    positions, paths = _source_index(root), _paths(root)
    relations: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    fact_roles: Counter[str] = Counter()
    fact_total = conflicts = unresolved = 0

    for index, relation in enumerate(original["results"], start=1):
        _require(type(relation) is dict and relation.get("status") in _DETECTOR_STATES,
                 "DETECTOR_RELATION_UNKNOWN_STATE")
        status = relation["status"]
        states[status] += 1
        evidence = relation["evidence"]
        _require(type(evidence) is dict and evidence.get("source_sha256") == source_hash,
                 "DETECTOR_SOURCE_EVIDENCE_HASH_MISMATCH")
        candidate_anchor = _anchor(
            evidence, positions, paths, source_hash, quote_field="cell_quote",
        )
        facts = evidence.get("denominator_sources")
        _require(type(facts) is list and len(facts) <= MAX_FACTS_PER_RELATION,
                 "DENOMINATOR_FACT_LIMIT_OR_FORMAT")
        fact_total += len(facts)
        _require(fact_total <= MAX_TOTAL_FACTS, "DENOMINATOR_TOTAL_FACT_LIMIT")
        reported_denominator = relation.get("denominator")
        _require(reported_denominator is None
                 or (type(reported_denominator) is int
                     and 0 < reported_denominator <= 999_999_999),
                 "DETECTOR_DENOMINATOR_OUT_OF_DOMAIN")
        _require(status not in _CHECKED_STATES or reported_denominator is not None,
                 "CHECKED_RELATION_WITHOUT_BASE")
        reasons = []
        traced = []
        for fact in facts:
            _require(type(fact) is dict and set(fact) == {"value", "evidence"},
                     "DENOMINATOR_FACT_SCHEMA_MISMATCH")
            value, fact_evidence = fact["value"], fact["evidence"]
            _require(type(value) is int and 0 <= value <= 999_999_999,
                     "DENOMINATOR_FACT_VALUE_OUT_OF_DOMAIN")
            _require(type(fact_evidence) is dict
                     and type(fact_evidence.get("role")) is str
                     and 0 < len(fact_evidence["role"]) <= 80,
                     "DENOMINATOR_FACT_ROLE_INVALID")
            role = fact_evidence["role"]
            fact_roles[role] += 1
            traced.append({
                "printed_integer": value,
                "detector_provenance_role": role,
                "numeric_equals_detector_base": (
                    reported_denominator is not None
                    and value == reported_denominator
                ),
                "source_anchor": _anchor(
                    fact_evidence, positions, paths, source_hash, quote_field="quote",
                ),
            })
        values = sorted({fact["printed_integer"] for fact in traced})
        if len(values) > 1:
            conflicts += 1
            reasons.append("MULTIPLE_VISIBLE_DENOMINATOR_VALUES")
        if status not in _CHECKED_STATES:
            unresolved += 1
            reasons.append("DETECTOR_DID_NOT_ACCEPT_ARITHMETIC_RELATION")
        if not traced:
            reasons.append("NO_EXPLICIT_DENOMINATOR_SOURCE_FACT")
        if status in _CHECKED_STATES:
            _require(any(fact["numeric_equals_detector_base"] for fact in traced),
                     "ACCEPTED_BASE_HAS_NO_SOURCE_ELEMENT")
        relations.append({
            "relation_id": f"{source_hash[:16]}:den-{index:04d}",
            "source_relation_index": index,
            "detector_status": status,
            "detector_reason": relation.get("reason"),
            "numerator": relation.get("numerator"),
            "reported_percent": relation.get("reported_percent"),
            "detector_denominator": reported_denominator,
            "detector_denominator_scope": relation.get("denominator_scope"),
            "relation_source_anchor": candidate_anchor,
            "denominator_fact_count": len(traced),
            "denominator_fact_values": values,
            "provenance_flags": reasons,
            "source_scope_review_state": (
                "MULTIPLE_VISIBLE_VALUES_REQUIRE_INDEPENDENT_REVIEW"
                if len(values) > 1 else "NOT_INDEPENDENTLY_ADJUDICATED"
            ),
            "denominator_facts": traced,
            "scientific_denominator_scope_independently_adjudicated": False,
        })
    return {
        "schema_version": VERSION,
        "source_sha256": source_hash,
        "classification": "SOURCE_REFERENCE_TRACE_NOT_DENOMINATOR_ADJUDICATION",
        "relation_count": len(relations),
        "fact_count": fact_total,
        "unresolved_relation_count": unresolved,
        "multiple_fact_values_relation_count": conflicts,
        "detector_status_counts": dict(sorted(states.items())),
        "denominator_fact_roles": dict(sorted(fact_roles.items())),
        "relations": relations,
        "detector_method_scope_overflow": bool(original["method_scope_overflow"]),
        "full_article_denominator_provenance_established": False,
        "source_origin_authenticated": False,
        "paper_error_established": False,
        "limitations": [
            "This replays the same detector. It does not independently validate its source interpretation.",
            "XML element byte spans include markup; they are not numeric-token byte offsets.",
            "Different explicit base values can be correctly scoped to different strata; a flag is not a verdict.",
            "Source SHA-256 proves byte identity, not original publication authenticity.",
            "Only the existing bounded percentage relationships are traced; absent detections are not negatives.",
            "Conditional, rounding-ambiguous and unresolved scope outcomes stay unresolved.",
        ],
    }
