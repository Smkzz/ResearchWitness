"""Source-byte-preserving table projection for the *existing* bounded JATS parser.

Projection is descriptive, not a replacement detector, a population/denominator
resolver, an empirical truth estimator, or a scientific finding. The immutable
PaperDocument model is reused from the legacy branch without changing its types.
"""
from __future__ import annotations

from hashlib import sha256

from . import _jats_parser as jats
from .paper_document import (
    HeaderCellReference, NumericAssertion, NumericValue, PaperDocument,
    SourceAnchor, Table, TableCell, TableColumn, TableFootnote, TableRow,
    CellSpan,
)

VERSION = "rw-jats-table-projection.v1"
MAX_MODEL_TABLES = jats.MAX_TABLES
MAX_MODEL_ROWS = jats.MAX_ROWS
MAX_MODEL_CELLS = jats.MAX_CELLS


def _paths(root: jats._Node) -> dict[int, str]:
    """Index exact original element locations using stable sibling ordinals."""
    paths: dict[int, str] = {}
    stack = [(root, "/article[1]")]
    while stack:
        node, path = stack.pop()
        paths[id(node)] = path
        counts: dict[str, int] = {}
        descendants: list[tuple[jats._Node, str]] = []
        for child in node.children:
            tag = jats._local_name(child.tag)
            counts[tag] = counts.get(tag, 0) + 1
            descendants.append((child, f"{path}/{tag}[{counts[tag]}]"))
        stack.extend(reversed(descendants))
    return paths


def _anchor(node: jats._Node, paths: dict[int, str], source_hash: str) -> SourceAnchor:
    return SourceAnchor(
        source_file="source.xml", source_sha256=source_hash,
        source_format="jats_xml", element_path=paths[id(node)],
        quote=jats._text(node), start_byte=node.byte_start, end_byte=node.byte_end,
    )


def _refs(node: jats._Node) -> tuple[tuple[str, str], ...]:
    """Preserve JATS cross-references as data, never resolve them as authority."""
    result: list[tuple[str, str]] = []
    for xref in jats._descendants(node, "xref"):
        kind = jats._attribute(xref, "ref-type") or ""
        rid = jats._attribute(xref, "rid") or ""
        result.append((kind, rid))
    return tuple(result)


def _numeric_values(
    text: str, headers: tuple[jats._Node, ...] = (),
    *, conflicting_header_roles: bool = False,
) -> tuple[NumericValue, ...]:
    """Preserve explicit numeric lexemes without inventing percentage roles.

    A count(SD) cell is syntactically similar to count(percent). Only an
    explicit '%' token or an unambiguous percentage heading permits percentage
    classification. A cell spanning distinct column roles is never classified
    from inherited headings alone.
    """
    heading = " ".join(jats._text(h) for h in headers).casefold()
    percent_heading = "%" in heading or "percent" in heading
    statistical_spread = any(
        marker in heading for marker in
        ("mean", "standard deviation", "sd", "confidence interval", "95% ci")
    )
    explicit_percent = "%" in text
    confident_percent = (
        explicit_percent or
        (percent_heading and not statistical_spread and not conflicting_header_roles)
    )
    ratio = jats._COUNT_RATIO_PERCENT_RE.fullmatch(text)
    combined = ratio or jats._COUNT_PERCENT_RE.fullmatch(text)
    if combined:
        count = combined.group("count")
        percent = combined.group("percent")
        count_role = "count" if confident_percent else None
        denom_role = "explicit_ratio_denominator" if confident_percent else None
        values = [NumericValue(count, str(int(count.replace(",", ""))), count_role, None)]
        if ratio:
            denominator = ratio.group("denominator")
            values.append(NumericValue(
                denominator, str(int(denominator.replace(",", ""))), denom_role, None,
            ))
        values.append(NumericValue(
            percent, percent, "percent" if confident_percent else None,
            len(percent.partition(".")[2]),
        ))
        return tuple(values)
    numeric = jats._PERCENT_ONLY_RE.fullmatch(text)
    if numeric:
        value = numeric.group("percent")
        role = (
            "percent" if (explicit_percent or confident_percent) else
            "count" if (not conflicting_header_roles and
                        jats._is_count_header(list(headers)) and
                        jats._COUNT_ONLY_RE.fullmatch(text)) else None
        )
        return (NumericValue(value, value, role, len(value.partition(".")[2])),)
    return ()


def _supported_header_rows(table: jats._Node) -> tuple[list[jats._Node], list[jats._Node], bool]:
    all_rows = list(jats._descendants(table, "tr"))
    theads = list(jats._descendants(table, "thead"))
    headers = [row for group in theads for row in jats._descendants(group, "tr")]
    if not headers and all_rows:
        cells = jats._cells(all_rows[0])
        if cells and all(jats._local_name(cell.tag) == "th" for cell in cells):
            headers = [all_rows[0]]
    fallback = not headers
    return headers, all_rows, fallback


def _row_group(node: jats._Node) -> str:
    parent = node.parent
    while parent is not None:
        tag = jats._local_name(parent.tag)
        if tag in {"tbody", "thead", "tfoot"}:
            return f"{tag}:{jats._attribute(parent, 'id') or 'unlabeled'}"
        if tag == "table":
            break
        parent = parent.parent
    return "table:unlabeled"


def _table(
    wrap: jats._Node, table: jats._Node, index: int,
    paths: dict[int, str], source_hash: str,
    duplicate_id: bool,
) -> Table:
    label_node = next(iter(jats._descendants(wrap, "label")), None)
    caption_node = next(iter(jats._descendants(wrap, "caption")), None)
    label = jats._text(label_node) if label_node else ""
    caption = jats._text(caption_node) if caption_node else ""
    source_id = jats._attribute(wrap, "id")
    # Duplicate source IDs remain visible in metadata rather than silently
    # pretending to be distinct publisher-assigned IDs.
    table_id = f"{source_id or 'unnamed'}#{index}"
    headers, all_rows, no_headers = _supported_header_rows(table)
    header_columns, malformed_headers, _ = jats._header_columns(headers)
    _header_grid, header_layout, _ = jats._layout_rows(headers, header=True)
    header_positions: dict[int, tuple[int, int]] = {}
    for ri, row in enumerate(headers):
        positions = header_layout[ri][0]
        for cell, col in zip(jats._cells(row), positions):
            header_positions[id(cell)] = (ri, col)

    header_ids = {id(row) for row in headers}
    body_rows = [row for row in all_rows if id(row) not in header_ids]
    grid, layouts, malformed_body = jats._layout_rows(body_rows)
    width = max((column + 1 for (_row, column) in grid), default=0)
    width = max(width, max(header_columns, default=-1) + 1)
    if width > jats.MAX_LAYOUT_COLUMNS:
        raise jats.JATSSourceError("JATS table projection exceeds column limit")

    cols = tuple(
        TableColumn(column, tuple(jats._text(x) for x in header_columns.get(column, ())))
        for column in range(width)
    )
    rows: list[TableRow] = []
    spans: list[CellSpan] = []
    bad_data_layout = malformed_body
    semantic_role_ambiguity = False
    for ri, row in enumerate(body_rows):
        cells = jats._cells(row)
        positions, supported = layouts[ri]
        bad_data_layout |= not supported
        row_identity = jats._text(cells[0]) if cells else f"row:{ri}"
        actual: list[TableCell] = []
        for cell, col in zip(cells, positions):
            raw = jats._text(cell)
            colspan, rowspan = jats._span(cell, "colspan"), jats._span(cell, "rowspan")
            if colspan is None or rowspan is None:
                bad_data_layout = True
                colspan = colspan or 1
                rowspan = rowspan or 1
            # A spanning body cell inherits every covered column, not just the
            # first. Keep the source-cited references deduplicated.
            column_headers = [
                tuple(header_columns.get(k, ()))
                for k in range(col, min(width, col + colspan))
            ]
            conflicting_roles = len({
                tuple(id(header) for header in h) for h in column_headers
            }) > 1
            semantic_role_ambiguity |= conflicting_roles
            inherited_headers = tuple(dict.fromkeys(
                id(header) for headers in column_headers for header in headers
            ))
            headers_by_id = {
                id(header): header for headers in column_headers for header in headers
            }
            inherited_headers = tuple(headers_by_id[key] for key in inherited_headers)
            refs: list[HeaderCellReference] = []
            for header in inherited_headers:
                header_ri, header_col = header_positions[id(header)]
                refs.append(HeaderCellReference(
                    text=jats._text(header), source_anchor=_anchor(header, paths, source_hash),
                    row_index=header_ri, column_start=header_col,
                    row_span=jats._span(header, "rowspan") or 1,
                    column_span=jats._span(header, "colspan") or 1,
                    cross_references=_refs(header),
                ))
            scope_nodes = list(inherited_headers)
            if caption_node is not None:
                scope_nodes.append(caption_node)
            cues = tuple(
                jats._text(node) for node in scope_nodes
                if jats._DENOMINATOR_RE.search(jats._text(node))
            )
            xrefs = _refs(cell)
            footnotes = tuple(rid for kind, rid in xrefs if kind in {"fn", "table-fn"})
            actual.append(TableCell(
                raw_text=raw,
                normalized_numeric_values=_numeric_values(
                    raw, inherited_headers, conflicting_header_roles=conflicting_roles,
                ),
                row_identity=row_identity,
                column_identity=col,
                effective_headers=tuple(jats._text(h) for h in inherited_headers),
                footnote_references=footnotes,
                cross_references=xrefs,
                scope_denominator_cues=cues,
                row_span=rowspan, column_span=colspan, column_start=col,
                source_anchor=_anchor(cell, paths, source_hash),
                effective_header_refs=tuple(refs),
                indentation_level=0,
            ))
            if colspan != 1 or rowspan != 1:
                spans.append(CellSpan(_row_group(row), ri, col, rowspan, colspan, raw))
        rows.append(TableRow(_row_group(row), ri, tuple(actual)))

    footnotes: list[TableFootnote] = []
    for foot in jats._descendants(wrap, "fn"):
        foot_label = next(iter(jats._descendants(foot, "label")), None)
        footnotes.append(TableFootnote(
            jats._attribute(foot, "id"),
            jats._text(foot_label) if foot_label else "",
            jats._text(foot), _anchor(foot, paths, source_hash),
        ))

    warnings = []
    if no_headers:
        warnings.append("explicit_header_not_available")
    if malformed_headers:
        warnings.append("header_layout_ambiguous")
    if bad_data_layout:
        warnings.append("body_layout_ambiguous")
    if duplicate_id:
        warnings.append("duplicate_source_table_id")
    if semantic_role_ambiguity:
        warnings.append("spanning_cell_role_ambiguous")
    warnings.append("numeric_lexemes_only_denominator_scope_not_inferred")
    return Table(
        label=label, caption=caption, table_id=table_id,
        wrap_metadata=tuple(sorted(
            [(jats._local_name(name), value) for name, value in wrap.attrs.items()]
        )),
        header_hierarchy=tuple(col.header_hierarchy for col in cols),
        rows=tuple(rows), columns=cols, spans=tuple(spans),
        footnotes=tuple(footnotes), source_anchor=_anchor(wrap, paths, source_hash),
        extraction_confidence=0.0,  # Not a calibrated confidence score.
        structure_status="ambiguous" if warnings[:-1] else "mapped_not_adjudicated",
        limitations=tuple(warnings),
        label_anchor=_anchor(label_node, paths, source_hash) if label_node else None,
        caption_anchor=_anchor(caption_node, paths, source_hash) if caption_node else None,
    )


def project_jats_tables(source: bytes, detector_report: dict | None = None) -> PaperDocument:
    """Bounded typed table projection; original XML offsets remain byte-exact.

    Reuse the same parser and detector implementation as the installed JATS
    audit. No independent scientific/source-correspondence review is implied.
    """
    root = jats._parse_jats(source)
    source_hash = sha256(source).hexdigest()
    paths = _paths(root)
    table_pairs: list[tuple[jats._Node, jats._Node]] = []
    for wrapper in jats._descendants(root, "table-wrap"):
        for table in jats._descendants(wrapper, "table"):
            table_pairs.append((wrapper, table))
            if len(table_pairs) > MAX_MODEL_TABLES:
                raise jats.JATSSourceError("JATS table projection exceeds table-count limit")

    # Bound projected source tables *before* constructing large nested models.
    estimated_rows = estimated_cells = 0
    for _wrapper, table in table_pairs:
        for row in jats._descendants(table, "tr"):
            estimated_rows += 1
            estimated_cells += len(jats._cells(row))
            if estimated_rows > MAX_MODEL_ROWS or estimated_cells > MAX_MODEL_CELLS:
                raise jats.JATSSourceError("JATS table projection exceeds row/cell limit")

    # Recompute supplied detector results against original bytes; merely checking
    # source hash and cell offset would permit fabricated numeric assertions.
    actual_report = jats.audit_jats_percentage_tables(source)
    if detector_report is not None:
        if (type(detector_report) is not dict or
                detector_report.get("source_sha256") != source_hash):
            raise jats.JATSSourceError("Source and detector report refer to different bytes")
        if detector_report != actual_report:
            raise jats.JATSSourceError("Supplied detector report does not match source")
    detector_report = actual_report

    identifiers: dict[str, int] = {}
    for wrapper, _table_node in table_pairs:
        key = jats._attribute(wrapper, "id")
        if key:
            identifiers[key] = identifiers.get(key, 0) + 1
    tables: list[Table] = []
    row_count = cell_count = 0
    for i, (wrap, tbl) in enumerate(table_pairs, start=1):
        key = jats._attribute(wrap, "id")
        mapped = _table(wrap, tbl, i, paths, source_hash,
                        bool(key and identifiers[key] > 1))
        tables.append(mapped)
        row_count += len(mapped.rows)
        cell_count += sum(len(row.cells) for row in mapped.rows)
        if row_count > MAX_MODEL_ROWS or cell_count > MAX_MODEL_CELLS:
            raise jats.JATSSourceError("JATS table projection exceeds row/cell limit")

    spans = {(cell.source_anchor.start_byte, cell.source_anchor.end_byte): cell
             for table in tables for row in table.rows for cell in row.cells}
    assertions: list[NumericAssertion] = []
    for finding in detector_report["results"]:
        evidence = finding["evidence"]
        start, end = evidence["byte_start"], evidence["byte_end"]
        cell = spans.get((start, end))
        if cell is None:
            raise jats.JATSSourceError("Detector finding is not bound to a projected cell")
        # Never promote a conditional denominator into an asserted fact.
        denominator = (str(finding["denominator"])
                       if finding["status"] in {"arithmetic_match", "arithmetic_mismatch_candidate"}
                       and finding["denominator"] is not None else None)
        source_facts = finding["evidence"].get("denominator_sources", [])
        if type(source_facts) is not list or len(source_facts) > 64:
            raise jats.JATSSourceError("Detector emitted invalid denominator evidence")
        provenance = [
            f"detector_status:{finding['status']}",
            f"denominator_scope:{finding['denominator_scope']}",
            "scientific_source_correspondence_not_adjudicated",
        ]
        for fact in source_facts:
            position = fact["evidence"]
            start, end = position["byte_start"], position["byte_end"]
            if (type(start) is not int or type(end) is not int or
                    not 0 <= start < end <= len(source)):
                raise jats.JATSSourceError("Detector denominator evidence outside original source")
            provenance.append(
                f"detector_denominator_fact:{position['role']}:{fact['value']}:{start}:{end}"
            )
        assertions.append(NumericAssertion(
            value=finding["reported_percent"], unit="percent",
            statistic_type="count_percentage", numerator=str(finding["numerator"]),
            denominator=denominator, population=None, group=None, outcome=None,
            timepoint=None, adjustment_status=None,
            source_anchor=cell.source_anchor,
            structural_provenance=tuple(provenance),
        ))

    title_node = next(iter(jats._descendants(root, "article-title")), None)
    title = jats._text(title_node) if title_node else ""
    warnings = ("narrative_sections_and_figures_not_projected",
                "table_projection_does_not_establish_denominator_scope_or_source_origin")
    return PaperDocument(
        model_version=VERSION, source_file="source.xml",
        source_sha256=source_hash, source_format="jats_xml", title=title,
        sections=(), paragraphs=(), tables=tuple(tables),
        numeric_assertions=tuple(assertions), extraction_warnings=warnings,
    )
