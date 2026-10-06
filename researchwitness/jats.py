"""Bounded, source-aware parsing of JATS XML into the canonical paper model."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from html.entities import html5
from xml.parsers import expat
from typing import Iterable
import re

from .paper_document import (
    CellSpan, NumericAssertion, NumericValue, PaperDocument, Paragraph, Section,
    SourceAnchor, Table, TableCell, TableColumn, TableFootnote, TableRow,
)
from .strict import Invalid

MAX_JATS_BYTES = 32 * 1024 * 1024
MAX_JATS_ELEMENTS = 250_000
MAX_JATS_DEPTH = 64
MAX_JATS_TEXT_BYTES = 16 * 1024 * 1024
MAX_TABLE_COLUMNS = 256
MAX_TABLE_ROWS = 10_000
MAX_JATS_TABLES = 1_000
MAX_JATS_TABLE_CELLS = 50_000
MAX_SPAN = 256

_COUNT_PERCENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*\(\s*(?P<percent>[0-9]{1,3}(?:\.[0-9]{1,6})?)\s*(?P<mark>%?)\s*\)\s*$'
)
_NUMBER = re.compile(r'(?<![A-Za-z0-9_])(?P<value>-?[0-9]+(?:\.[0-9]+)?)(?P<unit>\s*%)?(?![A-Za-z0-9_])')
_DENOMINATOR = re.compile(r'(?<![A-Za-z0-9_])[nN]\s*=\s*(?P<value>[0-9]{1,9})(?![0-9])')
_FOOTNOTE_MARK = re.compile(r'[a-z*†‡§¹²³⁴⁵⁶⁷⁸⁹⁰]$', re.IGNORECASE)
_UNSAFE_CUES = re.compile(
    r'\b(?:weighted|adjusted|multiple responses?|overlap(?:ping)?|missing data|available cases?|'
    r'denominator|excluding|excluded|per row|nonresponse)\b', re.IGNORECASE,
)
_TIMEPOINT = re.compile(r'\b(?:baseline|follow[ -]?up|week\s+\d+|month\s+\d+|year\s+\d+)\b', re.IGNORECASE)
_EXTERNAL_DOCTYPE = re.compile(
    rb'<!DOCTYPE\s+[A-Za-z_:][A-Za-z0-9_.:-]*\s+'
    rb'(?:SYSTEM\s+(?:"[^"<>]*"|\'[^\'<>]*\')|'
    rb'PUBLIC\s+(?:"[^"<>]*"|\'[^\'<>]*\')\s+(?:"[^"<>]*"|\'[^\'<>]*\'))\s*>',
    re.IGNORECASE | re.DOTALL,
)
_NAMED_ENTITY = re.compile(rb'&([A-Za-z][A-Za-z0-9._:-]*);')
_XML_LITERAL = re.compile(rb'<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>', re.DOTALL)


def _prepare_jats_bytes(source: bytes) -> bytes:
    """Drop external DTD references without loading them and expand known XML names.

    JATS publisher captures commonly carry an external DTD declaration and use
    its named character entities. The parser never fetches that DTD: only an
    external declaration without an internal subset is stripped, and names are
    accepted only when the Python HTML5 entity table maps them to Unicode.
    Internal subsets, custom entities, and unknown entity names fail closed.
    """
    def replace_entity(match: re.Match[bytes]) -> bytes:
        name = match.group(1).decode('ascii')
        if name in {'amp', 'lt', 'gt', 'apos', 'quot'}:
            return match.group(0)
        value = html5.get(name + ';')
        if value is None:
            raise Invalid('JATS source uses an unknown or unsupported named entity')
        return b''.join(f'&#{ord(character)};'.encode('ascii') for character in value)

    def prepare_markup_and_text(data: bytes) -> bytes:
        data = _EXTERNAL_DOCTYPE.sub(b'', data, count=1)
        if re.search(rb'<!DOCTYPE\b|<!ENTITY\b', data, re.IGNORECASE):
            raise Invalid('JATS DTD and entity declarations are unsupported')
        return _NAMED_ENTITY.sub(replace_entity, data)

    prepared: list[bytes] = []
    cursor = 0
    for literal in _XML_LITERAL.finditer(source):
        prepared.append(prepare_markup_and_text(source[cursor:literal.start()]))
        prepared.append(literal.group(0))
        cursor = literal.end()
    prepared.append(prepare_markup_and_text(source[cursor:]))
    return b''.join(prepared)


@dataclass(slots=True)
class _Node:
    name: str
    attributes: dict[str, str]
    source_start: int
    parent: _Node | None = None
    content: list[str | _Node] = field(default_factory=list)
    children: list[_Node] = field(default_factory=list)
    element_path: str = ''


def _local_name(name: str) -> str:
    return name.rsplit('}', 1)[-1].split(':')[-1].lower()


def _attribute_map(attrs: dict[str, str]) -> dict[str, str]:
    return {_local_name(key): value for key, value in attrs.items()}


def _node_text(node: _Node | None) -> str:
    if node is None:
        return ''
    parts: list[str] = []
    stack: list[tuple[_Node, int]] = [(node, 0)]
    while stack:
        current, index = stack.pop()
        if index >= len(current.content):
            continue
        stack.append((current, index + 1))
        item = current.content[index]
        if isinstance(item, str):
            parts.append(item)
        else:
            stack.append((item, 0))
    return re.sub(r'\s+', ' ', ''.join(parts)).strip()


def _descendants(node: _Node, names: set[str] | None = None) -> Iterable[_Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        if names is None or current.name in names:
            yield current
        stack.extend(reversed(current.children))


def _direct(node: _Node, name: str) -> list[_Node]:
    return [child for child in node.children if child.name == name]


def _footnote_text(node: _Node) -> tuple[str, str]:
    label = _node_text(next((child for child in node.children if child.name == 'label'), None))
    body = ' '.join(
        value for child in node.children if child.name != 'label'
        if (value := _node_text(child))
    )
    return label, ' '.join(value for value in (label, body) if value)


def _anchor(node: _Node, source_file: str, source_digest: str, quote: str) -> SourceAnchor:
    return SourceAnchor(
        source_file=source_file,
        source_sha256=source_digest,
        source_format='jats_xml',
        element_path=node.element_path,
        quote=quote[:1000],
        start_byte=None,
    )


def _build_tree(source: bytes) -> _Node:
    if len(source) > MAX_JATS_BYTES:
        raise Invalid('JATS source exceeded the configured 32 MiB limit')
    parse_source = _prepare_jats_bytes(source)
    parser = expat.ParserCreate(namespace_separator='}')
    parser.buffer_text = True
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    stack: list[_Node] = []
    root: _Node | None = None
    element_count = 0
    text_bytes = 0

    def fail_declaration(*_args) -> None:
        raise Invalid('JATS DTD and entity declarations are unsupported')

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal root, element_count
        element_count += 1
        if element_count > MAX_JATS_ELEMENTS:
            raise Invalid('JATS source exceeded the configured element limit')
        if len(stack) >= MAX_JATS_DEPTH:
            raise Invalid('JATS source exceeded the configured nesting limit')
        parent = stack[-1] if stack else None
        node = _Node(_local_name(name), _attribute_map(attrs), parser.CurrentByteIndex, parent)
        if parent is None:
            if root is not None:
                raise Invalid('JATS source has multiple root elements')
            root = node
        else:
            parent.children.append(node)
            parent.content.append(node)
        stack.append(node)

    def end(_name: str) -> None:
        if not stack:
            raise Invalid('JATS source has unbalanced elements')
        stack.pop()

    def character(data: str) -> None:
        nonlocal text_bytes
        text_bytes += len(data.encode('utf-8'))
        if text_bytes > MAX_JATS_TEXT_BYTES:
            raise Invalid('JATS source exceeded the configured extracted-text limit')
        if stack and data:
            content = stack[-1].content
            if content and isinstance(content[-1], str):
                content[-1] += data
            else:
                content.append(data)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = character
    parser.StartDoctypeDeclHandler = fail_declaration
    parser.EntityDeclHandler = fail_declaration
    parser.ExternalEntityRefHandler = lambda *_args: 0
    try:
        parser.Parse(parse_source, True)
    except Invalid:
        raise
    except (expat.ExpatError, ValueError) as exc:
        raise Invalid('JATS source is malformed or unsupported XML') from exc
    if root is None or stack:
        raise Invalid('JATS source is empty or incomplete')

    def assign_paths(root_node: _Node) -> None:
        todo = [(root_node, '', 1)]
        while todo:
            node, parent_path, sibling_index = todo.pop()
            if parent_path:
                node.element_path = f'{parent_path}/{node.name}[{sibling_index}]'
            else:
                node.element_path = f'/{node.name}[1]'
            counts: dict[str, int] = {}
            children: list[tuple[_Node, str, int]] = []
            for child in node.children:
                counts[child.name] = counts.get(child.name, 0) + 1
                children.append((child, node.element_path, counts[child.name]))
            todo.extend(reversed(children))

    assign_paths(root)
    return root


def _parse_span(cell: _Node, attr_name: str, default: int = 1) -> int:
    raw = cell.attributes.get(attr_name)
    if raw is None and attr_name == 'rowspan' and 'morerows' in cell.attributes:
        try:
            value = int(cell.attributes['morerows']) + 1
        except ValueError as exc:
            raise Invalid('JATS table contains an invalid morerows span') from exc
    elif raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise Invalid('JATS table contains an invalid cell span') from exc
    if not 1 <= value <= MAX_SPAN:
        raise Invalid('JATS table cell span is outside the supported range')
    return value


def _expand_rows(
    group_name: str, rows: list[_Node],
) -> tuple[list[list[_Node | None]], list[list[tuple[_Node, int, int, int]]], list[str]]:
    if len(rows) > MAX_TABLE_ROWS:
        raise Invalid('JATS table exceeded the configured row limit')
    grid: list[list[_Node | None]] = []
    placements: list[list[tuple[_Node, int, int, int]]] = []
    limitations: list[str] = []
    active: dict[int, tuple[int, _Node]] = {}
    for row in rows:
        current: list[_Node | None] = [None] * MAX_TABLE_COLUMNS
        next_active: dict[int, tuple[int, _Node]] = {}
        for col, (_remaining, node) in active.items():
            current[col] = node
            if _remaining > 1:
                next_active[col] = (_remaining - 1, node)
        row_placements: list[tuple[_Node, int, int, int]] = []
        cursor = 0
        cells = [child for child in row.children if child.name in ('td', 'th', 'entry')]
        for cell in cells:
            try:
                rowspan = _parse_span(cell, 'rowspan')
                colspan = _parse_span(cell, 'colspan')
            except Invalid as exc:
                limitations.append(str(exc))
                rowspan = colspan = 1
            while cursor + colspan <= MAX_TABLE_COLUMNS and any(current[index] is not None
                                                               for index in range(cursor, cursor + colspan)):
                cursor += 1
            if cursor + colspan > MAX_TABLE_COLUMNS:
                limitations.append('Table exceeded the configured column limit.')
                break
            if any(current[index] is not None for index in range(cursor, cursor + colspan)):
                limitations.append('Overlapping table spans prevented safe column alignment.')
                break
            for index in range(cursor, cursor + colspan):
                current[index] = cell
                if rowspan > 1:
                    previous = active.get(index)
                    if previous is not None:
                        limitations.append('Overlapping row spans prevented safe table reconstruction.')
                    next_active[index] = (rowspan - 1, cell)
            row_placements.append((cell, cursor, rowspan, colspan))
            cursor += colspan
        grid.append(current)
        placements.append(row_placements)
        active = next_active
    if active:
        limitations.append('A row span extends beyond its table row group.')
    width = max((max((idx + 1 for idx, cell in enumerate(row) if cell is not None), default=0)
                 for row in grid), default=0)
    if width > MAX_TABLE_COLUMNS:
        limitations.append('Table exceeded the configured column limit.')
    if any(any(cell is None for cell in row[:width]) for row in grid):
        limitations.append('A ragged table row contains a missing structural cell.')
    return [row[:width] for row in grid], placements, limitations


def _numeric_values(raw: str) -> tuple[NumericValue, ...]:
    values = []
    for match in _NUMBER.finditer(raw):
        surface = match.group('value') + (match.group('unit') or '').strip()
        exact = match.group('value')
        precision = len(exact.partition('.')[2]) if '.' in exact else 0
        values.append(NumericValue(surface, exact, '%' if match.group('unit') else None, precision))
    return tuple(values[:32])


def _table(
    root: _Node,
    source_file: str,
    source_digest: str,
    footnote_nodes: dict[str, _Node],
) -> tuple[Table, list[NumericAssertion]]:
    wrap = root
    label_node = next((node for node in wrap.children if node.name == 'label'), None)
    caption_node = next((node for node in wrap.children if node.name == 'caption'), None)
    label = _node_text(label_node)
    caption = _node_text(caption_node)
    table_node = next((node for node in _descendants(wrap) if node.name == 'table'), None)
    limitations: list[str] = []
    if table_node is None:
        limitations.append('No structured table element was present inside the table wrapper.')
        groups: list[tuple[str, list[_Node]]] = []
    else:
        groups = []
        for group_name in ('thead', 'tbody', 'tfoot'):
            for group_node in _direct(table_node, group_name):
                rows = [node for node in group_node.children if node.name == 'tr']
                groups.append((group_name, rows))
        loose_rows = [node for node in table_node.children if node.name == 'tr']
        if loose_rows:
            groups.append(('tbody', loose_rows))
            limitations.append('Rows outside thead/tbody/tfoot were preserved but do not establish header semantics.')
    grids: dict[str, list[list[_Node | None]]] = {}
    placements: dict[str, list[list[tuple[_Node, int, int, int]]]] = {}
    row_nodes: dict[str, list[_Node]] = {}
    for name, rows in groups:
        if name in grids:
            limitations.append(f'Multiple {name} groups were found; table arithmetic is unsupported.')
        grid, place, group_limits = _expand_rows(name, rows)
        grids[name] = grids.get(name, []) + grid
        placements[name] = placements.get(name, []) + place
        row_nodes[name] = row_nodes.get(name, []) + rows
        limitations.extend(group_limits)

    header_grid = grids.get('thead', [])
    body_grid = grids.get('tbody', [])
    header_width = max((len(row) for row in header_grid), default=0)
    body_width = max((len(row) for row in body_grid), default=0)
    width = max(header_width, body_width)
    if width == 0:
        limitations.append('No non-empty structured header and body grid could be reconstructed.')
    if header_width != width or body_width != width:
        limitations.append('Header and body columns do not align after resolving declared spans.')
    if not header_grid:
        limitations.append('An explicit thead header group is required for table arithmetic.')
    header_matrix: list[tuple[str, ...]] = []
    for col in range(width):
        labels = []
        for row in header_grid:
            cell = row[col] if col < len(row) else None
            value = _node_text(cell)
            if value and (not labels or labels[-1] != value):
                labels.append(value)
        header_matrix.append(tuple(labels))
    header_hierarchy = tuple(tuple(_node_text(cell) if cell is not None else '' for cell in row)
                             for row in header_grid)
    body_rows = row_nodes.get('tbody', [])
    body_labels_present = bool(body_rows) and all(
        bool((cells := [child for child in row.children if child.name in ('td', 'th')]))
        and bool(_node_text(cells[0])) for row in body_rows
    )
    stub = bool(header_matrix and header_matrix[0] and header_matrix[0][0].strip() and body_labels_present)
    if not stub:
        limitations.append('The first-column header and body rows do not clearly preserve row labels.')
    structural_problem = bool(limitations)

    footnotes: list[TableFootnote] = []
    for foot_group in [child for child in wrap.children if child.name in ('table-wrap-foot', 'table-foot')]:
        for fn in _descendants(foot_group, {'fn', 'p'}):
            if fn.name == 'fn':
                label_text, text = _footnote_text(fn)
                footnotes.append(TableFootnote(
                    fn.attributes.get('id'), label_text, text,
                    _anchor(fn, source_file, source_digest, text),
                ))
            elif not any(ancestor.name == 'fn' for ancestor in _parents(fn)):
                text = _node_text(fn)
                if text:
                    footnotes.append(TableFootnote(None, '', text, _anchor(fn, source_file, source_digest, text)))
    known_footnote_ids = {note.identifier for note in footnotes if note.identifier}
    referenced_ids = {
        identifier
        for xref in _descendants(wrap, {'xref'})
        for identifier in xref.attributes.get('rid', '').split()
    }
    for identifier in sorted(referenced_ids - known_footnote_ids):
        referenced = footnote_nodes.get(identifier)
        if referenced is not None:
            label_text, note_text = _footnote_text(referenced)
            footnotes.append(TableFootnote(
                identifier, label_text, note_text,
                _anchor(referenced, source_file, source_digest, note_text),
            ))

    all_notes = ' '.join(note.text for note in footnotes)
    table_context = ' '.join((caption, label, all_notes, *(header for column in header_matrix for header in column)))
    unsafe = _UNSAFE_CUES.search(table_context)
    if unsafe:
        limitations.append('Table context contains weighting, adjustment, missingness, multiple-response, or overlap cues.')
    # A row-spanning data value can propagate one group label into multiple rows;
    # retain its representation but do not treat the resulting grid as arithmetic-ready.
    for placements_in_group in placements.get('tbody', []):
        if any(rowspan > 1 for _cell, _start, rowspan, _span in placements_in_group):
            limitations.append('Data-row spans are preserved but make row identity ambiguous for arithmetic.')
            structural_problem = True

    source_rows: list[TableRow] = []
    spans: list[CellSpan] = []
    numeric_assertions: list[NumericAssertion] = []
    for group_name, rows in groups:
        group_grid = grids.get(group_name, [])
        group_placements = placements.get(group_name, [])
        for row_index, (row_node, row_placement) in enumerate(zip(row_nodes.get(group_name, []), group_placements)):
            row_grid = group_grid[row_index] if row_index < len(group_grid) else []
            row_label = _node_text(row_grid[0]) if row_grid else ''
            cells: list[TableCell] = []
            for cell_node, start, rowspan, colspan in row_placement:
                raw = _node_text(cell_node)
                if rowspan > 1 or colspan > 1:
                    spans.append(CellSpan(group_name, row_index, start, rowspan, colspan, raw))
                effective = header_matrix[start] if group_name != 'thead' and start < len(header_matrix) else ()
                footnote_refs = []
                cross_refs = []
                for xref in _descendants(cell_node, {'xref'}):
                    reference_type = xref.attributes.get('ref-type', '').lower()
                    for rid in xref.attributes.get('rid', '').split():
                        if reference_type in ('table-fn', 'fn', 'author-notes') or rid in footnote_nodes:
                            footnote_refs.append(rid)
                        else:
                            cross_refs.append((reference_type, rid))
                cues = []
                if group_name != 'thead' and _DENOMINATOR.search(raw):
                    cues.append('CELL_LOCAL_DENOMINATOR')
                if _UNSAFE_CUES.search(raw):
                    cues.append('WEIGHTED_ADJUSTED_MISSING_OR_OVERLAPPING_SCOPE_CUE')
                if footnote_refs or cross_refs:
                    cues.append('FOOTNOTE_OR_CROSS_REFERENCE_PRESENT')
                if group_name != 'thead' and start < width:
                    header_refs = [xref.attributes.get('rid', '').split()
                                   for header_row in header_grid
                                   for header_node in ([header_row[start]] if start < len(header_row) else [])
                                   if header_node is not None
                                   for xref in _descendants(header_node, {'xref'})]
                    if any(header_refs):
                        cues.append('HEADER_FOOTNOTE_OR_CROSS_REFERENCE_PRESENT')
                cell = TableCell(
                    raw_text=raw,
                    normalized_numeric_values=_numeric_values(raw),
                    row_identity=row_label,
                    column_identity=start,
                    effective_headers=tuple(effective),
                    footnote_references=tuple(dict.fromkeys(footnote_refs)),
                    cross_references=tuple(dict.fromkeys(cross_refs)),
                    scope_denominator_cues=tuple(cues),
                    row_span=rowspan,
                    column_span=colspan,
                    column_start=start,
                    source_anchor=_anchor(cell_node, source_file, source_digest, raw),
                )
                cells.append(cell)
                if group_name == 'tbody':
                    match = _COUNT_PERCENT.fullmatch(raw)
                    denominator_values = {
                        int(found.group('value')) for header in effective
                        for found in _DENOMINATOR.finditer(header)
                    }
                    if (match and len(denominator_values) == 1
                            and not footnote_refs and not cross_refs
                            and 'HEADER_FOOTNOTE_OR_CROSS_REFERENCE_PRESENT' not in cues
                            and not _FOOTNOTE_MARK.search(' '.join(effective))):
                        denominator = str(next(iter(denominator_values)))
                        percent = match.group('percent')
                        header_without_scope = [h for h in effective if not _DENOMINATOR.search(h)]
                        timepoint = next((m.group(0) for m in _TIMEPOINT.finditer(' '.join(effective))), None)
                        adjustment = 'adjusted' if re.search(r'\badjusted\b', table_context, re.IGNORECASE) else None
                        numeric_assertions.append(NumericAssertion(
                            value=percent,
                            unit='percent',
                            statistic_type='proportion_percent',
                            numerator=match.group('count'),
                            denominator=denominator,
                            population=None,
                            group=row_label or None,
                            outcome=' / '.join(header_without_scope) or None,
                            timepoint=timepoint,
                            adjustment_status=adjustment,
                            source_anchor=cell.source_anchor,
                            structural_provenance=(
                                'jats:table-wrap', f'table_id:{wrap.attributes.get("id", "")}',
                                f'thead_column:{start}', 'tbody_cell',
                            ),
                        ))
            source_rows.append(TableRow(group_name, row_index, tuple(cells)))

    denominator_header_cols = [
        col for col, header in enumerate(header_matrix)
        if any(_DENOMINATOR.search(item) for item in header)
    ]
    if not denominator_header_cols:
        limitations.append('No explicit column header supplies a denominator for count/percentage recomputation.')
    structure_status = 'STRUCTURE_RELIABLE' if not structural_problem and width > 0 else 'TABLE_STRUCTURE_UNSUPPORTED'
    confidence = 0.98 if structure_status == 'STRUCTURE_RELIABLE' else 0.45
    columns = tuple(TableColumn(index, header_matrix[index]) for index in range(width))
    table = Table(
        label=label,
        caption=caption,
        table_id=wrap.attributes.get('id', ''),
        wrap_metadata=tuple(sorted(wrap.attributes.items())),
        header_hierarchy=header_hierarchy,
        rows=tuple(source_rows),
        columns=columns,
        spans=tuple(spans),
        footnotes=tuple(footnotes),
        source_anchor=_anchor(wrap, source_file, source_digest, _node_text(wrap)),
        extraction_confidence=confidence,
        structure_status=structure_status,
        limitations=tuple(dict.fromkeys(limitations)),
    )
    return table, numeric_assertions


def _parents(node: _Node) -> Iterable[_Node]:
    parent = node.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def parse_jats(source: bytes, source_file: str = 'source.xml') -> PaperDocument:
    """Parse bounded JATS/XML without resolving DTDs, entities, or external resources."""
    root = _build_tree(source)
    digest = sha256(source).hexdigest()
    article_title_node = next((node for node in _descendants(root, {'article-title'})), None)
    title = _node_text(article_title_node)
    all_tables: list[Table] = []
    assertions: list[NumericAssertion] = []
    sections: list[Section] = []
    paragraphs: list[Paragraph] = []

    table_nodes = [node for node in _descendants(root, {'table-wrap'})]
    if len(table_nodes) > MAX_JATS_TABLES:
        raise Invalid('JATS source exceeded the configured table limit')
    table_cell_count = sum(
        1 for wrap in table_nodes for node in _descendants(wrap)
        if node.name in ('td', 'th', 'entry')
    )
    if table_cell_count > MAX_JATS_TABLE_CELLS:
        raise Invalid('JATS source exceeded the configured table-cell limit')
    footnote_nodes: dict[str, _Node] = {}
    for node in _descendants(root, {'fn'}):
        identifier = node.attributes.get('id')
        if not identifier:
            continue
        if identifier in footnote_nodes:
            raise Invalid('JATS source contains duplicate footnote identifiers')
        footnote_nodes[identifier] = node
    table_by_path: dict[str, Table] = {}
    for wrap in table_nodes:
        table, table_assertions = _table(wrap, source_file, digest, footnote_nodes)
        all_tables.append(table)
        assertions.extend(table_assertions)
        table_by_path[wrap.element_path] = table

    def paragraph_nodes(section_node: _Node) -> list[_Node]:
        found: list[_Node] = []
        stack = list(reversed(section_node.children))
        while stack:
            node = stack.pop()
            if node.name == 'sec' or node.name in ('table-wrap', 'fig', 'ref-list'):
                continue
            if node.name == 'p':
                found.append(node)
                continue
            stack.extend(reversed(node.children))
        return found

    def make_section(node: _Node, hierarchy: tuple[str, ...]) -> Section:
        title_node = next((child for child in node.children if child.name == 'title'), None)
        section_title = _node_text(title_node)
        current_hierarchy = hierarchy + ((section_title,) if section_title else ())
        own_paragraphs = tuple(
            Paragraph(_node_text(p), _anchor(p, source_file, digest, _node_text(p)))
            for p in paragraph_nodes(node) if _node_text(p)
        )
        paragraphs.extend(own_paragraphs)
        child_sections = tuple(make_section(child, current_hierarchy)
                               for child in node.children if child.name == 'sec')
        scoped_tables: list[_Node] = []
        todo = list(reversed(node.children))
        while todo:
            child = todo.pop()
            if child.name == 'sec':
                continue
            if child.name == 'table-wrap':
                scoped_tables.append(child)
                continue
            todo.extend(reversed(child.children))
        nested_table_ids = tuple(
            table_by_path[table_node.element_path].table_id
            for table_node in scoped_tables if table_node.element_path in table_by_path
        )
        quote = section_title or _node_text(node)[:1000]
        return Section(
            section_title,
            current_hierarchy,
            own_paragraphs,
            child_sections,
            nested_table_ids,
            _anchor(node, source_file, digest, quote),
        )

    abstract = next((node for node in _descendants(root, {'abstract'})), None)
    if abstract is not None:
        abstract_paragraphs = tuple(
            Paragraph(_node_text(p), _anchor(p, source_file, digest, _node_text(p)))
            for p in _descendants(abstract, {'p'}) if _node_text(p)
        )
        paragraphs.extend(abstract_paragraphs)
        sections.append(Section(
            'Abstract', ('Abstract',), abstract_paragraphs, (), (),
            _anchor(abstract, source_file, digest, _node_text(abstract)[:1000]),
        ))

    body = next((node for node in _descendants(root, {'body'})), None)
    if body is not None:
        for child in body.children:
            if child.name == 'sec':
                sections.append(make_section(child, ()))
            elif child.name == 'p' and _node_text(child):
                paragraph = Paragraph(_node_text(child), _anchor(child, source_file, digest, _node_text(child)))
                paragraphs.append(paragraph)
                sections.append(Section('', (), (paragraph,), (), (), _anchor(child, source_file, digest, paragraph.text)))

    warnings = []
    if not all_tables:
        warnings.append('No table-wrap elements were found in the JATS source.')
    if not sections:
        warnings.append('No abstract or body sections were found in the JATS source.')
    if len(paragraphs) > 100_000:
        raise Invalid('JATS source exceeded the configured paragraph limit')
    return PaperDocument(
        model_version='1.0',
        source_file=source_file,
        source_sha256=digest,
        source_format='jats_xml',
        title=title,
        sections=tuple(sections),
        paragraphs=tuple(paragraphs),
        tables=tuple(all_tables),
        numeric_assertions=tuple(assertions),
        extraction_warnings=tuple(warnings),
    )
