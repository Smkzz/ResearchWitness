"""Narrow source mapper for explicitly labelled PRISMA record counts.

Only a single JATS paragraph containing the labelled sequence ``records
identified: N; duplicates removed: D; records screened: S`` is checked. This
does not inspect diagram contents, join stages across passages, or equate
records, reports, and studies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from .paper_document import PaperDocument, Paragraph, SourceAnchor


MAX_PARAGRAPH_CHARS = 8_000
MAX_RECORD_COUNT = 1_000_000_000_000
MAX_RELATIONS = 256
_COUNT = r"(?P<{name}>(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?:[\u00a0\u202f ][0-9]{3})+|[0-9]{1,13}))"


def _count_pattern(name: str) -> str:
    return _COUNT.replace('{name}', name)


_SEQUENCE = re.compile(
    r"\brecords?\s+identified\s*[:(]\s*" + _count_pattern("identified") + r"\s*\)?\s*[;,]\s*"
    r"duplicates?\s+removed\s*[:(]\s*" + _count_pattern("duplicates") + r"\s*\)?\s*[;,]\s*"
    r"records?\s+screened\s*[:(]\s*" + _count_pattern("screened") + r"\s*\)?"
    r"(?![0-9])",
    re.IGNORECASE,
)
_RELATED_STAGE = re.compile(
    r"\b(?:records?\s+(?:identified|screened)|duplicates?\s+removed|"
    r"full[- ]texts?\s+assessed|studies?\s+included|"
    r"qualitative synthesis|quantitative synthesis)\b",
    re.IGNORECASE,
)
_INCOMPATIBLE_SCOPE = re.compile(
    r"\b(?:multiple databases?|PubMed|MEDLINE|Embase|Scopus|"
    r"full[- ]text|reports?\s+assessed|studies?\s+included|"
    r"qualitative|quantitative|overlap(?:ping)?|weighted|adjusted)\b",
    re.IGNORECASE,
)
_REVIEW_CONTEXT = re.compile(r"\b(?:PRISMA|systematic review|literature search)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MappedPrismaRelation:
    status: str
    reason: str | None
    records_identified: int | None
    duplicates_removed: int | None
    records_screened: int | None
    expected_screened: int | None
    difference: int | None
    source_anchors: tuple[tuple[str, SourceAnchor], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            'status': self.status,
            'reason': self.reason,
            'unit': 'records',
            'records_identified_exact': None if self.records_identified is None else str(self.records_identified),
            'duplicates_removed_exact': None if self.duplicates_removed is None else str(self.duplicates_removed),
            'records_screened_exact': None if self.records_screened is None else str(self.records_screened),
            'expected_screened_exact': None if self.expected_screened is None else str(self.expected_screened),
            'difference_exact': None if self.difference is None else str(self.difference),
            'source_anchors': [
                {'role': role, 'source_anchor': asdict(anchor)}
                for role, anchor in self.source_anchors
            ],
        }


def _quote_anchor(paragraph: Paragraph, start: int, end: int) -> SourceAnchor:
    text = paragraph.text
    left = max(0, start - 28)
    right = min(len(text), end + 28)
    quote = text[left:right][:1_000]
    source = paragraph.source_anchor
    return SourceAnchor(
        source_file=source.source_file,
        source_sha256=source.source_sha256,
        source_format=source.source_format,
        element_path=source.element_path,
        quote=quote,
    )


def _parse_count(raw: str) -> int | None:
    compact = re.sub(r"[\s,\u00a0\u202f]", "", raw)
    if not compact.isdecimal() or len(compact) > 13:
        return None
    value = int(compact)
    return value if value <= MAX_RECORD_COUNT else None


def _map_paragraph(paragraph: Paragraph) -> MappedPrismaRelation | None:
    text = paragraph.text
    if len(text) > MAX_PARAGRAPH_CHARS:
        if _RELATED_STAGE.search(text):
            zero = SourceAnchor(
                paragraph.source_anchor.source_file,
                paragraph.source_anchor.source_sha256,
                paragraph.source_anchor.source_format,
                paragraph.source_anchor.element_path,
                text[:1_000],
            )
            return MappedPrismaRelation(
                'UNSUPPORTED', 'PRISMA_PARAGRAPH_LIMIT', None, None, None, None, None,
                (('relation', zero),),
            )
        return None
    if not _RELATED_STAGE.search(text) or not _REVIEW_CONTEXT.search(text):
        return None
    if _INCOMPATIBLE_SCOPE.search(text):
        return MappedPrismaRelation(
            'UNSUPPORTED', 'PRISMA_SCOPE_OR_STAGE_AMBIGUOUS', None, None, None, None, None,
            (('relation', paragraph.source_anchor),),
        )
    matches = list(_SEQUENCE.finditer(text))
    if len(matches) != 1:
        return MappedPrismaRelation(
            'UNSUPPORTED', 'PRISMA_LABELLED_TRANSITION_NOT_RECOGNIZED', None, None, None, None, None,
            (('relation', paragraph.source_anchor),),
        )
    match = matches[0]
    values = tuple(_parse_count(match.group(name)) for name in ('identified', 'duplicates', 'screened'))
    if any(value is None for value in values):
        return MappedPrismaRelation(
            'UNSUPPORTED', 'PRISMA_COUNT_OUT_OF_BOUNDS', None, None, None, None, None,
            (('relation', paragraph.source_anchor),),
        )
    identified, duplicates, screened = values
    assert identified is not None and duplicates is not None and screened is not None
    if duplicates > identified:
        return MappedPrismaRelation(
            'UNSUPPORTED', 'PRISMA_DUPLICATES_EXCEED_IDENTIFIED_RECORDS',
            identified, duplicates, screened, identified - duplicates,
            screened - (identified - duplicates), (('relation', paragraph.source_anchor),),
        )
    expected = identified - duplicates
    roles = ('records_identified', 'duplicates_removed', 'records_screened')
    anchors = tuple(
        (role, _quote_anchor(paragraph, match.start(name), match.end(name)))
        for role, name in zip(roles, ('identified', 'duplicates', 'screened'), strict=True)
    )
    anchors += (('transition', _quote_anchor(paragraph, match.start(), match.end())),)
    difference = screened - expected
    return MappedPrismaRelation(
        'PRISMA_FLOW_ARITHMETIC_CANDIDATE' if difference else 'PRISMA_FLOW_BALANCED',
        None, identified, duplicates, screened, expected, difference, anchors,
    )


def map_jats_prisma_relations(
    document: PaperDocument, *, limit: int = MAX_RELATIONS,
) -> tuple[MappedPrismaRelation, ...]:
    """Map the supported explicitly labelled record-removal sequence."""
    if document.source_format != 'jats_xml':
        return ()
    if type(limit) is not int or limit < 1 or limit > MAX_RELATIONS + 1:
        raise ValueError(f'limit must be from 1 through {MAX_RELATIONS + 1}')
    results: list[MappedPrismaRelation] = []
    for paragraph in document.paragraphs:
        if paragraph.source_anchor.source_format != 'jats_xml':
            continue
        relation = _map_paragraph(paragraph)
        if relation is not None:
            results.append(relation)
            if len(results) == limit:
                break
    return tuple(results)
