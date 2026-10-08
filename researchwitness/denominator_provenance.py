"""Source-anchored denominator candidates and fail-closed semantic resolution.

The resolver deliberately does not use arithmetic agreement to select a base.
It first gathers structurally applicable explicit candidates, compares their
source-described scopes, and only then permits percentage arithmetic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import re
from typing import Any, Iterable, Mapping

from .paper_document import HeaderCellReference, SourceAnchor, Table, TableCell, TableFootnote, TableRow

MAX_DENOMINATOR_CANDIDATES = 64
MAX_SCOPE_EVIDENCE = 8
MAX_SCOPE_TEXT = 240

PROVENANCE_CLASSES = (
    'CELL_LOCAL_EXPLICIT',
    'ROW_LOCAL_EXPLICIT',
    'SUBGROUP_ROW_EXPLICIT',
    'COLUMN_HEADER_EXPLICIT',
    'HEADER_GROUP_EXPLICIT',
    'TABLE_GLOBAL_EXPLICIT',
    'PROSE_CONTEXT_EXPLICIT',
)

SCOPE_FIELDS = (
    'population', 'subgroup', 'treatment_arm', 'timepoint',
    'analysis_set', 'outcome', 'unit', 'percentage_base',
)
_SCOPE_COMPARISON_FIELDS = (
    'population', 'subgroup', 'treatment_arm', 'timepoint',
    'analysis_set', 'outcome', 'unit', 'percentage_base',
)

_DENOMINATOR_TOKEN = re.compile(
    r'(?<![A-Za-z0-9_])[nN]\s*=\s*'
    r'(?P<value>[+\-−]?\d[\d,.eE+\-−]*(?:[ \u00a0\u202f]\d{3})*)',
)
_COUNT_PERCENT_PARENT = re.compile(
    r'^\s*(?P<count>[0-9]{1,9})\s*\(\s*'
    r'[0-9]{1,3}(?:\.[0-9]{1,6})?\s*%\s*\)\s*$'
)
_GROUPED_COMMA = re.compile(r'^[0-9]{1,3}(?:,[0-9]{3})+$')
_GROUPED_SPACE = re.compile(r'^[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+$')
_TIMEPOINT = re.compile(
    r'\b(?:baseline|follow[ -]?up|post[ -]?treatment|week\s*\d{1,4}|'
    r'month\s*\d{1,4}|year\s*\d{1,4}|day\s*\d{1,5})\b', re.IGNORECASE,
)
_ANALYSIS_SET = re.compile(
    r'\b(?:modified\s+intention.to.treat|intention.to.treat|ITT|'
    r'per.protocol|PP|as.treated|safety.population|complete.case|evaluable.population|'
    r'(?:Bayesian|frequentist)\s+(?:framework|analysis)(?:\s+only)?)\b',
    re.IGNORECASE,
)
_POPULATION = re.compile(
    r'\b(?:overall|all\s+(?:participants?|patients?|respondents?|subjects?|individuals?)|'
    r'entire\s+cohort|full\s+cohort|total\s+(?:population|cohort|sample))\b', re.IGNORECASE,
)
_UNIT = re.compile(r'\b(participants?|patients?|respondents?|subjects?|individuals?)\b', re.IGNORECASE)
_TREATMENT = re.compile(
    r'\b(?:treatment|intervention|control|comparator|placebo|arm\s*[A-Za-z0-9-]*)\b',
    re.IGNORECASE,
)
_BASE = re.compile(r'\b(?:percentage|percentages|proportion|proportions)\s+(?:of|based\s+on|among)\s+([^.;,]{1,120})', re.IGNORECASE)
_GENERIC_HEADER = {
    'outcome', 'outcomes', 'characteristic', 'characteristics', 'variable', 'variables',
    'group', 'groups', 'measure', 'measures', 'value', 'values', 'n', 'n (%)', 'n/n (%)',
    'count', 'counts', 'result', 'results', 'total', 'all', 'all studies',
}
_AGGREGATE_HEADER = re.compile(r'\b(?:all|overall|total|entire|full)\b', re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ScopeDimension:
    value: str | None
    status: str
    source_anchors: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            'value': self.value,
            'status': self.status,
            'source_anchors': list(self.source_anchors),
        }


@dataclass(frozen=True, slots=True)
class RelationshipScope:
    population: ScopeDimension
    subgroup: ScopeDimension
    treatment_arm: ScopeDimension
    timepoint: ScopeDimension
    analysis_set: ScopeDimension
    outcome: ScopeDimension
    unit: ScopeDimension
    percentage_base: ScopeDimension

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name).to_dict() for name in SCOPE_FIELDS}


@dataclass(frozen=True, slots=True)
class SubgroupBoundary:
    source_row_index: int
    applies_from_row: int
    applies_until_row: int
    label_cell: TableCell
    denominator_cells: tuple[TableCell, ...]
    scope_cells: tuple[TableCell, ...] = ()


@dataclass(frozen=True, slots=True)
class ParentCountGroup:
    """A source-structured heading whose parent count supplies a local base."""

    heading_row_index: int
    applies_from_row: int
    applies_until_row: int
    heading_cell: TableCell
    parent_label_cell: TableCell
    parent_count_cells: tuple[TableCell, ...]


def anchor_dict(anchor: SourceAnchor) -> dict[str, Any]:
    return asdict(anchor)


def _clean(value: str) -> str:
    value = _DENOMINATOR_TOKEN.sub(' ', value)
    value = re.sub(r'\b(?:n\s*\(%\)|n\s*/\s*n\s*\(%\))\b', ' ', value, flags=re.IGNORECASE)
    value = re.sub(r'\s+', ' ', value).strip(' \t\r\n,;:()[]{}')
    return value[:MAX_SCOPE_TEXT]


def _normalize(value: str) -> str:
    return re.sub(r'[^\w]+', ' ', value.casefold(), flags=re.UNICODE).strip()


def _dimension(values: list[tuple[str, SourceAnchor | None]]) -> ScopeDimension:
    normalized: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for raw, anchor in values:
        text = re.sub(r'\s+', ' ', raw).strip()[:MAX_SCOPE_TEXT]
        key = _normalize(text)
        if not key:
            continue
        display, anchors = normalized.setdefault(key, (text, []))
        if anchor is not None and len(anchors) < MAX_SCOPE_EVIDENCE:
            anchors.append(anchor_dict(anchor))
    if not normalized:
        return ScopeDimension(None, 'UNSTATED')
    if len(normalized) > 1:
        anchors = tuple(anchor for _display, group in normalized.values() for anchor in group)[:MAX_SCOPE_EVIDENCE]
        return ScopeDimension(None, 'AMBIGUOUS', anchors)
    value, anchors = next(iter(normalized.values()))
    return ScopeDimension(value, 'EXPLICIT', tuple(anchors))


def _hierarchical_dimension(values: list[tuple[str, SourceAnchor | None]]) -> ScopeDimension:
    ordered: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for raw, anchor in values:
        text = re.sub(r'\s+', ' ', raw).strip()[:MAX_SCOPE_TEXT]
        key = _normalize(text)
        if not key:
            continue
        display, anchors = ordered.setdefault(key, (text, []))
        if anchor is not None and len(anchors) < MAX_SCOPE_EVIDENCE:
            anchors.append(anchor_dict(anchor))
    if not ordered:
        return ScopeDimension(None, 'UNSTATED')
    displays = [item[0] for item in ordered.values()]
    anchors = tuple(anchor for _display, values in ordered.values() for anchor in values)[:MAX_SCOPE_EVIDENCE]
    return ScopeDimension(' / '.join(displays)[:MAX_SCOPE_TEXT], 'EXPLICIT', anchors)


def _is_generic_header(value: str) -> bool:
    return _normalize(value) in {_normalize(item) for item in _GENERIC_HEADER}


def _scope_from_fragments(
    fragments: Iterable[tuple[str, SourceAnchor | None, str]],
    *,
    subgroup_hint: tuple[str, SourceAnchor | None] | None = None,
    outcome_hint: tuple[str, SourceAnchor | None] | None = None,
) -> RelationshipScope:
    bounded = list(fragments)[:96]
    all_text = ' '.join(text[:MAX_SCOPE_TEXT] for text, _anchor, _role in bounded)
    population_values: list[tuple[str, SourceAnchor | None]] = []
    time_values: list[tuple[str, SourceAnchor | None]] = []
    analysis_values: list[tuple[str, SourceAnchor | None]] = []
    arm_values: list[tuple[str, SourceAnchor | None]] = []
    unit_values: list[tuple[str, SourceAnchor | None]] = []
    base_values: list[tuple[str, SourceAnchor | None]] = []
    subgroup_values: list[tuple[str, SourceAnchor | None]] = []

    for raw, anchor, role in bounded:
        text = raw[:MAX_SCOPE_TEXT]
        for match in _POPULATION.finditer(text):
            population_values.append((match.group(0), anchor))
        for match in _TIMEPOINT.finditer(text):
            time_values.append((re.sub(r'\s+', ' ', match.group(0)).casefold(), anchor))
        for match in _ANALYSIS_SET.finditer(text):
            analysis_values.append((re.sub(r'\s+', ' ', match.group(0)).casefold(), anchor))
        if role in ('header', 'subgroup') and _TREATMENT.search(text):
            arm_values.append((_clean(text), anchor))
        for match in _UNIT.finditer(text):
            unit_values.append((match.group(1).casefold().rstrip('s'), anchor))
        for match in _BASE.finditer(text):
            base_values.append((_clean(match.group(1)), anchor))

        cleaned = _clean(text)
        if role == 'header' and cleaned and not _is_generic_header(cleaned):
            if not _POPULATION.search(cleaned) and not _TREATMENT.search(cleaned) \
                    and not _TIMEPOINT.search(cleaned) and not _ANALYSIS_SET.search(cleaned):
                subgroup_values.append((cleaned, anchor))

    if subgroup_hint is not None and subgroup_hint[0].strip():
        cleaned = _clean(subgroup_hint[0])
        if cleaned and not _POPULATION.search(cleaned) and not _TREATMENT.search(cleaned) \
                and not _TIMEPOINT.search(cleaned) and not _ANALYSIS_SET.search(cleaned):
            subgroup_values.append((cleaned, subgroup_hint[1]))

    outcome_values: list[tuple[str, SourceAnchor | None]] = []
    if outcome_hint is not None and outcome_hint[0].strip():
        outcome_values.append((_clean(outcome_hint[0]) or outcome_hint[0][:MAX_SCOPE_TEXT], outcome_hint[1]))

    return RelationshipScope(
        population=_dimension(population_values),
        subgroup=_hierarchical_dimension(subgroup_values),
        treatment_arm=_hierarchical_dimension(arm_values),
        timepoint=_dimension(time_values),
        analysis_set=_dimension(analysis_values),
        outcome=_dimension(outcome_values),
        unit=_dimension(unit_values),
        percentage_base=_dimension(base_values),
    )


def _table_fragments(table: Table) -> list[tuple[str, SourceAnchor | None, str]]:
    result: list[tuple[str, SourceAnchor | None, str]] = []
    if table.label:
        result.append((table.label, table.label_anchor, 'table'))
    if table.caption:
        result.append((table.caption, table.caption_anchor, 'table'))
    return result


def _header_fragments(cell: TableCell, up_to_row: int | None = None) -> list[tuple[str, SourceAnchor | None, str]]:
    refs = sorted(cell.effective_header_refs, key=lambda item: (item.row_index, item.column_start))
    if up_to_row is not None:
        refs = [item for item in refs if item.row_index <= up_to_row]
    return [(item.text, item.source_anchor, 'header') for item in refs[:64]]


def _row_label(row: TableRow) -> TableCell | None:
    return next((item for item in row.cells if item.column_start == 0), None)


def _row_denominator_applies_to_cell(table: Table, cell: TableCell) -> bool:
    """A row-label n is the aggregate row base, not a replacement for a stratified column base."""
    denominator_headers = [
        ref for ref in cell.effective_header_refs if _DENOMINATOR_TOKEN.search(ref.text)
    ]
    if not denominator_headers:
        return True
    if all(_AGGREGATE_HEADER.search(ref.text) is not None for ref in denominator_headers):
        return True

    table_headers: dict[tuple[str, str], HeaderCellReference] = {}
    for row in table.rows:
        for header_cell in row.cells:
            for ref in header_cell.effective_header_refs:
                if _DENOMINATOR_TOKEN.search(ref.text):
                    table_headers[(ref.source_anchor.element_path, ref.text)] = ref
    aggregate_headers = [
        ref for ref in table_headers.values() if _AGGREGATE_HEADER.search(ref.text)
    ]
    stratified_headers = [
        ref for ref in table_headers.values() if _AGGREGATE_HEADER.search(ref.text) is None
    ]
    # A row-label n spans only the aggregate column when the table explicitly
    # partitions that aggregate into separately based strata.
    stratified_partition = bool(aggregate_headers and len(stratified_headers) > 1)
    return not stratified_partition


def relationship_scope(
    table: Table,
    row: TableRow,
    cell: TableCell,
    subgroup_label: TableCell | None = None,
    linked_footnote_texts: Iterable[tuple[str, SourceAnchor]] = (),
) -> RelationshipScope:
    label_cell = _row_label(row)
    fragments = _table_fragments(table) + _header_fragments(cell)
    row_n_applies = label_cell is None or not _DENOMINATOR_TOKEN.search(label_cell.raw_text) \
        or _row_denominator_applies_to_cell(table, cell)
    if label_cell is not None and row_n_applies:
        fragments.append((label_cell.raw_text, label_cell.source_anchor, 'row'))
    fragments.append((cell.raw_text, cell.source_anchor, 'cell'))
    if subgroup_label is not None:
        fragments.append((subgroup_label.raw_text, subgroup_label.source_anchor, 'subgroup'))
    fragments.extend((text, anchor, 'footnote') for text, anchor in list(linked_footnote_texts)[:8])
    hint = None
    if subgroup_label is not None:
        hint = (subgroup_label.raw_text, subgroup_label.source_anchor)
    elif label_cell is not None and _DENOMINATOR_TOKEN.search(label_cell.raw_text) and row_n_applies:
        hint = (label_cell.raw_text, label_cell.source_anchor)
    return _scope_from_fragments(
        fragments,
        subgroup_hint=hint,
        outcome_hint=(label_cell.raw_text, label_cell.source_anchor)
        if label_cell and hint is None and row_n_applies else None,
    )


def _parse_value(raw: str) -> tuple[str | None, str | None]:
    token = raw.strip()
    if _GROUPED_COMMA.fullmatch(token) or _GROUPED_SPACE.fullmatch(token):
        return None, 'GROUPED_INTEGER_FORMAT_UNSUPPORTED'
    if ',' in token:
        return None, 'DECIMAL_SEPARATOR_UNSUPPORTED'
    if any(character.isdigit() and character not in '0123456789' for character in token):
        return None, 'MALFORMED_NUMERIC_TOKEN'
    if re.fullmatch(r'-[0-9]{1,9}', token):
        return None, 'OPERANDS_OUTSIDE_PROPORTION_DOMAIN'
    if not re.fullmatch(r'[0-9]{1,9}', token):
        return None, 'MALFORMED_NUMERIC_TOKEN'
    value = int(token)
    if value <= 0:
        return None, 'OPERANDS_OUTSIDE_PROPORTION_DOMAIN'
    return str(value), None


def _candidate(
    *,
    raw_value: str,
    anchor: SourceAnchor,
    provenance_class: str,
    structural_source: str,
    scope: RelationshipScope,
    applies_to: Mapping[str, Any],
    footnote_linkage: Iterable[str] = (),
    occurrence: int = 0,
    forced_reasons: Iterable[str] = (),
) -> dict[str, Any]:
    exact, parse_reason = _parse_value(raw_value)
    reasons = list(dict.fromkeys([*forced_reasons, *([parse_reason] if parse_reason else [])]))
    source_key = '\0'.join((anchor.source_sha256, anchor.element_path, provenance_class, str(occurrence), raw_value))
    return {
        'candidate_id': sha256(source_key.encode('utf-8')).hexdigest(),
        'value_exact': exact,
        'raw_value': raw_value[:80],
        'source_anchor': anchor_dict(anchor),
        'structural_source': structural_source,
        'semantic_scope': scope.to_dict(),
        'provenance_class': provenance_class,
        'applicability': dict(applies_to),
        'footnote_linkage': list(dict.fromkeys(footnote_linkage))[:16],
        'confidence': 'HIGH' if not reasons else 'LOW',
        'eligibility': 'INELIGIBLE' if reasons else 'ELIGIBLE',
        'precedence_class': 'SEMANTIC_SCOPE_SPECIFICITY',
        'structural_directness': {
            'CELL_LOCAL_EXPLICIT': 7,
            'ROW_LOCAL_EXPLICIT': 6,
            'SUBGROUP_ROW_EXPLICIT': 5,
            'COLUMN_HEADER_EXPLICIT': 4,
            'HEADER_GROUP_EXPLICIT': 3,
            'TABLE_GLOBAL_EXPLICIT': 2,
            'PROSE_CONTEXT_EXPLICIT': 1,
        }.get(provenance_class, 0),
        'scope_match': {'matching_fields': [], 'unmatched_relationship_fields': [], 'conflicting_fields': []},
        'rejection_reasons': reasons,
    }


def _missing_candidate(
    *,
    anchor: SourceAnchor,
    provenance_class: str,
    structural_source: str,
    scope: RelationshipScope,
    applies_to: Mapping[str, Any],
    raw_value: str = '',
) -> dict[str, Any]:
    source_key = '\0'.join((
        anchor.source_sha256, anchor.element_path, provenance_class, 'missing', raw_value,
    ))
    return {
        'candidate_id': sha256(source_key.encode('utf-8')).hexdigest(),
        'value_exact': None,
        'raw_value': raw_value[:80],
        'source_anchor': anchor_dict(anchor),
        'structural_source': structural_source,
        'semantic_scope': scope.to_dict(),
        'provenance_class': provenance_class,
        'applicability': dict(applies_to),
        'footnote_linkage': [],
        'confidence': 'LOW',
        'eligibility': 'INELIGIBLE',
        'precedence_class': 'SEMANTIC_SCOPE_SPECIFICITY',
        'structural_directness': 5,
        'scope_match': {'matching_fields': [], 'unmatched_relationship_fields': [], 'conflicting_fields': []},
        'rejection_reasons': ['DENOMINATOR_NOT_EXPLICIT'],
    }


def _token_candidates(text: str, anchor: SourceAnchor, **kwargs: Any) -> list[dict[str, Any]]:
    output = []
    for index, match in enumerate(_DENOMINATOR_TOKEN.finditer(text)):
        output.append(_candidate(raw_value=match.group('value'), anchor=anchor, occurrence=index, **kwargs))
    return output[:MAX_DENOMINATOR_CANDIDATES]


def _is_denominator_boundary_row(row: TableRow) -> tuple[TableCell | None, list[TableCell]]:
    label = _row_label(row)
    if label is None or not label.raw_text.strip():
        return None, []
    denominator_cells: list[TableCell] = []
    valid = True
    for item in row.cells:
        if item.column_start == 0:
            continue
        raw = item.raw_text.strip()
        if not raw or raw in {'-', '–', '—', '−'}:
            continue
        if _DENOMINATOR_TOKEN.search(raw):
            residue = _DENOMINATOR_TOKEN.sub('', raw).strip(' ,;:()[]{}')
            if residue and not item.footnote_references and not item.cross_references:
                valid = False
                break
            denominator_cells.append(item)
            continue
        valid = False
        break
    return (label, denominator_cells) if valid and denominator_cells else (None, [])


def _is_label_only_group_row(row: TableRow) -> TableCell | None:
    label = _row_label(row)
    if label is None or not label.raw_text.strip() or label.indentation_level:
        return None
    if any(cell.raw_text.strip() not in {'', '-', '–', '—', '−'}
           for cell in row.cells if cell.column_start > 0):
        return None
    return label


def _same_parent_label(parent: str, heading: str) -> bool:
    parent_words = _normalize(_clean(parent)).split()
    heading_words = _normalize(_clean(heading)).split()
    if not parent_words or len(heading_words) <= len(parent_words):
        return False
    return heading_words[:len(parent_words)] == parent_words


def parent_count_groups(table: Table) -> tuple[ParentCountGroup, ...]:
    """Bind indented child rows to an immediately preceding, source-labelled group.

    The denominator is the printed count in the parent row; no sibling-count
    addition or percentage matching is used. A lexical exclusion label ends
    the group so complementary rows such as “Not exposed” retain their own base.
    """
    rows = table.rows
    groups: list[ParentCountGroup] = []
    for heading_index, heading_row in enumerate(rows):
        if heading_row.row_group != 'tbody':
            continue
        heading = _is_label_only_group_row(heading_row)
        if heading is None or heading_index == 0:
            continue
        parent_index = heading_index - 1
        parent_row = rows[parent_index]
        if parent_row.row_group != 'tbody':
            continue
        parent_label = _row_label(parent_row)
        if parent_label is None or not _same_parent_label(parent_label.raw_text, heading.raw_text):
            continue
        parent_cells = tuple(
            cell for cell in parent_row.cells
            if cell.column_start > 0 and _COUNT_PERCENT_PARENT.fullmatch(cell.raw_text)
        )
        if not parent_cells:
            continue

        end = len(rows)
        for following_index in range(heading_index + 1, len(rows)):
            following = rows[following_index]
            if following.row_group != 'tbody':
                end = following_index
                break
            following_label = _row_label(following)
            if following_label is None:
                end = following_index
                break
            label_text = following_label.raw_text.strip()
            if (_is_label_only_group_row(following) is not None
                    or re.match(r'^(?:not|no|without|excluding|except)\b', label_text, re.IGNORECASE)):
                end = following_index
                break
            if following_label.indentation_level <= heading.indentation_level:
                end = following_index
                break
        groups.append(ParentCountGroup(
            heading_row_index=heading_index,
            applies_from_row=heading_index + 1,
            applies_until_row=end,
            heading_cell=heading,
            parent_label_cell=parent_label,
            parent_count_cells=parent_cells,
        ))
    return tuple(groups[:10_000])


def _active_parent_count_groups(
    groups: tuple[ParentCountGroup, ...],
    target_row_index: int,
) -> tuple[ParentCountGroup, ...]:
    return tuple(
        item for item in groups
        if item.applies_from_row <= target_row_index < item.applies_until_row
    )[-MAX_SCOPE_EVIDENCE:]


def subgroup_boundaries(table: Table) -> tuple[SubgroupBoundary, ...]:
    rows = [(index, row) for index, row in enumerate(table.rows) if row.row_group == 'tbody']
    boundaries: list[tuple[int, TableCell, tuple[TableCell, ...]]] = []
    for row_index, row in rows:
        label, cells = _is_denominator_boundary_row(row)
        if label is not None:
            boundaries.append((row_index, label, tuple(cells)))
    result: list[SubgroupBoundary] = []
    for position, (row_index, label, cells) in enumerate(boundaries):
        next_boundary = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(table.rows)
        end = next_boundary
        for next_index, next_row in rows:
            if row_index < next_index < next_boundary:
                next_label = _row_label(next_row)
                other_values = [item.raw_text.strip() for item in next_row.cells if item.column_start > 0]
                if (not any(item.raw_text.strip() for item in next_row.cells)
                        or (next_label is not None and next_label.raw_text.strip() and not any(other_values))):
                    end = next_index
                    break
        scope_cells = tuple(cell for cell in row.cells if cell.column_start > 0)
        result.append(SubgroupBoundary(row_index, row_index + 1, end, label, cells, scope_cells))
    return tuple(result[:10_000])


def _active_boundary(boundaries: tuple[SubgroupBoundary, ...], row_index: int) -> SubgroupBoundary | None:
    active = [item for item in boundaries if item.applies_from_row <= row_index < item.applies_until_row]
    return active[-1] if active else None


def _linked_footnotes(
    table: Table,
    cell: TableCell,
    row: TableRow,
) -> list[TableFootnote]:
    reference_ids = set(cell.footnote_references)
    label = _row_label(row)
    if label is not None:
        reference_ids.update(label.footnote_references)
    for header in cell.effective_header_refs:
        reference_ids.update(header.footnote_references)
    return [
        note for note in table.footnotes
        if note.identifier and note.identifier in reference_ids
    ][:8]


def _scope_candidates(
    table: Table,
    cell: TableCell,
    row: TableRow,
    row_index: int,
    subgroup: SubgroupBoundary | None,
    parent_groups: tuple[ParentCountGroup, ...],
    explicit_cell_denominator: str | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    active_parent_groups = _active_parent_count_groups(parent_groups, row_index)
    subgroup_label = (
        subgroup.label_cell if subgroup is not None else
        active_parent_groups[-1].heading_cell if active_parent_groups else None
    )
    relation = relationship_scope(
        table, row, cell, subgroup_label,
        ((note.text, note.source_anchor) for note in _linked_footnotes(table, cell, row)),
    )
    row_end = row_index + 1
    applicable_row = {'row_start': row_index, 'row_end_exclusive': row_end,
                      'column_start': 0, 'column_end_exclusive': len(table.columns)}

    # A denominator written in the percentage cell has the narrowest explicit
    # structural applicability and is resolved before any arithmetic.
    candidates.extend(_token_candidates(
        cell.raw_text, cell.source_anchor, provenance_class='CELL_LOCAL_EXPLICIT',
        structural_source='same JATS data cell', scope=relation,
        applies_to={**applicable_row, 'column_start': cell.column_start,
                    'column_end_exclusive': cell.column_start + cell.column_span},
        footnote_linkage=cell.footnote_references,
        forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED'] if cell.footnote_references or cell.cross_references else []),
    ))
    if explicit_cell_denominator is not None:
        candidates.append(_candidate(
            raw_value=explicit_cell_denominator,
            anchor=cell.source_anchor,
            provenance_class='CELL_LOCAL_EXPLICIT',
            structural_source='same JATS cell explicit numerator/denominator ratio',
            scope=relation,
            applies_to={**applicable_row, 'column_start': cell.column_start,
                        'column_end_exclusive': cell.column_start + cell.column_span},
            footnote_linkage=cell.footnote_references,
            forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED']
                            if cell.footnote_references or cell.cross_references else []),
        ))

    label = _row_label(row)
    if label is not None and _DENOMINATOR_TOKEN.search(label.raw_text):
        label_scope_fragments = _table_fragments(table) + _header_fragments(cell)
        label_scope_fragments.append((label.raw_text, label.source_anchor, 'row'))
        label_scope = _scope_from_fragments(
            label_scope_fragments,
            subgroup_hint=(label.raw_text, label.source_anchor),
        )
        row_label_applicability = (
            {**applicable_row, 'column_start': 0, 'column_end_exclusive': len(table.columns)}
            if _row_denominator_applies_to_cell(table, cell)
            else {**applicable_row, 'column_start': 0, 'column_end_exclusive': 0}
        )
        candidates.extend(_token_candidates(
            label.raw_text, label.source_anchor, provenance_class='ROW_LOCAL_EXPLICIT',
            structural_source='same JATS row label', scope=label_scope,
            applies_to=row_label_applicability,
            footnote_linkage=label.footnote_references,
            forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED']
                            if label.footnote_references or label.cross_references else []),
        ))

    for sibling in row.cells:
        if (sibling is cell or sibling.column_start == 0
                or not _DENOMINATOR_TOKEN.search(sibling.raw_text)):
            continue
        candidate_scope = relation
        candidates.extend(_token_candidates(
            sibling.raw_text, sibling.source_anchor, provenance_class='ROW_LOCAL_EXPLICIT',
            structural_source='same JATS table row', scope=candidate_scope,
            applies_to={**applicable_row, 'column_start': sibling.column_start,
                        'column_end_exclusive': sibling.column_start + sibling.column_span},
            footnote_linkage=sibling.footnote_references,
            forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED'] if sibling.footnote_references or sibling.cross_references else []),
        ))

    if subgroup is not None:
        subgroup_scope_fragments = _table_fragments(table) + _header_fragments(cell) + [
            (subgroup.label_cell.raw_text, subgroup.label_cell.source_anchor, 'subgroup'),
        ]
        subgroup_scope = _scope_from_fragments(
            subgroup_scope_fragments,
            subgroup_hint=(subgroup.label_cell.raw_text, subgroup.label_cell.source_anchor),
        )
        for denominator_cell in subgroup.denominator_cells:
            candidates.extend(_token_candidates(
                denominator_cell.raw_text, denominator_cell.source_anchor,
                provenance_class='SUBGROUP_ROW_EXPLICIT',
                structural_source='explicit denominator row bounding this subgroup',
                scope=subgroup_scope,
                applies_to={'row_start': subgroup.applies_from_row,
                            'row_end_exclusive': subgroup.applies_until_row,
                            'column_start': denominator_cell.column_start,
                            'column_end_exclusive': denominator_cell.column_start + denominator_cell.column_span},
                footnote_linkage=denominator_cell.footnote_references,
                forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED'] if denominator_cell.footnote_references
                                or denominator_cell.cross_references else []),
            ))
        if not any(
            item.column_start <= cell.column_identity < item.column_start + item.column_span
            for item in subgroup.denominator_cells
        ):
            scope_cell = next((
                item for item in subgroup.scope_cells
                if item.column_start <= cell.column_identity < item.column_start + item.column_span
            ), subgroup.label_cell)
            candidates.append(_missing_candidate(
                anchor=scope_cell.source_anchor,
                provenance_class='SUBGROUP_ROW_EXPLICIT',
                structural_source='explicit subgroup denominator boundary has no value for this column',
                scope=subgroup_scope,
                applies_to={'row_start': subgroup.applies_from_row,
                            'row_end_exclusive': subgroup.applies_until_row,
                            'column_start': cell.column_identity,
                            'column_end_exclusive': cell.column_identity + cell.column_span},
                raw_value=scope_cell.raw_text,
            ))

    for parent_group in active_parent_groups:
        matching_parent_cell = False
        for parent_cell in parent_group.parent_count_cells:
            if not (parent_cell.column_start <= cell.column_identity
                    < parent_cell.column_start + parent_cell.column_span):
                continue
            match = _COUNT_PERCENT_PARENT.fullmatch(parent_cell.raw_text)
            if match is None:
                continue
            matching_parent_cell = True
            parent_scope = _scope_from_fragments(
                _table_fragments(table) + _header_fragments(cell) + [
                    (parent_group.parent_label_cell.raw_text,
                     parent_group.parent_label_cell.source_anchor, 'row'),
                    (parent_group.heading_cell.raw_text,
                     parent_group.heading_cell.source_anchor, 'subgroup'),
                ],
                subgroup_hint=(parent_group.heading_cell.raw_text,
                              parent_group.heading_cell.source_anchor),
            )
            candidates.append(_candidate(
                raw_value=match.group('count'),
                anchor=parent_cell.source_anchor,
                provenance_class='SUBGROUP_ROW_EXPLICIT',
                structural_source='printed count in the parent row of a source-structured subgroup',
                scope=parent_scope,
                applies_to={'row_start': parent_group.applies_from_row,
                            'row_end_exclusive': parent_group.applies_until_row,
                            'column_start': parent_cell.column_start,
                            'column_end_exclusive': parent_cell.column_start + parent_cell.column_span,
                            'group_heading_row_index': parent_group.heading_row_index,
                            'parent_count_row_index': parent_group.heading_row_index - 1},
                footnote_linkage=parent_cell.footnote_references,
                forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED']
                                if parent_cell.footnote_references or parent_cell.cross_references else []),
            ))
        if not matching_parent_cell:
            parent_scope = _scope_from_fragments(
                _table_fragments(table) + _header_fragments(cell) + [
                    (parent_group.parent_label_cell.raw_text,
                     parent_group.parent_label_cell.source_anchor, 'row'),
                    (parent_group.heading_cell.raw_text,
                     parent_group.heading_cell.source_anchor, 'subgroup'),
                ],
                subgroup_hint=(parent_group.heading_cell.raw_text,
                              parent_group.heading_cell.source_anchor),
            )
            candidates.append(_missing_candidate(
                anchor=parent_group.heading_cell.source_anchor,
                provenance_class='SUBGROUP_ROW_EXPLICIT',
                structural_source='source-structured subgroup parent has no printed count for this column',
                scope=parent_scope,
                applies_to={'row_start': parent_group.applies_from_row,
                            'row_end_exclusive': parent_group.applies_until_row,
                            'column_start': cell.column_identity,
                            'column_end_exclusive': cell.column_identity + cell.column_span,
                            'group_heading_row_index': parent_group.heading_row_index,
                            'parent_count_row_index': parent_group.heading_row_index - 1},
                raw_value='',
            ))

    for ref in cell.effective_header_refs:
        if not _DENOMINATOR_TOKEN.search(ref.text):
            continue
        header_scope = _scope_from_fragments(
            _table_fragments(table) + _header_fragments(cell, ref.row_index),
        )
        provenance = 'HEADER_GROUP_EXPLICIT' if ref.column_span > 1 or ref.row_span > 1 else 'COLUMN_HEADER_EXPLICIT'
        candidates.extend(_token_candidates(
            ref.text, ref.source_anchor, provenance_class=provenance,
            structural_source='JATS thead cell covering the target column',
            scope=header_scope,
            applies_to={'row_start': 0, 'row_end_exclusive': len(table.rows),
                        'column_start': ref.column_start,
                        'column_end_exclusive': ref.column_start + ref.column_span,
                        'header_row_index': ref.row_index,
                        'header_row_span': ref.row_span,
                        'header_column_span': ref.column_span},
            forced_reasons=(['FOOTNOTE_SCOPE_UNRESOLVED']
                            if ref.footnote_references or ref.cross_references else []),
        ))

    for text, anchor in ((table.label, table.label_anchor), (table.caption, table.caption_anchor)):
        if text and anchor is not None and _DENOMINATOR_TOKEN.search(text):
            global_scope = _scope_from_fragments([(text, anchor, 'table')])
            candidates.extend(_token_candidates(
                text, anchor, provenance_class='TABLE_GLOBAL_EXPLICIT',
                structural_source='JATS table label or caption', scope=global_scope,
                applies_to={'row_start': 0, 'row_end_exclusive': len(table.rows),
                            'column_start': 0, 'column_end_exclusive': len(table.columns)},
            ))

    linked_ids = {note.identifier for note in _linked_footnotes(table, cell, row)
                  if note.identifier}
    for note in table.footnotes:
        if not _DENOMINATOR_TOKEN.search(note.text):
            continue
        linked = note.identifier is not None and note.identifier in linked_ids
        if not linked:
            continue
        note_scope = _scope_from_fragments(_table_fragments(table) + [(note.text, note.source_anchor, 'footnote')])
        candidates.extend(_token_candidates(
            note.text, note.source_anchor, provenance_class='PROSE_CONTEXT_EXPLICIT',
            structural_source='JATS table footnote', scope=note_scope,
            applies_to={'row_start': row_index if linked else 0,
                        'row_end_exclusive': row_end if linked else len(table.rows),
                        'column_start': cell.column_start if linked else 0,
                        'column_end_exclusive': cell.column_start + cell.column_span if linked else len(table.columns)},
            footnote_linkage=[note.identifier] if linked and note.identifier else [],
            forced_reasons=['FOOTNOTE_SCOPE_UNRESOLVED'],
        ))

    # Repeated IDs and duplicated source text remain distinct candidate
    # anchors; they must not be collapsed merely because their values match.
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates[:MAX_DENOMINATOR_CANDIDATES + 1]:
        unique[candidate['candidate_id']] = candidate
    return list(unique.values())[:MAX_DENOMINATOR_CANDIDATES]


def _compare_scopes(relationship: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[list[str], list[str], list[str], tuple[int, int, int]]:
    matching: list[str] = []
    unverified: list[str] = []
    conflicting: list[str] = []
    candidate_specificity = 0
    missing = 0
    for field in _SCOPE_COMPARISON_FIELDS:
        rel = relationship[field]
        cand = candidate[field]
        rel_known = rel['status'] == 'EXPLICIT' and rel.get('value') is not None
        cand_known = cand['status'] == 'EXPLICIT' and cand.get('value') is not None
        if rel['status'] == 'AMBIGUOUS' or cand['status'] == 'AMBIGUOUS':
            unverified.append(field)
            continue
        if cand_known:
            if not rel_known:
                candidate_specificity += 1
                unverified.append(field)
            elif field in ('subgroup', 'treatment_arm'):
                rel_path = [_normalize(part) for part in str(rel['value']).split(' / ')]
                cand_path = [_normalize(part) for part in str(cand['value']).split(' / ')]
                if cand_path == rel_path[:len(cand_path)]:
                    matching.append(field)
                    candidate_specificity += len(cand_path)
                else:
                    conflicting.append(field)
            elif _normalize(str(rel['value'])) != _normalize(str(cand['value'])):
                candidate_specificity += 1
                conflicting.append(field)
            else:
                candidate_specificity += 1
                matching.append(field)
        elif rel_known:
            missing += 1
    return matching, unverified, conflicting, (len(matching), candidate_specificity, -missing)


def resolve_denominator(
    table: Table,
    row: TableRow,
    cell: TableCell,
    row_index: int,
    boundaries: tuple[SubgroupBoundary, ...],
    parent_groups: tuple[ParentCountGroup, ...],
    explicit_cell_denominator: str | None = None,
) -> dict[str, Any]:
    subgroup = _active_boundary(boundaries, row_index)
    active_parent_groups = _active_parent_count_groups(parent_groups, row_index)
    subgroup_label = (
        subgroup.label_cell if subgroup is not None else
        active_parent_groups[-1].heading_cell if active_parent_groups else None
    )
    candidates = _scope_candidates(
        table, cell, row, row_index, subgroup, parent_groups, explicit_cell_denominator,
    )
    linked_notes = _linked_footnotes(table, cell, row)
    scope = relationship_scope(
        table, row, cell, subgroup_label,
        ((note.text, note.source_anchor) for note in linked_notes),
    ).to_dict()

    if len(candidates) >= MAX_DENOMINATOR_CANDIDATES:
        return {
            'denominator_scope_resolved': False,
            'denominator_provenance': {
                'resolution_status': 'UNRESOLVED',
                'resolution_reason': 'DENOMINATOR_CANDIDATE_LIMIT',
                'relationship_scope': scope,
                'selected_denominator': None,
                'rejected_competing_denominators': [
                    {**item, 'rejection_reasons': list(dict.fromkeys(item['rejection_reasons'] + ['DENOMINATOR_CANDIDATE_LIMIT']))}
                    for item in candidates
                ],
            },
            'skip_reasons': ['DENOMINATOR_CANDIDATE_LIMIT'],
        }

    applicable = []
    rejected: list[dict[str, Any]] = []
    ranks: dict[str, tuple[int, int, int]] = {}
    for item in candidates:
        applies = item['applicability']
        if not (applies.get('row_start', 0) <= row_index < applies.get('row_end_exclusive', len(table.rows))
                and applies.get('column_start', 0) <= cell.column_identity < applies.get('column_end_exclusive', len(table.columns))):
            item['rejection_reasons'] = ['NOT_STRUCTURALLY_APPLICABLE']
            item['eligibility'] = 'INELIGIBLE'
            rejected.append(item)
            continue
        matching, unverified, conflicting, rank = _compare_scopes(scope, item['semantic_scope'])
        item['scope_match'] = {
            'matching_fields': matching,
            'unmatched_relationship_fields': unverified,
            'conflicting_fields': conflicting,
        }
        rank = (*rank, int(item.get('structural_directness', 0)))
        ranks[item['candidate_id']] = rank
        if conflicting:
            item['rejection_reasons'] = list(dict.fromkeys(item['rejection_reasons'] + ['DENOMINATOR_SCOPE_MISMATCH']))
            item['eligibility'] = 'INELIGIBLE'
            rejected.append(item)
        elif unverified:
            item['rejection_reasons'] = list(dict.fromkeys(item['rejection_reasons'] + ['DENOMINATOR_SCOPE_UNRESOLVED']))
            item['eligibility'] = 'INELIGIBLE'
            rejected.append(item)
        else:
            applicable.append(item)

    valid = [item for item in applicable if item['eligibility'] == 'ELIGIBLE' and item['value_exact'] is not None]
    invalid = [item for item in applicable if item not in valid]
    skip_reasons: list[str] = []
    applicable_candidate_count = sum(
        1 for item in candidates if 'NOT_STRUCTURALLY_APPLICABLE' not in item.get('rejection_reasons', [])
    )
    if not candidates or applicable_candidate_count == 0:
        skip_reasons.append('DENOMINATOR_NOT_EXPLICIT')
        resolution_status = 'UNRESOLVED'
        resolution_reason = 'DENOMINATOR_NOT_EXPLICIT'
        selected = None
    elif not valid:
        reasons = [
            reason for item in candidates for reason in item.get('rejection_reasons', [])
            if reason != 'NOT_STRUCTURALLY_APPLICABLE'
        ]
        if not reasons or all(reason == 'NOT_STRUCTURALLY_APPLICABLE' for reason in reasons):
            reasons = ['DENOMINATOR_SCOPE_UNRESOLVED']
        skip_reasons.extend(reasons)
        resolution_status = 'UNRESOLVED'
        resolution_reason = next((reason for reason in (
            'FOOTNOTE_SCOPE_UNRESOLVED', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED',
            'DECIMAL_SEPARATOR_UNSUPPORTED', 'MALFORMED_NUMERIC_TOKEN',
            'OPERANDS_OUTSIDE_PROPORTION_DOMAIN', 'DENOMINATOR_SCOPE_UNRESOLVED',
            'DENOMINATOR_SCOPE_MISMATCH', 'DENOMINATOR_NOT_EXPLICIT',
        ) if reason in reasons), 'DENOMINATOR_SCOPE_UNRESOLVED')
        selected = None
    else:
        best_rank = max(ranks[item['candidate_id']] for item in valid)
        top = [item for item in valid if ranks[item['candidate_id']] == best_rank]
        blocking_invalid = [item for item in invalid if ranks.get(item['candidate_id'], (-1, -1, -1)) >= best_rank]
        if blocking_invalid:
            reasons = [
                reason for item in blocking_invalid for reason in item['rejection_reasons']
                if reason != 'NOT_STRUCTURALLY_APPLICABLE'
            ]
            skip_reasons.extend(reasons or ['DENOMINATOR_SCOPE_UNRESOLVED'])
            resolution_status = 'UNRESOLVED'
            resolution_reason = next((reason for reason in (
                'FOOTNOTE_SCOPE_UNRESOLVED', 'GROUPED_INTEGER_FORMAT_UNSUPPORTED',
                'DECIMAL_SEPARATOR_UNSUPPORTED', 'MALFORMED_NUMERIC_TOKEN',
                'OPERANDS_OUTSIDE_PROPORTION_DOMAIN', 'DENOMINATOR_SCOPE_UNRESOLVED',
            ) if reason in reasons), 'DENOMINATOR_SCOPE_UNRESOLVED')
            selected = None
        elif len(top) > 1:
            skip_reasons.append('DENOMINATOR_AMBIGUOUS')
            resolution_status = 'AMBIGUOUS'
            resolution_reason = 'DENOMINATOR_AMBIGUOUS'
            selected = None
            for item in top:
                item['rejection_reasons'] = ['DENOMINATOR_AMBIGUOUS']
                item['eligibility'] = 'AMBIGUOUS'
                rejected.append(item)
            for item in valid:
                if item not in top:
                    item['rejection_reasons'] = ['BROADER_SCOPE_THAN_AMBIGUOUS_CANDIDATE']
                    rejected.append(item)
        else:
            selected = top[0]
            selected['rejection_reasons'] = []
            selected['precedence_class'] = (
                f"SEMANTIC_SCOPE_MATCHES_{best_rank[0]}_STRUCTURAL_APPLICABILITY_{best_rank[3]}"
            )
            resolution_status = 'RESOLVED'
            resolution_reason = 'UNIQUE_MOST_SPECIFIC_EXPLICIT_SCOPE'
            for item in valid:
                if item is selected:
                    continue
                item['rejection_reasons'] = [
                    'LESS_DIRECT_STRUCTURAL_APPLICABILITY_THAN_SELECTED'
                    if ranks[item['candidate_id']][:3] == best_rank[:3]
                    else 'BROADER_SCOPE_THAN_SELECTED'
                ]
                rejected.append(item)
            for item in invalid:
                if item not in rejected:
                    rejected.append(item)

    # Preserve the selected source separately; all other structurally
    # applicable candidates retain explicit rejection reasons.
    if selected is not None:
        rejected.extend(item for item in candidates if item is not selected and item not in rejected)
    rejected = list({item['candidate_id']: item for item in rejected}.values())
    return {
        'denominator_scope_resolved': selected is not None,
        'denominator_exact': int(selected['value_exact']) if selected is not None else None,
        'denominator_source_anchor': selected['source_anchor'] if selected is not None else None,
        'denominator_provenance': {
            'resolution_status': resolution_status,
            'resolution_reason': resolution_reason,
            'relationship_scope': scope,
            'selected_denominator': selected,
            'rejected_competing_denominators': rejected,
        },
        'skip_reasons': list(dict.fromkeys(skip_reasons)),
    }

