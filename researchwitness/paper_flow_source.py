"""Conservative JATS prose adapter for the sample-flow arithmetic helper.

This adapter recognizes only a single-paragraph flow shape. It does not join
counts across sections, tables, captions, or figures, and it does not infer
disjointness from a list of exclusion reasons.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .paper_document import Paragraph, PaperDocument, SourceAnchor
from .paper_flow import (
    FlowEdge,
    FlowNode,
    FlowOperation,
    FlowRelation,
    FlowScope,
    check_flow_relation,
)


# Count syntax is deliberately integer-only and bounded. Comma and space
# grouping are accepted only in groups of three digits.
_COUNT_TEXT = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+|[0-9]{1,13})"
_COUNT = re.compile(r"(?P<count>" + _COUNT_TEXT + r")(?![0-9.,/])")
_UNIT_TEXT = r"participants?|individuals?|persons?|people|patients?|records?|reports?|studies"
_UNIT = re.compile(r"\b(?P<unit>" + _UNIT_TEXT + r")\b", re.IGNORECASE)
_TOTAL = re.compile(
    r"\b(?:of|among)\s+the\s+" + _COUNT_TEXT
    + r"\s+(?P<context>[^.;:]{0,120}?)\b(?P<unit>" + _UNIT_TEXT + r")\b",
    re.IGNORECASE,
)
_EXCLUDED = re.compile(r"\bwe\s+(?:then\s+)?excluded\b", re.IGNORECASE)
_INCLUDED = re.compile(
    r"\bfinally\s*,?\s*" + _COUNT_TEXT + r"\s+(?P<context>[^.;:]{0,120}?)"
    + r"\b(?P<unit>" + _UNIT_TEXT + r")\b[^.;]{0,160}?\b(?:were|was)\s+included\b",
    re.IGNORECASE,
)

# Only list separators followed immediately by another integer can start a new
# exclusion operand. A comma inside 1,234 is therefore never a list separator.
_EXCLUSION_SEPARATOR = re.compile(
    r"(?:,\s+(?:and\s+)?(?=" + _COUNT_TEXT + r"\s)|;\s*(?:and\s+)?(?="
    + _COUNT_TEXT + r"\s)|\s+and\s+(?=" + _COUNT_TEXT + r"\s))",
    re.IGNORECASE,
)
_EXCLUSION_ITEM = re.compile(
    r"^\s*(?:and\s+)?(?P<count>" + _COUNT_TEXT + r")\s+(?P<description>.{1,180})$",
    re.IGNORECASE,
)
_ITEM_REASON_START = re.compile(
    r"^(?:with\b|for\b|due\b|who\b|that\b|aged?\b|under\b|younger\b|older\b|"
    r"no\b|without\b|having\b|because\b|from\b|in\b|at\b|by\b|as\b|based\b)",
    re.IGNORECASE,
)

_DISJOINT = re.compile(r"\b(?:mutually\s+exclusive|non[ -]?overlapping|disjoint)\b", re.IGNORECASE)
_EXHAUSTIVE = re.compile(r"\bexhaustive\b|\bexhaust(?:s|ed|ing)?\s+all\b", re.IGNORECASE)
_REMAINDER_INCLUDED = re.compile(
    r"\b(?:all|the)\s+remaining\s+(?:participants?|individuals?|persons?|people|patients?|"
    r"records?|reports?|studies)\s+(?:were|was)\s+included\b",
    re.IGNORECASE,
)
_SEQUENTIAL = re.compile(
    r"\b(?:each\s+subsequent\s+exclusion|subsequent\s+exclusions?|"
    r"sequentially\s+excluded|exclusions?\s+were\s+applied\s+sequentially)\b"
    r".{0,100}?\b(?:from|to|against)\s+(?:the\s+)?remaining\b",
    re.IGNORECASE,
)
_CONFLICTING_RELATION = re.compile(
    r"\b(?:may|might|could|can)\s+overlap\b|\bnot\s+(?:necessarily\s+)?disjoint\b|"
    r"\bnot\s+exhaustive\b|\badditional\s+exclusions?\s+(?:may|were|are)\b",
    re.IGNORECASE,
)
_GROUP = re.compile(
    r"\b(?P<forward>[a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*){0,2})\s+(?:arm|group)\b|"
    r"\b(?:arm|group)\s+(?P<reverse>[a-z0-9_-]+)\b",
    re.IGNORECASE,
)
_TIMEPOINT = re.compile(
    r"\b(?:baseline|follow[ -]?up|week\s+[0-9]{1,4}|month\s+[0-9]{1,4}|year\s+[0-9]{1,4})\b",
    re.IGNORECASE,
)
_NAMED_POPULATION = re.compile(
    r"\b(?:cohort|study\s+population|trial\s+population|study\s+cohort)\s+"
    r"(?P<label>[A-Za-z0-9_-]+)\b",
    re.IGNORECASE,
)
_GENERIC_POPULATION_WORDS = {"all", "cohort", "participants", "participant", "study", "the", "total"}
_UNIT_ALIASES = {
    "participant": "participant", "participants": "participant",
    "individual": "participant", "individuals": "participant",
    "person": "participant", "persons": "participant", "people": "participant",
    "patient": "patient", "patients": "patient",
    "record": "record", "records": "record",
    "report": "report", "reports": "report",
    "study": "study", "studies": "study",
}

MAX_PARAGRAPH_CHARS = 20_000
MAX_EXCLUSION_OPERANDS = 32
MAX_COUNT = 1_000_000_000_000
MAX_MAPPED_RELATIONS = 256


@dataclass(frozen=True, slots=True)
class FlowSourceOperand:
    """A parsed count and the source element that contains its quote."""

    identifier: str
    role: str
    count: int
    unit: str
    population: str
    group: str
    timepoint: str
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowPopulation:
    """Population identity supplied by one paragraph-local flow assertion."""

    identifier: str
    label: str
    count_unit: str
    group: str
    timepoint: str
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowStage:
    """A numbered stage in the recognized single-paragraph flow."""

    identifier: str
    label: str
    count: int
    count_unit: str
    scope: FlowScope
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowTransition:
    """A source-local transition, including its explicitness and scope proof."""

    source_stage: str
    target_stage: str
    operation: str | None
    explicit: bool
    disjoint: bool | None
    exhaustive: bool | None
    scope: FlowScope
    source_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowExclusion:
    """One listed exclusion count, reason, and its two source anchors."""

    identifier: str
    count: int
    count_unit: str
    population: str
    reason: str
    group: str
    timepoint: str
    count_anchor: SourceAnchor
    reason_anchor: SourceAnchor


@dataclass(frozen=True, slots=True)
class FlowArithmeticRelation:
    """The explicitly evidenced arithmetic proposition over flow operands."""

    total_operand: str
    exclusion_operands: tuple[str, ...]
    included_operand: str
    operator: str | None
    explicit: bool
    disjoint: bool | None
    exhaustive: bool | None
    sequential: bool
    source_anchor: SourceAnchor
    operand_anchors: tuple[SourceAnchor, ...]


@dataclass(frozen=True, slots=True)
class MappedSampleFlow:
    """One source-local sample-flow relation and its conservative result.

    Statuses are ``FLOW_BALANCED``, ``FLOW_ARITHMETIC_CANDIDATE``,
    ``FLOW_RELATION_AMBIGUOUS``, or ``UNSUPPORTED``. A candidate is emitted
    only after explicit relation language and matching operand scope are
    established. ``relation`` is present only when the source mapper could
    form a bounded graph; ``arithmetic`` is the existing helper's result.
    """

    status: str
    reason: str | None
    operands: tuple[FlowSourceOperand, ...]
    relation_anchor: SourceAnchor
    relation: FlowRelation | None
    arithmetic: dict[str, Any] | None
    population: FlowPopulation | None = None
    stages: tuple[FlowStage, ...] = ()
    transitions: tuple[FlowTransition, ...] = ()
    exclusions: tuple[FlowExclusion, ...] = ()
    arithmetic_relation: FlowArithmeticRelation | None = None


def _canonical_unit(raw: str) -> str:
    return _UNIT_ALIASES[raw.casefold()]


def _parse_count(raw: str) -> int | None:
    digits = re.sub(r"[\s,]", "", raw)
    if not digits.isdigit() or len(digits) > 13:
        return None
    value = int(digits)
    if value > MAX_COUNT:
        return None
    return value


def _anchor_quote(paragraph: Paragraph, start: int, end: int) -> SourceAnchor:
    """Bind an operand quote to its source paragraph without inventing bytes.

    JATS Paragraph.text is a whitespace-normalized projection. Its SourceAnchor
    has an XML element path but no original byte offsets, so this adapter keeps
    the precise projected quote and the original hash/path and leaves offsets
    unset.
    """
    text = paragraph.text
    context_start = max(0, start - 36)
    context_end = min(len(text), end + 36)
    while context_start > 0 and not text[context_start - 1].isspace():
        context_start -= 1
    while context_end < len(text) and not text[context_end].isspace():
        context_end += 1
    quote = text[context_start:context_end][:1000]
    return SourceAnchor(
        source_file=paragraph.source_anchor.source_file,
        source_sha256=paragraph.source_anchor.source_sha256,
        source_format=paragraph.source_anchor.source_format,
        element_path=paragraph.source_anchor.element_path,
        quote=quote,
    )


def _population_label(text: str, unit_start: int) -> str:
    named = _NAMED_POPULATION.search(text)
    if named is not None:
        return named.group("label").casefold()
    before_unit = text[:unit_start]
    words = re.findall(r"[A-Za-z0-9_-]+", before_unit.casefold())
    meaningful = [word for word in words if word not in _GENERIC_POPULATION_WORDS]
    return " ".join(meaningful[-3:]) or "paragraph-cohort"


def _groups(text: str) -> set[str]:
    labels: set[str] = set()
    for match in _GROUP.finditer(text):
        label = (match.group("forward") or match.group("reverse") or "").casefold()
        label = " ".join(word for word in label.split() if word not in {"the", "study"})
        if label:
            labels.add(label)
    return labels


def _operand_timepoints(text: str) -> set[str]:
    """Read a timepoint only when it qualifies a count unit, not its reason."""
    found: set[str] = set()
    for unit_match in _UNIT.finditer(text):
        suffix = text[unit_match.end():unit_match.end() + 64]
        match = _TIMEPOINT.search(suffix)
        if match is not None and len(suffix[:match.start()]) <= 36:
            found.add(" ".join(match.group(0).casefold().split()))
    return found


def _list_items(text: str) -> list[tuple[re.Match[str], int, int]]:
    pieces: list[tuple[str, int, int]] = []
    start = 0
    for separator in _EXCLUSION_SEPARATOR.finditer(text):
        pieces.append((text[start:separator.start()], start, separator.start()))
        start = separator.end()
    pieces.append((text[start:], start, len(text)))

    results: list[tuple[re.Match[str], int, int]] = []
    for piece, offset, end in pieces:
        match = _EXCLUSION_ITEM.match(piece)
        if match is None:
            # The source may continue with a relation cue after the exclusion
            # list. Such trailing text is not another operand.
            continue
        description = match.group("description").strip()
        if not _UNIT.match(description) and not _ITEM_REASON_START.match(description):
            continue
        results.append((match, offset, end))
    return results


def _typed_entities(
    operands: tuple[FlowSourceOperand, ...],
    exclusions: tuple[FlowExclusion, ...],
    relation_anchor: SourceAnchor,
    *,
    disjoint: bool | None,
    exhaustive: bool | None,
    sequential: bool,
) -> dict[str, Any]:
    total = operands[0]
    included = operands[-1]
    population = FlowPopulation(
        "population-1", total.population, total.unit, total.group, total.timepoint, total.source_anchor,
    )
    stages = [FlowStage(
        "total", "starting_population", total.count, total.unit,
        FlowScope(total.population, total.group, total.timepoint), total.source_anchor,
    )]
    stages.extend(
        FlowStage(exclusion.identifier, "excluded", exclusion.count, exclusion.count_unit,
                  FlowScope(exclusion.population, exclusion.group, exclusion.timepoint),
                  exclusion.count_anchor)
        for exclusion in exclusions
    )
    stages.append(FlowStage("included", "included_population", included.count,
                             included.unit,
                             FlowScope(included.population, included.group, included.timepoint),
                             included.source_anchor))

    base_scope = FlowScope(total.population, total.group, total.timepoint)
    explicit_relation = disjoint is True and exhaustive is True
    exclusion_operation = (
        "subtract_remaining" if sequential else "subtract"
    ) if explicit_relation else None
    transitions = [
        FlowTransition("total", exclusion.identifier,
                       exclusion_operation, explicit_relation, disjoint, exhaustive,
                       FlowScope(exclusion.population, exclusion.group, exclusion.timepoint),
                       relation_anchor)
        for exclusion in exclusions
    ]
    transitions.append(FlowTransition(
        "total", "included", "equals_after_operations" if explicit_relation else None,
        explicit_relation, disjoint, exhaustive, base_scope, relation_anchor,
    ))
    arithmetic_relation = FlowArithmeticRelation(
        "total", tuple(exclusion.identifier for exclusion in exclusions), "included",
        "subtract" if explicit_relation else None, explicit_relation,
        disjoint, exhaustive, sequential, relation_anchor,
        tuple(operand.source_anchor for operand in operands),
    )
    return {
        "population": population,
        "stages": tuple(stages),
        "transitions": tuple(transitions),
        "exclusions": exclusions,
        "arithmetic_relation": arithmetic_relation,
    }


def _ambiguous(
    reason: str,
    paragraph: Paragraph,
    operands: tuple[FlowSourceOperand, ...] = (),
    relation_anchor: SourceAnchor | None = None,
    relation: FlowRelation | None = None,
    arithmetic: dict[str, Any] | None = None,
    status: str = "FLOW_RELATION_AMBIGUOUS",
    entities: dict[str, Any] | None = None,
) -> MappedSampleFlow:
    return MappedSampleFlow(
        status=status,
        reason=reason,
        operands=operands,
        relation_anchor=relation_anchor or paragraph.source_anchor,
        relation=relation,
        arithmetic=arithmetic,
        **(entities or {}),
    )


def _source_flow(paragraph: Paragraph) -> MappedSampleFlow | None:
    text = paragraph.text
    if len(text) > MAX_PARAGRAPH_CHARS:
        if _TOTAL.search(text) and _EXCLUDED.search(text) and _INCLUDED.search(text):
            return _ambiguous("FLOW_PARAGRAPH_EXCEEDS_LIMIT", paragraph, status="UNSUPPORTED")
        return None

    total_match = _TOTAL.search(text)
    excluded_match = _EXCLUDED.search(text)
    included_match = _INCLUDED.search(text)
    if total_match is None or excluded_match is None or included_match is None:
        return None
    if not (total_match.end() <= excluded_match.start() < included_match.start()):
        return _ambiguous("FLOW_OPERAND_ORDER_UNSUPPORTED", paragraph, status="UNSUPPORTED")

    total_count_match = _COUNT.search(text, total_match.start())
    included_count_match = _COUNT.search(text, included_match.start())
    if total_count_match is None or included_count_match is None:
        return _ambiguous("FLOW_COUNT_UNSUPPORTED", paragraph, status="UNSUPPORTED")
    total = _parse_count(total_count_match.group("count"))
    included = _parse_count(included_count_match.group("count"))
    if total is None or included is None:
        return _ambiguous("FLOW_COUNT_OUT_OF_BOUNDS", paragraph, status="UNSUPPORTED")

    exclusions_text_start = excluded_match.end()
    exclusions_text = text[exclusions_text_start:included_match.start()]
    item_matches = _list_items(exclusions_text)
    if len(item_matches) < 2:
        return _ambiguous("FLOW_NEEDS_TWO_EXCLUSIONS", paragraph, status="UNSUPPORTED")
    if len(item_matches) > MAX_EXCLUSION_OPERANDS:
        return _ambiguous("FLOW_EXCLUSION_LIMIT", paragraph, status="UNSUPPORTED")

    total_unit = _canonical_unit(total_match.group("unit"))
    included_unit = _canonical_unit(included_match.group("unit"))
    total_context_start = max(0, text.rfind(".", 0, total_match.start()) + 1)
    total_context = text[total_context_start:excluded_match.start()]
    included_context = text[included_match.start():included_match.end()]

    total_groups = _groups(total_context)
    included_groups = _groups(included_context)
    if len(total_groups) > 1 or len(included_groups) > 1:
        return _ambiguous("FLOW_GROUP_SCOPE_AMBIGUOUS", paragraph, status="UNSUPPORTED")
    total_group = next(iter(total_groups), None)
    included_group = next(iter(included_groups), total_group or "unstratified")

    total_times = _operand_timepoints(total_context)
    included_times = _operand_timepoints(included_context)
    if len(total_times) > 1 or len(included_times) > 1:
        return _ambiguous("FLOW_TIMEPOINT_SCOPE_AMBIGUOUS", paragraph, status="UNSUPPORTED")
    total_time = next(iter(total_times), "single-paragraph-flow")
    included_time = next(iter(included_times), total_time)

    total_context_after_count = text[total_count_match.end():excluded_match.start()]
    total_unit_offset = total_context_after_count.casefold().find(total_match.group("unit").casefold())
    population = _population_label(total_context_after_count, max(0, total_unit_offset))
    included_context_after_count = text[included_count_match.end():included_match.end()]
    included_unit_offset = included_context_after_count.casefold().find(included_match.group("unit").casefold())
    included_population = _population_label(included_context_after_count, max(0, included_unit_offset))
    if included_population == "paragraph-cohort":
        included_population = population

    operands: list[FlowSourceOperand] = [
        FlowSourceOperand(
            "total", "total", total, total_unit, population, total_group or "unstratified", total_time,
            _anchor_quote(paragraph, total_count_match.start("count"), total_count_match.end("count")),
        )
    ]
    exclusion_node_ids: list[str] = []
    exclusion_scope_mismatch = False
    exclusion_unit_mismatch = False
    source_exclusions: list[FlowExclusion] = []
    for index, (item_match, piece_offset, piece_end_offset) in enumerate(item_matches, start=1):
        item_count = _parse_count(item_match.group("count"))
        if item_count is None:
            return _ambiguous("FLOW_COUNT_OUT_OF_BOUNDS", paragraph, tuple(operands), status="UNSUPPORTED")
        piece_start = exclusions_text_start + piece_offset
        piece_end = exclusions_text_start + piece_end_offset
        piece = text[piece_start:piece_end]
        count_start = piece_start + item_match.start("count")
        count_end = piece_start + item_match.end("count")
        description = item_match.group("description")
        explicit_unit = _UNIT.match(description)
        unit = _canonical_unit(explicit_unit.group("unit")) if explicit_unit else total_unit
        group_set = _groups(piece)
        if len(group_set) > 1:
            exclusion_scope_mismatch = True
        group = next(iter(group_set), total_group or "unstratified")
        time_set = _operand_timepoints(piece)
        if len(time_set) > 1:
            exclusion_scope_mismatch = True
        timepoint = next(iter(time_set), total_time)
        piece_after_count = piece[item_match.end("count"):]
        unit_offset = (piece_after_count.casefold().find(explicit_unit.group("unit").casefold())
                       if explicit_unit else -1)
        item_population = (
            _population_label(piece_after_count, max(0, unit_offset)) if explicit_unit else population
        )
        if item_population == "paragraph-cohort":
            item_population = population
        if unit != total_unit:
            exclusion_unit_mismatch = True
        if (group != (total_group or "unstratified")
                or timepoint != total_time or item_population != population):
            exclusion_scope_mismatch = True
        identifier = f"exclusion-{index}"
        exclusion_node_ids.append(identifier)
        operands.append(FlowSourceOperand(
            identifier, "exclusion", item_count, unit, item_population, group, timepoint,
            _anchor_quote(paragraph, count_start, count_end),
        ))
        reason = description.strip()
        sentence_end = re.search(r"[.;](?:\s|$)", reason)
        if sentence_end is not None:
            reason = reason[:sentence_end.start()].rstrip()
        reason_start = piece_start + item_match.start("description")
        reason_anchor = _anchor_quote(paragraph, reason_start, reason_start + len(reason))
        source_exclusions.append(FlowExclusion(
            identifier, item_count, unit, item_population, reason, group, timepoint,
            _anchor_quote(paragraph, count_start, count_end), reason_anchor,
        ))

    operands.append(FlowSourceOperand(
        "included", "included", included, included_unit, included_population,
        included_group, included_time,
        _anchor_quote(paragraph, included_count_match.start("count"), included_count_match.end("count")),
    ))
    operand_tuple = tuple(operands)
    exclusion_tuple = tuple(source_exclusions)
    provisional_relation_anchor = _anchor_quote(
        paragraph, excluded_match.start(), included_match.end(),
    )
    provisional_entities = _typed_entities(
        operand_tuple, exclusion_tuple, provisional_relation_anchor,
        disjoint=None, exhaustive=None, sequential=False,
    )

    if total_unit != included_unit:
        return _ambiguous("FLOW_OPERAND_UNIT_MISMATCH", paragraph, operand_tuple,
                          relation_anchor=provisional_relation_anchor, status="UNSUPPORTED",
                          entities=provisional_entities)
    if exclusion_unit_mismatch:
        return _ambiguous("FLOW_OPERAND_UNIT_MISMATCH", paragraph, operand_tuple,
                          relation_anchor=provisional_relation_anchor, status="UNSUPPORTED",
                          entities=provisional_entities)
    if (included_population != population or included_group != (total_group or "unstratified")
            or included_time != total_time or exclusion_scope_mismatch):
        return _ambiguous("FLOW_OPERAND_SCOPE_MISMATCH", paragraph, operand_tuple,
                          relation_anchor=provisional_relation_anchor, status="UNSUPPORTED",
                          entities=provisional_entities)

    relation_start = exclusions_text_start
    relation_text = text[relation_start:included_match.start()]
    conflict = _CONFLICTING_RELATION.search(relation_text)
    disjoint = _DISJOINT.search(relation_text)
    exhaustive = _EXHAUSTIVE.search(relation_text)
    remainder = _REMAINDER_INCLUDED.search(relation_text)
    sequential = _SEQUENTIAL.search(relation_text)
    if conflict is not None:
        return _ambiguous(
            "FLOW_RELATION_CUE_CONFLICT", paragraph, operand_tuple,
            _anchor_quote(paragraph, relation_start + conflict.start(), relation_start + conflict.end()),
            entities=provisional_entities,
        )

    explicit_partition = disjoint is not None and exhaustive is not None and remainder is not None
    explicit_sequence = sequential is not None and remainder is not None
    if explicit_partition:
        cue_start = min(disjoint.start(), exhaustive.start(), remainder.start())
        cue_end = max(disjoint.end(), exhaustive.end(), remainder.end())
    elif explicit_sequence:
        cue_start = min(sequential.start(), remainder.start())
        cue_end = max(sequential.end(), remainder.end())
    else:
        return _ambiguous(
            "FLOW_DISJOINTNESS_EXHAUSTIVENESS_OR_SEQUENCE_NOT_EXPLICIT",
            paragraph, operand_tuple,
            _anchor_quote(paragraph, relation_start, included_match.end()),
            entities=provisional_entities,
        )

    relation_anchor = _anchor_quote(paragraph, relation_start + cue_start, relation_start + cue_end)
    typed_entities = _typed_entities(
        operand_tuple, exclusion_tuple, relation_anchor,
        disjoint=True, exhaustive=True, sequential=explicit_sequence,
    )
    scope = FlowScope(population, total_group or "unstratified", total_time)
    nodes = [FlowNode("total", "starting population", total, scope, operands[0].source_anchor)]
    for operand in operands[1:-1]:
        nodes.append(FlowNode(operand.identifier, "excluded", operand.count, scope, operand.source_anchor))
    nodes.append(FlowNode("included", "included population", included, scope, operands[-1].source_anchor))
    edges = [
        FlowEdge("total", operand.identifier,
                 "subtract_remaining" if explicit_sequence else "subtract",
                 True, True, True, relation_anchor)
        for operand in operands[1:-1]
    ]
    edges.append(FlowEdge("total", "included", "equals_after_operations", True, True, True, relation_anchor))
    relation = FlowRelation(
        tuple(nodes), tuple(edges),
        FlowOperation("included", tuple(["total", *exclusion_node_ids]), "subtract", True),
    )
    arithmetic = check_flow_relation(relation)
    return MappedSampleFlow(
        status=arithmetic["status"],
        reason=arithmetic.get("reason"),
        operands=tuple(operands),
        relation_anchor=relation_anchor,
        relation=relation,
        arithmetic=arithmetic,
        **typed_entities,
    )


def map_jats_sample_flows(
    document: PaperDocument, *, limit: int = MAX_MAPPED_RELATIONS,
) -> tuple[MappedSampleFlow, ...]:
    """Map the supported single-paragraph JATS flow form into arithmetic.

    The function returns one result for each paragraph with the narrow
    ``Of the N <unit> ... we excluded ... Finally, M <unit> were included``
    shape. Relation cues must explicitly establish disjoint/exhaustive
    exclusions plus inclusion of the remainder, or explicit sequential
    subtraction plus inclusion of the remainder. Other flow families and
    source formats are not inferred here.
    """
    if document.source_format != "jats_xml":
        return ()
    if type(limit) is not int or limit < 1 or limit > MAX_MAPPED_RELATIONS + 1:
        raise ValueError(f"limit must be from 1 through {MAX_MAPPED_RELATIONS + 1}")
    results = []
    for paragraph in document.paragraphs:
        if paragraph.source_anchor.source_format != "jats_xml":
            continue
        mapped = _source_flow(paragraph)
        if mapped is not None:
            results.append(mapped)
            if len(results) == limit:
                break
    return tuple(results)
