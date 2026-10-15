"""Conservative, offline arithmetic review of percentages in JATS tables.

This evidence-extraction aid sits outside the trusted ResearchWitness core. It
does not parse PDFs, authenticate a source, decide whether a paper is in error,
or resolve table scope when the document leaves it unclear.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
from xml.parsers import expat

from tools.public_discovery import percentage_recalculation
from tools.offline_files import read_regular

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_XML_NODES = 100_000
MAX_XML_DEPTH = 256
MAX_TABLES = 512
MAX_ROWS = 20_000
MAX_CELLS = 100_000
MAX_RESULTS = 1_000
MAX_ADJUSTMENT_NOTES = 8
MAX_EVIDENCE_TEXT = 500
MAX_LAYOUT_COLUMNS = 256
MAX_LAYOUT_SLOTS = MAX_CELLS
MAX_CELL_COMPONENTS = 8
MAX_ARTICLE_GROUP_POPULATIONS = 64

_INTEGER_TOKEN = r"(?:[0-9]{1,3}(?:,[0-9]{3}){1,2}|[0-9]{1,9})"
_COUNT_PERCENT_RE = re.compile(
    rf"^\s*(?P<count>{_INTEGER_TOKEN})\s*\(\s*"
    r"(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<symbol>%?)\s*\)\s*$"
)
_COUNT_RATIO_PERCENT_RE = re.compile(
    rf"^\s*(?P<count>{_INTEGER_TOKEN})\s*/\s*(?P<denominator>{_INTEGER_TOKEN})"
    r"\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<symbol>%?)\s*\)"
    r"\s*(?:[*#†‡]+)?\s*$"
)
_PERCENT_ONLY_RE = re.compile(
    r"^\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*%?\s*$"
)
_COUNT_ONLY_RE = re.compile(rf"^\s*(?P<count>{_INTEGER_TOKEN})\s*$")
_DENOMINATOR_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:n|N)\s*[=:]\s*(?P<value>{_INTEGER_TOKEN})(?![0-9]|[,.][0-9])"
)
_GROUP_POPULATION_RE = re.compile(
    rf"(?P<label>(?:[A-Za-z][A-Za-z0-9'’_-]*\s+){{0,3}}(?:group|arm))"
    rf"\s*\(\s*(?:n|N)\s*[=:]\s*(?P<value>{_INTEGER_TOKEN})\s*\)",
    re.IGNORECASE,
)
_HEADER_CUE_RE = re.compile(
    r"\b(?:parameter|variable|characteristic|value|count|number|frequency|percent(?:age)?)\b|"
    r"\bno(?:\.|\b)",
    re.IGNORECASE,
)
_PERCENT_CONTEXT_RE = re.compile(
    r"\bn\s*\(\s*%|\(\s*%\s*\)|\bpercent(?:age)?s?\b", re.IGNORECASE
)
_EXPLICIT_PERCENT_BASIS_RE = re.compile(
    r"\bpercent(?:age)?s?\b.{0,100}\b(?:denominator|based on|full cohort|entire cohort)\b|"
    r"\b(?:denominator|full cohort|entire cohort)\b.{0,100}\bpercent(?:age)?s?\b",
    re.IGNORECASE,
)
_EXPLICIT_PERCENT_OF_TOTAL_RE = re.compile(
    r"\bof\s+(?:the\s+)?(?:total|all)\s+[A-Za-z][A-Za-z0-9 /_-]{0,80}"
    r"\(\s*%\s*\)",
    re.IGNORECASE,
)
_FULL_WIDTH_TOTAL_ROW_RE = re.compile(
    rf"^\s*(?:(?:grand|overall)\s+)?total\s*[:=\-]?\s*"
    rf"(?P<count>{_INTEGER_TOKEN})\s*\(\s*100(?:\.0+)?\s*%\s*\)\s*$",
    re.IGNORECASE,
)
_ROW_GROUP_PERCENT_RE = re.compile(r"\bn\s*\(\s*%", re.IGNORECASE)
_ROW_SPECIFIC_RATIO_RE = re.compile(
    r"\bn\s*\(\s*%\s*[^)]*\bn\s*/\s*n\b", re.IGNORECASE
)
_ROUNDING_NOTE_RE = re.compile(
    r"\b(?:rounded|rounding|round\s+(?:to|up|down|off|(?:all\s+)?percent(?:age)?s?)|truncat(?:e|ed|ion))\b",
    re.IGNORECASE,
)
_CONTINUOUS_RE = re.compile(r"\b(?:mean|median|SD|IQR|standard deviation)\b", re.IGNORECASE)
_MISSING_RE = re.compile(r"^(?:missing|unknown|not available|not reported|not known)\b", re.IGNORECASE)
_COMPONENT_RE = re.compile(
    rf"(?P<label>[A-Za-z][A-Za-z _:.-]{{0,39}}?)\s*"
    rf"(?P<numeric>(?P<count>{_INTEGER_TOKEN})\s*\(\s*"
    r"(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*%\s*\))"
)
_ADJUSTMENT_NOTE_RE = re.compile(
    r"(?:\b(?:adjusted|weighted|standardized|standardised)\b.{0,120}"
    r"\b(?:percent(?:age)?s?|frequenc(?:y|ies)|proportions?|rates?)\b|"
    r"\b(?:percent(?:age)?s?|frequenc(?:y|ies)|proportions?|rates?)\b.{0,120}"
    r"\b(?:adjusted|weighted|standardized|standardised)\b)",
    re.IGNORECASE,
)
_DECLARATION_RE = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_BLOCK_TEXT_ELEMENTS = frozenset({
    "p", "label", "caption", "fn", "table-wrap-foot", "td", "th", "tr",
    "thead", "tbody", "tfoot", "list-item",
})


class JATSSourceError(ValueError):
    """The input is unsupported, malformed, or outside the parser's limits."""


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    byte_start: int
    start_tag_end: int
    byte_end: int = 0
    parts: list[str | "_Node"] = field(default_factory=list)
    children: list["_Node"] = field(default_factory=list)


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _tag_end(data: bytes, start: int) -> int:
    quote: int | None = None
    for index in range(start, len(data)):
        value = data[index]
        if quote is not None:
            if value == quote:
                quote = None
        elif value in (ord("'"), ord('"')):
            quote = value
        elif value == ord(">"):
            return index + 1
    raise JATSSourceError("XML tag has no closing bracket")


def _parse_jats(data: bytes) -> _Node:
    if not isinstance(data, bytes):
        raise JATSSourceError("JATS source must be supplied as bytes")
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise JATSSourceError("JATS source is empty or exceeds the 8 MiB limit")
    if b"\x00" in data or data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise JATSSourceError("Only UTF-8 XML is supported")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JATSSourceError("Only UTF-8 XML is supported") from exc
    if _DECLARATION_RE.search(data):
        raise JATSSourceError("DOCTYPE and ENTITY declarations are not accepted")

    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    stack: list[_Node] = []
    roots: list[_Node] = []
    node_count = 0

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_XML_NODES:
            raise JATSSourceError("JATS XML exceeds the element-count limit")
        if len(stack) >= MAX_XML_DEPTH:
            raise JATSSourceError("JATS XML exceeds the nesting-depth limit")
        start_index = parser.CurrentByteIndex
        node = _Node(name, dict(attrs), start_index, _tag_end(data, start_index))
        if stack:
            stack[-1].children.append(node)
            stack[-1].parts.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def end(_name: str) -> None:
        if not stack:
            raise JATSSourceError("Malformed JATS element nesting")
        node = stack.pop()
        close_index = parser.CurrentByteIndex
        if data[close_index:close_index + 2] == b"</":
            node.byte_end = _tag_end(data, close_index)
        else:  # Expat reports the byte after a self-closing start tag.
            node.byte_end = node.start_tag_end

    def character_data(value: str) -> None:
        if stack:
            stack[-1].parts.append(value)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = character_data
    parser.ExternalEntityRefHandler = lambda *_args: 0
    try:
        parser.Parse(data, True)
    except JATSSourceError:
        raise
    except expat.ExpatError as exc:
        raise JATSSourceError("Input is not well-formed JATS XML") from exc
    if stack or len(roots) != 1:
        raise JATSSourceError("JATS XML must have one complete document root")
    if _local_name(roots[0].tag) != "article":
        raise JATSSourceError("JATS input must have an article root")
    return roots[0]


def _text(node: _Node) -> str:
    pieces: list[str] = []
    for part in node.parts:
        if isinstance(part, _Node):
            child_text = _text(part)
            if _local_name(part.tag) in _BLOCK_TEXT_ELEMENTS:
                pieces.append(f" {child_text} ")
            else:
                pieces.append(child_text)
        else:
            pieces.append(part)
    return " ".join("".join(pieces).split())


def _descendants(node: _Node, name: str) -> Iterable[_Node]:
    for child in node.children:
        if _local_name(child.tag) == name:
            yield child
        yield from _descendants(child, name)


def _attribute(node: _Node, name: str) -> str | None:
    for key, value in node.attrs.items():
        if _local_name(key) == name:
            return value
    return None


def _cells(row: _Node) -> list[_Node]:
    return [child for child in row.children if _local_name(child.tag) in {"td", "th"}]


def _span(node: _Node, attribute: str) -> int | None:
    value = _attribute(node, attribute)
    if value is None:
        return 1
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if 1 <= parsed <= 64 else None


def _layout_rows(rows: list[_Node], *, header: bool = False):
    """Map explicit spans without guessing missing cells or allocating an unbounded grid."""
    grid: dict[tuple[int, int], _Node] = {}
    layouts: list[tuple[list[int], bool]] = []
    malformed = False
    for row_index, row in enumerate(rows):
        column = 0
        positions: list[int] = []
        supported = True
        for cell in _cells(row):
            while (row_index, column) in grid:
                column += 1
            positions.append(column)
            colspan, rowspan = _span(cell, "colspan"), _span(cell, "rowspan")
            if column + (colspan or 1) > MAX_LAYOUT_COLUMNS:
                raise JATSSourceError("JATS table exceeds the column-count limit")
            if (colspan is None or rowspan is None or row_index + (rowspan or 1) > len(rows)):
                malformed = True
                supported = False
                colspan = rowspan = 1
            assert colspan is not None and rowspan is not None
            text = _text(cell)
            numeric = bool(_COUNT_PERCENT_RE.fullmatch(text) or _COUNT_RATIO_PERCENT_RE.fullmatch(text)
                           or _PERCENT_ONLY_RE.fullmatch(text))
            if not header and numeric and (colspan != 1 or rowspan != 1):
                supported = False
            for r in range(row_index, row_index + rowspan):
                for c in range(column, column + colspan):
                    if (r, c) in grid:
                        malformed = True
                        supported = False
                    grid[r, c] = cell
                    if len(grid) > MAX_LAYOUT_SLOTS:
                        raise JATSSourceError("JATS table exceeds the expanded-layout limit")
            column += colspan
        layouts.append((positions, supported))
    width = max((c + 1 for _r, c in grid), default=0)
    if header and any((r, c) not in grid for r in range(len(rows)) for c in range(width)):
        malformed = True
    return grid, layouts, malformed


def _header_columns(header_rows: list[_Node]) -> tuple[dict[int, list[_Node]], bool, bool]:
    grid, _layouts, unsupported = _layout_rows(header_rows, header=True)
    columns: dict[int, list[_Node]] = {}
    for (row, column), cell in sorted(grid.items()):
        if not any(existing is cell for existing in columns.setdefault(column, [])):
            columns[column].append(cell)
    has_denominator = any(_DENOMINATOR_RE.search(_text(c)) for row in header_rows for c in _cells(row))
    return columns, unsupported, has_denominator


def _fragments(text: str) -> list[dict[str, Any] | None]:
    """Recognize a bounded list of explicitly labeled percentages in one cell."""
    matches = []
    for match in _COMPONENT_RE.finditer(text):
        matches.append(match)
        if len(matches) > MAX_CELL_COMPONENTS:
            return [None]
    if not 2 <= len(matches) <= MAX_CELL_COMPONENTS:
        return [None]
    end = 0
    for match in matches:
        if text[end:match.start()].strip(" ;,|\t\r\n"):
            return [None]
        end = match.end()
    if text[end:].strip(" ;,|\t\r\n") or len({m.group("label").strip() for m in matches}) != len(matches):
        return [None]
    return [{"numeric_quote": m.group("numeric"), "label": m.group("label").strip(),
             "character_start": m.start(), "character_end": m.end()} for m in matches]


def _group_marker(row: _Node) -> tuple[str, _Node] | None:
    cells = _cells(row)
    nonempty = [(cell, _text(cell)) for cell in cells if _text(cell)]
    if len(nonempty) != 1:
        return None
    cell, text = nonempty[0]
    if _COUNT_PERCENT_RE.fullmatch(text) or _COUNT_RATIO_PERCENT_RE.fullmatch(text) or _PERCENT_ONLY_RE.fullmatch(text):
        return None
    if len(cells) > 1 or (_span(cell, "colspan") or 1) > 1 or _DENOMINATOR_RE.search(text) or _ROW_GROUP_PERCENT_RE.search(text):
        return text, cell
    return None


def _adjustment_targets(node: _Node, wrapper_ids: set[str | None]) -> set[str]:
    """Only a narrow, exhaustive table-specific statement can narrow document scope."""
    refs = [xref for xref in _descendants(node, "xref") if _attribute(xref, "ref-type") == "table"]
    if len(refs) != 1:
        return set()
    targets = set((_attribute(refs[0], "rid") or "").split())
    if len(targets) != 1 or not targets.issubset(wrapper_ids):
        return set()
    reference = re.escape(_text(refs[0]))
    statement = (r"(?:The\s+)?(?:weighted|adjusted|standardized|standardised)\s+percentages?\s+"
                 r"(?:appear|are\s+(?:shown|reported|presented|used))\s+(?:only\s+)?in\s+"
                 + reference + r"\s*[.]?")
    return targets if re.fullmatch(statement, _text(node), re.IGNORECASE) else set()


def _evidence(node: _Node, role: str, quote: str) -> dict[str, Any]:
    return {
        "role": role,
        "byte_start": node.byte_start,
        "byte_end": node.byte_end,
        "quote": quote[:MAX_EVIDENCE_TEXT],
        "quote_truncated": len(quote) > MAX_EVIDENCE_TEXT,
    }


def _population_label_words(value: str) -> tuple[str, ...]:
    """Normalize a short named study group without guessing synonyms."""
    ignored = {"a", "an", "and", "for", "in", "of", "the", "to"}
    words = []
    for word in re.findall(r"[a-z0-9]+", value.casefold()):
        if word in ignored:
            continue
        # JATS sources commonly alternate "intervention" and
        # "interventional" for the same arm. No other stemming is applied.
        words.append("intervention" if word == "interventional" else word)
    return tuple(words)


def _article_group_populations(root: _Node) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    """Collect exact, source-anchored group n statements outside table markup.

    These statements are available only as conditional arithmetic context. A
    table must name the same group, and the value never becomes an asserted
    denominator: article-level allocation can differ from a table's analysis
    population after missingness or follow-up.
    """
    populations: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    seen = 0

    def walk(node: _Node, inside_table: bool = False) -> None:
        nonlocal seen
        inside_table = inside_table or _local_name(node.tag) == "table-wrap"
        if not inside_table and _local_name(node.tag) == "p":
            quote = _text(node)
            for match in _GROUP_POPULATION_RE.finditer(quote):
                seen += 1
                if seen > MAX_ARTICLE_GROUP_POPULATIONS:
                    populations.clear()
                    return
                label = _population_label_words(match.group("label"))
                if not label:
                    continue
                populations.setdefault(label, []).append({
                    "value": int(match.group("value").replace(",", "")),
                    "label": " ".join(label),
                    "evidence": _evidence(node, "article_group_population", quote),
                })
        for child in node.children:
            walk(child, inside_table)
            if seen > MAX_ARTICLE_GROUP_POPULATIONS:
                return

    body_nodes = list(_descendants(root, "body"))
    for body in body_nodes or [root]:
        walk(body)
    return populations


def _group_population_match(
    populations: dict[tuple[str, ...], list[dict[str, Any]]],
    header_nodes: list[_Node],
    table_context_nodes: list[_Node],
) -> dict[str, Any] | None:
    """Map a table or column's explicit group label to one article n statement."""
    def matches(nodes: list[_Node]) -> list[tuple[tuple[str, ...], list[dict[str, Any]], _Node]]:
        found = []
        for label, facts in populations.items():
            if not label:
                continue
            for node in nodes:
                context = _population_label_words(_text(node))
                width = len(label)
                if any(context[start:start + width] == label
                       for start in range(max(0, len(context) - width + 1))):
                    found.append((label, facts, node))
                    break
        return found

    # A per-column label is narrower than a table title and takes priority.
    found = matches(header_nodes) or matches(table_context_nodes)
    if len(found) != 1:
        return None
    label, facts, table_node = found[0]
    values = {fact["value"] for fact in facts}
    if len(values) != 1:
        return {"status": "conflicting", "label": " ".join(label),
                "facts": facts, "table_node": table_node}
    return {"status": "matched", "label": " ".join(label),
            "value": next(iter(values)), "fact": facts[0], "table_node": table_node}


def _denominator_facts(nodes: Iterable[tuple[str, _Node]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for role, node in nodes:
        quote = _text(node)
        for match in _DENOMINATOR_RE.finditer(quote):
            facts.append({
                "value": int(match.group("value").replace(",", "")),
                "evidence": _evidence(node, role, quote),
            })
    return facts


def _unique_values(facts: list[dict[str, Any]]) -> set[int]:
    return {fact["value"] for fact in facts}


def _cell_column_positions(cells: list[_Node]) -> tuple[list[int], bool]:
    positions: list[int] = []
    column = 0
    for cell in cells:
        span = _span(cell, "colspan")
        if span is None or span != 1:
            positions.append(column)
            return positions, False
        positions.append(column)
        column += span
    return positions, True


def _is_count_header(nodes: list[_Node]) -> bool:
    for node in nodes:
        text = _text(node).strip()
        if text == "n" or text.casefold() in {"no", "no.", "frequency", "frequencies"}:
            return True
        if re.search(r"\b(?:count|number|frequency)\b", text, re.IGNORECASE):
            return True
        # Uppercase N is a count only when its header spells out that role.
        # A bare N remains a denominator cue in _is_denominator_header.
        if re.fullmatch(
            r"N\s*(?:\(\s*(?:count|numerator|frequency)\s*\)|"
            r"[,:\-]\s*(?:count|numerator|frequency))",
            text,
            re.IGNORECASE,
        ):
            return True
        if re.fullmatch(
            r"N\s+of\s+(?:patients|participants|subjects|cases|admissions|respondents)",
            text,
            re.IGNORECASE,
        ):
            return True
    return False


def _is_denominator_header(nodes: list[_Node]) -> bool:
    return any(
        _text(node).strip() == "N"
        or re.fullmatch(r"(?:denominator|total\s+N)", _text(node).strip(), re.IGNORECASE)
        for node in nodes
    )


def _candidate_from_cell(
    *,
    source_sha256: str,
    table_id: str,
    table_index: int,
    row_index: int,
    cell_index: int,
    column: int,
    cell: _Node,
    cells: list[_Node],
    header_columns: dict[int, list[_Node]],
    header_layout_unsupported: bool,
    data_cell_layout_unsupported: bool,
    global_facts: list[dict[str, Any]],
    table_percentage_context: bool,
    row_group_context: tuple[str, _Node] | None,
    row_specific_denominator_context: bool,
    adjustment_notes: list[dict[str, Any]],
    rounding_note: str | None,
    fragment: dict[str, Any] | None = None,
    missing_scope_note: _Node | None = None,
    total_header_facts: list[dict[str, Any]] | None = None,
    inherited_row_labels: list[_Node] | None = None,
    explicit_table_percentage_basis: bool = False,
    article_group_populations: dict[tuple[str, ...], list[dict[str, Any]]] | None = None,
    table_population_context_nodes: list[_Node] | None = None,
) -> dict[str, Any] | None:
    cell_quote = _text(cell)
    parse_quote = fragment["numeric_quote"] if fragment else cell_quote
    count_ratio = _COUNT_RATIO_PERCENT_RE.fullmatch(parse_quote)
    combined = _COUNT_PERCENT_RE.fullmatch(parse_quote)
    ratio_denominator: int | None = None
    if count_ratio:
        count_text = count_ratio.group("count")
        percent_text = count_ratio.group("percent")
        has_percent_symbol = bool(count_ratio.group("symbol"))
        ratio_denominator = int(count_ratio.group("denominator").replace(",", ""))
        count_evidence: dict[str, Any] | None = None
    elif combined:
        count_text = combined.group("count")
        percent_text = combined.group("percent")
        has_percent_symbol = bool(combined.group("symbol"))
        count_evidence: dict[str, Any] | None = None
    else:
        count_text = percent_text = ""
        has_percent_symbol = False
        count_evidence = None

    header_nodes = list(header_columns.get(column, []))
    header_texts = [_text(node) for node in header_nodes]
    row_explicit_denominator: int | None = None
    row_denominator_evidence: dict[str, Any] | None = None
    row_denominator_header_evidence: list[dict[str, Any]] = []
    row_denominator_cell_evidence: dict[str, Any] | None = None
    row_denominator_missing = False
    if not combined and not count_ratio:
        # Separate count and percent columns are considered only when their
        # headers name each role; all other layouts abstain instead of guessing.
        percent_only = _PERCENT_ONLY_RE.fullmatch(cell_quote)
        positions, positions_supported = _cell_column_positions(cells)
        if not percent_only or not positions_supported or cell_index == 0:
            return None
        previous = cells[cell_index - 1]
        previous_column = column - 1
        previous_header_nodes = header_columns.get(previous_column, [])
        current_header = " ".join(header_texts)
        has_percent_header = bool(re.search(r"%|percent(?:age)?", current_header, re.IGNORECASE))
        if not has_percent_header:
            return None
        numerator_cell: _Node | None = None
        numerator_header_nodes: list[_Node] = []
        if cell_index >= 2:
            possible_count_cell = cells[cell_index - 2]
            possible_count_headers = header_columns.get(column - 2, [])
            has_row_n_and_N_columns = (
                _is_count_header(possible_count_headers)
                and _is_denominator_header(previous_header_nodes)
            )
            if has_row_n_and_N_columns:
                count_match = _COUNT_ONLY_RE.fullmatch(_text(possible_count_cell))
                denominator_match = _COUNT_ONLY_RE.fullmatch(_text(previous))
                if not count_match:
                    return None
                numerator_cell = possible_count_cell
                numerator_header_nodes = list(possible_count_headers)
                count_text = count_match.group("count")
                row_denominator_header_evidence = [
                    _evidence(item, "row_denominator_header", _text(item))
                    for item in previous_header_nodes
                ]
                row_denominator_cell_evidence = _evidence(
                    previous, "row_denominator_cell", _text(previous)
                )
                if denominator_match:
                    row_explicit_denominator = int(
                        denominator_match.group("count").replace(",", "")
                    )
                    row_denominator_evidence = row_denominator_cell_evidence
                else:
                    row_denominator_missing = True
                header_nodes = numerator_header_nodes + list(previous_header_nodes) + header_nodes
                header_texts = [_text(node) for node in header_nodes]
        if numerator_cell is None:
            previous_count = _COUNT_ONLY_RE.fullmatch(_text(previous))
            if not previous_count or not _is_count_header(previous_header_nodes):
                return None
            count_text = previous_count.group("count")
            numerator_cell = previous
            header_nodes = list(previous_header_nodes) + header_nodes
            header_texts = [_text(node) for node in header_nodes]
        percent_text = percent_only.group("percent")
        has_percent_symbol = True
        count_evidence = _evidence(numerator_cell, "count_cell", _text(numerator_cell))

    percentage_context = (
        has_percent_symbol
        or table_percentage_context
        or bool(row_group_context and _PERCENT_CONTEXT_RE.search(row_group_context[0]))
        or bool(_PERCENT_CONTEXT_RE.search(" ".join(header_texts)))
        or any(text.strip() == "%" for text in header_texts)
    )
    header_facts = _denominator_facts(("column_header", node) for node in header_nodes)
    row_label_nodes = [node for index, node in enumerate(cells) if index != cell_index]
    row_label_nodes.extend(inherited_row_labels or [])
    row_facts = _denominator_facts(("row_context", node) for node in row_label_nodes)
    group_facts = (
        _denominator_facts([("row_group_context", row_group_context[1])])
        if row_group_context else []
    )
    header_values = _unique_values(header_facts)
    global_values = _unique_values(global_facts)
    group_values = _unique_values(group_facts)
    type_ambiguous = not percentage_context
    if type_ambiguous and (
        not combined or not header_facts
        or _CONTINUOUS_RE.search(" ".join(header_texts + [_text(n) for n in row_label_nodes]))
    ):
        return None

    denominator: int | None = None
    denominator_scope: str | None = None
    ambiguity: str | None = None
    if ratio_denominator is not None:
        denominator = ratio_denominator
        denominator_scope = "cell_ratio"
    elif header_layout_unsupported:
        ambiguity = "unsupported_header_spans"
    elif data_cell_layout_unsupported:
        ambiguity = "unsupported_data_cell_spans"
    elif row_explicit_denominator is not None:
        denominator = row_explicit_denominator
        denominator_scope = "row_denominator_column"
    elif group_values and header_values and group_values != header_values:
        ambiguity = "row_group_column_denominator_conflict"
    elif len(group_values) == 1:
        denominator = next(iter(group_values))
        denominator_scope = "row_group"
    elif len(group_values) > 1:
        ambiguity = "conflicting_row_group_denominators"
    elif len(header_values) > 1:
        ambiguity = "conflicting_column_denominators"
    elif header_values:
        denominator = next(iter(header_values))
        denominator_scope = "column_header"
    elif len(global_values) > 1:
        ambiguity = "multiple_unscoped_table_denominators"
    elif global_values:
        denominator = next(iter(global_values))
        denominator_scope = (
            "table_total_row"
            if any(
                fact["value"] == denominator
                and fact["evidence"]["role"] == "table_total_row"
                for fact in global_facts
            )
            else "table_caption_or_footnote"
        )
    else:
        ambiguity = "no_explicit_denominator"

    if (explicit_table_percentage_basis and global_values and denominator is not None
            and global_values != {denominator}):
        ambiguity = "conflicting_explicit_table_percentage_basis"
        denominator = None
        denominator_scope = None

    if ratio_denominator is None and (
        (row_specific_denominator_context or row_denominator_missing)
        and row_explicit_denominator is None
    ):
        ambiguity = "row_specific_denominator_not_reported"
        denominator = None
        denominator_scope = None
    if adjustment_notes:
        ambiguity = "adjustment_method_scope_not_mapped"
        denominator = None
        denominator_scope = None
    if (ratio_denominator is None and row_explicit_denominator is None
            and header_values and total_header_facts
            and header_values != _unique_values(total_header_facts)):
        ambiguity = "cross_tab_denominator_scope_unclear"
        denominator = None
        denominator_scope = None
    if ratio_denominator is None and row_facts:
        row_values = _unique_values(row_facts)
        if len(row_values) > 1 or denominator is None or row_values != {denominator}:
            if ambiguity is None:
                ambiguity = "row_level_denominator_scope_unclear"
            denominator = None
            denominator_scope = None
    if ratio_denominator is None and group_facts:
        if len(group_values) > 1 or denominator is None or group_values != {denominator}:
            if ambiguity is None:
                ambiguity = "row_group_denominator_scope_unclear"
            denominator = None
            denominator_scope = None
    if type_ambiguous:
        ambiguity = "percentage_context_not_explicit"
        denominator = None
        denominator_scope = None
    conditional_calculation = None
    if (missing_scope_note is not None and ratio_denominator is None
            and row_explicit_denominator is None and ambiguity is None):
        if denominator is not None and not rounding_note:
            try:
                conditional_calculation = percentage_recalculation(
                    int(count_text.replace(",", "")), denominator, percent_text,
                    len(percent_text.partition(".")[2]),
                )
                conditional_calculation["denominator"] = denominator
                conditional_calculation["assumption"] = "displayed_denominator_applies_to_missing_data_group"
            except ValueError:
                pass
        ambiguity = "missing_data_denominator_scope_unclear"
        denominator = None
        denominator_scope = None

    population_match = _group_population_match(
        article_group_populations or {}, header_nodes,
        table_population_context_nodes or [],
    )
    if (conditional_calculation is None and denominator is None
            and ambiguity == "no_explicit_denominator"
            and population_match and population_match["status"] == "matched"
            and not rounding_note):
        try:
            conditional_calculation = percentage_recalculation(
                int(count_text.replace(",", "")), population_match["value"], percent_text,
                len(percent_text.partition(".")[2]),
            )
            conditional_calculation["denominator"] = population_match["value"]
            conditional_calculation["assumption"] = "matched_article_group_sample_size_may_apply_to_table"
            conditional_calculation["population_group"] = population_match["label"]
            conditional_calculation["evidence"] = {
                "group_population": population_match["fact"]["evidence"],
                "table_population_context": _evidence(
                    population_match["table_node"], "table_population_group_context",
                    _text(population_match["table_node"]),
                ),
            }
        except ValueError:
            pass

    evidence = {
        "source_sha256": source_sha256,
        "table_id": table_id,
        "table_index": table_index,
        "row_index": row_index,
        "cell_index": cell_index + 1,
        "byte_start": cell.byte_start,
        "byte_end": cell.byte_end,
        "cell_quote": cell_quote[:MAX_EVIDENCE_TEXT],
        "cell_quote_truncated": len(cell_quote) > MAX_EVIDENCE_TEXT,
        "row_context": " | ".join(_text(node) for node in row_label_nodes)[:MAX_EVIDENCE_TEXT],
        "column_headers": [text[:MAX_EVIDENCE_TEXT] for text in header_texts],
        "denominator_sources": header_facts + global_facts + group_facts + row_facts,
        "normalized_character_start": fragment["character_start"] if fragment else 0,
        "normalized_character_end": fragment["character_end"] if fragment else len(cell_quote),
    }
    if fragment:
        evidence["component_label"] = fragment["label"]
        evidence["relationship_quote"] = cell_quote[fragment["character_start"]:fragment["character_end"]]
    if missing_scope_note is not None:
        evidence["missing_data_scope_note"] = _evidence(missing_scope_note, "missing_data_row", _text(missing_scope_note))
    if total_header_facts:
        evidence["cross_tab_total_sources"] = total_header_facts
    if population_match and population_match["status"] == "conflicting":
        evidence["article_group_population_conflicts"] = [
            {"value": fact["value"], "evidence": fact["evidence"]}
            for fact in population_match["facts"]
        ]
    if ratio_denominator is not None:
        evidence["denominator_sources"].append({
            "value": ratio_denominator,
            "evidence": _evidence(cell, "cell_ratio_denominator", cell_quote),
        })
    if row_denominator_evidence is not None:
        evidence["denominator_sources"].append({
            "value": row_explicit_denominator,
            "evidence": row_denominator_evidence,
        })
    if row_denominator_header_evidence:
        evidence["row_denominator_header"] = row_denominator_header_evidence
    if row_denominator_cell_evidence is not None:
        evidence["row_denominator_cell"] = row_denominator_cell_evidence
    if row_group_context:
        evidence["row_group_context"] = _evidence(
            row_group_context[1], "row_group_context", row_group_context[0]
        )
    if adjustment_notes:
        evidence["adjustment_notes"] = adjustment_notes
    if count_evidence is not None:
        evidence["count_evidence"] = count_evidence
    result: dict[str, Any] = {
        "status": "scope_ambiguous",
        "reason": ambiguity,
        "numerator": int(count_text.replace(",", "")),
        "denominator": denominator,
        "denominator_scope": denominator_scope,
        "reported_percent": percent_text,
        "contract_expected_percent": None,
        "exact_ratio_percent": None,
        "display_precision": len(percent_text.partition(".")[2]),
        "evidence": evidence,
    }
    if conditional_calculation is not None:
        result["conditional_calculation"] = conditional_calculation
    if ambiguity:
        return result
    if denominator is None:
        result.update(status="scope_ambiguous", reason="no_explicit_denominator")
        return result
    if denominator <= 0:
        result.update(status="scope_ambiguous", reason="nonpositive_denominator", denominator=None)
        return result
    if rounding_note:
        result.update(status="rounding_ambiguous", reason="source_rounding_convention_not_modeled")
        result["evidence"]["rounding_note"] = rounding_note[:MAX_EVIDENCE_TEXT]
        return result
    try:
        arithmetic = percentage_recalculation(
            int(count_text.replace(",", "")),
            denominator,
            percent_text,
            len(percent_text.partition(".")[2]),
        )
    except ValueError as exc:
        result.update(status="scope_ambiguous", reason="invalid_or_unsupported_ratio")
        result["evidence"]["arithmetic_input_note"] = str(exc)
        return result
    result["contract_expected_percent"] = arithmetic["rounded_percent"]
    result["exact_ratio_percent"] = arithmetic["exact_ratio_percent"]
    result["status"] = (
        "arithmetic_match" if arithmetic["arithmetic_matches"]
        else "arithmetic_mismatch_candidate"
    )
    result["reason"] = None
    return result


def audit_jats_percentage_tables(data: bytes) -> dict[str, Any]:
    """Return source-anchored arithmetic candidates from one UTF-8 JATS file."""
    root = _parse_jats(data)
    source_sha256 = hashlib.sha256(data).hexdigest()
    wrappers = list(_descendants(root, "table-wrap"))
    if len(wrappers) > MAX_TABLES:
        raise JATSSourceError("JATS source exceeds the table-count limit")

    article_group_populations = _article_group_populations(root)
    adjustment_notes: list[tuple[dict[str, Any], set[str]]] = []
    wrapper_ids = {_attribute(w, "id") for w in wrappers if _attribute(w, "id")}
    method_scope_overflow = False

    def scan_methods(node: _Node, inside_table: bool = False) -> None:
        nonlocal method_scope_overflow
        inside_table = inside_table or _local_name(node.tag) == "table-wrap"
        if not inside_table and _local_name(node.tag) == "p":
            quote = _text(node)
            if _ADJUSTMENT_NOTE_RE.search(quote):
                targets = _adjustment_targets(node, wrapper_ids)
                if len(adjustment_notes) < MAX_ADJUSTMENT_NOTES:
                    note = _evidence(node, "document_method", quote)
                    note["target_table_ids"] = sorted(targets)
                    adjustment_notes.append((note, targets))
                else:
                    method_scope_overflow = True
        for child in node.children:
            scan_methods(child, inside_table)

    scan_methods(root)

    results: list[dict[str, Any]] = []
    rows_seen = cells_seen = tables_inspected = 0
    for wrapper in wrappers:
        tables = list(_descendants(wrapper, "table"))
        if not tables:
            continue
        label_node = next(iter(_descendants(wrapper, "label")), None)
        caption_node = next(iter(_descendants(wrapper, "caption")), None)
        foot_nodes = list(_descendants(wrapper, "table-wrap-foot"))
        for table in tables:
            tables_inspected += 1
            if tables_inspected > MAX_TABLES:
                raise JATSSourceError("JATS source exceeds the table-count limit")
            raw_table_id = _attribute(wrapper, "id") or f"table-{tables_inspected}"
            table_id = raw_table_id[:100]
            global_nodes: list[tuple[str, _Node]] = []
            if label_node is not None:
                global_nodes.append(("table_label", label_node))
            if caption_node is not None:
                global_nodes.append(("table_caption", caption_node))
            global_nodes.extend(("table_footnote", node) for node in foot_nodes)
            global_facts = _denominator_facts(global_nodes)

            thead_sections = list(_descendants(table, "thead"))
            header_rows = [row for section in thead_sections for row in _descendants(section, "tr")]
            all_rows = list(_descendants(table, "tr"))
            if not header_rows and all_rows:
                first_cells = _cells(all_rows[0])
                first_text = " ".join(_text(cell) for cell in first_cells)
                has_header_shape = (
                    first_cells
                    and all(_local_name(cell.tag) == "th" for cell in first_cells)
                )
                has_unmarked_header = (
                    len(first_cells) >= 2
                    and all(_text(cell) for cell in first_cells)
                    and bool(_HEADER_CUE_RE.search(first_text))
                    and not any(_COUNT_PERCENT_RE.fullmatch(_text(cell)) for cell in first_cells)
                )
                if has_header_shape or has_unmarked_header:
                    header_rows = [all_rows[0]]
            header_columns, header_layout_unsupported, _header_has_denominator = _header_columns(header_rows)
            total_header_nodes = {id(node): node for nodes in header_columns.values() for node in nodes
                                  if re.search(r"\b(?:no\.? of patients|number of patients|total(?: patients| participants| population)?|all participants)\b", _text(node), re.IGNORECASE)}
            total_header_facts = _denominator_facts(("total_population_header", node) for node in total_header_nodes.values())
            table_context = " ".join(
                [_text(node) for _role, node in global_nodes]
                + [_text(cell) for row in header_rows for cell in _cells(row)]
            )
            table_percentage_context = bool(
                _PERCENT_CONTEXT_RE.search(table_context)
                or any(
                    _text(cell).strip() == "%"
                    for row in header_rows for cell in _cells(row)
                )
            )
            table_rounding_context = " ".join(
                [table_context]
                + [_text(cell) for row in all_rows for cell in _cells(row)]
            )
            rounding_match = _ROUNDING_NOTE_RE.search(table_rounding_context)
            rounding_note = (
                table_rounding_context[
                    max(0, rounding_match.start() - 80):rounding_match.end() + 120
                ]
                if rounding_match else None
            )
            table_adjustment_notes = [note for note, targets in adjustment_notes
                                      if method_scope_overflow or not targets or raw_table_id in targets]
            for role, node in global_nodes:
                quote = _text(node)
                if _ADJUSTMENT_NOTE_RE.search(quote):
                    table_adjustment_notes.append(
                        _evidence(node, f"table_{role}", quote)
                    )
            for row in all_rows:
                for cell in _cells(row):
                    quote = _text(cell)
                    if (
                        len(table_adjustment_notes) < MAX_ADJUSTMENT_NOTES
                        and _ADJUSTMENT_NOTE_RE.search(quote)
                    ):
                        table_adjustment_notes.append(
                            _evidence(cell, "table_cell_method_note", quote)
                        )
                    if len(table_adjustment_notes) >= MAX_ADJUSTMENT_NOTES:
                        break
                if len(table_adjustment_notes) >= MAX_ADJUSTMENT_NOTES:
                    break

            explicit_table_percentage_basis = bool(
                _EXPLICIT_PERCENT_BASIS_RE.search(table_context)
                or _EXPLICIT_PERCENT_OF_TOTAL_RE.search(table_context)
            )

            body_sections = list(_descendants(table, "tbody"))
            if body_sections:
                body_rows = [row for section in body_sections for row in _descendants(section, "tr")]
            else:
                header_ids = {id(row) for row in header_rows}
                body_rows = [row for row in all_rows if id(row) not in header_ids]

            # A table-wide total can supply an explicitly reported denominator
            # only when the table itself says its percentages are of the total
            # population and one full-width row states Total N (100%). A bare
            # total, a subgroup total, or a total row without that scope cue is
            # never inherited by the data rows.
            header_ids = {id(row) for row in header_rows}
            total_row_candidates: list[tuple[_Node, _Node, int]] = []
            if explicit_table_percentage_basis and table_percentage_context and header_columns:
                header_width = max(header_columns) + 1
                for candidate_row in all_rows:
                    if id(candidate_row) in header_ids:
                        continue
                    candidate_cells = _cells(candidate_row)
                    if len(candidate_cells) != 1:
                        continue
                    total_cell = candidate_cells[0]
                    if _span(total_cell, "colspan") != header_width:
                        continue
                    total_match = _FULL_WIDTH_TOTAL_ROW_RE.fullmatch(_text(total_cell))
                    if total_match:
                        total_row_candidates.append((candidate_row, total_cell, int(
                            total_match.group("count").replace(",", "")
                        )))
            if len(total_row_candidates) == 1:
                total_row, total_cell, total_value = total_row_candidates[0]
                global_facts.append({
                    "value": total_value,
                    "evidence": _evidence(total_cell, "table_total_row", _text(total_cell)),
                })
                body_rows = [row for row in body_rows if id(row) != id(total_row)]

            body_grid, body_layouts, body_layout_malformed = _layout_rows(body_rows)
            grid_nodes_by_row: dict[int, dict[int, _Node]] = {}
            for (r, _c), node in body_grid.items():
                grid_nodes_by_row.setdefault(r, {})[id(node)] = node
            group_for_row: list[tuple[int, tuple[str, _Node] | None]] = []
            group_number = 0
            row_group_context: tuple[str, _Node] | None = None
            missing_by_group: dict[tuple[int, int], _Node] = {}
            for row, (positions, _supported) in zip(body_rows, body_layouts):
                marker = _group_marker(row)
                if marker:
                    group_number += 1
                    row_group_context = marker
                group_for_row.append((group_number, row_group_context))
                cells = _cells(row)
                if any(_MISSING_RE.search(_text(cell)) for cell in cells):
                    for index, cell in enumerate(cells):
                        count = re.match(rf"^\s*(?P<count>{_INTEGER_TOKEN})\s*(?:/[^()]+)?\s*\(", _text(cell))
                        if count and int(count.group("count").replace(",", "")) > 0:
                            missing_by_group[(group_number, positions[index])] = row
                        column = positions[index]
                        headers = " ".join(_text(n) for n in header_columns.get(column, []))
                        if index > 0 and re.search(r"%|percent", headers, re.IGNORECASE):
                            previous_headers = header_columns.get(positions[index - 1], [])
                            count_index = index - 1
                            if index > 1 and _is_denominator_header(previous_headers):
                                count_index = index - 2
                            if _is_count_header(header_columns.get(positions[count_index], [])):
                                count_only = _COUNT_ONLY_RE.fullmatch(_text(cells[count_index]))
                                if count_only and int(count_only.group("count").replace(",", "")) > 0:
                                    missing_by_group[(group_number, column)] = row

            for row_index, row in enumerate(body_rows, start=1):
                rows_seen += 1
                if rows_seen > MAX_ROWS:
                    raise JATSSourceError("JATS source exceeds the row-count limit")
                cells = _cells(row)
                group_number, row_group_context = group_for_row[row_index - 1]
                if _group_marker(row):
                    continue
                positions, positions_supported = body_layouts[row_index - 1]
                own_ids = {id(cell) for cell in cells}
                inherited = {identity: node for identity, node in grid_nodes_by_row.get(row_index - 1, {}).items()
                             if identity not in own_ids}
                inherited_numeric = any(
                    _COUNT_PERCENT_RE.fullmatch(_text(node)) or _COUNT_RATIO_PERCENT_RE.fullmatch(_text(node))
                    or _PERCENT_ONLY_RE.fullmatch(_text(node)) for node in inherited.values())
                for cell_index, cell in enumerate(cells):
                    cells_seen += 1
                    if cells_seen > MAX_CELLS:
                        raise JATSSourceError("JATS source exceeds the cell-count limit")
                    column = positions[cell_index] if cell_index < len(positions) else cell_index
                    header_texts = " ".join(
                        _text(item) for item in header_columns.get(column, [])
                    )
                    row_specific_denominator_context = bool(
                        _ROW_SPECIFIC_RATIO_RE.search(header_texts)
                        or _ROW_SPECIFIC_RATIO_RE.search(table_context)
                        or (
                            row_group_context
                            and _ROW_SPECIFIC_RATIO_RE.search(row_group_context[0])
                        )
                    )
                    for fragment in _fragments(_text(cell)):
                        candidate = _candidate_from_cell(
                            source_sha256=source_sha256,
                            table_id=table_id,
                            table_index=tables_inspected,
                            row_index=row_index,
                            cell_index=cell_index,
                            column=column,
                            cell=cell,
                            cells=cells,
                            header_columns=header_columns,
                            header_layout_unsupported=header_layout_unsupported,
                            data_cell_layout_unsupported=not positions_supported or body_layout_malformed or inherited_numeric,
                            global_facts=global_facts,
                            table_percentage_context=table_percentage_context,
                            row_group_context=row_group_context,
                            row_specific_denominator_context=row_specific_denominator_context,
                            adjustment_notes=table_adjustment_notes,
                            rounding_note=rounding_note,
                            fragment=fragment,
                            missing_scope_note=missing_by_group.get((group_number, column)),
                            total_header_facts=total_header_facts,
                            inherited_row_labels=list(inherited.values()),
                            explicit_table_percentage_basis=explicit_table_percentage_basis,
                            article_group_populations=article_group_populations,
                            table_population_context_nodes=[
                                node for node in (label_node, caption_node) if node is not None
                            ],
                        )
                        if candidate is not None:
                            results.append(candidate)
                            if len(results) > MAX_RESULTS:
                                raise JATSSourceError("JATS source exceeds the result-count limit")

    return {
        "source_format": "JATS XML",
        "source_sha256": source_sha256,
        "extracted_text_sha256": hashlib.sha256(_text(root).encode("utf-8")).hexdigest(),
        "extraction_profile": "jats-normalized-text-v1",
        "method_scope_overflow": method_scope_overflow,
        "tables_inspected": tables_inspected,
        "percentage_cells_reviewed": len(results),
        "results": results,
        "limitations": [
            "Arithmetic candidates are not proof of a scientific error.",
            "A SHA-256 commits to the supplied bytes; it does not authenticate their source.",
            "Only explicit n (%) cells or headed count/percent columns with denominator evidence are evaluated.",
            "PDF, OCR, and publisher-layout extraction are not supported.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jats_xml", help="one local UTF-8 JATS XML file")
    args = parser.parse_args(argv)
    try:
        data = read_regular(Path(args.jats_xml), MAX_SOURCE_BYTES)
        report = audit_jats_percentage_tables(data)
    except (OSError, ValueError) as exc:
        print(f"JATS audit failed: {exc}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI invocation
    raise SystemExit(main())
