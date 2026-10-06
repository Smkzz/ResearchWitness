"""Canonical source-aware document model for paper screening.

The model keeps source structure and provenance attached to content. Text views
are projections for navigation; they are not a replacement for table structure.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    source_file: str
    source_sha256: str
    source_format: str
    element_path: str
    quote: str
    start_byte: int | None = None
    end_byte: int | None = None


@dataclass(frozen=True, slots=True)
class NumericValue:
    surface: str
    exact: str
    unit: str | None = None
    display_precision: int | None = None


@dataclass(frozen=True, slots=True)
class Paragraph:
    text: str
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    hierarchy: tuple[str, ...]
    paragraphs: tuple[Paragraph, ...]
    child_sections: tuple[Section, ...]
    table_ids: tuple[str, ...]
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class TableCell:
    raw_text: str
    normalized_numeric_values: tuple[NumericValue, ...]
    row_identity: str
    column_identity: int
    effective_headers: tuple[str, ...]
    footnote_references: tuple[str, ...]
    cross_references: tuple[tuple[str, str], ...]
    scope_denominator_cues: tuple[str, ...]
    row_span: int
    column_span: int
    column_start: int
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class TableRow:
    row_group: str
    row_index: int
    cells: tuple[TableCell, ...]


@dataclass(frozen=True, slots=True)
class TableColumn:
    index: int
    header_hierarchy: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CellSpan:
    row_group: str
    row_index: int
    column_start: int
    row_span: int
    column_span: int
    raw_text: str


@dataclass(frozen=True, slots=True)
class TableFootnote:
    identifier: str | None
    label: str
    text: str
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class Figure:
    """A source-mapped JATS figure caption; embedded image content is not decoded."""

    label: str
    caption: str
    graphic_present: bool
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class Table:
    label: str
    caption: str
    table_id: str
    wrap_metadata: tuple[tuple[str, str], ...]
    header_hierarchy: tuple[tuple[str, ...], ...]
    rows: tuple[TableRow, ...]
    columns: tuple[TableColumn, ...]
    spans: tuple[CellSpan, ...]
    footnotes: tuple[TableFootnote, ...]
    source_anchor: SourceAnchor
    extraction_confidence: float
    structure_status: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NumericAssertion:
    value: str
    unit: str | None
    statistic_type: str
    numerator: str | None
    denominator: str | None
    population: str | None
    group: str | None
    outcome: str | None
    timepoint: str | None
    adjustment_status: str | None
    source_anchor: SourceAnchor
    structural_provenance: tuple[str, ...]

    @property
    def identity_key(self) -> tuple[str, ...] | None:
        """Return a strict cross-section identity only when all core dimensions exist."""
        required = (
            self.population, self.group, self.outcome, self.statistic_type,
            self.timepoint, self.unit, self.adjustment_status,
        )
        if any(value is None or not value.strip() for value in required):
            return None
        return tuple(value.casefold().strip() for value in required if value is not None)


@dataclass(frozen=True, slots=True)
class PaperDocument:
    model_version: str
    source_file: str
    source_sha256: str
    source_format: str
    title: str
    sections: tuple[Section, ...]
    paragraphs: tuple[Paragraph, ...]
    tables: tuple[Table, ...]
    numeric_assertions: tuple[NumericAssertion, ...]
    extraction_warnings: tuple[str, ...]
    figures: tuple[Figure, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the immutable model using JSON-compatible values."""
        return asdict(self)

    def text_projection(self) -> bytes:
        """Return narrative text only; table cells never enter this projection."""
        parts = [self.title] if self.title else []

        def visit(section: Section) -> None:
            if section.title:
                parts.append(section.title)
            parts.extend(paragraph.text for paragraph in section.paragraphs)
            for child in section.child_sections:
                visit(child)

        for section in self.sections:
            visit(section)
        return ("\n\n".join(part for part in parts if part.strip()) + "\n").encode("utf-8")
