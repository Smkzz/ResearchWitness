"""Optional source-anchored hypotheses for multi-column JATS population sections.

This is a developer-exposed *conditional* arithmetic review, not a change to
existing audit-jats results, an authenticated source, or a scientific error
finding. Run offline with: python -m researchwitness.jats_section_proposals FILE
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from ._jats_files import read_regular
from ._jats_math import percentage_recalculation
from ._jats_parser import (
    _ADJUSTMENT_NOTE_RE,
    _COUNT_PERCENT_RE,
    _ROUNDING_NOTE_RE,
    _attribute,
    _cells,
    _denominator_facts,
    _descendants,
    _evidence,
    _header_columns,
    _parse_jats,
    _span,
    _text,
    JATSSourceError,
    MAX_RESULTS,
    MAX_ROWS,
    MAX_SOURCE_BYTES,
    MAX_TABLES,
)

_SECTION_LABEL_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9 /,+&\u2013\u2014_-]{0,100}\b"
    r"(?:patients|participants|subjects|cases|respondents)$",
    re.IGNORECASE,
)
_SECTION_N_RE = re.compile(r"^\s*N\s*[=:]\s*([0-9]{1,9}|[0-9]{1,3}(?:,[0-9]{3}){1,2})\s*$")
_ROW_PERCENT_CUE_RE = re.compile(r"\bn\s*\(\s*%\s*\)", re.IGNORECASE)
MAX_PROPOSAL_QUOTE = 200


def _single_cell_columns(cells: list[Any]) -> bool:
    return all(_span(c, "colspan") == 1 and _span(c, "rowspan") == 1 for c in cells)


def _section(cells: list[Any]) -> tuple[str, list[int]] | None:
    if len(cells) < 3 or len(cells) > 64 or not _single_cell_columns(cells):
        return None
    label = _text(cells[0])
    if not _SECTION_LABEL_RE.fullmatch(label):
        return None
    values: list[int] = []
    for cell in cells[1:]:
        m = _SECTION_N_RE.fullmatch(_text(cell))
        if not m:
            return None
        v = int(m.group(1).replace(",", ""))
        if v <= 0:
            return None
        values.append(v)
    return label, values


def review_section_denominators(data: bytes) -> dict[str, Any]:
    """Return conditional arithmetic paired with local printed section Ns.

    A section N is a *hypothesis*, not a proved percentage base. A conflicting
    older column header remains visible; no denominator is silently resolved.
    """
    root = _parse_jats(data)  # Enforces bytes, entity, node and depth limits.
    source_sha = hashlib.sha256(data).hexdigest()
    wrappers = list(_descendants(root, "table-wrap"))
    if len(wrappers) > MAX_TABLES:
        raise JATSSourceError("Too many table wrappers")
    results: list[dict[str, Any]] = []
    section_count = table_count = rows_seen = 0
    skipped_unscoped = 0
    for wrapper in wrappers:
        tables = list(_descendants(wrapper, "table"))
        if not tables:
            continue
        cap = next(iter(_descendants(wrapper, "caption")), None)
        foot = list(_descendants(wrapper, "table-wrap-foot"))
        local_context = " ".join(_text(x) for x in ([cap] if cap else []) + foot)
        # Adjustment or rounding method must not be smuggled in as a raw percentage.
        blocked_method = bool(_ADJUSTMENT_NOTE_RE.search(local_context) or
                              _ROUNDING_NOTE_RE.search(local_context))
        for table in tables:
            table_count += 1
            if table_count > MAX_TABLES:
                raise JATSSourceError("Too many table elements")
            name = (_attribute(wrapper, "id") or f"table-{table_count}")[:100]
            heads = [r for s in _descendants(table, "thead") for r in _descendants(s, "tr")]
            headers, unsupported_headers, _ = _header_columns(heads)
            body = [r for s in _descendants(table, "tbody") for r in _descendants(s, "tr")]
            if not body:
                head_ids = {id(r) for r in heads}
                body = [r for r in _descendants(table, "tr") if id(r) not in head_ids]
            # Reject all nonrectangular body layouts. A rowspan inherited from
            # an earlier row can otherwise shift a later column invisibly.
            if any(not _single_cell_columns(_cells(row)) for row in body):
                rows_seen += len(body)
                if rows_seen > MAX_ROWS:
                    raise JATSSourceError("Too many table rows")
                skipped_unscoped += len(body)
                continue
            active: tuple[str, list[int], list[Any]] | None = None
            for row in body:
                rows_seen += 1
                if rows_seen > MAX_ROWS:
                    raise JATSSourceError("Too many table rows")
                cells = _cells(row)
                marker = _section(cells)
                if marker is not None:
                    active = marker[0], marker[1], cells
                    section_count += 1
                    continue
                # Any apparent N-per-column row is a boundary even if its
                # population label is unrecognised or the Ns are inconsistent.
                # Never carry the previous denominator through a new section.
                n_count = sum(bool(_SECTION_N_RE.fullmatch(_text(c)))
                              for c in cells[1:])
                if (cells and (_SECTION_LABEL_RE.fullmatch(_text(cells[0]))
                               or n_count >= 2)):
                    active = None
                    skipped_unscoped += 1
                    continue
                if active is None or not cells:
                    continue
                label, ns, marker_cells = active
                if (len(cells) != len(marker_cells) or not _single_cell_columns(cells)
                        or unsupported_headers or blocked_method):
                    skipped_unscoped += 1
                    continue
                row_label = _text(cells[0])
                if not _ROW_PERCENT_CUE_RE.search(row_label):
                    continue
                if _ADJUSTMENT_NOTE_RE.search(row_label) or _ROUNDING_NOTE_RE.search(row_label):
                    skipped_unscoped += 1
                    continue
                for idx, cell in enumerate(cells[1:], start=1):
                    match = _COUNT_PERCENT_RE.fullmatch(_text(cell))
                    if not match:
                        continue
                    numerator = int(match.group("count").replace(",", ""))
                    reported = match.group("percent")
                    denominator = ns[idx - 1]
                    try:
                        calculation = percentage_recalculation(
                            numerator, denominator, reported, len(reported.partition(".")[2])
                        )
                    except ValueError:
                        skipped_unscoped += 1
                        continue
                    header_sources = _denominator_facts(
                        ("column_header", n) for n in headers.get(idx, [])
                    )
                    reported_in_header = sorted({f["value"] for f in header_sources})
                    result = {
                        "table_id": name,
                        "table_index": table_count,
                        "section_label": label[:MAX_PROPOSAL_QUOTE],
                        "row_label": row_label[:MAX_PROPOSAL_QUOTE],
                        "source_sha256": source_sha,
                        "numerator": numerator,
                        "proposed_denominator": denominator,
                        "reported_percent": reported,
                        "expected_at_printed_precision": calculation["rounded_percent"],
                        "arithmetic_status_if_section_n_applies": (
                            "conditional_match" if calculation["arithmetic_matches"]
                            else "conditional_mismatch"
                        ),
                        "column_header_denominators": reported_in_header,
                        "conflicting_header": bool(reported_in_header and
                                                   reported_in_header != [denominator]),
                        "source_evidence": {
                            "cell": _evidence(cell, "source_cell", _text(cell)),
                            "row_label": _evidence(cells[0], "explicit_row_n_percent", row_label),
                            "section_label": _evidence(marker_cells[0], "population_section", label),
                            "section_denominator": _evidence(
                                marker_cells[idx], "same_column_section_n", _text(marker_cells[idx])
                            ),
                            "older_header_denominators": header_sources,
                        },
                        "scientific_error_established": False,
                        "scope_adjudicated": False,
                    }
                    results.append(result)
                    if len(results) > MAX_RESULTS:
                        raise JATSSourceError("Too many section denominator proposals")
    return {
        "schema_version": "rw-jats-section-denominator-hypotheses.v1",
        "source_sha256": source_sha,
        "representation_authenticated": False,
        "scientific_error_established": False,
        "changes_to_existing_audit": False,
        "tables_seen": table_count,
        "section_headers_seen": section_count,
        "conditional_pairs": len(results),
        "conditional_mismatch_count": sum(
            r["arithmetic_status_if_section_n_applies"] == "conditional_mismatch"
            for r in results
        ),
        "unscoped_rows_skipped": skipped_unscoped,
        "limitations": [
            "Only sections with explicit per-column N and rows explicitly labeled n (%) are reviewed.",
            "Section N may not be the applicable percentage denominator (missingness, subgroup, methods).",
            "Conflicting older headers are exposed, never overwritten or adjudicated.",
            "A mismatch is conditional arithmetic, not a scientific error or independent benchmark finding.",
            "Publisher origin, byte history, scientific scope and full-paper coverage are not established.",
        ],
        "proposals": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        source = read_regular(args.source, MAX_SOURCE_BYTES)
        actual = hashlib.sha256(source).hexdigest()
        if actual != args.expected_source_sha256:
            raise ValueError("Input SHA-256 does not match externally supplied pin")
        print(json.dumps(review_section_denominators(source), indent=2, sort_keys=True))
    except (ValueError, OSError) as exc:
        print(f"section-review: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
