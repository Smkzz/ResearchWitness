"""Opt-in, source-anchored count-only JATS table-total arithmetic.

Checks *only* a compact two-column, explicitly exhaustive & disjoint
participant-category table with a final Total row. This cannot determine
paper correctness, infer an unstated population, or repair missing data.
"""
from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from .paper_document import PaperDocument, Table

VERSION = "rw-jats-explicit-participant-total.v1"
MAX_ROWS_PER_TABLE = 64
MAX_COUNT = 999_999_999
_COUNT = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3}){1,2}|[0-9]{1,9})\Z")
_EXPLICIT_PARTITION = re.compile(
    r"\bmutually exclusive and exhaustive categories of participants\b",
    re.IGNORECASE,
)
_UNSAFE_CONTEXT = re.compile(
    r"\b(?:not mutually|not exhaustive|overlap(?:ping)?|multiple responses?|"
    r"weighted|adjusted|imputed|estimated|subsample|subset|available cases?|"
    r"missing(?:ness)?|unknown|unreported|exclud(?:e|ed|ing)|"
    r"non-exhaustive|nonexclusive|non-exclusive)\b",
    re.IGNORECASE,
)


def _count(text: str) -> int | None:
    token = text.strip()
    if _COUNT.fullmatch(token) is None:
        return None
    amount = int(token.replace(",", ""))
    return amount if 0 <= amount <= MAX_COUNT else None


def _headers(table: Table) -> bool:
    # Recognize intended count headers even when a malformed span creates
    # extra projected columns: this is UNSUPPORTED, not NOT_APPLICABLE.
    if len(table.columns) < 2:
        return False
    labels = [" ".join(" ".join(col.header_hierarchy).split()).casefold()
              for col in table.columns]
    return labels[0] == "category" and labels[1] in {
        "participants", "number of participants", "participants (n)",
    }


def _case(table: Table) -> dict[str, Any]:
    output: dict[str, Any] = {
        "table_id": table.table_id,
        "status": "NOT_APPLICABLE",
        "reason": None,
        "computed_total_exact": None,
        "reported_total_exact": None,
        "difference_exact": None,
        "category_operands": [],
        "total_anchor": None,
        "caption_anchor": None,
        "scientific_error_established": False,
    }
    if not _headers(table):
        return output
    output["status"] = "UNSUPPORTED"
    if not _EXPLICIT_PARTITION.search(table.caption):
        output["reason"] = "EXHAUSTIVE_DISJOINT_SOURCE_DECLARATION_MISSING"
        return output
    if (_UNSAFE_CONTEXT.search(table.caption) or
            _UNSAFE_CONTEXT.search(table.label)):
        output["reason"] = "SOURCE_SCOPE_CONFLICT"
        return output
    if (len(table.columns) != 2
            or table.structure_status != "mapped_not_adjudicated"
            or table.spans or table.footnotes):
        output["reason"] = "UNRESOLVED_TABLE_STRUCTURE_OR_FOOTNOTES"
        return output
    if (len(table.rows) < 3 or len(table.rows) > MAX_ROWS_PER_TABLE
            or len({row.row_group for row in table.rows}) != 1):
        output["reason"] = "TOTAL_ROW_OR_GROUP_STRUCTURE_AMBIGUOUS"
        return output
    observed: list[tuple[str, int, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in table.rows:
        if len(row.cells) != 2 or [c.column_start for c in row.cells] != [0, 1]:
            output["reason"] = "COUNT_COLUMN_LAYOUT_AMBIGUOUS"
            return output
        label, value = row.cells
        if any(
            cell.row_span != 1 or cell.column_span != 1
            or cell.footnote_references or cell.cross_references
            or cell.scope_denominator_cues or cell.indentation_level
            or any(ref.cross_references or ref.footnote_references
                   for ref in cell.effective_header_refs)
            for cell in (label, value)
        ):
            output["reason"] = "COUNT_CELL_SCOPE_OR_ANCHOR_UNRESOLVED"
            return output
        label_text = " ".join(label.raw_text.split())
        normalized = label_text.casefold()
        amount = _count(value.raw_text)
        if (not normalized or normalized in seen
                or _UNSAFE_CONTEXT.search(label_text)
                or amount is None):
            output["reason"] = "COUNT_OPERAND_OR_CATEGORY_INVALID"
            return output
        seen.add(normalized)
        observed.append((normalized, amount, asdict(value.source_anchor)))
    if observed[-1][0] != "total" or any(x[0] == "total" for x in observed[:-1]):
        output["reason"] = "FINAL_UNIQUE_TOTAL_ROW_REQUIRED"
        return output
    expected = sum(value for _, value, _ in observed[:-1])
    reported = observed[-1][1]
    if expected > MAX_COUNT:
        output["reason"] = "COUNT_SUM_OUT_OF_DOMAIN"
        return output
    output.update({
        "status": ("COUNT_TOTAL_MATCH" if expected == reported
                   else "COUNT_TOTAL_MISMATCH_CANDIDATE"),
        "reason": None,
        "computed_total_exact": str(expected),
        "reported_total_exact": str(reported),
        "difference_exact": str(reported - expected),
        "category_operands": [
            {"category": label, "count_exact": str(count), "source_anchor": anchor}
            for label, count, anchor in observed[:-1]
        ],
        "total_anchor": observed[-1][2],
        "caption_anchor": (asdict(table.caption_anchor)
                           if table.caption_anchor is not None else None),
    })
    return output


def check_explicit_participant_totals(document: PaperDocument) -> dict[str, Any]:
    """Report every table and each arithmetic eligibility refusal."""
    if document.source_format != "jats_xml":
        raise ValueError("Only source-mapped JATS documents are supported")
    cases = [_case(table) for table in document.tables]
    statuses = {k: sum(item["status"] == k for item in cases) for k in (
        "COUNT_TOTAL_MATCH", "COUNT_TOTAL_MISMATCH_CANDIDATE",
        "UNSUPPORTED", "NOT_APPLICABLE",
    )}
    return {
        "schema_version": VERSION,
        "mode": "opt_in_explicit_mutually_exclusive_exhaustive_participant_count_totals",
        "tables_seen": len(document.tables),
        "status_counts": statuses,
        "candidate_count": statuses["COUNT_TOTAL_MISMATCH_CANDIDATE"],
        "checked_table_count": (
            statuses["COUNT_TOTAL_MATCH"] + statuses["COUNT_TOTAL_MISMATCH_CANDIDATE"]
        ),
        "cases": cases,
        "whole_paper_coverage_established": False,
        "scientific_error_established": False,
        "source_origin_authenticated": False,
        "limitations": [
            "One explicitly disjoint, exhaustive, participant-category table only.",
            "Final total versus disjoint category counts; no statistical or source truth.",
            "No source-independent proof that categories are disjoint or exhaustive.",
            "Ambiguous structure, notes, scope, missingness and noninteger values abstain.",
            "Original XML element spans are not token-level byte offsets.",
            "All mismatch candidates remain unreviewed and scientifically unadjudicated.",
        ],
    }
